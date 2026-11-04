"""Darling Cloud v2 —— FastAPI 入口"""
from contextlib import asynccontextmanager
from pathlib import Path
import os, socket, subprocess, sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import (BASE_DIR, HOST, PORT, ensure_dirs, ARIA2_DIR,
                         ARIA2_RPC_PORT, ARIA2_RPC_SECRET, find_aria2c)
from core.db import init_db
from api import auth, users, files, admin, upload, download, public, share, offline, dav


def _maybe_start_aria2c() -> None:
    """如果包内有 aria2c 且 RPC 端口空闲，自动拉起 daemon"""
    if find_aria2c():
        try:
            s = socket.create_connection(("127.0.0.1", ARIA2_RPC_PORT), timeout=1)
            s.close()
            return  # 已在跑
        except OSError:
            pass
        exe = find_aria2c()
        args = [
            exe, "--enable-rpc", "--rpc-listen-all=false",
            f"--rpc-listen-port={ARIA2_RPC_PORT}",
            f"--dir={ARIA2_DIR}",
            "--max-concurrent-downloads=5",
            "--continue=true",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--quiet",
        ]
        if ARIA2_RPC_SECRET:
            args.append(f"--rpc-secret={ARIA2_RPC_SECRET}")
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    init_db()
    _maybe_start_aria2c()
    yield


app = FastAPI(title="Darling Cloud v2", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(download.router)
app.include_router(public.router)
app.include_router(share.router)
app.include_router(offline.router)
app.include_router(dav.router)


@app.get("/api/ping")
async def ping():
    return {"ok": True, "service": "darling-cloud", "version": "0.1.0"}


# 静态前端（web/dist 构建后挂载；SPA history 路由 fallback 到 index.html）
import sys
if getattr(sys, "frozen", False):
    _web_dist = Path(sys._MEIPASS) / "web_dist"
else:
    _web_dist = BASE_DIR.parent / "web" / "dist"
if _web_dist.exists():
    import os
    from starlette.responses import FileResponse

    assets = StaticFiles(directory=str(_web_dist))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            from starlette.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = _web_dist / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(_web_dist / "index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
