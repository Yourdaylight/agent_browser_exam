"""
考试题目基类和配置 - 真正的浏览器自动化能力测评
"""
from typing import List, Dict, Any
from server.validators import (
    BrowserActionValidator,
    BrowserContextHTTPValidator,
    OpenPageAndExtractTitleValidator,
    OpenPageAndScreenshotValidator,
    ClickElementValidator,
    TypeAndSubmitValidator,
    WaitForContentValidator,
    LoopDetectionValidator,
    RefMapCacheValidator,
    ErrorTranslationValidator,
    OnDemandSnapshotValidator,
    SearchValidator,
    MultiStepValidator,
    ControlHandoverValidator
)


class Task:
    """题目配置"""

    def __init__(
        self,
        task_id: str,
        title: str,
        description: str,
        instructions: str,
        validator,
        max_score: int = 5,
        level: str = "L1",
        hints: List[str] = None
    ):
        self.id = task_id
        self.title = title
        self.description = description
        self.instructions = instructions
        self.validator = validator
        self.max_score = max_score
        self.level = level
        self.hints = hints or []

    def to_dict(self) -> Dict[str, Any]:
        validator_config = None
        if hasattr(self.validator, 'get_config'):
            validator_config = self.validator.get_config()
        elif hasattr(self.validator, 'url_pattern'):
            validator_config = {
                "type": "BrowserActionValidator",
                "url_pattern": getattr(self.validator, 'url_pattern', None),
                "validate_action": getattr(self.validator, 'validate_action', None),
                "validate_selector": getattr(self.validator, 'validate_selector', None),
                "expected_content": getattr(self.validator, 'expected_content', None)
            }

        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "instructions": self.instructions,
            "max_score": self.max_score,
            "level": self.level,
            "hints": self.hints,
            "validator_config": validator_config
        }


# ============================================
# L1 基础能力题目
# 浏览器操作为主(3道) + 少量 HTTP 请求解析(2道)
# HTTP 请求必须有 navigate 前提（浏览器已打开）
# ============================================

L1_TASKS = [
    # ---- 浏览器操作题（3道） ----

    Task(
        task_id="L1-1",
        title="打开网页并提取标题",
        description="使用浏览器打开网页，提取页面 <title> 标签内容",
        instructions="""请使用浏览器自动化工具（如 Playwright/Puppeteer）完成以下操作：

1. 打开浏览器，访问 https://example.com
2. 提取页面的 <title> 标签内容
3. 提交提取到的标题文本""",
        validator=OpenPageAndExtractTitleValidator(),
        max_score=5,
        level="L1",
        hints=[
            "Playwright: page.goto('https://example.com') 然后 page.title()",
            "Puppeteer: page.goto(url) 然后 page.title()",
            "答案应该是 'Example Domain'"
        ]
    ),

    Task(
        task_id="L1-2",
        title="提取页面 DOM 文本",
        description="打开网页后提取指定 DOM 元素的文本内容",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://example.com
2. 找到页面中 <h1> 标签的文本内容
3. 提交提取到的文本

注意：需要使用 DOM API 如 querySelector 或 textContent，不能直接 HTTP 请求。""",
        validator=BrowserActionValidator(
            url_pattern=r"example\.com",
            expected_content="Example Domain",
            validate_action="navigate",
            max_score=5
        ),
        max_score=5,
        level="L1",
        hints=[
            "Playwright: page.locator('h1').textContent()",
            "Puppeteer: page.$eval('h1', el => el.textContent)",
            "页面 h1 的文本内容是 'Example Domain'"
        ]
    ),

    Task(
        task_id="L1-3",
        title="点击页面链接并截图",
        description="打开网页，点击链接，截图记录新页面",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://example.com
2. 点击页面中的链接（<a> 标签）
3. 对新页面进行截图

提交截图操作完成即可得分。""",
        validator=BrowserActionValidator(
            url_pattern=r"example\.com",
            validate_action="click",
            validate_selector="a",
            max_score=5
        ),
        max_score=5,
        level="L1",
        hints=[
            "先 page.goto() 打开 example.com",
            "page.click('a') 点击链接",
            "page.screenshot() 截图"
        ]
    ),

    # ---- HTTP 请求解析题（2道） ----
    # 注意：这些题目要求浏览器已打开（navigate），HTTP 请求在浏览器上下文中完成

    Task(
        task_id="L1-4",
        title="HTTP GET 请求解析 JSON",
        description="在浏览器打开的前提下，发起 HTTP GET 请求获取 JSON 数据并提取字段",
        instructions="""请完成以下操作：

1. 先打开浏览器，访问 https://httpbin.org （必须这一步！）
2. 发起 HTTP GET 请求到 https://httpbin.org/json
3. 从返回的 JSON 中提取 slideshow 对象的 title 值
4. 提交提取到的值

【注意】必须先打开浏览器！没有打开浏览器的前提下 HTTP 请求不算数。
可以通过浏览器内的 fetch API、curl 命令、或浏览器自动化工具的 request API 来发起请求。""",
        validator=BrowserContextHTTPValidator(
            api_url="https://httpbin.org/json",
            json_path="slideshow.title",
            expected="Slide 1",
            max_score=5
        ),
        max_score=5,
        level="L1",
        hints=[
            "验证器要求：execution_log 中必须有 navigate 操作",
            "浏览器内 fetch: page.evaluate(() => fetch('https://httpbin.org/json').then(r => r.json()))",
            "Playwright API: page.request.get('https://httpbin.org/json')",
            "答案: slideshow.title = 'Slide 1'"
        ]
    ),

    Task(
        task_id="L1-5",
        title="HTTP POST 请求提交表单",
        description="在浏览器打开的前提下，发起 HTTP POST 请求提交表单数据并验证响应",
        instructions="""请完成以下操作：

1. 先打开浏览器，访问 https://httpbin.org （必须这一步！）
2. 发起 HTTP POST 请求到 https://httpbin.org/post
3. 表单数据: name=TestUser, age=25
4. 从返回的 JSON 中提取 form.name 的值
5. 提交提取到的值

【注意】必须先打开浏览器！没有打开浏览器的前提下 HTTP 请求不算数。""",
        validator=BrowserContextHTTPValidator(
            api_url="https://httpbin.org/post",
            json_path="form.name",
            expected="TestUser",
            max_score=5
        ),
        max_score=5,
        level="L1",
        hints=[
            "验证器要求：execution_log 中必须有 navigate 操作",
            "curl: curl -X POST -d 'name=TestUser&age=25' https://httpbin.org/post",
            "Playwright API: page.request.post(url, data={...})",
            "答案: form.name = 'TestUser'"
        ]
    ),
]


