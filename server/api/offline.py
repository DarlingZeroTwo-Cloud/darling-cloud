"""离线下载：Aria2 磁力/HTTP 任务管理"""
import asyncio
import json
import re
import shutil
import uuid
from urllib import request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import FILES_DIR
from core.db import db
from core.deps import get_current_user
from core.security import sanitize_name

router = APIRouter(prefix="/api/offline", tags=["offline"])

ARIA2_RPC = "http://127.0.0.1:6800/jsonrpc"
ARIA2_SECRET = ""


class TaskIn(BaseModel):
    url: str
    is_public: bool = False


def _aria2_available() -> bool:
    return bool(shutil.which("aria2c"))


def _rpc(method: str, params: list) -> dict | None:
    """调用 aria2 JSON-RPC；失败返回 None"""
    if not _aria2_available():
        return None
    body = json.dumps({"jsonrpc": "2.0", "id": "dc", "method": method, "params": params}).encode()
    req = request.Request(ARIA2_RPC, data=body, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _is_magnet(url: str) -> bool:
    return url.startswith("magnet:") or url.startswith("ed2k:")


@router.post("")
async def add_task(body: TaskIn, user: dict = Depends(get_current_user)):
    """添加离线下载任务（HTTP/磁力）"""
    url = body.url.strip()
    if not url.startswith(("http://", "https://", "magnet:", "ed2k:")):
        raise HTTPException(400, "仅支持 HTTP/HTTPS/磁力链接")
    if not user["group"].get("can_upload"):
        raise HTTPException(403, "当前用户组不可上传")

    if not _aria2_available():
        raise HTTPException(503, "服务器未安装 aria2c，请先安装：apt install aria2 或 pacman -S aria2")

    # 下载目录 = 临时待转存区（完成后转存到用户空间）
    out_dir = FILES_DIR.parent / "offline" / f"u{user['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    gid = None
    if _is_magnet(url):
        r = _rpc("aria2.addUri", [[url], {"dir": str(out_dir), "seed-time": "0"}])
    else:
        r = _rpc("aria2.addUri", [[url], {"dir": str(out_dir)}])
    if r and "result" in r:
        gid = r["result"]

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO aria2_tasks(owner_id, url, gid, is_public, status) VALUES(?, ?, ?, ?, ?)",
            (user["id"], url, gid, int(body.is_public), "queued" if gid else "error"))
        return {"task_id": cur.lastrowid, "gid": gid}


@router.get("")
async def list_tasks(user: dict = Depends(get_current_user)):
    """任务列表（含进度）"""
    with db() as conn:
        rows = conn.execute("SELECT * FROM aria2_tasks WHERE owner_id=? ORDER BY id DESC",
                            (user["id"],)).fetchall()
        tasks = [dict(r) for r in rows]
    # 刷新活动任务进度
    for t in tasks:
        if t["gid"] and t["status"] in ("queued", "active", "paused"):
            r = _rpc("aria2.tellStatus", [t["gid"], ["status", "completedLength", "totalLength", "downloadSpeed"]])
            if r and "result" in r:
                res = r["result"]
                t["progress"] = round(int(res.get("completedLength", 0)) * 100 / max(int(res.get("totalLength", 1)), 1), 1)
                t["speed"] = int(res.get("downloadSpeed", 0))
                st = res.get("status")
                if st == "complete":
                    t["status"] = "complete"
                elif st in ("error", "removed"):
                    t["status"] = "error"
                else:
                    t["status"] = st
            with db() as conn2:
                conn2.execute("UPDATE aria2_tasks SET progress=?, speed=?, status=? WHERE id=?",
                              (t["progress"], t["speed"], t["status"], t["id"]))
    return tasks


@router.delete("/{tid}")
async def cancel_task(tid: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        row = conn.execute("SELECT * FROM aria2_tasks WHERE id=? AND owner_id=?",
                           (tid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在")
        if row["gid"]:
            _rpc("aria2.remove", [row["gid"]])
        conn.execute("UPDATE aria2_tasks SET status='canceled' WHERE id=?", (tid,))
        return {"ok": True}


class TransferIn(BaseModel):
    name: str | None = None
    parent_id: int | None = 0


@router.post("/{tid}/transfer")
async def transfer_task(tid: int, body: TransferIn,
                        user: dict = Depends(get_current_user)):
    """下载完成后转存到用户空间"""
    with db() as conn:
        row = conn.execute("SELECT * FROM aria2_tasks WHERE id=? AND owner_id=?",
                           (tid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在")
        if row["status"] != "complete":
            raise HTTPException(400, "任务尚未完成")
        out_dir = FILES_DIR.parent / "offline" / f"u{user['id']}"
        candidates = [p for p in out_dir.iterdir() if p.is_file()] if out_dir.exists() else []
        if not candidates:
            raise HTTPException(404, "下载产物不存在")
        p = candidates[0]
        fname = sanitize_name(body.name or p.name)
        size = p.stat().st_size
        import hashlib
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        from core.storage import blob_exists, store_blob
        if not blob_exists(sha):
            store_blob(p, sha)
        else:
            p.unlink(missing_ok=True)
        cur = conn.execute(
            "INSERT INTO files(owner_id, name, parent_id, size, sha256, is_public) VALUES(?, ?, ?, ?, ?, ?)",
            (user["id"], fname, None if body.parent_id == 0 else body.parent_id, size,
             sha, int(row["is_public"])))
        conn.execute("UPDATE aria2_tasks SET status='transferred', file_id=? WHERE id=?", (cur.lastrowid, tid))
        return {"file_id": cur.lastrowid, "name": fname}
