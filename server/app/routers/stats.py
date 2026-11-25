from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from ..constants import CLOSED_STATUSES
from ..database import get_db
from ..deps import get_current_user, require_admin, require_staff
from ..models import Order, Quality, User
from ..ratelimit import client_ip, rate_limit
from ..services.oplog import log_op
from ..services.order_svc import order_view

router = APIRouter(prefix="/api/stats", tags=["stats"])

def _month_key(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m") if dt else None


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.is_deleted == False).options(selectinload(Order.quality), selectinload(Order.agent))  # noqa: E712
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    orders = q.all()

    qualities = {qc.code: qc for qc in db.query(Quality).all()}
    is_agent = user.role == "agent"
    # 金额类数据（真实价收入/毛利/代理抽成）仅管理员可见；写手/代理端全部置空
    show_money = user.role == "admin"
    price_of = (lambda o: float(o.agent_price)) if user.role == "staff" else (lambda o: float(o.owner_price))

    now = datetime.now()
    this_month_key = now.strftime("%Y-%m")

    status_counts = {s: 0 for s in ("pending", "in_progress", "completed", "closed", "after_sale", "cancelled")}
    quality_counts: dict[str, int] = {}
    monthly_orders: dict[str, int] = {}
    monthly_income: dict[str, float] = {}
    monthly_gross: dict[str, float] = {}
    income = 0.0
    closed_count = 0
    cycle_days: list[float] = []
    on_time_total = on_time_hit = 0
    agent_stat: dict[int, dict] = {}

    for o in orders:
        status_counts[o.status] = status_counts.get(o.status, 0) + 1
        qcode = o.quality.code if o.quality else "white"
        quality_counts[qcode] = quality_counts.get(qcode, 0) + 1

        mkey = _month_key(o.created_at)
        if mkey:
            monthly_orders[mkey] = monthly_orders.get(mkey, 0) + 1

        if o.status in CLOSED_STATUSES:
            closed_count += 1
            price = price_of(o)
            income += price
            ckey = _month_key(o.closed_at or o.completed_at or o.created_at)
            if ckey:
                monthly_income[ckey] = monthly_income.get(ckey, 0.0) + price
                if not is_agent:
                    monthly_gross[ckey] = monthly_gross.get(ckey, 0.0) + float(o.owner_price) - float(o.agent_price)

        if o.accepted_at and o.completed_at:
            cycle_days.append(max((o.completed_at - o.accepted_at).total_seconds() / 86400.0, 0.0))
        if o.completed_at and o.deadline:
            on_time_total += 1
            if o.completed_at.date() <= o.deadline:
                on_time_hit += 1

        if not is_agent and o.agent:
            key = o.agent.id
            stat = agent_stat.setdefault(
                key,
                {"name": o.agent.display_name or o.agent.username, "username": o.agent.username,
                 "count": 0, "closed": 0, "income": 0.0},
            )
            stat["count"] += 1
            if o.status in CLOSED_STATUSES:
                stat["closed"] += 1
                stat["income"] += float(o.owner_price)

    # 近 12 个月趋势
    trend = []
    y, m = now.year, now.month
    months: list[str] = []
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    trend = [
        {"month": mk, "orders": monthly_orders.get(mk, 0), "income": round(monthly_income.get(mk, 0.0), 2)}
        for mk in months
    ]

    quality_dist = []
    for code, qc in sorted(qualities.items(), key=lambda kv: kv[1].sort):
        if code in quality_counts:
            quality_dist.append({
                "code": code, "name": qc.name, "color": qc.color, "count": quality_counts[code],
            })

    buckets = [(0, 3), (3, 7), (7, 14), (14, 30), (30, 10**9)]
    bucket_labels = ["3天内", "3-7天", "7-14天", "14-30天", "30天以上"]
    cycle_dist = {label: 0 for label in bucket_labels}
    for d in cycle_days:
        for (lo, hi), label in zip(buckets, bucket_labels):
            if lo <= d < hi:
                cycle_dist[label] += 1
                break

    agent_rank = sorted(
        (
            {"id": uid, "name": s["name"], "username": s["username"],
             "count": s["count"], "closed": s["closed"], "income": round(s["income"], 2)}
            for uid, s in agent_stat.items()
        ),
        key=lambda x: x["count"],
        reverse=True,
    )[:8]

    recent = [
        order_view(o, user.role)
        for o in sorted(orders, key=lambda x: x.created_at or datetime.min, reverse=True)[:8]
    ]

    # ---- 周/月 KPI 面板 ----
    def count_in(days_back: int, offset: int = 0, *, status_in=None, price_mode=None):
        lo = now - timedelta(days=days_back * (offset + 1))
        hi = now - timedelta(days=days_back * offset)
        total = 0
        for o in orders:
            t = o.created_at
            if price_mode == "income":
                # 收入口径与 cards/settlement 一致：已结单（含售后），按结单时间
                if o.status not in CLOSED_STATUSES or o.closed_at is None:
                    continue
                t = o.closed_at
            if t is None or not (lo <= t < hi):
                continue
            if status_in and o.status not in status_in:
                continue
            total += price_of(o) if price_mode == "income" else 1
        return total

    def completed_in(days_back: int, offset: int = 0) -> int:
        """按完成时间统计近 N 天完成/结单的单量（不是创建时间）。"""
        lo = now - timedelta(days=days_back * (offset + 1))
        hi = now + timedelta(seconds=1) if offset == 0 else now - timedelta(days=days_back * offset)
        total = 0
        for o in orders:
            stamp = o.completed_at or (o.closed_at if o.status in CLOSED_STATUSES else None)
            if stamp is not None and lo <= stamp < hi:
                total += 1
        return total

    def delta_pct(cur: float, prev: float) -> float | None:
        if prev == 0:
            return None
        return round((cur - prev) / prev * 100, 1)

    kpis = {
        "week_new": count_in(7),
        "week_new_prev": count_in(7, 1),
        "week_completed": completed_in(7),
        "week_completed_prev": completed_in(7, 1),
        "month_new": count_in(30),
        "month_new_prev": count_in(30, 1),
        "month_income": round(count_in(30, price_mode="income"), 2),
        "month_income_prev": round(count_in(30, 1, price_mode="income"), 2),
        # 日历月口径（与 month_gross 一致，供「本月概览」卡使用）
        "month_income_cal": round(monthly_income.get(this_month_key, 0.0), 2),
        "month_gross": round(monthly_gross.get(this_month_key, 0.0), 2),
        "active_orders": status_counts.get("pending", 0) + status_counts.get("in_progress", 0) + status_counts.get("after_sale", 0),
    }
    kpis["week_new_delta"] = delta_pct(kpis["week_new"], kpis["week_new_prev"])
    kpis["month_new_delta"] = delta_pct(kpis["month_new"], kpis["month_new_prev"])
    kpis["month_income_delta"] = delta_pct(kpis["month_income"], kpis["month_income_prev"])
    # 日历月口径环比（上月 key）
    _py, _pm = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    prev_month_key = f"{_py:04d}-{_pm:02d}"
    kpis["month_income_cal_prev"] = round(monthly_income.get(prev_month_key, 0.0), 2)
    kpis["month_income_cal_delta"] = delta_pct(kpis["month_income_cal"], kpis["month_income_cal_prev"])

    # ---- 近 14 日活跃（接单/完成） ----
    activity_daily = []
    for d in range(13, -1, -1):
        day = (now - timedelta(days=d)).date()
        created_n = sum(1 for o in orders if o.created_at and o.created_at.date() == day)
        done_n = sum(
            1 for o in orders
            if o.completed_at and o.completed_at.date() == day
        )
        activity_daily.append({"date": day.strftime("%m-%d"), "orders": created_n, "completed": done_n})

    # ---- 运营健康度雷达（0-100） ----
    total_n = max(len(orders), 1)
    done_rate = (status_counts.get("completed", 0) + status_counts.get("closed", 0)) / total_n * 100
    close_rate = status_counts.get("closed", 0) / total_n * 100
    on_time_rate_v = (on_time_hit / on_time_total * 100) if on_time_total else 0
    avg_cycle = sum(cycle_days) / len(cycle_days) if cycle_days else 30.0
    speed_score = max(0.0, min(100.0, (30.0 - min(avg_cycle, 30.0)) / 30.0 * 100))
    activity_score = min(len(orders) / 30.0 * 100, 100.0)
    health_rate = max(0.0, 100.0 - status_counts.get("after_sale", 0) / total_n * 100)
    radar = [
        {"name": "完成率", "value": round(done_rate, 1)},
        {"name": "结单率", "value": round(close_rate, 1)},
        {"name": "按时交付", "value": round(on_time_rate_v, 1)},
        {"name": "交付速度", "value": round(speed_score, 1)},
        {"name": "活跃度", "value": round(activity_score, 1)},
        {"name": "售后健康", "value": round(health_rate, 1)},
    ]

    # 一周接单热力（周一~周日 × 6 时段）
    hours_bins = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
    heat = [[0] * 6 for _ in range(7)]
    for o in orders:
        t = o.created_at
        if not t:
            continue
        wd = t.weekday()
        hour = t.hour
        for bi, (lo, hi) in enumerate(hours_bins):
            if lo <= hour < hi:
                heat[wd][bi] += 1
                break

    # ---- 项目类型全量统计 ----
    project_type_counts = {"program": 0, "thesis": 0, "thesis_program": 0}
    for o in orders:
        if o.project_type in project_type_counts:
            project_type_counts[o.project_type] += 1

    # ---- 交付提醒：未完结且 7 天内到期（含已逾期），逾期优先、按期限升序 ----
    today = now.date()
    due_soon = []
    for o in orders:
        if o.status not in ("pending", "in_progress", "after_sale") or o.deadline is None:
            continue
        days_left = (o.deadline - today).days
        if days_left > 7:
            continue
        due_soon.append({
            "id": o.id,
            "title": o.title,
            "deadline": o.deadline.isoformat(),
            "days_left": days_left,
            "status": o.status,
            "project_type": o.project_type,
            "quality": {"name": o.quality.name, "color": o.quality.color} if o.quality else None,
            "agent_name": (o.agent.display_name or o.agent.username) if o.agent else None,
        })
    due_soon.sort(key=lambda x: x["days_left"])
    due_soon = due_soon[:8]

    if not show_money:
        # 写手/代理不见金额：收入/客单价/毛利/趋势收入线/代理抽成一并置空，前端按 None 隐藏
        for k in ("income", "avg_price", "month_income", "month_income_prev",
                  "month_income_cal", "month_income_cal_prev", "month_income_cal_delta",
                  "month_income_delta", "month_gross"):
            if k in kpis:
                kpis[k] = None
        agent_rank = []

    return {
        "role": user.role,
        "show_money": show_money,
        "activity_heatmap": heat,
        "cards": {
            "total": len(orders),
            "this_month": monthly_orders.get(this_month_key, 0),
            "in_progress": status_counts.get("in_progress", 0) + status_counts.get("after_sale", 0),
            "completed": status_counts.get("completed", 0),
            "closed": closed_count,
            "income": round(income, 2) if show_money else None,
            "avg_price": (round(income / closed_count, 2) if closed_count else 0.0) if show_money else None,
            "avg_cycle_days": round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else 0.0,
            "on_time_rate": round(on_time_hit / on_time_total * 100, 1) if on_time_total else None,
        },
        "status_counts": status_counts,
        "trend": [
            {"month": t["month"], "orders": t["orders"], "income": (t["income"] if show_money else 0)}
            for t in trend
        ],
        "quality_dist": quality_dist,
        "cycle_dist": [{"label": k, "count": v} for k, v in cycle_dist.items()],
        "agent_rank": agent_rank,
        "recent": recent,
        "due_soon": due_soon,
        "project_type_counts": project_type_counts,
        "kpis": kpis,
        "activity_daily": activity_daily,
        "radar": radar,
    }


