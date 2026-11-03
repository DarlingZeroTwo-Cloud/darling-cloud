"""Darling Cloud v2 配置中心"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录（默认项目根 data/，可用环境变量覆盖）
DATA_DIR = Path(os.environ.get("DARLING_DATA", BASE_DIR / "data"))
FILES_DIR = DATA_DIR / "files"      # 按 SHA-256 去重存储
DB_PATH = DATA_DIR / "darling.db"   # SQLite
TMP_DIR = DATA_DIR / "tmp"          # 分片上传临时区

# 服务
HOST = os.environ.get("DARLING_HOST", "127.0.0.1")
PORT = int(os.environ.get("DARLING_PORT", "8080"))

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


def ensure_dirs() -> None:
    for d in (FILES_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)
