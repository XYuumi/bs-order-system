"""交付验收单 PDF（A4 验收单：订单信息、时间线、文件清单、验收结论与防伪验证码）。

排版规范：
- A4 纵向，页边距上下 20mm、左右 18mm
- 每页斜向浅色「验收单」水印；页脚页码 + 系统生成标识
- 表格式布局，文件清单过长时自动分页并重复表头

安全边界：
- 订单数据统一走 order_view 按角色裁剪；成交价仅 admin / agent 可见，写手不出现 owner_price，
  multiplier 任何角色都不出现；
- 验证码 = HMAC-SHA256(订单号 + 验收时间, JWT_SECRET) 前 12 位大写十六进制，可离线复核。
"""
from __future__ import annotations

import hashlib
import hmac
import io
from datetime import date, datetime
from typing import Sequence
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..config import JWT_SECRET
from ..models import Order, OrderFile, User
from .order_svc import STATUS_CN, order_view

# reportlab 内置 CJK 字体，无需任何外部字体文件
FONT = "STSong-Light"
_FONT_READY = False

CATEGORY_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}
FILE_CATEGORY_CN = {"package": "程序包", "video": "演示视频", "doc": "文档", "other": "其他"}


def _register_font() -> None:
    global _FONT_READY
    if _FONT_READY:
        return
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    _FONT_READY = True


# ==================== 验证码 ====================

def accept_stamp(accepted_at: datetime | None) -> str:
    """参与签名的验收时间文本；未验收时为空串（验证码仅绑定订单号）。"""
    return accepted_at.strftime("%Y-%m-%d %H:%M:%S") if accepted_at else ""


def verification_code(order_id: str, accepted_at: datetime | None) -> str:
    """防伪验证码：HMAC-SHA256(订单号 + 验收时间, JWT_SECRET) 前 12 位大写十六进制。"""
    message = f"{order_id}{accept_stamp(accepted_at)}".encode()
    return hmac.new(JWT_SECRET.encode(), message, hashlib.sha256).hexdigest()[:12].upper()


# ==================== 文本格式化 ====================

def format_size(size: int | None) -> str:
    """字节数 → 人类可读（B/KB/MB/GB）。"""
    value = float(size or 0)
    unit = "B"
    for candidate in ("KB", "MB", "GB"):
        if value < 1024:
            break
        value /= 1024
        unit = candidate
    return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"


def _text(value: object, default: str = "—") -> str:
    """转义为 reportlab 段落可用的文本，空值显示占位符。"""
    text = str(value).strip() if value is not None else ""
    if not text:
        return default
    return _xml_escape(text).replace("\n", "<br/>")


def _fmt_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "—"


