"""内容寻址存储：分片合并、SHA-256 去重、引用计数删除"""
import hashlib
import shutil
from pathlib import Path

from core.config import FILES_DIR, TMP_DIR


def blob_path(sha256: str) -> Path:
    """物理文件路径：data/files/ab/<sha256>"""
    return FILES_DIR / sha256[:2] / sha256


def compute_sha256(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def blob_exists(sha256: str) -> bool:
    return blob_path(sha256).exists()


def store_blob(src: Path, sha256: str) -> Path:
    """把合并后的文件放入内容寻址区（已存在则直接返回）"""
    target = blob_path(sha256)
    if target.exists():
        src.unlink(missing_ok=True)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))
    return target


def ref_count(conn, sha256: str) -> int:
    """files 表中引用该 sha256 的行数（含回收站）"""
    return conn.execute("SELECT COUNT(*) c FROM files WHERE sha256=?", (sha256,)).fetchone()["c"]


def delete_blob_if_unused(conn, sha256: str) -> bool:
    """引用数归零时删除物理文件，返回是否删除"""
    if not sha256:
        return False
    if ref_count(conn, sha256) == 0:
        p = blob_path(sha256)
        if p.exists():
            p.unlink()
            return True
    return False


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
