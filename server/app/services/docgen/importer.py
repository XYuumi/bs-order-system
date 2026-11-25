"""原文需求书 → 九章结构化导入（规则式解析，不改写内容）。

用途：「直接采用上传需求书」时，把原文按标题拆进九章结构，用户即可像
AI 生成稿一样逐条编辑、表格化查看与导出 Word；解析不出足够章节时
由调用方回落到原文直用（mode=raw），行为与旧版一致。

- 章节识别：中文章节序号（一、/第一章/第1章/1.）+ 关键词模糊匹配；
- 表格识别：extract.py 输出的 Markdown 表格语法（| 分隔 + |---| 行）；
- 内容原样搬运：不做任何改写、总结或补齐，未识别章节留空待用户补充。
"""
from __future__ import annotations

import re

from .template import CHAPTER_HEADINGS

# 关键词 → 章节键（按文档常见写法排序，先命中先得）
CHAPTER_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("goal", ("项目目标", "项目背景", "背景与目标", "概述", "简介", "项目介绍", "建设意义")),
    ("scope", ("建设范围", "范围", "建设内容", "内容", "总体设计", "总体方案")),
    ("roles", ("角色定义", "角色", "用户角色", "用户类型", "身份", "权限设计", "权限")),
    ("scenarios", ("业务场景", "场景", "业务流程", "流程", "用例")),
    ("functions", ("功能需求", "功能", "需求分析", "模块", "功能模块", "需求")),
    ("rules", ("业务规则", "规则", "约束", "要求", "规范", "非功能", "其他说明")),
    ("data_scope", ("数据范围", "实体", "数据描述", "数据需求", "数据项")),
    ("tech", ("技术架构", "技术选型", "架构", "技术", "选型", "运行环境", "开发环境")),
    ("database", ("数据库设计", "数据库", "表设计", "表结构", "数据表", "数据结构")),
]

# 章节序号前缀：一、/第一章/第1章/1./1、/（一）等；子级：1.1 / 1.1、
_HEAD_NUM = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百\d]+\s*[章节部分]|[一二三四五六七八九十]{1,3}|\d{1,2}|[（(]\s*[一二三四五六七八九十\d]{1,3}\s*[)）])"
    r"\s*[、.．:：]?\s*"
)
_SUB_NUM = re.compile(r"^\d{1,2}\.\d{1,2}\s*[、.．:：]?\s*")
_MD_SEP = re.compile(r"^\|(\s*:?-{2,}:?\s*\|)+$")
_BULLET = re.compile(r"^(?:[•·\-–*]|\d{1,2}[、.．)）]|[（(]\d{1,2}[)）])\s*")
# 三级编号：5.1.1（模块内子节）、二级编号：5.1（功能分组）
_SUB_NUM_3 = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{1,2}\s*[、.．:：]?\s*")
_SUB_NUM = re.compile(r"^\d{1,2}\.\d{1,2}\s*[、.．:：]?\s*")
_SQL_TYPE = re.compile(
    r"\b(VARCHAR|BIGINT|INT|INTEGER|DATETIME|DATE|TIME|TEXT|DECIMAL|CHAR|TINYINT|SMALLINT|"
    r"FLOAT|DOUBLE|BOOLEAN|BOOL|LONGTEXT|TIMESTAMP|ENUM)\b", re.I
)


def _looks_like_db_table(rows: list[list[str]]) -> bool:
    """按内容特征判断是否数据库表：任一前3行单元格含 SQL 类型关键字。"""
    flat = " ".join(c for r in rows[:3] for c in r)
    return bool(_SQL_TYPE.search(flat))


def _looks_like_stack_table(rows: list[list[str]]) -> bool:
    """技术选型表特征：表头含 层级/技术/框架/选型/版本 等字样。"""
    head = " ".join(rows[0]) if rows else ""
    return any(k in head for k in ("层级", "技术", "框架", "选型", "版本"))


def _match_chapter(line: str) -> str | None:
    """行文本是否是可识别的章节标题；返回章节键或 None。

    多章节关键词命中时取「最长命中词」对应的章节——
    如「数据范围」应归 data_scope 而不是被 scope 的短词「范围」抢走。
    带子级编号（如 9.1 用户表）的行是节标题不是章标题，跳过。
    """
    text = line.strip()
    if not text or len(text) > 30:
        return None
    if any(text.endswith(c) for c in "。！？；，,."):
        return None
    if _SUB_NUM.match(text):
        return None  # 子级编号（9.1、3.2 等）不是章标题
    m = _HEAD_NUM.match(text)
    if not m:
        return None
    rest = text[m.end():].strip()
    if not rest or len(rest) > 24:
        return None
    best_key, best_len = None, 0
    for key, words in CHAPTER_KEYWORDS:
        for w in words:
            if w in rest and len(w) > best_len:
                best_key, best_len = key, len(w)
    return best_key


