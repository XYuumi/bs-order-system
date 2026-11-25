"""原始需求文档文本提取：txt/md/json 直读，docx 走 python-docx，pdf 走 pypdf（可选依赖）。

“本系统格式”= 能按九章 chapters 结构解析的 JSON（如之前导出的需求书），
这种文件无需 AI 转换，可直接导入为需求书。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from .template import CHAPTER_ORDER

ALLOWED_EXTS = {".txt", ".md", ".json", ".docx", ".pdf"}
MAX_FILE_MB = 10


def is_our_doc(obj) -> bool:
    """判断 JSON 对象是否为本系统九章需求书结构。"""
    if not isinstance(obj, dict):
        return False
    chapters = obj.get("chapters")
    return isinstance(chapters, dict) and all(k in chapters for k in CHAPTER_ORDER)


def extract_text(filename: str, data: bytes) -> tuple[str, bool]:
    """按扩展名提取文本。返回 (文本, 是否本系统格式)；不支持/解析失败抛 ValueError。"""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支持的格式「{ext or '未知'}」，请上传 Word(.docx) / PDF / TXT / Markdown / JSON 文件")
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"文件超过 {MAX_FILE_MB}MB 上限")
    if not data:
        raise ValueError("文件为空")

    if ext in (".txt", ".md"):
        return _decode_text(data), False
    if ext == ".json":
        text = _decode_text(data)
        try:
            return text, is_our_doc(json.loads(text))
        except (ValueError, TypeError):
            return text, False
    if ext == ".docx":
        return _docx_text(io.BytesIO(data)), False
    if ext == ".pdf":
        return _pdf_text(io.BytesIO(data)), False
    raise ValueError(f"不支持的格式「{ext}」")


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _docx_text(stream) -> str:
    """按文档原始顺序提取：段落保持原位，表格转 Markdown 表格语法。

    表格用 | 分隔 + |---| 分隔行的标准 Markdown 语法表达，预览与导出端
    识别该语法渲染为真正的表格（cells 内的 | 用 \\| 转义）。
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(stream)
    parts: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, doc).text.strip()
            if text:
                parts.append(text)
        elif child.tag == qn("w:tbl"):
            md = _table_to_markdown(Table(child, doc))
            if md:
                parts.append(md)
    return "\n".join(parts)


def _table_to_markdown(table) -> str:
    """docx 表格 → Markdown 表格文本。合并单元格按 python-docx 惯例重复显示。"""
    grid: list[list[str]] = []
    for row in table.rows:
        cells = []
        for c in row.cells:
            text = " ".join(c.text.split()).replace("|", "\\|")
            cells.append(text)
        grid.append(cells)
    grid = [r for r in grid if any(c for c in r)]
    if not grid:
        return ""
    ncols = max(len(r) for r in grid)
    for r in grid:  # 补齐列数，避免行间错位
        r.extend([""] * (ncols - len(r)))
    lines = ["| " + " | ".join(grid[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * ncols) + " |")
    lines.extend("| " + " | ".join(r) + " |" for r in grid[1:])
    return "\n".join(lines)


def _pdf_text(stream) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("服务器未安装 PDF 解析组件（pip install pypdf），请改传 Word/TXT 版本") from exc
    try:
        reader = PdfReader(stream)
        pages = []
        for page in reader.pages:
            t = (page.extract_text() or "").strip()
            if t:
                pages.append(t)
    except Exception as exc:  # noqa: BLE001 —— pypdf 对损坏/加密文件抛多种异常
        raise ValueError(f"PDF 解析失败: {exc}") from exc
    return "\n".join(pages)
