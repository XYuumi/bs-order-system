"""AI 参谋：交付风险雷达 + 需求书体检 + 客户回访话术 + 验收清单。

设计原则：
- 确定性规则负责“事实与分数”，大模型负责“解释与行动建议”，避免模型幻觉制造假风险；
- 所有 AI 调用统一配额、限流、审计日志与 Token 记账；
- 严格复用订单访问权限，写手只能看到 can_access 的订单。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import require_staff
from ..models import Order, OrderFile, OrderNote, User
from ..ratelimit import client_ip, rate_limit
from ..services.ai_quota import ensure_ai_quota
from ..services.oplog import log_op
from ..services.order_svc import can_access

router = APIRouter(prefix="/api/ai-ops", tags=["ai-ops"])

ACTIVE_STATUSES = ("pending", "in_progress", "completed", "after_sale")
STATUS_LABEL = {
    "pending": "待开始", "in_progress": "制作中", "completed": "已完成",
    "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消",
}
PROJECT_TYPE_LABEL = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}
SCENE_LABEL = {
    "kickoff": "需求确认", "progress": "进度同步", "risk": "延期沟通",
    "acceptance": "验收提醒", "aftersale": "售后回访",
}
TONE_LABEL = {"warm": "亲切", "professional": "专业", "concise": "简洁"}


def _today() -> date:
    return datetime.now().date()


def _get_order(db: Session, order_id: str) -> Order:
    order = (
        db.query(Order)
        .options(selectinload(Order.quality), selectinload(Order.assignee), selectinload(Order.agent))
        .filter(Order.id == order_id, Order.is_deleted == False)  # noqa: E712
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def _accessible(db: Session, user: User, order_id: str) -> Order:
    order = _get_order(db, order_id)
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权访问该订单")
    return order


def _ai_guard(db: Session, user: User, request: Request, action: str) -> None:
    rate_limit(request, "ai_ops_" + action, f"{user.id}:{client_ip(request)}", limit=6, window_seconds=60)
    ensure_ai_quota(db, user.id)


def _ai_call(db: Session, user: User, system: str, prompt: str, *, scene: str, max_tokens: int = 1400,
             order_id: str | None = None, temperature: float = 0.4, json_mode: bool = False) -> str:
    from ..services.docgen.ai import AIGenerationError, deepseek_chat

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            text = deepseek_chat(
                db, system, prompt, max_tokens=max_tokens, temperature=temperature,
                scene=scene, order_id=order_id, user_id=user.id, json_mode=json_mode,
            )
        except AIGenerationError as exc:
            last_error = exc
            continue
        if (text or "").strip():
            return text
        last_error = AIGenerationError("AI 未返回内容")
    raise HTTPException(status_code=503, detail=str(last_error or "AI 暂时不可用，请稍后重试"))


def _parse_json(text: str) -> dict:
    from ..services.docgen.ai import _loads_repair

    data, _strategy = _loads_repair(text)
    return data if isinstance(data, dict) else {}


def _unescape_fragment(value: str) -> str:
    try:
        return json.loads('"' + value + '"')
    except Exception:
        return value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _reply_message(data: dict, raw: str) -> str:
    """从模型输出中取回访消息；兼容整体 JSON 解析失败或字段被二次编码。"""
    value = data.get("message") if isinstance(data, dict) else None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.startswith("{") and '"message"' in text:
            inner = _parse_json(text)
            if isinstance(inner.get("message"), str) and inner["message"].strip():
                return inner["message"].strip()
        return text
    match = re.search(r'"message"\s*:\s*"(.*?)"\s*,\s*"tips"', raw or "", re.S)
    if match:
        return _unescape_fragment(match.group(1)).strip()
    match = re.search(r'"message"\s*:\s*"(.*?)"\s*\}', raw or "", re.S)
    if match:
        return _unescape_fragment(match.group(1)).strip()
    match = re.search(r'"message"\s*:\s*"(.*?)"', raw or "", re.S)
    if match:
        return _unescape_fragment(match.group(1)).strip()
    text = (raw or "").strip()
    if text and not text.startswith("{") and '"message"' not in text:
        return text[:1000]
    return ""


def _progress_text(order: Order) -> str:
    if order.status == "pending":
        return "尚未开始制作"
    if order.status == "in_progress":
        if order.accepted_at:
            return f"制作中（接单后第 {max((_today() - order.accepted_at.date()).days, 1)} 天）"
        return "制作中"
    if order.status == "completed":
        return "已完成待结单"
    if order.status == "after_sale":
        return "售后处理中"
    return STATUS_LABEL.get(order.status, order.status)


def _risk_of(order: Order, *, file_counts: dict[str, int], note_count: int) -> dict[str, Any]:
    """确定性风险评分：只使用数据库事实，可解释、可复现。"""
    reasons: list[dict[str, Any]] = []
    score = 0

    def add(weight: int, code: str, label: str) -> None:
        nonlocal score
        score += weight
        reasons.append({"code": code, "label": label, "weight": weight})

    today = _today()
    days_left = (order.deadline - today).days if order.deadline else None
    if order.deadline is None:
        add(14, "no_deadline", "未设置交付期限")
    elif days_left < 0:
        add(42 + min(abs(days_left) * 3, 18), "overdue", f"已逾期 {abs(days_left)} 天")
    elif days_left <= 2:
        add(34, "due_urgent", f"仅剩 {days_left} 天到期")
    elif days_left <= 7:
        add(20, "due_soon", f"{days_left} 天后到期")

    if order.status == "pending":
        add(12, "not_started", "仍未开始制作")
        if order.created_at and (datetime.now() - order.created_at).days >= 3:
            add(8, "pending_age", "下单超过 3 天仍未开工")
    elif order.status == "in_progress" and not order.assignee:
        add(16, "no_assignee", "制作中但未指定负责人")
    elif order.status == "completed":
        add(8, "awaiting_close", "已完成待结单")
    elif order.status == "after_sale":
        add(20, "after_sale", "处于售后处理中")

    pkg = file_counts.get("package", 0)
    video = file_counts.get("video", 0)
    if not pkg and not video:
        add(10 if order.status != "completed" else 18, "no_deliverable", "还没有程序包或演示视频")
    elif order.status == "completed" and not pkg:
        add(10, "no_package", "已完成但缺少程序包")
    if not order.requirement or not str(order.requirement).strip():
        add(8, "no_requirement", "需求书尚未生成")
    if note_count == 0:
        add(4, "no_notes", "没有任何客户跟进记录")
    if order.status == "in_progress" and order.accepted_at:
        idle = (datetime.now() - order.accepted_at).days
        if idle >= 10 and days_left is not None and days_left <= 7:
            add(6, "tight_window", f"已制作 {idle} 天且临近交付")
    if order.customer_accepted_at is None and order.status in ("completed", "closed"):
        add(5, "not_accepted", "客户尚未确认验收")

    score = min(score, 100)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"

    def next_action() -> str:
        codes = {r["code"] for r in reasons}
        if "overdue" in codes:
            return "今天先联系客户说明进度并给出明确交付时间，同步把订单标记为高优先级。"
        if "due_urgent" in codes:
            return "24 小时内安排负责人冲刺，先交付可运行版本，再补充文档。"
        if "no_deliverable" in codes:
            return "补齐程序包/演示视频并上传，再生成客户交付链接。"
        if "no_assignee" in codes:
            return "立刻指定制作负责人，避免订单悬空。"
        if "no_requirement" in codes:
            return "先确认需求并生成需求书，作为后续验收依据。"
        if "not_started" in codes:
            return "确认客户资料是否齐全，安排开工时间。"
        if "no_notes" in codes:
            return "补一条客户跟进记录，写清当前约定与下一步。"
        return "按计划推进，并在交付前 3 天做一次自检。"

    return {
        "order_id": order.id,
        "title": order.title or "",
        "status": order.status,
        "status_label": STATUS_LABEL.get(order.status, order.status),
        "project_type": order.project_type,
        "project_type_label": PROJECT_TYPE_LABEL.get(order.project_type, order.project_type or "-"),
        "deadline": order.deadline.isoformat() if order.deadline else None,
        "days_left": days_left,
        "assignee": (order.assignee.display_name or order.assignee.username) if order.assignee else None,
        "progress": _progress_text(order),
        "risk_score": score,
        "risk_level": level,
        "reasons": sorted(reasons, key=lambda x: -x["weight"]),
        "next_action": next_action(),
        "file_counts": file_counts,
        "note_count": note_count,
    }


def _collect_risks(db: Session, user: User) -> list[dict[str, Any]]:
    q = (
        db.query(Order)
        .options(selectinload(Order.quality), selectinload(Order.assignee), selectinload(Order.agent))
        .filter(Order.is_deleted == False, Order.status.in_(ACTIVE_STATUSES))  # noqa: E712
    )
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    orders = q.all()
    ids = [o.id for o in orders]
    if not ids:
        return []

    file_rows = (
        db.query(OrderFile.order_id, OrderFile.category, func.count(OrderFile.id))
        .filter(OrderFile.order_id.in_(ids), OrderFile.is_deleted == False)  # noqa: E712
        .group_by(OrderFile.order_id, OrderFile.category)
        .all()
    )
    file_map: dict[str, dict[str, int]] = {}
    for oid, cat, cnt in file_rows:
        file_map.setdefault(oid, {})[cat] = int(cnt)
    note_rows = (
        db.query(OrderNote.order_id, func.count(OrderNote.id))
        .filter(OrderNote.order_id.in_(ids))
        .group_by(OrderNote.order_id)
        .all()
    )
    note_map = {oid: int(cnt) for oid, cnt in note_rows}

    risks = [
        _risk_of(o, file_counts=file_map.get(o.id, {}), note_count=note_map.get(o.id, 0))
        for o in orders
    ]
    risks.sort(key=lambda r: (-r["risk_score"], r["deadline"] or "9999-12-31"))
    return risks


@router.get("/overview")
def overview(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    from ..services.docgen.ai import ai_available

    risks = _collect_risks(db, user)
    active = len(risks)
    high = sum(1 for r in risks if r["risk_level"] == "high")
    medium = sum(1 for r in risks if r["risk_level"] == "medium")
    overdue = sum(1 for r in risks if (r["days_left"] is not None and r["days_left"] < 0))
    due7 = sum(1 for r in risks if (r["days_left"] is not None and 0 <= r["days_left"] <= 7))
    no_owner = sum(1 for r in risks if "no_assignee" in {x["code"] for x in r["reasons"]})
    no_doc = sum(1 for r in risks if "no_requirement" in {x["code"] for x in r["reasons"]})
    avg_score = round(sum(r["risk_score"] for r in risks) / active, 1) if active else 0
    recent_q = (
        db.query(Order)
        .options(selectinload(Order.quality))
        .filter(Order.is_deleted == False, Order.status.in_(("closed", "after_sale")))  # noqa: E712
        .order_by(Order.closed_at.desc(), Order.created_at.desc())
        .limit(8)
    )
    recent = []
    for o in recent_q.all():
        recent.append({
            "order_id": o.id, "title": o.title or "", "status": o.status,
            "status_label": STATUS_LABEL.get(o.status, o.status),
            "deadline": o.deadline.isoformat() if o.deadline else None,
            "closed_at": o.closed_at.isoformat(timespec="minutes") if o.closed_at else None,
            "customer_accepted": bool(o.customer_accepted_at),
            "project_type_label": PROJECT_TYPE_LABEL.get(o.project_type, o.project_type or "-"),
        })
    option_q = db.query(Order).filter(Order.is_deleted == False)  # noqa: E712
    if user.role == "agent":
        option_q = option_q.filter(Order.agent_user_id == user.id)
    options = []
    for o in option_q.order_by(Order.created_at.desc()).limit(60).all():
        options.append({"order_id": o.id, "title": o.title or "", "status": o.status, "status_label": STATUS_LABEL.get(o.status, o.status)})
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ai_ready": ai_available(db),
        "stats": {
            "active": active, "high": high, "medium": medium, "safe": active - high - medium,
            "overdue": overdue, "due_7": due7, "no_owner": no_owner, "no_requirement": no_doc,
            "avg_score": avg_score,
        },
        "focus": risks[:3],
        "risks": risks[:40],
        "recent": recent,
        "order_options": options,
    }


@router.post("/risk-brief")
def risk_brief(request: Request, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    risks = _collect_risks(db, user)
    if not risks:
        # 空态不需要调用模型，也不应消耗 AI 配额/触发限流。
        return {"headline": "当前没有在制订单", "summary": "所有订单都已交付或归档，可以先复盘最近结单，或提前整理交付模板。", "priorities": [], "generated_at": datetime.now().isoformat(timespec="seconds")}
    _ai_guard(db, user, request, "brief")
    top = risks[:10]
    context = "\n".join(
        f'- {r["order_id"]}「{r["title"][:38]}」状态{r["status_label"]}，期限{r["deadline"] or "未设置"}，'
        f'剩余{r["days_left"] if r["days_left"] is not None else "?"}天，风险{r["risk_score"]}分（{r["risk_level"]}），'
        f'原因：{"；".join(x["label"] for x in r["reasons"][:4]) or "常规"}'
        for r in top
    )
    system = (
        "你是毕业设计交付团队的项目总监。根据系统计算出的真实风险数据，给出今天可直接执行的优先级安排。"
        "只输出 JSON，不要 Markdown 代码块，禁止编造不存在的订单或数据。"
    )
    prompt = f"""今天：{_today().isoformat()}。在制订单风险清单（已按风险分降序）：
{context}

