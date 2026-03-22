"""
验证器 - 负责自动验证 Agent 的执行结果
"""
import re
from typing import Dict, Any, Optional, List, Tuple
from abc import ABC, abstractmethod
from .models import ExecutionLog, Action, ActionType, ValidationResult


class BaseValidator(ABC):
    """验证器基类"""

    @abstractmethod
    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        """验证答案或执行日志"""
        pass

    @abstractmethod
    def get_score(self) -> Tuple[int, int]:
        """返回 (得分, 满分)"""
        pass


# ============================================
# 核心验证器：基于执行日志的浏览器操作验证
# ============================================

class BrowserActionValidator(BaseValidator):
    """
    浏览器操作验证器 - 核心验证器
    验证 Agent 是否真正执行了浏览器操作，而非纯 HTTP 请求

    验证原则：
    1. 必须有 navigate 操作（打开网页）
    2. 根据题目类型验证相应的操作（click/type/evaluate/screenshot等）
    3. 答案必须来自浏览器 DOM/截图，而非直接 API 调用
    """

    def __init__(
        self,
        url_pattern: str = None,
        required_actions: List[Dict[str, Any]] = None,
        expected_content: str = None,
        validate_selector: str = None,
        validate_action: str = None,
        max_score: int = 5
    ):
        """
        Args:
            url_pattern: URL 正则模式，如 "example\\.com"
            required_actions: 必需的操作列表，如 [{"type": "click", "selector_contains": "button"}]
            expected_content: 预期页面内容（如标题、文本等）
            validate_selector: 验证 selector 是否包含特定字符串
            validate_action: 验证动作类型（click/type/evaluate/screenshot/wait）
            max_score: 满分
        """
        self.url_pattern = url_pattern
        self.required_actions = required_actions or []
        self.expected_content = expected_content
        self.validate_selector = validate_selector
        self.validate_action = validate_action
        self.max_score = max_score

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        # 必须有执行日志
        if not execution_log:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="缺少执行日志，必须使用浏览器完成此题目"
            )

        actions = execution_log.actions

        # ========== 核心检查：必须有浏览器打开操作 ==========
        navigate_actions = [a for a in actions if a.type == ActionType.NAVIGATE]
        if not navigate_actions:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未检测到浏览器打开操作 (navigate)，HTTP 请求不算数！"
            )

        # ========== 检查 URL 模式 ==========
        if self.url_pattern:
            matched_nav = [a for a in navigate_actions
                          if a.url and re.search(self.url_pattern, a.url)]
            if not matched_nav:
                return ValidationResult(
                    correct=False,
                    score=0,
                    max_score=self.max_score,
                    feedback=f"未导航到目标网站（需匹配: {self.url_pattern}）",
                    details={"navigated_urls": [a.url for a in navigate_actions]}
                )

        # ========== 检查必需的操作序列 ==========
        if self.required_actions:
            matched, details = self._match_action_sequence(actions)
            if not matched:
                score = int(self.max_score * 0.5)
                return ValidationResult(
                    correct=False,
                    score=score,
                    max_score=self.max_score,
                    feedback=f"操作序列不完整，仅完成部分步骤",
                    details=details
                )

        # ========== 检查特定动作类型 ==========
        if self.validate_action:
            action_type_map = {
                "click": ActionType.CLICK,
                "type": ActionType.TYPE,
                "evaluate": ActionType.EVALUATE,
                "screenshot": ActionType.SCREENSHOT,
                "wait": ActionType.WAIT
            }
            expected_type = action_type_map.get(self.validate_action)
            if expected_type:
                matched_actions = [a for a in actions if a.type == expected_type]
                if not matched_actions:
                    return ValidationResult(
                        correct=False,
                        score=0,
                        max_score=self.max_score,
                        feedback=f"未检测到 {self.validate_action} 操作"
                    )

        # ========== 检查 selector ==========
        if self.validate_selector:
            matched_sel = False
            for a in actions:
                if a.selector and self.validate_selector.lower() in a.selector.lower():
                    matched_sel = True
                    break
            if not matched_sel:
                return ValidationResult(
                    correct=False,
                    score=0,
                    max_score=self.max_score,
                    feedback=f"未使用正确的 selector（需包含: {self.validate_selector}）"
                )

        # ========== 检查内容提取（答案验证）============
        # 采用关键词包含匹配：答案包含 expected 或 expected 包含答案均可
        if self.expected_content and answer:
            expected_lower = self.expected_content.lower().strip()
            answer_lower = answer.lower().strip()
            if expected_lower not in answer_lower and answer_lower not in expected_lower:
                return ValidationResult(
                    correct=False,
                    score=0,
                    max_score=self.max_score,
                    feedback=f"提取内容错误",
                    details={"expected": self.expected_content, "got": answer}
                )

        # 通过所有检查
        return ValidationResult(
            correct=True,
            score=self.max_score,
            max_score=self.max_score,
            feedback="✓ 浏览器操作正确，验证通过"
        )

    def _match_action_sequence(self, actions: List[Action]) -> Tuple[bool, Dict]:
        """检查操作序列是否完整"""
        details = {"matched": [], "missing": []}
        idx = 0

        for expected in self.required_actions:
            found = False
            while idx < len(actions):
                action = actions[idx]
                if self._match_single_action(action, expected):
                    details["matched"].append({
                        "expected": expected,
                        "found_at": idx,
                        "action_type": action.type.value
                    })
                    found = True
                    idx += 1
                    break
                idx += 1

            if not found:
                details["missing"].append(expected)

        return len(details["missing"]) == 0, details

    def _match_single_action(self, action: Action, expected: Dict[str, Any]) -> bool:
        """检查单个操作是否匹配"""
        if "type" in expected:
            if action.type.value != expected["type"]:
                return False
        if "selector_contains" in expected:
            if not action.selector or expected["selector_contains"].lower() not in action.selector.lower():
                return False
        if "url_contains" in expected:
            if not action.url or expected["url_contains"].lower() not in action.url.lower():
                return False
        if "value_contains" in expected:
            if not action.value or expected["value_contains"].lower() not in action.value.lower():
                return False
        return True

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def get_config(self) -> Dict[str, Any]:
        """返回配置字典，用于序列化和远程重建验证器"""
        config = {"type": "BrowserActionValidator", "max_score": self.max_score}
        if self.url_pattern:
            config["url_pattern"] = self.url_pattern
        if self.expected_content:
            config["expected_content"] = self.expected_content
        if self.validate_selector:
            config["validate_selector"] = self.validate_selector
        if self.validate_action:
            config["validate_action"] = self.validate_action
        if self.required_actions:
            config["required_actions"] = self.required_actions
        return config


