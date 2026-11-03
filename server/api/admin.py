"""管理端 API：仪表盘 / 用户 / 用户组 / 分类 / 全站设置（管理员专属）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.deps import get_current_user, require_admin
from core.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- 仪表盘 ----------
@router.get("/dashboard")
async def dashboard(_: dict = Depends(require_admin)):
    with db() as conn:
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        files = conn.execute("SELECT COUNT(*) c FROM files WHERE is_dir=0 AND deleted_at IS NULL").fetchone()["c"]
        size = conn.execute("SELECT COALESCE(SUM(size),0) s FROM files WHERE is_dir=0 AND deleted_at IS NULL").fetchone()["s"]
        today = conn.execute(
            "SELECT COUNT(*) c FROM files WHERE is_dir=0 AND date(created_at)=date('now')").fetchone()["c"]
        return {"users": users, "files": files, "total_size": size, "today_uploads": today}


# ---------- 用户管理 ----------
@router.get("/users")
async def list_users(_: dict = Depends(require_admin)):
    with db() as conn:
        rows = conn.execute(
            "SELECT u.id, u.username, u.email, u.nickname, u.is_active, u.created_at, g.name AS group_name, g.is_admin "
            "FROM users u JOIN groups g ON u.group_id=g.id ORDER BY u.id").fetchall()
        return [dict(r) for r in rows]


class UserPatchIn(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None
    new_password: str | None = Field(default=None, min_length=6, max_length=128)


@router.patch("/users/{uid}")
async def patch_user(uid: int, body: UserPatchIn, _: dict = Depends(require_admin)):
    """启用/停用用户、授予/撤销管理员、重置密码"""
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, "用户不存在")
        if body.is_active is not None:
            conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(body.is_active), uid))
        if body.new_password:
            conn.execute("UPDATE users SET pass_hash=? WHERE id=?",
                         (hash_password(body.new_password), uid))
        if body.is_admin is not None:
            admin_grp = conn.execute("SELECT id FROM groups WHERE is_admin=1").fetchone()
            normal_grp = conn.execute("SELECT id FROM groups WHERE is_admin=0 ORDER BY id LIMIT 1").fetchone()
            new_grp = admin_grp["id"] if body.is_admin else normal_grp["id"]
            conn.execute("UPDATE users SET group_id=? WHERE id=?", (new_grp, uid))
        return {"ok": True}


# ---------- 用户资源管理（管理员可看/清理任意用户文件） ----------
@router.get("/users/{uid}/files")
async def user_files(uid: int, _: dict = Depends(require_admin)):
    """列出某用户的全部文件（违规清理入口）"""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            raise HTTPException(404, "用户不存在")
        rows = conn.execute(
            "SELECT f.id, f.name, f.is_dir, f.size, f.is_public, f.category_id, f.desc_text, f.created_at "
            "FROM files f WHERE f.owner_id=? AND f.deleted_at IS NULL ORDER BY f.is_dir DESC, f.id DESC",
            (uid,)).fetchall()
        return [dict(r) for r in rows]


@router.delete("/users/{uid}/files/{fid}")
async def user_file_delete(uid: int, fid: int, _: dict = Depends(require_admin)):
    """管理员强制删除任意用户文件（软删入回收站，可恢复）"""
    with db() as conn:
        row = conn.execute("SELECT id FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                           (fid, uid)).fetchone()
        if not row:
            raise HTTPException(404, "文件不存在")
        conn.execute("UPDATE files SET deleted_at=datetime('now') WHERE id=?", (fid,))
        return {"ok": True}


# ---------- 用户组 / 配额 ----------
class GroupIn(BaseModel):
    can_upload: bool | None = None
    priv_quota: int | None = None
    pub_quota: int | None = None


@router.get("/groups")
async def list_groups(_: dict = Depends(require_admin)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM groups ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.put("/groups/{gid}")
async def update_group(gid: int, body: GroupIn, _: dict = Depends(require_admin)):
    with db() as conn:
        row = conn.execute("SELECT id FROM groups WHERE id=?", (gid,)).fetchone()
        if not row:
            raise HTTPException(404, "用户组不存在")
        conn.execute(
            "UPDATE groups SET can_upload=COALESCE(?, can_upload), priv_quota=COALESCE(?, priv_quota), "
            "pub_quota=COALESCE(?, pub_quota) WHERE id=?",
            (None if body.can_upload is None else int(body.can_upload),
             body.priv_quota, body.pub_quota, gid))
        return {"ok": True}


# ---------- 分类管理 ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    icon: str | None = None


@router.get("/categories")
async def list_categories(_: dict = Depends(require_admin)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/categories")
async def create_category(body: CategoryIn, _: dict = Depends(require_admin)):
    with db() as conn:
        if conn.execute("SELECT 1 FROM categories WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(400, "分类已存在")
        cur = conn.execute("INSERT INTO categories(name, icon) VALUES(?, ?)",
                           (body.name, body.icon))
        return {"id": cur.lastrowid, "name": body.name, "icon": body.icon}


@router.delete("/categories/{cid}")
async def delete_category(cid: int, _: dict = Depends(require_admin)):
    with db() as conn:
        row = conn.execute("SELECT id FROM categories WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "分类不存在")
        conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        conn.execute("UPDATE files SET category_id=NULL WHERE category_id=?", (cid,))
        return {"ok": True}


# ---------- 全站设置 ----------
class SettingsIn(BaseModel):
    allow_register: bool | None = None
    storage_backend: str | None = None
    captcha_level: str | None = None


@router.get("/settings")
async def get_settings(_: dict = Depends(require_admin)):
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
async def put_settings(body: SettingsIn, _: dict = Depends(require_admin)):
    with db() as conn:
        for key, val in [("allow_register", body.allow_register),
                         ("storage_backend", body.storage_backend),
                         ("captcha_level", body.captcha_level)]:
            if val is not None:
                conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (key, str(val)))
        return {"ok": True}
