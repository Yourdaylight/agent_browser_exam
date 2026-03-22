"""
考试配置集中管理 — 唯一数据源

所有级别的超时、标签、描述、指令模板等统一在此定义。
题数和总分从 exam_papers 动态计算，避免硬编码不一致。
"""
from typing import Any, Dict


EXAM_LEVEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "v1": {
        "label": "基础能力评测 v1",
        "short_label": "L1 入门",
        "difficulty": "easy",
        "description": "打开网页、提取 DOM 文本、点击链接截图、HTTP 请求解析等基础浏览器操作能力。",
        "timeout_minutes": 10,
        "instruction_template": (
            "请阅读 {base_url}/exam/v1.md 并按照其中的指引完成 "
            "Agent Browser Exam「基础能力评测 v1」考试。"
        ),
    },
    "v2": {
        "label": "中级能力评测 v2",
        "short_label": "L2 进阶",
        "difficulty": "medium",
        "description": (
            "内置交互式页面操作（排序筛选、表单向导、标签页切换、仪表盘），"
            "外部网页提取（东方财富、Wikipedia），百度搜索操作。"
        ),
        "timeout_minutes": 20,
        "instruction_template": (
            "请阅读 {base_url}/exam/v2.md 并按照其中的指引完成 "
            "Agent Browser Exam「中级能力评测 v2」考试。"
        ),
    },
    "v3": {
        "label": "高级能力评测 v3",
        "short_label": "L3 噩梦",
        "difficulty": "hard",
        "description": (
            "社交平台登录与内容发布（GitHub/微博/知乎可选，文字+图文不同分值，GitHub用户附加Star）、"
            "电商购物协作（淘宝/京东登录+搜索iPhone+加购物车+比价）、"
            "电商比价寻找更便宜商铺。"
        ),
        "timeout_minutes": 30,
        "instruction_template": (
            "请阅读 {base_url}/exam/v3.md 并按照其中的指引完成 "
            "Agent Browser Exam「高级能力评测 v3」考试。"
        ),
    },
}


def get_timeout_minutes(exam_id: str) -> int:
    """获取指定级别的超时时间（分钟）"""
    cfg = EXAM_LEVEL_CONFIG.get(exam_id)
    if not cfg:
        return 30  # 默认
    return cfg["timeout_minutes"]


def get_exam_meta() -> Dict[str, Any]:
    """
    返回完整考试元信息，包含每个级别的题数和总分（从实际 task list 计算）。
    用于 GET /api/exam-meta 端点和前端动态渲染。
    """
    from exam_papers import get_tasks_for_level

    meta: Dict[str, Any] = {}
    for level, cfg in EXAM_LEVEL_CONFIG.items():
        tasks = get_tasks_for_level(level)
        meta[level] = {
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "difficulty": cfg["difficulty"],
            "description": cfg["description"],
            "timeout_minutes": cfg["timeout_minutes"],
            "instruction_template": cfg["instruction_template"],
            "task_count": len(tasks),
            "total_score": sum(t["max_score"] for t in tasks),
        }
    return meta
