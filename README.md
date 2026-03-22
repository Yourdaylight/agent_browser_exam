# Agent Browser 能力考试平台

> 自动化验证 Agent 浏览器自动化能力的考试系统

## 概述

本平台用于对比评测主流 Agent 浏览器自动化方案的能力：

- **browser-use** - Python AI Agent 框架
- **agent-browser** - Rust CLI 工具
- **openclaw** - AI 编程助手内置浏览器
- **finnie** - 自研方案

## 考试结构

| Level | 题目数 | 分值 | 验证方式 |
|:------|:-------|:-----|:---------|
| **L1 基础** | 5 题 | 30 分 | API/JS 自动验证 |
| **L2 中级** | 4 题 | 50 分 | 日志行为分析 |
| **L3 高级** | 4 题 | 60 分 | 组合验证 |

## 核心特性

- **100% 自动验证** - 无需人工审核
- **多 Agent 对比** - 统一排行榜
- **行为日志分析** - 验证循环检测、缓存等能力
- **公开 API 验证** - 使用 httpbin/GitHub API 等

## 快速开始

### 1. 安装依赖

```bash
cd agent-browser-exam
pip install -r requirements.txt
```

### 2. 启动验证服务器

```bash
python -m server.main
# 服务启动在 http://localhost:8080
```

### 3. Agent 接入

```python
from client.agent_sdk import AgentExamClient

client = AgentExamClient(
    server_url="http://localhost:8080",
    agent_name="finnie",
    agent_version="1.0.0"
)

# 注册考试
exam_token = await client.register("v1")

# 执行每道题
for task in exam_token["tasks"]:
    result = await client.execute_task(task)
    await client.submit(task["id"], result)

# 获取成绩
score = await client.get_score()
```

## 题目列表

### L1 基础能力

| 题号 | 题目 | 验证方式 | 分值 |
|:-----|:-----|:---------|:-----|
| L1-1 | HTTP GET + JSON 解析 | API 对比 | 5 |
| L1-2 | DOM 文本查找 | JS 执行 | 5 |
| L1-3 | 表单 POST 验证 | API 对比 | 5 |
| L1-4 | 元素点击 + 状态验证 | JS 执行 | 5 |
| L1-5 | Cookie 设置验证 | API 对比 | 10 |

### L2 中级能力

| 题号 | 题目 | 验证方式 | 分值 |
|:-----|:-----|:---------|:-----|
| L2-1 | 循环检测能力 | 日志分析 | 15 |
| L2-2 | RefMap 缓存命中率 | 日志分析 | 15 |
| L2-3 | 错误翻译友好度 | 日志分析 | 10 |
| L2-4 | 按需快照触发 | 日志分析 | 10 |

### L3 高级能力

| 题号 | 题目 | 验证方式 | 分值 |
|:-----|:-----|:---------|:-----|
| L3-1 | GitHub API 操作 | API 验证 | 15 |
| L3-2 | 百度搜索验证 | API + JS | 15 |
| L3-3 | 控制权切换 | 事件序列 | 15 |
| L3-4 | 多步操作组合 | 日志链分析 | 15 |

## 验证方式

### 1. API 验证
直接调用目标 API，对比返回结果

### 2. JS 执行验证
在页面执行 JavaScript 获取 DOM 状态

### 3. 日志行为分析
分析 Agent 上传的执行日志，验证行为是否符合预期

### 4. 事件序列验证
验证特定事件（loop_detected、control_handover 等）的触发顺序

## 项目结构

```
agent-browser-exam/
├── README.md
├── requirements.txt
├── server/
│   ├── __init__.py
│   ├── main.py          # FastAPI 服务器
│   ├── validators.py     # 验证器
│   └── models.py         # 数据模型
├── client/
│   ├── __init__.py
│   └── agent_sdk.py      # Agent SDK
├── exam_papers/
│   ├── __init__.py
│   ├── base.py           # 题目基类
│   ├── v1.py             # L1 基础题
│   ├── v2.py             # L2 中级题
│   └── v3.py             # L3 高级题
└── tests/
    └── test_validators.py
```

## License

MIT