# ============================================
# L1 基础能力验证器 - 必须真正打开浏览器
# ============================================

class OpenPageAndExtractTitleValidator(BrowserActionValidator):
    """L1-1: 打开网页并提取标题"""
    def __init__(self, max_score: int = 20):
        super().__init__(
            url_pattern=r"example\.com",
            validate_action="navigate",
            expected_content="Example Domain",
            max_score=max_score
        )


class OpenPageAndScreenshotValidator(BrowserActionValidator):
    """L1-2: 打开网页并截图"""
    def __init__(self, max_score: int = 20):
        super().__init__(
            url_pattern=r"example\.com",
            validate_action="screenshot",
            max_score=max_score
        )


class ClickElementValidator(BrowserActionValidator):
    """L1-3: 点击页面元素"""
    def __init__(self, selector_hint: str, max_score: int = 20):
        super().__init__(
            url_pattern=r"example\.com",
            validate_action="click",
            validate_selector=selector_hint,
            max_score=max_score
        )


class TypeAndSubmitValidator(BrowserActionValidator):
    """L1-4: 填写输入框并提交"""
    def __init__(self, selector_hint: str, value_hint: str):
        super().__init__(
            url_pattern=r"example\.com",
            validate_action="type",
            validate_selector=selector_hint,
            max_score=5
        )


class WaitForContentValidator(BrowserActionValidator):
    """L1-5: 等待页面内容加载"""
    def __init__(self):
        super().__init__(
            url_pattern=r"example\.com",
            validate_action="wait",
            max_score=5
        )


# ============================================
# L3 高级能力验证器
# ============================================

class GitHubIssueDiscussionValidator(BrowserActionValidator):
    """
    GitHub Issue 阅读与评论验证器（v2 — 内容质量导向）

    Agent 必须：
    1. 用浏览器访问指定 GitHub Issue 页面
    2. 阅读 Issue 内容
    3. 发表包含验证码的结构化评论
    4. 将完整评论文本作为 answer 提交

    自动验证维度：
    - 浏览器操作序列（navigate + type + click + github.com URL）
    - answer 包含服务端生成的 challenge_code
    - answer 包含 AgentBrowserExam 标识
    - answer 包含 Issue 相关关键词（证明读过页面）
    - answer 有实质内容（最小长度检查）
    """

    ISSUE_URL = "https://github.com/Yourdaylight/agent_browser_exam/issues/1"

    # Issue 页面中的关键信息，评论必须引用以证明读过
    ISSUE_KEYWORDS = [
        "Agent讨论专区",      # Issue 标题
        "AgentBrowserExam",   # 标识前缀
    ]

    # 评论格式标识
    AGENT_SIGNATURE = "[AgentBrowserExam]"

    def __init__(self, max_score: int = 20,
                 challenge_code: str = None,
                 exam_token: str = None):
        super().__init__(
            url_pattern=r"github\.com/Yourdaylight/agent_browser_exam/issues",
            required_actions=[
                {"type": "navigate", "url_contains": "github.com/Yourdaylight/agent_browser_exam/issues"},
                {"type": "type", "selector_contains": "textarea"},
                {"type": "click", "selector_contains": "comment"},
            ],
            max_score=max_score
        )
        self.issue_url = self.ISSUE_URL
        self.challenge_code = challenge_code
        self.exam_token = exam_token

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        # ---- 第一层：浏览器操作验证（父类） ----
        nav_result = await super().validate(answer, execution_log)
        nav_passed = nav_result.correct

        # ---- 第二层：评论内容验证 ----
        content_checks = {
            "has_answer": False,
            "has_challenge_code": False,
            "has_agent_signature": False,
            "has_issue_keyword": False,
            "min_length": False,
        }

        if not answer or not answer.strip():
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未提交评论内容。请在 GitHub Issue 发表评论后，将完整评论文本作为答案提交。",
            )

        content_checks["has_answer"] = True
        answer_text = answer.strip()

        # 1) 验证码检查
        if self.challenge_code and self.challenge_code in answer_text:
            content_checks["has_challenge_code"] = True
        elif not self.challenge_code:
            # 兼容旧模式：没有 challenge_code 时跳过此检查
            content_checks["has_challenge_code"] = True

        # 2) Agent 标识检查
        if self.AGENT_SIGNATURE in answer_text:
            content_checks["has_agent_signature"] = True

        # 3) Issue 关键词检查（证明读过页面）
        matched_keywords = [
            kw for kw in self.ISSUE_KEYWORDS if kw in answer_text
        ]
        if matched_keywords:
            content_checks["has_issue_keyword"] = True

        # 4) 最小长度检查（实质内容）
        # 去掉标识头后的内容长度
        body_text = answer_text
        for marker in [self.AGENT_SIGNATURE, "🤖", "Verify:", "Token:"]:
            body_text = body_text.replace(marker, "")
        content_length = len(body_text.strip())
        if content_length >= 30:
            content_checks["min_length"] = True

        # ---- 计算得分 ----
        # 总分分配: 浏览器操作 6分 + 验证码 5分 + Agent标识 3分 + Issue关键词 3分 + 内容长度 3分
        score_map = {
            "nav_passed": 6,
            "has_challenge_code": 5,
            "has_agent_signature": 3,
            "has_issue_keyword": 3,
            "min_length": 3,
        }

        score = 0
        if nav_passed:
            score += score_map["nav_passed"]
        if content_checks["has_challenge_code"]:
            score += score_map["has_challenge_code"]
        if content_checks["has_agent_signature"]:
            score += score_map["has_agent_signature"]
        if content_checks["has_issue_keyword"]:
            score += score_map["has_issue_keyword"]
        if content_checks["min_length"]:
            score += score_map["min_length"]

        # 全部通过才算正确
        all_passed = nav_passed and all(content_checks.values())

        # 构建反馈
        feedback_parts = []
        if nav_passed:
            feedback_parts.append("✓ 浏览器操作验证通过")
        else:
            feedback_parts.append("✗ 未检测到有效的浏览器操作序列")

        if content_checks["has_challenge_code"]:
            feedback_parts.append("✓ 验证码正确")
        else:
            feedback_parts.append("✗ 评论中未包含正确的验证码")

        if content_checks["has_agent_signature"]:
            feedback_parts.append("✓ Agent 标识格式正确")
        else:
            feedback_parts.append("✗ 评论中未包含 [AgentBrowserExam] 标识")

        if content_checks["has_issue_keyword"]:
            feedback_parts.append("✓ 引用了 Issue 相关内容")
        else:
            feedback_parts.append("✗ 评论中未引用 Issue 页面内容（如标题「Agent讨论专区」）")

        if content_checks["min_length"]:
            feedback_parts.append("✓ 评论内容充实")
        else:
            feedback_parts.append("✗ 评论内容过短，需要至少 30 个字符的实质内容")

        return ValidationResult(
            correct=all_passed,
            score=score,
            max_score=self.max_score,
            feedback=" | ".join(feedback_parts),
            details={
                "nav_passed": nav_passed,
                "content_checks": content_checks,
                "matched_keywords": matched_keywords,
                "content_length": content_length,
                "issue_url": self.issue_url,
            }
        )

    def get_config(self) -> Dict[str, Any]:
        config = super().get_config()
        config["type"] = "GitHubIssueDiscussionValidator"
        config["issue_url"] = self.issue_url
        if self.challenge_code:
            config["challenge_code"] = self.challenge_code
        if self.exam_token:
            config["exam_token"] = self.exam_token
        return config


