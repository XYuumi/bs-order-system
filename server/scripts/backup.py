"""数据库自动备份（加密 JSON）。用法（server 目录）：
  .venv/Scripts/python.exe scripts/backup.py
与后台「一键备份」共用 app.services.backup_svc：Fernet 加密、保留最近 14 份。
恢复：.venv/Scripts/python.exe scripts/restore_backup.py（自动选最新备份）
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from app.services.backup_svc import backup_now  # noqa: E402


def main() -> int:
    info = backup_now()
    print(
        f"备份完成: {info['name']}（{info['size'] // 1024} KB，{info['rows']} 行，"
        f"{'已加密' if info.get('encrypted') else '明文'}）"
    )
    if info.get("removed_old"):
        print(f"清理旧备份: {info['removed_old']} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
