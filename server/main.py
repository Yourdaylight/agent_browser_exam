"""
Agent Browser 能力考试 - 验证服务器
"""
import uuid
import asyncio
import os
import time
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
    RegisterRequest
)
from .validators import (
    BrowserActionValidator, BrowserContextHTTPValidator,
    OpenPageAndExtractTitleValidator, OpenPageAndScreenshotValidator,
    ClickElementValidator, TypeAndSubmitValidator, WaitForContentValidator,
    LoopDetectionValidator, RefMapCacheValidator, ErrorTranslationValidator,
    OnDemandSnapshotValidator, ControlHandoverValidator,
    SearchValidator, MultiStepValidator
)
from .security import (
    security_manager, get_client_ip, verify_request,
    add_security_headers, SecurityManager
)


# 题目配置
from exam_papers import get_tasks_for_level


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
    elif validator_type == "JSONPathValidator":
        from .validators import JSONPathValidator
        return JSONPathValidator(
            url=validator_config["url"],
            json_path=validator_config["json_path"],
            expected=validator_config.get("expected")
        )
    elif validator_type == "HTTPAPIValidator":
        from .validators import HTTPAPIValidator
        return HTTPAPIValidator(
            expected_url=validator_config["expected_url"],
            expected_pattern=validator_config.get("expected_pattern")
        )
    return None


# 存储
exam_sessions: Dict[str, ExamSession] = {}
leaderboard: Dict[str, list] = {"v1": [], "v2": [], "v3": []}


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


@app.get("/exam/{filename}")
async def get_exam_paper(filename: str):
    """获取试卷文件"""
    if filename not in ["v1.md", "v2.md", "v3.md"]:
        raise HTTPException(status_code=404, detail="试卷不存在")

    file_path = os.path.join(exam_papers_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="试卷文件不存在")

    return FileResponse(
        file_path,
        media_type="text/markdown",
        filename=filename
    )


@app.get("/favicon.ico")
async def favicon():
    """忽略 favicon 请求"""
    return FileResponse(os.path.join(web_dir, "favicon.ico")) if os.path.exists(os.path.join(web_dir, "favicon.ico")) else b""


@app.get("/cert/{exam_token}")
async def get_cert_page(exam_token: str):
    """获取证书页面 - 动态查询考试成绩"""

    if exam_token not in exam_sessions:
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

    session = exam_sessions[exam_token]
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
    return uuid.uuid4().hex[:12].upper()


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
        current_task_index=0
    )

    exam_sessions[exam_token] = session

    return {
        "exam_token": exam_token,
        "total_questions": len(tasks),
        "total_score": sum(t["max_score"] for t in tasks),
        "first_question": tasks[0] if tasks else None,
        "exam_id": data.exam_id,
        "expires_in_minutes": 30
    }


@app.post("/api/submit")
async def submit_answer(request: Request, data: TaskSubmit):
    """提交答案或执行日志"""

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

    if exam_token not in exam_sessions:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    session = exam_sessions[exam_token]

    # 检查是否已超时（30分钟）
    if datetime.now() - session.started_at > timedelta(minutes=30):
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
    execution_log = ExecutionLog(**data.execution_log) if data.execution_log else None
    result = await validator.validate(data.answer, execution_log)

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

    # 如果完成，生成成绩
    if session.completed:
        await _finalize_exam(session)

    return {
        "correct": result.correct,
        "score": result.score,
        "progress": {
            "completed": len(session.results),
            "total": len(session.tasks)
        },
        "next_question": next_task,
        "all_done": session.completed,
        "feedback": result.feedback,
        "details": result.details
    }


@app.get("/api/next/{exam_token}")
async def get_next_question(exam_token: str):
    """断线重连时获取当前题目"""

    if exam_token not in exam_sessions:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    session = exam_sessions[exam_token]

    if session.completed:
        return {"all_done": True, "score": await _get_total_score(session)}

    # 找到下一个未完成的题目
    for i, t in enumerate(session.tasks):
        if t["id"] not in session.results:
            session.current_task_index = i
            return {"next_question": t, "all_done": False}

    return {"all_done": True}


@app.get("/api/score/{exam_token}")
async def get_score(exam_token: str):
    """获取考试成绩"""

    if exam_token not in exam_sessions:
        raise HTTPException(status_code=404, detail="考试会话不存在或已过期")

    session = exam_sessions[exam_token]

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
        rank=0,  # 稍后计算
        agent_name=session.agent_name,
        agent_type=session.agent_type,
        total_score=score,
        max_score=max_score,
        total_time_seconds=total_time,
        grade=grade,
        exam_id=session.exam_id
    )

    # 添加到排行榜并排序
    leaderboard[level].append(entry)
    leaderboard[level].sort(key=lambda x: (-x.total_score, x.total_time_seconds))

    # 更新排名
    for i, e in enumerate(leaderboard[level]):
        e.rank = i + 1


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

    if level not in leaderboard:
        raise HTTPException(status_code=404, detail="考试级别不存在")

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
            for e in leaderboard[level][:20]  # 只返回前20
        ]
    }


@app.get("/api/certificate/{exam_token}")
async def get_certificate(exam_token: str):
    """获取证书"""

    if exam_token not in exam_sessions:
        raise HTTPException(status_code=404, detail="考试会话不存在")

    session = exam_sessions[exam_token]

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
        "active_sessions": len(exam_sessions),
        "leaderboard_entries": {
            level: len(entries) for level, entries in leaderboard.items()
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
    now = datetime.now()
    expired_tokens = [
        token for token, session in exam_sessions.items()
        if now - session.started_at > timedelta(minutes=60)
    ]
    for token in expired_tokens:
        del exam_sessions[token]

    return {
        "cleaned_ip_sessions": cleaned,
        "cleaned_exam_sessions": len(expired_tokens)
    }


def start_server(host: str = "0.0.0.0", port: int = 8080):
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
