"""毕设系统专属 AI Bot：知识问答 + 全系统 Agent 工具调用。

权限模型（双层，服务端强制）：
1. TOOL_CAPS 硬性角色上限 —— 代码级常量，任何配置都无法越权：
   - 代理（agent）永远无法获得 用户管理/订单修改/回收站 等工具
   - 写手（staff）永远无法 建单/管理用户
2. bot_permissions 设置（JSON：{"admin":[...],"staff":[...],"agent":[...]}）
   管理员可按角色进一步收窄（与硬上限取交集）；未配置 = 使用默认集。
   旧 bot_tools（全局白名单）仍然兼容：两者都取交集。

所有写操作记审计日志（log_op，action 前缀 ai_）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import AI_RATE_PER_MINUTE
from ..constants import CLOSED_STATUSES
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Announcement, Order, Quality, Suggestion, User
from ..ratelimit import client_ip, rate_limit
from ..services.notify_svc import notify_status_changed, push
from ..services.oplog import log_op
from ..services.order_svc import (
    can_access, can_change_status, can_download, create_order, normalize_project_type, order_query, order_view, set_order_status,
)
from ..services.pricing import compute_prices, get_quality_by_code
from ..services.settings_svc import get_setting

router = APIRouter(prefix="/api/chat", tags=["chat"])

STATUS_CN = {
    "pending": "待开始", "in_progress": "制作中", "completed": "已完成",
    "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消",
}
PROJECT_TYPE_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}

# 内置系统知识（管理员可在设置页追加自定义内容覆盖）
DEFAULT_KNOWLEDGE = """# 毕设接单管理系统知识库

## 系统定位
论文毕设接单的私人管理站点：订单全生命周期、需求书智能生成（Word）、程序包/演示视频管理、双价格体系、操作日志、数据看板与代理开放 API。

## 角色体系
- **管理员（平台）**：全权限，可见真实价与代理价，管理用户/品质/设置/备份
- **写手**：负责写程序/做单，只可见代理价，可拉取全部订单、回传制作状态、上传演示视频与交付包、编辑需求书
- **代理/销售**：前端对接客户，只可见代理价，可创建订单、查看下载需求书/视频/交付包、生成客户交付链接，不能修改订单

## 定价体系
- 品质分6档：白(×1)/绿(×2)/蓝(×3)/紫(×4)/橙(×5)/红(×6)
- 基础价：真实价基础300元，代理价基础50元
- 真实价 = 基础价 × 品质倍率（**仅管理员可见**）
- 代理价 = 50 × 品质倍率（写手/代理可见）
- 写手与代理端永不返回真实价、倍率或毛利

## 订单流转
待开始(pending) → 制作中(in_progress) → 已完成(completed) → 已结单(closed)，另有 售后中(after_sale)/已取消(cancelled)
部署状态：未部署(undeployed) / 已部署(deployed) / 无需部署(not_required)

## 核心功能
- 需求书：DeepSeek AI 一键生成九章结构化需求书，可在线编辑、导出 Word
- 演示视频/交付包：上传后自动生成缩略图，支持在线播放和免登录客户交付链接
- 撞单检测：创建订单时自动比对相似题目
- AI 经营报告：一键生成近7/30天分析报告
- 客户交付链接：免登录在线播放视频+下载交付包（HMAC签名，可设有效期）
- 客户报价单：免登录品质价格表
- 代理业绩榜：免登录月度排行+星级评定
- 经营数据大屏：免登录投影展示
- 收款凭证 PDF：一键生成正式收款凭证（含中文大写金额）
- 订单跟进时间线：与客户/团队的沟通记录
- 需求书修改对比：版本 diff + AI 总结
- 分片断点续传：大文件（GB级视频）上传
- 数据备份：一键 JSON 备份
- 建议反馈工单：代理提交建议/问题，后台与写手收到通知并可回复
- 站内私信：代理与平台/上下级互聊（WebSocket 实时）
- 客户验收：交付页「确认验收」留时间戳与 IP
- 公告管理：管理员发布系统公告，全员铃铛可见

## API 接口（/api/v1）
- GET /orders：拉取订单列表
- POST /orders：创建订单
- GET /orders/{id}：订单详情
- POST /orders/{id}/status：回传制作状态
- POST /orders/{id}/files：上传交付物（写手）
- GET /orders/{id}/requirement.docx：下载需求书
- GET /qualities：品质列表

## 常见问题
Q: 怎么创建订单？
A: 订单管理 → 新建订单，或直接让我（毕设助手）帮你建单。

Q: 怎么给客户交付？
A: 订单详情 → 文件 tab → 获取交付链接，发给客户即可免登录在线看视频/下载包。

Q: 写手怎么接单？
A: 写手在订单列表看到全部订单，进入详情可回传制作状态、上传视频和交付包。

Q: 怎么生成需求书？
A: 订单详情 → 需求书 tab → AI 智能生成或纯模板生成。

