"""单号生成：YYMMDD-NNN，按天原子递增；支持导入历史项目时使用自定义编号。"""
from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import engine
from ..models import Order, OrderSeq

# 自定义编号允许的字符集（与 orders.id String(16) 主键长度一致）
CUSTOM_NO_RE = re.compile(r"^[A-Za-z0-9_-]{2,16}$")
# 形如自动单号的编号：按字面解析出日期与序号，还原历史单的统计口径
CUSTOM_NO_STD_RE = re.compile(r"^(\d{6})-(\d{1,3})$")
# 非标准格式编号借用的高位序号段（seq 为 SmallInteger，上限 32767；
# 自动编号当天最多三位数，30001 起互不干扰）
CUSTOM_SEQ_HIGH_MIN, CUSTOM_SEQ_HIGH_MAX = 30001, 32767


def _sync_seq_counter(db: Session, day: date, seq: int) -> None:
    """把某天的自动取号计数器抬高到至少 seq。

    自定义「今天的标准编号」（如手工导入 260101-001）不抬高计数器的话，
    下一个自动取号会分配到相同 (日期, 序号)，撞 uq_order_date_seq 唯一约束。
    历史日期同理抬高，防止同一天再导入更多历史单时与后续补号冲突。
    """
    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO order_seq (order_date, last_seq) VALUES (:d, :s) "
                    "ON DUPLICATE KEY UPDATE last_seq = GREATEST(last_seq, :s)"
                ),
                {"d": day, "s": seq},
            )
        return
    # 非 MySQL（单测 SQLite）：行锁改写，复用 _allocate_fallback 的并发策略
    for _ in range(3):
        row = db.execute(
            select(OrderSeq).where(OrderSeq.order_date == day).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            try:
                with db.begin_nested():
                    db.add(OrderSeq(order_date=day, last_seq=seq))
                    db.flush()
                return
            except IntegrityError:
                continue
        if row.last_seq < seq:
            row.last_seq = seq
        return


def custom_order_no(db: Session, no: str) -> tuple[str, int, date]:
    """校验并规整自定义编号，返回 (单号, 序号, 日期)。

    - 编号必须由 2-16 位字母/数字/中划线/下划线组成，且不得与现有单号重复；
    - 形如 YYMMDD-NNN 的编号解析出真实日期与序号（历史订单还原原口径），
      与现有订单的 (日期, 序号) 冲突时明确报错；
    - 其他格式：日期取今天，序号从 32767 向下分配高位段。
    """
    no = (no or "").strip()
    if not CUSTOM_NO_RE.fullmatch(no):
        raise ValueError("自定义编号仅支持 2-16 位字母、数字、中划线(-)、下划线(_)")
    if db.get(Order, no) is not None:
        raise ValueError(f"编号已存在：{no}")

    m = CUSTOM_NO_STD_RE.fullmatch(no)
    if m:
        try:
            parsed_date = datetime.strptime(m.group(1), "%y%m%d").date()
        except ValueError:
            parsed_date = None  # 日期位不是真实日期（如 991332）时按非标准格式处理
        if parsed_date is not None:
            seq = int(m.group(2))
            clash = (
                db.query(Order.id)
                .filter(Order.order_date == parsed_date, Order.seq == seq)
                .first()
            )
            if clash:
                raise ValueError(f"编号 {no} 与现有订单的日期/序号冲突，请换一个编号")
            _sync_seq_counter(db, parsed_date, seq)
            return no, seq, parsed_date

    today = date.today()
    highest = (
        db.query(Order.seq)
        .filter(Order.order_date == today, Order.seq >= CUSTOM_SEQ_HIGH_MIN)
        .order_by(Order.seq.desc())
        .first()
    )
    seq = (highest[0] - 1) if highest else CUSTOM_SEQ_HIGH_MAX
    if seq < CUSTOM_SEQ_HIGH_MIN:
        raise ValueError("今日自定义编号数量已达上限，请明天再导入或改用自动编号")
    return no, seq, today


def _allocate_mysql(today: date) -> int:
    """独立连接取号并立即提交：行锁只在本语句内持有。

    用 INSERT ... ON DUPLICATE KEY UPDATE + LAST_INSERT_ID(expr) 一次往返完成
    「不存在则插入 1，存在则 +1」。原来的 SELECT ... FOR UPDATE 会把取号行的
    排他锁一直挂到调用方事务提交，AI 助手路径（只开 SAVEPOINT、commit 在整轮
    LLM 循环之后）曾因此长时间占锁，把当天其他建单全部堵成锁等待超时。
    代价：调用方后续回滚时该号被浪费（单号出现空缺属可接受）。
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO order_seq (order_date, last_seq) "
                "VALUES (:d, LAST_INSERT_ID(1)) "
                "ON DUPLICATE KEY UPDATE last_seq = LAST_INSERT_ID(last_seq + 1)"
            ),
            {"d": today},
        )
        return int(conn.execute(text("SELECT LAST_INSERT_ID()")).scalar_one())


def _allocate_fallback(db: Session, today: date) -> int:
    """非 MySQL（如 SQLite 单测）退化实现：保持原有行为。"""
    for _ in range(3):
        row = db.execute(
            select(OrderSeq).where(OrderSeq.order_date == today).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            try:
                # 用保存点隔离并发首次取号的唯一键冲突，避免回滚调用方已有事务。
                with db.begin_nested():
                    db.add(OrderSeq(order_date=today, last_seq=1))
                    db.flush()
                return 1
            except IntegrityError:
                continue
        row.last_seq += 1
        return int(row.last_seq)
    raise RuntimeError("生成单号失败，请重试")


def next_order_no(db: Session) -> tuple[str, int, date]:
    """分配当日单号，返回 (单号, 序号, 日期)。"""
    today = date.today()
    if engine.dialect.name == "mysql":
        seq = _allocate_mysql(today)
    else:
        seq = _allocate_fallback(db, today)
    order_no = today.strftime("%y%m%d") + "-" + "%03d" % seq
    return order_no, seq, today