def _fmt_date(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "按约定"


def _display_user(user: User | None) -> str:
    if not user:
        return "—"
    return (user.display_name or "").strip() or user.username


# ==================== 验收单数据 ====================

def receipt_data(
    order: Order,
    *,
    role: str,
    files: Sequence[OrderFile] = (),
    now: datetime | None = None,
) -> dict:
    """构造验收单数据；价格视野复用 order_view，非 admin 不含真实价/倍率。"""
    view = order_view(order, role)
    accepted_at = order.customer_accepted_at
    generated_at = now or datetime.now()
    accepted_ip = (order.customer_accepted_ip or "").strip()

    if accepted_at:
        accepted_note = f"客户在线确认（IP {accepted_ip}）" if accepted_ip else "客户在线确认"
    else:
        accepted_note = "待客户确认"

    data = {
        "order_id": view["id"],
        "title": view["title"],
        "quality": view["quality"]["name"] or "—",
        "category": CATEGORY_CN.get(order.project_type, order.project_type or "未设置"),
        "status": STATUS_CN.get(order.status, order.status or "—"),
        "deadline": _fmt_date(order.deadline),
        "customer_info": order.customer_info or "",
        "agent": _display_user(order.agent),
        "assignee": _display_user(order.assignee),
        "generated_at": generated_at,
        "accepted": accepted_at is not None,
        "accepted_at": accepted_at,
        "accepted_ip": accepted_ip,
        "timeline": [
            {"label": "下单时间", "time": order.created_at, "note": "系统建单"},
            {"label": "开始制作", "time": order.accepted_at, "note": "状态流转"},
            {"label": "完成制作", "time": order.completed_at, "note": "状态流转"},
            {"label": "客户验收", "time": accepted_at, "note": accepted_note},
        ],
        "files": [
            {
                "name": f.original_name or "—",
                "category": FILE_CATEGORY_CN.get(f.category, f.category or "—"),
                "size": int(f.size or 0),
                "size_text": format_size(f.size),
            }
            for f in files
        ],
        "verification_code": verification_code(view["id"], accepted_at),
        "conclusion": (
            "客户已通过在线交付页确认验收，交付文件与订单内容一致，本单验收通过。"
            if accepted_at
            else "客户尚未完成在线验收确认，本单仅作交付清单留档，最终以客户确认为准。"
        ),
    }
    # 验收单面向付款方（代理/销售）与管理员：展示成交价。写手只能看交付清单，不出成交价；
    # 写手价是内部成本，任何角色都不出现在验收单上
    if role in ("admin", "agent"):
        data["owner_price"] = float(order.owner_price)
    return data


# ==================== PDF 渲染 ====================

def _decorate(canvas, doc) -> None:
    """每页装饰：斜向浅色「验收单」水印 + 页脚页码。"""
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1a1a2e"))
    canvas.setFillAlpha(0.06)
    canvas.translate(width / 2, height / 2)
    canvas.rotate(32)
    canvas.setFont(FONT, 72)
    canvas.drawCentredString(0, 0, "验收单")
    canvas.restoreState()

    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#999999"))
    canvas.drawCentredString(width / 2, 12 * mm, f"第 {doc.page} 页 · 交付验收单由系统自动生成")
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    def style(name: str, **kwargs) -> ParagraphStyle:
        kwargs.setdefault("fontName", FONT)
        kwargs.setdefault("wordWrap", "CJK")
        return ParagraphStyle(name, **kwargs)

    return {
        "site": style("site", fontSize=12, textColor=colors.HexColor("#333333")),
        "meta": style("meta", fontSize=9, textColor=colors.HexColor("#666666"), alignment=2),
        "title": style("title", fontSize=24, textColor=colors.HexColor("#1a1a2e"),
                       alignment=1, leading=30, spaceBefore=4, spaceAfter=2),
        "sub": style("sub", fontSize=9, textColor=colors.HexColor("#888888"), alignment=1),
        "section": style("section", fontSize=11, textColor=colors.HexColor("#1a1a2e"), leading=18),
        "label": style("label", fontSize=9.5, textColor=colors.HexColor("#444444"), leading=15),
        "value": style("value", fontSize=9.5, textColor=colors.HexColor("#222222"), leading=15),
        "note": style("note", fontSize=8.5, textColor=colors.HexColor("#888888"), leading=14),
        "th": style("th", fontSize=9, textColor=colors.white, leading=13),
        "td": style("td", fontSize=9, textColor=colors.HexColor("#222222"), leading=13),
        "code": style("code", fontSize=15, textColor=colors.HexColor("#C0392B"), leading=20),
        "sign": style("sign", fontSize=9.5, textColor=colors.HexColor("#333333")),
    }


def _section(title: str, s: dict[str, ParagraphStyle]) -> list:
    return [Spacer(1, 6 * mm), Paragraph(title, s["section"]), Spacer(1, 2 * mm)]


def _build_story(data: dict, doc: SimpleDocTemplate, site_name: str) -> list:
    s = _styles()
    story: list = []

    # ── 顶部：站点名（左）+ 单号/生成日期（右） ──
    top = Table(
        [
            [Paragraph(_text(site_name, "毕设接单"), s["site"]),
             Paragraph(f"单号：{_text(data['order_id'])}", s["meta"])],
            [Paragraph("", s["site"]),
             Paragraph(f"生成日期：{data['generated_at'].strftime('%Y年%m月%d日 %H:%M')}", s["meta"])],
        ],
        colWidths=[doc.width * 0.6, doc.width * 0.4],
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
    story.append(Paragraph("交付验收单", s["title"]))
    story.append(Paragraph("DELIVERY ACCEPTANCE FORM", s["sub"]))
    story.append(Spacer(1, 8 * mm))

    # ── 订单信息 ──
    info_rows = [
        [Paragraph("项目标题", s["label"]), Paragraph(_text(data["title"]), s["value"]), "", ""],
        [Paragraph("订单编号", s["label"]), Paragraph(_text(data["order_id"]), s["value"]),
         Paragraph("品质等级", s["label"]), Paragraph(_text(data["quality"]), s["value"])],
        [Paragraph("服务类型", s["label"]), Paragraph(_text(data["category"]), s["value"]),
         Paragraph("当前状态", s["label"]), Paragraph(_text(data["status"]), s["value"])],
        [Paragraph("客户信息", s["label"]), Paragraph(_text(data["customer_info"]), s["value"]), "", ""],
        [Paragraph("接单代理", s["label"]), Paragraph(_text(data["agent"]), s["value"]),
         Paragraph("制作负责人", s["label"]), Paragraph(_text(data["assignee"]), s["value"])],
        [Paragraph("交付期限", s["label"]), Paragraph(_text(data["deadline"]), s["value"]),
         Paragraph("成交价", s["label"]),
         Paragraph(f"¥ {data['owner_price']:.2f}" if "owner_price" in data else "—", s["value"])],
    ]

    info = Table(info_rows, colWidths=[24 * mm, doc.width / 2 - 24 * mm, 24 * mm, doc.width / 2 - 24 * mm])
    info_style = [
        ("SPAN", (1, 0), (3, 0)),
        ("SPAN", (1, 3), (3, 3)),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F6F8")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#F5F6F8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5D8DE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    info.setStyle(TableStyle(info_style))
    story.append(info)

    # ── 时间线 ──
    story.extend(_section("交付时间线", s))
    time_rows = [[Paragraph("节点", s["th"]), Paragraph("时间", s["th"]), Paragraph("备注", s["th"])]]
    for item in data["timeline"]:
        time_rows.append([
            Paragraph(item["label"], s["td"]),
            Paragraph(_fmt_time(item["time"]), s["td"]),
            Paragraph(_text(item["note"]), s["td"]),
        ])
    timeline = Table(time_rows, colWidths=[30 * mm, 50 * mm, doc.width - 80 * mm], repeatRows=1)
    timeline.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5D8DE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(timeline)

    # ── 文件清单 ──
    story.extend(_section("交付文件清单", s))
    file_rows = [[Paragraph("序号", s["th"]), Paragraph("文件名称", s["th"]),
                  Paragraph("分类", s["th"]), Paragraph("大小", s["th"])]]
    if data["files"]:
        for index, item in enumerate(data["files"], start=1):
            file_rows.append([
                Paragraph(str(index), s["td"]),
                Paragraph(_text(item["name"]), s["td"]),
                Paragraph(_text(item["category"]), s["td"]),
                Paragraph(_text(item["size_text"]), s["td"]),
            ])
    else:
        file_rows.append([Paragraph("—", s["td"]),
                          Paragraph("该订单暂无交付文件", s["td"]), "", ""])
    files_table = Table(
        file_rows,
        colWidths=[12 * mm, doc.width - 62 * mm, 26 * mm, 24 * mm],
        repeatRows=1,
    )
    file_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5D8DE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if not data["files"]:
        file_style.append(("SPAN", (1, 1), (3, 1)))
    files_table.setStyle(TableStyle(file_style))
    story.append(files_table)

    # ── 验收结论与验证码 ──
    story.extend(_section("验收结论与防伪验证码", s))
    box = Table(
        [
            [Paragraph("验收结论", s["label"])],
            [Paragraph(_text(data["conclusion"]), s["value"])],
            [Paragraph(f"防伪验证码：{_text(data['verification_code'])}", s["code"])],
            [Paragraph("验证码由订单号与验收时间经 HMAC-SHA256 计算取前 12 位，可向平台核验本验收单真伪。", s["note"])],
        ],
        colWidths=[doc.width],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D5D8DE")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(box)

    # ── 签署区 ──
    story.append(Spacer(1, 10 * mm))
    sign = Table(
        [[Paragraph("客户确认（签字）：", s["sign"]), Paragraph("", s["sign"]),
          Paragraph("确认日期：", s["sign"]), Paragraph("", s["sign"])]],
        colWidths=[40 * mm, doc.width / 2 - 40 * mm, 26 * mm, doc.width / 2 - 26 * mm],
    )
    sign.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, 0), 0.5, colors.HexColor("#999999")),
        ("LINEBELOW", (3, 0), (3, 0), 0.5, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sign)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("（本验收单由系统自动生成，客户签字确认后生效，验证码可向平台核验）", s["note"]))
    return story


def render_receipt_pdf(
    order: Order,
    *,
    role: str,
    files: Sequence[OrderFile] = (),
    site_name: str = "毕设接单",
    now: datetime | None = None,
) -> bytes:
    """生成 A4 交付验收单 PDF，返回完整字节。"""
    _register_font()
    data = receipt_data(order, role=role, files=files, now=now)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"交付验收单 {data['order_id']}", author=str(site_name or "毕设接单"),
    )
    story = _build_story(data, doc, site_name)
    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buf.getvalue()
