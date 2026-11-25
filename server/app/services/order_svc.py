"""订单公共服务：视图 shaping、创建、权限判断（Web 与代理 API 共用）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from ..models import Order, OrderFile, StatusRevertRequest, User
from .order_no import custom_order_no, next_order_no
from .pricing import compute_prices, get_quality_by_code


def default_deadline() -> date:
    """创建订单未填交付期限时的默认值：一个月后（按日对齐，目标月天数不足时取月末）。"""
    today = date.today()
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    last_day = (date(y, m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(today.day, last_day))


def order_query(db: Session):
    return db.query(Order).filter(Order.is_deleted == False).options(  # noqa: E712
        selectinload(Order.quality),
        selectinload(Order.agent),
        selectinload(Order.assignee),
        selectinload(Order.creator),
    )


def trash_query(db: Session):
    return db.query(Order).filter(Order.is_deleted == True).options(  # noqa: E712
        selectinload(Order.quality),
        selectinload(Order.agent),
        selectinload(Order.assignee),
        selectinload(Order.creator),
    )


def can_access(order: Order, user: User) -> bool:
    """查看权限：管理员/协助者全量，代理只看自己名下订单。"""
    if user.role in ("admin", "staff"):
        return True
    return order.agent_user_id == user.id


def can_download(order: Order, user: User) -> bool:
    """下载/预览权限：写手可下载全部订单的视频/程序包等交付物（含缩略图、交付链接）。

    - 管理员/写手：全部；
    - 代理：仅本人名下订单。
    """
    if user.role in ("admin", "staff"):
        return True
    return order.agent_user_id == user.id


def can_manage_files(order: Order, user: User) -> bool:
    """删除文件权限：管理员/写手可管理全部订单文件（论文留档另有不可删规则拦截）。"""
    return user.role in ("admin", "staff")


# 结单/售后属财务终态，只允许管理员操作
ADMIN_ONLY_STATUSES = {"closed", "after_sale"}

# 写手只能推进到「开始制作 / 完成」，不能取消、结单、转售后。
# pending→completed 是合法的：写手可能拿到单就直接做完；不能因中间态缺失而卡住。
STAFF_STATUS_TRANSITIONS = {
    "pending": {"in_progress", "completed"},
    "in_progress": {"completed"},
}

# 手误撤回只允许回退一步，且不涉及终态
STATUS_REVERT_TARGETS = {
    "in_progress": "pending",
    "completed": "in_progress",
}


def can_change_status(order: Order, user: User, new_status: str) -> bool:
    """状态权限：已取消为终态；管理员可改其余任意状态，写手仅本人负责订单的有限推进。"""
    # 已取消订单不提供恢复入口：审计、统计与交付链接都以取消时的快照为准。
    if order.status == "cancelled":
        return False
    if user.role == "admin":
        return True
    if user.role != "staff":
        return False
    if new_status in ADMIN_ONLY_STATUSES:
        return False
    # 未分派订单允许写手认领；已分派订单只能由负责人推进
    if order.assignee_user_id not in (None, user.id):
        return False
    return new_status in STAFF_STATUS_TRANSITIONS.get(order.status, set())


def allowed_statuses(order: Order, user: User) -> list[str]:
    """当前用户对当前订单可直达的状态（供前端按钮/批量下拉使用）。"""
    if order.status == "cancelled":
        return []
    if user.role == "admin":
        return [s for s in STATUS_CN if s != order.status]
    if user.role != "staff" or order.assignee_user_id not in (None, user.id):
        return []
    return [s for s in STATUS_CN if s in STAFF_STATUS_TRANSITIONS.get(order.status, set())]


def revert_target(order: Order, user: User) -> str | None:
    """写手可申请的撤回目标；非本人负责或终态返回 None。"""
    if user.role != "staff" or order.assignee_user_id != user.id:
        return None
    return STATUS_REVERT_TARGETS.get(order.status)


REVERT_STATUS_CN = {
    "pending": "待审批", "approved": "已通过", "rejected": "已驳回", "cancelled": "已撤回",
}


def revert_view(r: StatusRevertRequest) -> dict:
    return {
        "id": r.id,
        "order_id": r.order_id,
        "requested_by": r.requested_by,
        "username": r.username,
        "from_status": r.from_status,
        "from_status_cn": STATUS_CN.get(r.from_status, r.from_status),
        "to_status": r.to_status,
        "to_status_cn": STATUS_CN.get(r.to_status, r.to_status),
        "reason": r.reason,
        "status": r.status,
        "status_cn": REVERT_STATUS_CN.get(r.status, r.status),
        "reviewed_by": r.reviewed_by,
        "reviewer_name": r.reviewer_name,
        "review_note": r.review_note,
        "reviewed_at": r.reviewed_at,
        "created_at": r.created_at,
    }


def file_view(f: OrderFile) -> dict:
    return {
        "id": f.id,
        "order_id": f.order_id,
        "category": f.category,
        "original_name": f.original_name,
        "size": f.size,
        "mime": f.mime,
        "remark": f.remark,
        "uploaded_by": f.uploaded_by,
        "created_at": f.created_at,
    }


def order_view(order: Order, role: str, *, with_requirement: bool = False, video: dict | None = None) -> dict:
    q = order.quality
    view = {
        "id": order.id,
        "title": order.title,
        "quality": {
            "code": q.code if q else "",
            "name": q.name if q else "",
            "color": q.color if q else "",
        },
        "video": video,
        "status": order.status,
        "deploy_status": order.deploy_status,
        "project_type": order.project_type,
        "deadline": order.deadline,
        "tech_stack": order.tech_stack,
        "customer_info": order.customer_info,
        "remark": order.remark,
        # 原始需求资料仅工作人员可见（生成需求书用）；代理不下发
        **({
            "source_requirement": order.source_requirement,
            "source_apply_mode": order.source_apply_mode or "reference",
            "requirement_notes": order.requirement_notes,
        } if role in ("admin", "staff") else {}),
        "agent": (
            {"id": order.agent.id, "username": order.agent.username, "display_name": order.agent.display_name}
            if order.agent
            else None
        ),
        "assignee": (
            {"id": order.assignee.id, "username": order.assignee.username, "display_name": order.assignee.display_name}
            if order.assignee
            else None
        ),
        "created_by": order.creator.username if order.creator else "",
        "requirement_source": order.requirement_source,
        "requirement_updated_at": order.requirement_updated_at,
        "has_requirement": bool(order.requirement),
        "accepted_at": order.accepted_at,
        "customer_accepted_at": order.customer_accepted_at,
        "completed_at": order.completed_at,
        "closed_at": order.closed_at,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }
    # 价格视野（中间商模式）：
    # - 管理员：成交价（真实价）+ 写手价 + 倍率，赚差价的两端都可见；
    # - 写手：仅写手价（自己的报酬）；
    # - 代理（销售/同行）：仅成交价（自己下单时填的付款额），写手价是内部成本不下发。
    if role == "admin":
        view["owner_price"] = float(order.owner_price)
        view["multiplier"] = float(order.multiplier)
        view["agent_price"] = float(order.agent_price)
    elif role == "staff":
        view["agent_price"] = float(order.agent_price)
    elif role == "agent":
        view["owner_price"] = float(order.owner_price)
    if with_requirement and order.requirement:
        import json

        try:
            view["requirement"] = json.loads(order.requirement)
        except (ValueError, TypeError):
            view["requirement"] = None
    return view


# 项目类型（唯一分类维度）：纯程序设计 / 纯论文 / 论文+设计；含论文的类型启用论文四阶段留档
PROJECT_TYPES = ("program", "thesis", "thesis_program")
PROJECT_TYPE_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}

# 旧「工种」值 → 项目类型的归一映射（兼容历史数据、Excel 旧模板与旧版对接脚本）
LEGACY_CATEGORY_MAP = {"code": "program", "design": "program", "thesis": "thesis"}


def normalize_project_type(value: str | None, legacy_category: str | None = None) -> str | None:
    """项目类型归一：新值直取；旧工种值映射；都无则 None（未设置，按纯程序设计对待）。"""
    if value in PROJECT_TYPES:
        return value
    return LEGACY_CATEGORY_MAP.get((legacy_category or "").strip()) if legacy_category else None


def derive_category(project_type: str | None) -> str:
    """遗留列 orders.category 的推导值（仅保持历史数据/外部 SQL 可读，业务不再使用）。"""
    return "thesis" if project_type == "thesis" else "code"


def has_paper_workflow(order: Order) -> bool:
    """订单是否启用论文进度（任务书/开题报告/初稿/终稿留档）。"""
    return order.project_type in ("thesis", "thesis_program")


def create_order(
    db: Session,
    *,
    title: str,
    quality_code: str,
    creator: User,
    deadline=None,
    tech_stack: str | None = None,
    customer_info: str | None = None,
    remark: str | None = None,
    source_requirement: str | None = None,
    source_apply_mode: str | None = None,
    requirement_notes: str | None = None,
    agent_user: User | None = None,
    project_type: str | None = None,
    owner_price_override: float | None = None,
    order_no: str | None = None,
) -> Order:
    """创建订单：取号 → 计价 → 落库。调用方负责 log 与 commit。

    order_no 传入自定义编号（导入历史项目保留原编号）时跳过自动取号，
    留空则按天自动生成 YYMMDD-NNN。
    """
    clean_title = (title or "").strip()
    if len(clean_title) < 2:
        raise ValueError("题目至少 2 个字符")
    quality = get_quality_by_code(db, quality_code)
    if not quality:
        raise ValueError(f"品质不存在或已停用: {quality_code}")
    # 交付期限留空：默认一个月后（Web / Excel 导入 / API 建单同口径）
    if deadline is None:
        deadline = default_deadline()

    custom_no = (order_no or "").strip()
    if custom_no:
        order_no, seq, order_date = custom_order_no(db, custom_no)
    else:
        order_no, seq, order_date = next_order_no(db)
    owner_price, agent_price, multiplier = compute_prices(db, quality)
    if owner_price_override is not None:
        owner_price = round(Decimal(str(owner_price_override)), 2)
        # 创建/Excel 导入必须与更新路径同口径：真实价为正且不得低于代理价，避免负毛利。
        # 例外：代理（销售/同行）自填成交价不受写手价下限约束——亏单与否由管理员自行权衡。
        if owner_price <= 0:
            raise ValueError("成交价必须大于 0")
        if owner_price < Decimal(str(agent_price)) and not (
            agent_user and agent_user.id == creator.id
        ):
            raise ValueError(f"真实价不能低于代理价（¥{agent_price}）")

    order = Order(
        id=order_no,
        order_date=order_date,
        seq=seq,
        title=clean_title,
        quality_id=quality.id,
        multiplier=multiplier,
        owner_price=owner_price,
        agent_price=agent_price,
        status="pending",
        deploy_status="undeployed",
        # category 为遗留列：按项目类型推导写入，保持历史数据可读
        category=derive_category(project_type),
        project_type=project_type if project_type in PROJECT_TYPES else None,
        deadline=deadline,
        tech_stack=(tech_stack or "").strip() or None,
        customer_info=(customer_info or "").strip() or None,
        remark=(remark or "").strip() or None,
        source_requirement=(source_requirement or "").strip() or None,
        source_apply_mode=source_apply_mode if source_apply_mode in ("reference", "direct") else None,
        requirement_notes=(requirement_notes or "").strip() or None,
        agent_user_id=agent_user.id if agent_user else None,
        created_by=creator.id,
    )
    db.add(order)
    db.flush()
    return order


STATUS_TRANSITIONS = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": {"closed", "after_sale"},
    "closed": {"after_sale"},
    "after_sale": {"closed"},
    # 已取消为终态：不再允许 cancelled→pending 复活（确有需要由管理员新建/恢复）
    "cancelled": set(),
}

STATUS_CN = {
    "pending": "待开始", "in_progress": "制作中", "completed": "已完成",
    "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消",
}


def set_order_status(order: Order, new_status: str, *, allow_any: bool = False) -> bool:
    """唯一状态入口：白名单校验 + 关键时间戳。返回是否发生变化。

    allow_any 仅用于管理员直改与撤回审批通过：允许非相邻跳转，并同步清理回退后
    不应保留的时间戳（例如已结单撤回完成后必须清空 closed_at，否则营收统计仍会计入）。

    所有入口（网页单条/批量、AI 工具、API v1）必须走这里，禁止直接改 order.status。
    """
    if order.status == new_status:
        return False
    # 兜底：任何调用方（含 allow_any 的管理员直改/批量）都不能复活已取消订单。
    if order.status == "cancelled":
        raise ValueError("已取消订单为终态，不能恢复；如需继续请新建订单")
    if not allow_any:
        allowed = STATUS_TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"状态不能从「{STATUS_CN.get(order.status, order.status)}」"
                f"直接变更为「{STATUS_CN.get(new_status, new_status)}」"
            )
    now = datetime.now()
    if new_status == "pending":
        # 回退到待开始：之前推进产生的时间戳全部作废，重新开始计时
        order.accepted_at = None
        order.completed_at = None
        order.closed_at = None
    elif new_status == "in_progress":
        if order.accepted_at is None:
            order.accepted_at = now
        order.completed_at = None
        order.closed_at = None
    elif new_status == "completed":
        if order.accepted_at is None:
            order.accepted_at = now
        if order.completed_at is None:
            order.completed_at = now
        order.closed_at = None
    elif new_status in ("closed", "after_sale"):
        if order.accepted_at is None:
            order.accepted_at = now
        if order.completed_at is None:
            order.completed_at = now
        # 售后同样属于财务结单；completed→after_sale 直转时也要补 closed_at，
        # 否则按 closed_at 统计的营收/对账单会漏掉这笔售后单。
        if order.closed_at is None:
            order.closed_at = now
    # cancelled：保留历史时间戳用于审计，不影响营收口径（CLOSED_STATUSES 不含 cancelled）
    order.status = new_status
    return True


def apply_status(order: Order, new_status: str) -> bool:
    """兼容旧调用名，实际执行中央状态机。"""
    return set_order_status(order, new_status)


def user_allowed_project_types(user: User) -> list[str] | None:
    """用户的 API 可拉取项目类型；None = 不限制。

    历史存量为旧工种值（code/design/thesis），读取时统一归一为项目类型；
    保存时（users 路由）已只接受项目类型新值。
    """
    raw = (user.api_categories or "").strip()
    if not raw:
        return None
    types: list[str] = []
    for part in raw.split(","):
        mapped = normalize_project_type(part.strip())
        if mapped and mapped not in types:
            types.append(mapped)
    return types or None
