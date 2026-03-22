"""
轻量级 SQLite 存储后端 — 替代内存字典

- 考试会话 (exam_sessions): 复合主键 (exam_token, exam_id) 支持同一准考证号多级别
- 排行榜 (leaderboard)
- 页面统计 (page_stats)
- 线程安全，使用 check_same_thread=False
"""
import json
import logging
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .models import ExamSession, LeaderboardEntry, TaskResult

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Schema & Migration
    # ------------------------------------------------------------------

    def _init_db(self):
        conn = self._get_conn()

        # 确保 leaderboard / page_stats 表存在（这两张表结构不变）
        conn.executescript("""
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
        """)

        # 处理 exam_sessions 表：检测是否需要从旧结构迁移
        self._migrate_exam_sessions(conn)

    def _is_old_schema(self, conn: sqlite3.Connection) -> bool:
        """检查 exam_sessions 是否为旧的单 PK (exam_token) 结构"""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='exam_sessions'"
        ).fetchone()
        if row is None:
            return False  # 表不存在，直接建新表
        ddl: str = row[0] or ""
        # 新表含有 exam_id 列；旧表没有
        return "exam_id" not in ddl.lower()

    def _migrate_exam_sessions(self, conn: sqlite3.Connection):
        """
        将 exam_sessions 从旧结构（exam_token TEXT PK）迁移到
        新结构（exam_token + exam_id 复合 PK）。

        旧数据的 exam_id 从 JSON data 的 $.exam_id 中提取。
        使用事务保证原子性。
        """
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exam_sessions'"
        ).fetchone()

        if not table_exists:
            # 全新部署，直接建新表
            self._create_new_sessions_table(conn)
            return

        if not self._is_old_schema(conn):
            # 已经是新结构，无需迁移
            return

        logger.info("[storage] Migrating exam_sessions to composite PK (exam_token, exam_id) ...")

        try:
            # 在 autocommit 模式下手动管理事务
            conn.execute("BEGIN IMMEDIATE")

            # 1. 读取旧数据
            rows = conn.execute("SELECT exam_token, data, device_fingerprint FROM exam_sessions").fetchall()

            # 2. 重命名旧表
            conn.execute("ALTER TABLE exam_sessions RENAME TO _exam_sessions_old")

            # 3. 建新表（不能用 executescript，会自动 COMMIT）
            conn.execute("""
                CREATE TABLE exam_sessions (
                    exam_token TEXT NOT NULL,
                    exam_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    device_fingerprint TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (exam_token, exam_id)
                )
            """)

            # 4. 迁移数据：从 JSON 里提取 exam_id
            for row in rows:
                try:
                    data_json = json.loads(row["data"])
                    exam_id = data_json.get("exam_id", "v1")
                    fp = row["device_fingerprint"] if "device_fingerprint" in row.keys() else ""
                    conn.execute(
                        "INSERT OR IGNORE INTO exam_sessions (exam_token, exam_id, data, device_fingerprint) VALUES (?, ?, ?, ?)",
                        (row["exam_token"], exam_id, row["data"], fp),
                    )
                except Exception as e:
                    logger.warning(f"[storage] Skipping bad row {row['exam_token']}: {e}")

            # 5. 删除旧表
            conn.execute("DROP TABLE _exam_sessions_old")

            conn.execute("COMMIT")
            logger.info("[storage] Migration completed successfully.")

            # 创建索引（在事务外）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON exam_sessions(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_fingerprint ON exam_sessions(device_fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON exam_sessions(exam_token)")

        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"[storage] Migration failed, rolled back: {e}")
            raise

    def _create_new_sessions_table(self, conn: sqlite3.Connection):
        """创建新版 exam_sessions 表（复合主键）"""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS exam_sessions (
                exam_token TEXT NOT NULL,
                exam_id TEXT NOT NULL,
                data TEXT NOT NULL,
                device_fingerprint TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (exam_token, exam_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_created ON exam_sessions(created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_fingerprint ON exam_sessions(device_fingerprint);
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON exam_sessions(exam_token);
        """)

    # ------------------------------------------------------------------
    # Exam Session CRUD
    # ------------------------------------------------------------------

    def save_session(self, session: ExamSession):
        """保存会话，以 (exam_token, exam_id) 为复合主键"""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO exam_sessions (exam_token, exam_id, data, device_fingerprint) VALUES (?, ?, ?, ?)",
            (session.exam_token, session.exam_id.value, session.model_dump_json(), session.device_fingerprint),
        )

    def get_session(self, exam_token: str, exam_id: Optional[str] = None) -> Optional[ExamSession]:
        """
        获取会话。
        - 如果指定了 exam_id → 精确查找 (exam_token, exam_id)
        - 如果未指定 exam_id → 查找该 token 下最新的会话（向后兼容）
        """
        conn = self._get_conn()
        if exam_id:
            row = conn.execute(
                "SELECT data FROM exam_sessions WHERE exam_token = ? AND exam_id = ?",
                (exam_token, exam_id),
            ).fetchone()
        else:
            # 向后兼容：返回该 token 下最新创建的会话
            row = conn.execute(
                "SELECT data FROM exam_sessions WHERE exam_token = ? ORDER BY created_at DESC LIMIT 1",
                (exam_token,),
            ).fetchone()
        if row:
            return ExamSession.model_validate_json(row["data"])
        return None

    def get_sessions_by_token(self, exam_token: str) -> List[ExamSession]:
        """获取同一 exam_token 下的所有级别会话"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM exam_sessions WHERE exam_token = ? ORDER BY created_at ASC",
            (exam_token,),
        ).fetchall()
        sessions = []
        for row in rows:
            try:
                sessions.append(ExamSession.model_validate_json(row["data"]))
            except Exception:
                pass
        return sessions

    def get_completed_levels(self, exam_token: str) -> List[str]:
        """获取该 exam_token 已完成的级别列表"""
        sessions = self.get_sessions_by_token(exam_token)
        return [s.exam_id.value for s in sessions if s.completed]

    def get_session_by_fingerprint(self, fingerprint: str, exam_id: str) -> Optional[ExamSession]:
        """按设备指纹 + 考试级别查找未过期的活跃会话"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM exam_sessions WHERE device_fingerprint = ? AND exam_id = ?",
            (fingerprint, exam_id),
        ).fetchall()
        for row in rows:
            try:
                session = ExamSession.model_validate_json(row["data"])
                if not session.completed:
                    if datetime.now() - session.started_at <= timedelta(minutes=session.timeout_minutes):
                        return session
            except Exception:
                pass
        return None

    def delete_session(self, exam_token: str, exam_id: Optional[str] = None):
        conn = self._get_conn()
        if exam_id:
            conn.execute(
                "DELETE FROM exam_sessions WHERE exam_token = ? AND exam_id = ?",
                (exam_token, exam_id),
            )
        else:
            conn.execute("DELETE FROM exam_sessions WHERE exam_token = ?", (exam_token,))

    def get_all_sessions(self) -> Dict[str, ExamSession]:
        """返回所有会话（key 为 exam_token:exam_id）"""
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM exam_sessions").fetchall()
        result = {}
        for r in rows:
            try:
                s = ExamSession.model_validate_json(r["data"])
                result[f"{s.exam_token}:{s.exam_id.value}"] = s
            except Exception:
                pass
        return result

    def cleanup_expired_sessions(self, max_age_minutes: int = 60) -> int:
        conn = self._get_conn()
        rows = conn.execute("SELECT exam_token, exam_id, data FROM exam_sessions").fetchall()
        expired = []
        for row in rows:
            try:
                session = ExamSession.model_validate_json(row["data"])
                if datetime.now() - session.started_at > timedelta(minutes=max_age_minutes):
                    expired.append((row["exam_token"], row["exam_id"]))
            except Exception:
                pass
        for token, eid in expired:
            self.delete_session(token, eid)
        return len(expired)

    def session_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as c FROM exam_sessions").fetchone()
        return row["c"]

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Page Stats
    # ------------------------------------------------------------------

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
