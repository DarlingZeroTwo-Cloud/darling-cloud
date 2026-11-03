"""用户 API：个人设置 / 修改密码 / 一键清缓存"""
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import TMP_DIR
from core.db import db
from core.deps import get_current_user
from core.security import hash_password, verify_password

router = APIRouter(prefix="/api/user", tags=["user"])


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)
    avatar: str | None = None


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


@router.patch("/me")
async def update_profile(body: ProfileIn, user: dict = Depends(get_current_user)):
    with db() as conn:
        conn.execute(
            "UPDATE users SET nickname=COALESCE(?, nickname), avatar=COALESCE(?, avatar) WHERE id=?",
            (body.nickname, body.avatar, user["id"]),
        )
        return {"ok": True}


@router.post("/password")
async def change_password(body: PasswordIn, user: dict = Depends(get_current_user)):
    with db() as conn:
        row = conn.execute("SELECT pass_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not verify_password(body.old_password, row["pass_hash"]):
            raise HTTPException(400, "原密码错误")
        conn.execute("UPDATE users SET pass_hash=? WHERE id=?",
                     (hash_password(body.new_password), user["id"]))
        return {"ok": True}


@router.post("/clear-cache")
async def clear_cache(user: dict = Depends(get_current_user)):
    """一键清缓存：清理临时分片区（各用户自己上传的残留）"""
    if TMP_DIR.exists():
        for p in TMP_DIR.iterdir():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    return {"ok": True, "cleared": True}


@router.get("/quota")
async def quota(user: dict = Depends(get_current_user)):
    """用量明细：私有/公开占用"""
    with db() as conn:
        priv = conn.execute(
            "SELECT COALESCE(SUM(size),0) AS s FROM files WHERE owner_id=? AND is_public=0 AND is_dir=0 AND deleted_at IS NULL",
            (user["id"],)).fetchone()["s"]
        pub = conn.execute(
            "SELECT COALESCE(SUM(size),0) AS s FROM files WHERE owner_id=? AND is_public=1 AND is_dir=0 AND deleted_at IS NULL",
            (user["id"],)).fetchone()["s"]
        grp = user["group"]
        return {
            "priv_used": priv, "priv_quota": grp.get("priv_quota", 0),
            "pub_used": pub, "pub_quota": grp.get("pub_quota", 0),
        }
