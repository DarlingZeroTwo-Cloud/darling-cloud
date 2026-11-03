"""WebDAV 服务（RFC 4918 精简实现）
- Basic Auth 鉴权（DB 用户）
- 虚拟目录树 = files 表（内容寻址物理存储，WebDAV 呈现逻辑目录）
- 支持：PROPFIND / PROPPATCH / MKCOL / GET / PUT / DELETE / COPY / MOVE / LOCK / UNLOCK / OPTIONS
- 支持：Windows 资源管理器映射、rclone、RaiDrive 等客户端
"""
import base64
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from core.config import CHUNK_SIZE, MAX_FILE_SIZE, TMP_DIR
from core.db import db
from core.security import sanitize_name
from core.storage import blob_exists, blob_path, compute_sha256, store_blob, upload_dir

router = APIRouter()

DAV_NS = "DAV:"
NS = {"D": DAV_NS}
PROP_NAMES = ["displayname", "getcontentlength", "getcontenttype", "resourcetype",
              "getlastmodified", "creationdate", "getetag"]


def _dav_auth(request: Request) -> dict:
    """Basic Auth → DB 用户"""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        raise HTTPException(401, "需要 WebDAV 账号认证", headers={"WWW-Authenticate": 'Basic realm="Darling Cloud"'})
    try:
        raw = base64.b64decode(auth[6:]).decode()
        username, password = raw.split(":", 1)
    except Exception:
        raise HTTPException(401, "认证格式错误", headers={"WWW-Authenticate": 'Basic realm="Darling Cloud"'})
    with db() as conn:
        from core.security import verify_password
        row = conn.execute("SELECT u.*, g.can_upload, g.priv_quota FROM users u "
                           "JOIN groups g ON u.group_id=g.id WHERE u.username=? AND u.is_active=1",
                           (username,)).fetchone()
        if not row or not verify_password(password, row["pass_hash"]):
            raise HTTPException(401, "用户名或密码错误", headers={"WWW-Authenticate": 'Basic realm="Darling Cloud"'})
        return dict(row)


def _node(conn, user_id: int, dav_path: str) -> dict | None:
    """把 /dav/ 路径解析成 files 记录（name 逐级匹配）"""
    parts = [unquote(p) for p in dav_path.strip("/").split("/") if p]
    if not parts:
        return None  # 根
    parent_id = 0
    cur = None
    for name in parts:
        cur = conn.execute("SELECT * FROM files WHERE owner_id=? AND parent_id=? AND name=? AND deleted_at IS NULL",
                           (user_id, parent_id, name)).fetchone()
        if not cur:
            return None
        parent_id = cur["id"]
    return dict(cur) if cur else None


def _children(conn, user_id: int, parent_id: int):
    return conn.execute("SELECT * FROM files WHERE owner_id=? AND parent_id=? AND deleted_at IS NULL "
                        "ORDER BY is_dir DESC, name", (user_id, parent_id)).fetchall()


def _href(path: str) -> str:
    return "/dav/" + "/".join(quote(p) for p in path.strip("/").split("/") if p)


def _prop_xml(node: dict | None, path: str, user: dict) -> str:
    """生成单个节点的 PROPFIND 响应 XML"""
    if node is None:
        return f'<D:response><D:href>{_href(path)}</D:href><D:status>HTTP/1.1 404 Not Found</D:status></D:response>'
    is_dir = bool(node["is_dir"])
    size = 0 if is_dir else (node["size"] or 0)
    mtime = (node["updated_at"] or "").replace(" ", "T") + "Z"
    ctype = "httpd/unix-directory" if is_dir else "application/octet-stream"
    res = (f'<D:response><D:href>{_href(path)}</D:href>'
           f'<D:propstat><D:prop>'
           f'<D:displayname>{node["name"]}</D:displayname>'
           f'<D:resourcetype>{"<D:collection/>" if is_dir else ""}</D:resourcetype>'
           f'<D:getcontentlength>{size}</D:getcontentlength>'
           f'<D:getcontenttype>{ctype}</D:getcontenttype>'
           f'<D:getlastmodified>{mtime}</D:getlastmodified>'
           f'<D:creationdate>{mtime}</D:creationdate>'
           f'<D:getetag>"dc-{node["id"]}"</D:getetag>'
           f'<D:quota-available-bytes>{max(user["priv_quota"] - 0, 0)}</D:quota-available-bytes>'
           f'<D:quota-used-bytes>0</D:quota-used-bytes>'
           f'</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>'
           f'</D:response>')
    # XML 转义
    return res.replace("&", "&amp;").replace("<D:", "<D:")


