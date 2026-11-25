"""老库幂等补列：create_all 只建缺失表，不会给已有表追加列。

每次给已有表加列时，除了在 models.py 声明，还要：
1. 在 sql/ 下补一份迁移脚本（手工执行兜底）；
2. 在 _UPGRADES 里加一项，启动时自动补齐。

幂等策略：直接执行下方硬编码的 DDL 字面量；MySQL 报「列/索引已存在」
（错误码 1060/1061）时视为已完成静默跳过，其余异常只记日志不阻断启动。
本模块不接收任何外部输入。
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger("uvicorn.error")

# 1060 = Duplicate column name, 1061 = Duplicate key name
_DUPLICATE_CODES = {1060, 1061}


def _add_project_type(conn: Connection) -> None:
    conn.execute(text(
        "ALTER TABLE `orders` ADD COLUMN `project_type` VARCHAR(20) NULL DEFAULT NULL"
    ))


def _add_project_type_index(conn: Connection) -> None:
    conn.execute(text(
        "CREATE INDEX `ix_orders_project_type` ON `orders` (`project_type`)"
    ))


def _backfill_project_type(conn: Connection) -> None:
    """老数据回填：project_type 为空的历史订单按旧工种列映射
    （纯论文→纯论文；程序/艺术设计→纯程序设计，均不改变原“无论文流程”行为）。幂等。"""
    conn.execute(text(
        "UPDATE `orders` SET `project_type` = "
        "CASE WHEN `category` = 'thesis' THEN 'thesis' ELSE 'program' END "
        "WHERE `project_type` IS NULL"
    ))


def _add_source_apply_mode(conn: Connection) -> None:
    conn.execute(text(
        "ALTER TABLE `orders` ADD COLUMN `source_apply_mode` VARCHAR(10) NULL DEFAULT NULL AFTER `source_requirement`"
    ))


# (说明, DDL/数据动作)
_UPGRADES = [
    ("orders.project_type 列", _add_project_type),
    ("orders.ix_orders_project_type 索引", _add_project_type_index),
    ("orders.project_type 历史数据回填", _backfill_project_type),
    ("orders.source_apply_mode 列", _add_source_apply_mode),
]


def ensure_columns(engine: Engine) -> None:
    for label, action in _UPGRADES:
        try:
            with engine.begin() as conn:
                action(conn)
            logger.warning(f"[upgrade] 已自动补齐: {label}")
        except OperationalError as exc:
            code = exc.orig.args[0] if getattr(exc, "orig", None) and exc.orig.args else None
            if code in _DUPLICATE_CODES:
                continue  # 已存在，幂等跳过
            logger.warning(f"[upgrade] 补齐失败 {label}: {exc}；请手工执行 sql/ 迁移脚本")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[upgrade] 补齐失败 {label}: {exc}；请手工执行 sql/ 迁移脚本")
