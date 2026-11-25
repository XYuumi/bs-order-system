from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .constants import SOURCE_REQUIREMENT_MAX_CHARS


def _check_pwd_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("密码过长（最多 72 字节）")
    return value


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        return _check_pwd_bytes(value)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=100)
    new_password: str = Field(min_length=6, max_length=100)

    @field_validator("new_password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        return _check_pwd_bytes(value)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(min_length=6, max_length=100)
    display_name: str = Field(default="", max_length=50)
    role: str = Field(pattern=r"^(admin|staff|agent)$")
    # 多级代理：上级代理ID与抽成比例（0~100，下级结单时按代理价抽给上级）
    parent_id: Optional[int] = Field(default=None, ge=1)
    commission_rate: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    # API 可拉取类别：传空数组/None=全部；否则 code/design/thesis 子集
    api_categories: Optional[list[str]] = Field(default=None)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        return _check_pwd_bytes(value)


class UserUpdateIn(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=50)
    role: Optional[str] = Field(default=None, pattern=r"^(admin|staff|agent)$")
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    parent_id: Optional[int] = Field(default=None, ge=1)
    commission_rate: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    api_categories: Optional[list[str]] = Field(default=None)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str | None) -> str | None:
        return _check_pwd_bytes(value) if value is not None else None


class QualityUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=20)
    color: Optional[str] = Field(default=None, max_length=10)
    multiplier: Optional[float] = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    sort: Optional[int] = Field(default=None, ge=0, le=999)
    enabled: Optional[bool] = None
    # 传数字=设置自定义价，显式传 null=清除（恢复 基础价×倍率）
    owner_price_override: Optional[float] = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    agent_price_override: Optional[float] = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)


CATEGORIES = ("code", "design", "thesis")  # 旧工种值：仅作为兼容入参接受，业务上已废弃

# 项目类型（唯一分类维度）：纯程序设计 / 纯论文 / 论文+设计
PROJECT_TYPES = ("program", "thesis", "thesis_program")


class OrderCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    quality_code: str = Field(min_length=1, max_length=10)
    # 自定义订单编号（导入历史项目保留原编号）：留空按天自动生成 YYMMDD-NNN；
    # 仅管理员/协助者可指定，2-16 位字母/数字/中划线/下划线，重复或冲突会报错
    order_no: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{2,16}$")
    # program=纯程序设计 thesis=纯论文 thesis_program=论文+设计；不传且传了旧 category 时按旧值映射
    project_type: Optional[str] = Field(default=None, pattern=r"^(program|thesis|thesis_program)$")
    # 废弃兼容：旧对接脚本可能仍传工种 code/design/thesis；服务端归一为项目类型
    category: Optional[str] = Field(default=None, pattern=r"^(code|design|thesis)$")
    deadline: Optional[date] = None
    tech_stack: Optional[str] = Field(default=None, max_length=100)
    customer_info: Optional[str] = Field(default=None, max_length=255)
    remark: Optional[str] = Field(default=None, max_length=2000)
    # 原始需求资料：上传文档提取全文 / 口头需求要点，AI 生成需求书时作为基准（而非仅凭题目）
    source_requirement: Optional[str] = Field(default=None, max_length=SOURCE_REQUIREMENT_MAX_CHARS)
    # 上传需求书应用方式：reference=作为参考由 AI 生成（默认）；direct=原文直接应用不做修改
    source_apply_mode: Optional[str] = Field(default=None, pattern=r"^(reference|direct)$")
    requirement_notes: Optional[str] = Field(default=None, max_length=4000)
    # 管理员/协助者建单时可指定来源代理用户名；代理自己建单固定归属自己
    agent_username: Optional[str] = Field(default=None, max_length=50)
    # 仅管理员：下单时直接覆盖本单真实价快照（不改品质公式）；None=按品质公式计价
    owner_price: Optional[float] = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)


class OrderUpdateIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    quality_code: Optional[str] = Field(default=None, min_length=1, max_length=10)
    project_type: Optional[str] = Field(default=None, pattern=r"^(program|thesis|thesis_program)$")
    owner_price: Optional[float] = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)  # 仅管理员
    deadline: Optional[date] = None
    tech_stack: Optional[str] = Field(default=None, max_length=100)
    customer_info: Optional[str] = Field(default=None, max_length=255)
    remark: Optional[str] = Field(default=None, max_length=2000)
    source_requirement: Optional[str] = Field(default=None, max_length=SOURCE_REQUIREMENT_MAX_CHARS)
    source_apply_mode: Optional[str] = Field(default=None, pattern=r"^(reference|direct)$")
    requirement_notes: Optional[str] = Field(default=None, max_length=4000)
    agent_username: Optional[str] = Field(default=None, max_length=50)  # 仅管理员
    assignee_username: Optional[str] = Field(default=None, max_length=50)  # 仅管理员/协助者


class StatusIn(BaseModel):
    status: str = Field(pattern=r"^(pending|in_progress|completed|closed|after_sale|cancelled)$")


class BatchStatusIn(BaseModel):
    # 批量流转：后端按状态机白名单逐单校验，非法跳转的订单会被跳过并在 results 中说明
    ids: list[str] = Field(min_length=1, max_length=100)
    status: str = Field(pattern=r"^(pending|in_progress|completed|closed|after_sale|cancelled)$")


class StatusRevertIn(BaseModel):
    # 写手手误后申请回退：in_progress→pending / completed→in_progress
    to_status: str = Field(pattern=r"^(pending|in_progress)$")
    reason: str = Field(min_length=2, max_length=300)


class StatusRevertReviewIn(BaseModel):
    action: str = Field(pattern=r"^(approve|reject)$")
    note: str | None = Field(default=None, max_length=300)


class TitleCheckIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)


class DeployStatusIn(BaseModel):
    deploy_status: str = Field(pattern=r"^(undeployed|deployed|not_required)$")


class GenerateIn(BaseModel):
    mode: str = Field(default="auto", pattern=r"^(auto|ai|template)$")


class RequirementSaveIn(BaseModel):
    document: dict


class RequirementReviseIn(BaseModel):
    # AI 按修改建议修订需求书：不落库，返回修订稿由前端展示、用户确认后再走保存
    instruction: str = Field(min_length=2, max_length=1000)
    document: dict