# ============================================
# L2 中级能力题目 - 浏览器交互与高级操作
# ============================================

L2_TASKS = [
    Task(
        task_id="L2-1",
        title="循环检测能力",
        description="验证 Agent 能否检测到重复操作并停止",
        instructions="""请模拟以下场景：

1. 打开浏览器，访问任意页面
2. 编写脚本连续点击"下一页"按钮 10 次
3. 如果 Agent 有循环检测能力，应该在检测到重复操作后停止
4. 上传执行日志（包含 actions 和 events）

【关键】需要在 execution_log.events 中记录 loop_detected 事件。""",
        validator=LoopDetectionValidator(
            max_consecutive_same=3,
            max_attempts_before_stop=5
        ),
        max_score=15,
        level="L2",
        hints=[
            "循环检测应识别连续相同类型的操作",
            "检查 execution_log.events 中是否有 loop_detected 事件",
            "metadata 中应该有循环检测配置"
        ]
    ),

    Task(
        task_id="L2-2",
        title="页面缓存命中率",
        description="验证同一页面重复访问时的缓存能力",
        instructions="""请执行以下操作：

1. 首次访问 https://example.com，记录 token 消耗
2. 再次访问同一页面，验证是否使用缓存
3. 上传两次访问的 token 消耗数据到 metadata

预期：第二次访问 token < 第一次的 10%""",
        validator=RefMapCacheValidator(
            cache_hit_threshold=0.9
        ),
        max_score=15,
        level="L2",
        hints=[
            "需要在 metadata 中记录 first_visit_tokens 和 second_visit_tokens",
            "检查第二次访问是否有 cache_hit 事件"
        ]
    ),

    Task(
        task_id="L2-3",
        title="错误信息友好度",
        description="验证 Agent 的错误信息是否 AI 友好",
        instructions="""请执行一个会失败的操作（如使用错误的 selector），验证返回的错误信息是否包含：
1. 错误类型的描述
2. 可能的解决方案或建议

上传错误日志进行分析。""",
        validator=ErrorTranslationValidator(
            required_keywords=["selector", "建议", "try"]
        ),
        max_score=10,
        level="L2",
        hints=[
            "错误信息应该包含 'selector' 关键词",
            "应该给出修复建议或下一步操作",
            "检查 events 中 type=error 的事件"
        ]
    ),

    Task(
        task_id="L2-4",
        title="按需快照策略",
        description="验证快照是否按需触发而非每次操作都触发",
        instructions="""请执行以下操作：

1. 访问同一页面 3 次，每次间隔 2 秒
2. 验证快照是否在 TTL 有效期内被缓存复用
3. 上传执行日志到 metadata

预期：TTL 命中次数 > 0 或快照次数 <= 3""",
        validator=OnDemandSnapshotValidator(
            max_snapshot_count=3
        ),
        max_score=10,
        level="L2",
        hints=[
            "按需快照应该有 TTL 机制",
            "metadata.ttl_hits 应该 > 0",
            "快照次数应该 <= max_snapshot_count"
        ]
    ),
]


