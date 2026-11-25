"""重置管理员密码。用法（server 目录）：
  NEW_ADMIN_PASSWORD=xxx .venv/Scripts/python.exe scripts/set_admin_password.py
（密码从环境变量读取，避免出现在源码/命令历史之外）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> int:
    new_pw = os.environ.get("NEW_ADMIN_PASSWORD", "")
    if not new_pw or len(new_pw) < 6:
        print("请通过环境变量 NEW_ADMIN_PASSWORD 提供至少 6 位新密码")
        return 2
    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.role == "admin").all()
        if not admins:
            print("没有管理员账号，请先执行 init_db")
            return 1
        for admin in admins:
            admin.password_hash = hash_password(new_pw)
        db.commit()
        print(f"已重置 {len(admins)} 个管理员账号的密码（用户名：{', '.join(a.username for a in admins)}）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
