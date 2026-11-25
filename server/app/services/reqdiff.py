"""需求书版本对比：结构化九章 → 扁平条目 → SequenceMatcher 段级差异。

输出条目：{chapter, heading, label, kind: changed|added|removed, old, new}
供前端红绿高亮展示"哪段什么时候改的、改前改后"。
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher

CHAPTER_ORDER = [
    ("goal", "一、项目目标"),
    ("scope", "二、建设范围"),
    ("roles", "三、用户角色"),
    ("scenarios", "四、业务场景"),
    ("functions", "五、功能需求"),
    ("rules", "六、业务规则"),
    ("data_scope", "七、数据范围"),
    ("tech", "八、技术方案"),
    ("database", "九、数据库设计"),
]


def _flatten(chapters: dict, key: str) -> list[tuple[str, str]]:
    """把某章内容拍平为 [(条目标签, 文本)]，文本用于比对。"""
    ch = (chapters or {}).get(key) or {}
    out: list[tuple[str, str]] = []
    if key == "goal":
        for i, p in enumerate(ch.get("paragraphs") or []):
            out.append((f"段落 {i + 1}", p))
    elif key in ("scope", "scenarios", "rules", "data_scope"):
        for i, s in enumerate(ch.get("items") or []):
            out.append((f"第 {i + 1} 条", s))
    elif key == "roles":
        for r in ch.get("roles") or []:
            out.append((f"角色「{r.get('name', '?')}」", f"角色名：{r.get('name', '')}"))
            for j, p in enumerate(r.get("points") or []):
                out.append((f"「{r.get('name', '?')}」要点 {j + 1}", p))
    elif key == "functions":
        for g in ch.get("groups") or []:
            for m in g.get("modules") or []:
                out.append((f"{g.get('name', '')} / {m.get('name', '')}", f"模块：{m.get('name', '')}"))
                for j, p in enumerate(m.get("points") or []):
                    out.append((f"{g.get('name', '')} / {m.get('name', '')} · 功能 {j + 1}", p))
    elif key == "tech":
        intro = ch.get("intro")
        if intro:
            out.append(("架构说明", intro))
        for i, row in enumerate(ch.get("stack_table") or []):
            out.append((f"技术选型 {i + 1}", " | ".join(str(c) for c in row)))
        for i, s in enumerate(ch.get("structure") or []):
            text = f"{s.get('dir', '')}：{s.get('desc', '')}" if isinstance(s, dict) else " | ".join(str(c) for c in s)
            out.append((f"目录结构 {i + 1}", text))
    elif key == "database":
        intro = ch.get("intro")
        if intro:
            out.append(("总体约定", intro))
        for t in ch.get("tables") or []:
            out.append((f"数据表「{t.get('name', '?')}」", f"表：{t.get('name', '')}"))
            for j, col in enumerate(t.get("columns") or []):
                out.append((f"「{t.get('name', '?')}」字段 {j + 1}", " | ".join(str(c) for c in col)))
    return [(label, str(text)) for label, text in out]


def inline_ops(old: str, new: str) -> tuple[list[dict], list[dict]]:
    """字符级内联差异：返回 (old_ops, new_ops)，每段 {t: eq|del|ins, s: 文本}。
    前端用 del 红 / ins 绿 高亮"改了哪几个字"，代替整段红绿。"""
    sm = SequenceMatcher(None, old or "", new or "", autojunk=False)
    old_ops: list[dict] = []
    new_ops: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            old_ops.append({"t": "eq", "s": old[i1:i2]})
            new_ops.append({"t": "eq", "s": new[j1:j2]})
        elif tag == "delete":
            old_ops.append({"t": "del", "s": old[i1:i2]})
        elif tag == "insert":
            new_ops.append({"t": "ins", "s": new[j1:j2]})
        else:  # replace
            old_ops.append({"t": "del", "s": old[i1:i2]})
            new_ops.append({"t": "ins", "s": new[j1:j2]})
    return old_ops, new_ops


def diff_documents(old_doc: dict, new_doc: dict) -> list[dict]:
    """对比两份 {title, chapters} 文档，返回差异条目列表。

    mode=raw（原文直用）的文档没有章节结构：两侧任一为原文时按全文对比，
    返回单条字符级差异，避免被误报为「内容完全一致」。
    """
    results: list[dict] = []
    old_raw = (old_doc or {}).get("mode") == "raw"
    new_raw = (new_doc or {}).get("mode") == "raw"
    if old_raw or new_raw:
        old_text = str((old_doc or {}).get("raw_text") or "")
        new_text = str((new_doc or {}).get("raw_text") or "")
        if old_text == new_text:
            return results
        entry = {
            "chapter": "raw", "heading": "需求书原文", "label": "需求书原文 · 全文",
            "kind": "changed", "old": old_text, "new": new_text,
        }
        o_ops, n_ops = inline_ops(old_text, new_text)
        entry["old_ops"] = o_ops
        entry["new_ops"] = n_ops
        results.append(entry)
        return results
    old_ch = (old_doc or {}).get("chapters") or {}
    new_ch = (new_doc or {}).get("chapters") or {}
    for key, heading in CHAPTER_ORDER:
        old_items = _flatten(old_ch, key)
        new_items = _flatten(new_ch, key)
        old_texts = [t for _, t in old_items]
        new_texts = [t for _, t in new_items]
        if old_texts == new_texts:
            continue
        sm = SequenceMatcher(None, old_texts, new_texts, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            olds = old_items[i1:i2]
            news = new_items[j1:j2]
            if tag == "delete":
                for label, text in olds:
                    results.append({"chapter": key, "heading": heading, "label": f"{heading} · {label}",
                                    "kind": "removed", "old": text, "new": None})
            elif tag == "insert":
                for label, text in news:
                    results.append({"chapter": key, "heading": heading, "label": f"{heading} · {label}",
                                    "kind": "added", "old": None, "new": text})
            else:  # replace：同序号配对展示改前改后，多出的一侧按增/删处理
                pairs = max(len(olds), len(news))
                for idx in range(pairs):
                    if idx < len(olds) and idx < len(news):
                        entry = {"chapter": key, "heading": heading,
                                 "label": f"{heading} · {news[idx][0]}",
                                 "kind": "changed", "old": olds[idx][1], "new": news[idx][1]}
                        # 段落级内联差异（前端红绿字符高亮）
                        o_ops, n_ops = inline_ops(olds[idx][1], news[idx][1])
                        entry["old_ops"] = o_ops
                        entry["new_ops"] = n_ops
                        results.append(entry)
                    elif idx < len(olds):
                        results.append({"chapter": key, "heading": heading, "label": f"{heading} · {olds[idx][0]}",
                                        "kind": "removed", "old": olds[idx][1], "new": None})
                    else:
                        results.append({"chapter": key, "heading": heading, "label": f"{heading} · {news[idx][0]}",
                                        "kind": "added", "old": None, "new": news[idx][1]})
    return results


def diff_text_for_ai(diffs: list[dict]) -> str:
    lines = []
    for d in diffs[:40]:
        old = (d.get("old") or "")[:80]
        new = (d.get("new") or "")[:80]
        kind_cn = {"changed": "修改", "added": "新增", "removed": "删除"}[d["kind"]]
        lines.append(f"[{kind_cn}]{d['label']}：{old or '（空）'} → {new or '（空）'}")
    return "\n".join(lines)


def load_document(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None
