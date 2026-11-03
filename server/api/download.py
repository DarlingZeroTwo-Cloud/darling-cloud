"""文件下载 / 打包 / 缩略图 / 回收站"""
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image

from core.config import TMP_DIR
from core.db import db
from core.deps import get_current_user
from core.storage import blob_path, delete_blob_if_unused, ref_count

router = APIRouter(prefix="/api", tags=["files"])

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".flac": "audio/flac", ".pdf": "application/pdf",
    ".zip": "application/zip", ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed", ".tar": "application/x-tar",
    ".gz": "application/gzip", ".txt": "text/plain", ".md": "text/markdown",
    ".json": "application/json", ".py": "text/x-python",
    ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _own_file(conn, fid: int, uid: int, include_trash: bool = False):
    q = "SELECT * FROM files WHERE id=? AND owner_id=?"
    if not include_trash:
        q += " AND deleted_at IS NULL"
    row = conn.execute(q, (fid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "文件不存在")
    return row


def _physical(row) -> Path:
    if not row["sha256"]:
        raise HTTPException(400, "文件无实体内容")
    p = blob_path(row["sha256"])
    if not p.exists():
        raise HTTPException(404, "物理文件缺失")
    return p


@router.get("/files/{fid}/download")
async def download_file(fid: int, user: dict = Depends(get_current_user)):
    """下载（支持 Range 断点续传）"""
    with db() as conn:
        row = _own_file(conn, fid, user["id"])
        if row["is_dir"]:
            raise HTTPException(400, "文件夹请用打包下载")
        conn.execute("UPDATE files SET download_count=download_count+1 WHERE id=?", (fid,))
        p = _physical(row)
        mime = MIME.get(p.suffix.lower(), "application/octet-stream")
        # 中文文件名转义（RFC 5987）
        disp = f"attachment; filename*=UTF-8''{quote(row['name'])}"
        return FileResponse(p, media_type=mime, headers={"Content-Disposition": disp},
                            filename=row["name"])


@router.get("/zip")
async def download_many(ids: str, user: dict = Depends(get_current_user)):
    """多选打包 zip 下载（ids 逗号分隔；含文件夹递归）"""
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        raise HTTPException(400, "未选择文件")
    buf = io.BytesIO()
    with db() as conn:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            def add(fid: int, arc: str):
                row = _own_file(conn, fid, user["id"])
                if row["is_dir"]:
                    kids = conn.execute(
                        "SELECT * FROM files WHERE parent_id=? AND owner_id=? AND deleted_at IS NULL ORDER BY is_dir DESC, name",
                        (fid, user["id"])).fetchall()
                    for k in kids:
                        add(k["id"], f"{arc}{k['name']}/" if k["is_dir"] else f"{arc}{k['name']}")
                else:
                    zf.write(_physical(row), arcname=arc)
            for fid in id_list:
                row = _own_file(conn, fid, user["id"])
                add(fid, row["name"] + ("/" if row["is_dir"] else ""))
    buf.seek(0)
    return Response(content=buf.getvalue(),
                    media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=darling-download.zip"})


@router.get("/files/{fid}/thumbnail")
async def thumbnail(fid: int, size: int = 256, user: dict = Depends(get_current_user)):
    """图片缩略图（Pillow，宽高自适应）"""
    with db() as conn:
        row = _own_file(conn, fid, user["id"])
        p = _physical(row)
    try:
        img = Image.open(p)
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=80)
        return Response(content=buf.getvalue(), media_type="image/jpeg")
    except Exception:
        raise HTTPException(400, "该文件不支持缩略图")


# ---------- 回收站 ----------
@router.get("/recycle")
async def list_recycle(user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE owner_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (user["id"],)).fetchall()
        return [dict(r) for r in rows]


@router.post("/recycle/{fid}/restore")
async def restore_file(fid: int, user: dict = Depends(get_current_user)):
    """恢复：若父目录仍存在则还原原位，否则回根目录"""
    with db() as conn:
        row = _own_file(conn, fid, user["id"], include_trash=True)
        pid = row["parent_id"]
        if pid is not None:
            parent = conn.execute(
                "SELECT id FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (pid, user["id"])).fetchone()
            if not parent:
                pid = None
        conn.execute("UPDATE files SET deleted_at=NULL, parent_id=? WHERE id=?",
                     (pid, fid))
        # 恢复其下子项（若同批被删）
        conn.execute("UPDATE files SET deleted_at=NULL WHERE owner_id=? AND parent_id=? AND deleted_at IS NOT NULL",
                     (user["id"], fid))
        return {"ok": True}


@router.delete("/recycle/{fid}")
async def delete_permanent(fid: int, user: dict = Depends(get_current_user)):
    """彻底删除（递归；引用归零才删物理文件）"""
    with db() as conn:
        row = _own_file(conn, fid, user["id"], include_trash=True)
        sha_list = []
        stack = [row]
        while stack:
            cur = stack.pop()
            kids = conn.execute("SELECT * FROM files WHERE parent_id=? AND owner_id=?",
                                (cur["id"], user["id"])).fetchall()
            stack.extend(kids)
            if cur["sha256"]:
                sha_list.append(cur["sha256"])
            conn.execute("DELETE FROM files WHERE id=? AND owner_id=?", (cur["id"], user["id"]))
        for sha in set(sha_list):
            delete_blob_if_unused(conn, sha)
        return {"ok": True}


@router.post("/recycle/clear")
async def clear_recycle(user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM files WHERE owner_id=? AND deleted_at IS NOT NULL",
                            (user["id"],)).fetchall()
        shas = []
        for r in rows:
            stack = [r]
            while stack:
                cur = stack.pop()
                kids = conn.execute("SELECT * FROM files WHERE parent_id=? AND owner_id=?",
                                    (cur["id"], user["id"])).fetchall()
                stack.extend(kids)
                if cur["sha256"]:
                    shas.append(cur["sha256"])
                conn.execute("DELETE FROM files WHERE id=? AND owner_id=?",
                             (cur["id"], user["id"]))
        for sha in set(shas):
            delete_blob_if_unused(conn, sha)
        return {"ok": True}


def quote(s: str) -> str:
    from urllib.parse import quote as _q
    return _q(s)
