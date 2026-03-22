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
    GitHubIssueDiscussionValidator,
    LoopDetectionValidator,
    RefMapCacheValidator,
    ErrorTranslationValidator,
    OnDemandSnapshotValidator,
    SearchValidator,
    MultiStepValidator,
    ControlHandoverValidator,
    BuiltInPageValidator,
    GitHubStarValidator,
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
        max_score=20,
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
            max_score=20
        ),
        max_score=20,
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
            max_score=20
        ),
        max_score=20,
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
            max_score=20
        ),
        max_score=20,
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
            max_score=20
        ),
        max_score=20,
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
# L2 中级能力题目 - 浏览器 UI 交互操作
# 5 道内置页面题 + 2 道外部网站题 = 100 分
# ============================================

L2_TASKS = [
    # ---- 内置页面题（5道）----

    Task(
        task_id="L2-1",
        title="服务器数据表格翻页",
        description="在内置服务器监控页面中翻页并提取特定数据",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问考试服务器的内置页面: {base_url}/exam-page/data-table
2. 这是一个服务器监控数据表格，共 50 条记录，每页 10 条，共 5 页
3. 翻到第 3 页（需要点击"下一页"按钮或页码"3"）
4. 在第 3 页中找到 IP 地址为 10.0.2.15 的服务器
5. 提取该服务器的 CPU 使用率（CPU Usage 列）
6. 提交提取到的 CPU 使用率

【注意】目标数据只在第 3 页出现，你必须真正执行翻页操作。""",
        validator=BuiltInPageValidator(
            page_id="data-table",
            expected_answer="78.3%",
            required_operations=[
                {"type": "navigate"},
                {"type": "click"},
            ],
            max_score=15,
        ),
        max_score=15,
        level="L2",
        hints=[
            "先 page.goto() 访问 /exam-page/data-table",
            "需要点击'下一页'按钮翻到第 3 页",
            "目标服务器 IP 是 10.0.2.15",
            "在表格中找到该行后，提取 CPU Usage 列的值"
        ]
    ),

    Task(
        task_id="L2-2",
        title="商品排序与筛选",
        description="在内置电商页面中排序和筛选商品，找到最贵的电子产品",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问考试服务器的内置页面: {base_url}/exam-page/products
2. 这是一个电商商品目录页面，包含 32 件商品
3. 使用排序下拉框，选择 "Price: High to Low" 按价格降序排列
4. 使用分类筛选下拉框，选择 "Electronics"
5. 排在最前面的商品即为最贵的电子产品
6. 提取该商品的名称并提交

【注意】必须同时执行排序和筛选操作，否则结果不正确。""",
        validator=BuiltInPageValidator(
            page_id="products",
            expected_answer="ProMax Ultra Monitor",
            required_operations=[
                {"type": "navigate"},
                {"type": "click"},
            ],
            max_score=15,
        ),
        max_score=15,
        level="L2",
        hints=[
            "先 page.goto() 访问 /exam-page/products",
            "使用 select 元素选择排序方式: 'price-desc'",
            "使用分类筛选选择 'Electronics'",
            "最贵的电子产品是 ProMax Ultra Monitor"
        ]
    ),

    Task(
        task_id="L2-3",
        title="多步表单向导",
        description="在内置订单向导页面中填写表单并获取订单号",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问考试服务器的内置页面: {base_url}/exam-page/wizard
2. 这是一个 3 步订单向导表单
3. 在第 1 步（收货信息）中填写所有必填字段:
   - Full Name: 任意名字
   - Email Address: 有效的邮箱格式
   - Phone Number: 任意电话号码
   - Shipping Address: 任意地址
4. 点击 "Next Step" 按钮进入第 2 步
5. 在第 2 步（支付方式）中选择任意支付方式
6. 点击 "Next Step" 按钮进入第 3 步确认页
7. 在确认页找到订单号（格式为 ORD-XXXXXXXX-XXXX）
8. 提交完整的订单号

【注意】每步都有必填验证，不填写无法进入下一步。""",
        validator=BuiltInPageValidator(
            page_id="wizard",
            expected_answer="ORD-20260322-A7X9",
            required_operations=[
                {"type": "navigate"},
                {"type": "type"},
                {"type": "click"},
            ],
            max_score=15,
        ),
        max_score=15,
        level="L2",
        hints=[
            "先 page.goto() 访问 /exam-page/wizard",
            "使用 page.fill() 或 page.type() 填写必填字段",
            "点击 'Next Step' 按钮进入下一步",
            "最后一步会显示订单号 ORD-20260322-A7X9"
        ]
    ),

    Task(
        task_id="L2-4",
        title="文档标签页切换",
        description="在内置系统文档页面中切换标签页，查找安全漏洞数据",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问考试服务器的内置页面: {base_url}/exam-page/tabs
2. 这是一个系统文档页面，顶部有 5 个标签页: Overview / Performance / Security / Network / Logs
3. 默认显示的是 "Overview" 标签页内容
4. 点击 "Security" 标签页
5. 在 Security 标签页中找到漏洞报告表格
6. 统计 "Critical" 级别的漏洞数量
7. 提交 Critical 级别的漏洞数量

【注意】Critical 漏洞数据只在 Security 标签页中显示。""",
        validator=BuiltInPageValidator(
            page_id="tabs",
            expected_answer="3",
            required_operations=[
                {"type": "navigate"},
                {"type": "click"},
            ],
            max_score=10,
        ),
        max_score=10,
        level="L2",
        hints=[
            "先 page.goto() 访问 /exam-page/tabs",
            "点击 'Security' 标签按钮切换到安全页",
            "在漏洞表格中查找 Severity 列为 Critical 的行",
            "Critical 级别的漏洞有 3 个"
        ]
    ),

    Task(
        task_id="L2-5",
        title="综合监控仪表盘",
        description="在内置运维仪表盘中筛选错误状态并展开详情",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问考试服务器的内置页面: {base_url}/exam-page/dashboard
2. 这是一个运维监控仪表盘，包含多个服务的状态信息
3. 使用状态下拉筛选框，选择 "Error" 过滤出错误状态的服务
4. 在筛选结果中，找到第一条错误服务
5. 点击该行左侧的展开按钮（▶ 按钮）展开详细信息
6. 在展开的详情中找到错误信息（红色文字显示）
7. 提交该错误信息的完整文本

【注意】必须先筛选再展开，直接展开全部数据中的行找不到目标。""",
        validator=BuiltInPageValidator(
            page_id="dashboard",
            expected_answer="Connection timeout to database replica-3",
            required_operations=[
                {"type": "navigate"},
                {"type": "click"},
            ],
            max_score=15,
        ),
        max_score=15,
        level="L2",
        hints=[
            "先 page.goto() 访问 /exam-page/dashboard",
            "使用 select 元素选择 Status = Error",
            "点击第一条错误行左侧的展开按钮",
            "错误信息是: Connection timeout to database replica-3"
        ]
    ),

    # ---- 外部网站题（2道）----

    Task(
        task_id="L2-6",
        title="东方财富页面内容读取",
        description="访问东方财富网站并提取页面标题",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://www.eastmoney.com （东方财富官网）
2. 等待页面加载完成
3. 提取页面的 <title> 标签内容
4. 提交提取到的标题文本

【注意】必须使用浏览器操作，不能直接用 curl 获取！""",
        validator=BrowserActionValidator(
            url_pattern=r"eastmoney\.com",
            validate_action="navigate",
            expected_content="东方财富网",
            max_score=15
        ),
        max_score=15,
        level="L2",
        hints=[
            "Playwright: page.goto('https://www.eastmoney.com') 然后 page.title()",
            "标题包含'东方财富网'关键词即可通过"
        ]
    ),

    Task(
        task_id="L2-7",
        title="Wikipedia 信息提取",
        description="访问 Wikipedia 页面，提取文章标题和首段内容",
        instructions="""请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 https://en.wikipedia.org/wiki/Python_(programming_language)
2. 等待页面加载完成
3. 提取页面的 <title> 标签内容
4. 提交提取到的标题文本

【注意】必须使用浏览器操作，不能直接用 HTTP API 获取！""",
        validator=BrowserActionValidator(
            url_pattern=r"wikipedia\.org/wiki/Python",
            validate_action="navigate",
            expected_content="Python (programming language) - Wikipedia",
            max_score=15
        ),
        max_score=15,
        level="L2",
        hints=[
            "Playwright: page.goto('https://en.wikipedia.org/wiki/Python_(programming_language)')",
            "标题格式为 'Python (programming language) - Wikipedia'"
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
        max_score=20,
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
        max_score=25,
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
        max_score=25,
        level="L3",
        hints=[
            "事件序列应该是: control_handover -> user_action -> control_resume",
            "检查 events 中是否包含完整的切换序列",
            "metadata 中应该有 control_handover_reason 字段"
        ]
    ),

    Task(
        task_id="L3-4",
        title="GitHub Issue 阅读与评论",
        description="用浏览器访问 GitHub Issue，阅读内容并发表包含验证码的结构化评论",
        instructions="""【⚠️ 主人在旁提示】本题需要在 GitHub 上登录并发表评论，涉及账号身份校验。请确认主人在旁边，必要时由主人协助完成登录操作。

请使用浏览器自动化工具完成以下操作：

1. 打开浏览器，访问 GitHub Issue: https://github.com/Yourdaylight/agent_browser_exam/issues/1
2. 仔细阅读 Issue 的标题和描述内容
3. 在 Issue 的评论框中发表一条评论，评论必须严格遵循以下格式：

---
🤖 [AgentBrowserExam] {你的Agent名称} ({你使用的模型名称}) | Token: {你的准考证号} | Verify: {验证码}

{你对这个 Issue 的看法或对 Agent Browser Exam 的建议，至少 30 个字符}
---

4. 将你在 GitHub 上发表的完整评论内容作为答案提交

【重要说明】
- 必须使用浏览器操作访问 Issue 页面（不能用 GitHub API）
- 评论中的「验证码」是服务端为你生成的唯一标识，见本题 instructions 开头的 challenge 字段
- 评论必须包含验证码，否则无法通过自动验证
- 评论的「看法/建议」部分需要有实质内容（至少 30 个字符），不能是空话或纯表情
- 服务端会自动验证评论中是否包含正确的验证码和 Issue 相关关键词""",
        validator=GitHubIssueDiscussionValidator(),
        max_score=25,
        level="L3",
        hints=[
            "先 page.goto('https://github.com/Yourdaylight/agent_browser_exam/issues/1')",
            "注意阅读 Issue 标题「Agent讨论专区」和描述",
            "评论开头必须包含 🤖 [AgentBrowserExam] 标识和验证码",
            "验证码在题目 instructions 中有标注，格式为 Verify: xxxxxx",
            "最终将你在 GitHub 发表的完整评论文本作为答案提交"
        ]
    ),

    Task(
        task_id="L3-5",
        title="GitHub 仓库 Star",
        description="给 Agent Browser Exam 的 GitHub 仓库点一个 Star",
        instructions="""请使用浏览器完成以下操作：

1. 打开浏览器，访问 GitHub 仓库: https://github.com/Yourdaylight/agent_browser_exam
2. 如果未登录，请主人协助完成 GitHub 登录
3. 点击页面上的 ⭐ Star 按钮，给该仓库点一个 Star
4. 确认 Star 按钮变为高亮状态（已 Star）

【注意】
- 必须使用浏览器操作访问 GitHub 仓库页面
- 系统会在开考前记录当前 Star 数，考完后自动验证是否增加
- 如果主人已 Star 过该仓库，请使用另一个 GitHub 账号完成""",
        validator=GitHubStarValidator(),
        max_score=5,
        level="L3",
        hints=[
            "先 page.goto('https://github.com/Yourdaylight/agent_browser_exam')",
            "找到 Star 按钮并点击",
            "Star 按钮通常在页面右上角仓库标题旁边",
            "如果按钮已高亮（Unstar），说明已经 Star 过了"
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
