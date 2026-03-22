"""
轻量级 SQLite 存储后端 — 替代内存字典

- 考试会话 (exam_sessions)
- 排行榜 (leaderboard)
- 页面统计 (page_stats)
- 线程安全，使用 check_same_thread=False
"""
import json
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .models import ExamSession, LeaderboardEntry, TaskResult


class Storage:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "exam.db"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._db_path = db_path
                cls._instance._local = threading.local()
                cls._instance._init_db()
            return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        """每个线程独立连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level=None,  # autocommit for writes
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS exam_sessions (
                exam_token TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS page_stats (
                page_id TEXT PRIMARY KEY,
                visits INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                last_visit TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_leaderboard_level ON leaderboard(level);
            CREATE INDEX IF NOT EXISTS idx_sessions_created ON exam_sessions(created_at);
        """)

        # 兼容迁移：为旧表添加 device_fingerprint 列
        try:
            self._get_conn().execute(
                "ALTER TABLE exam_sessions ADD COLUMN device_fingerprint TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass  # 列已存在

        # 指纹索引（在列确认存在后创建）
        try:
            self._get_conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_fingerprint ON exam_sessions(device_fingerprint)"
            )
        except sqlite3.OperationalError:
            pass  # 索引已存在或列不存在

    # ---- Exam Session ----

    def save_session(self, session: ExamSession):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO exam_sessions (exam_token, data, device_fingerprint) VALUES (?, ?, ?)",
            (session.exam_token, session.model_dump_json(), session.device_fingerprint),
        )

    def get_session(self, exam_token: str) -> Optional[ExamSession]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM exam_sessions WHERE exam_token = ?",
            (exam_token,),
        ).fetchone()
        if row:
            return ExamSession.model_validate_json(row["data"])
        return None

    def get_session_by_fingerprint(self, fingerprint: str, exam_id: str) -> Optional[ExamSession]:
        """按设备指纹 + 考试级别查找未过期的活跃会话"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM exam_sessions WHERE device_fingerprint = ?",
            (fingerprint,),
        ).fetchall()
        for row in rows:
            try:
                session = ExamSession.model_validate_json(row["data"])
                if session.exam_id.value == exam_id and not session.completed:
                    if datetime.now() - session.started_at <= timedelta(minutes=session.timeout_minutes):
                        return session
            except Exception:
                pass
        return None

    def delete_session(self, exam_token: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM exam_sessions WHERE exam_token = ?", (exam_token,))

    def get_all_sessions(self) -> Dict[str, ExamSession]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM exam_sessions").fetchall()
        return {ExamSession.model_validate_json(r["data"]).exam_token: ExamSession.model_validate_json(r["data"]) for r in rows}

    def cleanup_expired_sessions(self, max_age_minutes: int = 60) -> int:
        conn = self._get_conn()
        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
        # 先加载，检查 started_at (在 data JSON 里)
        rows = conn.execute("SELECT exam_token, data FROM exam_sessions").fetchall()
        expired = []
        for row in rows:
            try:
                session = ExamSession.model_validate_json(row["data"])
                if datetime.now() - session.started_at > timedelta(minutes=max_age_minutes):
                    expired.append(row["exam_token"])
            except Exception:
                pass
        for token in expired:
            self.delete_session(token)
        return len(expired)

    def session_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as c FROM exam_sessions").fetchone()
        return row["c"]

    # ---- Leaderboard ----

    def add_leaderboard_entry(self, level: str, entry: LeaderboardEntry):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO leaderboard (level, data) VALUES (?, ?)",
            (level, entry.model_dump_json()),
        )

    def get_leaderboard(self, level: str, limit: int = 20) -> List[LeaderboardEntry]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM leaderboard WHERE level = ? ORDER BY id ASC",
            (level,),
        ).fetchall()
        entries = [LeaderboardEntry.model_validate_json(r["data"]) for r in rows]
        # Sort by score desc, time asc
        entries.sort(key=lambda x: (-x.total_score, x.total_time_seconds))
        for i, e in enumerate(entries):
            e.rank = i + 1
        return entries[:limit]

    def leaderboard_count(self, level: str) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM leaderboard WHERE level = ?", (level,)
        ).fetchone()
        return row["c"]

    # ---- Page Stats ----

    def increment_page_stat(self, page_id: str, field: str):
        conn = self._get_conn()
        conn.execute(
            f"INSERT INTO page_stats (page_id, {field}) VALUES (?, 1) "
            f"ON CONFLICT(page_id) DO UPDATE SET {field} = {field} + 1",
            (page_id,),
        )

    def update_page_last_visit(self, page_id: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO page_stats (page_id, last_visit) VALUES (?, ?) "
            "ON CONFLICT(page_id) DO UPDATE SET last_visit = ?",
            (page_id, datetime.now().isoformat(), datetime.now().isoformat()),
        )

    def get_page_stats(self) -> Dict[str, Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM page_stats").fetchall()
        return {
            r["page_id"]: {
                "visits": r["visits"],
                "clicks": r["clicks"],
                "last_visit": r["last_visit"],
            }
            for r in rows
        }


# 全局单例
def get_storage() -> Storage:
    db_path = os.environ.get("EXAM_DB_PATH", "")
    if not db_path:
        # 默认在项目根目录下
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exam.db")
    return Storage(db_path)
