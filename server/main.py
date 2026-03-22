"""
Agent Browser 能力考试 - 验证服务器
"""
import uuid
import asyncio
import os
import time
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from .models import (
    ExamLevel, ExamSession, TaskSubmit, ValidationResult,
    TaskResult, ExamScore, LeaderboardEntry, ExecutionLog,
    RegisterRequest, BaseModel
)
from .validators import (
    BrowserActionValidator, BrowserContextHTTPValidator,
    GitHubIssueDiscussionValidator,
    OpenPageAndExtractTitleValidator, OpenPageAndScreenshotValidator,
    ClickElementValidator, TypeAndSubmitValidator, WaitForContentValidator,
    LoopDetectionValidator, RefMapCacheValidator, ErrorTranslationValidator,
    OnDemandSnapshotValidator, ControlHandoverValidator,
    SearchValidator, MultiStepValidator, BuiltInPageValidator,
    GitHubStarValidator,
)
from .security import (
    security_manager, get_client_ip, verify_request,
    add_security_headers, SecurityManager
)
from .storage import get_storage


# 题目配置
from exam_papers import get_tasks_for_level


def _get_base_url() -> str:
    """获取对外服务的基础 URL，优先读环境变量 EXAM_BASE_URL，否则从请求头推断"""
    return os.environ.get("EXAM_BASE_URL", "").rstrip("/")


def _get_db() -> Any:
    """获取存储实例（延迟初始化）"""
    return get_storage()


# 验证器工厂
def create_validator(validator_config: Dict) -> Optional[Any]:
    """根据配置创建验证器"""
    if not validator_config:
        return None

    validator_type = validator_config.get("type")
    if validator_type == "BrowserActionValidator":
        return BrowserActionValidator(**{k: v for k, v in validator_config.items() if k != "type"})
    elif validator_type == "BrowserContextHTTPValidator":
        return BrowserContextHTTPValidator(**{k: v for k, v in validator_config.items() if k != "type"})
    elif validator_type == "GitHubIssueDiscussionValidator":
        return GitHubIssueDiscussionValidator(
            max_score=validator_config.get("max_score", 20),
            challenge_code=validator_config.get("challenge_code"),
            exam_token=validator_config.get("exam_token"),
        )
    elif validator_type == "BuiltInPageValidator":
        from .exam_pages import PAGE_ANSWERS
        page_id = validator_config.get("page_id")
        expected = PAGE_ANSWERS.get(page_id, "")
        return BuiltInPageValidator(
            page_id=page_id,
            expected_answer=expected,
            required_operations=validator_config.get("required_operations", []),
            max_score=validator_config.get("max_score", 15),
        )
    elif validator_type == "GitHubStarValidator":
        return GitHubStarValidator(
            max_score=validator_config.get("max_score", 5),
            initial_star_count=validator_config.get("initial_star_count", 0),
        )

    return None


# 存储（已迁移至 SQLite，保留变量名兼容）
# exam_sessions, leaderboard, page_stats 现在通过 get_storage() 访问


app = FastAPI(title="Agent Browser Exam", version="1.0.0")

# CORS 配置 - 限制来源
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",") or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != [""] else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """频率限制中间件"""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[str, list] = {}

    async def dispatch(self, request: Request, call_next):
        ip = get_client_ip(request)

        # 检查 IP 白名单/黑名单
        allowed, reason = security_manager.check_ip(ip)
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": f"IP 地址已被限制: {reason}"}
            )

        # 频率限制
        now = time.time()
        if ip not in self.request_counts:
            self.request_counts[ip] = []

        # 清理过期的请求记录
        self.request_counts[ip] = [
            t for t in self.request_counts[ip]
            if now - t < 60
        ]

        if len(self.request_counts[ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"}
            )

        self.request_counts[ip].append(now)

        response = await call_next(request)
        return add_security_headers(response)


app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

# 挂载静态文件
web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")

# 试卷文件目录
exam_papers_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exam_papers", "md")


# ============ 内置考题页面路由 ============

@app.get("/exam-page/{page_id}")
async def get_exam_page(page_id: str, request: Request, preview: bool = False):
    """获取内置考题页面"""
    from .exam_pages import get_page_path
    file_path = get_page_path(page_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="考题页面不存在")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 记录访问
    db = _get_db()
    db.increment_page_stat(page_id, "visits")
    db.update_page_last_visit(page_id)

    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": "inline"}
    )


