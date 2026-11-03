"""认证 API：注册（验证码+人机）、登录、验证码"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field

from core.config import JWT_EXPIRE_HOURS
from core.db import db
from core.deps import get_current_user
from core.security import (gen_captcha, gen_captcha_id, hash_password,
                           make_token, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    email: EmailStr
    captcha_id: str
    captcha_answer: str


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = False


def _consume_captcha(conn, cid: str, answer: str) -> bool:
    row = conn.execute("SELECT * FROM captchas WHERE id=?", (cid,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM captchas WHERE id=?", (cid,))
    if row["expires_at"] < datetime.now().isoformat():
        return False
    return row["answer"].strip() == answer.strip()


def _count_users(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


@router.get("/captcha")
async def captcha():
    """图形验证码（算术题，PNG）"""
    answer, png = gen_captcha()
    cid = gen_captcha_id()
    with db() as conn:
        conn.execute("DELETE FROM captchas WHERE expires_at < datetime('now')")
        conn.execute(
            "INSERT INTO captchas(id, answer, kind, expires_at) VALUES(?, ?, 'math', ?)",
            (cid, answer, (datetime.now() + timedelta(minutes=5)).isoformat()),
        )
    return Response(content=png, media_type="image/png",
                    headers={"X-Captcha-Id": cid})


@router.post("/register")
async def register(body: RegisterIn):
    """注册。用户名唯一；首个注册账号自动成为管理员。"""
    username = body.username.strip()
    with db() as conn:
        allow = conn.execute(
            "SELECT value FROM settings WHERE key='allow_register'").fetchone()
        if allow and allow["value"] == "0":
            raise HTTPException(403, "站点已关闭自由注册")
        if not _consume_captcha(conn, body.captcha_id, body.captcha_answer):
            raise HTTPException(400, "验证码错误或已过期，请重试")
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(400, "用户名已存在")
        # 首个注册账号 = 管理员（group 3），否则普通用户（group 2）
        group_id = 3 if _count_users(conn) == 0 else 2
        cur = conn.execute(
            "INSERT INTO users(username, email, pass_hash, group_id) VALUES(?, ?, ?, ?)",
            (username, body.email, hash_password(body.password), group_id),
        )
        uid = cur.lastrowid
        token = make_token(uid, JWT_EXPIRE_HOURS)
        return {"token": token, "user": {"id": uid, "username": username,
                                         "is_admin": group_id == 3}}


@router.post("/login")
async def login(body: LoginIn):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?",
                           (body.username.strip(),)).fetchone()
        if not row or not verify_password(body.password, row["pass_hash"]):
            raise HTTPException(401, "用户名或密码错误")
        if not row["is_active"]:
            raise HTTPException(403, "账号已被停用")
        grp = conn.execute("SELECT * FROM groups WHERE id=?", (row["group_id"],)).fetchone()
        token = make_token(row["id"], 24 * 30 if body.remember else JWT_EXPIRE_HOURS)
        return {"token": token, "user": {
            "id": row["id"], "username": row["username"], "nickname": row["nickname"],
            "email": row["email"], "group": dict(grp)["name"] if grp else "",
            "is_admin": bool(grp["is_admin"]) if grp else False,
        }}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """根据 token 返回当前用户（前端刷新用）"""
    return {"user": {
        "id": user["id"], "username": user["username"], "nickname": user["nickname"],
        "email": user["email"], "group": user["group"].get("name", ""),
        "is_admin": bool(user["group"].get("is_admin")),
    }}
