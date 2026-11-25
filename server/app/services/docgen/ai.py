"""DeepSeek 需求书生成：题目 → 九章结构 JSON（与模板同 Schema）。"""
from __future__ import annotations

import json

import httpx
import re
import time
from sqlalchemy.orm import Session

from ...config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_TIMEOUT
from ...urlguard import assert_safe_url
from ..settings_svc import get_setting
from .template import CHAPTER_ORDER, build_template_doc, normalize_doc

SYSTEM_PROMPT = (
    "你是一名资深的计算机专业毕业设计需求分析师，擅长为本科毕设定制开发需求书。"
    "你写的需求书结构规范、用词书面、要点动词开头、贴合题目业务域，功能粒度适合本科毕业设计工作量。"
    "你必须只输出一个 JSON 对象，不要输出任何解释性文字或 Markdown 代码块。"
)

SCHEMA_PROMPT = """请为题目「{title}」编写完整的开发需求书，技术栈偏好：{tech}。输出严格符合以下 JSON 结构（所有字段为必填，全部使用中文书面语）：
{{
  "title": "《题目》需求书",
  "chapters": {{
    "goal": {{"paragraphs": ["3~4 段项目目标文字，每段 80~150 字，覆盖：业务背景与痛点、业务闭环与技术组合、毕业设计定位"]}},
    "scope": {{"items": ["3~5 条建设范围，按 前台用户端/后台管理端/后端服务/数据存储 逐条划分"]}},
    "roles": {{"roles": [{{"name": "角色名", "points": ["4~9 条以动词开头的职责要点"]}}]}},
    "scenarios": {{"items": ["恰好 10 条端到端核心业务场景，覆盖 建档→流转→审核→统计 故事线"]}},
    "functions": {{"groups": [
        {{"name": "前台用户端功能", "modules": [{{"name": "模块名", "points": ["3~6 条『支持…』开头的功能点"], "note": "可选，范围划界说明"}}]}},
        {{"name": "后台管理端功能", "modules": [同上]}}
    ]}},
    "rules": {{"items": ["10~16 条全局业务规则，覆盖密码加密、权限隔离、状态流转（待审核—已通过—已驳回）、唯一性校验、统计口径等"]}},
    "data_scope": {{"items": ["每个数据实体一行，格式『实体名：字段1、字段2、…』，8~10 行"]}},
    "tech": {{
      "intro": "一段技术架构说明",
      "stack_table": [["层级", "技术选型", "版本说明"] x 8~12 行，必须与给定技术栈偏好一致],
      "structure": [{{"dir": "目录名", "desc": "该目录职责说明"}} x 5~8 项，覆盖 backend/frontend 或 src/webapp、sql、docs、部署脚本]
    }},
    "database": {{
      "intro": "数据库总体约定（MySQL 8.0、InnoDB、utf8mb4、BIGINT 自增主键、审计字段）",
      "tables": [{{"name": "中文名（英文表名）", "columns": [["字段名", "类型", "说明"] x 6~12 行]}} x 8~10 张表，必须贴合题目业务域命名]
    }}
  }}
}}

硬性要求：
1. 功能模块必须贴合题目业务域（前台 6~8 个、后台 6~8 个模块），禁止出现与题目无关的通用凑数模块；
2. 数据库表必须为该题目定制（如题目是宠物医院则出 pet/owner/appointment 等表），禁止用 biz_info 这类泛型表名；
3. 技术选型必须与题目匹配（题目为准）：题目指明的语言/框架/平台（如 Python、Django、Flask、SpringBoot、JSP、微信小程序、Swing 等）必须作为技术栈核心；{tech_rule}
4. 要点句式统一：功能点以「支持/查看/提供」开头，角色职责以动词开头；
5. 全文不出现价格、工期、交付物、公司署名等商务信息。{context_blocks}"""


def _tech_rules(tech_stack: str | None, has_context: bool) -> tuple[str, str]:
    """返回 (tech 展示值, 硬性要求第 3 条补充)。技术栈留空时由 AI 按题目自行选型，不再默认 SpringBoot。"""
    tech = (tech_stack or "").strip()
    if tech:
        return tech, f"给定技术栈偏好为「{tech}」，若与题目指明的语言/平台冲突，必须以题目为准并采用与题目一致的技术组合。"
    if has_context:
        return "未指定", (
            "技术栈未指定：请根据题目与客户原始需求选择最合适的技术组合，"
            "题目指明语言/框架/平台时必须以其为核心（如题目含 Python 则用 Python 系技术栈）。"
        )
    return "未指定（由你按题目选型）", \
        "技术栈未指定：请根据题目选择最合适的技术组合，题目指明语言/框架/平台时必须以其为核心（如题目含 Python 则用 Python 系技术栈）。"