def _multistatus(body: str) -> Response:
    return Response(
        content='<?xml version="1.0" encoding="utf-8"?>'
                f'<D:multistatus xmlns:D="DAV:">{body}</D:multistatus>',
        media_type='application/xml; charset="utf-8"',
        headers={"DAV": "1,2", "MS-Author-Via": "DAV"})


def _find_put_target(conn, user_id: int, dav_path: str):
    """PUT/MKCOL/COPY/MOVE 目标解析：返回 (parent_id, name)"""
    parts = [unquote(p) for p in dav_path.strip("/").split("/") if p]
    if not parts:
        raise HTTPException(400, "路径无效")
    name = sanitize_name(parts[-1])
    parent_id = 0
    for i, p in enumerate(parts[:-1]):
        row = conn.execute("SELECT * FROM files WHERE owner_id=? AND parent_id=? AND name=? AND deleted_at IS NULL",
                           (user_id, parent_id, p)).fetchone()
        if not row or not row["is_dir"]:
            raise HTTPException(409, f"父目录不存在: {p}")
        parent_id = row["id"]
    return parent_id, name


# ---------- 路由 ----------
@router.api_route("/dav/{path:path}", methods=["OPTIONS"])
async def dav_options(path: str):
    return Response(status_code=200, headers={
        "DAV": "1,2", "Allow": "OPTIONS, PROPFIND, PROPPATCH, MKCOL, GET, PUT, DELETE, COPY, MOVE, LOCK, UNLOCK",
        "MS-Author-Via": "DAV", "Content-Length": "0"})


@router.api_route("/dav/{path:path}", methods=["PROPFIND"])
async def dav_propfind(path: str, request: Request):
    user = _dav_auth(request)
    depth = request.headers.get("depth", "1")
    with db() as conn:
        node = _node(conn, user["id"], path)
        if node is None and path.strip("/") != "":
            return _multistatus(_prop_xml(None, path, user))
        body = f'<D:response><D:href>{_href(path)}</D:href></D:response>' if path == "" else ""
        root = None if path.strip("/") == "" else node
        # 根
        resp = _prop_xml(root, path, user)
        if depth == "1":
            parent_id = 0 if not root else root["id"]
            for c in _children(conn, user["id"], parent_id):
                resp += _prop_xml(dict(c), f"{path.rstrip('/')}/{c['name']}", user)
        return _multistatus(resp)


@router.api_route("/dav/{path:path}", methods=["PROPPATCH"])
async def dav_proppatch(path: str, request: Request):
    user = _dav_auth(request)
    return _multistatus(f'<D:response><D:href>{_href(path)}</D:href>'
                        f'<D:propstat><D:prop/><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>')


@router.api_route("/dav/{path:path}", methods=["MKCOL"])
async def dav_mkcol(path: str, request: Request):
    user = _dav_auth(request)
    with db() as conn:
        parent_id, name = _find_put_target(conn, user["id"], path)
        dup = conn.execute("SELECT 1 FROM files WHERE owner_id=? AND parent_id=? AND name=? AND deleted_at IS NULL",
                           (user["id"], parent_id, name)).fetchone()
        if dup:
            raise HTTPException(405, "已存在同名节点")
        conn.execute("INSERT INTO files(owner_id, name, parent_id, is_dir) VALUES(?, ?, ?, 1)",
                     (user["id"], name, parent_id))
        return Response(status_code=201)


@router.api_route("/dav/{path:path}", methods=["GET", "HEAD"])
async def dav_get(path: str, request: Request):
    user = _dav_auth(request)
    with db() as conn:
        node = _node(conn, user["id"], path)
        if not node:
            raise HTTPException(404, "文件不存在")
        if node["is_dir"]:
            raise HTTPException(405, "集合不可下载")
        p = blob_path(node["sha256"]) if node["sha256"] else None
        if not p or not p.exists():
            raise HTTPException(404, "物理文件缺失")
        conn.execute("UPDATE files SET download_count=download_count+1 WHERE id=?", (node["id"],))
        return FileResponse(p, media_type="application/octet-stream",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(node['name'])}"})


@router.api_route("/dav/{path:path}", methods=["PUT"])
async def dav_put(path: str, request: Request):
    user = _dav_auth(request)
    length = int(request.headers.get("content-length", 0))
    if length <= 0 or length > MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小不合法")
    with db() as conn:
        parent_id, name = _find_put_target(conn, user["id"], path)
        # 配额校验（当前已用）
        used = conn.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE owner_id=? AND is_public=0 AND deleted_at IS NULL",
                            (user["id"],)).fetchone()[0]
        if used + length > user["priv_quota"]:
            raise HTTPException(507, "配额不足（Insufficient Storage）")
        # 流式写入临时文件
        tmp = TMP_DIR / f"dav-{user['id']}-{hashlib.md5(path.encode()).hexdigest()[:8]}.bin"
        total = 0
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                total += len(chunk)
        sha = compute_sha256(tmp)
        # 秒传检测
        if not blob_exists(sha):
            store_blob(tmp, sha)
        else:
            tmp.unlink(missing_ok=True)
        dup = conn.execute("SELECT id FROM files WHERE owner_id=? AND parent_id=? AND name=? AND deleted_at IS NULL",
                           (user["id"], parent_id, name)).fetchone()
        if dup:
            conn.execute("UPDATE files SET size=?, sha256=?, updated_at=datetime('now') WHERE id=?",
                         (total, sha, dup["id"]))
        else:
            conn.execute("INSERT INTO files(owner_id, name, parent_id, size, sha256) VALUES(?, ?, ?, ?, ?)",
                         (user["id"], name, parent_id, total, sha))
        return Response(status_code=201)