输出 JSON：
{{
  "headline": "一句话判断今天整体交付压力（不超过 28 字）",
  "summary": "2-3 句说明最需要关注的集中风险（不超过 120 字）",
  "priorities": [
    {{"order_id": "单号", "title": "题目", "urgency": "now|today|this_week", "action": "具体动作，不超过 40 字", "reason": "为什么优先，不超过 40 字"}}
  ]
}}
priorities 最多 5 条，必须来自上面的清单。"""
    text = _ai_call(db, user, system, prompt, scene="ai_risk_brief", max_tokens=1600, temperature=0.3, json_mode=True)
    data = _parse_json(text)
    priorities = data.get("priorities") if isinstance(data.get("priorities"), list) else []
    valid_ids = {r["order_id"] for r in top}
    clean = []
    for p in priorities[:5]:
        if not isinstance(p, dict):
            continue
        oid = str(p.get("order_id") or "").strip()
        if oid not in valid_ids:
            continue
        clean.append({
            "order_id": oid,
            "title": str(p.get("title") or ""),
            "urgency": p.get("urgency") if p.get("urgency") in ("now", "today", "this_week") else "today",
            "action": str(p.get("action") or ""),
            "reason": str(p.get("reason") or ""),
        })
    log_op(db, "ai_risk_brief", request=request, user=user, detail={"orders": len(top)})
    db.commit()
    return {
        "headline": str(data.get("headline") or "交付风险已梳理"),
        "summary": str(data.get("summary") or text[:200]),
        "priorities": clean,
        "risk_count": len(risks),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _requirement_metrics(text: str) -> dict[str, Any]:
    t = text or ""
    sections = re.findall(r"(?m)^\s*(?:[一二三四五六七八九十]+[、.]|\d+[、.]|#{1,3}\s)", t)
    numbers = re.findall(r"\d+(?:\.\d+)?\s*(?:个|项|张|天|周|用户|角色|模块|页面|%|次|人)", t)
    return {
        "chars": len(t),
        "sections": len(sections),
        "numbers": len(numbers),
        "has_acceptance": bool(re.search(r"验收|测试|交付标准|功能清单", t)),
        "has_tech": bool(re.search(r"Spring|Vue|React|Django|Flask|MySQL|Python|Java|Node|小程序|UniApp|PHP|Vite", t, re.I)),
    }


@router.post("/requirement-review")
def requirement_review(body: dict, request: Request, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    order_id = str((body or {}).get("order_id") or "").strip()
    if not order_id:
        raise HTTPException(status_code=400, detail="缺少 order_id")
    order = _accessible(db, user, order_id)
    text = str(order.requirement or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="该订单还没有需求书，请先生成或粘贴需求内容")
    _ai_guard(db, user, request, "review")

    metrics = _requirement_metrics(text)
    excerpt = text[:7000]
    system = (
        "你是资深软件项目需求评审专家，熟悉高校毕业设计交付。请严格依据给定需求书评审，不要编造需求书中不存在的内容。"
        "只输出 JSON，不要 Markdown 代码块。"
    )
    prompt = f"""订单题目：{order.title}