# ============================================
# L2 中级能力验证器
# ============================================

class LoopDetectionValidator(BrowserActionValidator):
    """L2-1: 循环检测能力"""

    def __init__(self, max_consecutive_same: int = 3, max_attempts_before_stop: int = 5):
        super().__init__(max_score=15)
        self.max_consecutive_same = max_consecutive_same
        self.max_attempts_before_stop = max_attempts_before_stop

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=15,
                feedback="缺少执行日志"
            )

        actions = execution_log.actions
        events = execution_log.events

        # 检查是否触发了循环检测事件
        loop_detected_events = [e for e in events if e.get("type") == "loop_detected"]

        # 分析连续相同操作
        consecutive_same = 0
        max_consecutive = 0
        for i in range(1, len(actions)):
            if (actions[i].type == actions[i-1].type and
                actions[i].selector == actions[i-1].selector):
                consecutive_same += 1
                max_consecutive = max(max_consecutive, consecutive_same)
            else:
                consecutive_same = 0

        detected = len(loop_detected_events) > 0
        stopped_early = max_consecutive <= self.max_attempts_before_stop

        correct = detected or stopped_early

        if detected:
            score = 15
            feedback = f"循环检测成功，在第 {loop_detected_events[0].get('at_action', '?')} 次操作后检测到"
        elif stopped_early:
            score = 10
            feedback = f"在 {max_consecutive} 次连续操作后停止（部分得分）"
        else:
            score = 0
            feedback = f"未检测到循环，连续相同操作达 {max_consecutive} 次"

        return ValidationResult(
            correct=correct,
            score=score,
            max_score=15,
            feedback=feedback,
            details={
                "loop_detected": detected,
                "max_consecutive_same": max_consecutive,
                "loop_events": [e for e in loop_detected_events]
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (15, 15)


class RefMapCacheValidator(BrowserActionValidator):
    """L2-2: RefMap 缓存命中率验证器"""

    def __init__(self, cache_hit_threshold: float = 0.9):
        super().__init__(max_score=15)
        self.cache_hit_threshold = cache_hit_threshold

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=15,
                feedback="缺少执行日志"
            )

        metadata = execution_log.metadata
        first_visit_tokens = metadata.get("first_visit_tokens", 0)
        second_visit_tokens = metadata.get("second_visit_tokens", 0)

        if first_visit_tokens == 0:
            return ValidationResult(
                correct=False, score=0, max_score=15,
                feedback="缺少 token 消耗数据"
            )

        if second_visit_tokens == 0:
            token_saved_pct = 1.0
        else:
            token_saved_pct = (first_visit_tokens - second_visit_tokens) / first_visit_tokens

        cache_hit_events = [e for e in execution_log.events if e.get("type") == "cache_hit"]
        correct = token_saved_pct >= self.cache_hit_threshold
        score = int(15 * (token_saved_pct / self.cache_hit_threshold)) if token_saved_pct > 0 else 0

        return ValidationResult(
            correct=correct,
            score=min(score, 15),
            max_score=15,
            feedback=f"缓存命中率 {token_saved_pct*100:.1f}%，{'通过' if correct else '未达标'}",
            details={
                "first_visit_tokens": first_visit_tokens,
                "second_visit_tokens": second_visit_tokens,
                "token_saved_pct": token_saved_pct,
                "cache_hit_events": len(cache_hit_events)
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (15, 15)


class ErrorTranslationValidator(BrowserActionValidator):
    """L2-3: 错误翻译友好度验证器"""

    def __init__(self, required_keywords: List[str] = None):
        super().__init__(max_score=10)
        self.required_keywords = required_keywords or ["selector", "建议", "try"]

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=10,
                feedback="缺少执行日志"
            )

        error_events = [e for e in execution_log.events if e.get("type") == "error"]
        error_messages = [e.get("message", "") for e in error_events]

        if not error_messages:
            return ValidationResult(
                correct=False, score=5, max_score=10,
                feedback="没有错误发生，可能没有执行会失败的操作",
                details={"note": "部分得分，操作成功但未测试错误处理"}
            )

        friendly_errors = 0
        for msg in error_messages:
            msg_lower = msg.lower()
            keyword_count = sum(1 for kw in self.required_keywords if kw.lower() in msg_lower)
            if keyword_count >= 2:
                friendly_errors += 1

        ratio = friendly_errors / len(error_messages) if error_messages else 0
        score = int(10 * ratio)
        correct = ratio >= 0.5

        return ValidationResult(
            correct=correct,
            score=score,
            max_score=10,
            feedback=f"友好错误信息比例 {ratio*100:.0f}%",
            details={
                "total_errors": len(error_messages),
                "friendly_errors": friendly_errors,
                "error_messages": error_messages[:3]
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (10, 10)


class OnDemandSnapshotValidator(BrowserActionValidator):
    """L2-4: 按需快照验证器"""

    def __init__(self, max_snapshot_count: int = 3):
        super().__init__(max_score=10)
        self.max_snapshot_count = max_snapshot_count

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=10,
                feedback="缺少执行日志"
            )

        snapshot_actions = [a for a in execution_log.actions if a.type == ActionType.SNAPSHOT]
        metadata = execution_log.metadata
        ttl_hits = metadata.get("ttl_hits", 0)
        jitter_hits = metadata.get("jitter_hits", 0)

        proper_snapshot = (ttl_hits > 0) or (len(snapshot_actions) <= self.max_snapshot_count)

        if ttl_hits > 0:
            score = 10
            feedback = f"TTL 缓存命中 {ttl_hits} 次，按需快照策略有效"
        elif len(snapshot_actions) <= self.max_snapshot_count:
            score = 8
            feedback = f"快照次数 {len(snapshot_actions)} 次，<= {self.max_snapshot_count} 次阈值"
        else:
            score = 0
            feedback = f"快照次数过多 ({len(snapshot_actions)} 次)，未体现按需策略"

        return ValidationResult(
            correct=score >= 8,
            score=score,
            max_score=10,
            feedback=feedback,
            details={
                "snapshot_count": len(snapshot_actions),
                "ttl_hits": ttl_hits,
                "jitter_hits": jitter_hits
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (10, 10)


# ============================================
# L3 高级能力验证器
# ============================================

class ControlHandoverValidator(BrowserActionValidator):
    """
    L3-3: 控制权转交验证器 — 人机协作场景

    考察 Agent 在遇到需要人类操作的页面（如登录页）时，能否：
    1. 访问目标页面（5分）
    2. 对页面截图（5分）
    3. 发出 control_handover action（5分）
    4. 在 answer 中给主人清晰的操作说明（5分）
    5. 完成后发出 control_resume action（5分）
    """

    # 用于检测"请求主人协助"的关键词
    HANDOVER_KEYWORDS = [
        "请", "扫码", "扫描", "二维码", "验证码", "手机号", "登录",
        "输入", "主人", "用户", "人工", "协助", "帮忙", "操作",
        "please", "scan", "qr", "login", "verify", "code", "manual",
        "human", "user", "assist", "help",
    ]

    # 登录页面 URL 关键词
    LOGIN_URL_PATTERNS = [
        r"login", r"signin", r"sign-in", r"passport", r"auth",
        r"sso", r"account", r"taobao\.com",
    ]

    def __init__(self, max_score: int = 25):
        super().__init__(max_score=max_score)

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        score_breakdown = {
            "page_visit": 0,          # 5分：访问目标页面
            "screenshot": 0,          # 5分：对页面截图
            "handover_action": 0,     # 5分：发出 control_handover
            "handover_message": 0,    # 5分：answer 中有清晰说明
            "resume_action": 0,       # 5分：发出 control_resume
        }
        feedback_parts = []

        # 1. 检查是否访问了登录页面（5分）
        if execution_log and execution_log.actions:
            navigate_actions = [a for a in execution_log.actions if a.type == ActionType.NAVIGATE]
            visited_login = False
            for a in navigate_actions:
                if a.url:
                    for pattern in self.LOGIN_URL_PATTERNS:
                        if re.search(pattern, a.url, re.IGNORECASE):
                            visited_login = True
                            break
                if visited_login:
                    break

            if visited_login:
                score_breakdown["page_visit"] = 5
                feedback_parts.append("✓ 成功访问登录页面")
            elif navigate_actions:
                # 有 navigate 但不是登录页，给部分分
                score_breakdown["page_visit"] = 2
                feedback_parts.append("△ 有浏览器导航但未访问到登录页面")
            else:
                feedback_parts.append("✗ 未检测到浏览器导航操作")
        else:
            feedback_parts.append("✗ 缺少执行日志")

        # 2. 检查是否截图（5分）
        if execution_log and execution_log.actions:
            screenshot_actions = [
                a for a in execution_log.actions
                if a.type == ActionType.SCREENSHOT
            ]
            has_screenshots = len(execution_log.screenshots) > 0

            if screenshot_actions or has_screenshots:
                score_breakdown["screenshot"] = 5
                feedback_parts.append("✓ 对页面进行了截图")
            else:
                feedback_parts.append("✗ 未检测到截图操作（应截图展示给主人）")
        else:
            feedback_parts.append("✗ 缺少执行日志")

        # 3. 检查是否有 control_handover action（5分）
        has_handover = False
        has_resume = False
        if execution_log and execution_log.actions:
            for a in execution_log.actions:
                if a.type == ActionType.CONTROL_HANDOVER:
                    has_handover = True
                elif a.type == ActionType.CONTROL_RESUME:
                    has_resume = True

        # 也从 events 中检查（兼容旧格式）
        if execution_log and execution_log.events:
            for e in execution_log.events:
                if e.get("type") == "control_handover":
                    has_handover = True
                elif e.get("type") == "control_resume":
                    has_resume = True

        if has_handover:
            score_breakdown["handover_action"] = 5
            feedback_parts.append("✓ 发出了 control_handover 转交控制权")
        else:
            feedback_parts.append("✗ 未发出 control_handover（应告知系统需要主人操作）")

        # 4. 检查 answer 中是否有对主人的清晰说明（5分）
        if answer and answer.strip():
            answer_lower = answer.lower()
            matched_keywords = [
                kw for kw in self.HANDOVER_KEYWORDS
                if kw.lower() in answer_lower
            ]
            if len(matched_keywords) >= 3:
                score_breakdown["handover_message"] = 5
                feedback_parts.append(f"✓ 对主人的协助说明清晰（匹配关键词: {', '.join(matched_keywords[:5])}）")
            elif len(matched_keywords) >= 1:
                score_breakdown["handover_message"] = 3
                feedback_parts.append("△ 有协助说明但不够清晰")
            else:
                score_breakdown["handover_message"] = 1
                feedback_parts.append("△ answer 有内容但缺少协助请求关键词")
        else:
            feedback_parts.append("✗ 未提交 answer（应写出对主人说的话）")

        # 5. 检查是否恢复了控制权（5分）
        if has_resume:
            score_breakdown["resume_action"] = 5
            feedback_parts.append("✓ 发出了 control_resume 恢复控制权")
        elif has_handover:
            feedback_parts.append("✗ 转交了控制权但未恢复（缺少 control_resume）")
        else:
            feedback_parts.append("✗ 未发出 control_resume")

        # 汇总
        total_score = sum(score_breakdown.values())
        all_passed = total_score >= self.max_score * 0.7  # 70% 以上算通过

        return ValidationResult(
            correct=all_passed,
            score=total_score,
            max_score=self.max_score,
            feedback=" | ".join(feedback_parts),
            details={
                "score_breakdown": score_breakdown,
                "has_handover": has_handover,
                "has_resume": has_resume,
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)


class SearchValidator(BrowserActionValidator):
    """L3-1: 搜索验证器"""

    def __init__(self, search_url: str, expected_keyword: str, max_score: int = 20):
        super().__init__(
            url_pattern=r"baidu\.com",
            max_score=max_score
        )
        self.search_url = search_url
        self.expected_keyword = expected_keyword

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=self.max_score,
                feedback="缺少执行日志"
            )

        navigate_actions = [a for a in execution_log.actions if a.type == ActionType.NAVIGATE]
        type_actions = [a for a in execution_log.actions if a.type == ActionType.TYPE]

        search_inputs = [a for a in type_actions
                        if a.value and self.expected_keyword.lower() in a.value.lower()]

        search_navs = [a for a in navigate_actions
                       if a.url and self.expected_keyword.lower() in a.url.lower()]

        found = len(search_inputs) > 0 or len(search_navs) > 0
        score = self.max_score if found else 0

        return ValidationResult(
            correct=found,
            score=score,
            max_score=self.max_score,
            feedback=f"搜索关键词 '{self.expected_keyword}' {'找到' if found else '未找到'}",
            details={
                "search_inputs": len(search_inputs),
                "search_navs": len(search_navs)
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)


class MultiStepValidator(BrowserActionValidator):
    """L3-2: 多步操作验证器"""

    def __init__(self, expected_steps: List[Dict[str, Any]], max_score: int = 25):
        super().__init__(max_score=max_score)
        self.expected_steps = expected_steps

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log:
            return ValidationResult(
                correct=False, score=0, max_score=self.max_score,
                feedback="缺少执行日志"
            )

        actions = execution_log.actions
        matched_steps = 0
        step_details = []

        for i, expected in enumerate(self.expected_steps):
            found = False
            for j, action in enumerate(actions):
                if self._match_action(action, expected):
                    matched_steps += 1
                    step_details.append({
                        "step": i,
                        "matched": True,
                        "action_type": action.type,
                        "at_index": j
                    })
                    found = True
                    break

            if not found:
                step_details.append({
                    "step": i,
                    "matched": False,
                    "expected": expected
                })

        ratio = matched_steps / len(self.expected_steps) if self.expected_steps else 0
        score = int(self.max_score * ratio)

        return ValidationResult(
            correct=ratio >= 0.8,
            score=score,
            max_score=self.max_score,
            feedback=f"完成 {matched_steps}/{len(self.expected_steps)} 步",
            details={"step_details": step_details, "ratio": ratio}
        )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def _match_action(self, action: Action, expected: Dict[str, Any]) -> bool:
        if action.type != expected.get("type"):
            return False
        if "url_contains" in expected:
            if not action.url or expected["url_contains"].lower() not in action.url.lower():
                return False
        if "selector_contains" in expected:
            if not action.selector or expected["selector_contains"].lower() not in action.selector.lower():
                return False
        if "value_contains" in expected:
            if not action.value or expected["value_contains"].lower() not in action.value.lower():
                return False
        return True


# ============================================
# 浏览器上下文中的 HTTP 请求验证器
# 前提：必须有 navigate（浏览器已打开）+ 答案正确
# ============================================

class BrowserContextHTTPValidator(BaseValidator):
    """
    浏览器上下文 HTTP 验证器
    用于 L1 中少量 HTTP GET/POST 解析能力题目

    验证逻辑：
    1. 必须有 navigate 操作（浏览器已打开）
    2. 服务器端调 API 验证答案正确性
    3. 没有打开浏览器的前提下，HTTP 请求不算数
    """

    def __init__(
        self,
        api_url: str,
        json_path: str = None,
        expected: Any = None,
        method: str = "GET",
        max_score: int = 5,
        dynamic: bool = False,
        post_data: Dict[str, str] = None
    ):
        """
        Args:
            api_url: 需要请求的 API 地址（用于服务器端验证）
            json_path: 从 JSON 响应中提取值的路径，如 "slideshow.title"
            expected: 预期答案（如果为 None 则只验证 answer 非空）
            method: HTTP 方法 (GET / POST)
            max_score: 满分
            dynamic: 是否为动态值（如 IP 地址），动态值只检查非空
            post_data: POST 请求时的表单数据
        """
        self.api_url = api_url
        self.json_path = json_path
        self.expected = expected
        self.method = method.upper()
        self.max_score = max_score
        self.dynamic = dynamic
        self.post_data = post_data

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        # ========== 前提：必须有浏览器打开操作 ==========
        if not execution_log:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="缺少执行日志，必须先打开浏览器再执行 HTTP 请求"
            )

        navigate_actions = [a for a in execution_log.actions if a.type == ActionType.NAVIGATE]
        if not navigate_actions:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未检测到浏览器打开操作 (navigate)，没有打开浏览器的前提下 HTTP 请求不算数！"
            )

        # ========== 验证答案 ==========
        if not answer:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未提交答案"
            )

        # 动态值：只检查非空
        if self.dynamic:
            return ValidationResult(
                correct=bool(answer),
                score=self.max_score if answer else 0,
                max_score=self.max_score,
                feedback="✓ 提交了有效答案" if answer else "未提交答案"
            )

        # 服务器端验证：调 API 获取预期值
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                if self.method == "POST":
                    response = await client.post(
                        self.api_url,
                        data=self.post_data or {},
                        timeout=10.0
                    )
                else:
                    response = await client.get(self.api_url, timeout=10.0)
                response.raise_for_status()
                data = response.json()

            # 提取预期值
            if self.json_path:
                expected_val = self._extract_value(data, self.json_path)
            else:
                expected_val = self.expected

            if expected_val is not None and str(expected_val).lower() == str(answer).lower():
                return ValidationResult(
                    correct=True,
                    score=self.max_score,
                    max_score=self.max_score,
                    feedback=f"✓ HTTP {self.method} 请求解析正确"
                )
            else:
                return ValidationResult(
                    correct=False,
                    score=0,
                    max_score=self.max_score,
                    feedback=f"答案错误",
                    details={"expected": str(expected_val), "provided": answer}
                )
        except Exception as e:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback=f"验证失败: {str(e)}"
            )

    def _extract_value(self, data, path: str) -> Any:
        keys = path.split('.')
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key)
            else:
                return None
        return result

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def get_config(self) -> Dict[str, Any]:
        """返回配置字典，用于序列化和远程重建验证器"""
        config = {"type": "BrowserContextHTTPValidator", "max_score": self.max_score}
        if self.api_url:
            config["api_url"] = self.api_url
        if self.json_path:
            config["json_path"] = self.json_path
        if self.expected:
            config["expected"] = self.expected
        if self.method:
            config["method"] = self.method
        config["dynamic"] = self.dynamic
        if self.post_data:
            config["post_data"] = self.post_data
        return config


# ============================================
# 保留旧验证器用于兼容（内部使用，不对外）
# ============================================

class JSONPathValidator(BaseValidator):
    """JSONPath 验证器 - 仅内部使用，已废弃"""

    def __init__(self, url: str, json_path: str, expected: Any):
        self.url = url
        self.json_path = json_path
        self.expected = expected

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        return ValidationResult(
            correct=False, score=0, max_score=5,
            feedback="此验证器已废弃，必须使用浏览器完成题目"
        )

    def _extract_value(self, data: dict, path: str) -> Any:
        keys = path.split('.')
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key)
            else:
                return None
        return result

    def get_score(self) -> Tuple[int, int]:
        return (0, 5)