class PageTrackRequest(BaseModel):
    """页面访问追踪请求"""
    page_id: str
    event: str  # "visit" | "click" | "interaction"


@app.post("/api/exam-page/track")
async def track_page_event(data: PageTrackRequest):
    """记录页面访问/操作事件（由页面 JS 调用）"""
    db = _get_db()
    if data.event == "visit":
        db.increment_page_stat(data.page_id, "visits")
        db.update_page_last_visit(data.page_id)
    elif data.event == "click":
        db.increment_page_stat(data.page_id, "clicks")

    return {"ok": True}


@app.get("/api/exam-page/stats")
async def get_page_stats():
    """获取所有内置页面的访问统计"""
    return {"pages": _get_db().get_page_stats()}


@app.get("/exam/{filename}")
async def get_exam_paper(filename: str, request: Request):
    """获取试卷文件，动态替换 BASE_URL 占位符"""
    if filename not in ["v1.md", "v2.md", "v3.md"]:
        raise HTTPException(status_code=404, detail="试卷不存在")

    file_path = os.path.join(exam_papers_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="试卷文件不存在")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 动态推断 BASE_URL
    base_url = _get_base_url()
    if not base_url:
        # 从请求头推断
        host = request.headers.get("host", "localhost:8080")
        scheme = request.headers.get("x-forwarded-proto", "http")
        base_url = f"{scheme}://{host}"

    # 将所有 localhost:8080 替换为实际域名
    content = content.replace("http://localhost:8080", base_url)

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@app.get("/favicon.ico")
async def favicon():
    """忽略 favicon 请求"""
    return FileResponse(os.path.join(web_dir, "favicon.ico")) if os.path.exists(os.path.join(web_dir, "favicon.ico")) else b""


