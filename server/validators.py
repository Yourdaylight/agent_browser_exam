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
        if self.expected_content and answer:
            if self.expected_content.lower() != answer.lower():
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
    """L3-3: 控制权切换验证器"""

    def __init__(self, max_score: int = 25):
        super().__init__(max_score=max_score)

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

        events = execution_log.events
        actions = execution_log.actions

        handover_idx = None
        resume_idx = None

        for i, e in enumerate(events):
            if e.get("type") == "control_handover":
                handover_idx = i
            elif e.get("type") == "control_resume":
                resume_idx = i

        has_user_action = any(
            e.get("type") == "user_action" or a.type == ActionType.CLICK
            for a in actions
            for e in events
        )

        correct = (handover_idx is not None and resume_idx is not None)
        partial_score = int(self.max_score * 0.5)
        score = self.max_score if correct else (partial_score if handover_idx is not None else 0)

        if correct:
            feedback = "控制权切换序列完整：handover -> resume"
        elif handover_idx is not None:
            feedback = "触发了控制权切换，但未恢复"
        else:
            feedback = "未检测到控制权切换事件"

        return ValidationResult(
            correct=correct,
            score=score,
            max_score=self.max_score,
            feedback=feedback,
            details={
                "handover_detected": handover_idx is not None,
                "resume_detected": resume_idx is not None,
                "event_count": len(events)
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
        dynamic: bool = False
    ):
        """
        Args:
            api_url: 需要请求的 API 地址（用于服务器端验证）
            json_path: 从 JSON 响应中提取值的路径，如 "slideshow.title"
            expected: 预期答案（如果为 None 则只验证 answer 非空）
            method: HTTP 方法
            max_score: 满分
            dynamic: 是否为动态值（如 IP 地址），动态值只检查非空
        """
        self.api_url = api_url
        self.json_path = json_path
        self.expected = expected
        self.method = method
        self.max_score = max_score
        self.dynamic = dynamic

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
                response = await client.get(self.api_url, timeout=10.0)
                response.raise_for_status()
                data = response.json()

            # 提取预期值
            if self.json_path:
                expected_val = self._extract_value(data, self.json_path)
            else:
                expected_val = self.expected

            if str(expected_val).lower() == str(answer).lower():
                return ValidationResult(
                    correct=True,
                    score=self.max_score,
                    max_score=self.max_score,
                    feedback=f"✓ HTTP 请求解析正确"
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
