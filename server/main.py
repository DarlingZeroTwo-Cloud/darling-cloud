"""Darling Cloud v2 —— FastAPI 入口"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import BASE_DIR, HOST, PORT, ensure_dirs
from core.db import init_db
from api import auth, users, files, admin, upload, download


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    init_db()
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


@app.get("/api/ping")
async def ping():
    return {"ok": True, "service": "darling-cloud", "version": "0.1.0"}


# 静态前端（web/dist 构建后挂载）
_web_dist = BASE_DIR.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
