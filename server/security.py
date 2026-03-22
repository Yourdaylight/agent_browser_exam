"""
安全模块 - API Key 认证、频率限制、IP 防护
"""
import os
import time
import hashlib
import secrets
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import HTTPException, Request
from threading import Lock


@dataclass
class APIKeyConfig:
    """API Key 配置"""
    key: str
    owner: str  # 密钥所有者标识
    is_admin: bool = False
    exam_limit: int = 10  # 允许的最大考试次数
    rate_limit_per_minute: int = 30  # 每分钟请求限制
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    exam_count: int = 0  # 当前已使用考试次数
    is_active: bool = True


@dataclass
class RateLimitEntry:
    """频率限制记录"""
    count: int = 0
    window_start: float = field(default_factory=time.time)


class SecurityManager:
    """安全管理器"""

    def __init__(self):
        self.api_keys: Dict[str, APIKeyConfig] = {}
        self.rate_limits: Dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self.ip_blacklist: set = set()
        self.ip_whitelist: set = set()
        self.exam_sessions_by_ip: Dict[str, set] = defaultdict(set)  # IP -> exam_tokens
        self._lock = Lock()

        # 加载环境变量中的默认 admin key
        admin_key = os.environ.get("EXAM_ADMIN_KEY")
        if admin_key:
            self.add_api_key(admin_key, "admin", is_admin=True)

    def add_api_key(self, key: str, owner: str, is_admin: bool = False,
                    exam_limit: int = 10, rate_limit_per_minute: int = 30) -> None:
        """添加 API Key"""
        hashed = self._hash_key(key)
        with self._lock:
            self.api_keys[hashed] = APIKeyConfig(
                key=hashed,
                owner=owner,
                is_admin=is_admin,
                exam_limit=exam_limit,
                rate_limit_per_minute=rate_limit_per_minute
            )

    def verify_api_key(self, key: Optional[str]) -> Tuple[bool, Optional[APIKeyConfig]]:
        """验证 API Key"""
        if not key:
            return False, None

        hashed = self._hash_key(key)
        with self._lock:
            config = self.api_keys.get(hashed)
            if not config or not config.is_active:
                return False, None

            # 更新最后使用时间
            config.last_used = datetime.now()
            return True, config

    def _hash_key(self, key: str) -> str:
        """对 key 进行哈希处理"""
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def check_rate_limit(self, identifier: str, limit: int) -> Tuple[bool, int]:
        """
        检查频率限制
        返回: (是否通过, 剩余请求数)
        """
        now = time.time()
        with self._lock:
            entry = self.rate_limits[identifier]

            # 如果窗口期已过，重置
            if now - entry.window_start > 60:
                entry.count = 0
                entry.window_start = now

            if entry.count >= limit:
                return False, 0

            entry.count += 1
            return True, limit - entry.count

    def block_ip(self, ip: str) -> None:
        """封禁 IP"""
        with self._lock:
            self.ip_blacklist.add(ip)
            # 从白名单移除（如果有）
            self.ip_whitelist.discard(ip)

    def unblock_ip(self, ip: str) -> None:
        """解封 IP"""
        with self._lock:
            self.ip_blacklist.discard(ip)

    def allow_ip(self, ip: str) -> None:
        """添加 IP 到白名单"""
        with self._lock:
            self.ip_whitelist.add(ip)
            # 从黑名单移除（如果有）
            self.ip_blacklist.discard(ip)

    def check_ip(self, ip: str) -> Tuple[bool, str]:
        """
        检查 IP 状态
        返回: (是否允许, 原因)
        """
        with self._lock:
            # 白名单优先
            if ip in self.ip_whitelist:
                return True, "whitelist"

            # 黑名单
            if ip in self.ip_blacklist:
                return False, "blacklisted"

            return True, "allowed"

    def record_exam_session(self, ip: str, exam_token: str) -> bool:
        """
        记录考试会话
        返回: 是否允许创建新会话
        """
        with self._lock:
            sessions = self.exam_sessions_by_ip[ip]

            # 检查是否已达到限制
            if len(sessions) >= 10:  # 每个 IP 最多 10 个未完成的考试
                return False

            sessions.add(exam_token)
            return True

    def remove_exam_session(self, ip: str, exam_token: str) -> None:
        """移除考试会话记录"""
        with self._lock:
            sessions = self.exam_sessions_by_ip.get(ip)
            if sessions:
                sessions.discard(exam_token)

    def cleanup_stale_sessions(self, max_age_minutes: int = 60) -> int:
        """
        清理过期的会话记录
        返回: 清理的会话数量
        """
        with self._lock:
            cleaned = 0
            now = datetime.now()
            for ip, sessions in list(self.exam_sessions_by_ip.items()):
                # 保留最近活跃的会话
                if len(sessions) > 5:
                    # 保留一半
                    to_remove = len(sessions) // 2
                    for _ in range(to_remove):
                        sessions.pop()
                        cleaned += 1
            return cleaned

    def generate_api_key(self, owner: str, **kwargs) -> Tuple[str, APIKeyConfig]:
        """
        生成新的 API Key
        返回: (明文 key, 配置对象)
        """
        raw_key = f"exam_{secrets.token_urlsafe(24)}"
        config = APIKeyConfig(
            key=self._hash_key(raw_key),
            owner=owner,
            **kwargs
        )
        with self._lock:
            self.api_keys[config.key] = config

        return raw_key, config

    def get_stats(self) -> Dict:
        """获取安全统计信息"""
        with self._lock:
            return {
                "total_api_keys": len(self.api_keys),
                "active_api_keys": sum(1 for k in self.api_keys.values() if k.is_active),
                "blocked_ips": len(self.ip_blacklist),
                "whitelisted_ips": len(self.ip_whitelist),
                "active_ips": len(self.exam_sessions_by_ip)
            }


# 全局安全管理器
security_manager = SecurityManager()


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP"""
    # 优先使用 X-Forwarded-For 头
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # 其次使用 X-Real-IP 头
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 最后使用直接连接的 IP
    if request.client:
        return request.client.host

    return "unknown"


async def verify_request(request: Request, require_key: bool = True) -> Tuple[str, APIKeyConfig]:
    """
    验证请求的安全性
    返回: (客户端 IP, API Key 配置)

    抛出 HTTPException 如果验证失败
    """
    ip = get_client_ip(request)

    # 检查 IP 是否被封禁
    allowed, reason = security_manager.check_ip(ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"IP 地址已被限制: {reason}"
        )

    # 验证 API Key（如果需要）
    api_key = request.headers.get("X-API-Key")
    if require_key:
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="缺少 API Key，请通过 X-API-Key 头提供"
            )

        valid, config = security_manager.verify_api_key(api_key)
        if not valid:
            raise HTTPException(
                status_code=401,
                detail="无效的 API Key"
            )

        # 检查频率限制
        allowed, remaining = security_manager.check_rate_limit(
            f"api:{config.owner}",
            config.rate_limit_per_minute
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试"
            )

        return ip, config

    return ip, None


def add_security_headers(response):
    """添加安全响应头"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
