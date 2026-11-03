"""安全：密码哈希（argon2）、JWT、文件名消毒、验证码"""
import io
import random
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from PIL import Image, ImageDraw, ImageFont

from core.config import JWT_SECRET, JWT_EXPIRE_HOURS

_ph = PasswordHasher()

_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4",
             "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2",
             "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"}


# ---------- 密码 ----------
def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except Exception:
        return False


# ---------- JWT ----------
def make_token(user_id: int, hours: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=hours or JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, JWT_SECRET, algorithm="HS256")


def parse_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        return None


# ---------- 文件名消毒 ----------
def sanitize_name(name: str) -> str:
    name = _ILLEGAL.sub("_", name).strip().strip(".")
    if not name or name.lower() in _RESERVED or name in (".", ".."):
        raise ValueError("非法文件名")
    return name[:255]


# ---------- 验证码（图形 + 人机，轻量友好） ----------
def gen_captcha() -> tuple[str, bytes]:
    """返回 (answer, png_bytes)。算术题验证码，轻量不刁难。"""
    a, b = random.randint(1, 9), random.randint(1, 9)
    op = random.choice(["+", "-"])
    if op == "-" and a < b:
        a, b = b, a
    answer = str(a + b if op == "+" else a - b)
    text = f"{a} {op} {b} = ?"

    w, h = 140, 48
    img = Image.new("RGB", (w, h), (245, 247, 255))
    draw = ImageDraw.Draw(img)
    for _ in range(3):
        draw.line([(random.randint(0, w), random.randint(0, h)),
                   (random.randint(0, w), random.randint(0, h))],
                  fill=(180, 190, 230), width=1)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    x = 14
    for ch in text:
        draw.text((x, random.randint(8, 14)), ch, fill=(40, 70, 180), font=font)
        x += 22
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return answer, buf.getvalue()


def gen_captcha_id() -> str:
    return secrets.token_hex(8)


def gen_share_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def gen_extract_code() -> str:
    return f"{random.randint(0, 9999):04d}"
