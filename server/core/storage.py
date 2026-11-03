"""内容寻址存储：分片合并、SHA-256 去重、引用计数删除、多后端（本地/远程挂载扩容）"""
import hashlib
import shutil
from pathlib import Path

from core.config import FILES_DIR, REMOTE_DIR, TMP_DIR, get_setting


def storage_roots() -> list:
    """返回内容寻址根目录列表：本地 + 远程挂载（若启用）。本地始终参与。"""
    roots = [FILES_DIR]
    if get_setting("storage_backend", "local") == "remote" and REMOTE_DIR:
        roots.append(REMOTE_DIR)
    return roots


def blob_path(sha256: str) -> Path:
    """在启用后端中查找物理文件；找不到返回本地路径（写入用）"""
    for root in storage_roots():
        p = root / sha256[:2] / sha256
        if p.exists():
            return p
    return FILES_DIR / sha256[:2] / sha256


def blob_exists(sha256: str) -> bool:
    return blob_path(sha256).exists()


def compute_sha256(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def store_blob(src: Path, sha256: str) -> Path:
    """把合并后的文件放入内容寻址区（优先远程挂载扩容盘；已存在则直接返回）"""
    for root in storage_roots():
        p = root / sha256[:2] / sha256
        if p.exists():
            src.unlink(missing_ok=True)
            return p
    # 写入策略：远程挂载启用 → 写远程（扩容）；否则写本地
    root = storage_roots()[-1] if get_setting("storage_backend", "local") == "remote" and REMOTE_DIR else FILES_DIR
    target = root / sha256[:2] / sha256
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))
    return target


def delete_blob_if_unused(conn, sha256: str) -> bool:
    """引用数归零时删除物理文件（所有后端），返回是否删除"""
    if not sha256:
        return False
    if ref_count(conn, sha256) == 0:
        for root in storage_roots():
            p = root / sha256[:2] / sha256
            if p.exists():
                p.unlink()
                return True
    return False


def ref_count(conn, sha256: str) -> int:
    """files 表中引用该 sha256 的行数（含回收站）"""
    return conn.execute("SELECT COUNT(*) c FROM files WHERE sha256=?", (sha256,)).fetchone()["c"]


def upload_dir(upload_id: str) -> Path:
    d = TMP_DIR / upload_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def merge_chunks(upload_id: str, total_chunks: int, dest: Path) -> Path:
    """按序号合并分片到 dest"""
    d = upload_dir(upload_id)
    with open(dest, "wb") as out:
        for i in range(total_chunks):
            part = d / str(i)
            if not part.exists():
                raise FileNotFoundError(f"缺少分片 {i}")
            with open(part, "rb") as p:
                shutil.copyfileobj(p, out, 8 * 1024 * 1024)
    return dest


def cleanup_upload(upload_id: str) -> None:
    shutil.rmtree(upload_dir(upload_id), ignore_errors=True)