Q: 怎么导出对账单？
A: 订单中心 → 对账单，选月份查看/导出 CSV。
"""


class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


# ============================== 工具目录（全系统覆盖） ==============================

def _p(*props):
    return {"type": "object", "properties": dict(props)}


TOOL_CATALOG: list[dict] = [
    # ---------- 订单组 ----------
    {"name": "query_orders", "group": "订单", "caps": {"admin", "staff", "agent"},
     "desc": "搜索/筛选订单（关键词/状态/项目类型/品质）。代理只能查自己的单。",
     "params": _p(
         ("keyword", {"type": "string", "description": "题目关键词"}),
         ("status", {"type": "string", "enum": list(STATUS_CN)}),
         ("project_type", {"type": "string", "enum": list(PROJECT_TYPE_CN)}),
         ("limit", {"type": "integer", "description": "默认10，最大30"}),
     )},
    {"name": "get_order_detail", "group": "订单", "caps": {"admin", "staff", "agent"},
     "desc": "查单个订单详情（状态/品质/期限/文件数/跟进等）。",
     "params": _p(("order_id", {"type": "string"}),), "required": ["order_id"]},
    {"name": "create_order", "group": "订单", "caps": {"admin", "agent"},
     "desc": "创建新订单（管理员/代理）。返回订单号。",
     "params": _p(
         ("title", {"type": "string"}),
         ("price", {"type": "number", "description": "成交价（代理下单时自己应付的金额）；仅代理需要填"}),
         ("order_no", {"type": "string", "description": "自定义订单编号，留空自动生成；仅管理员，用于导入历史项目保留原编号"}),
         ("quality_code", {"type": "string", "enum": ["white", "green", "blue", "purple", "orange", "red"]}),
         ("project_type", {"type": "string", "enum": list(PROJECT_TYPE_CN)}),
         ("deadline", {"type": "string", "description": "YYYY-MM-DD"}),
         ("tech_stack", {"type": "string"}),
         ("customer_info", {"type": "string"}),
         ("remark", {"type": "string"}),
     ), "required": ["title"]},
    {"name": "update_order", "group": "订单", "caps": {"admin"},
     "desc": "修改订单信息（题目/期限/技术栈/客户信息/备注/品质重计价）。仅管理员。",
     "params": _p(
         ("order_id", {"type": "string"}),
         ("title", {"type": "string"}), ("deadline", {"type": "string", "description": "YYYY-MM-DD"}),
         ("tech_stack", {"type": "string"}), ("customer_info", {"type": "string"}),
         ("remark", {"type": "string"}),
         ("quality_code", {"type": "string", "enum": ["white", "green", "blue", "purple", "orange", "red"], "description": "改品质会按新倍率重算价格"}),
     ), "required": ["order_id"]},
    {"name": "update_order_status", "group": "订单", "caps": {"admin", "staff"},
     "desc": "改订单状态（制作中/已完成/结单/售后/取消）。管理员与写手。",
     "params": _p(("order_id", {"type": "string"}), ("new_status", {"type": "string", "enum": list(STATUS_CN)})),
     "required": ["order_id", "new_status"]},
    {"name": "assign_order", "group": "订单", "caps": {"admin"},
     "desc": "指派订单的来源代理或制作负责人（按用户名）。仅管理员。",
     "params": _p(("order_id", {"type": "string"}),
                  ("agent_username", {"type": "string", "description": "来源代理用户名"}),
                  ("assignee_username", {"type": "string", "description": "制作负责人（写手）用户名"})),
     "required": ["order_id"]},
    {"name": "trash_order", "group": "订单", "caps": {"admin"},
     "desc": "把订单移入回收站（软删除，可恢复）。仅管理员，敏感操作。",
     "params": _p(("order_id", {"type": "string"}),), "required": ["order_id"], "sensitive": True},
    {"name": "restore_order", "group": "订单", "caps": {"admin"},
     "desc": "从回收站恢复订单。仅管理员，敏感操作。",
     "params": _p(("order_id", {"type": "string"}),), "required": ["order_id"], "sensitive": True},
    {"name": "list_order_files", "group": "订单", "caps": {"admin", "staff", "agent"},
     "desc": "列订单附件（交付包/视频/文档）。代理仅限自己的单。",
     "params": _p(("order_id", {"type": "string"}),), "required": ["order_id"]},
    {"name": "get_deliver_link", "group": "订单", "caps": {"admin", "staff", "agent"},
     "desc": "生成客户交付链接（免登录看视频/下载包）。代理仅限自己的单。",
     "params": _p(("order_id", {"type": "string"}),), "required": ["order_id"]},
    # ---------- 统计与价格 ----------
    {"name": "get_stats", "group": "统计", "caps": {"admin", "staff", "agent"},
     "desc": "经营统计概览：各状态数量/本月新建完成/可见营收（按角色视野）。",
     "params": _p()},
    {"name": "list_qualities", "group": "统计", "caps": {"admin", "staff", "agent"},
     "desc": "品质档位与各角色可见价格。",
     "params": _p()},
    {"name": "get_settlement", "group": "统计", "caps": {"admin", "agent"},
     "desc": "对账单（默认本月）：代理看自己，管理员看全部汇总。格式 YYYY-MM。",
     "params": _p(("month", {"type": "string", "description": "YYYY-MM，默认当月"}),
                  ("agent_username", {"type": "string", "description": "仅管理员可指定代理"}))},
    # ---------- 用户管理（仅管理员，全部敏感） ----------
    {"name": "list_users", "group": "用户", "caps": {"admin"},
     "desc": "列系统用户（角色/上级/抽成/状态/API Key 状态）。仅管理员。",
     "params": _p(("role", {"type": "string", "enum": ["admin", "staff", "agent"]}))},
    {"name": "create_user", "group": "用户", "caps": {"admin"},
     "desc": "新建用户账号（仅限代理/写手，不能建管理员）。",
     "params": _p(
         ("username", {"type": "string"}), ("password", {"type": "string", "description": "至少6位"}),
         ("display_name", {"type": "string"}), ("role", {"type": "string", "enum": ["agent", "staff"]}),
         ("parent_username", {"type": "string", "description": "上级代理用户名（可选）"}),
         ("commission_rate", {"type": "number", "description": "给上级的抽成比例 0-100（可选）"}),
     ), "required": ["username", "password", "role"]},
    {"name": "update_user", "group": "用户", "caps": {"admin"},
     "desc": "修改用户（显示名/上级/抽成/启用停用）。仅管理员，敏感操作。",
     "params": _p(
         ("username", {"type": "string"}),
         ("display_name", {"type": "string"}),
         ("parent_username", {"type": "string", "description": "设为空字符串清除上级"}),
         ("commission_rate", {"type": "number"}),
         ("is_active", {"type": "boolean"}),
     ), "required": ["username"], "sensitive": True},
    {"name": "reset_api_key", "group": "用户", "caps": {"admin"},
     "desc": "重置某用户的 API Key（旧 Key 立即失效）。仅管理员，敏感操作。",
     "params": _p(("username", {"type": "string"}),), "required": ["username"], "sensitive": True},
    # ---------- 协作 ----------
    {"name": "list_suggestions", "group": "协作", "caps": {"admin", "staff", "agent"},
     "desc": "列建议/工单（代理看自己提交的，管理员/写手看全部）。",
     "params": _p(("status", {"type": "string", "enum": ["open", "processing", "resolved", "closed"]}))},
    {"name": "reply_suggestion", "group": "协作", "caps": {"admin", "staff"},
     "desc": "回复建议/工单（提交人会收到通知）。管理员/写手。",
     "params": _p(("suggestion_id", {"type": "integer"}), ("reply", {"type": "string"}),
                  ("status", {"type": "string", "enum": ["open", "processing", "resolved", "closed"]})),
     "required": ["suggestion_id", "reply"]},
    {"name": "list_announcements", "group": "协作", "caps": {"admin", "staff", "agent"},
     "desc": "列系统公告。",
     "params": _p(("limit", {"type": "integer", "description": "默认5"}))},
    {"name": "publish_announcement", "group": "协作", "caps": {"admin"},
     "desc": "发布系统公告（全员可见）。仅管理员，敏感操作。",
     "params": _p(("title", {"type": "string"}), ("content", {"type": "string"}),
                  ("level", {"type": "string", "enum": ["info", "warning", "important"]})),
     "required": ["title", "content"], "sensitive": True},
]

TOOL_CAPS = {t["name"]: t["caps"] for t in TOOL_CATALOG}
SENSITIVE_TOOLS = {t["name"] for t in TOOL_CATALOG if t.get("sensitive")}

# 各角色默认工具（未配置 bot_permissions 时）
DEFAULT_ROLE_TOOLS = {
    "admin": {t["name"] for t in TOOL_CATALOG},
    "staff": {"query_orders", "get_order_detail", "update_order_status", "list_order_files",
              "get_stats", "list_qualities", "list_suggestions", "reply_suggestion", "list_announcements"},
    "agent": {"query_orders", "get_order_detail", "create_order", "list_order_files",
              "get_deliver_link", "get_stats", "list_qualities", "get_settlement",
              "list_suggestions", "list_announcements"},
}

MAX_TOOL_ROUNDS = 5


def allowed_tools_for(db: Session, role: str) -> set[str]:
    """双层权限：角色硬上限 ∩ 管理员配置（bot_permissions，兼容旧 bot_tools）。"""
    caps = TOOL_CAPS.keys() if role == "admin" else {
        n for n, roles in TOOL_CAPS.items() if role in roles
    }
    allowed = set(DEFAULT_ROLE_TOOLS.get(role, set())) & caps

    raw = (get_setting(db, "bot_permissions") or "").strip()
    if raw:
        try:
            conf = json.loads(raw)
            per_role = conf.get(role)
            if isinstance(per_role, list) and per_role:
                # 只收窄：配置只能从角色默认集合里减，不能借 caps 加回默认未开放的工具。
                allowed &= {n for n in per_role if n in caps}
        except (ValueError, TypeError):
            pass
    # 兼容旧全局白名单
    legacy = (get_setting(db, "bot_tools") or "").strip()
    if legacy:
        try:
            lg = json.loads(legacy)
            if isinstance(lg, list) and lg:
                allowed &= {n for n in lg if n in caps}
        except (ValueError, TypeError):
            pass
    return allowed


# ============================== 工具实现 ==============================

def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _get_user_by_name(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == (username or "").strip()).first()


def _brief_order(o: Order, role: str) -> dict:
    v = order_view(o, role)
    item = {
        "id": v["id"], "title": v["title"], "status": STATUS_CN.get(o.status, o.status),
        "project_type": PROJECT_TYPE_CN.get(o.project_type, o.project_type or "未设置"), "quality": v["quality"]["name"],
        **({"owner_price": v["owner_price"]} if "owner_price" in v else {}),
        **({"agent_price": v["agent_price"]} if "agent_price" in v else {}),
        "deadline": str(o.deadline) if o.deadline else None,
    }
    return item


def _tool_query_orders(db, user, args):
    q = order_query(db)
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    kw = (args.get("keyword") or "").strip()
    if kw:
        q = q.filter(Order.title.contains(kw))
    if args.get("status") in STATUS_CN:
        q = q.filter(Order.status == args["status"])
    if args.get("project_type") in PROJECT_TYPE_CN:
        q = q.filter(Order.project_type == args["project_type"])
    try:
        limit = min(max(int(args.get("limit") or 10), 1), 30)
    except (TypeError, ValueError):
        limit = 10
    rows = q.order_by(Order.created_at.desc()).limit(limit).all()
    return {"total": q.count(), "returned": len(rows),
            "orders": [_brief_order(o, user.role) for o in rows]}


def _tool_get_order_detail(db, user, args):
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or (order.is_deleted and user.role != "admin") or not can_access(order, user):
        return {"error": f"订单 {oid} 不存在或无权访问"}
    from ..models import OrderFile
    files = db.query(OrderFile).filter(OrderFile.order_id == oid, OrderFile.is_deleted == False).count()  # noqa: E712
    v = order_view(order, user.role)
    out = {
        "id": v["id"], "title": v["title"], "status": STATUS_CN.get(order.status, order.status),
        "deploy_status": {"undeployed": "未部署", "deployed": "已部署", "not_required": "无需部署"}.get(order.deploy_status, order.deploy_status),
        "project_type": PROJECT_TYPE_CN.get(order.project_type, order.project_type or "未设置"), "quality": v["quality"]["name"],
        **({"owner_price": v["owner_price"]} if "owner_price" in v else {}),
        **({"agent_price": v["agent_price"]} if "agent_price" in v else {}),
        "deadline": str(order.deadline) if order.deadline else None,
        "tech_stack": order.tech_stack, "customer_info": order.customer_info, "remark": order.remark,
        "agent": v["agent"]["display_name"] if v["agent"] else None,
        "assignee": v["assignee"]["display_name"] if v["assignee"] else None,
        "files_count": files, "has_requirement": v["has_requirement"],
        "customer_accepted": bool(order.customer_accepted_at),
    }
    if "owner_price" in v:
        out["owner_price"] = v["owner_price"]
    return out


def _tool_create_order(db, user, args, request):
    title = (args.get("title") or "").strip()
    if not title:
        return {"error": "题目不能为空"}
    quality_code = args.get("quality_code") or "white"
    if not get_quality_by_code(db, quality_code):
        return {"error": f"品质 {quality_code} 不存在"}
    try:
        order = create_order(
            db, title=title, quality_code=quality_code, creator=user,
            agent_user=user if user.role == "agent" else None,
            project_type=normalize_project_type(args.get("project_type"), args.get("category")),
            deadline=_parse_date(args.get("deadline")),
            tech_stack=args.get("tech_stack"), customer_info=args.get("customer_info"),
            # 自定义编号仅管理员可让 AI 指定（导入历史项目场景）
            order_no=(args.get("order_no") or "").strip() or None if user.role == "admin" else None,
            # 代理（销售/同行）经 AI 建单时填自己应付的成交价
            owner_price_override=(
                float(args.get("price") or args.get("owner_price") or 0) or None
                if user.role == "agent" else None
            ),
            remark=args.get("remark"),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    log_op(db, "ai_create_order", request=request, user=user, entity_id=order.id,
           detail={"title": title, "quality": quality_code})
    push(db, [order.created_by] if order.agent_user_id and order.agent_user_id != user.id else [],
         f"订单 {order.id} 已由 AI 创建", body=title, order_id=order.id)
    v = order_view(order, user.role)
    out = {"success": True, "order_id": order.id, "title": order.title,
           "quality": v["quality"]["name"], "status": "待开始",
           **({"owner_price": v["owner_price"]} if "owner_price" in v else {}),
           **({"agent_price": v["agent_price"]} if "agent_price" in v else {})}
    return out


def _tool_update_order(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可修改订单信息"}
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or order.is_deleted:
        return {"error": f"订单 {oid} 不存在"}
    changes: dict = {}
    for field, col in (("title", "title"), ("tech_stack", "tech_stack"),
                       ("customer_info", "customer_info"), ("remark", "remark")):
        if args.get(field) is not None:
            changes[col] = args[field]
    if args.get("deadline"):
        dl = _parse_date(args["deadline"])
        if dl is None:
            return {"error": f"截止日期「{args['deadline']}」无法识别，请用 YYYY-MM-DD 格式"}
        changes["deadline"] = dl
    if args.get("quality_code"):
        # 换品质会重算两侧价格（等价于改 owner_price），与 REST 接口保持一致：必须密码确认
        from ..security import verify_password

        pwd = request.headers.get("x-confirm-password", "")
        if not pwd or not verify_password(pwd, user.password_hash):
            return {"error": "调整品质会重算订单价格，请到订单详情页修改（需输入登录密码确认）"}
        q = get_quality_by_code(db, args["quality_code"])
        if not q:
            return {"error": f"品质 {args['quality_code']} 不存在"}
        from decimal import Decimal

        owner_price, agent_price, mult = compute_prices(db, q)
        changes.update({"quality_id": q.id, "multiplier": mult,
                        "owner_price": owner_price, "agent_price": agent_price})
    if not changes:
        return {"error": "没有可更新字段"}
    for k, v in changes.items():
        setattr(order, k, v)
    log_op(db, "ai_update_order", request=request, user=user, entity_id=oid,
           detail={"fields": list(changes.keys())})
    return {"success": True, "order_id": oid, "updated_fields": list(changes.keys())}


def _tool_update_order_status(db, user, args, request):
    if user.role not in ("admin", "staff"):
        return {"error": "无权修改订单状态"}
    oid = (args.get("order_id") or "").strip()
    new_status = args.get("new_status")
    if new_status not in STATUS_CN:
        return {"error": f"非法状态: {new_status}"}
    order = db.get(Order, oid)
    if not order or order.is_deleted:
        return {"error": f"订单 {oid} 不存在"}
    if not can_change_status(order, user, new_status):
        return {"error": "无权把该订单推进到此状态（写手仅可开始制作/标记完成）"}
    try:
        changed = set_order_status(order, new_status, allow_any=True)  # 权限已由 can_change_status 校验
    except ValueError as exc:
        return {"error": str(exc)}
    if not changed:
        return {"success": True, "order_id": oid, "status": STATUS_CN[new_status], "changed": False}
    log_op(db, "ai_update_status", request=request, user=user, entity_id=oid, detail={"status": new_status})
    notify_status_changed(db, order, user.id, new_status)
    return {"success": True, "order_id": oid, "status": STATUS_CN[new_status], "title": order.title, "changed": True}


def _tool_assign_order(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可指派订单"}
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or order.is_deleted:
        return {"error": f"订单 {oid} 不存在"}
    assigned = []
    if args.get("agent_username") is not None:
        au = _get_user_by_name(db, args["agent_username"])
        if not au or au.role != "agent" or not au.is_active:
            return {"error": f"代理 {args['agent_username']} 不存在或已停用"}
        order.agent_user_id = au.id
        assigned.append(f"代理={au.username}")
    if args.get("assignee_username") is not None:
        su = _get_user_by_name(db, args["assignee_username"])
        if not su or su.role not in ("staff", "admin") or not su.is_active:
            return {"error": f"写手 {args['assignee_username']} 不存在或已停用"}
        order.assignee_user_id = su.id
        assigned.append(f"负责人={su.username}")
    if not assigned:
        return {"error": "未指定 agent_username 或 assignee_username"}
    log_op(db, "ai_assign_order", request=request, user=user, entity_id=oid, detail={" | ".join(assigned): True})
    push(db, [u for u in (order.agent_user_id, order.assignee_user_id) if u and u != user.id],
         f"订单 {oid} 已指派（AI 操作）", body=order.title, order_id=oid)
    return {"success": True, "order_id": oid, "assigned": assigned}


def _tool_trash_order(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可删除订单"}
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or order.is_deleted:
        return {"error": f"订单 {oid} 不存在或已在回收站"}
    order.is_deleted = True
    log_op(db, "ai_trash_order", request=request, user=user, entity_id=oid, detail={"title": order.title})
    return {"success": True, "order_id": oid, "note": "已移入回收站，可恢复"}


def _tool_restore_order(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可恢复订单"}
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or not order.is_deleted:
        return {"error": f"订单 {oid} 不在回收站"}
    order.is_deleted = False
    log_op(db, "ai_restore_order", request=request, user=user, entity_id=oid, detail={})
    return {"success": True, "order_id": oid, "note": "已恢复"}


def _tool_list_order_files(db, user, args):
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or order.is_deleted or not can_access(order, user):
        return {"error": f"订单 {oid} 不存在或无权访问"}
    from ..models import OrderFile
    from ..services.order_svc import file_view
    rows = db.query(OrderFile).filter(OrderFile.order_id == oid, OrderFile.is_deleted == False).all()  # noqa: E712
    return {"order_id": oid, "files": [
        {"id": f.id, "name": f.original_name, "category": f.category,
         "size_mb": round(f.size / 1048576, 1), "remark": f.remark} for f in rows]}


def _tool_get_deliver_link(db, user, args, request):
    oid = (args.get("order_id") or "").strip()
    order = db.get(Order, oid)
    if not order or order.is_deleted or not can_download(order, user):
        return {"error": f"订单 {oid} 不存在或无权获取交付链接"}
    from ..services.deliver import make_token
    token = make_token(oid, order.deliver_token_version)
    log_op(db, "ai_deliver_link", request=request, user=user, entity_id=oid, detail={})
    return {"order_id": oid, "url": f"/deliver/{token}",
            "note": "免登录客户交付页：在线看视频+下载交付包"}


def _tool_get_stats(db, user):
    """订单统计：SQL 聚合 + 最近 365 天时间窗 + 单次 LIMIT，避免全表加载。"""
    from sqlalchemy import case as sa_case, func as sa_func

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    since = now - timedelta(days=365)
    price_col = Order.agent_price if user.role == "staff" else Order.owner_price

    filters = [Order.is_deleted == False, Order.created_at >= since]  # noqa: E712
    if user.role == "agent":
        filters.append(Order.agent_user_id == user.id)

    rows = (
        db.query(
            Order.status,
            sa_func.count().label("total"),
            sa_func.sum(sa_case((Order.created_at >= month_start, 1), else_=0)).label("month_new"),
            sa_func.sum(sa_case((Order.completed_at >= month_start, 1), else_=0)).label("month_done"),
            sa_func.sum(sa_case((Order.status.in_(CLOSED_STATUSES), price_col), else_=0)).label("revenue"),
        )
        .filter(*filters)
        .group_by(Order.status)
        .all()
    )
    by_status: dict[str, int] = {}
    total = month_new = month_done = 0
    revenue = 0.0
    for status, count, new_cnt, done_cnt, rev in rows:
        by_status[status] = int(count or 0)
        total += int(count or 0)
        month_new += int(new_cnt or 0)
        month_done += int(done_cnt or 0)
        revenue += float(rev or 0)
    recent_rows = (
        db.query(Order.id, Order.title, Order.status)
        .filter(*filters)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(5)
        .all()
    )
    recent = [{"id": oid, "title": title, "status": STATUS_CN.get(status, status)}
              for oid, title, status in recent_rows]
    return {
        "total": total,
        "by_status": {STATUS_CN.get(k, k): v for k, v in by_status.items()},
        "month_new": month_new, "month_done": month_done,
        "closed_revenue": round(revenue, 2) if user.role == "admin" else None,
        "revenue_field": "已结单真实价合计（仅管理员）" if user.role == "admin" else None,
        "recent_5": recent, "generated_at": now.strftime("%Y-%m-%d %H:%M"),
    }


def _tool_list_qualities(db, user):
    qualities = db.query(Quality).filter(Quality.enabled == True).order_by(Quality.sort).all()  # noqa: E712
    items = []
    for q in qualities:
        owner_p, agent_p, mult = compute_prices(db, q)
        item = {"code": q.code, "name": q.name, "color": q.color}
        if user.role == "admin":
            item["multiplier"] = float(mult)
            item["owner_price"] = float(owner_p)
            item["agent_price"] = float(agent_p)
        elif user.role == "staff":
            item["agent_price"] = float(agent_p)
        elif user.role == "agent":
            item["owner_price"] = float(owner_p)
        items.append(item)
    return {"qualities": items,
            "note": "owner_price 仅管理员可见；agent_price 为写手/代理价格口径"}


def _tool_get_settlement(db, user, args):
    from ..routers.stats import _month_range

    month = (args.get("month") or datetime.now().strftime("%Y-%m")).strip()
    try:
        start, end = _month_range(month)
    except Exception:  # noqa: BLE001
        return {"error": f"月份格式应为 YYYY-MM"}
    q = order_query(db).filter(Order.status.in_(CLOSED_STATUSES), Order.closed_at >= start, Order.closed_at < end)
    agents_scope: list[User]
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
        agents_scope = [user]
    else:
        if args.get("agent_username"):
            au = _get_user_by_name(db, args["agent_username"])
            if not au or au.role != "agent":
                return {"error": f"代理 {args['agent_username']} 不存在"}
            q = q.filter(Order.agent_user_id == au.id)
            agents_scope = [au]
        else:
            agents_scope = db.query(User).filter(User.role == "agent").all()
    orders = q.all()
    own = {a.id: {"name": a.display_name or a.username, "count": 0, "total": 0.0} for a in agents_scope}
    for o in orders:
        if o.agent_user_id in own:
            own[o.agent_user_id]["count"] += 1
            own[o.agent_user_id]["total"] += float(o.agent_price if user.role == "staff" else o.owner_price)
    return {"month": month,
            "agents": [{"name": v["name"], "closed": v["count"], "amount": round(v["total"], 2)}
                       for v in own.values() if v["count"]],
            "note": "金额口径随角色：管理员为真实价，代理为代理价"}


def _tool_list_users(db, user, args):
    if user.role != "admin":
        return {"error": "仅管理员可查看用户列表"}
    q = db.query(User)
    if args.get("role") in ("admin", "staff", "agent"):
        q = q.filter(User.role == args["role"])
    rows = q.order_by(User.id).limit(50).all()
    return {"users": [{
        "username": u.username, "display_name": u.display_name, "role": u.role,
        "is_active": u.is_active, "has_api_key": bool(u.api_key),
        "last_login_at": str(u.last_login_at)[:16] if u.last_login_at else None,
    } for u in rows]}


def _tool_create_user(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可创建用户"}
    username = (args.get("username") or "").strip()
    password = args.get("password") or ""
    role = args.get("role")
    import re

    if not username or len(password) < 6:
        return {"error": "用户名必填，密码至少 6 位"}
    if not re.fullmatch(r"[A-Za-z0-9_\-]{2,50}", username):
        return {"error": "用户名只能包含字母/数字/下划线/短横线（2-50 位）"}
    if role not in ("agent", "staff"):
        return {"error": "AI 只能创建代理或写手账号（admin 请在后台手动建）"}
    if _get_user_by_name(db, username):
        return {"error": f"用户名 {username} 已存在"}
    from ..security import hash_password

    parent = None
    if role == "agent" and args.get("parent_username"):
        parent = _get_user_by_name(db, args["parent_username"])
        if not parent or parent.role != "agent" or not parent.is_active:
            return {"error": f"上级代理 {args['parent_username']} 不存在或已停用"}
    try:
        rate = max(0.0, min(float(args.get("commission_rate") or 0), 100.0))
        password_hash = hash_password(password)
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}
    u = User(username=username, password_hash=password_hash,
             display_name=(args.get("display_name") or username)[:50], role=role,
             parent_id=parent.id if parent else None,
             commission_rate=rate if role == "agent" else 0)
    db.add(u)
    db.flush()
    log_op(db, "ai_create_user", request=request, user=user, entity_id=u.id,
           detail={"username": username, "role": role})
    return {"success": True, "username": username, "role": role,
            "parent": parent.username if parent else None}


def _tool_update_user(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可修改用户"}
    target = _get_user_by_name(db, args.get("username") or "")
    if not target:
        return {"error": f"用户 {args.get('username')} 不存在"}
    changes = []
    if args.get("display_name") is not None:
        target.display_name = args["display_name"][:50]
        changes.append("display_name")
    if args.get("parent_username") is not None:
        if target.role != "agent":
            return {"error": "只有代理角色可以设置上级"}
        pn = args["parent_username"].strip()
        if pn == "":
            target.parent_id = None
            changes.append("parent=清除")
        else:
            parent = _get_user_by_name(db, pn)
            if not parent or parent.role != "agent" or not parent.is_active or parent.id == target.id:
                return {"error": f"上级代理 {pn} 无效"}
            # 防止上下级成环
            cursor, depth = parent, 0
            while cursor is not None and depth < 10:
                if cursor.id == target.id:
                    return {"error": "不能形成上级代理循环"}
                cursor = db.get(User, cursor.parent_id) if cursor.parent_id else None
                depth += 1
            target.parent_id = parent.id
            changes.append(f"parent={pn}")
    if args.get("commission_rate") is not None:
        if target.role != "agent":
            return {"error": "只有代理角色可以设置抽成"}
        try:
            rate = max(0.0, min(float(args["commission_rate"]), 100.0))
        except (TypeError, ValueError):
            return {"error": "抽成比例应为 0-100 数字"}
        target.commission_rate = rate
        changes.append("commission_rate")
    if args.get("is_active") is not None:
        if target.id == user.id and args["is_active"] is False:
            return {"error": "不能停用自己"}
        if target.is_active and not args["is_active"]:
            target.token_version = int(target.token_version or 0) + 1
            if target.api_key:
                from ..security import gen_api_key
                target.api_key = gen_api_key()
                changes.append("api_key=rotated")
            from ..ws import queue_ws_event
            queue_ws_event(db, [target.id], {"type": "force_logout", "message": "账号已被停用"})
        target.is_active = bool(args["is_active"])
        changes.append("is_active")
    if not changes:
        return {"error": "没有可更新字段"}
    log_op(db, "ai_update_user", request=request, user=user, entity_id=target.id, detail={"changes": changes})
    return {"success": True, "username": target.username, "updated": changes}


def _tool_reset_api_key(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可重置 API Key"}
    target = _get_user_by_name(db, args.get("username") or "")
    if not target:
        return {"error": f"用户 {args.get('username')} 不存在"}
    from ..security import gen_api_key

    target.api_key = gen_api_key()
    log_op(db, "ai_reset_api_key", request=request, user=user, entity_id=target.id,
           detail={"username": target.username})
    return {"success": True, "username": target.username, "new_api_key": target.api_key,
            "note": "旧 Key 已失效，请通知用户更新"}


def _tool_list_suggestions(db, user, args):
    q = db.query(Suggestion)
    if user.role == "agent":
        q = q.filter(Suggestion.user_id == user.id)
    if args.get("status") in ("open", "processing", "resolved", "closed"):
        q = q.filter(Suggestion.status == args["status"])
    rows = q.order_by(Suggestion.created_at.desc()).limit(20).all()
    return {"suggestions": [{
        "id": s.id, "order_id": s.order_id, "username": s.username, "kind": s.kind,
        "status": s.status, "content": (s.content or "")[:80],
        "reply": (s.reply or "")[:60], "created_at": str(s.created_at)[:16],
    } for s in rows]}


def _tool_reply_suggestion(db, user, args, request):
    if user.role not in ("admin", "staff"):
        return {"error": "仅管理员/写手可回复建议"}
    try:
        sid = int(args.get("suggestion_id"))
    except (TypeError, ValueError):
        return {"error": "suggestion_id 应为数字"}
    s = db.get(Suggestion, sid)
    if not s:
        return {"error": f"建议 #{sid} 不存在"}
    reply = (args.get("reply") or "").strip()
    if not reply:
        return {"error": "回复内容不能为空"}
    s.reply = reply
    s.replied_by = user.display_name or user.username
    s.replied_at = datetime.now()
    if args.get("status") in ("open", "processing", "resolved", "closed"):
        s.status = args["status"]
    push(db, [s.user_id], f"你的建议 #{s.id} 已回复（AI 转达）", body=reply[:200], order_id=s.order_id)
    log_op(db, "ai_reply_suggestion", request=request, user=user, entity_id=s.id, detail={})
    return {"success": True, "suggestion_id": sid, "status": s.status}


def _tool_list_announcements(db, user, args):
    try:
        limit = min(max(int(args.get("limit") or 5), 1), 20)
    except (TypeError, ValueError):
        limit = 5
    rows = (db.query(Announcement)
            .filter(Announcement.is_published == True)  # noqa: E712
            .order_by(Announcement.created_at.desc()).limit(limit).all())
    return {"announcements": [{
        "id": a.id, "title": a.title, "level": a.level,
        "content": (a.content or "")[:120], "created_at": str(a.created_at)[:16],
    } for a in rows]}


def _tool_publish_announcement(db, user, args, request):
    if user.role != "admin":
        return {"error": "仅管理员可发布公告"}
    title = (args.get("title") or "").strip()
    content = (args.get("content") or "").strip()
    if not title or not content:
        return {"error": "标题和内容必填"}
    level = args.get("level") if args.get("level") in ("info", "warning", "important") else "info"
    a = Announcement(title=title[:120], content=content[:2000], level=level,
                     created_by=user.id, is_published=True)
    db.add(a)
    db.flush()
    targets = [u.id for u in db.query(User.id).filter(User.is_active == True, User.id != user.id).all()]  # noqa: E712
    push(db, targets, f"📢 新公告：{title[:60]}", body=content[:200])
    log_op(db, "ai_publish_announcement", request=request, user=user, entity_id=a.id, detail={"level": level})
    return {"success": True, "id": a.id, "title": a.title}


# 会产生写操作的工具：执行成功后立刻落库，避免后续 LLM 回合失败时
# 已经把「已创建 / 已修改」告诉用户、数据库里却没有（get_db 只 close 不 commit，等于静默回滚）。
WRITE_TOOLS = {
    "create_order", "update_order", "update_order_status", "assign_order",
    "trash_order", "restore_order", "create_user", "update_user",
    "reset_api_key", "reply_suggestion", "publish_announcement",
}


def execute_tool(name: str, args: dict, user: User, db: Session, request: Request) -> dict:
    """执行一个工具调用：敏感工具要求密码确认，失败回滚到保存点，避免部分修改残留。"""
    if name in SENSITIVE_TOOLS:
        from ..security import verify_password

        pwd = request.headers.get("x-confirm-password", "")
        if not pwd or not verify_password(pwd, user.password_hash):
            return {"error": "该操作涉及敏感数据，请在对应页面完成（需输入登录密码确认）"}

    events = db.info.get("_ws_events", [])
    event_mark = len(events)
    sp = db.begin_nested()
    try:
        if name == "query_orders":
            result = _tool_query_orders(db, user, args)
        elif name == "get_order_detail":
            result = _tool_get_order_detail(db, user, args)
        elif name == "create_order":
            result = _tool_create_order(db, user, args, request)
        elif name == "update_order":
            result = _tool_update_order(db, user, args, request)
        elif name == "update_order_status":
            result = _tool_update_order_status(db, user, args, request)
        elif name == "assign_order":
            result = _tool_assign_order(db, user, args, request)
        elif name == "trash_order":
            result = _tool_trash_order(db, user, args, request)
        elif name == "restore_order":
            result = _tool_restore_order(db, user, args, request)
        elif name == "list_order_files":
            result = _tool_list_order_files(db, user, args)
        elif name == "get_deliver_link":
            result = _tool_get_deliver_link(db, user, args, request)
        elif name == "get_stats":
            result = _tool_get_stats(db, user)
        elif name == "list_qualities":
            result = _tool_list_qualities(db, user)
        elif name == "get_settlement":
            result = _tool_get_settlement(db, user, args)
        elif name == "list_users":
            result = _tool_list_users(db, user, args)
        elif name == "create_user":
            result = _tool_create_user(db, user, args, request)
        elif name == "update_user":
            result = _tool_update_user(db, user, args, request)
        elif name == "reset_api_key":
            result = _tool_reset_api_key(db, user, args, request)
        elif name == "list_suggestions":
            result = _tool_list_suggestions(db, user, args)
        elif name == "reply_suggestion":
            result = _tool_reply_suggestion(db, user, args, request)
        elif name == "list_announcements":
            result = _tool_list_announcements(db, user, args)
        elif name == "publish_announcement":
            result = _tool_publish_announcement(db, user, args, request)
        else:
            result = {"error": f"未知工具 {name}"}
        if isinstance(result, dict) and result.get("error"):
            sp.rollback()
            del events[event_mark:]
        else:
            sp.commit()
            if name in WRITE_TOOLS:
                db.commit()
        return result
    except Exception as exc:  # noqa: BLE001 —— 工具失败不炸对话，交给模型向用户解释
        try:
            sp.rollback()
        except Exception:  # noqa: BLE001
            pass
        del events[event_mark:]
        return {"error": f"工具执行失败: {exc}"}


def tool_summary(name: str, args: dict, result: dict) -> str:
    ok = not result.get("error")
    if name in ("create_order", "create_user") and ok:
        key = "order_id" if name == "create_order" else "username"
        return f"已创建 {result.get(key, '')}"
    if name in ("update_order", "update_user") and ok:
        return f"已更新 {result.get('order_id') or result.get('username', '')}"
    if name == "update_order_status" and ok:
        return f"订单 {result.get('order_id')} → {result.get('status')}"
    if name == "assign_order" and ok:
        return f"已指派 {result.get('order_id')}"
    if name == "trash_order" and ok:
        return f"{result.get('order_id')} 移入回收站"
    if name == "restore_order" and ok:
        return f"{result.get('order_id')} 已恢复"
    if name == "reset_api_key" and ok:
        return f"已重置 {result.get('username')} 的 Key"
    if name == "reply_suggestion" and ok:
        return f"已回复建议 #{result.get('suggestion_id')}"
    if name == "publish_announcement" and ok:
        return f"已发布公告「{result.get('title', '')[:16]}」"
    if name == "get_deliver_link" and ok:
        return f"已生成 {result.get('order_id')} 交付链接"
    if not ok:
        return "操作失败"
    if name == "query_orders":
        return f"查询订单（命中 {result.get('total', 0)} 条）"
    if name == "get_order_detail":
        return f"查询订单 {args.get('order_id', '')}"
    if name == "get_stats":
        return "获取经营统计"
    if name == "list_qualities":
        return "查询品质价格"
    if name == "get_settlement":
        return "查询对账单"
    return name


# ============================== 端点 ==============================

@router.get("/builtin-knowledge")
def builtin_knowledge(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """内置知识库只读视图（AI 中心查阅用）。"""
    custom = get_setting(db, "bot_knowledge")
    return {"knowledge": DEFAULT_KNOWLEDGE, "customized": bool(custom and custom.strip())}


@router.get("/tools")
def list_tools(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """工具目录 + 各角色硬上限 + 当前生效权限（AI 中心权限矩阵用）。"""
    allowed = allowed_tools_for(db, user.role)
    return {
        "catalog": [
            {"name": t["name"], "group": t["group"], "desc": t["desc"],
             "caps": sorted(t["caps"]), "sensitive": bool(t.get("sensitive"))}
            for t in TOOL_CATALOG
        ],
        "role_defaults": {r: sorted(v & {n for n, caps in TOOL_CAPS.items() if r in caps})
                          for r, v in DEFAULT_ROLE_TOOLS.items()},
        "my_allowed": sorted(allowed),
    }


@router.post("")
def chat(
    body: ChatIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI Bot 对话：知识问答 + 全系统工具调用（双层权限约束）。"""
    from ..services.docgen.ai import AIGenerationError, deepseek_raw

    rate_limit(request, "ai_chat", f"{user.id}:{client_ip(request)}", limit=AI_RATE_PER_MINUTE, window_seconds=60)
    from ..services.ai_quota import ensure_ai_quota

    ensure_ai_quota(db, user.id)
    if not body.messages:
        raise HTTPException(status_code=400, detail="消息不能为空")

    custom = get_setting(db, "bot_knowledge")
    knowledge = custom.strip() if custom and custom.strip() else DEFAULT_KNOWLEDGE

    allowed = allowed_tools_for(db, user.role)
    tool_names = ", ".join(sorted(allowed)) if allowed else "无"
    today = datetime.now().strftime("%Y年%m月%d日")

    custom_prefix = (get_setting(db, "bot_system_prompt") or "").strip()

    system_prompt = (
        (custom_prefix + "\n\n" if custom_prefix else "")
        + "你是「毕设助手」，毕设接单管理系统的专属 AI 机器人，兼具知识问答与业务操作能力。\n"
        f"当前登录用户：{user.display_name or user.username}，角色：{user.role}，今天：{today}。\n\n"
        "## 回答要求\n"
        "1. 基于知识库与工具返回的真实数据回答，不知道就说不知道，不要编造订单号/用户名和数字\n"
        "2. 回答简洁实用，使用 Markdown 格式（列表、加粗、表格都可以）\n"
        "3. 涉及操作步骤时给出具体路径；执行了工具操作时明确告知结果（如订单号/新账号名）\n"
        "4. 用中文回答\n"
        "5. 价格视野：只能提及工具结果里返回的价格字段，不要猜测另一侧价格\n"
        "6. 创建账号等敏感操作成功后，提醒用户妥善保存初始密码\n\n"
        "## 可用工具\n"
        f"{tool_names}\n"
        "用户表达业务意图（查/建/改/删/指派/发布等）时主动调用对应工具完成操作，不要只教他手动去做；"
        "无权限的工具会返回错误，向用户解释权限限制即可，不要尝试绕过。\n\n"
        f"# 系统知识库\n{knowledge}"
    )

    chat_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in body.messages:
        chat_messages.append({"role": m.role, "content": m.content})

    tools = [
        {"type": "function", "function": {
            "name": t["name"], "description": t["desc"], "parameters": t["params"],
            **({"required": t["required"]} if t.get("required") else {}),
        }}
        for t in TOOL_CATALOG if t["name"] in allowed
    ] or None
    actions: list[dict] = []

    try:
        reply = ""
        for _ in range(MAX_TOOL_ROUNDS + 1):
            msg = deepseek_raw(db, chat_messages, tools=tools, max_tokens=2048, temperature=0.7,
                               scene="chat", user_id=user.id)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                reply = msg.get("content") or ""
                break

            chat_messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = {}
                if name not in allowed:  # 双保险：模型伪造的工具名直接拒绝
                    result = {"error": f"工具 {name} 不在当前角色可用范围"}
                else:
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError:
                        args = {}
                    result = execute_tool(name, args, user, db, request)
                actions.append({
                    "name": name, "args": args,
                    "summary": tool_summary(name, args, result),
                    "ok": not result.get("error"),
                })
                chat_messages.append({
                    "role": "tool", "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:6000],
                })
            if len(actions) >= 8:
                chat_messages.append({"role": "user", "content": "（工具调用次数已达上限，请基于现有结果直接回答）"})
        if not reply:
            reply = "（操作已完成，如需查看结果请刷新页面）"
    except AIGenerationError as exc:
        # 已经执行成功的工具操作（上面每个写工具执行完都会 commit）不再回滚，
        # 这里只做一次显式收尾，确保没有半开的隐式事务。
        db.commit()
        raise HTTPException(status_code=503, detail=f"AI 暂时不可用: {exc}")

    log_op(db, "bot_chat", request=request, user=user,
           detail={"msg_count": len(body.messages), "reply_len": len(reply),
                   "tools": [a["name"] for a in actions]})
    db.commit()

    return {"reply": reply, "actions": actions}
