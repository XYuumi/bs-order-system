"""从备份恢复数据（支持加密 .json.enc 与旧版明文 .json）。

用法（server 目录）：
  .venv/Scripts/python.exe scripts/restore_backup.py [备份文件名或路径]
不传参数时自动选取 backups/ 下最新备份。
恢复前会自动为当前数据库生成一份加密快照；只清理/恢复备份中存在的表，
按外键子表先删、父表先插的顺序执行。表名只来自 SQLAlchemy 模型白名单。
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import MetaData  # noqa: E402

from app.config import BASE_DIR  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.backup_svc import backup_now, read_backup_payload  # noqa: E402

BACKUP_DIR = (BASE_DIR / "server" / "backups").resolve()
SAFE_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _coerce(value, column):
    if value is None:
        return None
    type_name = type(column.type).__name__
    if isinstance(value, dict) and "__hex__" in value:
        return bytes.fromhex(value["__hex__"])
    if type_name == "Date":
        return date.fromisoformat(str(value)[:10])
    if type_name == "DateTime":
        return datetime.fromisoformat(str(value))
    if type_name in ("Numeric", "DECIMAL"):
        return Decimal(str(value))
    if type_name in ("BigInteger", "SmallInteger", "Integer"):
        return int(value)
    return value


def _latest_backup() -> Path:
    files = sorted(
        p for p in BACKUP_DIR.glob("bs-backup-*")
        if p.is_file() and p.resolve().is_relative_to(BACKUP_DIR)
    )
    if not files:
        raise RuntimeError("backups 目录中没有备份文件")
    return files[-1]


def _read_external(path: Path) -> dict:
    """读取 backups 目录外的备份（解密逻辑复用 backup_svc 的密钥）。"""
    import json

    from app.services.backup_svc import _fernet

    raw = path.read_bytes()
    if path.suffix == ".enc":
        raw = _fernet().decrypt(raw)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise RuntimeError("备份格式不正确")
    return data


def _model_map() -> dict[str, type]:
    """表名 -> ORM 模型（只允许代码里声明的表）。"""
    result = {}
    for mapper in Base.registry.mappers:
        model = mapper.class_
        name = getattr(model, "__tablename__", "")
        if name and SAFE_TABLE_RE.match(name):
            result[name] = model
    return result


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        path = Path(argv[1])
        if not path.is_absolute():
            path = (BACKUP_DIR / path).resolve()
    else:
        path = _latest_backup()
    if not path.is_file():
        raise RuntimeError(f"备份不存在: {path}")

    payload = read_backup_payload(path.name) if path.parent == BACKUP_DIR else _read_external(path)

    # 恢复前先为当前数据做一份快照，防止误操作。
    snapshot = backup_now()
    print(f"[restore] 当前库快照: {snapshot['name']}")
    print(f"[restore] 恢复来源: {path.name}")

    meta = MetaData()
    meta.reflect(bind=engine)
    models = _model_map()
    included_names = [
        table.name for table in meta.sorted_tables
        if table.name in models and table.name in payload["tables"]
    ]

    total = 0
    db = SessionLocal()
    try:
        # 子表先清空；只处理备份中存在的表，避免清掉新版本新增表。
        for name in reversed(included_names):
            db.query(models[name]).delete(synchronize_session=False)
        # 父表先写入。
        for name in included_names:
            model = models[name]
            rows = payload["tables"].get(name) or []
            if not rows:
                continue
            columns = {c.name: c for c in model.__table__.columns}
            mappings = [
                {col: _coerce(row.get(col), columns[col]) for col in columns if col in row}
                for row in rows
            ]
            db.bulk_insert_mappings(model, mappings)
            total += len(mappings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"[restore] 完成：{total} 行，{len(included_names)} 张表（来源 {path.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