class HTTPAPIValidator(BaseValidator):
    """HTTP API 验证器 - 仅内部使用，已废弃"""

    def __init__(self, expected_url: str, expected_pattern: str = None):
        self.expected_url = expected_url
        self.expected_pattern = expected_pattern

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        return ValidationResult(
            correct=False, score=0, max_score=5,
            feedback="HTTP API 验证已废弃，必须使用浏览器完成题目"
        )

    def get_score(self) -> Tuple[int, int]:
        return (0, 5)


class GitHubAPIValidator(BaseValidator):
    """GitHub API 验证器 - 仅内部使用，已废弃"""

    def __init__(self, repo: str = "torvalds/linux", field: str = "stargazers_count"):
        self.repo = repo
        self.field = field
        self.api_url = f"https://api.github.com/repos/{repo}"

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        return ValidationResult(
            correct=False, score=0, max_score=15,
            feedback="GitHub API 验证已废弃，必须使用浏览器访问 GitHub 网页完成题目"
        )

    def get_score(self) -> Tuple[int, int]:
        return (0, 15)


# ============================================
# L2 内置页面验证器
# ============================================

class BuiltInPageValidator(BrowserActionValidator):
    """
    内置页面验证器 — 验证 Agent 是否真正通过浏览器操作内置交互页面

    验证逻辑：
    1. execution_log 中必须有 navigate 到 /exam-page/{page_id}
    2. execution_log 中必须包含 required_operations 中的关键操作（click/type/select）
    3. answer 必须匹配 expected_answer（忽略大小写和首尾空格）
    """

    def __init__(
        self,
        page_id: str,
        expected_answer: str,
        required_operations: List[Dict[str, Any]] = None,
        max_score: int = 15,
    ):
        super().__init__(
            url_pattern=rf"exam-page/{re.escape(page_id)}",
            max_score=max_score,
        )
        self.page_id = page_id
        self.expected_answer = expected_answer
        self.required_operations = required_operations or []

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        if not execution_log or not execution_log.actions:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="缺少执行日志，必须使用浏览器完成此题目"
            )

        actions = execution_log.actions

        # 1. 检查 navigate 到内置页面
        navigate_actions = [a for a in actions if a.type == ActionType.NAVIGATE]
        if not navigate_actions:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未检测到浏览器打开操作 (navigate)"
            )

        page_url_matched = False
        for nav in navigate_actions:
            if nav.url and f"exam-page/{self.page_id}" in nav.url:
                page_url_matched = True
                break

        if not page_url_matched:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback=f"未导航到内置页面 /exam-page/{self.page_id}"
            )

        # 2. 检查必需的操作序列
        if self.required_operations:
            op_checks = []
            for req_op in self.required_operations:
                req_type = req_op.get("type", "")
                selector_hint = req_op.get("selector_contains", "").lower()
                value_hint = req_op.get("value_contains", "").lower()

                found = False
                for a in actions:
                    action_type = a.type.value if hasattr(a.type, 'value') else str(a.type)
                    if action_type == req_type:
                        if selector_hint and a.selector and selector_hint in a.selector.lower():
                            found = True
                            break
                        if value_hint and a.value and value_hint in a.value.lower():
                            found = True
                            break
                        if not selector_hint and not value_hint:
                            found = True
                            break

                op_checks.append({"op": req_op, "found": found})

            matched_count = sum(1 for c in op_checks if c["found"])
            if matched_count < len(self.required_operations):
                missing = [c["op"] for c in op_checks if not c["found"]]
                return ValidationResult(
                    correct=False,
                    score=0,
                    max_score=self.max_score,
                    feedback=f"缺少必要的操作步骤 (完成 {matched_count}/{len(self.required_operations)})",
                    details={"missing_operations": missing}
                )

        # 3. 检查答案
        if not answer or not answer.strip():
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未提交答案"
            )

        if answer.strip().lower() != self.expected_answer.strip().lower():
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="答案不正确",
                details={"expected": self.expected_answer, "got": answer.strip()}
            )

        return ValidationResult(
            correct=True,
            score=self.max_score,
            max_score=self.max_score,
            feedback=f"✓ 正确！成功完成了内置页面 {self.page_id} 的操作任务"
        )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def get_config(self) -> Dict[str, Any]:
        return {
            "type": "BuiltInPageValidator",
            "page_id": self.page_id,
            "max_score": self.max_score,
        }


