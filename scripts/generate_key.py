#!/usr/bin/env python3
"""
生成 API Key 的脚本

Usage:
    python scripts/generate_key.py                    # 生成普通 key
    python scripts/generate_key.py --admin            # 生成 admin key
    python scripts/generate_key.py --list             # 列出已存在的 keys
"""
import argparse
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.security import security_manager


def main():
    parser = argparse.ArgumentParser(description="生成 API Key")
    parser.add_argument("--admin", action="store_true", help="创建管理员权限的 key")
    parser.add_argument("--owner", default="default", help="Key 所有者标识")
    parser.add_argument("--exam-limit", type=int, default=10, help="最大考试次数")
    parser.add_argument("--rate-limit", type=int, default=30, help="每分钟请求限制")
    parser.add_argument("--list", action="store_true", help="列出已存在的 keys")

    args = parser.parse_args()

    if args.list:
        print("已存在的 API Keys:")
        for key, config in security_manager.api_keys.items():
            status = "active" if config.is_active else "inactive"
            admin = " (admin)" if config.is_admin else ""
            print(f"  - {config.owner}{admin}: {config.exam_limit} exams, {config.rate_limit} req/min [{status}]")
        return

    # 生成新的 key
    raw_key, config = security_manager.generate_api_key(
        owner=args.owner,
        is_admin=args.admin,
        exam_limit=args.exam_limit,
        rate_limit_per_minute=args.rate_limit
    )

    print(f"✅ API Key 已生成:")
    print(f"   所有者: {args.owner}")
    print(f"   类型: {'管理员' if args.admin else '普通用户'}")
    print(f"   Key: {raw_key}")
    print(f"   考试次数限制: {args.exam_limit}")
    print(f"   频率限制: {args.rate_limit} req/min")
    print()
    print("⚠️  请妥善保存此 Key，只返回一次！")


if __name__ == "__main__":
    main()
