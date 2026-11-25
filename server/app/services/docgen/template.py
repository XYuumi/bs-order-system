"""需求书模板引擎：从题目 + 技术栈偏好生成九章结构的完整 JSON 文稿。

该 JSON 是需求书的唯一数据源：AI 生成、在线编辑、docx 渲染都围绕它进行，
缺失部分由模板兜底（normalize_doc），保证任何情况下都能导出格式一致的 Word。
"""
from __future__ import annotations

import re

CHAPTER_ORDER = ["goal", "scope", "roles", "scenarios", "functions", "rules", "data_scope", "tech", "database"]


def build_raw_doc(title: str, raw_text: str) -> dict:
    """原文直用文档：mode=raw，全文原样保存，不做任何结构化改写。

    生成入口在「直接采用上传需求书」时使用；预览/编辑/导出/对比都按原文渲染。
    """
    return {
        "title": f"{title}需求书",
        "mode": "raw",
        "raw_text": str(raw_text or ""),
    }


def tech_label_from_doc(document: dict) -> str | None:
    """从技术选型表提取简短技术栈标签（用于生成后回写 order.tech_stack），≤100 字符。"""
    try:
        rows = document["chapters"]["tech"]["stack_table"]
    except (KeyError, TypeError):
        return None
    picks: list[str] = []
    for row in rows:
        if not (isinstance(row, list) and len(row) >= 2):
            continue
        layer = str(row[0]).strip()
        # 覆盖各预设的层级命名：后端/前端/数据库，以及 Python 数据分析类的
        # 数据采集/开发语言/数据处理/可视化/Web 展示 等，避免漏识别导致标签只剩数据库
        if any(k in layer for k in ("后端", "前端", "数据库", "采集", "框架", "语言", "数据处理", "可视化", "展示", "容器", "服务")):
            tech = str(row[1]).strip()
            if tech and tech not in picks:
                picks.append(tech)
        if len(picks) >= 3:
            break
    return " + ".join(picks)[:100] or None

CHAPTER_HEADINGS = {
    "goal": "一、项目目标",
    "scope": "二、建设范围",
    "roles": "三、角色定义",
    "scenarios": "四、核心业务场景",
    "functions": "五、功能需求",
    "rules": "六、业务规则",
    "data_scope": "七、数据范围",
    "tech": "八、技术架构",
    "database": "九、数据库设计（MySQL 8.0）",
}