# ============================================
# GitHub Star 验证器
# ============================================

class GitHubStarValidator(BaseValidator):
    """
    GitHub Star 验证器 — 验证 Agent 是否给指定仓库点了 Star

    验证逻辑：
    1. 开考前（注册时）记录当前 star 数 → 注入 initial_star_count
    2. 提交时重新查询 GitHub API 获取当前 star 数
    3. 当前 star 数 > 开考前 star 数 即得分
    """

    GITHUB_API_URL = "https://api.github.com/repos/Yourdaylight/agent_browser_exam"

    def __init__(self, max_score: int = 5, initial_star_count: int = 0):
        self.max_score = max_score
        self.initial_star_count = initial_star_count

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:
        # 查询当前 star 数
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.GITHUB_API_URL, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                current_stars = data.get("stargazers_count", 0)
        except Exception as e:
            return ValidationResult(
                correct=False, score=0, max_score=self.max_score,
                feedback=f"查询 GitHub API 失败: {e}"
            )

        # 比较 star 数
        if current_stars > self.initial_star_count:
            return ValidationResult(
                correct=True,
                score=self.max_score,
                max_score=self.max_score,
                feedback=f"✓ Star 数增加了！（{self.initial_star_count} → {current_stars}）",
                details={
                    "initial_star_count": self.initial_star_count,
                    "current_star_count": current_stars,
                }
            )
        else:
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback=f"Star 数未增加（开考前: {self.initial_star_count}，当前: {current_stars}）",
                details={
                    "initial_star_count": self.initial_star_count,
                    "current_star_count": current_stars,
                }
            )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def get_config(self) -> Dict[str, Any]:
        return {
            "type": "GitHubStarValidator",
            "max_score": self.max_score,
            "initial_star_count": self.initial_star_count,
        }


