"""文件 API（私有空间）：目录 CRUD / 重命名 / 移动 / 回收站"""
from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.deps import get_current_user
from core.security import sanitize_name

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_owned(conn, fid: int, uid: int):
    row = conn.execute("SELECT * FROM files WHERE id=? AND owner_id=?",
                       (fid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "文件不存在")
    return row


@router.get("")
async def list_files(parent_id: int | None = 0, user: dict = Depends(get_current_user)):
    """列出当前用户私有空间目录内容（回收站除外）"""
    with db() as conn:
        pid = None if parent_id == 0 else parent_id
        rows = conn.execute(
            "SELECT * FROM files WHERE owner_id=? AND is_public=0 AND deleted_at IS NULL "
            "AND parent_id IS ? ORDER BY is_dir DESC, name COLLATE NOCASE",
            (user["id"], pid)).fetchall()
        return [dict(r) for r in rows]


@router.post("/dir")
async def create_dir(name: str, parent_id: int | None = 0,
                     user: dict = Depends(get_current_user)):
    """新建文件夹（私有空间）"""
    name = sanitize_name(name)
    with db() as conn:
        pid = None if parent_id == 0 else parent_id
        if pid is not None:
            _get_owned(conn, pid, user["id"])
        cur = conn.execute(
            "INSERT INTO files(owner_id, name, parent_id, is_dir) VALUES(?, ?, ?, 1)",
            (user["id"], name, pid))
        row = conn.execute("SELECT * FROM files WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.patch("/{fid}")
async def update_file(fid: int, name: str | None = None, parent_id: int | None = None,
                      star: bool | None = None, user: dict = Depends(get_current_user)):
    """重命名 / 移动 / 星标"""
    with db() as conn:
        row = _get_owned(conn, fid, user["id"])
        if row["deleted_at"]:
            raise HTTPException(400, "文件在回收站")
        if name is not None:
            name = sanitize_name(name)
        if parent_id is not None and parent_id != 0:
            _get_owned(conn, parent_id, user["id"])
            # 禁止移入自身/子树
            pid = parent_id
            while pid is not None:
                if pid == fid:
                    raise HTTPException(400, "不能移动到自身内部")
                r = conn.execute("SELECT parent_id FROM files WHERE id=? AND owner_id=?",
                                 (pid, user["id"])).fetchone()
                pid = r["parent_id"] if r else None
        new_parent = None if parent_id == 0 else parent_id
        star_v = None if star is None else int(star)
        conn.execute(
            "UPDATE files SET name=COALESCE(?, name), parent_id=COALESCE(?, parent_id), "
            "star=COALESCE(?, star), updated_at=datetime('now') WHERE id=?",
            (name, new_parent, star_v, fid))
        return dict(_get_owned(conn, fid, user["id"]))


@router.delete("/{fid}")
async def trash_file(fid: int, user: dict = Depends(get_current_user)):
    """移入回收站（软删除，递归子项）"""
    with db() as conn:
        row = _get_owned(conn, fid, user["id"])
        stack = [row["id"]]
        while stack:
            cur = stack.pop()
            conn.execute("UPDATE files SET deleted_at=datetime('now') WHERE id=? AND owner_id=?",
                         (cur, user["id"]))
            kids = conn.execute("SELECT id FROM files WHERE parent_id=? AND owner_id=? AND deleted_at IS NULL",
                                (cur, user["id"])).fetchall()
            stack.extend(k["id"] for k in kids)
        return {"ok": True}


@router.get("/{fid}")
async def get_file(fid: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        return dict(_get_owned(conn, fid, user["id"]))