def short_name(title: str) -> str:
    """从完整题目中提取系统简称，如「基于SpringBoot的养老院管理系统的设计与实现」→「养老院管理系统」。"""
    t = (title or "").strip()
    t = re.sub(r"^(基于|采用|使用)[^，,。;；]{1,20}的", "", t)
    for suf in ("的设计与实现", "设计与实现", "项目需求书", "需求书", "系统的设计", "系统设计"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t or (title or "").strip()


# ---------------------------------------------------------------------------
# 技术栈预设：与既有工程三套主流方案对齐
# ---------------------------------------------------------------------------

def _stack_preset(tech_stack: str | None, title: str = "") -> dict:
    """技术栈预设路由：关键词同时参考 偏好+题目。

    历史 bug：偏好留空时一律落回 SpringBoot 默认，导致「基于Python的…」题目
    生成 SpringBoot 文档。现在题目指明 Python/JSP 等同样生效；Java 系关键词
    优先级最高，防止「基于SpringBoot的…可视化系统」被"可视化"误判为 Python 系。
    """
    ts = f"{tech_stack or ''} {title or ''}".lower()
    is_jsp = any(k in ts for k in ("jsp", "servlet", "javaweb", "java web"))
    is_java = is_jsp or any(k in ts for k in ("spring", "maven", "tomcat")) or bool(re.search(r"\bjava\b", ts))
    is_py = any(k in ts for k in ("python", "django", "flask", "fastapi", "scrapy"))

    if is_jsp:
        return _preset_jsp()
    if is_java and not is_py:
        return _preset_springboot()
    if is_py and any(k in ts for k in ("爬虫", "爬取", "采集", "数据分析", "数据采集", "舆情", "口碑", "趋势", "满意度", "可视化", "分析")):
        return _preset_py_analysis()
    if is_py:
        return _preset_django()
    return _preset_springboot()


def _preset_py_analysis() -> dict:
    return {
        "stack_table": [
            ["数据采集", "Requests + Scrapy", "静态页面请求与动态渲染抓取，支持断点续爬"],
            ["开发语言", "Python 3.12", "生态丰富，开发效率高"],
            ["数据处理", "pandas + NumPy", "数据清洗、去重、结构化与统计分析"],
            ["可视化", "ECharts 5 / Pyecharts", "交互式统计图表与可视化大屏"],
            ["Web 展示", "Flask 3", "轻量 Web 框架，承载可视化与查询页面"],
            ["数据库", "MySQL 8.0", "InnoDB 引擎，utf8mb4 字符集"],
            ["运行环境", "Windows / Linux", "支持一键启动脚本"],
            ["开发工具", "PyCharm / VS Code", "主流 IDE"],
        ],
        "structure": [
            {"dir": "spider/", "desc": "采集模块：目标站点请求、解析规则、调度与去重"},
            {"dir": "analysis/", "desc": "分析模块：数据清洗、统计计算、指标建模"},
            {"dir": "web/", "desc": "展示模块：Flask 路由、模板页面与 ECharts 图表"},
            {"dir": "sql/", "desc": "数据库初始化脚本与建表语句"},
            {"dir": "docs/", "desc": "项目文档：需求书、部署说明等"},
            {"dir": "start.bat / start.sh", "desc": "一键启动脚本"},
        ],
        "backend_name": "Python 数据采集与分析服务",
    }


def _preset_django() -> dict:
    return {
        "stack_table": [
            ["后端框架", "Django 5.2", "成熟的 MTV 全栈框架，自带 ORM 与 Admin"],
            ["开发语言", "Python 3.12", "生态丰富，开发效率高"],
            ["前端技术", "HTML5 + CSS3 + JavaScript + Bootstrap 5", "响应式页面，兼容主流浏览器"],
            ["数据库", "MySQL 8.0", "InnoDB 引擎，utf8mb4 字符集"],
            ["数据访问", "Django ORM", "模型化操作数据库，防注入"],
            ["模板引擎", "Django Template", "服务端渲染页面"],
            ["运行环境", "Windows / Linux", "支持一键部署脚本"],
            ["开发工具", "PyCharm / VS Code", "主流 IDE"],
        ],
        "structure": [
            {"dir": "backend/", "desc": "后端工程：Django 项目配置、应用模块、模型与视图"},
            {"dir": "backend/app/", "desc": "核心应用：模型层 models、视图层 views、路由 urls、模板 templates"},
            {"dir": "backend/static/", "desc": "静态资源：CSS、JS、图片等文件"},
            {"dir": "sql/", "desc": "数据库初始化脚本与建表语句"},
            {"dir": "docs/", "desc": "项目文档：需求书、部署说明等"},
            {"dir": "start.bat / start.sh", "desc": "一键启动脚本"},
        ],
        "backend_name": "Django 后端",
    }


def _preset_jsp() -> dict:
    return {
        "stack_table": [
            ["后端技术", "JSP + Servlet", "经典 Java Web 三层架构"],
            ["开发语言", "Java 8", "稳定性好，适用面广"],
            ["前端技术", "HTML5 + CSS3 + JavaScript + jQuery + Bootstrap", "响应式页面"],
            ["数据库", "MySQL 8.0", "InnoDB 引擎，utf8mb4 字符集"],
            ["数据访问", "JDBC + PreparedStatement", "预编译防注入"],
            ["Web 容器", "Tomcat 9", "Servlet 容器与静态资源托管"],
            ["运行环境", "Windows / Linux", "支持一键部署脚本"],
            ["开发工具", "IDEA / Eclipse", "主流 Java IDE"],
        ],
        "structure": [
            {"dir": "src/", "desc": "Java 源码：servlet 控制层、dao 数据访问层、entity 实体类、util 工具类"},
            {"dir": "webapp/", "desc": "Web 资源：JSP 页面、static 静态资源、WEB-INF 配置"},
            {"dir": "sql/", "desc": "数据库初始化脚本与建表语句"},
            {"dir": "docs/", "desc": "项目文档：需求书、部署说明等"},
            {"dir": "deploy.bat / deploy.sh", "desc": "一键部署脚本"},
        ],
        "backend_name": "JSP 后端",
    }


def _preset_springboot() -> dict:
    return {
        "stack_table": [
            ["后端框架", "SpringBoot 3.x", "简化配置的 Java 企业级框架"],
            ["开发语言", "Java 17", "LTS 版本，性能与语言特性兼顾"],
            ["前端框架", "Vue 3 + Element Plus", "组件化开发，界面美观易维护"],
            ["数据库", "MySQL 8.0", "InnoDB 引擎，utf8mb4 字符集"],
            ["数据访问", "MyBatis-Plus", "增强版 ORM，通用 CRUD"],
            ["接口规范", "RESTful API + JSON", "前后端分离交互"],
            ["运行环境", "Windows / Linux", "支持一键部署脚本"],
            ["构建工具", "Maven / Vite", "后端与前端工程构建"],
            ["开发工具", "IDEA / VS Code", "主流 IDE"],
        ],
        "structure": [
            {"dir": "backend/", "desc": "后端工程：SpringBoot 启动类、controller 控制层、service 业务层、mapper 持久层、entity 实体类"},
            {"dir": "frontend/", "desc": "前端工程：Vue3 页面组件、路由、状态管理与请求封装"},
            {"dir": "sql/", "desc": "数据库初始化脚本与建表语句"},
            {"dir": "docs/", "desc": "项目文档：需求书、部署说明等"},
            {"dir": "deploy.bat / deploy.sh", "desc": "一键部署脚本（含环境检查）"},
        ],
        "backend_name": "SpringBoot 后端",
    }


def build_template_doc(title: str, tech_stack: str | None = None) -> dict:
    name = short_name(title)
    preset = _stack_preset(tech_stack, title)
    bk = preset["backend_name"]

    goal = [
        f"随着信息化建设的不断推进，传统人工管理模式在{short_name(title).replace('管理系统', '').replace('系统', '') or '相关业务'}领域暴露出效率低、易出错、数据难以沉淀等问题。"
        f"本文档描述的「{name}」旨在通过一套完整的线上管理系统，将分散的业务流程统一到Web平台，实现业务数据的规范化登记、流转、审核与统计。",
        f"系统围绕「注册登录—信息维护—业务办理—审核流转—数据统计」的业务闭环展开，采用{bk}与MySQL数据库相结合的技术组合，"
        "为各类角色的日常操作提供统一入口，并保障数据的一致性与安全性。",
        "本系统定位为计算机专业毕业设计作品，功能覆盖前台用户端与后台管理端，"
        "可为毕业论文撰写、系统测试与答辩演示提供完整的工程支撑。",
    ]

    scope = [
        f"前台用户端：面向普通用户，提供注册登录、信息浏览、业务申请、个人中心等自助服务功能。",
        f"后台管理端：面向管理员，提供用户管理、业务数据管理、审核处理、公告发布与数据统计等管理功能。",
        f"{bk}：提供 RESTful 接口、业务逻辑处理、权限控制与数据持久化。",
        "数据存储层：基于 MySQL 8.0 的数据库设计，涵盖用户、业务、日志等数据实体。",
    ]

    roles = [
        {
            "name": "普通用户",
            "points": [
                "注册账号并登录系统，维护个人基础信息与密码。",
                "浏览系统公告与业务信息列表，按条件检索感兴趣的内容。",
                "发起业务申请，填写并提交相关表单信息。",
                "在个人中心查看自己的历史记录与当前处理状态。",
                "接收系统消息通知，了解业务办理进展。",
                "对已完成业务进行评价或反馈意见。",
            ],
        },
        {
            "name": "管理员",
            "points": [
                "使用管理员账号登录后台，获得全部管理权限。",
                "维护用户账号信息，对违规账号进行禁用或解禁。",
                "管理业务基础数据（分类、字典等），保证数据规范统一。",
                "审核用户提交的申请，执行通过或驳回操作并填写意见。",
                "发布、修改、下架系统公告。",
                "查看多维数据统计报表，掌握系统运行情况。",
                "查询系统操作日志，追溯关键操作。",
            ],
        },
    ]

    scenarios = [
        f"访客在注册页面填写基本信息，系统校验通过后创建账号，随后即可登录使用{name}。",
        "用户登录后进入首页，浏览最新发布的公告与业务信息。",
        "用户通过列表页的条件检索功能，快速定位需要的业务信息并查看详情。",
        "用户在业务申请页面填写表单并提交，系统生成一条待审核记录。",
        "管理员登录后台，在审核列表中查看新提交的申请，核对信息后执行通过操作。",
        "申请被驳回时，系统记录驳回意见，用户可在个人中心查看原因并修改后重新提交。",
        "管理员对业务基础数据进行维护，新增或调整分类，保持数据结构清晰。",
        "管理员发布一条系统公告，所有用户登录后均可查看该公告内容。",
        "管理员打开数据统计页面，查看近期业务量、用户增长等趋势图表。",
        "系统自动记录关键操作日志，管理员按条件检索，追溯某一操作的执行人与时间。",
    ]

    functions = [
        {
            "name": "前台用户端功能",
            "modules": [
                {"name": "账户管理", "points": ["支持用户注册与登录，校验账号唯一性。", "支持修改密码与个人资料。", "支持退出登录。"]},
                {"name": "信息浏览", "points": ["支持首页展示公告与推荐信息。", "支持列表分页浏览。", "支持按关键词与分类检索。", "支持查看信息详情。"]},
                {"name": "业务申请", "points": ["支持在线填写并提交业务申请表单。", "支持查看申请的当前状态。", "支持撤回未处理的申请。"]},
                {"name": "个人中心", "points": ["支持查看个人信息与历史记录。", "支持查看消息通知。", "支持提交意见反馈。"]},
                {"name": "消息公告", "points": ["支持查看系统公告列表与详情。", "支持站内消息提醒。"]},
                {"name": "数据展示", "points": ["支持展示个人相关业务的统计信息。", "支持图表化呈现常用数据。"]},
            ],
        },
        {
            "name": "后台管理端功能",
            "modules": [
                {"name": "管理员登录", "points": ["支持管理员账号密码登录。", "支持登录校验与权限控制。"]},
                {"name": "用户管理", "points": ["支持用户列表分页与检索。", "支持查看、编辑用户信息。", "支持禁用/启用账号。", "支持重置用户密码。"]},
                {"name": "业务数据管理", "points": ["支持业务信息的增删改查。", "支持分类与字典维护。", "支持批量操作。"]},
                {"name": "审核管理", "points": ["支持待审核列表展示。", "支持通过/驳回并填写意见。", "支持查看审核历史。"]},
                {"name": "公告管理", "points": ["支持公告的发布、编辑与下架。", "支持设置公告置顶。"]},
                {"name": "数据统计", "points": ["支持用户量、业务量趋势统计。", "支持分类维度统计与图表展示。", "支持统计结果导出。"]},
                {"name": "日志管理", "points": ["支持记录关键操作日志。", "支持按操作人、时间、类型检索日志。"]},
            ],
        },
    ]

    rules = [
        "用户密码采用加密存储，系统不以明文保存或展示密码。",
        "普通用户与管理员权限严格隔离，未授权接口一律拒绝访问。",
        "业务申请状态按「待审核—已通过—已驳回」流转，状态变更须记录操作人与时间。",
        "同一用户对同一业务在处理中存在未完结记录时，不允许重复提交。",
        "所有列表查询必须分页返回，单页条数由系统限制。",
        "删除操作优先采用逻辑删除，保留历史数据以备追溯。",
        "审核驳回必须填写驳回原因，便于用户修改后重新提交。",
        "统计口径以创建时间为准，金额与数量保留两位小数。",
        "系统时间统一取服务器时间，禁止信任客户端提交的时间。",
        "所有写操作均记录操作日志，日志不可修改与删除。",
        "关键表使用统一的主键与审计字段（创建时间、更新时间）约定。",
        "前端对所有输入做基础校验，后端做最终校验，双层防护。",
    ]

    data_scope = [
        "用户信息：账号、昵称、密码（密文）、手机号、状态、注册时间",
        "管理员信息：账号、姓名、密码（密文）、角色、状态",
        "公告信息：标题、内容、是否置顶、发布人、发布时间、状态",
        "业务分类：分类名称、排序、状态",
        "业务信息：标题、分类、封面、详情、发布人、发布时间、状态",
        "业务申请：申请编号、用户、业务、申请说明、状态、审核意见、申请时间",
        "审核记录：申请编号、审核人、审核动作、审核意见、审核时间",
        "消息通知：接收用户、标题、内容、是否已读、创建时间",
        "意见反馈：反馈用户、反馈内容、处理状态、处理结果、反馈时间",
        "操作日志：操作人、操作类型、操作对象、操作内容、IP、操作时间",
    ]

    database_tables = [
        {
            "name": "用户表（sys_user）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["username", "VARCHAR(50)", "登录账号，唯一"],
                ["password", "VARCHAR(128)", "密码（BCrypt 加密存储）"],
                ["nickname", "VARCHAR(50)", "昵称"],
                ["phone", "VARCHAR(20)", "手机号"],
                ["avatar", "VARCHAR(255)", "头像地址"],
                ["status", "TINYINT", "状态：1 启用 0 禁用"],
                ["created_at", "DATETIME", "创建时间"],
                ["updated_at", "DATETIME", "更新时间"],
            ],
        },
        {
            "name": "公告表（sys_notice）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["title", "VARCHAR(200)", "公告标题"],
                ["content", "TEXT", "公告内容"],
                ["is_top", "TINYINT", "是否置顶：1 是 0 否"],
                ["status", "TINYINT", "状态：1 已发布 0 下架"],
                ["publisher_id", "BIGINT", "发布人 ID"],
                ["created_at", "DATETIME", "发布时间"],
            ],
        },
        {
            "name": "业务分类表（biz_category）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["name", "VARCHAR(50)", "分类名称"],
                ["sort", "INT", "排序号"],
                ["status", "TINYINT", "状态：1 启用 0 停用"],
            ],
        },
        {
            "name": "业务信息表（biz_info）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["title", "VARCHAR(200)", "业务标题"],
                ["category_id", "BIGINT", "分类 ID"],
                ["cover", "VARCHAR(255)", "封面图地址"],
                ["content", "TEXT", "业务详情"],
                ["status", "TINYINT", "状态：1 上架 0 下架"],
                ["publisher_id", "BIGINT", "发布人 ID"],
                ["created_at", "DATETIME", "发布时间"],
            ],
        },
        {
            "name": "业务申请表（biz_apply）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["apply_no", "VARCHAR(32)", "申请编号"],
                ["user_id", "BIGINT", "申请用户 ID"],
                ["biz_id", "BIGINT", "业务 ID"],
                ["description", "VARCHAR(500)", "申请说明"],
                ["status", "TINYINT", "状态：0 待审核 1 通过 2 驳回"],
                ["apply_time", "DATETIME", "申请时间"],
            ],
        },
        {
            "name": "审核记录表（biz_review）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["apply_id", "BIGINT", "申请 ID"],
                ["reviewer_id", "BIGINT", "审核人 ID"],
                ["action", "TINYINT", "动作：1 通过 2 驳回"],
                ["comment", "VARCHAR(500)", "审核意见"],
                ["created_at", "DATETIME", "审核时间"],
            ],
        },
        {
            "name": "消息通知表（sys_message）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["user_id", "BIGINT", "接收用户 ID"],
                ["title", "VARCHAR(200)", "消息标题"],
                ["content", "VARCHAR(500)", "消息内容"],
                ["is_read", "TINYINT", "是否已读：1 是 0 否"],
                ["created_at", "DATETIME", "创建时间"],
            ],
        },
        {
            "name": "意见反馈表（sys_feedback）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["user_id", "BIGINT", "反馈用户 ID"],
                ["content", "VARCHAR(1000)", "反馈内容"],
                ["status", "TINYINT", "处理状态：0 待处理 1 已处理"],
                ["result", "VARCHAR(500)", "处理结果"],
                ["created_at", "DATETIME", "反馈时间"],
            ],
        },
        {
            "name": "操作日志表（operation_log）",
            "columns": [
                ["id", "BIGINT", "主键，自增"],
                ["user_id", "BIGINT", "操作人 ID"],
                ["action", "VARCHAR(50)", "操作类型"],
                ["entity_type", "VARCHAR(30)", "对象类型"],
                ["entity_id", "VARCHAR(32)", "对象 ID"],
                ["detail", "TEXT", "操作详情（JSON）"],
                ["ip", "VARCHAR(64)", "操作 IP"],
                ["created_at", "DATETIME", "操作时间"],
            ],
        },
    ]

    return {
        "title": f"{title}需求书",
        "chapters": {
            "goal": {"heading": CHAPTER_HEADINGS["goal"], "paragraphs": goal},
            "scope": {"heading": CHAPTER_HEADINGS["scope"], "items": scope},
            "roles": {"heading": CHAPTER_HEADINGS["roles"], "roles": roles},
            "scenarios": {"heading": CHAPTER_HEADINGS["scenarios"], "items": scenarios},
            "functions": {"heading": CHAPTER_HEADINGS["functions"], "groups": functions},
            "rules": {"heading": CHAPTER_HEADINGS["rules"], "items": rules},
            "data_scope": {"heading": CHAPTER_HEADINGS["data_scope"], "items": data_scope},
            "tech": {
                "heading": CHAPTER_HEADINGS["tech"],
                "intro": f"系统采用前后端分离架构，结合成熟稳定的技术选型，保证{name}的可维护性与可扩展性。",
                "stack_table": preset["stack_table"],
                "structure": preset["structure"],
            },
            "database": {
                "heading": CHAPTER_HEADINGS["database"],
                "intro": "数据库统一采用 MySQL 8.0，存储引擎 InnoDB，字符集 utf8mb4；"
                         "主键使用 BIGINT 自增，业务表统一包含创建时间、更新时间审计字段。",
                "tables": database_tables,
            },
        },
    }