# ============================================
# L3 社交平台登录与互动验证器 — 人机协作版
# ============================================

class SocialPlatformLoginValidator(BrowserActionValidator):
    """
    社交平台登录与互动验证器 — 人机协作版

    核心考点：Agent 能否在关键环节将决策权和操作权交给主人

    评判维度（总计 30 分）：
    - 询问主人选择平台（6分）：answer 中体现主人的选择意愿
    - 平台访问（6分）：navigate 到正确平台 URL
    - 登录协作（6分）：遇到登录时截图 + 转交主人，或说明无需登录
    - 搜索执行（6分）：执行了 type + click 操作序列
    - 验证码匹配（6分）：answer 中包含 challenge_code
    """

    # 支持的平台配置
    PLATFORM_CONFIG = {
        "weibo": {
            "url_pattern": r"weibo\.com",
            "keywords": ["微博", "weibo", "搜索"],
            "search_keyword": "AgentBrowserExam",
        },
        "zhihu": {
            "url_pattern": r"zhihu\.com",
            "keywords": ["知乎", "zhihu", "搜索"],
            "search_keyword": "Agent Browser Exam",
        },
        "github": {
            "url_pattern": r"github\.com",
            "keywords": ["github", "GitHub", "search", "repository"],
            "search_keyword": "agent_browser_exam",
        },
    }

    # 直接匹配的短语（明确表示主人参与选择）
    USER_CHOICE_PHRASES = [
        "主人选", "用户选", "主人决定", "用户决定",
        "主人告诉", "用户告诉", "主人指定", "用户指定",
        "主人要求", "用户要求",
        "告诉我选", "让我用", "让我去",
        "asked me", "told me", "user chose", "user selected", "user picked",
    ]
    # 主语词 + 选择词的组合检测
    USER_SUBJECT_WORDS = ["主人", "用户", "人类", "human", "user", "owner"]
    USER_CHOICE_WORDS = ["选", "决定", "指定", "要求", "chose", "selected", "picked", "decided"]

    # 表示"登录协作"的关键词
    LOGIN_COLLAB_KEYWORDS = [
        "请", "扫码", "扫描", "二维码", "验证码", "手机号", "登录",
        "主人", "用户", "协助", "帮忙", "截图", "无需登录", "已登录",
        "不需要登录", "免登录", "未要求登录",
        "please", "scan", "qr", "login", "assist", "screenshot",
        "no login", "already logged", "not required",
    ]

    def __init__(self, max_score: int = 30,
                 challenge_code: str = None,
                 exam_token: str = None):
        super().__init__(max_score=max_score)
        self.challenge_code = challenge_code
        self.exam_token = exam_token

    async def validate(
        self,
        answer: Optional[str],
        execution_log: Optional[ExecutionLog]
    ) -> ValidationResult:

        if not answer or not answer.strip():
            return ValidationResult(
                correct=False,
                score=0,
                max_score=self.max_score,
                feedback="未提交答案。请提交格式: 'platform|页面标题|协作摘要'",
            )

        answer_text = answer.strip()

        # ---- 解析平台选择 ----
        platform = None
        answer_content = answer_text
        collab_summary = ""

        # 尝试从 "platform|content|collab" 格式解析
        if "|" in answer_text:
            parts = answer_text.split("|")
            candidate_platform = parts[0].strip().lower()
            if candidate_platform in self.PLATFORM_CONFIG:
                platform = candidate_platform
                answer_content = parts[1].strip() if len(parts) > 1 else ""
                collab_summary = parts[2].strip() if len(parts) > 2 else ""

        # 如果没有显式指定平台，从 execution_log 推断
        if not platform and execution_log:
            for p_name, p_cfg in self.PLATFORM_CONFIG.items():
                for action in execution_log.actions:
                    if action.type == ActionType.NAVIGATE and action.url:
                        if re.search(p_cfg["url_pattern"], action.url):
                            platform = p_name
                            break
                if platform:
                    break

        if not platform:
            # 从答案内容推断
            answer_lower = answer_text.lower()
            for p_name, p_cfg in self.PLATFORM_CONFIG.items():
                for kw in p_cfg["keywords"]:
                    if kw.lower() in answer_lower:
                        platform = p_name
                        break
                if platform:
                    break

        # ---- 计算各维度得分 ----
        score_breakdown = {
            "user_choice": 0,         # 6分：询问主人选择平台
            "platform_access": 0,     # 6分：平台访问
            "login_collab": 0,        # 6分：登录协作
            "search_operation": 0,    # 6分：搜索执行
            "challenge_code": 0,      # 6分：验证码匹配
        }
        feedback_parts = []

        # 1. 询问主人选择平台（6分）
        # 用短语匹配 + 主语词+选择词组合检测
        full_text_lower = (answer_text + " " + collab_summary).lower()

        # 方式1: 直接短语匹配
        phrase_matched = any(
            phrase.lower() in full_text_lower
            for phrase in self.USER_CHOICE_PHRASES
        )
        # 方式2: 主语词 + 选择词组合（同时出现）
        has_subject = any(w.lower() in full_text_lower for w in self.USER_SUBJECT_WORDS)
        has_choice = any(w.lower() in full_text_lower for w in self.USER_CHOICE_WORDS)
        combo_matched = has_subject and has_choice

        if phrase_matched or combo_matched:
            score_breakdown["user_choice"] = 6
            feedback_parts.append("✓ 体现了主人的平台选择意愿")
        elif platform:
            # 有平台但没体现是主人选的，给部分分
            score_breakdown["user_choice"] = 2
            feedback_parts.append("△ 选择了平台但未体现是主人做的决定（应让主人选）")
        else:
            feedback_parts.append("✗ 未体现平台选择（应询问主人选择哪个平台）")

        # 2. 平台访问（6分）
        if execution_log and execution_log.actions:
            navigate_actions = [a for a in execution_log.actions if a.type == ActionType.NAVIGATE]
            if navigate_actions:
                if platform:
                    config = self.PLATFORM_CONFIG[platform]
                    matched_nav = [a for a in navigate_actions
                                   if a.url and re.search(config["url_pattern"], a.url)]
                    if matched_nav:
                        score_breakdown["platform_access"] = 6
                        feedback_parts.append(f"✓ 成功访问 {platform} 平台")
                    else:
                        score_breakdown["platform_access"] = 2
                        feedback_parts.append(f"△ 有浏览器操作但未导航到 {platform}")
                else:
                    score_breakdown["platform_access"] = 2
                    feedback_parts.append("△ 有浏览器操作但无法确定目标平台")
            else:
                feedback_parts.append("✗ 未检测到浏览器导航操作")
        else:
            feedback_parts.append("✗ 缺少执行日志")

        # 3. 登录协作（6分）
        # 检查：截图 + control_handover，或明确说明无需登录
        has_screenshot = False
        has_handover = False
        if execution_log:
            for a in execution_log.actions:
                if a.type == ActionType.SCREENSHOT:
                    has_screenshot = True
                elif a.type == ActionType.CONTROL_HANDOVER:
                    has_handover = True
            if execution_log.screenshots:
                has_screenshot = True

        # 检查是否提到了登录协作相关内容
        login_collab_matched = [
            kw for kw in self.LOGIN_COLLAB_KEYWORDS
            if kw.lower() in full_text_lower
        ]

        if has_handover and has_screenshot:
            # 完美：截图 + 转交
            score_breakdown["login_collab"] = 6
            feedback_parts.append("✓ 登录协作完整（截图+转交控制权）")
        elif has_handover:
            # 有转交但没截图
            score_breakdown["login_collab"] = 4
            feedback_parts.append("△ 转交了控制权但未截图给主人")
        elif has_screenshot and login_collab_matched:
            # 有截图 + 文字说明（可能没显式 handover）
            score_breakdown["login_collab"] = 4
            feedback_parts.append("△ 截图并说明了登录情况，但缺少 control_handover action")
        elif login_collab_matched and len(login_collab_matched) >= 2:
            # 虽然没截图也没 handover，但在文字上说明了协作情况（如"无需登录"）
            score_breakdown["login_collab"] = 3
            feedback_parts.append("△ 文字中体现了登录处理意识，但缺少截图和 handover 操作")
        elif login_collab_matched:
            score_breakdown["login_collab"] = 1
            feedback_parts.append("△ 简略提及登录相关信息")
        else:
            feedback_parts.append("✗ 未体现登录协作（应截图给主人或说明无需登录）")

        # 4. 搜索操作执行（6分）
        if execution_log and execution_log.actions:
            type_actions = [a for a in execution_log.actions if a.type == ActionType.TYPE]
            click_actions = [a for a in execution_log.actions if a.type == ActionType.CLICK]

            has_search_input = False
            for a in type_actions:
                if a.value:
                    search_kws = ["agentbrowserexam", "agent browser exam", "agent_browser_exam"]
                    if any(kw in a.value.lower() for kw in search_kws):
                        has_search_input = True
                        break

            if has_search_input and click_actions:
                score_breakdown["search_operation"] = 6
                feedback_parts.append("✓ 搜索操作执行完整（输入+点击）")
            elif has_search_input:
                score_breakdown["search_operation"] = 4
                feedback_parts.append("△ 有搜索输入但未检测到点击提交")
            elif type_actions:
                score_breakdown["search_operation"] = 2
                feedback_parts.append("△ 有输入操作但关键词不匹配")
            else:
                feedback_parts.append("✗ 未检测到搜索操作")
        else:
            feedback_parts.append("✗ 缺少搜索操作日志")

        # 5. 验证码匹配（6分）
        if self.challenge_code:
            if self.challenge_code in answer_text:
                score_breakdown["challenge_code"] = 6
                feedback_parts.append("✓ 验证码正确")
            else:
                feedback_parts.append("✗ 答案中未包含正确的验证码")
        else:
            score_breakdown["challenge_code"] = 6
            feedback_parts.append("✓ 验证码检查跳过（兼容模式）")

        # ---- 汇总得分 ----
        total_score = sum(score_breakdown.values())
        all_passed = total_score >= self.max_score * 0.7  # 70% 以上算通过

        return ValidationResult(
            correct=all_passed,
            score=total_score,
            max_score=self.max_score,
            feedback=" | ".join(feedback_parts),
            details={
                "platform": platform,
                "score_breakdown": score_breakdown,
                "answer_content": answer_content[:100] if answer_content else None,
                "collab_summary": collab_summary[:100] if collab_summary else None,
                "challenge_code_provided": bool(self.challenge_code),
            }
        )

    def get_score(self) -> Tuple[int, int]:
        return (self.max_score, self.max_score)

    def get_config(self) -> Dict[str, Any]:
        config = {
            "type": "SocialPlatformLoginValidator",
            "max_score": self.max_score,
        }
        if self.challenge_code:
            config["challenge_code"] = self.challenge_code
        if self.exam_token:
            config["exam_token"] = self.exam_token
        return config
