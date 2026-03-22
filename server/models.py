"""
数据模型定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ExamLevel(str, Enum):
    V1 = "v1"  # 基础能力
    V2 = "v2"  # 中级能力
    V3 = "v3"  # 高级能力


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    HOVER = "hover"
    SELECT = "select"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    EXECUTE_SCRIPT = "execute_script"
    EVALUATE = "evaluate"  # 执行 JavaScript 并获取结果
    SNAPSHOT = "snapshot"
    ERROR = "error"
    LOOP_DETECTED = "loop_detected"
    CONTROL_HANDOVER = "control_handover"
    CONTROL_RESUME = "control_resume"
    CACHE_HIT = "cache_hit"


class Action(BaseModel):
    """执行动作"""
    type: ActionType
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    timestamp: float
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None


class ExecutionLog(BaseModel):
    """执行日志"""
    task_id: str
    actions: List[Action] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    token_consumed: int = 0
    screenshots: List[str] = Field(default_factory=list)  # base64 encoded
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskSubmit(BaseModel):
    """任务提交"""
    exam_token: str
    task_id: str
    answer: Optional[str] = None  # 直接答案（如 L1 题）
    execution_log: Optional[ExecutionLog] = None  # 执行日志（如 L2/L3 题）


class ValidationResult(BaseModel):
    """验证结果"""
    correct: bool
    score: int
    max_score: int
    feedback: str
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """任务结果"""
    task_id: str
    correct: bool
    score: int
    max_score: int
    submitted_at: datetime


class ExamSession(BaseModel):
    """考试会话"""
    exam_token: str
    agent_name: str
    agent_version: str
    agent_type: str
    skill_list: List[str]
    model_name: str
    exam_id: ExamLevel
    started_at: datetime
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    results: Dict[str, TaskResult] = Field(default_factory=dict)
    current_task_index: int = 0
    completed: bool = False


class ExamScore(BaseModel):
    """考试成绩"""
    exam_token: str
    agent_name: str
    agent_type: str
    total_score: int
    max_score: int
    total_time_seconds: float
    task_results: List[TaskResult]
    rank: Optional[int] = None
    grade: str  # S, A, B, C, D, F


class LeaderboardEntry(BaseModel):
    """排行榜条目"""
    rank: int
    agent_name: str
    agent_type: str
    total_score: int
    max_score: int
    total_time_seconds: float
    grade: str
    exam_id: ExamLevel


class RegisterRequest(BaseModel):
    """注册请求"""
    exam_id: str = Field(..., description="考试级别: v1, v2, v3")
    claw_name: str = Field(..., description="Agent 名称")
    claw_version: str = Field(..., description="Agent 版本")
    claw_type: str = Field(default="browser", description="Agent 类型")
    skill_list: List[str] = Field(default_factory=list, description="技能列表")
    model_name: str = Field(default="gpt-4", description="模型名称")
