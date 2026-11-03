"""依赖注入：当前用户 / 管理员校验 / 游客模式"""
from fastapi import Depends, Header, HTTPException

from core.db import db
from core.security import parse_token


def get_current_user(authorization: str | None = Header(default=None)):
    """返回用户 dict；未登录抛 401"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    uid = parse_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "登录已过期")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=? AND is_active=1", (uid,)).fetchone()
        if not row:
            raise HTTPException(401, "用户不存在或已停用")
        user = dict(row)
        grp = conn.execute("SELECT * FROM groups WHERE id=?", (user["group_id"],)).fetchone()
        user["group"] = dict(grp) if grp else {}
        return user


def require_admin(user: dict = Depends(get_current_user)):
    if not user.get("group", {}).get("is_admin"):
        raise HTTPException(403, "需要管理员权限")
    return user
