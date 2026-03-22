"""
Agent 端 SDK - 用于 Agent 接入考试平台
"""
import asyncio
import json
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from server.models import Action, ActionType, ExecutionLog


@dataclass
class ExamConfig:
    """考试配置"""
    server_url: str
    agent_name: str
    agent_version: str
    agent_type: str
    model_name: str
    skill_list: List[str] = field(default_factory=list)


@dataclass
class TaskContext:
    """任务上下文"""
    task_id: str
    title: str
    description: str
    instructions: str
    max_score: int


class AgentExamClient:
    """Agent 考试客户端"""

    def __init__(self, config: ExamConfig):
        self.config = config
        self.exam_token: Optional[str] = None
        self.current_task: Optional[TaskContext] = None
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def register(self, exam_level: str = "v1") -> Dict[str, Any]:
        """注册考试"""

        response = await self.client.post(
            f"{self.config.server_url}/api/register",
            json={
                "exam_id": exam_level,
                "claw_name": self.config.agent_name,
                "claw_version": self.config.agent_version,
                "claw_type": self.config.agent_type,
                "skill_list": self.config.skill_list,
                "model_name": self.config.model_name
            }
        )

        if response.status_code != 200:
            raise Exception(f"注册失败: {response.text}")

        data = response.json()
        self.exam_token = data["exam_token"]

        return data

    async def get_current_task(self) -> Optional[TaskContext]:
        """获取当前任务"""

        if not self.exam_token:
            raise Exception("未注册考试")

        response = await self.client.get(
            f"{self.config.server_url}/api/next/{self.exam_token}"
        )

        if response.status_code != 200:
            raise Exception(f"获取任务失败: {response.text}")

        data = response.json()

        if data.get("all_done"):
            return None

        if "next_question" in data and data["next_question"]:
            self.current_task = TaskContext(
                task_id=data["next_question"]["id"],
                title=data["next_question"]["title"],
                description=data["next_question"]["description"],
                instructions=data["next_question"]["instructions"],
                max_score=data["next_question"]["max_score"]
            )

        return self.current_task

    async def submit_answer(self, answer: str) -> Dict[str, Any]:
        """提交直接答案（如 L1 题）"""

        if not self.exam_token or not self.current_task:
            raise Exception("没有当前任务")

        response = await self.client.post(
            f"{self.config.server_url}/api/submit",
            json={
                "exam_token": self.exam_token,
                "task_id": self.current_task.task_id,
                "answer": answer,
                "execution_log": None
            }
        )

        if response.status_code != 200:
            raise Exception(f"提交失败: {response.text}")

        return response.json()

    async def submit_with_log(self, execution_log: ExecutionLog) -> Dict[str, Any]:
        """提交带执行日志的答案（如 L2/L3 题）"""

        if not self.exam_token or not self.current_task:
            raise Exception("没有当前任务")

        log_data = {
            "task_id": execution_log.task_id,
            "actions": [
                {
                    "type": a.type.value,
                    "selector": a.selector,
                    "value": a.value,
                    "url": a.url,
                    "timestamp": a.timestamp,
                    "duration_ms": a.duration_ms,
                    "success": a.success,
                    "error_message": a.error_message
                }
                for a in execution_log.actions
            ],
            "events": execution_log.events,
            "token_consumed": execution_log.token_consumed,
            "screenshots": execution_log.screenshots,
            "metadata": execution_log.metadata
        }

        response = await self.client.post(
            f"{self.config.server_url}/api/submit",
            json={
                "exam_token": self.exam_token,
                "task_id": self.current_task.task_id,
                "answer": None,
                "execution_log": log_data
            }
        )

        if response.status_code != 200:
            raise Exception(f"提交失败: {response.text}")

        return response.json()

    async def get_score(self) -> Dict[str, Any]:
        """获取当前成绩"""

        if not self.exam_token:
            raise Exception("未注册考试")

        response = await self.client.get(
            f"{self.config.server_url}/api/score/{self.exam_token}"
        )

        if response.status_code != 200:
            raise Exception(f"获取成绩失败: {response.text}")

        return response.json()

    async def run_exam(self, exam_level: str = "v1"):
        """运行完整考试"""

        print(f"开始考试 {exam_level}...")

        # 1. 注册
        reg_data = await self.register(exam_level)
        print(f"注册成功，准考证号: {self.exam_token}")
        print(f"题目数量: {reg_data['total_questions']}, 满分: {reg_data['total_score']}")

        # 2. 循环答题
        while True:
            task = await self.get_current_task()
            if not task:
                break

            print(f"\n{'='*50}")
            print(f"当前题目: {task.task_id} - {task.title}")
            print(f"描述: {task.description}")
            print(f"说明: {task.instructions}")
            print(f"{'='*50}")

            # 这里 Agent 应该实现自己的解题逻辑
            # 示例：直接提交占位答案
            answer = input("请输入答案（或输入'exec'让 Agent 执行）: ")

            if answer.lower() == "exec":
                # Agent 实现解题
                result = await self._execute_task(task)
            else:
                result = await self.submit_answer(answer)

            print(f"结果: {'✓ 正确' if result['correct'] else '✗ 错误'}")
            print(f"得分: {result['score']}")
            print(f"反馈: {result.get('feedback', '')}")

        # 3. 获取最终成绩
        final_score = await self.get_score()
        print(f"\n{'='*50}")
        print(f"考试完成!")
        print(f"总分: {final_score['total_score']}/{final_score['max_score']}")
        print(f"评级: {final_score['grade']}")
        print(f"用时: {final_score['total_time_seconds']:.1f}秒")
        print(f"{'='*50}")

        return final_score

    async def _execute_task(self, task: TaskContext) -> Dict[str, Any]:
        """执行任务 - Agent 需要实现的具体逻辑"""

        # 这是一个示例实现，实际使用时 Agent 应该有自己的实现
        execution_log = ExecutionLog(
            task_id=task.task_id,
            actions=[],
            events=[],
            token_consumed=0,
            metadata={}
        )

        # 模拟一些操作
        execution_log.actions.append(Action(
            type=ActionType.NAVIGATE,
            url="https://example.com",
            timestamp=time.time(),
            success=True
        ))

        # 添加元数据
        if task.task_id == "L2-1":  # 循环检测
            execution_log.events.append({
                "type": "loop_detected",
                "at_action": 5,
                "reason": "连续相同操作超过阈值"
            })

        elif task.task_id == "L2-2":  # RefMap 缓存
            execution_log.metadata["first_visit_tokens"] = 15000
            execution_log.metadata["second_visit_tokens"] = 500
            execution_log.events.append({
                "type": "cache_hit",
                "cached_selector": "button.submit"
            })

        return await self.submit_with_log(execution_log)


# ============================================
# 简化用法
# ============================================

async def quick_exam(
    server_url: str,
    agent_name: str,
    agent_type: str,
    model_name: str,
    exam_level: str = "v1"
):
    """快速开始考试"""

    config = ExamConfig(
        server_url=server_url,
        agent_name=agent_name,
        agent_version="1.0.0",
        agent_type=agent_type,
        model_name=model_name,
        skill_list=["browser-automation"]
    )

    async with AgentExamClient(config) as client:
        return await client.run_exam(exam_level)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":

    async def example():
        config = ExamConfig(
            server_url="http://localhost:8080",
            agent_name="finnie",
            agent_version="1.0.0",
            agent_type="finnie-agent",
            model_name="gpt-4",
            skill_list=["browser-automation", "refmap"]
        )

        async with AgentExamClient(config) as client:
            # 注册 v1 考试
            await client.register("v1")

            # 获取第一题
            task = await client.get_current_task()
            print(f"第一题: {task.title}")

            # 提交答案
            result = await client.submit_answer("Slide 1")
            print(f"结果: {result}")

    # 运行示例
    asyncio.run(example())
