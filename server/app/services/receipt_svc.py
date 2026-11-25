"""订单收款凭证 PDF（代理发给客户的收款确认单，金额为成交价）。

正式排版规范：
- A4 纵向，页边距上下 22mm、左右 18mm
- 顶部：站点名 + 单号 + 日期（右对齐），下粗线
- 主体：两列表格（订单信息），底部大字金额区
- 底部：说明 + 对接人 + 系统生成标识
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from xml.sax.saxutils import escape as _xml_escape

from ..models import Order

_FONTS_READY = False
FONT = "SimSun"
FONT_BOLD = "SimHei"


def receipt_amount(order: Order) -> float:
    """收款凭证金额 = 成交价：代理（及其客户）应付的金额。写手价是内部成本，不出现在对外凭证上。"""
    return float(order.owner_price)


def _register_fonts() -> None:
    global _FONTS_READY, FONT, FONT_BOLD
    if _FONTS_READY:
        return
    candidates = [
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
        ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("WenQuanYi", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for name, path in candidates:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                continue
    names = pdfmetrics.getRegisteredFontNames()
    if "SimHei" not in names and "NotoSansCJK" not in names and "WenQuanYi" not in names:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            names = pdfmetrics.getRegisteredFontNames()
        except Exception:
            pass
    FONT_BOLD = next((n for n in ("SimHei", "NotoSansCJK", "WenQuanYi", "STSong-Light") if n in names), "Helvetica-Bold")
    FONT = "SimSun" if "SimSun" in names else FONT_BOLD
    _FONTS_READY = True


CN_NUM = "零壹贰叁肆伍陆柒捌玖"
CN_UNIT = "", "拾", "佰", "仟"
CN_GROUP = "", "万", "亿", "兆"


def amount_to_cn(amount: float) -> str:
    """金额转中文大写（精确到分），覆盖跨四位分组的零位规则。"""
    amount = round(float(amount) + 1e-9, 2)
    negative = amount < 0
    amount = abs(amount)
    integer = int(amount)
    cents = int(round((amount - integer) * 100))
    if integer == 0 and cents == 0:
        return "零元整"

    def four_digits(n: int) -> str:
        parts: list[str] = []
        zero_pending = False
        for i in range(3, -1, -1):
            d = n // (10 ** i) % 10
            if d == 0:
                if parts:
                    zero_pending = True
            else:
                if zero_pending:
                    parts.append("零")
                    zero_pending = False
                parts.append(CN_NUM[d] + CN_UNIT[i])
        return "".join(parts)

    groups: list[tuple[int, int]] = []
    n, gi = integer, 0
    while n > 0:
        groups.append((n % 10000, gi))
        n //= 10000
        gi += 1
    groups.reverse()

    out = ""
    zero_pending = False
    for seg, group_index in groups:
        if seg == 0:
            if out:
                zero_pending = True
            continue
        if out and (zero_pending or seg < 1000):
            if not out.endswith("零"):
                out += "零"
        out += four_digits(seg) + CN_GROUP[group_index]
        zero_pending = False

    if not out:
        out = "零"
    result = out + "元"
    if cents == 0:
        result += "整"
    else:
        jiao, fen = divmod(cents, 10)
        if jiao:
            result += CN_NUM[jiao] + "角"
        elif fen:
            result += "零"
        if fen:
            result += CN_NUM[fen] + "分"
    return ("负" if negative else "") + result


def render_receipt(order: Order, *, site_name: str, holder_name: str | None) -> io.BytesIO:
    """生成 A4 收款凭证 PDF。"""
    _register_fonts()

    # 样式
    s_site = ParagraphStyle("site", fontName=FONT_BOLD, fontSize=12, textColor=colors.HexColor("#333333"), alignment=0)
    s_meta = ParagraphStyle("meta", fontName=FONT, fontSize=9, textColor=colors.HexColor("#666666"), alignment=2)
    s_title = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=22, textColor=colors.HexColor("#1a1a2e"), alignment=1, spaceBefore=6, spaceAfter=2)
    s_sub = ParagraphStyle("sub", fontName=FONT, fontSize=10, textColor=colors.HexColor("#888888"), alignment=1)
    s_label = ParagraphStyle("label", fontName=FONT_BOLD, fontSize=10, textColor=colors.HexColor("#444444"), leading=16)
    s_value = ParagraphStyle("value", fontName=FONT, fontSize=10, textColor=colors.HexColor("#222222"), leading=16)
    s_note = ParagraphStyle("note", fontName=FONT, fontSize=9, textColor=colors.HexColor("#888888"), leading=15)
    s_money_label = ParagraphStyle("ml", fontName=FONT_BOLD, fontSize=11, textColor=colors.HexColor("#333333"))
    s_money_num = ParagraphStyle("mn", fontName=FONT_BOLD, fontSize=18, textColor=colors.HexColor("#C0392B"), alignment=1, leading=24)
    s_money_cn = ParagraphStyle("mc", fontName=FONT, fontSize=10, textColor=colors.HexColor("#555555"), alignment=1, leading=16)
    s_holder = ParagraphStyle("holder", fontName=FONT, fontSize=10, textColor=colors.HexColor("#333333"))
    s_stamp = ParagraphStyle("stamp", fontName=FONT, fontSize=8, textColor=colors.HexColor("#AAAAAA"), alignment=1)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )

    cat_cn = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}.get(order.project_type, order.project_type or "")
    q = order.quality

    story = []

    # ── 顶部：站点名（左）+ 编号/日期（右） ──
    top = Table(
        [[Paragraph(_xml_escape(str(site_name or "")), s_site), Paragraph(f"编号：{_xml_escape(str(order.id))}", s_meta)],
         [Paragraph("", s_site), Paragraph(f"日期：{datetime.now().strftime('%Y年%m月%d日')}", s_meta)]],
        colWidths=[doc.width / 2, doc.width / 2],
    )
    top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(top)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 8 * mm))

    # ── 标题 ──
    story.append(Paragraph("服务收款凭证", s_title))
    story.append(Paragraph("SERVICE PAYMENT RECEIPT", s_sub))
    story.append(Spacer(1, 10 * mm))

    # ── 订单信息表（两列 label-value） ──
    info_rows = [
        [Paragraph("项目名称", s_label), Paragraph(_xml_escape(str(order.title or "")), s_value), "", ""],
        [Paragraph("服务类型", s_label), Paragraph(_xml_escape(str(cat_cn or "")), s_value), Paragraph("服务品质", s_label), Paragraph(_xml_escape(str(q.name if q else "-")), s_value)],
        [Paragraph("订单编号", s_label), Paragraph(_xml_escape(str(order.id)), s_value), Paragraph("交付期限", s_label), Paragraph(_xml_escape(str(order.deadline or "按约定")), s_value)],
    ]
    info_table = Table(info_rows, colWidths=[26 * mm, doc.width / 2 - 26 * mm, 26 * mm, doc.width / 2 - 26 * mm])
    info_table.setStyle(TableStyle([
        ("SPAN", (1, 0), (3, 0)),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F6F8")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#F5F6F8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5D8DE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10 * mm))

    # ── 金额区 ──
    amount = receipt_amount(order)
    story.append(Paragraph("应收金额（人民币）", s_money_label))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"¥ {amount:.2f}", s_money_num))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(amount_to_cn(amount), s_money_cn))
    story.append(Spacer(1, 10 * mm))

    # ── 说明 ──
    story.append(Paragraph("说明：", s_label))
    story.append(Spacer(1, 1 * mm))
    for note in [
        "1. 本凭证用于确认上述服务项目的应收款项，请以对接人提供的收款账户为准；",
        "2. 付款后请保留本凭证，如需发票/收据请与对接人沟通；",
        "3. 交付内容（演示视频、程序包等）将以在线交付链接形式提供，链接请勿转发无关人员。",
    ]:
        story.append(Paragraph(note, s_note))
    story.append(Spacer(1, 16 * mm))

    # ── 底部：对接人 + 生成标识 ──
    bottom = Table([
        [Paragraph(f"服务对接人：{_xml_escape(str(holder_name or '—'))}", s_holder), Paragraph("", s_holder)],
        [Paragraph("", s_holder), Paragraph("（本凭证由系统自动生成）", s_stamp)],
    ], colWidths=[doc.width / 2, doc.width / 2])
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(bottom)

    doc.build(story)
    buf.seek(0)
    return buf
