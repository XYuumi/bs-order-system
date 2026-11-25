"""演示数据：生成跨 8 个月的模拟订单/用户/日志，供统计与截图验证。

用法（server 目录）：
  .venv/Scripts/python.exe scripts/demo_data.py create   # 生成（密码随机生成并打印）
  .venv/Scripts/python.exe scripts/demo_data.py clean    # 清理演示数据
"""
from __future__ import annotations

import json
import random
import secrets
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal  # noqa: E402
from app.models import OperationLog, Order, OrderFile, OrderSeq, Quality, User  # noqa: E402
from app.security import gen_api_key, hash_password  # noqa: E402
from app.services.docgen import build_template_doc  # noqa: E402

random.seed(20261018)

TITLES = [
    "基于SpringBoot的宠物医院管理系统设计与实现", "基于Django的高校实验室预约管理系统",
    "基于Vue3的社区团购平台设计与实现", "基于SpringBoot的智慧养老院管理系统",
    "基于Python的校园二手书交易平台", "基于JSP的学生成绩管理系统",
    "基于SpringBoot的健身房会员管理系统", "基于Django的旅游景区导览系统",
    "基于微信小程序的食堂点餐系统", "基于SpringBoot的图书借阅管理系统",
    "基于Python的招聘数据采集与分析系统", "基于SpringBoot的房屋租赁管理系统",
    "基于Vue3的在线考试系统设计与实现", "基于Django的学生宿舍管理系统",
    "基于SpringBoot的农产品溯源系统", "基于Python的股票预测分析系统",
    "基于SpringBoot的医院挂号管理系统", "基于Django的博客发布平台",
    "基于Vue3的电影推荐系统设计与实现", "基于SpringBoot的仓储管理系统",
    "基于Python的航班信息分析系统", "基于SpringBoot的停车场管理系统",
    "基于Django的志愿者服务管理系统", "基于SpringBoot的药店销售管理系统",
    "基于Vue3的个人财务管理系统的设计", "基于Python的音乐推荐系统",
    "基于SpringBoot的企业人事管理系统", "基于Django的在线学习平台",
    "基于JSP的图书商城系统", "基于SpringBoot的民宿预订管理系统",
]
TECH = ["SpringBoot+Vue3", "Django", "SpringBoot+Vue3", "JSP+Servlet", "Flask"]


