#!/usr/bin/env python3
"""
快速运行考试脚本

Usage:
    python run_exam.py                    # 运行 v1 基础考试
    python run_exam.py --level v2        # 运行 v2 中级考试
    python run_exam.py --level v3        # 运行 v3 高级考试
    python run_exam.py --server http://localhost:8080  # 指定服务器
"""

import argparse
import asyncio
from client.agent_sdk import AgentExamClient, ExamConfig


async def main():
    parser = argparse.ArgumentParser(description="Agent Browser Exam Client")
    parser.add_argument("--server", default="http://localhost:8080", help="考试服务器地址")
    parser.add_argument("--level", default="v1", choices=["v1", "v2", "v3"], help="考试级别")
    parser.add_argument("--agent-name", default="finnie", help="Agent 名称")
    parser.add_argument("--agent-version", default="1.0.0", help="Agent 版本")
    parser.add_argument("--agent-type", default="finnie-agent", help="Agent 类型")
    parser.add_argument("--model", default="gpt-4", help="模型名称")
    parser.add_argument("--skills", nargs="+", default=["browser-automation"], help="技能列表")

    args = parser.parse_args()

    config = ExamConfig(
        server_url=args.server,
        agent_name=args.agent_name,
        agent_version=args.agent_version,
        agent_type=args.agent_type,
        model_name=args.model,
        skill_list=args.skills
    )

    async with AgentExamClient(config) as client:
        await client.run_exam(args.level)


if __name__ == "__main__":
    asyncio.run(main())
