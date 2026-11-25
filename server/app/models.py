from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "sys_user"
    __table_args__ = (Index("ix_user_parent", "parent_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(50), default="")
    # admin=管理员 staff=内部协助者 agent=代理/销售
    role: Mapped[str] = mapped_column(String(10), default="agent")
    # 个性角色标签：非空时前端用它替代默认角色名（如“高级鸽子”），仅影响展示不影响权限
    role_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 会话版本：改密/角色变更/停用/退出所有设备时递增，旧 JWT 立即失效
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # 登录安全：连续失败计数与锁定截止（5 次失败锁 10 分钟）
    failed_logins: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # TOTP 两步验证（动态码）；pending 为待确认密钥
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_pending: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 多级代理：上级代理与抽成比例（下级订单结单时按代理价抽成给上级）
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    commission_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    # API 可拉取的项目类型（CSV：program,thesis,thesis_program）；空 = 全部。
    # 历史存量为旧工种值，读取/保存时统一归一（见 order_svc.normalize_project_type）
    api_categories: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    orders_as_agent = relationship("Order", foreign_keys="Order.agent_user_id", back_populates="agent")


class Quality(Base):
    __tablename__ = "quality"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # white/green/blue/purple/orange/red
    name: Mapped[str] = mapped_column(String(20))               # 白色/绿色/...
    color: Mapped[str] = mapped_column(String(10))              # 前端徽章色
    multiplier: Mapped[float] = mapped_column(Numeric(6, 2))    # 价格倍率
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 可选：该品质的自定义价格（不填则按 基础价×倍率）
    owner_price_override: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    agent_price_override: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_date", "seq", name="uq_order_date_seq"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_agent", "agent_user_id"),
        Index("ix_orders_created", "created_at"),
        Index("ix_orders_deleted", "is_deleted"),
        Index("ix_orders_category", "category"),
        Index("ix_orders_project_type", "project_type"),
    )

    # 主键即单号，如 260101-001
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_date: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(SmallInteger)

    title: Mapped[str] = mapped_column(String(255))
    quality_id: Mapped[int] = mapped_column(ForeignKey("quality.id", ondelete="RESTRICT"))
    multiplier: Mapped[float] = mapped_column(Numeric(6, 2))          # 下单时倍率快照
    owner_price: Mapped[float] = mapped_column(Numeric(10, 2))       # 真实价（仅管理员可见）
    agent_price: Mapped[float] = mapped_column(Numeric(10, 2))       # 代理价

    # pending/in_progress/completed/closed/after_sale/cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # undeployed/deployed/not_required
    deploy_status: Mapped[str] = mapped_column(String(20), default="undeployed")
    # 遗留列（旧「工种」code/design/thesis）：业务已改用 project_type，此列仅按项目类型推导写入，
    # 供历史数据/外部 SQL 兼容，不再对外暴露
    category: Mapped[str] = mapped_column(String(10), default="thesis")
    # 项目类型（唯一分类维度）：program=纯程序设计 thesis=纯论文 thesis_program=论文+设计；
    # NULL=旧订单未设置（按纯程序设计对待，不启用论文进度）
    project_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tech_stack: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 技术栈偏好
    customer_info: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 客户原始需求资料：上传文档提取的全文 / 口头需求要点总结，AI 生成需求书时作为基准
    source_requirement: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    # 上传需求书的应用方式：reference=作为参考由 AI 生成（默认）；direct=原文直接应用，不做修改
    source_apply_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    requirement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    agent_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)  # 来源代理
    assignee_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)  # 制作负责人
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="RESTRICT"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)  # 回收站软删除
    # 交付链接版本：撤销链接时递增，旧链接立即失效
    deliver_token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    requirement: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)     # 需求书 JSON
    requirement_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # ai/template/manual
    requirement_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)   # 开始制作
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 完成
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)     # 结单
    # 客户验收（交付页点「确认验收」留痕）
    customer_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    customer_accepted_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    quality = relationship("Quality")
    agent = relationship("User", foreign_keys=[agent_user_id])
    assignee = relationship("User", foreign_keys=[assignee_user_id])
    creator = relationship("User", foreign_keys=[created_by])


