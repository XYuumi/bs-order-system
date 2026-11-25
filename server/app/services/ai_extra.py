"""AI 增强功能：题目分析推荐项目类型 + 订单智能摘要。

支持「技能覆写」：bot_skills 设置（JSON）中同名技能若带 prompt 字段，则替换默认系统提示词。
所有调用经 _chat 统一记账 Token 用量（scene 由调用方传入）。
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..urlguard import assert_safe_url
from .settings_svc import get_setting
from .docgen.ai import get_ai_config


class AIError(Exception):
    pass


def get_skill(db: Session, key: str) -> dict:
    """读取技能配置（bot_skills JSON：[{key,name,enabled,prompt}]）。"""
    raw = get_setting(db, "bot_skills") or ""
    try:
        skills = json.loads(raw) if raw.strip() else []
    except (ValueError, TypeError):
        skills = []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, dict) and s.get("key") == key:
                return s
    return {}


def skill_prompt(db: Session, key: str, default: str) -> str:
    """技能启停 + 提示词覆写：enabled=false 场景由调用方决定降级；有 prompt 则替换。"""
    s = get_skill(db, key)
    if s.get("prompt") and str(s["prompt"]).strip():
        return str(s["prompt"]).strip()
    return default


def _chat(db: Session, system: str, user: str, max_tokens: int = 512,
          scene: str = "chat", order_id: str | None = None,
          user_id: int | None = None) -> str:
    cfg = get_ai_config(db)
    key = cfg["key"]
    if not key:
        raise AIError("未配置 DeepSeek API Key")
    base_url = cfg["base_url"]
    model = cfg["model"]
    timeout = cfg["timeout"]

    url = base_url + "/chat/completions"
    try:
        assert_safe_url(url)
    except ValueError as exc:
        raise AIError(f"接口地址不安全: {exc}") from exc

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            t0 = time.monotonic()
            resp = client.post(url, json=payload, headers=headers)
            cost_ms = int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError as exc:
        raise AIError(f"调用失败: {exc}") from exc
    if resp.status_code != 200:
        raise AIError(f"返回 {resp.status_code}: {resp.text[:200]}")

    # Token 用量记账（失败静默）
    try:
        from .docgen.ai import log_ai_usage

        log_ai_usage(db, scene, model, resp.json(), cost_ms, user_id=user_id, order_id=order_id)
    except Exception:  # noqa: BLE001
        pass

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AIError("响应解析失败") from exc


def analyze_title(db: Session, title: str, user_id: int | None = None) -> dict[str, Any]:
    """根据论文题目推荐项目类型、技术栈、难度参考（技能 key: title_analyze）。"""
    default = (
        "你是毕设接单系统的智能助手。根据论文题目，判断项目类型（纯程序设计/纯论文/论文+设计）和推荐技术栈。"
        "只输出 JSON，不要其他文字。"
    )
    system = skill_prompt(db, "title_analyze", default)
    user = f"""题目：{title}

请分析并输出 JSON：
{{
  "project_type": "program|thesis|thesis_program",
  "project_type_reason": "一句话理由",
  "suggested_tech": "推荐技术栈（必须与题目指明的语言/框架一致）",
  "difficulty": "简单|中等|偏难",
  "suggested_quality": "white|green|blue",
  "keywords": ["关键词1", "关键词2"]
}}

判断规则：
- 只要论文不要程序（纯理论/法律/会计/文学） → thesis
- 要程序不要论文 → program
- 毕业设计最常见的"论文+系统开发" → thesis_program
- 推荐技术栈必须与题目匹配：题目含 Python/爬虫/数据分析 → Python 系（如 Requests/Scrapy+pandas+Flask/ECharts 或 Django）；
  题目含 SpringBoot/Java → Java 系；题目含微信小程序 → 小程序+后端；禁止推荐与题目冲突的技术栈"""

    raw = _chat(db, system, user, scene="title", user_id=user_id)
    try:
        # 尝试去掉可能的 markdown 代码块标记
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"project_type": "thesis", "project_type_reason": "AI 分析失败，默认纯论文", "suggested_tech": "", "difficulty": "", "suggested_quality": "white", "keywords": []}


def order_summary(db: Session, order_data: dict, user_id: int | None = None) -> str:
    """生成订单的智能摘要（用于详情页顶部；技能 key: order_summary）。"""
    default = "你是毕设项目的项目经理，用简洁的中文总结订单状态。不超过 80 字。"
    system = skill_prompt(db, "order_summary", default)
    user = f"""订单信息：
- 单号：{order_data.get('id')}
- 题目：{order_data.get('title')}
- 项目类型：{order_data.get('project_type')}
- 状态：{order_data.get('status')}
- 品质：{order_data.get('quality')}
- 期限：{order_data.get('deadline') or '未设置'}
- 部署：{order_data.get('deploy_status')}

请用一句话概括当前进度和下一步建议。"""

    return _chat(db, system, user, max_tokens=200, scene="summary",
                 order_id=order_data.get("id"), user_id=user_id)
