"""上传 API：分片上传 / 秒传 / 断点续传"""
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import CHUNK_SIZE, MAX_FILE_SIZE, TMP_DIR
from core.db import db
from core.deps import get_current_user
from core.security import sanitize_name
from core.storage import (blob_exists, cleanup_upload, compute_sha256, merge_chunks,
                          ref_count, store_blob, upload_dir)

router = APIRouter(prefix="/api/upload", tags=["upload"])


class InitIn(BaseModel):
    name: str
    size: int
    is_public: bool = False
    parent_id: int | None = 0
    category_id: int | None = None
    desc_text: str | None = None
    sha256: str | None = None


class CompleteIn(BaseModel):
    sha256: str


def _check_quota(conn, user: dict, size: int, is_public: bool) -> None:
    grp = user["group"]
    quota = grp.get("pub_quota" if is_public else "priv_quota", 0)
    used = conn.execute(
        "SELECT COALESCE(SUM(size),0) s FROM files WHERE owner_id=? AND is_public=? AND is_dir=0 AND deleted_at IS NULL",
        (user["id"], int(is_public))).fetchone()["s"]
    if quota > 0 and used + size > quota:
        raise HTTPException(413, "空间配额不足")


@router.post("/init")
async def init_upload(body: InitIn, user: dict = Depends(get_current_user)):
    """初始化上传。sha256 已存在 → 秒传（直接返回 complete）。
    chunk_size 8MB；返回已接收分片（断点续传）。"""
    name = sanitize_name(body.name)
    size = body.size
    if size <= 0 or size > MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小不合法")
    if not user["group"].get("can_upload"):
        raise HTTPException(403, "当前用户组不可上传")

    with db() as conn:
        _check_quota(conn, user, size, body.is_public)
        # 秒传：物理文件已存在 → 直接落库
        if body.sha256 and blob_exists(body.sha256):
            cur = conn.execute(
                "INSERT INTO files(owner_id, name, parent_id, size, sha256, is_public, category_id, desc_text) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (user["id"], name, None if body.parent_id == 0 else body.parent_id,
                 size, body.sha256, int(body.is_public), body.category_id, body.desc_text))
            return {"instant": True, "file_id": cur.lastrowid}

        upload_id = secrets.token_hex(12)
        chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        conn.execute(
            "INSERT INTO uploads(id, owner_id, name, parent_id, is_public, category_id, desc_text, size, chunks) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (upload_id, user["id"], name, None if body.parent_id == 0 else body.parent_id,
             int(body.is_public), body.category_id, body.desc_text, size, chunks))
        d = upload_dir(upload_id)
        received = [i for i in range(chunks) if (d / str(i)).exists()]
        return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE, "chunks": chunks,
                "received": received, "instant": False}


@router.post("/{upload_id}/chunk/{index}")
async def upload_chunk(upload_id: str, index: int, file: UploadFile = File(...),
                       user: dict = Depends(get_current_user)):
    """上传单个分片（断点续传：已存在的分片跳过）"""
    with db() as conn:
        up = conn.execute("SELECT * FROM uploads WHERE id=? AND owner_id=?",
                          (upload_id, user["id"])).fetchone()
        if not up:
            raise HTTPException(404, "上传任务不存在")
    if index < 0 or index >= up["chunks"]:
        raise HTTPException(400, "分片序号越界")
    d = upload_dir(upload_id)
    part = d / str(index)
    if part.exists():
        return {"index": index, "skipped": True}
    with open(part, "wb") as out:
        while True:
            block = await file.read(CHUNK_SIZE)
            if not block:
                break
            out.write(block)
    if part.stat().st_size > CHUNK_SIZE:
        part.unlink()
        raise HTTPException(400, "分片超过 8MB")
    return {"index": index, "skipped": False}


@router.post("/{upload_id}/complete")
async def complete_upload(upload_id: str, body: CompleteIn,
                          user: dict = Depends(get_current_user)):
    """合并分片 → 去重落库 → 建文件记录"""
    with db() as conn:
        up = conn.execute("SELECT * FROM uploads WHERE id=? AND owner_id=?",
                          (upload_id, user["id"])).fetchone()
        if not up:
            raise HTTPException(404, "上传任务不存在")
        d = upload_dir(upload_id)
        got = sum(1 for i in range(up["chunks"]) if (d / str(i)).exists())
        if got != up["chunks"]:
            raise HTTPException(400, f"分片不完整：{got}/{up['chunks']}")

        merged = TMP_DIR / f"{upload_id}.merged"
        try:
            merge_chunks(upload_id, up["chunks"], merged)
            actual = compute_sha256(merged)
            if actual != body.sha256:
                raise HTTPException(400, "文件校验失败（SHA-256 不匹配）")
            # 配额二次校验（合并真实大小）
            _check_quota(conn, user, up["size"], bool(up["is_public"]))
            store_blob(merged, actual)
            cur = conn.execute(
                "INSERT INTO files(owner_id, name, parent_id, size, sha256, is_public, category_id, desc_text) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (up["owner_id"], up["name"], up["parent_id"], up["size"], actual,
                 up["is_public"], up["category_id"], up["desc_text"]))
            fid = cur.lastrowid
            conn.execute("DELETE FROM uploads WHERE id=?", (upload_id,))
        finally:
            cleanup_upload(upload_id)
            merged.unlink(missing_ok=True)
        return {"file_id": fid, "size": up["size"]}


@router.get("/{upload_id}/progress")
async def upload_progress(upload_id: str, user: dict = Depends(get_current_user)):
    """断点续传：查询已接收分片"""
    with db() as conn:
        up = conn.execute("SELECT * FROM uploads WHERE id=? AND owner_id=?",
                          (upload_id, user["id"])).fetchone()
        if not up:
            raise HTTPException(404, "上传任务不存在")
        d = upload_dir(upload_id)
        received = [i for i in range(up["chunks"]) if (d / str(i)).exists()]
        return {"upload_id": upload_id, "chunks": up["chunks"], "received": received}
