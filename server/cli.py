"""darling-cloud 命令行入口（单二进制 / 开发启动共用）
用法：
    python server/cli.py start [--host 0.0.0.0] [--port 8080] [--data ./data]
    # 或打包后：
    ./darling-cloud start
"""
import argparse
import os
import sys


def _banner(host: str, port: int) -> None:
    print()
    print("  Darling Cloud v2  ——  开源私有云盘")
    print("  ─" * 34)
    print(f"  本机访问:  http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}")
    print(f"  公开广场:  无需登录即可浏览/下载")
    print("  首个注册账号自动成为管理员")
    print("  WebDAV:    http://<host>:<port>/dav/  （用户名+登录密码）")
    print("  帮助:      http://<host>:<port>/help")
    print("  ─" * 34)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(prog="darling-cloud", description="Darling Cloud v2 开源私有云盘")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("start", help="启动服务端（一条命令）")
    p.add_argument("--host", default=os.environ.get("DARLING_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DARLING_PORT", "8080")))
    p.add_argument("--data", default=os.environ.get("DARLING_DATA", ""),
                   help="数据目录（库/文件/临时区），默认 ./data")

    sub.add_parser("version", help="显示版本号")
    ap.add_argument("--version", action="store_true", help="显示版本号")

    args = ap.parse_args()

    if args.version or args.cmd == "version":
        print("darling-cloud v0.1.0 (M5)")
        return 0

    if args.cmd != "start":
        ap.print_help()
        return 0

    if args.data:
        os.environ["DARLING_DATA"] = os.path.abspath(args.data)

    _banner(args.host, args.port)

    import uvicorn

    from core.config import ensure_dirs
    ensure_dirs()

    from main import app
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
