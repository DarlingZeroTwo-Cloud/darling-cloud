"""Darling Cloud v2 配置中心"""
from pathlib import Path
import os, sys, shutil

BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录（默认项目根 data/，可用环境变量覆盖）
DATA_DIR = Path(os.environ.get("DARLING_DATA", BASE_DIR / "data"))
FILES_DIR = DATA_DIR / "files"      # 按 SHA-256 去重存储（本地后端）
REMOTE_DIR = Path(os.environ.get("DARLING_REMOTE", ""))  # 远程挂载扩容目录（另一台机器挂载，如 NFS/SFTP）
DB_PATH = DATA_DIR / "darling.db"   # SQLite
TMP_DIR = DATA_DIR / "tmp"          # 分片上传临时区
ARIA2_DIR = DATA_DIR / "aria2"      # aria2c 运行目录（.aria2 控制文件、下载临时文件）

# 服务
HOST = os.environ.get("DARLING_HOST", "127.0.0.1")
PORT = int(os.environ.get("DARLING_PORT", "8080"))

# aria2c RPC
ARIA2_RPC_PORT = int(os.environ.get("DARLING_ARIA2_PORT", "6800"))
ARIA2_RPC_SECRET = os.environ.get("DARLING_ARIA2_SECRET", "")


def find_aria2c() -> str:
    """按顺序找 aria2c：包内同目录 → frozen _MEIPASS → 环境变量 → PATH。返回可执行路径或空串。"""
    candidates = []
    exe = "aria2c.exe" if os.name == "nt" else "aria2c"
    # frozen 模式：exe 同目录（PyInstaller onefile 解包到 _MEIPASS，但我们把 aria2c 放在发布目录里，不是 _MEIPASS）
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / exe)
        candidates.append(Path(sys._MEIPASS) / exe)
    # 源码模式：项目根
    candidates.append(BASE_DIR.parent / exe)
    candidates.append(BASE_DIR / exe)
    # 环境变量
    env = os.environ.get("DARLING_ARIA2C")
    if env:
        candidates.append(Path(env))
    for c in candidates:
        try:
            if c.is_file() and os.access(c, os.X_OK):
                return str(c)
        except Exception:
            pass
    found = shutil.which("aria2c")
    return found or ""

# 上传
CHUNK_SIZE = 8 * 1024 * 1024        # 分片 8MB
MAX_FILE_SIZE = int(os.environ.get("DARLING_MAX_FILE", str(10 * 1024 * 1024 * 1024)))  # 默认 10GB

# 安全
JWT_SECRET = os.environ.get("DARLING_SECRET", "darling-cloud-dev-secret")
JWT_EXPIRE_HOURS = 24
TOKEN_LEN = 16                       # 分享 token 长度

# AI（Agnes AI，可选，v0.4 启用）
AGNES_BASE = os.environ.get("AGNES_BASE", "https://apihub.agnes-ai.com/v1")
AGNES_KEY = os.environ.get("AGNES_KEY", "")


def get_setting(key: str, default: str = "") -> str:
    """读全站设置（惰性导入避免循环依赖）"""
    from core.db import db
    try:
        with db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default
    except Exception:
        return default


def ensure_dirs() -> None:
    for d in (FILES_DIR, TMP_DIR, ARIA2_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if REMOTE_DIR:
        REMOTE_DIR.mkdir(parents=True, exist_ok=True)