项目类型：{PROJECT_TYPE_LABEL.get(order.project_type, order.project_type or "未设置")}
需求书统计：{metrics['chars']} 字，{metrics['sections']} 个章节，{metrics['numbers']} 处量化描述，技术栈{'已写明' if metrics['has_tech'] else '未写明'}，验收/测试章节{'有' if metrics['has_acceptance'] else '缺失'}。

需求书正文：
{excerpt}

从以下 6 个维度各打 0-100 分并给一句具体点评：
clarity（目标与范围清晰）、completeness（功能/角色/数据完整）、tech（技术方案可落地）、
testability（验收标准可测试）、consistency（前后一致无矛盾）、delivery（交付物与文档明确）。
再列出最多 6 条最值得改的问题，按严重度排序，必须引用原文或指出缺失项。
输出 JSON：
{{
  "score": 0-100 综合分,
  "summary": "80 字内总体结论",
  "dimensions": [{{"key":"clarity","label":"目标清晰度","score":0,"comment":"..."}}],
  "issues": [{{"severity":"high|medium|low","title":"问题标题","detail":"问题说明","suggestion":"可直接采用的修改建议"}}],
  "highlights": ["做得好的地方，最多 3 条"]
}}"""
    raw = _ai_call(db, user, system, prompt, scene="ai_requirement_review", max_tokens=3000, temperature=0.25, order_id=order.id, json_mode=True)
    data = _parse_json(raw)
    dims = data.get("dimensions") if isinstance(data.get("dimensions"), list) else []
    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    if not dims:
        raise HTTPException(status_code=503, detail="AI 返回格式异常，请稍后重试")
    label_map = {
        "clarity": "目标清晰度", "completeness": "需求完整度", "tech": "技术可落地",
        "testability": "验收可测试", "consistency": "前后一致性", "delivery": "交付明确度",
    }
    clean_dims = []
    for d in dims[:6]:
        if not isinstance(d, dict):
            continue
        key = str(d.get("key") or "")
        try:
            sc = max(0, min(100, int(float(d.get("score") or 0))))
        except (TypeError, ValueError):
            sc = 0
        clean_dims.append({"key": key, "label": str(d.get("label") or label_map.get(key, key)), "score": sc, "comment": str(d.get("comment") or "")})
    if not clean_dims:
        raise HTTPException(status_code=503, detail="AI 返回格式异常，请稍后重试")
    clean_issues = []
    for it in issues[:6]:
        if not isinstance(it, dict):
            continue
        sev = it.get("severity") if it.get("severity") in ("high", "medium", "low") else "medium"
        clean_issues.append({
            "severity": sev, "title": str(it.get("title") or ""),
            "detail": str(it.get("detail") or ""), "suggestion": str(it.get("suggestion") or ""),
        })
    try:
        score = max(0, min(100, int(float(data.get("score") or 0))))
    except (TypeError, ValueError):
        score = round(sum(d["score"] for d in clean_dims) / len(clean_dims)) if clean_dims else 0
    log_op(db, "ai_requirement_review", request=request, user=user, detail={"order_id": order.id, "score": score})
    db.commit()
    return {
        "order_id": order.id, "title": order.title, "score": score,
        "summary": str(data.get("summary") or ""), "dimensions": clean_dims,
        "issues": clean_issues,
        "highlights": [str(x) for x in (data.get("highlights") or []) if str(x).strip()][:3],
        "metrics": metrics, "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.post("/reply")
def reply(body: dict, request: Request, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    body = body or {}
    order_id = str(body.get("order_id") or "").strip()
    if not order_id:
        raise HTTPException(status_code=400, detail="缺少 order_id")
    scene = str(body.get("scene") or "progress")
    if scene not in SCENE_LABEL:
        raise HTTPException(status_code=400, detail="不支持的回访场景")
    tone = str(body.get("tone") or "warm")
    if tone not in TONE_LABEL:
        raise HTTPException(status_code=400, detail="不支持的语气")
    order = _accessible(db, user, order_id)
    _ai_guard(db, user, request, "reply")

    notes = (
        db.query(OrderNote).filter(OrderNote.order_id == order.id)
        .order_by(OrderNote.created_at.desc()).limit(4).all()
    )
    files = (
        db.query(OrderFile).filter(OrderFile.order_id == order.id, OrderFile.is_deleted == False)  # noqa: E712
        .all()
    )
    progress = _progress_text(order)
    last_notes = "；".join(f"{n.username}：{(n.content or '')[:80]}" for n in notes) or "暂无"
    system = (
        "你是毕业设计接单团队的客户成功顾问。写真实、可发送的中文客户消息，不夸大承诺、不编造进度，"
        "不使用「亲」「宝子」等过度营销称呼。只输出 JSON，不要 Markdown 代码块。"
    )
    prompt = f"""订单：{order.id}「{order.title}」
