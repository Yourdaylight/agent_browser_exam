# Agent Browser Exam 三维度内容审计与修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 审计 v1/v2/v3 三个维度考试的代码、文档、前端一致性，修复所有不一致问题，并为缺失能力维度补充题目。

**Architecture:** 逐文件审计 `base.py`（题目定义）、`validators.py`（验证器）、`v1.md`/`v2.md`/`v3.md`（考试文档）、`index.html`（前端卡片）、`main.py`（服务端逻辑）之间的数据一致性。核心原则：所有入口展示的题目数量、总分、描述必须与 `base.py` 中的实际定义完全一致。

**Tech Stack:** Python (FastAPI), Markdown, HTML/JS

---

## 审计现状汇总

### 三维度考试总览

| 维度 | 代码定义 (base.py) | 实际题目 | 总分 |
|:-----|:-------------------|:---------|:-----|
| v1 (L1) | L1_TASKS | 5题 | 25分 |
| v2 (L2) | L2_TASKS | 5题 | 60分 |
| v3 (L3) | L3_TASKS | 4题 | 65分 |

### 发现的不一致问题

| # | 文件 | 问题 | 严重度 |
|:--|:-----|:-----|:-------|
| 1 | `web/index.html` L2 卡片 | 显示 `4题 · 50分`，应为 `5题 · 60分` | 高 |
| 2 | `web/index.html` L3 卡片 | 显示 `4题 · 60分`，应为 `4题 · 65分` | 高 |
| 3 | `v1.md` 考试大纲 | 描述的是旧版 HTTP 题目，与 base.py 中新题目完全不符 | 高 |
| 4 | `v2.md` Token 提醒 | 写"共 4 道题"，应为 5 道 | 低 |
| 5 | `v1.md` 与代码 | v1.md 说 L1 是 HTTP 题目，但 base.py 中 L1 已改为浏览器操作为主（3题浏览器 + 2题 HTTP in browser context） | 高 |
| 6 | L2 题目设计问题 | L2-1~L2-4 都是验证 Agent 框架内部能力（循环检测、缓存、快照），普通 Agent 无法自报 execution_log，只有集成浏览器框架的 Agent 才能答 | 中 |

### 各维度题目分析

#### v1 (L1) 基础能力 — 5 题 · 25 分

| 题号 | 题目 | 验证器 | 类型 | 评价 |
|:-----|:-----|:-------|:-----|:-----|
| L1-1 | 打开网页提取标题 | OpenPageAndExtractTitleValidator | 浏览器 | 好。简单直接 |
| L1-2 | 提取 DOM 文本 | BrowserActionValidator | 浏览器 | 好。验证 navigate + content |
| L1-3 | 点击链接并截图 | BrowserActionValidator | 浏览器 | 好。验证 click + screenshot |
| L1-4 | HTTP GET + JSON | BrowserContextHTTPValidator | HTTP(in browser) | 好。必须有 navigate 前提 |
| L1-5 | HTTP POST 表单 | BrowserContextHTTPValidator | HTTP(in browser) | 好。必须有 navigate 前提 |

**结论：L1 题目设计合理，但 v1.md 文档与代码完全不一致，需要重写。**

#### v2 (L2) 中级能力 — 5 题 · 60 分

| 题号 | 题目 | 验证器 | 类型 | 评价 |
|:-----|:-----|:-------|:-----|:-----|
| L2-1 | 循环检测能力 | LoopDetectionValidator | 框架内部 | 需自报 execution_log.events |
| L2-2 | 页面缓存命中率 | RefMapCacheValidator | 框架内部 | 需自报 metadata |
| L2-3 | 错误信息友好度 | ErrorTranslationValidator | 框架内部 | 需自报 execution_log.events |
| L2-4 | 按需快照策略 | OnDemandSnapshotValidator | 框架内部 | 需自报 execution_log.metadata |
| L2-5 | 东方财富页面内容读取 | BrowserActionValidator | 浏览器 | 好。真实网站访问 |

**结论：L2-1~L2-4 全部依赖自报 execution_log，容易作弊。L2-5 是唯一真正验证浏览器操作的题目。建议增加更多真实浏览器交互题。**

#### v3 (L3) 高级能力 — 4 题 · 65 分

| 题号 | 题目 | 验证器 | 类型 | 评价 |
|:-----|:-----|:-------|:-----|:-----|
| L3-1 | 百度搜索操作 | SearchValidator | 浏览器 | 好。navigate + type + search |
| L3-2 | 多步操作组合 | MultiStepValidator | 浏览器 | 好。验证操作序列 |
| L3-3 | 控制权切换 | ControlHandoverValidator | 框架内部 | 需自报 events |
| L3-4 | GitHub Issue 评论 | GitHubIssueDiscussionValidator | 浏览器+内容 | 好。Challenge-Response + 内容验证 |

