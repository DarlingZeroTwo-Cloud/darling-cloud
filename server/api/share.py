"""分享 API：创建/列表/取消；免登录分享落地页 + 提取码 + 过期 + 次数限制"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.db import db
from core.deps import get_current_user
from core.security import gen_share_token, make_token, parse_token
from core.storage import blob_path

router = APIRouter(prefix="/api", tags=["shares"])

MIME = {
    ".jpg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".mp4": "video/mp4", ".webp": "video/webp", ".mp3": "audio/mpeg",
    ".pdf": "application/pdf", ".zip": "application/zip", ".txt": "text/plain",
    ".md": "text/markdown", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ShareIn(BaseModel):
    file_id: int
    password: str | None = None       # 提取码（不填则无）
    expire_hours: int | None = None   # 过期（小时，不填则永久）
    max_downloads: int | None = None  # 次数上限（不填则不限）
    allow_download: bool = True


def _share_ok(conn, share) -> bool:
    """校验分享是否仍有效（未过期、次数未达上限、文件未删）"""
    if share["expire_at"] and share["expire_at"] < datetime.now().isoformat():
        return False
    if share["max_downloads"] and share["downloads"] >= share["max_downloads"]:
        return False
    f = conn.execute("SELECT 1 FROM files WHERE id=? AND deleted_at IS NULL",
                     (share["file_id"],)).fetchone()
    return bool(f)


@router.post("/shares")
async def create_share(body: ShareIn, user: dict = Depends(get_current_user)):
    """创建分享链接（私有文件）"""
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=? AND owner_id=? AND is_public=0 AND deleted_at IS NULL",
                           (body.file_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        token = gen_share_token()
        expire = None
        if body.expire_hours:
            expire = (datetime.now() + timedelta(hours=body.expire_hours)).isoformat()
        cur = conn.execute(
            "INSERT INTO shares(owner_id, file_id, token, password, expire_at, max_downloads, allow_download) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (user["id"], body.file_id, token, body.password, expire,
             body.max_downloads, int(body.allow_download)))
        return {"share_id": cur.lastrowid, "token": token,
                "url": f"/s/{token}"}


@router.get("/shares")
async def my_shares(user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute(
            "SELECT s.*, f.name AS file_name, f.size AS file_size FROM shares s "
            "JOIN files f ON s.file_id=f.id WHERE s.owner_id=? ORDER BY s.id DESC",
            (user["id"],)).fetchall()
        return [dict(r) for r in rows]


@router.delete("/shares/{sid}")
async def delete_share(sid: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        row = conn.execute("SELECT id FROM shares WHERE id=? AND owner_id=?",
                           (sid, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "分享不存在")
        conn.execute("DELETE FROM shares WHERE id=?", (sid,))
        return {"ok": True}


# ---------- 免登录分享落地 ----------
@router.get("/s/{token}")
async def share_page(token: str):
    """分享落地信息（免登录）"""
    with db() as conn:
        s = conn.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
        if not s:
            raise HTTPException(404, "分享不存在")
        if not _share_ok(conn, s):
            raise HTTPException(410, "分享已过期或达到下载次数上限")
        f = conn.execute("SELECT * FROM files WHERE id=? AND deleted_at IS NULL",
                         (s["file_id"],)).fetchone()
        owner = conn.execute("SELECT username FROM users WHERE id=?", (s["owner_id"],)).fetchone()
        return {"token": s["token"], "name": f["name"], "size": f["size"],
                "is_dir": bool(f["is_dir"]), "owner": owner["username"] if owner else "",
                "has_password": bool(s["password"]),
                "expire_at": s["expire_at"], "downloads": s["downloads"],
                "max_downloads": s["max_downloads"], "allow_download": bool(s["allow_download"])}


class VerifyIn(BaseModel):
    password: str | None = None


@router.post("/s/{token}/verify")
async def share_verify(token: str, body: VerifyIn):
    """验证提取码 → 返回一次性下载令牌"""
    with db() as conn:
        s = conn.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
        if not s:
            raise HTTPException(404, "分享不存在")
        if not _share_ok(conn, s):
            raise HTTPException(410, "分享已失效")
        if s["password"] and s["password"] != (body.password or ""):
            raise HTTPException(403, "提取码错误")
        dl = make_token(int(s["id"]), 2)
        return {"download_token": dl}


@router.get("/s/{token}/download")
async def share_download(token: str, t: str | None = None):
    """免登录下载（需通过 verify 的令牌；无密码分享可直接带 t）"""
    with db() as conn:
        s = conn.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
        if not s:
            raise HTTPException(404, "分享不存在")
        if not _share_ok(conn, s):
            raise HTTPException(410, "分享已失效")
        if not s["allow_download"]:
            raise HTTPException(403, "分享已禁止下载")
        if s["password"]:
            # 需要验证令牌：token 载荷 = share id
            sid = parse_token(t or "")
            if sid != s["id"]:
                raise HTTPException(403, "需要提取码")
        f = conn.execute("SELECT * FROM files WHERE id=? AND deleted_at IS NULL",
                         (s["file_id"],)).fetchone()
        if not f:
            raise HTTPException(404, "文件已删除")
        conn.execute("UPDATE shares SET downloads=downloads+1 WHERE id=?", (s["id"],))
        conn.execute("UPDATE files SET download_count=download_count+1 WHERE id=?", (f["id"],))
        conn.execute("INSERT INTO share_logs(share_id) VALUES(?)", (s["id"],))
        if f["is_dir"]:
            # 文件夹分享 → zip 打包
            import io, zipfile
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                def add(fid: int, arc: str):
                    r = conn.execute("SELECT * FROM files WHERE id=? AND deleted_at IS NULL",
                                     (fid,)).fetchone()
                    if r["is_dir"]:
                        for k in conn.execute("SELECT * FROM files WHERE parent_id=? AND deleted_at IS NULL ORDER BY is_dir DESC, name",
                                              (fid,)).fetchall():
                            add(k["id"], f"{arc}{k['name']}/" if k["is_dir"] else f"{arc}{k['name']}")
                    else:
                        p = blob_path(r["sha256"])
                        if p.exists():
                            zf.write(p, arcname=arc)
                add(f["id"], f["name"] + "/")
            buf.seek(0)
            from fastapi.responses import Response
            return Response(content=buf.getvalue(), media_type="application/zip",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{f['name']}.zip"})
        p = blob_path(f["sha256"])
        if not p.exists():
            raise HTTPException(404, "物理文件缺失")
        from urllib.parse import quote
        disp = f"attachment; filename*=UTF-8''{quote(f['name'])}"
        return FileResponse(p, media_type=MIME.get(p.suffix.lower(), "application/octet-stream"),
                            headers={"Content-Disposition": disp}, filename=f["name"])