def create() -> int:
    db = SessionLocal()
    demo_pw = secrets.token_urlsafe(9)
    try:
        if db.query(Order).filter(Order.id.like("demo%")).count() or db.query(User).filter(
                User.username.like("demo_%")).count():
            print("已存在演示数据，先执行 clean 再 create")
            return 1

        pw_hash = hash_password(demo_pw)
        agent_a = User(username="demo_agent_a", password_hash=pw_hash, display_name="王代理", role="agent", api_key=gen_api_key())
        agent_b = User(username="demo_agent_b", password_hash=pw_hash, display_name="李销售", role="agent", api_key=gen_api_key())
        staff = User(username="demo_staff_z", password_hash=pw_hash, display_name="小张（协助）", role="staff")
        db.add_all([agent_a, agent_b, staff])
        db.flush()
        admin = db.query(User).filter(User.role == "admin").first()
        qualities = sorted(db.query(Quality).all(), key=lambda q: q.sort)

        now = datetime.now()
        seq_by_date: dict[date, int] = {}
        status_pool = (["closed"] * 13 + ["completed"] * 6 + ["in_progress"] * 6 +
                       ["pending"] * 3 + ["after_sale"] * 1 + ["cancelled"] * 1)
        random.shuffle(status_pool)

        for i, title in enumerate(TITLES):
            days_ago = random.randint(2, 240)
            created = now - timedelta(days=days_ago, hours=random.randint(0, 12))
            od = created.date()
            seq_by_date[od] = seq_by_date.get(od, 0) + 1
            order_id = f"demo{od.strftime('%y%m%d')}-{seq_by_date[od]:03d}"

            quality = random.choice(qualities)
            mult = float(quality.multiplier)
            order = Order(
                id=order_id, order_date=od, seq=seq_by_date[od],
                title=title, quality_id=quality.id, multiplier=mult,
                owner_price=round(300 * mult, 2), agent_price=round(50 * mult, 2),
                status="pending", deploy_status="undeployed",
                deadline=(created + timedelta(days=random.randint(10, 40))).date(),
                tech_stack=random.choice(TECH),
                customer_info=random.choice(["QQ 客户", "微信客户", "转介绍", None, None]),
                agent_user_id=random.choice([agent_a.id, agent_b.id, None, None]),
                assignee_user_id=random.choice([staff.id, staff.id, admin.id]),
                created_by=random.choice([admin.id, staff.id]),
                created_at=created, updated_at=created,
            )

            status = status_pool[i % len(status_pool)]
            if status != "pending":
                order.accepted_at = created + timedelta(days=random.randint(1, 3))
                order.status = "in_progress"
                if status in ("completed", "closed", "after_sale"):
                    order.completed_at = order.accepted_at + timedelta(days=random.randint(3, 21))
                    order.status = "completed"
                    order.deploy_status = random.choice(["deployed", "deployed", "undeployed", "not_required"])
                    if status in ("closed", "after_sale"):
                        order.closed_at = order.completed_at + timedelta(days=random.randint(1, 5))
                        order.status = "closed" if status == "closed" else "after_sale"
                elif status == "cancelled":
                    order.status = "cancelled"
            else:
                order.status = "pending"

            if random.random() < 0.6:
                order.requirement = json.dumps(build_template_doc(title, order.tech_stack), ensure_ascii=False)
                order.requirement_source = "template"
                order.requirement_updated_at = order.created_at + timedelta(hours=2)

            db.add(order)
            db.flush()
            db.add(OperationLog(
                user_id=order.created_by,
                username="admin" if order.created_by == admin.id else staff.username,
                role="admin" if order.created_by == admin.id else "staff",
                action="order_create", entity_type="order", entity_id=order.id,
                detail=json.dumps({"title": title, "quality": quality.code,
                                   "owner_price": float(order.owner_price),
                                   "agent_price": float(order.agent_price)}, ensure_ascii=False),
                ip="127.0.0.1", created_at=order.created_at,
            ))

        for od, last in seq_by_date.items():
            db.add(OrderSeq(order_date=od, last_seq=last))

        db.commit()
        print(f"演示数据已生成：{len(TITLES)} 个订单 + 2 代理 + 1 协助者")
        print(f"演示账号：demo_agent_a / demo_agent_b / demo_staff_z，密码均为：{demo_pw}")
        return 0
    finally:
        db.close()


def clean() -> int:
    db = SessionLocal()
    try:
        demo_orders = db.query(Order).filter(Order.id.like("demo%")).all()
        ids = [o.id for o in demo_orders]
        if ids:
            db.query(OrderFile).filter(OrderFile.order_id.in_(ids)).delete(synchronize_session=False)
            db.query(OperationLog).filter(OperationLog.entity_type == "order",
                                          OperationLog.entity_id.in_(ids)).delete(synchronize_session=False)
            db.query(Order).filter(Order.id.in_(ids)).delete(synchronize_session=False)
            db.query(OrderSeq).delete(synchronize_session=False)
        demo_users = db.query(User).filter(User.username.like("demo_%")).all()
        for u in demo_users:
            db.query(Order).filter(Order.agent_user_id == u.id).update({"agent_user_id": None}, synchronize_session=False)
            db.query(Order).filter(Order.assignee_user_id == u.id).update({"assignee_user_id": None}, synchronize_session=False)
            db.query(OperationLog).filter(OperationLog.user_id == u.id).delete(synchronize_session=False)
            db.delete(u)
        db.commit()
        print(f"已清理 {len(ids)} 个演示订单与 {len(demo_users)} 个演示用户")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "create":
        sys.exit(create())
    elif cmd == "clean":
        sys.exit(clean())
    print("用法: demo_data.py [create|clean]")
    sys.exit(2)