def _is_sub_heading(line: str) -> str | None:
    """子级标题；返回去序号标题或 None。

    三级编号（5.1.1）→ 模块名；二级编号（5.1）→ 分组名；
    带编号的行放宽到 60 字符（数据库表名含英文时较长）。
    """
    text = line.strip()
    if not text:
        return None
    # 三级编号（5.1.1 xxx）优先匹配
    if _SUB_NUM_3.match(text):
        if len(text) > 60:
            return None
        return _SUB_NUM_3.sub("", text).strip(" ：:") or None
    # 二级编号（5.1 xxx / 9.1 xxx）
    if _SUB_NUM.match(text):
        if len(text) > 60 or _match_chapter(text):
            return None
        return _SUB_NUM.sub("", text).strip(" ：:") or None
    if len(text) > 30 or _match_chapter(text):
        return None
    # 短行以冒号结尾 → 子标题
    if len(text) <= 16 and text.endswith(("：", ":")) and not _BULLET.match(text):
        return text.rstrip(" ：:")
    return None


def _is_group_heading(line: str) -> str | None:
    """二级编号（5.1、5.2）在功能章节中是分组标题（如"5.1 管理员端功能"）。"""
    text = line.strip()
    if not text or _SUB_NUM_3.match(text):
        return None
    if _SUB_NUM.match(text) and not _match_chapter(text) and len(text) <= 60:
        return _SUB_NUM.sub("", text).strip(" ：:") or None
    return None


def _split_md_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells, buf, esc = [], [], False
    for ch in body:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _parse_md_table(lines: list[str]) -> list[list[str]] | None:
    """Markdown 表格块 → 行列表；不合法（缺分隔行）返回 None。"""
    if len(lines) < 2 or not all(l.strip().startswith("|") for l in lines):
        return None
    if not _MD_SEP.match(lines[1].strip()):
        return None
    rows = [_split_md_row(l) for l in lines[2:]]
    return [r for r in rows if any(c for c in r)] or None