# ---------------------------------------------------------------------------
# 结构校验与兜底归一化：AI 输出 / 编辑器保存的内容都先过这里
# ---------------------------------------------------------------------------

def _as_str_list(v, limit: int = 60) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:limit]


def _as_table(v) -> list[list[str]]:
    if not isinstance(v, list):
        return []
    rows = []
    for r in v:
        if isinstance(r, list) and len(r) >= 2:
            rows.append([str(c).strip() for c in r[:3]])
    return rows


def normalize_doc(raw: dict | None, title: str, tech_stack: str | None = None) -> dict:
    """将任意来源的文档数据归一化为合法结构；缺失章节用模板补齐。

    例外：mode=raw（原文直用）的文档不做任何补齐/改写，原样返回——
    补模板章节就等于修改了用户「直接采用」的原文。
    """
    if isinstance(raw, dict) and raw.get("mode") == "raw":
        text = str(raw.get("raw_text") or "").strip()
        if text:
            return {"title": str(raw.get("title") or f"{title}需求书"), "mode": "raw", "raw_text": text}
    fallback = build_template_doc(title, tech_stack)
    if not isinstance(raw, dict):
        return fallback

    raw_chapters = raw.get("chapters") if isinstance(raw.get("chapters"), dict) else {}
    doc_title = str(raw.get("title") or f"{title}需求书").strip()
    chapters: dict = {}

    def merged(key: str) -> dict:
        base = dict(fallback["chapters"][key])
        src = raw_chapters.get(key)
        return src if isinstance(src, dict) else base

    # 一、项目目标
    src = merged("goal")
    paras = _as_str_list(src.get("paragraphs"))
    chapters["goal"] = {
        "heading": CHAPTER_HEADINGS["goal"],
        "paragraphs": paras or fallback["chapters"]["goal"]["paragraphs"],
    }

    # 二、建设范围
    src = merged("scope")
    items = _as_str_list(src.get("items"))
    chapters["scope"] = {
        "heading": CHAPTER_HEADINGS["scope"],
        "items": items or fallback["chapters"]["scope"]["items"],
    }

    # 三、角色定义
    src = merged("roles")
    roles = []
    if isinstance(src.get("roles"), list):
        for r in src["roles"]:
            if isinstance(r, dict) and str(r.get("name") or "").strip():
                roles.append({
                    "name": str(r["name"]).strip(),
                    "points": _as_str_list(r.get("points")) or ["使用系统提供的相关功能。"],
                })
    chapters["roles"] = {
        "heading": CHAPTER_HEADINGS["roles"],
        "roles": roles or fallback["chapters"]["roles"]["roles"],
    }

    # 四、核心业务场景
    src = merged("scenarios")
    chapters["scenarios"] = {
        "heading": CHAPTER_HEADINGS["scenarios"],
        "items": _as_str_list(src.get("items")) or fallback["chapters"]["scenarios"]["items"],
    }

    # 五、功能需求
    src = merged("functions")
    groups = []
    if isinstance(src.get("groups"), list):
        for g in src["groups"]:
            if not (isinstance(g, dict) and str(g.get("name") or "").strip()):
                continue
            modules = []
            for m in g.get("modules") or []:
                if isinstance(m, dict) and str(m.get("name") or "").strip():
                    note = str(m.get("note") or "").strip()
                    modules.append({
                        "name": str(m["name"]).strip(),
                        "points": _as_str_list(m.get("points")),
                        **({"note": note} if note else {}),
                    })
            if modules:
                groups.append({"name": str(g["name"]).strip(), "modules": modules})
    chapters["functions"] = {
        "heading": CHAPTER_HEADINGS["functions"],
        "groups": groups or fallback["chapters"]["functions"]["groups"],
    }

    # 六、业务规则
    src = merged("rules")
    chapters["rules"] = {
        "heading": CHAPTER_HEADINGS["rules"],
        "items": _as_str_list(src.get("items")) or fallback["chapters"]["rules"]["items"],
    }

    # 七、数据范围
    src = merged("data_scope")
    chapters["data_scope"] = {
        "heading": CHAPTER_HEADINGS["data_scope"],
        "items": _as_str_list(src.get("items")) or fallback["chapters"]["data_scope"]["items"],
    }

    # 八、技术架构
    src = merged("tech")
    stack = _as_table(src.get("stack_table"))
    structure = []
    if isinstance(src.get("structure"), list):
        for s in src["structure"]:
            if isinstance(s, dict) and str(s.get("dir") or "").strip():
                structure.append({"dir": str(s["dir"]).strip(), "desc": str(s.get("desc") or "").strip()})
            elif isinstance(s, list) and len(s) >= 1:
                structure.append({"dir": str(s[0]), "desc": str(s[1]) if len(s) > 1 else ""})
    fb_tech = fallback["chapters"]["tech"]
    chapters["tech"] = {
        "heading": CHAPTER_HEADINGS["tech"],
        "intro": str(src.get("intro") or "").strip() or fb_tech["intro"],
        "stack_table": stack or fb_tech["stack_table"],
        "structure": structure or fb_tech["structure"],
    }

    # 九、数据库设计
    src = merged("database")
    tables = []
    if isinstance(src.get("tables"), list):
        for t in src["tables"]:
            if isinstance(t, dict) and str(t.get("name") or "").strip():
                cols = _as_table(t.get("columns"))
                if cols:
                    tables.append({"name": str(t["name"]).strip(), "columns": cols})
    fb_db = fallback["chapters"]["database"]
    chapters["database"] = {
        "heading": CHAPTER_HEADINGS["database"],
        "intro": str(src.get("intro") or "").strip() or fb_db["intro"],
        "tables": tables or fb_db["tables"],
    }

    return {"title": doc_title, "chapters": chapters}
