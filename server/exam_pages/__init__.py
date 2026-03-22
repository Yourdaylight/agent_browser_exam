"""
内置考题页面注册表
"""
import os

EXAM_PAGES_DIR = os.path.join(os.path.dirname(__file__))

# 页面 ID → 文件名映射
PAGE_REGISTRY = {
    "data-table": "data-table.html",
    "products": "products.html",
    "wizard": "wizard.html",
    "tabs": "tabs.html",
    "dashboard": "dashboard.html",
}

# 页面 ID → 答案映射（验证器用）
PAGE_ANSWERS = {
    "data-table": "78.3%",
    "products": "ProMax Ultra Monitor",
    "wizard": "ORD-20260322-A7X9",
    "tabs": "3",
    "dashboard": "Connection timeout to database replica-3",
}


def get_page_path(page_id: str) -> str:
    filename = PAGE_REGISTRY.get(page_id)
    if not filename:
        return None
    return os.path.join(EXAM_PAGES_DIR, filename)


def list_pages() -> list:
    return list(PAGE_REGISTRY.keys())