class AIGenerationError(Exception):
    pass


def _post_json(client: httpx.Client, url: str, *, headers: dict, payload: dict):
    """POST 并对 DeepSeek 网关的瞬时性 400（Model Not Exist）自动重试一次。

    该错误在密钥/模型名均正确时也会偶发（实测同参数重试即成功），
    属供应商侧抖动；只重试一次、只认这一种错误文本，其余原样返回。
    """
    resp = client.post(url, json=payload, headers=headers)
    if resp.status_code == 400 and "model not exist" in resp.text.lower():
        time.sleep(2)
        resp = client.post(url, json=payload, headers=headers)
    return resp


def log_ai_usage(db, scene: str, model: str, resp_json: dict, duration_ms: int,
                 user_id: int | None = None, order_id: str | None = None) -> None:
    """DeepSeek 响应记账（usage 字段），失败静默（不阻塞业务）。调用方负责 commit。"""
    if db is None:
        return
    try:
        usage = (resp_json or {}).get("usage") or {}
        from ...models import AiUsage

        db.add(AiUsage(
            scene=scene[:30], model=model[:60],
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            duration_ms=int(duration_ms), user_id=user_id, order_id=order_id,
        ))
    except Exception:  # noqa: BLE001
        pass


def deepseek_chat(db: Session, system: str, user_content: str, *, max_tokens: int = 2048, temperature: float = 0.7, scene: str = "chat", order_id: str | None = None, user_id: int | None = None, json_mode: bool = False) -> str:
    """通用 DeepSeek 对话：返回纯文本 content（需求书生成之外的场景使用，如经营周报）。"""
    cfg = get_ai_config(db)
    if not cfg["key"]:
        raise AIGenerationError("未配置 DeepSeek API Key（可在系统设置页填写）")

    url = cfg["base_url"] + "/chat/completions"
    try:
        assert_safe_url(url)
    except ValueError as exc:
        raise AIGenerationError(f"DeepSeek 接口地址不安全: {exc}") from exc

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            t0 = time.monotonic()
            resp = _post_json(client, url, headers=headers, payload=payload)
            cost_ms = int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError as exc:
        raise AIGenerationError(f"调用 DeepSeek 失败: {exc}") from exc

    if resp.status_code != 200:
        raise AIGenerationError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:300]}")

    try:
        body = resp.json()
        log_ai_usage(db, scene, cfg["model"], body, cost_ms, order_id=order_id, user_id=user_id)
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise AIGenerationError("DeepSeek 响应解析失败") from exc


