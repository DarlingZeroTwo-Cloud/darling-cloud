"""公开资源区：免登录浏览/搜索/下载；仅上传者可删"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core.db import db
from core.deps import get_current_user
from core.storage import blob_path

router = APIRouter(prefix="/api/public", tags=["public"])

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".pdf": "application/pdf", ".zip": "application/zip",
    ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
    ".py": "text/x-python", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/files")
async def public_files(keyword: str | None = None, category_id: int | None = None,
                       sort: str = "new"):
    """公开资源列表：免登录。keyword 匹配名称/简介；category 筛选。"""
    with db() as conn:
        sql = ("SELECT f.*, u.username AS owner FROM files f "
               "JOIN users u ON f.owner_id=u.id "
               "WHERE f.is_public=1 AND f.is_dir=0 AND f.deleted_at IS NULL")
        args = []
        if keyword:
            sql += " AND (f.name LIKE ? OR f.desc_text LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        if category_id:
            sql += " AND f.category_id=?"
            args.append(category_id)
        sql += " ORDER BY " + ("f.download_count DESC" if sort == "hot" else "f.created_at DESC")
        sql += " LIMIT 200"
        rows = conn.execute(sql, args).fetchall()
        return {"files": [dict(r) for r in rows],
                "categories": [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY id").fetchall()]}


@router.get("/files/{fid}/download")
async def public_download(fid: int):
    """公开文件免登录下载（计数）"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE id=? AND is_public=1 AND is_dir=0 AND deleted_at IS NULL",
            (fid,)).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在或已下架")
        if not row["sha256"]:
            raise HTTPException(400, "文件无实体")
        p = blob_path(row["sha256"])
        if not p.exists():
            raise HTTPException(404, "物理文件缺失")
        conn.execute("UPDATE files SET download_count=download_count+1 WHERE id=?", (fid,))
        mime = MIME.get(p.suffix.lower(), "application/octet-stream")
        from urllib.parse import quote
        disp = f"attachment; filename*=UTF-8''{quote(row['name'])}"
        return FileResponse(p, media_type=mime, headers={"Content-Disposition": disp},
                            filename=row["name"])


@router.delete("/files/{fid}")
async def public_delete(fid: int, user: dict = Depends(get_current_user)):
    """仅上传者可删除公开资源"""
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=? AND is_public=1 AND deleted_at IS NULL",
                           (fid,)).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        if row["owner_id"] != user["id"] and not user["group"].get("is_admin"):
            raise HTTPException(403, "只有上传者或管理员可以删除")
        conn.execute("UPDATE files SET deleted_at=datetime('now') WHERE id=?", (fid,))
        return {"ok": True}
