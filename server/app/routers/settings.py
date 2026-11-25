from __future__ import annotations

import hmac
import json
import math
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_password_confirm
from ..models import Quality, User
from ..ratelimit import client_ip, rate_limit
from ..schemas import QualityUpdateIn
from ..services.pricing import compute_prices, get_base_prices, quality_view
from ..services.settings_svc import SECRET_KEYS, get_setting, get_settings_map, set_setting
from ..services.oplog import log_op
from ..urlguard import UnsafeUrlError, assert_safe_url

router = APIRouter(prefix="/api", tags=["settings"])

EDITABLE_KEYS = {
    "owner_base_price", "agent_base_price", "site_name",
    "deepseek_base_url", "deepseek_model", "deepseek_timeout",
    "webhook_url",
    # 需求书 Word 页眉（学校名，留空不加）
    "docx_school",
    # 客户交付链接有效期（天，0 = 永久）
    "deliver_expire_days",
    # 备份完成后自动同步到的目录（如网盘同步盘），留空停用
    "backup_sync_dir",
    # 备份完成后是否推送 webhook 通知（依赖 webhook_url）
    "backup_notify_webhook",
    # AI Bot：知识库（Markdown）、系统提示词前缀、工具开关(JSON)、按角色权限矩阵(JSON)、技能配置(JSON)
    "bot_knowledge", "bot_system_prompt", "bot_tools", "bot_permissions", "bot_skills",
    # 成本估算：每 1K tokens 单价（元），用于 Token 统计页
    "ai_price_per_1k",
    # 登录安全：失败锁定阈值/时长（分钟）
    "login_lock_threshold", "login_lock_minutes",
    # 订单详情防截图水印开关（1/0）
    "watermark_enabled",
}
MASK = "******"