# ============================================
# L3 高级能力题目 - 复杂浏览器自动化场景
# ============================================

L3_TASKS = [
    Task(
        task_id="L3-1",
        title="百度搜索操作",
        description="在百度搜索框输入关键词并执行搜索",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://www.baidu.com
2. 在搜索框中输入关键词 "github"
3. 点击搜索按钮或按回车执行搜索
4. 验证搜索结果页面已加载

【注意】必须使用浏览器操作！""",
        validator=SearchValidator(
            search_url="https://www.baidu.com",
            expected_keyword="github"
        ),
        max_score=15,
        level="L3",
        hints=[
            "搜索框的 selector 通常是 #kw 或 input[name='wd']",
            "可以使用 page.type('#kw', 'github') 或 page.fill()",
            "点击搜索按钮 #su 或按 Enter 键"
        ]
    ),

    Task(
        task_id="L3-2",
        title="多步操作组合",
        description="验证复杂多步骤操作的正确性",
        instructions="""请执行以下操作序列：

1. 访问 https://example.com
2. 点击页面中的链接或按钮
3. 验证页面内容变化

上传执行日志，验证操作序列是否符合预期。""",
        validator=MultiStepValidator(
            expected_steps=[
                {"type": "navigate", "url_contains": "example"},
                {"type": "click"}
            ]
        ),
        max_score=15,
        level="L3",
        hints=[
            "预期步骤：先导航到 example.com，再执行点击操作",
            "检查 actions 序列是否包含所有预期步骤",
            "至少 80% 步骤匹配才能通过"
        ]
    ),

    Task(
        task_id="L3-3",
        title="控制权切换",
        description="验证 Agent ↔ User 控制权切换机制",
        instructions="""请模拟以下场景：
1. Agent 检测到需要人类操作的页面（如验证码）
2. 触发 control_handover 事件
3. 模拟用户操作（点击）
4. 触发 control_resume 事件恢复 Agent 控制

上传完整的事件序列日志。""",
        validator=ControlHandoverValidator(),
        max_score=15,
        level="L3",
        hints=[
            "事件序列应该是: control_handover -> user_action -> control_resume",
            "检查 events 中是否包含完整的切换序列",
            "metadata 中应该有 control_handover_reason 字段"
        ]
    ),

    Task(
        task_id="L3-4",
        title="GitHub 页面操作",
        description="在 GitHub 网页上执行操作（不用 API）",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://github.com
2. 提取页面的标题或任意文本内容
3. 验证 GitHub 页面正常加载

【注意】必须访问 GitHub 网页，不用 GitHub API！""",
        validator=BrowserActionValidator(
            url_pattern=r"github\.com",
            validate_action="navigate",
            max_score=15
        ),
        max_score=15,
        level="L3",
        hints=[
            "验证器会检查是否有 navigate 到 github.com",
            "可以使用 page.content() 或 page.inner_text() 提取内容"
        ]
    ),
]


# ============================================
# 题目获取接口
# ============================================

def get_tasks_for_level(level: str) -> List[Dict[str, Any]]:
    """根据考试级别获取题目列表"""

    task_map = {
        "v1": L1_TASKS,
        "v2": L2_TASKS,
        "v3": L3_TASKS
    }

    tasks = task_map.get(level, [])
    return [t.to_dict() for t in tasks]


def get_all_tasks() -> Dict[str, List[Dict[str, Any]]]:
    """获取所有题目"""
    return {
        "v1": [t.to_dict() for t in L1_TASKS],
        "v2": [t.to_dict() for t in L2_TASKS],
        "v3": [t.to_dict() for t in L3_TASKS]
    }