状态：{STATUS_LABEL.get(order.status, order.status)}；进度：{progress}
交付期限：{order.deadline or "未设置"}；客户验收：{"已验收 " + str(order.customer_accepted_at) if order.customer_accepted_at else "未验收"}
文件：{len(files)} 个；最近跟进：{last_notes}
场景：{SCENE_LABEL[scene]}；语气：{TONE_LABEL[tone]}

要求：
- 可直接发微信，160 字以内，不要标题党；
- 必须包含一个明确的下一步或时间点；
- 风险/延期场景不许甩锅，先给方案；
- 不透露内部成本、真实价、毛利或其他订单信息。
输出 JSON：{{"message":"消息正文","tips":["沟通要点，最多 3 条"],"suggested_time":"建议发送时间，如 今天 18:00 前"}}"""
    message = ""
    data: dict = {}
    for attempt in range(2):
        ask = prompt if attempt == 0 else prompt + "\n\n上一次输出无法解析为 JSON。只输出一个合法 JSON 对象，不要解释，不要 Markdown 代码块。"
        raw = _ai_call(db, user, system, ask, scene="ai_reply_" + scene, max_tokens=1200, temperature=0.55, order_id=order.id, json_mode=True)
        data = _parse_json(raw)
        message = _reply_message(data, raw)
        if message:
            break
    if not message:
        raise HTTPException(status_code=503, detail="AI 返回格式异常，请稍后重试")
    tips = [str(x) for x in (data.get("tips") or []) if str(x).strip()][:3] if isinstance(data.get("tips"), list) else []
    log_op(db, "ai_reply", request=request, user=user, detail={"order_id": order.id, "scene": scene})
    db.commit()
    return {
        "order_id": order.id, "title": order.title, "scene": scene, "scene_label": SCENE_LABEL[scene],
        "tone": tone, "message": message, "tips": tips,
        "suggested_time": str(data.get("suggested_time") or ""),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.post("/acceptance")
def acceptance(body: dict, request: Request, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    order_id = str((body or {}).get("order_id") or "").strip()
    if not order_id:
        raise HTTPException(status_code=400, detail="缺少 order_id")
    order = _accessible(db, user, order_id)
    text = str(order.requirement or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="该订单还没有需求书，请先生成需求书")
    _ai_guard(db, user, request, "acceptance")
    files = (
        db.query(OrderFile).filter(OrderFile.order_id == order.id, OrderFile.is_deleted == False)  # noqa: E712
        .all()
    )
    file_desc = "、".join(f"{f.original_name}（{f.category}）" for f in files[:12]) or "暂无文件"
    system = (
        "你是交付验收负责人。根据需求书生成可直接照着执行的验收与测试清单，覆盖功能、数据、权限、"
        "兼容性、交付物与答辩演示。只输出中文 Markdown 列表，不要客套话，不要编造需求书之外的功能。"
    )
    prompt = f"""订单：{order.id}「{order.title}」
项目类型：{PROJECT_TYPE_LABEL.get(order.project_type, order.project_type or "未设置")}
已上传文件：{file_desc}
需求书：
{text[:6500]}

请输出：
## 一、交付物核对
## 二、核心功能验收
## 三、数据与权限
## 四、兼容性与演示
## 五、风险项与答辩备忘
每个章节 3-8 条，使用「- [ ] 」复选框；每条控制在 40 字内，尽量引用需求书中的模块名。"""
    markdown = _ai_call(db, user, system, prompt, scene="ai_acceptance", max_tokens=1800, temperature=0.3, order_id=order.id)
    log_op(db, "ai_acceptance", request=request, user=user, detail={"order_id": order.id})
    db.commit()
    return {
        "order_id": order.id, "title": order.title, "markdown": markdown.strip(),
        "file_count": len(files), "generated_at": datetime.now().isoformat(timespec="seconds"),
    }