class OrderFile(Base):
    __tablename__ = "order_file"
    __table_args__ = (Index("ix_order_file_order", "order_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    # package=程序包 video=演示视频 doc=文档 other=其他
    category: Mapped[str] = mapped_column(String(10))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(128))  # 随机文件名，含子目录
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChunkUpload(Base):
    """分片上传会话：记录归属、总大小、已收分片与过期时间，防止越权查询和无限写盘。"""
    __tablename__ = "chunk_upload"
    __table_args__ = (
        Index("ix_chunk_upload_order", "order_id"),
        Index("ix_chunk_upload_user", "user_id"),
        Index("ix_chunk_upload_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(10))
    size: Mapped[int] = mapped_column(BigInteger)
    chunk_size: Mapped[int] = mapped_column(Integer)
    total_chunks: Mapped[int] = mapped_column(Integer)
    received: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 数组，已接收分片序号
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OperationLog(Base):
    __tablename__ = "operation_log"
    __table_args__ = (
        Index("ix_oplog_entity", "entity_type", "entity_id"),
        Index("ix_oplog_created", "created_at"),
        Index("ix_oplog_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    role: Mapped[str] = mapped_column(String(10), default="-")
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: before/after 等
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class OrderSeq(Base):
    __tablename__ = "order_seq"

    order_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_seq: Mapped[int] = mapped_column(SmallInteger, default=0)


class RequirementVersion(Base):
    """需求书历史版本：每次生成/保存前快照，可回滚。"""
    __tablename__ = "requirement_version"
    __table_args__ = (Index("ix_reqver_order", "order_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    document: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Notification(Base):
    """站内通知：状态流转/文件上传/需求书更新时推送给相关用户（右上角铃铛）。"""
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notify_user", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OrderNote(Base):
    """订单跟进记录：与客户/代理的沟通日志，按时间线展示。"""
    __tablename__ = "order_note"
    __table_args__ = (Index("ix_note_order", "order_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    role: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Suggestion(Base):
    """建议/工单：代理提交（只能建议不能改单），后台与写手同步收到通知。"""
    __tablename__ = "suggestion"
    __table_args__ = (
        Index("ix_sug_user", "user_id"),
        Index("ix_sug_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 关联订单（可空=通用建议）
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    kind: Mapped[str] = mapped_column(String(20), default="suggestion")  # suggestion/issue/urgent
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/processing/resolved/closed
    reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    replied_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ChatMessage(Base):
    """站内私信：代理与上级/平台（管理员+写手）互聊。"""
    __tablename__ = "chat_message"
    __table_args__ = (
        Index("ix_chat_to", "to_id", "is_read"),
        Index("ix_chat_pair", "from_id", "to_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"))
    to_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(String(2000))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AiUsage(Base):
    """AI Token 用量：所有 DeepSeek 调用出口统一记账（chat/需求书/摘要/周报/diff/标题分析）。"""
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_scene", "scene"),
        Index("ix_ai_usage_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scene: Mapped[str] = mapped_column(String(30))          # chat/docgen/summary/report/diff/title
    model: Mapped[str] = mapped_column(String(60))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Announcement(Base):
    """系统公告：管理员发布，全员铃铛/工作台可见。"""
    __tablename__ = "announcement"
    __table_args__ = (Index("ix_ann_published", "is_published", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(20), default="info")  # info/warning/important
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Customer(Base):
    """客户库（轻 CRM）：代理/平台沉淀客户信息，与订单 customer_info 自由关联。"""
    __tablename__ = "customer"
    __table_args__ = (
        Index("ix_customer_owner", "owner_id"),
        UniqueConstraint("owner_id", "name", name="uq_customer_owner_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)   # 微信/电话/QQ
    school: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # 学校/专业
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)    # 来源渠道
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class OrderTemplate(Base):
    """模板库：需求书模板 / 技术栈片段 / 报价话术 / 常用备注，下单与需求书编辑时一键插入。"""
    __tablename__ = "order_template"
    __table_args__ = (
        Index("ix_tpl_kind", "kind"),
        Index("ix_tpl_owner", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), default="requirement")  # requirement/tech/remark/quote
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(LONGTEXT)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="-")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class StatusRevertRequest(Base):
    """写手撤回状态申请：手误推进后需管理员审批，通过才回退状态。"""
    __tablename__ = "status_revert_request"
    __table_args__ = (
        Index("ix_revert_order", "order_id", "status"),
        Index("ix_revert_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    requested_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(50), default="-")
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(300))
    # pending/approved/rejected/cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reviewer_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    order = relationship("Order")


class OrderPaperDoc(Base):
    """论文交付物留档：任务书/开题报告/初稿/终稿，每次提交/修改都追加一行（append-only）。

    - doc_type: task_book=任务书 proposal=开题报告 draft=初稿 final=终稿
    - round: 该订单该类文档的第几版（初稿每次修改 +1，形成修改留档链）
    - file_id 关联 order_file（category=paper）；删除留档文件被后端禁止，保证链完整
    """
    __tablename__ = "order_paper_doc"
    __table_args__ = (
        Index("ix_paper_doc_order", "order_id", "doc_type"),
        Index("ix_paper_doc_file", "file_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id", ondelete="CASCADE"))
    doc_type: Mapped[str] = mapped_column(String(20))
    round: Mapped[int] = mapped_column(Integer, default=1)
    file_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("order_file.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(50), default="-")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    file = relationship("OrderFile")
