"""需求书 docx 渲染器：九章 JSON → 格式统一的 Word 文档。

排版对齐既有需求书样式：
- 正文宋体小四(12pt)、行距 1.15、段后 10 磅
- 章标题(一、~九、) 黑体 15pt 加粗 蓝 #4F81BD；二级 12pt；三级 11pt
- 技术选型/数据库设计使用三列表格，表头浅蓝底纹
- mode=raw（原文直用）：按原文逐行渲染，仅对明显是标题的行套标题样式，文字内容不做任何修改
"""
from __future__ import annotations

import io
import re

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BLUE = "4F81BD"
HEADER_FILL = "D9E2F1"
HEI = "黑体"
SONG = "宋体"

# 原文模式下按行识别标题：中文序号（一、二章…）、「第X章/节」、数字编号（1. / 1.1 / 1.1.2）且行较短
_RAW_HEADING_RE = re.compile(
    r"^(?:[一二三四五六七八九十百]+、|第[一二三四五六七八九十百\d]+[章节部分]|[一二三四五六七八九十]+\s*[、.．])"
)
_RAW_NUM_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*[、.．\s]")


def _apply_font(run, size: float, *, east: str = SONG, bold: bool = False, color: str | None = None, mono: bool = False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = "Courier New" if mono else "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), east if not mono else "Courier New")
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _heading(doc: Document, text: str, level: int, size: float):
    p = doc.add_heading("", level=level)
    p.paragraph_format.space_before = Pt({2: 18, 3: 10, 4: 8}.get(level, 8))
    p.paragraph_format.space_after = Pt({2: 10, 3: 5, 4: 4}.get(level, 4))
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    _apply_font(run, size, east=HEI, bold=True, color=BLUE)
    return p


def _body(doc: Document, text: str, *, indent_cm: float = 0.0, hanging: bool = False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = 1.15
    pf.space_after = Pt(10)
    if indent_cm:
        pf.left_indent = Cm(indent_cm)
        if hanging:
            pf.first_line_indent = Cm(-0.55)
    run = p.add_run(text)
    _apply_font(run, 12)
    return p


def _bullet(doc: Document, text: str):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = 1.15
    pf.space_after = Pt(6)
    pf.left_indent = Cm(0.85)
    pf.first_line_indent = Cm(-0.55)
    run = p.add_run("• " + text)
    _apply_font(run, 12)
    return p


def _numbered(doc: Document, no: int, text: str):
    _bullet(doc, f"{no}. {text}")


def _shade(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _table(doc: Document, headers: list[str], rows: list[list[str]], widths_cm: list[float]):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)

    for idx, (header, width) in enumerate(zip(headers, widths_cm)):
        cell = table.rows[0].cells[idx]
        cell.width = Cm(width)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _shade(cell, HEADER_FILL)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(2)
        run = p.add_run(header)
        _apply_font(run, 10.5, bold=True)

    for r in rows:
        cells = table.add_row().cells
        for idx in range(len(headers)):
            cell = cells[idx]
            cell.width = Cm(widths_cm[idx])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.space_before = Pt(2)
            run = p.add_run(str(r[idx]) if idx < len(r) else "")
            _apply_font(run, 10.5)

    # 表格后留一点间距
    tail = doc.add_paragraph()
    tail.paragraph_format.space_after = Pt(4)
    tail_run = tail.add_run("")
    _apply_font(tail_run, 6)
    return table


def _is_raw_heading(line: str) -> bool:
    """原文模式下行级标题识别：只影响样式，不改内容。"""
    text = line.strip()
    if not text or len(text) > 40:
        return False
    if _RAW_HEADING_RE.match(text):
        return True
    return bool(_RAW_NUM_HEADING_RE.match(text)) and not text.endswith(("。", "！", "？", "；", ",", "，"))


_MD_TABLE_SEP_RE = re.compile(r"^\|(\s*:?-{2,}:?\s*\|)+$")


def _split_md_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    # 仅按未转义的 | 分列，再还原单元格内的 \|
    cells, buf, escaped = [], [], False
    for ch in body:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "|":
            cells.append(buf)
            buf = []
        else:
            buf.append(ch)
    cells.append(buf)
    return ["".join(c).strip() for c in cells]


def _parse_md_table(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """识别 Markdown 表格块（首行表头 + |---| 分隔行 + 数据行）；不合法返回 None。"""
    if len(lines) < 2 or not all(l.strip().startswith("|") for l in lines):
        return None
    if not _MD_TABLE_SEP_RE.match(lines[1].strip()):
        return None
    headers = _split_md_row(lines[0])
    rows = [_split_md_row(l) for l in lines[2:]]
    return headers, rows


def _render_raw_body(doc: Document, raw_text: str) -> None:
    lines = str(raw_text or "").splitlines()
    idx = 0
    while idx < len(lines):
        text = lines[idx].rstrip()
        # Markdown 表格块：收集连续 | 开头的行，成块渲染为真正的 Word 表格
        if text.strip().startswith("|"):
            block = [text]
            j = idx + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                block.append(lines[j].rstrip())
                j += 1
            parsed = _parse_md_table(block)
            if parsed:
                headers, rows = parsed
                ncols = max(len(headers), *(len(r) for r in rows)) if rows else len(headers)
                headers += [""] * (ncols - len(headers))
                widths = [15.5 / ncols] * ncols
                _table(doc, headers, rows, widths)
                idx = j
                continue
        if not text.strip():
            # 保留空行造成的段落间隔（用小字号空段，导出更接近原文观感）
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run("")
            _apply_font(run, 6)
            idx += 1
            continue
        if _is_raw_heading(text):
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.space_before = Pt(12)
            pf.space_after = Pt(6)
            pf.line_spacing = 1.15
            run = p.add_run(text)
            _apply_font(run, 13, east=HEI, bold=True, color=BLUE)
        else:
            _body(doc, text)
        idx += 1


def render_docx(doc_data: dict, school: str | None = None) -> io.BytesIO:
    doc = Document()

    # A4 纸张与页边距
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.18)
    section.right_margin = Cm(3.18)

    # 页眉（学校名，设置里配置；留空不加）
    school_text = (school or "").strip()
    if school_text:
        hp = section.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = hp.add_run(school_text)
        _apply_font(run, 9)

    # Normal 样式基准
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

    # 文档标题
    title_p = doc.add_heading("", level=0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(12)
    run = title_p.add_run(str(doc_data.get("title", "需求书")))
    _apply_font(run, 22, east=HEI, bold=True)

    # 原文直用：逐行渲染上传的原文，仅对标题行套样式，内容不做修改
    if doc_data.get("mode") == "raw":
        _render_raw_body(doc, doc_data.get("raw_text") or "")
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    chapters = doc_data.get("chapters", {})

    # 一、项目目标
    goal = chapters.get("goal", {})
    _heading(doc, goal.get("heading", "一、项目目标"), 2, 15)
    for para in goal.get("paragraphs", []):
        _body(doc, para)

    # 二、建设范围
    scope = chapters.get("scope", {})
    _heading(doc, scope.get("heading", "二、建设范围"), 2, 15)
    for item in scope.get("items", []):
        _body(doc, item)

    # 三、角色定义
    roles = chapters.get("roles", {})
    _heading(doc, roles.get("heading", "三、角色定义"), 2, 15)
    for i, role in enumerate(roles.get("roles", []), start=1):
        _heading(doc, f"3.{i} {role.get('name', '')}", 3, 12)
        for pt in role.get("points", []):
            _bullet(doc, pt)

    # 四、核心业务场景
    scenarios = chapters.get("scenarios", {})
    _heading(doc, scenarios.get("heading", "四、核心业务场景"), 2, 15)
    for i, item in enumerate(scenarios.get("items", []), start=1):
        _numbered(doc, i, item)

    # 五、功能需求
    functions = chapters.get("functions", {})
    _heading(doc, functions.get("heading", "五、功能需求"), 2, 15)
    for gi, group in enumerate(functions.get("groups", []), start=1):
        _heading(doc, f"5.{gi} {group.get('name', '')}", 3, 12)
        for mi, module in enumerate(group.get("modules", []), start=1):
            _heading(doc, f"5.{gi}.{mi} {module.get('name', '')}", 4, 11)
            for pt in module.get("points", []):
                _bullet(doc, pt)
            note = module.get("note")
            if note:
                p = _body(doc, "说明：" + note)
                p.runs[0].font.color.rgb = RGBColor.from_string("888888")

    # 六、业务规则
    rules = chapters.get("rules", {})
    _heading(doc, rules.get("heading", "六、业务规则"), 2, 15)
    for i, item in enumerate(rules.get("items", []), start=1):
        _numbered(doc, i, item)

    # 七、数据范围
    data_scope = chapters.get("data_scope", {})
    _heading(doc, data_scope.get("heading", "七、数据范围"), 2, 15)
    for item in data_scope.get("items", []):
        _body(doc, item)

    # 八、技术架构
    tech = chapters.get("tech", {})
    _heading(doc, tech.get("heading", "八、技术架构"), 2, 15)
    if tech.get("intro"):
        _body(doc, tech["intro"])
    _heading(doc, "8.1 技术选型", 3, 12)
    _table(doc, ["层级", "技术选型", "版本说明"], tech.get("stack_table", []), [3.2, 5.6, 5.7])
    _heading(doc, "8.2 项目结构", 3, 12)
    for s in tech.get("structure", []):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.15
        pf.space_after = Pt(6)
        run = p.add_run(f"{s.get('dir', '')}")
        _apply_font(run, 10.5, mono=True)
        run2 = p.add_run(f"  {s.get('desc', '')}")
        _apply_font(run2, 10.5)
        # 长路径允许任意位置断行（Word 默认只在空格处断）
        for r in (run, run2):
            r.font.element.rPr.append(OxmlElement("w:wordWrap"))
            r.font.element.rPr[-1].set(qn("w:val"), "0")

    # 九、数据库设计
    database = chapters.get("database", {})
    _heading(doc, database.get("heading", "九、数据库设计（MySQL 8.0）"), 2, 15)
    if database.get("intro"):
        _body(doc, database["intro"])
    for i, t in enumerate(database.get("tables", []), start=1):
        _heading(doc, f"9.{i} {t.get('name', '')}", 3, 12)
        _table(doc, ["字段名", "类型", "说明"], t.get("columns", []), [4.2, 3.6, 6.7])

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
