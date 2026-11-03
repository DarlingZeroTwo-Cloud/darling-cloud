#!/usr/bin/env python3
"""Darling Cloud 打包脚本
用法：
    python3 scripts/build.py release     # 前端构建 + PyInstaller 单二进制 + tar.gz 发布包
    python3 scripts/build.py frontend    # 仅构建前端
    python3 scripts/build.py binary      # 仅打单二进制
"""
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"
BIN_NAME = "darling-cloud"


def run(cmd, cwd=None):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)


def build_frontend():
    print("==> 构建前端")
    run(["npm", "run", "build"], cwd=ROOT / "web")
    assert (ROOT / "web" / "dist" / "index.html").exists(), "前端构建产物缺失"


def build_binary():
    print("==> PyInstaller 单二进制")
    import importlib.util
    if importlib.util.find_spec("PyInstaller") is None:
        run([sys.executable, "-m", "pip", "install", "-q", "pyinstaller",
             "-i", "https://mirrors.huaweicloud.com/repository/pypi/simple"])
    dist_dir = ROOT / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
         "--name", BIN_NAME,
         "--add-data", f"{ROOT / 'web' / 'dist'}:web_dist",
         "--paths", str(ROOT / "server"),
         "--distpath", str(dist_dir),
         "--workpath", str(ROOT / "build" / "pyi-work"),
         "--specpath", str(ROOT / "build"),
         str(ROOT / "server" / "cli.py")])
    exe = dist_dir / BIN_NAME
    assert exe.exists(), "单二进制未生成"
    exe.chmod(0o755)
    print(f"  -> {exe}")
    return exe


def build_release():
    build_frontend()
    exe = build_binary()

    print("==> 打发布包 tar.gz")
    pkg = ROOT / "dist" / f"darling-cloud-v{VERSION}-linux-x86_64"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    shutil.copy(exe, pkg / BIN_NAME)
    shutil.copy(ROOT / "scripts" / "start.sh", pkg / "start.sh")
    shutil.copy(ROOT / "start.bat", pkg / "start.bat")
    shutil.copy(ROOT / "docs" / "DEPLOY.md", pkg / "DEPLOY.md")
    shutil.copy(ROOT / "README.md", pkg / "README.md")
    if (ROOT / "LICENSE").exists():
        shutil.copy(ROOT / "LICENSE", pkg / "LICENSE")

    tarball = ROOT / "dist" / f"darling-cloud-v{VERSION}-linux-x86_64.tar.gz"
    if tarball.exists():
        tarball.unlink()
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(pkg, arcname=pkg.name)
    print(f"  -> {tarball} ({tarball.stat().st_size / 1048576:.1f} MB)")
    return tarball


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "release"
    if cmd == "frontend":
        build_frontend()
    elif cmd == "binary":
        build_binary()
    else:
        build_release()