@router.get("/settings")
def get_settings(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = get_settings_map(db)
    key = data.get("deepseek_api_key", "")
    data["deepseek_api_key"] = MASK if key else ""
    data["deepseek_key_set"] = bool(key)
    return {"settings": data}


def _number(value, name: str, *, minimum: float = 0, maximum: float | None = None) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{name} 必须是数字")
    if not math.isfinite(num) or num < minimum or (maximum is not None and num > maximum):
        raise HTTPException(status_code=400, detail=f"{name} 超出允许范围")
    return num


def _text(value, name: str, max_len: int) -> str:
    text = str(value or "")
    if len(text) > max_len:
        raise HTTPException(status_code=400, detail=f"{name} 最多 {max_len} 个字符")
    return text


@router.put("/settings")
def update_settings(
    body: dict,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    body = body or {}
    price_keys = {"owner_base_price", "agent_base_price"}
    if price_keys & set(body.keys()):
        require_password_confirm(request, admin)

    changed = {}
    for k, v in body.items():
        if k in SECRET_KEYS:
            # 提交掩码 = 前端表示「未修改」，跳过；显式提交空串 = 清空该密钥（原先无法清空）。
            if v == MASK:
                continue
            if v == "":
                set_setting(db, k, "")
                changed[k] = ""
                continue
            secret_val = str(v)
            if len(secret_val) > 500:
                raise HTTPException(status_code=400, detail="密钥长度异常")
            set_setting(db, k, secret_val)
            changed[k] = MASK
        elif k in EDITABLE_KEYS:
            if k in price_keys:
                v = _number(v, k, minimum=0, maximum=10_000_000)
            elif k == "deliver_expire_days":
                v = int(_number(v, k, minimum=0, maximum=3650))
            elif k == "deepseek_timeout":
                v = int(_number(v, k, minimum=5, maximum=600))
            elif k == "login_lock_threshold":
                v = int(_number(v, k, minimum=1, maximum=100))
            elif k == "login_lock_minutes":
                v = int(_number(v, k, minimum=1, maximum=1440))
            elif k == "ai_price_per_1k":
                v = _number(v, k, minimum=0, maximum=100_000)
            elif k in ("deepseek_base_url", "webhook_url"):
                v = _text(v, k, 300).strip()
                if v:
                    # 网址不合法是入参问题：返回 400 与原因，而不是让 ValueError 冒成 500
                    try:
                        assert_safe_url(v)
                    except UnsafeUrlError as exc:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
            elif k == "backup_sync_dir":
                v = _text(v, k, 500).strip()
                if v:
                    path = Path(v)
                    # casefold 后比较，避免 c:\windows / C:/WINDOWS 之类的绕过大写检查
                    blocked = ("c:\\windows", "c:\\program files", "c:\\program files (x86)")
                    try:
                        resolved = path.resolve()
                    except OSError:
                        raise HTTPException(status_code=400, detail="同步目录路径非法")
                    if (
                        not path.is_absolute()
                        or resolved == Path(resolved.anchor)
                        or str(resolved).casefold().startswith(blocked)
                    ):
                        raise HTTPException(status_code=400, detail="同步目录必须是安全的绝对路径")
            elif k == "backup_notify_webhook":
                v = "1" if str(v).lower() in ("1", "true", "yes", "on") else "0"
            elif k == "watermark_enabled":
                v = "1" if str(v).lower() in ("1", "true", "yes", "on") else "0"
            elif k == "site_name":
                v = _text(v, k, 100).strip()
            elif k == "docx_school":
                v = _text(v, k, 100).strip()
            elif k == "deepseek_model":
                v = _text(v, k, 60).strip()
            else:
                v = _text(v, k, 200_000)
            set_setting(db, k, str(v))
            changed[k] = v
    if not changed:
        raise HTTPException(status_code=400, detail="没有可保存的配置")
    log_op(db, "settings_update", request=request, user=admin, detail={"keys": sorted(changed.keys())})
    db.commit()
    data = get_settings_map(db)
    data["deepseek_api_key"] = MASK if data.get("deepseek_api_key") else ""
    return {"settings": data}


@router.get("/settings/dash-layout")
def get_dash_layout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """工作台默认布局（按 admin/user 两套；「存为默认布局」按钮写入，重置布局后回落到这里）。"""
    def _parse(raw):
        try:
            items = json.loads(raw or "[]")
            return items if isinstance(items, list) else []
        except (ValueError, TypeError):
            return []

    data = get_settings_map(db, ["dash_layout_admin", "dash_layout_user"])
    return {"admin": _parse(data.get("dash_layout_admin")),
            "user": _parse(data.get("dash_layout_user"))}


@router.post("/settings/dash-layout")
def save_dash_layout(
    body: dict,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把当前工作台卡片布局存为默认（scope=admin 影响管理员端，user 影响写手/代理端）。

    管理员可存两套；代理只能存自己那套（user）。
    """
    scope = (body or {}).get("scope")
    if scope not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="scope 必须是 admin 或 user")
    if scope == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可保存管理员端默认布局")
    if scope == "user" and user.role not in ("admin", "agent"):
        raise HTTPException(status_code=403, detail="仅管理员或代理可保存该默认布局")
    items = (body or {}).get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 40):
        raise HTTPException(status_code=400, detail="布局数据不合法")
    clean = []
    for it in items:
        try:
            clean.append({
                "id": str(it["id"])[:40],
                "x": max(0, int(it["x"])), "y": max(0, int(it["y"])),
                "w": min(12, max(1, int(it["w"]))), "h": min(60, max(1, int(it["h"]))),
            })
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="布局条目不合法") from exc
    set_setting(db, f"dash_layout_{scope}", json.dumps(clean, ensure_ascii=False))
    db.commit()
    log_op(db, "dash_layout_save", request=request, user=user,
           detail={"scope": scope, "cards": len(clean)})
    db.commit()
    return {"ok": True, "scope": scope, "cards": len(clean)}


@router.get("/settings/public")
def public_settings(db: Session = Depends(get_db)):
    """公开配置：登录页/公开页使用，只暴露非敏感字段。"""
    from ..services.docgen.ai import ai_available

    data = get_settings_map(db, ["site_name", "watermark_enabled"])
    return {
        "site_name": data.get("site_name", ""),
        "ai_ready": ai_available(db),
        # 水印开关下发布尔值；默认开启（兼容未写库的老库）
        "watermark_enabled": data.get("watermark_enabled", "1") != "0",
    }


# ==================== 数据备份（管理员） ====================

@router.post("/admin/backup")
def run_backup(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from ..services.backup_svc import backup_now, sync_backup

    info = backup_now()
    # 自动同步到外部目录（如网盘同步盘）+ webhook 通知
    try:
        sync_info = sync_backup(db, info["name"])
        info.update(sync_info)
    except Exception as exc:  # noqa: BLE001 —— 同步失败不影响备份本身
        info["sync_error"] = str(exc)[:200]
    log_op(db, "db_backup", request=request, user=admin, detail={"name": info["name"], "rows": info["rows"]})
    db.commit()
    return info


@router.get("/admin/backups")
def list_backups(admin: User = Depends(require_admin)):
    from ..services.backup_svc import list_backups as _list

    return {"items": _list()}


@router.get("/admin/backups/{name}/download")
def download_backup(name: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    from ..services.backup_svc import backup_file

    require_password_confirm(request, admin)
    try:
        path = backup_file(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份不存在")
    log_op(db, "db_backup_download", request=request, user=admin, detail={"name": path.name})
    db.commit()
    media = "application/octet-stream" if path.suffix == ".enc" else "application/json"
    return FileResponse(str(path), media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{path.name}"'})


@router.delete("/admin/backups/{name}")
def delete_backup(name: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from ..services.backup_svc import backup_file

    require_password_confirm(request, admin)
    try:
        path = backup_file(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path.exists():
        path.unlink()
    log_op(db, "db_backup_delete", request=request, user=admin, detail={"name": name})
    db.commit()
    return {"ok": True}


# ==================== 客户报价单（公开分享页） ====================

@router.get("/quote/link")
def get_quote_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取报价单分享 token（首次调用自动生成，登录用户均可，供代理发给客户）。"""
    token = get_setting(db, "quote_token")
    if not token:
        token = secrets.token_urlsafe(12)
        set_setting(db, "quote_token", token)
        db.commit()
    return {"token": token}


@router.get("/quote/{token}")
def public_quote(token: str, request: Request, db: Session = Depends(get_db)):
    """公开报价单：token 校验（恒时比较）。只下发客户价（price），不含写手价与倍率。"""
    rate_limit(request, "quote", client_ip(request), 30, 60)
    saved = get_setting(db, "quote_token") or ""
    if not saved or not hmac.compare_digest(saved, token):
        raise HTTPException(status_code=404, detail="报价单不存在或已失效")
    qualities = db.query(Quality).filter(Quality.enabled == True).order_by(Quality.sort).all()  # noqa: E712
    owner_base, agent_base = get_base_prices(db)
    site_name = get_settings_map(db, ["site_name"]).get("site_name", "")
    # 客户价按成交价基准计算（含自定义真实价）；写手价与倍率对 public 角色不下发，见 quality_view
    items = [quality_view(q, owner_base, agent_base, "public") for q in qualities]
    return {
        "site_name": site_name or "毕设接单",
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "qualities": items,
    }


@router.get("/qualities")
def list_qualities(
    enabled_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner_base, agent_base = get_base_prices(db)
    q = db.query(Quality).order_by(Quality.sort, Quality.id)
    if enabled_only:
        q = q.filter(Quality.enabled == True)  # noqa: E712
    return {"qualities": [quality_view(qc, owner_base, agent_base, user.role) for qc in q.all()]}


@router.put("/qualities/{code}")
def update_quality(
    code: str,
    body: QualityUpdateIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_password_confirm(request, admin)
    qc = db.query(Quality).filter(Quality.code == code).first()
    if not qc:
        raise HTTPException(status_code=404, detail="品质不存在")
    changes = {}
    if body.name is not None:
        qc.name = _text(body.name, "品质名称", 20).strip()
        changes["name"] = qc.name
    if body.color is not None:
        qc.color = _text(body.color, "颜色", 20).strip()
        changes["color"] = qc.color
    if body.multiplier is not None:
        qc.multiplier = _number(body.multiplier, "倍率", minimum=0.01, maximum=100)
        changes["multiplier"] = float(qc.multiplier)
    if body.sort is not None:
        qc.sort = body.sort
        changes["sort"] = qc.sort
    if body.enabled is not None:
        qc.enabled = body.enabled
        changes["enabled"] = qc.enabled
    # 自定义价：区分“未传”与“传 null 清除”
    fields = body.model_fields_set
    if "owner_price_override" in fields:
        qc.owner_price_override = (
            _number(body.owner_price_override, "真实价", minimum=0, maximum=10_000_000)
            if body.owner_price_override is not None else None
        )
        changes["owner_price_override"] = qc.owner_price_override
    if "agent_price_override" in fields:
        qc.agent_price_override = (
            _number(body.agent_price_override, "代理价", minimum=0, maximum=10_000_000)
            if body.agent_price_override is not None else None
        )
        changes["agent_price_override"] = qc.agent_price_override
    # 交叉校验：改价格相关字段时，真实价不得低于代理价（与下单口径一致，防止负毛利）
    if {"owner_price_override", "agent_price_override", "multiplier"} & fields:
        owner_price, agent_price, _ = compute_prices(db, qc)
        if owner_price < agent_price:
            raise HTTPException(
                status_code=400,
                detail=f"真实价（¥{owner_price}）不能低于代理价（¥{agent_price}），请调整自定义价或倍率",
            )
    log_op(db, "quality_update", request=request, user=admin, entity_type="quality", entity_id=qc.code, detail=changes)
    db.commit()
    owner_base, agent_base = get_base_prices(db)
    return {"quality": quality_view(qc, owner_base, agent_base, "admin")}