def deepseek_raw(db: Session, messages: list[dict], *, tools: list[dict] | None = None,
                 max_tokens: int = 2048, temperature: float = 0.7, scene: str = "chat", user_id: int | None = None) -> dict:
    """原生对话：完整 messages（可含 tool 结果），可携带 tools 做函数调用，返回 message 对象。"""
    cfg = get_ai_config(db)
    if not cfg["key"]:
        raise AIGenerationError("未配置 DeepSeek API Key（可在系统设置页填写）")

    url = cfg["base_url"] + "/chat/completions"
    try:
        assert_safe_url(url)
    except ValueError as exc:
        raise AIGenerationError(f"DeepSeek 接口地址不安全: {exc}") from exc

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            t0 = time.monotonic()
            resp = _post_json(client, url, headers=headers, payload=payload)
            cost_ms = int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError as exc:
        raise AIGenerationError(f"调用 DeepSeek 失败: {exc}") from exc

    if resp.status_code != 200:
        raise AIGenerationError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:300]}")

    try:
        body = resp.json()
        log_ai_usage(db, scene, cfg["model"], body, cost_ms, user_id=user_id)
        return body["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as exc:
        raise AIGenerationError("DeepSeek 响应解析失败") from exc


def get_ai_config(db: Session) -> dict:
    key = get_setting(db, "deepseek_api_key") or DEEPSEEK_API_KEY
    base_url = get_setting(db, "deepseek_base_url") or DEEPSEEK_BASE_URL
    model = get_setting(db, "deepseek_model") or DEEPSEEK_MODEL
    try:
        timeout = int(get_setting(db, "deepseek_timeout") or DEEPSEEK_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEEPSEEK_TIMEOUT
    # 防御历史脏配置：0/负数/超大值都会让 AI 调用立即失败或长期挂起。
    timeout = min(max(timeout, 5), 600)
    return {"key": key, "base_url": base_url.rstrip("/"), "model": model, "timeout": timeout}


def ai_available(db: Session) -> bool:
    return bool(get_ai_config(db)["key"])


def _loads_repair(text: str):
    """宽松 JSON 解析：先标准解析；失败则修复模型输出常见问题后重试。

    覆盖：markdown 代码栅栏、max_tokens 截断（字符串/括号未闭合）、
    字符串内裸换行/制表符、尾逗号。返回 (obj|None, 策略名)。
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0].strip()
    try:
        return json.loads(s), "direct"
    except json.JSONDecodeError:
        pass

    # 1) 截断修复：单遍扫描括号栈与字符串状态，闭合未完成的结构
    stack = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
    repaired = s
    if in_str:  # 字符串被截断：去掉结尾悬空反斜杠/替换符后补引号
        if repaired.endswith("\\"):
            repaired = repaired[:-1]
        repaired = repaired.rstrip("\ufffd")
        repaired += '"'
    if repaired.rstrip().endswith(","):
        repaired = repaired.rstrip()[:-1]
    repaired = repaired.rstrip()
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    try:
        return json.loads(repaired), "truncation-repair"
    except json.JSONDecodeError:
        pass

    # 2) 字符串内裸控制字符：把 "..." 内部的换行/制表/引号替换为转义形式
    def _escape_raw(m):
        inner = m.group(1)
        inner = inner.replace("\\", "\\\\").replace('"', '\\"')
        inner = inner.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + inner + '"'

    escaped = re.sub(r'"((?:[^"\\]|\\.)*)"', _escape_raw, repaired, flags=re.S)
    try:
        return json.loads(escaped), "escape-repair"
    except json.JSONDecodeError:
        return None, "failed"


def generate_by_ai(db: Session, title: str, tech_stack: str | None, *, order_id: str | None = None,
                   user_id: int | None = None, source_text: str | None = None,
                   notes: str | None = None) -> dict:
    cfg = get_ai_config(db)
    if not cfg["key"]:
        raise AIGenerationError("未配置 DeepSeek API Key（可在系统设置页填写）")

    url = cfg["base_url"] + "/chat/completions"
    try:
        assert_safe_url(url)
    except ValueError as exc:
        raise AIGenerationError(f"DeepSeek 接口地址不安全: {exc}") from exc

    # 原始需求资料（上传文档全文 / 口头需求要点）：有则作为生成基准，题目只作辅助
    blocks = ""
    src = (source_text or "").strip()
    if src:
        if len(src) > 8000:
            src = src[:8000] + "\n……（原文过长，此处截断）"
        blocks += (
            "\n\n客户原始需求文档内容（需求书必须完整覆盖其中的功能、角色与数据要求，"
            "客户没提到但毕设必需的基础能力（登录、权限、日志等）可自行补齐）：\n" + src
        )
    nts = (notes or "").strip()
    if nts:
        blocks += "\n\n客户需求要点（口头描述总结，必须逐条体现）：\n" + nts
    if blocks:
        blocks += "\n\n以客户需求为准，题目仅用于把握业务域与措辞；不要照抄原文口语，统一转为规范书面语。"

    tech, tech_rule = _tech_rules(tech_stack, has_context=bool(blocks))
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": SCHEMA_PROMPT.format(
                title=title, tech=tech, tech_rule=tech_rule, context_blocks=blocks,
            )},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 1.0,
        "max_tokens": 8192,
    }
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            t0 = time.monotonic()
            resp = _post_json(client, url, headers=headers, payload=payload)
            cost_ms = int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError as exc:
        raise AIGenerationError(f"调用 DeepSeek 失败: {exc}") from exc

    if resp.status_code != 200:
        raise AIGenerationError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        log_ai_usage(db, "docgen", cfg["model"], data, cost_ms, user_id=user_id, order_id=order_id)
        content = data["choices"][0]["message"]["content"]
        raw, strategy = _loads_repair(content)
        if raw is None:
            # 修复失败：带加强转义指令重试一次（模型偶发在长文本里输出裸引号/换行）
            retry_payload = dict(payload)
            retry_payload["messages"] = [
                {"role": "system", "content": SYSTEM_PROMPT + ' 所有字符串内的引号必须转义为 \\"，禁止裸换行。'},
                payload["messages"][1],
            ]
            try:
                with httpx.Client(timeout=cfg["timeout"]) as client:
                    resp2 = client.post(url, json=retry_payload, headers=headers)
            except httpx.HTTPError as exc:
                raise AIGenerationError(f"DeepSeek 重试失败: {exc}") from exc
            if resp2.status_code == 200:
                data2 = resp2.json()
                log_ai_usage(db, "docgen_retry", cfg["model"], data2, 0, user_id=user_id, order_id=order_id)
                raw, strategy = _loads_repair(data2["choices"][0]["message"]["content"])
                if raw is not None:
                    strategy += "+retry"
        if raw is None:
            raise AIGenerationError(
                f"DeepSeek 响应解析失败（已尝试修复与重试，内容长度 {len(content)}，"
                f"疑似超出 max_tokens 截断）")
    except AIGenerationError:
        raise
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise AIGenerationError(f"DeepSeek 响应解析失败: {exc}") from exc

    # 归一化：缺失章节模板兜底，保证结构完整（截断修复产生的缺章在此补齐）
    return normalize_doc(raw, title, tech_stack)


REVISE_SYSTEM_PROMPT = (
    "你是一名资深的计算机专业毕业设计需求分析师。用户会给你一份开发需求书的 JSON 文档和一条修改要求，"
    "你需要严格按照修改要求做最小化修改：修改要求未涉及的内容必须逐字保留，禁止顺手润色或重写。"
    "你必须只输出修改后的完整 JSON 对象（结构与输入完全一致），不要输出任何解释性文字或 Markdown 代码块。"
)

REVISE_USER_PROMPT = """请按下面的修改要求修订需求书。

系统题目：{title}
技术栈偏好：{tech}

修改要求：
{instruction}

当前需求书 JSON：
{document}

硬性要求：
1. 输出修改后的完整文档 JSON，结构与输入完全一致（title + 九个章节键不得增删改键名）；
2. 只改动修改要求涉及的部分，其余章节与条目必须原样保留；
3. 新增内容遵守原有句式规范：功能点以「支持/查看/提供」开头，角色职责以动词开头，全部使用中文书面语；
4. 不出现价格、工期、交付物、公司署名等商务信息。"""


def revise_by_ai(db: Session, document: dict, instruction: str, title: str, tech_stack: str | None,
                 *, order_id: str | None = None, user_id: int | None = None) -> dict:
    """按用户修改建议让 AI 修订现有需求书，返回修订后的文档（不落库，由调用方决定保存时机）。"""
    cfg = get_ai_config(db)
    if not cfg["key"]:
        raise AIGenerationError("未配置 DeepSeek API Key（可在系统设置页填写）")

    base = normalize_doc(document, title, tech_stack)
    url = cfg["base_url"] + "/chat/completions"
    try:
        assert_safe_url(url)
    except ValueError as exc:
        raise AIGenerationError(f"DeepSeek 接口地址不安全: {exc}") from exc

    tech = (tech_stack or "").strip() or "未指定"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": REVISE_SYSTEM_PROMPT},
            {"role": "user", "content": REVISE_USER_PROMPT.format(
                title=title, tech=tech, instruction=instruction.strip(),
                document=json.dumps(base, ensure_ascii=False),
            )},
        ],
        "response_format": {"type": "json_object"},
        # 修订任务要的是精准最小改动而非创作，低温度更稳
        "temperature": 0.2,
        "max_tokens": 8192,
    }
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            t0 = time.monotonic()
            resp = _post_json(client, url, headers=headers, payload=payload)
            cost_ms = int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError as exc:
        raise AIGenerationError(f"调用 DeepSeek 失败: {exc}") from exc

    if resp.status_code != 200:
        raise AIGenerationError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        log_ai_usage(db, "docrevise", cfg["model"], data, cost_ms, order_id=order_id, user_id=user_id)
        content = data["choices"][0]["message"]["content"]
        raw, _strategy = _loads_repair(content)
    except (KeyError, IndexError, ValueError) as exc:
        raise AIGenerationError("DeepSeek 响应解析失败") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("chapters"), dict):
        raise AIGenerationError("AI 修订结果结构异常，已放弃应用（原文档未受影响）")

    # 防截断/丢章：AI 未返回的章节回退用原文档章节（而非通用模板），
    # 归一化后若某章被模板兜底替换而原文档并非模板内容，也回退为原文档该章。
    raw_chapters = raw["chapters"]
    merged = {"title": raw.get("title") or base.get("title"), "chapters": {}}
    for key in CHAPTER_ORDER:
        src = raw_chapters.get(key)
        merged["chapters"][key] = src if isinstance(src, dict) and src else base["chapters"][key]
    result = normalize_doc(merged, title, tech_stack)
    fallback = build_template_doc(title, tech_stack)
    for key in CHAPTER_ORDER:
        if (result["chapters"][key] == fallback["chapters"][key]
                and base["chapters"].get(key) != fallback["chapters"][key]):
            result["chapters"][key] = base["chapters"][key]
    return result
