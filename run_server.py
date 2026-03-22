#!/usr/bin/env python3
"""
启动考试验证服务器

Usage:
    python run_server.py                    # 启动在 0.0.0.0:8080
    python run_server.py --host 127.0.0.1   # 指定地址
    python run_server.py --port 9000        # 指定端口
"""

import argparse
from server.main import start_server


def main():
    parser = argparse.ArgumentParser(description="Agent Browser Exam Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")

    args = parser.parse_args()

    print(f"启动 Agent Browser Exam 服务器...")
    print(f"地址: http://{args.host}:{args.port}")
    print(f"API 文档: http://{args.host}:{args.port}/docs")

    start_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