**结论：L3 题目设计较好，3/4 题目有真实的浏览器验证。L3-3 控制权切换依赖自报 events，可以保留但权重不宜过高。**

---

## 实施任务

### Task 1: 修复前端 index.html 数据不一致

**Files:**
- Modify: `web/index.html:52-63` (L2 卡片)
- Modify: `web/index.html:66-76` (L3 卡片)

**Step 1: 修复 L2 卡片元数据**

将 L2 卡片从 `4题 · 50分` 改为 `5题 · 60分`，更新描述文案。

**Step 2: 修复 L3 卡片元数据**

将 L3 卡片从 `4题 · 60分` 改为 `4题 · 65分`。

**Step 3: 提交**

```bash
git add web/index.html
git commit -m "fix: sync exam card metadata with base.py (L2: 5题/60分, L3: 4题/65分)"
```

---

### Task 2: 重写 v1.md 考试文档

**Files:**
- Modify: `exam_papers/md/v1.md`

**Step 1: 重写考试大纲**

当前 v1.md 描述的是旧版 HTTP 题目（HTTP GET + JSON、HTTP Headers、POST 表单、IP 获取、延迟响应），但 `base.py` 中 L1_TASKS 已经完全重写为浏览器操作为主的题目。需要将考试大纲更新为与代码一致：

| 题号 | 题目 | 分值 |
|:-----|:-----|:----:|
| L1-1 | 打开网页并提取标题 | 5分 |
| L1-2 | 提取页面 DOM 文本 | 5分 |
| L1-3 | 点击页面链接并截图 | 5分 |
| L1-4 | HTTP GET 请求解析 JSON（需浏览器上下文） | 5分 |
| L1-5 | HTTP POST 请求提交表单（需浏览器上下文） | 5分 |

**Step 2: 更新注意事项**

强调 L1-4 和 L1-5 必须先打开浏览器。

**Step 3: 提交**

```bash
git add exam_papers/md/v1.md
git commit -m "fix: rewrite v1.md exam outline to match actual L1_TASKS in base.py"
```

---

### Task 3: 修复 v2.md 题目数量

**Files:**
- Modify: `exam_papers/md/v2.md`

**Step 1: 修复 Token 消耗提醒**

将"本次考试共 4 道题"改为"本次考试共 5 道题"。

**Step 2: 提交**

```bash
git add exam_papers/md/v2.md
git commit -m "fix: correct task count from 4 to 5 in v2.md"
```

---

### Task 4: 为 L2 增加真实浏览器交互题

**Files:**
- Modify: `exam_papers/base.py` (L2_TASKS)
- Modify: `server/validators.py` (新增验证器)
- Modify: `exam_papers/md/v2.md` (更新大纲)
- Modify: `web/index.html` (更新卡片元数据)

**Step 1: 设计新题目**

为 L2 增加 2 道真实浏览器交互题（与 L2-5 东方财富类似的真实网站操作），替代纯自报型题目或作为补充。建议题目：

- **L2-6: Wikipedia 信息提取** — 访问 Wikipedia 页面，提取文章标题和第一段内容（验证 navigate + DOM 提取）
- **L2-7: 表单填写与提交** — 访问 httpbin.org/forms，填写表单并提交，验证返回结果

**Step 2: 在 base.py 中添加新题目到 L2_TASKS**

**Step 3: 在 v2.md 中更新考试大纲**

**Step 4: 更新前端卡片元数据**

**Step 5: 提交**

```bash
git add exam_papers/base.py server/validators.py exam_papers/md/v2.md web/index.html
git commit -m "feat: add real browser interaction tasks for L2 (Wikipedia extraction, form submission)"
```

---

### Task 5: 全面一致性验证

**Files:**
- Read-only: all files

**Step 1: 交叉验证所有数据源**

确认以下数据在 `base.py`、`v1.md`、`v2.md`、`v3.md`、`index.html` 中完全一致：
- 每个维度的题目数量
- 每个维度的总分
- 每道题的题号、标题、分值
- Token 消耗提醒中的题目数量

**Step 2: 验证所有验证器在 validators.py 中都有定义**

**Step 3: 验证所有验证器在 main.py 的 create_validator 工厂中都有对应的 case**

**Step 4: 生成一致性报告**