def text_to_doc(title: str, text: str) -> dict | None:
    """把需求书原文解析为九章结构文档；识别度不足（<2 章）返回 None。"""
    lines = str(text or "").splitlines()
    doc = {
        "title": f"{title}需求书",
        "mode": "imported",  # 结构化导入：与 ai/manual 同渲染路径，可编辑
        "chapters": {
            "goal": {"heading": CHAPTER_HEADINGS["goal"], "paragraphs": []},
            "scope": {"heading": CHAPTER_HEADINGS["scope"], "items": []},
            "roles": {"heading": CHAPTER_HEADINGS["roles"], "roles": []},
            "scenarios": {"heading": CHAPTER_HEADINGS["scenarios"], "items": []},
            "functions": {"heading": CHAPTER_HEADINGS["functions"], "groups": []},
            "rules": {"heading": CHAPTER_HEADINGS["rules"], "items": []},
            "data_scope": {"heading": CHAPTER_HEADINGS["data_scope"], "items": []},
            "tech": {"heading": CHAPTER_HEADINGS["tech"], "intro": "", "stack_table": [], "structure": []},
            "database": {"heading": CHAPTER_HEADINGS["database"], "intro": "", "tables": []},
        },
    }
    ch = doc["chapters"]
    cur: str | None = None          # 当前章节键
    cur_module: dict | None = None  # functions 当前模块
    cur_role: dict | None = None    # roles 当前角色
    db_table_name: str | None = None  # database 最近一个子标题（表名）
    seen: set[str] = set()
    first_content = True
    i, n = 0, len(lines)

    def _new_module(name: str) -> dict:
        if not ch["functions"]["groups"]:
            ch["functions"]["groups"].append({"name": "功能需求", "modules": []})
        m = {"name": name[:30], "points": []}
        ch["functions"]["groups"][-1]["modules"].append(m)
        return m

    role_def = re.compile(r"^(.{1,12})\s*[：:]\s*(.+)$")

    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        # Markdown 表格块
        if stripped.startswith("|"):
            block = [line]
            j = i + 1
            while j < n and lines[j].strip().startswith("|"):
                block.append(lines[j].rstrip())
                j += 1
            rows = _parse_md_table(block)
            if rows:
                first = rows[0][0] if rows[0] else ""
                if _looks_like_db_table(rows):
                    # 优先用前置子标题（如"9.1 用户表（sys_user）"）作表名
                    if db_table_name:
                        name = db_table_name
                        db_table_name = None  # 用完即清，下一张表重新取
                    else:
                        name = first if first and ("表" in first or len(first) <= 20) else f"数据表{len(ch['database']['tables']) + 1}"
                    ch["database"]["tables"].append({"name": name[:60], "columns": rows})
                elif cur == "tech" and not ch["tech"]["stack_table"] and (_looks_like_stack_table(rows) or cur == "tech"):
                    ch["tech"]["stack_table"] = rows
                elif cur == "roles":
                    for r in rows[:8]:
                        if r and r[0]:
                            ch["roles"]["roles"].append({"name": r[0][:20], "points": [c for c in r[1:] if c][:4]})
                elif _looks_like_stack_table(rows):
                    ch["tech"]["stack_table"] = rows
                else:
                    ch["data_scope"]["items"].extend("；".join(c for c in r if c) for r in rows)
            i = j
            continue

        # 章节标题
        key = _match_chapter(stripped)
        if key:
            cur = key
            seen.add(key)
            cur_module = None
            cur_role = None
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # 子级标题 → functions 分组/模块 / roles 角色 / database 表名
        sub = _is_sub_heading(stripped)
        if sub:
            if cur == "functions":
                # 二级编号（5.1）→ 新分组；三级编号（5.1.1）→ 新模块
                grp = _is_group_heading(stripped)
                if grp:
                    ch["functions"]["groups"].append({"name": grp[:30], "modules": []})
                    cur_module = None
                else:
                    cur_module = _new_module(sub)
            elif cur == "roles":
                cur_role = {"name": sub[:20], "points": []}
                ch["roles"]["roles"].append(cur_role)
                cur_module = None
            elif cur == "database":
                # 记录子标题作为下一个数据库表的名称（如"9.1 用户表（sys_user）"）
                db_table_name = sub
                if not ch["database"]["intro"]:
                    ch["database"]["intro"] = sub
            # tech 章节的子标题（8.1 技术选型 / 8.2 项目结构）是节标签，不进 intro
            i += 1
            continue

        # 角色章节：短行（≤6字）且非编号/非列点 → 新角色名（如"巡检员"、"系统管理员"）
        if cur == "roles" and len(stripped) <= 8 and not _BULLET.match(stripped) and not stripped.startswith("|"):
            cur_role = {"name": stripped[:20], "points": []}
            ch["roles"]["roles"].append(cur_role)
            i += 1
            continue

        # 文档自身标题（首行且含“需求书”）不进正文
        if first_content and "需求书" in stripped and len(stripped) <= 40:
            first_content = False
            i += 1
            continue
        first_content = False

        item = _BULLET.sub("", stripped)

        if cur in (None, "goal"):
            ch["goal"]["paragraphs"].append(stripped)
        elif cur == "scope" or cur == "rules" or cur == "scenarios" or cur == "data_scope":
            ch[cur]["items"].append(item)
        elif cur == "roles":
            m = role_def.match(stripped)
            if m and (cur_role is None or m.group(1).strip() != cur_role["name"]):
                cur_role = {"name": m.group(1).strip()[:20], "points": [m.group(2).strip()]}
                ch["roles"]["roles"].append(cur_role)
            elif m and cur_role is not None:
                cur_role["points"].append(m.group(2).strip())
            elif cur_role is not None:
                cur_role["points"].append(item)
            else:
                cur_role = {"name": item[:20], "points": []}
                ch["roles"]["roles"].append(cur_role)
        elif cur == "functions":
            mod = cur_module if cur_module is not None else _new_module("功能点")
            mod["points"].append(item)
        elif cur == "tech":
            # 疑似目录路径行（如 backend/：描述 或 frontend/src/ 描述）归入项目结构
            _m = re.match(r"^([\w./\\-]+)[：:]\s*(.+)$", stripped)
            if _m:
                ch["tech"]["structure"].append({"dir": _m.group(1)[:50], "desc": _m.group(2)[:100]})
            elif re.match(r"^[\w./\\-]+\s+\S", stripped) and "/" in stripped.split()[0]:
                parts = stripped.split(None, 1)
                ch["tech"]["structure"].append({"dir": parts[0][:50], "desc": (parts[1] if len(parts) > 1 else "")[:100]})
            else:
                ch["tech"]["intro"] = (ch["tech"]["intro"] + ("。" if ch["tech"]["intro"] and not ch["tech"]["intro"].endswith("。") else "") + stripped)
        elif cur == "database":
            ch["database"]["intro"] = (ch["database"]["intro"] + ("。" if ch["database"]["intro"] and not ch["database"]["intro"].endswith("。") else "") + stripped)
        i += 1

    # 识别度：至少两个明确章节，或一个章节 + 至少一张表
    if len(seen) >= 2 or (len(seen) == 1 and (ch["tech"]["stack_table"] or ch["database"]["tables"])):
        return doc
    return None