@app.get("/cert/{exam_token}")
async def get_cert_page(exam_token: str):
    """获取证书页面 - 动态查询考试成绩"""

    if not (session := _get_db().get_session(exam_token)):
        cert_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>考试成绩 - Agent Browser Exam</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #667eea, #764ba2); min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; }
        .card { background: white; border-radius: 20px; padding: 40px; max-width: 500px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        h1 { color: #333; } .error { color: #e74c3c; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="card">
        <h1>❌ 成绩不存在</h1>
        <p class="error">准考证号无效或已过期</p>
    </div>
</body>
</html>"""
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=cert_html)

    score_data = await _get_exam_score(session)

    task_rows = ""
    for tr in score_data.get("task_results", []):
        icon = "✅" if tr["correct"] else "❌"
        task_rows += f"<tr><td>{tr['task_id']}</td><td>{icon} {tr['score']}分</td></tr>"

    grade_colors = {"S": "#ffd700", "A": "#667eea", "B": "#48bb78", "C": "#f56565", "D": "#ed8936", "F": "#999"}
    grade_color = grade_colors.get(score_data["grade"], "#667eea")

    cert_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>考试成绩 - {score_data['agent_name']} - Agent Browser Exam</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        .card {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        h1 {{ color: #333; margin: 0 0 5px 0; }}
        .subtitle {{ color: #666; margin: 0 0 20px 0; }}
        .agent {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
        .score-display {{ margin: 20px 0; }}
        .score-number {{ font-size: 64px; font-weight: bold; color: #667eea; }}
        .grade-badge {{
            display: inline-block;
            font-size: 36px;
            font-weight: bold;
            color: white;
            background: {grade_color};
            width: 80px;
            height: 80px;
            line-height: 80px;
            border-radius: 50%;
            margin: 15px 0;
        }}
        .meta {{ color: #888; font-size: 14px; margin: 15px 0; }}
        .token-box {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-radius: 10px;
            font-family: monospace;
            font-size: 18px;
            margin: 15px 0;
            word-break: break-all;
        }}
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }}
        .results-table th, .results-table td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        .results-table th {{ background: #f8f9fa; }}
        .links {{ margin-top: 20px; }}
        .links a {{ color: #667eea; text-decoration: none; margin: 0 10px; }}
        .links a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🎉 考试成绩</h1>
            <p class="subtitle">Agent Browser Exam</p>
            <p class="agent">{score_data['agent_name']} · {score_data['agent_type']}</p>

            <div class="score-display">
                <div class="score-number">{score_data['total_score']}/{score_data['max_score']}</div>
                <div class="grade-badge">{score_data['grade']}</div>
            </div>

            <table class="results-table">
                <thead>
                    <tr><th>题号</th><th>得分</th></tr>
                </thead>
                <tbody>
                    {task_rows}
                </tbody>
            </table>

            <div class="token-box">{exam_token}</div>
            <p class="meta">用时 {score_data['total_time_seconds']:.1f} 秒</p>

            <div class="links">
                <a href="/web/#leaderboard">🏆 查看排行榜</a>
                <a href="/web">← 回到首页</a>
            </div>
        </div>
    </div>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=cert_html)


def generate_exam_token() -> str:
    """
    生成带 HMAC 签名的准考证号，防止 Agent 伪造。
    格式: {随机ID}_{HMAC签名}
    随机ID: 16 字符 hex (64 bit entropy)
    签名: 8 字符 hex (32 bit HMAC-SHA256)
    Agent 即使猜到 ID，没有 HMAC_SECRET 也无法伪造有效签名。
    """
    _hmac_secret = os.environ.get("EXAM_HMAC_SECRET", "agent_browser_exam_2026_secret")
    token_id = secrets.token_hex(8).upper()  # 16 字符
    sig = hmac.new(
        _hmac_secret.encode(),
        token_id.encode(),
        hashlib.sha256
    ).hexdigest()[:8].upper()
    return f"{token_id}_{sig}"


def verify_exam_token(token: str) -> bool:
    """验证准考证号的 HMAC 签名是否有效"""
    if "_" not in token:
        return False
    token_id, sig = token.rsplit("_", 1)
    _hmac_secret = os.environ.get("EXAM_HMAC_SECRET", "agent_browser_exam_2026_secret")
    expected_sig = hmac.new(
        _hmac_secret.encode(),
        token_id.encode(),
        hashlib.sha256
    ).hexdigest()[:8].upper()
    return hmac.compare_digest(sig, expected_sig)


def calculate_grade(total_score: int, max_score: int) -> str:
    ratio = total_score / max_score if max_score > 0 else 0
    if ratio >= 0.95:
        return "S"
    elif ratio >= 0.85:
        return "A"
    elif ratio >= 0.70:
        return "B"
    elif ratio >= 0.60:
        return "C"
    elif ratio >= 0.50:
        return "D"
    else:
        return "F"


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "Agent Browser Exam"}


@app.get("/api/tasks/{level}")
async def get_tasks(level: str):
    """获取题目列表"""
    if level not in ["v1", "v2", "v3"]:
        raise HTTPException(status_code=400, detail="无效的考试级别")

    tasks = get_tasks_for_level(level)
    return tasks


@app.get("/")
async def root():
    return {
        "name": "Agent Browser Exam",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /api/health",
            "register": "POST /api/register",
            "submit": "POST /api/submit",
            "score": "GET /api/score/{exam_token}",
            "leaderboard": "GET /api/leaderboard/{level}"
        }
    }


@app.post("/api/register")
async def register(request: Request, data: RegisterRequest):
    """注册考试，获取准考证号和第一题"""

    # 注册不需要 API Key，只检查 IP 频率限制
    ip = get_client_ip(request)

    # 检查 IP 频率限制（注册接口单独限制：每分钟 10 次）
    allowed, remaining = security_manager.check_rate_limit(f"register:{ip}", 10)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="注册过于频繁，请稍后再试"
        )

    if data.exam_id not in ["v1", "v2", "v3"]:
        raise HTTPException(status_code=400, detail="无效的考试级别")

    exam_token = generate_exam_token()

    # 获取题目
    tasks = get_tasks_for_level(data.exam_id)

    # 为 L3-4（GitHub Issue 讨论）注入 challenge_code
    challenge_code = None
    for task in tasks:
        if task.get("id") == "L3-4":
            challenge_code = secrets.token_hex(4).upper()  # 8字符大写十六进制
            # 将 challenge_code 嵌入 instructions
            task["instructions"] = (
                f"【你的专属验证码】Verify: {challenge_code}\n\n"
                + task["instructions"]
            )
            # 将 challenge_code 写入 validator_config，供验证器使用
            if task.get("validator_config"):
                task["validator_config"]["challenge_code"] = challenge_code
            break

    # 为 L3-5（GitHub Star）注入开考前 star 数
    for task in tasks:
        if task.get("id") == "L3-5":
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/repos/Yourdaylight/agent_browser_exam",
                        timeout=10.0
                    )
                    resp.raise_for_status()
                    star_count = resp.json().get("stargazers_count", 0)
                if task.get("validator_config"):
                    task["validator_config"]["initial_star_count"] = star_count
            except Exception:
                pass  # star 数获取失败不影响注册
            break

    # 按级别设置差异化超时时间
    EXAM_TIMEOUT = {"v1": 10, "v2": 20, "v3": 30}
    timeout_minutes = EXAM_TIMEOUT.get(data.exam_id, 30)

    # 创建会话
    session = ExamSession(
        exam_token=exam_token,
        agent_name=data.claw_name,
        agent_version=data.claw_version,
        agent_type=data.claw_type,
        skill_list=data.skill_list,
        model_name=data.model_name,
        exam_id=ExamLevel(data.exam_id),
        started_at=datetime.now(),
        tasks=tasks,
        current_task_index=0,
        timeout_minutes=timeout_minutes,
    )

    _get_db().save_session(session)

    return {
        "exam_token": exam_token,
        "total_questions": len(tasks),
        "total_score": sum(t["max_score"] for t in tasks),
        "first_question": tasks[0] if tasks else None,
        "exam_id": data.exam_id,
        "expires_in_minutes": timeout_minutes,
        "resume_hint": (
            f"[重要] 请务必保存你的准考证号: {exam_token}\n"
            f"如果你的对话因上下文超长而中断，可以在新对话中调用 GET /api/next/{exam_token} 继续答题。\n"
            f"所有已提交的答案会保留，不会丢失。"
        ),
    }


@app.post("/api/submit")
async def submit_answer(request: Request, data: TaskSubmit):
    """提交答案或执行日志"""

    # 验证准考证号签名
    if not verify_exam_token(data.exam_token):
        raise HTTPException(status_code=403, detail="无效的准考证号，签名验证失败")

    # 提交不需要 API Key，使用 exam_token 验证
    ip = get_client_ip(request)

    # 提交频率限制
    allowed, remaining = security_manager.check_rate_limit(f"submit:{ip}", 60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="提交过于频繁，请稍后再试"
        )

    exam_token = data.exam_token
    task_id = data.task_id

    session = _get_db().get_session(exam_token)
    if not session:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    # 检查是否已超时
    if datetime.now() - session.started_at > timedelta(minutes=session.timeout_minutes):
        raise HTTPException(status_code=410, detail="考试已超时")

    # 查找题目配置
    task_config = None
    for t in session.tasks:
        if t["id"] == task_id:
            task_config = t
            break

    if not task_config:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 创建验证器
    validator_config = task_config.get("validator_config")
    validator = create_validator(validator_config)

    if not validator:
        raise HTTPException(status_code=500, detail="题目验证器未配置")

    # 执行验证
    # data.execution_log 已经被 Pydantic 解析为 ExecutionLog 对象，直接使用
    result = await validator.validate(data.answer, data.execution_log)

    # 记录结果
    task_result = TaskResult(
        task_id=task_id,
        correct=result.correct,
        score=result.score,
        max_score=result.max_score,
        submitted_at=datetime.now()
    )
    session.results[task_id] = task_result

    # 获取下一题
    next_task = None
    current_idx = session.current_task_index

    for i, t in enumerate(session.tasks):
        if t["id"] == task_id:
            current_idx = i
            break

    if current_idx + 1 < len(session.tasks):
        next_task = session.tasks[current_idx + 1]
        session.current_task_index = current_idx + 1
    else:
        session.completed = True

    # 持久化 session
    _get_db().save_session(session)

    # 如果完成，生成成绩
    if session.completed:
        await _finalize_exam(session)

    result = {
        "correct": result.correct,
        "score": result.score,
        "progress": {
            "completed": len(session.results),
            "total": len(session.tasks)
        },
        "next_question": next_task,
        "all_done": session.completed,
        "feedback": result.feedback,
        "details": result.details,
        "exam_token": exam_token,
    }
    if not session.completed:
        result["resume_hint"] = (
            f"准考证号: {exam_token} (请保存)\n"
            f"如对话中断，用 GET /api/next/{exam_token} 继续答题"
        )
    return result


@app.get("/api/next/{exam_token}")
async def get_next_question(exam_token: str):
    """断线重连时获取当前题目"""

    if not verify_exam_token(exam_token):
        raise HTTPException(status_code=403, detail="无效的准考证号")

    session = _get_db().get_session(exam_token)
    if not session:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    if session.completed:
        return {"all_done": True, "score": await _get_total_score(session)}

    # 找到下一个未完成的题目
    for i, t in enumerate(session.tasks):
        if t["id"] not in session.results:
            session.current_task_index = i
            _get_db().save_session(session)
            return {
                "next_question": t,
                "all_done": False,
                "progress": {
                    "completed": len(session.results),
                    "total": len(session.tasks)
                },
                "resume_hint": (
                    f"已从断点恢复！准考证号: {exam_token}\n"
                    f"如再次中断，用 GET /api/next/{exam_token} 继续答题"
                ),
            }

    return {"all_done": True}


@app.get("/api/score/{exam_token}")
async def get_score(exam_token: str):
    """获取考试成绩"""

    if not verify_exam_token(exam_token):
        raise HTTPException(status_code=403, detail="无效的准考证号")

    session = _get_db().get_session(exam_token)
    if not session:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    if not session.completed:
        # 返回当前进度
        return {
            "status": "in_progress",
            "completed": len(session.results),
            "total": len(session.tasks),
            "current_score": sum(r.score for r in session.results.values())
        }

    return await _get_exam_score(session)


async def _finalize_exam(session: ExamSession):
    """完成考试，计算成绩"""

    # 更新排行榜
    level = session.exam_id.value
    score = sum(r.score for r in session.results.values())
    max_score = sum(r.max_score for r in session.results.values())
    total_time = (datetime.now() - session.started_at).total_seconds()
    grade = calculate_grade(score, max_score)

    entry = LeaderboardEntry(
        rank=0,
        agent_name=session.agent_name,
        agent_type=session.agent_type,
        total_score=score,
        max_score=max_score,
        total_time_seconds=total_time,
        grade=grade,
        exam_id=session.exam_id
    )

    _get_db().add_leaderboard_entry(level, entry)


async def _get_total_score(session: ExamSession) -> int:
    return sum(r.score for r in session.results.values())


async def _get_exam_score(session: ExamSession) -> Dict:
    score = await _get_total_score(session)
    max_score = sum(t["max_score"] for t in session.tasks)
    total_time = (datetime.now() - session.started_at).total_seconds()
    grade = calculate_grade(score, max_score)

    return {
        "status": "completed",
        "exam_token": session.exam_token,
        "agent_name": session.agent_name,
        "agent_type": session.agent_type,
        "total_score": score,
        "max_score": max_score,
        "total_time_seconds": total_time,
        "grade": grade,
        "task_results": [
            {
                "task_id": r.task_id,
                "correct": r.correct,
                "score": r.score,
                "max_score": r.max_score
            }
            for r in session.results.values()
        ],
        "certificate_url": f"/api/certificate/{session.exam_token}"
    }


@app.get("/api/leaderboard/{level}")
async def get_leaderboard(level: str):
    """获取排行榜"""

    if level not in ["v1", "v2", "v3"]:
        raise HTTPException(status_code=404, detail="考试级别不存在")

    entries = _get_db().get_leaderboard(level)

    return {
        "level": level,
        "entries": [
            {
                "rank": e.rank,
                "agent_name": e.agent_name,
                "agent_type": e.agent_type,
                "total_score": e.total_score,
                "max_score": e.max_score,
                "total_time_seconds": e.total_time_seconds,
                "grade": e.grade
            }
            for e in entries
        ]
    }


@app.get("/api/certificate/{exam_token}")
async def get_certificate(exam_token: str):
    """获取证书"""

    if not verify_exam_token(exam_token):
        raise HTTPException(status_code=403, detail="无效的准考证号")

    session = _get_db().get_session(exam_token)
    if not session:
        raise HTTPException(status_code=404, detail="考试会话不存在")

    if not session.completed:
        raise HTTPException(status_code=400, detail="考试尚未完成")

    score = sum(r.score for r in session.results.values())
    max_score = sum(t["max_score"] for t in session.tasks)
    grade = calculate_grade(score, max_score)

    return {
        "certificate_url": f"https://exam.finnie.ai/cert/{exam_token}.png",
        "exam_token": exam_token,
        "agent_name": session.agent_name,
        "agent_type": session.agent_type,
        "total_score": score,
        "max_score": max_score,
        "grade": grade,
        "exam_id": session.exam_id.value,
        "issued_at": datetime.now().isoformat()
    }


# ============ 管理接口 ============

@app.post("/admin/api-key")
async def create_api_key(
    request: Request,
    owner: str,
    exam_limit: int = 10,
    rate_limit_per_minute: int = 30
):
    """创建新的 API Key（需要 admin 权限）"""
    ip, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    raw_key, config = security_manager.generate_api_key(
        owner=owner,
        exam_limit=exam_limit,
        rate_limit_per_minute=rate_limit_per_minute
    )

    return {
        "api_key": raw_key,  # 只在创建时返回明文
        "owner": owner,
        "exam_limit": exam_limit,
        "rate_limit_per_minute": rate_limit_per_minute,
        "message": "请妥善保存 API Key，只返回一次"
    }


@app.delete("/admin/api-key/{owner}")
async def revoke_api_key(request: Request, owner: str):
    """撤销指定所有者的 API Key"""
    ip, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    # 查找并禁用该所有者的 key
    for key, cfg in security_manager.api_keys.items():
        if cfg.owner == owner:
            cfg.is_active = False

    return {"message": f"已禁用 {owner} 的 API Key"}


@app.post("/admin/ip/block/{ip}")
async def block_ip(request: Request, ip: str):
    """封禁 IP 地址"""
    ip_addr, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    security_manager.block_ip(ip)
    return {"message": f"已封禁 IP: {ip}"}


@app.post("/admin/ip/unblock/{ip}")
async def unblock_ip(request: Request, ip: str):
    """解封 IP 地址"""
    ip_addr, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    security_manager.unblock_ip(ip)
    return {"message": f"已解封 IP: {ip}"}


@app.post("/admin/ip/allow/{ip}")
async def allow_ip(request: Request, ip: str):
    """将 IP 加入白名单"""
    ip_addr, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    security_manager.allow_ip(ip)
    return {"message": f"已将 IP 加入白名单: {ip}"}


@app.get("/admin/stats")
async def get_stats(request: Request):
    """获取安全统计信息"""
    ip_addr, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    return {
        "security": security_manager.get_stats(),
        "active_sessions": _get_db().session_count(),
        "leaderboard_entries": {
            level: _get_db().leaderboard_count(level)
            for level in ["v1", "v2", "v3"]
        }
    }


@app.post("/admin/cleanup")
async def cleanup(request: Request):
    """清理过期会话"""
    ip_addr, key_config = await verify_request(request)

    if not key_config or not key_config.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    cleaned = security_manager.cleanup_stale_sessions()

    # 清理过期的考试会话
    cleaned_exam = _get_db().cleanup_expired_sessions(60)

    return {
        "cleaned_ip_sessions": cleaned,
        "cleaned_exam_sessions": cleaned_exam
    }


def start_server(host: str = "0.0.0.0", port: int = 8080):
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
