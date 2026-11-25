"""建库建表 + 初始数据：python -m app.init_db（在 server 目录、venv 激活后执行）。"""
from __future__ import annotations

import secrets
import string
import sys

from sqlalchemy import create_engine, text

from .config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, ADMIN_INITIAL_PASSWORD
from .database import SessionLocal, engine
from .models import Base, Quality, Setting, User
from .security import gen_api_key, hash_password
from .services.settings_svc import DEFAULT_SETTINGS

QUALITIES = [
    ("white", "白色", "#9ca3af", 1, 1),
    ("green", "绿色", "#22c55e", 2, 2),
    ("blue", "蓝色", "#3b82f6", 3, 3),
    ("purple", "紫色", "#a855f7", 4, 4),
    ("orange", "橙色", "#f97316", 5, 5),
    ("red", "红色", "#ef4444", 6, 6),
]


def create_database() -> None:
    server_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/?charset=utf8mb4"
    server_engine = create_engine(server_url)
    with server_engine.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        conn.commit()
    server_engine.dispose()
    print(f"[init] 数据库 {DB_NAME} 已就绪")


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(Quality).count() == 0:
            for code, name, color, mult, sort in QUALITIES:
                db.add(Quality(code=code, name=name, color=color, multiplier=mult, sort=sort))
            db.commit()
            print(f"[init] 已写入 {len(QUALITIES)} 个品质")

        for key, value in DEFAULT_SETTINGS.items():
            if db.get(Setting, key) is None:
                db.add(Setting(key=key, value=value))
        db.commit()
        print("[init] 系统设置已就绪")

        if db.query(User).filter(User.role == "admin").count() == 0:
            alphabet = string.ascii_letters + string.digits
            password = ADMIN_INITIAL_PASSWORD or "".join(secrets.choice(alphabet) for _ in range(12))
            admin = User(
                username="admin",
                password_hash=hash_password(password),
                display_name="管理员",
                role="admin",
            )
            db.add(admin)
            db.commit()
            print("=" * 56)
            print(f"[init] 初始管理员账号: admin")
            print(f"[init] 初始管理员密码: {password}")
            print("[init] 请登录后尽快在「个人中心」修改密码")
            print("=" * 56)
        else:
            print("[init] 管理员账号已存在，跳过")
    finally:
        db.close()


def main() -> int:
    create_database()
    Base.metadata.create_all(bind=engine)
    print("[init] 数据表已同步")
    seed()
    print("[init] 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