@router.api_route("/dav/{path:path}", methods=["DELETE"])
async def dav_delete(path: str, request: Request):
    user = _dav_auth(request)
    with db() as conn:
        node = _node(conn, user["id"], path)
        if not node:
            raise HTTPException(404, "节点不存在")
        conn.execute("UPDATE files SET deleted_at=datetime('now') WHERE id=?", (node["id"],))
        return Response(status_code=204)


@router.api_route("/dav/{path:path}", methods=["COPY", "MOVE"])
async def dav_copy_move(path: str, request: Request):
    user = _dav_auth(request)
    dest_hdr = request.headers.get("destination", "")
    if not dest_hdr:
        raise HTTPException(400, "缺少 Destination 头")
    from urllib.parse import urlparse
    dest = unquote(urlparse(dest_hdr).path)
    if dest.startswith("/dav/"):
        dest = dest[5:]
    is_move = request.method == "MOVE"
    overwrite = request.headers.get("overwrite", "T").upper() != "F"
    with db() as conn:
        src = _node(conn, user["id"], path)
        if not src:
            raise HTTPException(404, "源不存在")
        d_parent, d_name = _find_put_target(conn, user["id"], dest)
        dup = conn.execute("SELECT id FROM files WHERE owner_id=? AND parent_id=? AND name=? AND deleted_at IS NULL",
                           (user["id"], d_parent, d_name)).fetchone()
        if dup and not overwrite:
            raise HTTPException(412, "目标已存在")
        if dup:
            conn.execute("UPDATE files SET deleted_at=datetime('now') WHERE id=?", (dup["id"],))
        if is_move:
            # 防环：目标不能是源的子级
            pid = d_parent
            while pid:
                if pid == src["id"]:
                    raise HTTPException(409, "不能移动到自身子目录")
                pid = conn.execute("SELECT parent_id FROM files WHERE id=?", (pid,)).fetchone()["parent_id"]
            conn.execute("UPDATE files SET parent_id=?, name=? WHERE id=?", (d_parent, d_name, src["id"]))
        else:
            # 复制（目录递归复制；顶层用目标名，子级沿用原名）
            def dup_rec(fid, new_parent, use_name=None):
                r = conn.execute("SELECT * FROM files WHERE id=? AND deleted_at IS NULL", (fid,)).fetchone()
                cur = conn.execute(
                    "INSERT INTO files(owner_id, name, parent_id, is_dir, size, sha256, category_id, desc_text) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (user["id"], use_name or r["name"], new_parent, r["is_dir"], r["size"], r["sha256"],
                     r["category_id"], r["desc_text"]))
                if r["is_dir"]:
                    for c in conn.execute("SELECT id FROM files WHERE parent_id=? AND deleted_at IS NULL",
                                          (fid,)).fetchall():
                        dup_rec(c["id"], cur.lastrowid)
            dup_rec(src["id"], d_parent, d_name)
        return Response(status_code=201 if dup else 204)


@router.api_route("/dav/{path:path}", methods=["LOCK"])
async def dav_lock(path: str, request: Request):
    user = _dav_auth(request)
    token = f"opaquelocktoken:dc-{user['id']}-{hashlib.md5(path.encode()).hexdigest()[:12]}"
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            f'<D:prop xmlns:D="DAV:"><D:lockdiscovery><D:activelock>'
            f'<D:locktype><D:write/></D:locktype><D:lockscope><D:exclusive/></D:lockscope>'
            f'<D:depth>infinity</D:depth><D:locktoken><D:href>{token}</D:href></D:locktoken>'
            f'</D:activelock></D:lockdiscovery></D:prop>')
    return Response(content=body, media_type='application/xml; charset="utf-8"',
                    headers={"Lock-Token": f"<{token}>", "DAV": "1,2"})


@router.api_route("/dav/{path:path}", methods=["UNLOCK"])
async def dav_unlock(path: str, request: Request):
    _dav_auth(request)
    return Response(status_code=204)
