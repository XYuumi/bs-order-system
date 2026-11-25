"""站内通知：写入 notification 表，供右上角铃铛拉取；在线用户经 WebSocket 实时推送。调用方负责 commit。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Notification, Order
from ..ws import queue_ws_event

STATUS_CN = {
    "pending": "待开始", "in_progress": "制作中", "completed": "已完成",
    "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消",
}


def push(db: Session, user_ids: list[int], title: str, body: str | None = None, order_id: str | None = None) -> None:
    """给一批用户写通知（去重、忽略空）+ 在线实时推送。"""
    for uid in dict.fromkeys(user_ids):
        if not uid:
            continue
        db.add(Notification(user_id=uid, title=title[:120], body=(body or None) and body[:500], order_id=order_id))
    queue_ws_event(db, list(user_ids), {
        "type": "notify",
        "title": title[:120],
        "body": (body or "")[:200],
        "order_id": order_id,
    })


def notify_order_created(db: Session, order: Order, actor_id: int) -> None:
    """新订单创建 → 通知全部管理员与写手（制作侧跟进），以及订单代理本人（非创建者时）。"""
    from ..models import User

    targets = [
        uid
        for (uid,) in db.query(User.id).filter(
            User.role.in_(("admin", "staff")),
            User.is_active == True,  # noqa: E712
        ).all()
        if uid != actor_id
    ]
    if order.agent_user_id and order.agent_user_id != actor_id:
        targets.append(order.agent_user_id)
    push(
        db, targets,
        f"新订单 {order.id} 已创建",
        body=order.title,
        order_id=order.id,
    )


def notify_status_changed(db: Session, order: Order, actor_id: int, new_status: str) -> None:
    """状态流转 → 通知订单代理与创建人（操作者本人除外）。"""
    targets = []
    if order.agent_user_id and order.agent_user_id != actor_id:
        targets.append(order.agent_user_id)
    if order.created_by and order.created_by != actor_id:
        targets.append(order.created_by)
    push(
        db, targets,
        f"订单 {order.id} 状态变更为「{STATUS_CN.get(new_status, new_status)}」",
        body=order.title,
        order_id=order.id,
    )


def notify_file_uploaded(db: Session, order: Order, actor_id: int, filename: str, category: str,
                         replaced: list[str] | None = None) -> None:
    """交付物上传（视频/程序包）→ 通知代理与创建人；替换上传时点明替换了哪个旧文件。"""
    if category not in ("video", "package"):
        return
    targets = []
    if order.agent_user_id and order.agent_user_id != actor_id:
        targets.append(order.agent_user_id)
    if order.created_by and order.created_by != actor_id:
        targets.append(order.created_by)
    cat_cn = "演示视频" if category == "video" else "交付包"
    if replaced:
        title, body = f"订单 {order.id} 替换了{cat_cn}", f"{filename}（替换了 {'、'.join(replaced)}）· {order.title}"
    else:
        title, body = f"订单 {order.id} 上传了新{cat_cn}", f"{filename}（{order.title}）"
    push(db, targets, title, body=body, order_id=order.id)


def notify_requirement_updated(db: Session, order: Order, actor_id: int, action: str) -> None:
    """需求书生成/编辑 → 通知代理与创建人。"""
    targets = []
    if order.agent_user_id and order.agent_user_id != actor_id:
        targets.append(order.agent_user_id)
    if order.created_by and order.created_by != actor_id:
        targets.append(order.created_by)
    push(
        db, targets,
        f"订单 {order.id} 需求书已{action}",
        body=order.title,
        order_id=order.id,
    )
