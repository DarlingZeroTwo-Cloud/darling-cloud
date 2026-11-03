"""SQLite 数据库：连接 + 建表（用户/用户组/文件/上传/验证码/设置）"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from core.config import DB_PATH

SCHEMA = """
-- 用户组（默认：游客/普通用户/管理员）
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    is_default  INTEGER NOT NULL DEFAULT 0,
    can_upload  INTEGER NOT NULL DEFAULT 1,
    priv_quota  INTEGER NOT NULL DEFAULT 5368709120,   -- 私有空间 5GB
    pub_quota   INTEGER NOT NULL DEFAULT 10737418240,  -- 公开空间 10GB
    is_admin    INTEGER NOT NULL DEFAULT 0
);

-- 用户
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL,
    pass_hash   TEXT NOT NULL,
    nickname    TEXT,
    avatar      TEXT,
    group_id    INTEGER NOT NULL DEFAULT 2,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(group_id) REFERENCES groups(id)
);

-- 文件/文件夹（私有空间；公开区复用 files + is_public 标记）
CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    parent_id   INTEGER,              -- NULL = 根
    is_dir      INTEGER NOT NULL DEFAULT 0,
    size        INTEGER NOT NULL DEFAULT 0,
    sha256      TEXT,
    mime        TEXT,
    is_public   INTEGER NOT NULL DEFAULT 0,  -- 1=公开区
    category_id INTEGER,
    desc_text   TEXT,                 -- 公开资源简介
    star        INTEGER NOT NULL DEFAULT 0,  -- 星标
    download_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT,                 -- 非空 = 回收站
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_files_owner  ON files(owner_id, parent_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_files_public ON files(is_public, deleted_at);

-- 分类（公开区）
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    icon        TEXT
);

-- 分片上传任务
CREATE TABLE IF NOT EXISTS uploads (
    id          TEXT PRIMARY KEY,
    owner_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    parent_id   INTEGER,
    is_public   INTEGER NOT NULL DEFAULT 0,
    category_id INTEGER,
    desc_text   TEXT,
    size        INTEGER NOT NULL,
    chunks      INTEGER NOT NULL,
    received    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id)
);

-- 分享链接
CREATE TABLE IF NOT EXISTS shares (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    file_id     INTEGER NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    password    TEXT,                 -- 提取码（可空）
    expire_at   TEXT,                 -- 过期时间（可空=永久）
    max_downloads INTEGER,            -- 次数上限（可空=不限）
    downloads   INTEGER NOT NULL DEFAULT 0,
    allow_download INTEGER NOT NULL DEFAULT 1,
    allow_upload   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id),
    FOREIGN KEY(file_id) REFERENCES files(id)
);

-- 离线下载任务（Aria2）
CREATE TABLE IF NOT EXISTS aria2_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    url         TEXT NOT NULL,
    gid         TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued/active/paused/complete/error
    target_dir  INTEGER,
    is_public   INTEGER NOT NULL DEFAULT 0,
    progress    REAL NOT NULL DEFAULT 0,
    speed       INTEGER NOT NULL DEFAULT 0,
    file_id     INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id)
);

-- 全站设置
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

-- 验证码（图形/人机，短期有效）
CREATE TABLE IF NOT EXISTS captchas (
    id          TEXT PRIMARY KEY,
    answer      TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'math',
    expires_at  TEXT NOT NULL
);

-- 分享访问记录（次数统计用，轻量）
CREATE TABLE IF NOT EXISTS share_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    share_id    INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(share_id) REFERENCES shares(id)
);
"""

DEFAULTS = [
    # 默认分类
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('图片','image')",),
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('视频','video')",),
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('文档','doc')",),
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('音乐','audio')",),
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('压缩包','zip')",),
    ("INSERT OR IGNORE INTO categories(name, icon) VALUES('其他','other')",),
    # 默认用户组：1游客 / 2普通 / 3管理员
    ("INSERT OR IGNORE INTO groups(name, is_default, can_upload, priv_quota, pub_quota, is_admin) VALUES('游客',1,0,0,0,0)",),
    ("INSERT OR IGNORE INTO groups(name, is_default, can_upload, priv_quota, pub_quota, is_admin) VALUES('普通用户',1,1,5368709120,10737418240,0)",),
    ("INSERT OR IGNORE INTO groups(name, is_default, can_upload, priv_quota, pub_quota, is_admin) VALUES('管理员',1,1,10737418240,21474836480,1)",),
    # 全站设置
    ("INSERT OR IGNORE INTO settings(key, value) VALUES('allow_register','1')",),
    ("INSERT OR IGNORE INTO settings(key, value) VALUES('storage_backend','local')",),
    ("INSERT OR IGNORE INTO settings(key, value) VALUES('captcha_level','easy')",),
]


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        for (sql,) in DEFAULTS:
            conn.execute(sql)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    return dict(row)
