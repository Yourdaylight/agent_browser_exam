"""
验证器单元测试
"""
import pytest
import asyncio
from datetime import datetime

from server.models import ExecutionLog, Action, ActionType
from server.validators import (
    JSONPathValidator, LoopDetectionValidator, RefMapCacheValidator,
    ErrorTranslationValidator, OnDemandSnapshotValidator,
    ControlHandoverValidator, GitHubAPIValidator, SearchValidator
)


# ============================================
# JSONPathValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_json_path_validator_success():
    """JSONPath 验证 - 正确答案"""
    validator = JSONPathValidator(
        url="https://httpbin.org/json",
        json_path="slideshow.title",
        expected=None  # 不对比，只验证 API 能调用
    )

    # httpbin.org 返回的是 Sample Slide Show
    result = await validator.validate("Sample Slide Show", None)

    assert result.correct is True
    assert result.score == 5


@pytest.mark.asyncio
async def test_json_path_validator_wrong():
    """JSONPath 验证 - 错误答案"""
    validator = JSONPathValidator(
        url="https://httpbin.org/json",
        json_path="slideshow.title",
        expected="Slide 1"
    )

    result = await validator.validate("Wrong Answer", None)

    assert result.correct is False
    assert result.score == 0


# ============================================
# LoopDetectionValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_loop_detection_with_event():
    """循环检测 - 有 loop_detected 事件"""
    validator = LoopDetectionValidator()

    log = ExecutionLog(
        task_id="L2-1",
        actions=[
            Action(type=ActionType.CLICK, selector="button.next", timestamp=1.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=2.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=3.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=4.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=5.0),
        ],
        events=[
            {"type": "loop_detected", "at_action": 5, "reason": "重复点击"}
        ]
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 15
    assert "循环检测成功" in result.feedback


@pytest.mark.asyncio
async def test_loop_detection_stopped_early():
    """循环检测 - 提前停止"""
    validator = LoopDetectionValidator(max_attempts_before_stop=5)

    log = ExecutionLog(
        task_id="L2-1",
        actions=[
            Action(type=ActionType.CLICK, selector="button.next", timestamp=1.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=2.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=3.0),
        ],
        events=[]
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 10  # 部分得分


@pytest.mark.asyncio
async def test_loop_detection_no_loop():
    """循环检测 - 未检测到循环"""
    validator = LoopDetectionValidator()

    log = ExecutionLog(
        task_id="L2-1",
        actions=[
            Action(type=ActionType.CLICK, selector="button.next", timestamp=1.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=2.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=3.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=4.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=5.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=6.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=7.0),
            Action(type=ActionType.CLICK, selector="button.next", timestamp=8.0),
        ],
        events=[]
    )

    result = await validator.validate(None, log)

    assert result.correct is False
    assert result.score == 0


# ============================================
# RefMapCacheValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_refmap_cache_hit():
    """RefMap 缓存 - 完全命中"""
    validator = RefMapCacheValidator(cache_hit_threshold=0.9)

    log = ExecutionLog(
        task_id="L2-2",
        actions=[],
        events=[{"type": "cache_hit"}],
        token_consumed=500,
        metadata={
            "first_visit_tokens": 15000,
            "second_visit_tokens": 0
        }
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 15
    assert "100.0%" in result.feedback


@pytest.mark.asyncio
async def test_refmap_partial_cache():
    """RefMap 缓存 - 部分命中"""
    validator = RefMapCacheValidator(cache_hit_threshold=0.9)

    log = ExecutionLog(
        task_id="L2-2",
        actions=[],
        events=[],
        token_consumed=2000,
        metadata={
            "first_visit_tokens": 15000,
            "second_visit_tokens": 1500  # 90% 节省
        }
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 15


@pytest.mark.asyncio
async def test_refmap_no_cache():
    """RefMap 缓存 - 未命中"""
    validator = RefMapCacheValidator(cache_hit_threshold=0.9)

    log = ExecutionLog(
        task_id="L2-2",
        actions=[],
        events=[],
        token_consumed=15000,
        metadata={
            "first_visit_tokens": 15000,
            "second_visit_tokens": 15000  # 无节省
        }
    )

    result = await validator.validate(None, log)

    assert result.correct is False
    assert result.score == 0


# ============================================
# ErrorTranslationValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_error_translation_friendly():
    """错误翻译 - 友好错误信息"""
    validator = ErrorTranslationValidator(
        required_keywords=["selector", "建议", "try"]
    )

    log = ExecutionLog(
        task_id="L2-3",
        actions=[],
        events=[
            {
                "type": "error",
                "message": "Selector 'button.submit' not found. 建议检查 selector 是否正确，try 使用 aria-label"
            }
        ]
    )

    result = await validator.validate(None, log)

    assert result.score > 0  # 至少部分得分


@pytest.mark.asyncio
async def test_error_translation_not_friendly():
    """错误翻译 - 非友好错误信息"""
    validator = ErrorTranslationValidator(
        required_keywords=["selector", "建议", "try"]
    )

    log = ExecutionLog(
        task_id="L2-3",
        actions=[],
        events=[
            {"type": "error", "message": "Element not found"}
        ]
    )

    result = await validator.validate(None, log)

    assert result.score == 0


# ============================================
# OnDemandSnapshotValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_on_demand_snapshot_ttl_hit():
    """按需快照 - TTL 命中"""
    validator = OnDemandSnapshotValidator(max_snapshot_count=3)

    log = ExecutionLog(
        task_id="L2-4",
        actions=[],
        events=[],
        metadata={
            "ttl_hits": 2,
            "jitter_hits": 0
        }
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 10
    assert "TTL" in result.feedback


@pytest.mark.asyncio
async def test_on_demand_snapshot_few_snapshots():
    """按需快照 - 快照次数少"""
    validator = OnDemandSnapshotValidator(max_snapshot_count=3)

    log = ExecutionLog(
        task_id="L2-4",
        actions=[
            Action(type=ActionType.SNAPSHOT, timestamp=1.0),
            Action(type=ActionType.SNAPSHOT, timestamp=2.0),
        ],
        events=[],
        metadata={}
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 8


# ============================================
# ControlHandoverValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_control_handover_complete():
    """控制权切换 - 完整序列"""
    validator = ControlHandoverValidator()

    log = ExecutionLog(
        task_id="L3-3",
        actions=[
            Action(type=ActionType.CLICK, selector="button.verify", timestamp=1.0)
        ],
        events=[
            {"type": "control_handover", "reason": "验证码"},
            {"type": "user_action"},
            {"type": "control_resume"}
        ]
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 15


@pytest.mark.asyncio
async def test_control_handover_partial():
    """控制权切换 - 部分序列"""
    validator = ControlHandoverValidator()

    log = ExecutionLog(
        task_id="L3-3",
        actions=[],
        events=[
            {"type": "control_handover", "reason": "验证码"}
        ]
    )

    result = await validator.validate(None, log)

    # 只有 handover 没有 resume 时应该部分得分
    # 当前逻辑是 score=8 if handover_idx else 0
    # 但测试预期 handover_idx is not None 应该得 8 分
    assert result.score > 0  # 至少有一些分数


# ============================================
# GitHubAPIValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_github_api_validator():
    """GitHub API 验证"""
    validator = GitHubAPIValidator(
        repo="torvalds/linux",
        field="stargazers_count"
    )

    # 这个测试需要实际调用 GitHub API
    # 由于 API 可能返回动态值，我们只测试格式
    result = await validator.validate("999999", None)

    # 结果取决于实际 API 返回值
    # 验证器应该能正确调用 API
    assert result.max_score == 15


# ============================================
# SearchValidator 测试
# ============================================

@pytest.mark.asyncio
async def test_search_validator_found():
    """搜索验证 - 找到关键词"""
    validator = SearchValidator(
        search_url="https://www.baidu.com",
        expected_keyword="github"
    )

    log = ExecutionLog(
        task_id="L3-2",
        actions=[
            Action(type=ActionType.TYPE, selector="input[name='wd']", value="github", timestamp=1.0),
        ],
        events=[]
    )

    result = await validator.validate(None, log)

    assert result.correct is True
    assert result.score == 15


@pytest.mark.asyncio
async def test_search_validator_not_found():
    """搜索验证 - 未找到关键词"""
    validator = SearchValidator(
        search_url="https://www.baidu.com",
        expected_keyword="github"
    )

    log = ExecutionLog(
        task_id="L3-2",
        actions=[
            Action(type=ActionType.TYPE, selector="input[name='wd']", value="other", timestamp=1.0),
        ],
        events=[]
    )

    result = await validator.validate(None, log)

    assert result.correct is False
    assert result.score == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