# ==================== AI 经营报告 ====================

STATUS_CN_MAP = {"pending": "待开始", "in_progress": "制作中", "completed": "已完成",
                 "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消"}


@router.get("/ai-report")
def ai_report(
    request: Request,
    period: str = Query(default="week", pattern=r"^(week|month)$"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """AI 经营报告：汇总近 7/30 天数据交给 DeepSeek 输出 Markdown 分析（含收入，仅管理员）。"""
    from ..services.docgen.ai import AIGenerationError, deepseek_chat, get_ai_config
    from ..services.ai_quota import ensure_ai_quota

    rate_limit(request, "ai_report", f"{user.id}:{client_ip(request)}", limit=3, window_seconds=60)
    ensure_ai_quota(db, user.id)

    days = 7 if period == "week" else 30
    now = datetime.now()
    lo = now - timedelta(days=days)
    prev_lo = lo - timedelta(days=days)

    q = db.query(Order).filter(Order.is_deleted == False)  # noqa: E712
    new_orders = q.filter(Order.created_at >= lo).all()
    closed_orders = q.filter(Order.status.in_(CLOSED_STATUSES), Order.closed_at >= lo).all()
    prev_new = q.filter(Order.created_at >= prev_lo, Order.created_at < lo).count()
    prev_income = sum(
        float(o.owner_price)
        for o in q.filter(
            Order.status.in_(CLOSED_STATUSES),
            Order.closed_at >= prev_lo,
            Order.closed_at < lo,
        )
    )

    status_now = {}
    for o in new_orders:
        status_now[o.status] = status_now.get(o.status, 0) + 1
    income = sum(float(o.owner_price) for o in closed_orders)
    cycles = [(o.completed_at - o.accepted_at).days for o in closed_orders if o.completed_at and o.accepted_at]
    avg_cycle = round(sum(cycles) / len(cycles), 1) if cycles else None

    pt_cn = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}
    cat_counts = {}
    for o in new_orders:
        key = pt_cn.get(o.project_type, "未设置")
        cat_counts[key] = cat_counts.get(key, 0) + 1

    agent_counts = {}
    for o in new_orders:
        if o.agent:
            name = o.agent.display_name or o.agent.username
            agent_counts[name] = agent_counts.get(name, 0) + 1
    top_agents = sorted(agent_counts.items(), key=lambda x: -x[1])[:3]

    today = now.date()
    due = q.filter(
        Order.status.in_(["pending", "in_progress", "after_sale"]),
        Order.deadline != None,  # noqa: E711
        Order.deadline <= today + timedelta(days=7),
    ).order_by(Order.deadline.asc()).limit(6).all()

    def _delta(cur, prev):
        if not prev:
            return "无同期数据"
        return f"{round((cur - prev) / prev * 100, 1):+}%"

    summary = f"""统计周期：近 {days} 天（{lo.strftime('%Y-%m-%d')} ~ {now.strftime('%Y-%m-%d')}）
- 新增订单：{len(new_orders)} 单（上期 {prev_new} 单，环比 {_delta(len(new_orders), prev_new)}）
- 已结单：{len(closed_orders)} 单；确认收入（真实价）：¥{round(income, 2)}（上期 ¥{round(prev_income, 2)}，环比 {_delta(income, prev_income)}）
- 新单当前状态分布：{('、'.join(f'{STATUS_CN_MAP.get(k, k)} {v}' for k, v in status_now.items())) or '无'}
- 新单项目类型分布：{('、'.join(f'{k} {v}' for k, v in cat_counts.items())) or '无'}
- 来源代理 Top：{('、'.join(f'{n} {c} 单' for n, c in top_agents)) or '无（全部自接）'}
- 平均交付周期：{f'{avg_cycle} 天' if avg_cycle is not None else '暂无完整交付'}
- 7 天内到期/已逾期的在制订单：{len(due)} 单{('：' + '；'.join(f'{o.id}「{(o.title or "")[:20]}」期限{o.deadline}' for o in due)) if due else ''}"""

    from ..services.ai_extra import skill_prompt

    system = skill_prompt(db, "biz_report", (
        "你是一名毕业设计接单业务的资深运营顾问。根据给定的真实经营数据，输出一份结构清晰的中文 Markdown 周报/月报。"
        "要求：只用给定数据，禁止编造数字；提到风险订单时带上单号；语气专业克制；总长度 500~800 字。"
        "结构：## 总体表现（2-3 句结论）/ ## 亮点 / ## 风险与需关注订单 / ## 下阶段建议（3-5 条，具体可执行）。"
    ))

    try:
        report = deepseek_chat(db, system, summary, max_tokens=1600, temperature=0.6, scene="report")
    except AIGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    log_op(db, "ai_report", request=request, user=user, detail={"period": period, "days": days})
    db.commit()
    cfg_model = get_ai_config(db)["model"]
    return {"report": report, "period": period, "days": days, "model": cfg_model, "generated_at": now.strftime("%Y-%m-%d %H:%M")}


# ==================== 代理对账单 ====================

def _month_range(month: str):
    try:
        if len(month) != 7 or month[4] != "-":
            raise ValueError
        y, m = int(month[:4]), int(month[5:7])
        if not 1 <= m <= 12:
            raise ValueError
        start = datetime(y, m, 1)
        end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
        return start, end
    except (ValueError, IndexError):
        return None, None


def _closed_in_month(db: Session, start, end, agent_ids: list | None):
    q = db.query(Order).options(selectinload(Order.quality)).filter(
        Order.is_deleted == False,  # noqa: E712
        Order.status.in_(CLOSED_STATUSES),
        Order.closed_at >= start,
        Order.closed_at < end,
    )
    if agent_ids:
        q = q.filter(Order.agent_user_id.in_(agent_ids))
    return q.all()


def _dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _commission(db: Session, agents: list[User], orders: list[Order]) -> dict[int, dict]:
    """按代理计算 当月已结单代理价 / 收到下级抽成 / 付给上级抽成 / 净得。

    金额全程 Decimal，避免 float 累加误差。上级无论是否在传入的 agents 里
    （例如上级是管理员、已停用或不在当前对账范围）都会计入“已付出”，
    否则代理净得会虚高；上级是管理员时这笔抽成即平台留存。
    """
    ids = {a.id for a in agents}
    parent_ids = {a.parent_id for a in agents if a.parent_id and a.parent_id not in ids}
    if parent_ids:
        parents = db.query(User).filter(User.id.in_(parent_ids)).all()
        agents = list(agents) + [p for p in parents if p.id not in ids]
    result = {a.id: {"own_total": Decimal("0"), "received": Decimal("0"),
                     "paid": Decimal("0"), "net": Decimal("0")} for a in agents}
    for o in orders:
        if o.agent_user_id in result:
            result[o.agent_user_id]["own_total"] += _dec(o.owner_price)
    for a in agents:
        # 没有上级的根代理不产生「付给上级」的抽成，否则净得会被凭空扣减
        if not a.parent_id:
            continue
        rate = Decimal(str(a.commission_rate or 0))
        if rate <= 0:
            continue
        paid = (result[a.id]["own_total"] * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        result[a.id]["paid"] = paid
        if a.parent_id and a.parent_id in result:
            result[a.parent_id]["received"] += paid
    for r in result.values():
        r["net"] = r["own_total"] - r["paid"] + r["received"]
    return {uid: {k: float(v) for k, v in r.items()} for uid, r in result.items()}


@router.get("/settlement")
def settlement(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    agent_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 对账单只属于钱：仅管理员（总览）与代理（本人）可看，写手不可见
    if user.role not in ("admin", "agent"):
        raise HTTPException(status_code=403, detail="对账单仅管理员与代理可查看")
    start, end = _month_range(month)
    if not start:
        raise HTTPException(status_code=400, detail="month 格式应为 YYYY-MM")
    if user.role == "agent":
        agent_id = user.id

    if agent_id:
        target = db.get(User, agent_id)
        if not target or target.role != "agent":
            raise HTTPException(status_code=404, detail="代理不存在")
        # 单代理模式：本人 + 直接下级 一起纳入，才能算出“收到下级抽成”
        children = db.query(User).filter(
            User.parent_id == target.id, User.role == "agent",
        ).all()
        parent_user = db.get(User, target.parent_id) if target.parent_id else None
        involved_ids = [target.id] + [c.id for c in children]
        if parent_user and parent_user.role == "agent":
            involved_ids.append(parent_user.id)
        orders = _closed_in_month(db, start, end, involved_ids)
        involved_agents = [target] + list(children) + ([parent_user] if parent_user and parent_user.role == "agent" else [])
        comm = _commission(db, involved_agents, orders)
        return {
            "month": month,
            "agent": {"id": target.id, "username": target.username, "display_name": target.display_name,
                      "parent_id": target.parent_id,
                      "parent_name": (parent_user.display_name or parent_user.username) if parent_user else None,
                      "commission_rate": float(target.commission_rate or 0)},
            "summary": comm.get(target.id, {"own_total": 0, "received": 0, "paid": 0, "net": 0}),
            "items": [{
                "id": o.id, "title": o.title,
                "quality": {"name": o.quality.name, "color": o.quality.color} if o.quality else None,
                "agent_price": float(o.owner_price), "closed_at": o.closed_at,
            } for o in sorted(orders, key=lambda x: x.closed_at or datetime.min) if o.agent_user_id == target.id],
        }

    orders = _closed_in_month(db, start, end, None)
    # 总览包含已停用代理的历史订单，否则 orders 计数与代理行合计会对不上。
    agents = db.query(User).filter(User.role == "agent").all()
    comm = _commission(db, agents, orders)

    # 管理员/协助者总览模式：按代理汇总
    return {
        "month": month,
        "agents": [{
            "id": a.id, "username": a.username, "display_name": a.display_name or a.username,
            "parent_id": a.parent_id, "commission_rate": float(a.commission_rate or 0),
            **comm.get(a.id, {"own_total": 0, "received": 0, "paid": 0, "net": 0}),
        } for a in agents],
        "totals": {
            "own_total": round(sum(c["own_total"] for c in comm.values()), 2),
            "received": round(sum(c["received"] for c in comm.values()), 2),
            "paid": round(sum(c["paid"] for c in comm.values()), 2),
            "net": round(sum(c["net"] for c in comm.values()), 2),
            "count": len(orders),
        },
    }


@router.get("/settlement/export")
def settlement_export(
    request: Request,
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    agent_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("admin", "agent"):
        raise HTTPException(status_code=403, detail="对账单仅管理员与代理可导出")
    import csv
    import io

    data = settlement(month=month, agent_id=agent_id, user=user, db=db)
    def _cell(v):
        text = str(v)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    buf = io.StringIO()
    w = csv.writer(buf)
    if "items" in data:  # 单代理明细
        a = data["agent"]
        w.writerow(["单号", "题目", "品质", "代理价", "结单时间"])
        for it in data["items"]:
            w.writerow([_cell(it["id"]), _cell(it["title"]), _cell(it["quality"]["name"] if it["quality"] else ""),
                        it["agent_price"], str(it["closed_at"])[:19]])
        s = data["summary"]
        w.writerow([])
        w.writerow(["汇总", f"{a['display_name']}（{a['username']}）"])
        w.writerow(["已结单代理价合计", s["own_total"]])
        w.writerow(["收到下级抽成", s["received"]])
        w.writerow(["付给上级抽成", s["paid"]])
        w.writerow(["净得", s["net"]])
    else:  # 总览
        w.writerow(["代理", "上级抽成%", "已结单代理价", "收到下级抽成", "付给上级抽成", "净得"])
        for a in data["agents"]:
            w.writerow([_cell(a["display_name"]), a["commission_rate"], a["own_total"], a["received"], a["paid"], a["net"]])
        t = data["totals"]
        w.writerow(["合计", "", t["own_total"], t["received"], t["paid"], t["net"]])
    log_op(db, "settlement_export", request=request, user=user, detail={"month": month, "agent_id": agent_id})
    db.commit()
    filename = f"settlement-{month}.csv"
    return StreamingResponse(
        iter(["\ufeff" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ============================== 写手绩效看板 ==============================

@router.get("/writer-perf")
def writer_perf(
    month: str | None = None,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """写手绩效：接单量/完成量/按时率/平均交付天数/售后率/写手报酬，可选月份过滤（YYYY-MM）。"""
    from sqlalchemy import func
    from ..services.order_svc import order_query as _oq

    staff = db.query(User).filter(User.role == "staff", User.is_active == True).all()  # noqa: E712
    q = _oq(db).filter(Order.assignee_user_id != None)  # noqa: E712
    if month:
        start, end = _month_range(month)
        if not start:
            raise HTTPException(status_code=422, detail="month 格式应为 YYYY-MM")
        # 按“完成/结单月”归属，与经营月报、对账单口径一致；未完成单落到创建月
        stamp = func.coalesce(Order.completed_at, Order.closed_at, Order.created_at)
        q = q.filter(stamp >= start, stamp < end)
    orders = q.all()
    by_assignee: dict[int, list[Order]] = {}
    for o in orders:
        by_assignee.setdefault(o.assignee_user_id, []).append(o)

    rows = []
    for s in staff:
        os_ = by_assignee.get(s.id, [])
        total = len(os_)
        done = [o for o in os_ if o.status in ("completed", "closed", "after_sale")]
        on_time = [o for o in done if o.deadline and o.completed_at and o.completed_at.date() <= o.deadline]
        # 交付周期统一为 接单→完成；未记录接单时间的单不参与平均，避免用
        # created_at 顶替导致周期被低估（与 overview 口径一致）
        days = [(o.completed_at - o.accepted_at).days
                for o in done if o.completed_at and o.accepted_at]
        after_sale = [o for o in os_ if o.status == "after_sale"]
        income = sum(float(o.agent_price) for o in os_ if o.status in CLOSED_STATUSES)
        rows.append({
            "id": s.id,
            "name": s.display_name or s.username,
            "username": s.username,
            "total": total,
            "in_progress": sum(1 for o in os_ if o.status == "in_progress"),
            "done": len(done),
            "closed": sum(1 for o in os_ if o.status in CLOSED_STATUSES),
            "on_time": len(on_time),
            "on_time_rate": round(len(on_time) / len(done) * 100, 1) if done else None,
            "avg_days": round(sum(days) / len(days), 1) if days else None,
            "after_sale": len(after_sale),
            "after_sale_rate": round(len(after_sale) / total * 100, 1) if total else None,
            "income": round(income, 2),
        })
    rows.sort(key=lambda r: r["total"], reverse=True)
    with_days = [r["avg_days"] for r in rows if r["avg_days"] is not None]
    totals = {
        "total": sum(r["total"] for r in rows),
        "done": sum(r["done"] for r in rows),
        "avg_days": round(sum(with_days) / len(with_days), 1) if with_days else None,
        "income": round(sum(r["income"] for r in rows), 2),
        "staff_count": len(rows),
    }
    return {"month": month, "rows": rows, "totals": totals}


# ============================== AI Token 用量统计 ==============================

SCENE_CN = {
    "chat": "AI 助手对话", "docgen": "需求书生成", "summary": "订单摘要",
    "report": "经营周报", "diff": "差异总结", "title": "题目分析",
}


@router.get("/ai-usage")
def ai_usage_stats(
    days: int = 30,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Token 用量：总量/按场景/按天趋势/明细 + 成本估算。"""
    from datetime import timedelta as _td

    from ..models import AiUsage
    from ..services.settings_svc import get_setting

    days = min(max(days, 1), 365)
    start = datetime.now() - _td(days=days)
    q = db.query(AiUsage).filter(AiUsage.created_at >= start)
    rows = q.order_by(AiUsage.created_at.desc()).all()

    try:
        price_1k = float(get_setting(db, "ai_price_per_1k") or 0)
    except ValueError:
        price_1k = 0

    by_scene: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    total_tokens = total_calls = 0
    for r in rows:
        sc = SCENE_CN.get(r.scene, r.scene)
        b = by_scene.setdefault(sc, {"scene": sc, "calls": 0, "tokens": 0})
        b["calls"] += 1
        b["tokens"] += r.total_tokens or 0
        day = r.created_at.strftime("%Y-%m-%d") if r.created_at else "?"
        d = by_day.setdefault(day, {"day": day, "tokens": 0, "calls": 0})
        d["tokens"] += r.total_tokens or 0
        d["calls"] += 1
        total_tokens += r.total_tokens or 0
        total_calls += 1

    day_list = sorted(by_day.values(), key=lambda x: x["day"])
    return {
        "days": days,
        "totals": {
            "calls": total_calls,
            "tokens": total_tokens,
            "prompt": sum(r.prompt_tokens or 0 for r in rows),
            "completion": sum(r.completion_tokens or 0 for r in rows),
            "cost": round(total_tokens / 1000 * price_1k, 2) if price_1k else 0,
            "price_1k": price_1k,
        },
        "by_scene": sorted(by_scene.values(), key=lambda x: -x["tokens"]),
        "by_day": day_list,
        "recent": [
            {"id": r.id, "scene": SCENE_CN.get(r.scene, r.scene), "model": r.model,
             "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
             "total_tokens": r.total_tokens, "duration_ms": r.duration_ms,
             "order_id": r.order_id, "created_at": r.created_at}
            for r in rows[:100]
        ],
    }


# ============================== 订单毛利看板 ==============================

@router.get("/margin")
def margin_stats(
    month: str | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """订单毛利：成交价（owner_price）- 写手报酬（agent_price）。

    仅管理员可见，避免代理/写手看到成本价。默认统计全部已结单/售后订单，
    可按 YYYY-MM 过滤；同时给出品质维度与近 6 个月趋势。
    """
    q = db.query(Order).options(selectinload(Order.quality)).filter(
        Order.is_deleted == False,  # noqa: E712
        Order.status.in_(CLOSED_STATUSES),
    )
    start = end = None
    if month:
        start, end = _month_range(month)
        if not start:
            raise HTTPException(status_code=422, detail="month 格式应为 YYYY-MM")
        q = q.filter(Order.closed_at >= start, Order.closed_at < end)
    rows = q.all()

    def profit_of(o: Order) -> tuple[Decimal, Decimal]:
        return _dec(o.owner_price), _dec(o.agent_price)

    revenue = Decimal("0")
    cost = Decimal("0")
    by_quality: dict[str, dict] = {}
    by_month: dict[str, dict] = {}
    items = []
    for o in rows:
        rev, cst = profit_of(o)
        gross = rev - cst
        revenue += rev
        cost += cst
        qname = o.quality.name if o.quality else "未分类"
        qcode = o.quality.code if o.quality else ""
        qb = by_quality.setdefault(qcode or qname, {
            "code": qcode, "name": qname, "count": 0,
            "revenue": Decimal("0"), "cost": Decimal("0"), "profit": Decimal("0"),
        })
        qb["count"] += 1
        qb["revenue"] += rev
        qb["cost"] += cst
        qb["profit"] += gross
        stamp = o.closed_at or o.completed_at or o.created_at
        if stamp:
            key = stamp.strftime("%Y-%m")
            mb = by_month.setdefault(key, {
                "month": key, "count": 0,
                "revenue": Decimal("0"), "cost": Decimal("0"), "profit": Decimal("0"),
            })
            mb["count"] += 1
            mb["revenue"] += rev
            mb["cost"] += cst
            mb["profit"] += gross
        items.append({
            "id": o.id, "title": o.title, "quality": qname,
            "closed_at": o.closed_at, "revenue": float(rev), "cost": float(cst),
            "profit": float(gross),
            "margin_rate": round(float(gross / rev * 100), 1) if rev else None,
        })

    def rate(rev: Decimal, profit: Decimal) -> float | None:
        return round(float(profit / rev * 100), 1) if rev else None

    gross_profit = revenue - cost
    quality_rows = []
    for v in by_quality.values():
        quality_rows.append({
            "code": v["code"], "name": v["name"], "count": v["count"],
            "revenue": float(v["revenue"]), "cost": float(v["cost"]),
            "profit": float(v["profit"]),
            "margin_rate": rate(v["revenue"], v["profit"]),
        })
    quality_rows.sort(key=lambda r: -r["profit"])
    trend = []
    for v in sorted(by_month.values(), key=lambda x: x["month"])[-6:]:
        trend.append({
            "month": v["month"], "count": v["count"],
            "revenue": float(v["revenue"]), "cost": float(v["cost"]),
            "profit": float(v["profit"]),
            "margin_rate": rate(v["revenue"], v["profit"]),
        })
    items.sort(key=lambda r: -r["profit"])
    return {
        "month": month,
        "summary": {
            "count": len(rows), "revenue": float(revenue), "cost": float(cost),
            "profit": float(gross_profit), "margin_rate": rate(revenue, gross_profit),
            "avg_profit": round(float(gross_profit / len(rows)), 2) if rows else 0,
        },
        "by_quality": quality_rows,
        "trend": trend,
        "top_orders": items[:10],
        "low_margin_orders": sorted(
            [i for i in items if i["revenue"] > 0], key=lambda r: (r["margin_rate"] is None, r["margin_rate"])
        )[:10],
    }


# ============================== SLA / 交期风险 ==============================

@router.get("/deadline-risk")
def deadline_risk(
    days: int = Query(default=3, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """交期风险：逾期 + N 天内到期（默认 3 天），按紧急程度排序。

    代理只看自己名下订单；管理员/写手看全局，方便安排产能。
    """
    from ..services.order_svc import order_query as _oq

    today = date.today()
    horizon = today + timedelta(days=days)
    q = _oq(db).filter(
        Order.status.in_(("pending", "in_progress")),
        Order.deadline.isnot(None),
        Order.deadline <= horizon,
    )
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    rows = q.order_by(Order.deadline.asc()).limit(200).all()
    overdue, soon = [], []
    for o in rows:
        days_left = (o.deadline - today).days
        item = {
            "id": o.id, "title": o.title, "status": o.status,
            "deadline": o.deadline, "days_left": days_left,
            "quality": {"code": o.quality.code, "name": o.quality.name} if o.quality else None,
            "assignee": (o.assignee.display_name or o.assignee.username) if o.assignee else None,
            "agent": (o.agent.display_name or o.agent.username) if o.agent else None,
        }
        (overdue if days_left < 0 else soon).append(item)
    return {
        "days": days,
        "today": today,
        "summary": {"overdue": len(overdue), "soon": len(soon), "total": len(overdue) + len(soon)},
        "overdue": overdue[:50],
        "soon": soon[:50],
    }
