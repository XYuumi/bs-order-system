"""上传需求书「直接应用/参考生成」两种应用方式的回归测试。"""
from __future__ import annotations

import json

from helpers import ADMIN_PASSWORD

PLAIN_TEXT = """养老院管理系统需求书

一、项目目标
建设一套养老院管理系统，实现老人档案、入住登记、护理排班、费用结算的线上管理。

二、功能需求
1. 老人档案管理：登记基本信息、健康状况、联系人。
2. 入住管理：办理入住、退住，记录床位。
3. 护理排班：按周排班，自动提醒。
"""


def _make_order(admin_client, **extra):
    resp = admin_client.post("/api/orders", json={
        "title": "需求书应用方式测试", "quality_code": "white", "project_type": "thesis_program",
        **extra,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["order"]


class TestDirectApply:
    def test_direct_apply_plain_text(self, admin_client):
        """普通文本需求书 + direct：生成结果为原文直用，一字不改，且不依赖 AI。"""
        order = _make_order(
            admin_client,
            source_requirement=PLAIN_TEXT,
            source_apply_mode="direct",
        )
        assert order["source_apply_mode"] == "direct"

        resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source"] == "manual"
        assert "直接采用" in (data["note"] or "")
        doc = data["document"]
        assert doc["mode"] == "raw"
        # 建单入参会 strip 首尾空白（既有行为），除此之外逐字保留
        assert doc["raw_text"] == PLAIN_TEXT.strip()
        assert "chapters" not in doc                   # 没有被结构化改写

        # 下载 Word 正常（原文渲染分支）
        dl = admin_client.get(f"/api/orders/{order['id']}/requirement/docx")
        assert dl.status_code == 200
        assert dl.content[:2] == b"PK"  # docx 是 zip 包

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_direct_apply_keeps_unmapped_sections_in_place(self, admin_client):
        """含无对应章节段落（售后服务）的原文：直接采用后一字不改，不拆进九章、不归进功能需求。"""
        text = PLAIN_TEXT + "\n十、售后服务\n交付后提供一年免费维护。\n"
        order = _make_order(admin_client, source_requirement=text, source_apply_mode="direct")

        resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["source"] == "manual"
        assert "直接采用" in (resp.json()["note"] or "")
        doc = resp.json()["document"]
        assert doc["mode"] == "raw"
        assert doc["raw_text"] == text.strip()

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_direct_apply_our_json_still_structured(self, admin_client, db):
        """本系统九章 JSON + direct：按结构化导入，内容不变。"""
        from app.services.docgen import build_template_doc

        ours = build_template_doc("基于SpringBoot的图书管理系统", "SpringBoot+Vue3")
        order = _make_order(
            admin_client,
            source_requirement=json.dumps(ours, ensure_ascii=False),
            source_apply_mode="direct",
        )
        resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})
        assert resp.status_code == 200, resp.text
        doc = resp.json()["document"]
        assert doc.get("mode") != "raw"
        assert "chapters" in doc
        assert doc["chapters"]["goal"]["paragraphs"] == ours["chapters"]["goal"]["paragraphs"]

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_reference_mode_keeps_old_behavior(self, admin_client):
        """参考模式（默认）：AI 未配置时走模板生成，不会把原文直接当需求书。"""
        order = _make_order(admin_client, source_requirement=PLAIN_TEXT)  # 不传 mode = reference
        assert order["source_apply_mode"] == "reference"
        resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})
        assert resp.status_code == 200, resp.text
        doc = resp.json()["document"]
        assert doc.get("mode") != "raw"
        assert "chapters" in doc

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_direct_mode_explicit_template_still_template(self, admin_client):
        """直接应用模式下显式点「纯模板生成」：尊重用户显式选择，生成模板。"""
        order = _make_order(
            admin_client, source_requirement=PLAIN_TEXT, source_apply_mode="direct",
        )
        resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "template"})
        assert resp.status_code == 200, resp.text
        doc = resp.json()["document"]
        assert doc.get("mode") != "raw"
        assert "chapters" in doc

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_update_apply_mode(self, admin_client):
        """编辑订单可切换应用方式（参考 ↔ 直接）。"""
        order = _make_order(admin_client, source_requirement=PLAIN_TEXT)
        resp = admin_client.patch(
            f"/api/orders/{order['id']}", json={"source_apply_mode": "direct"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["order"]["source_apply_mode"] == "direct"

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_raw_doc_edit_preserves_content(self, admin_client):
        """原文直用后编辑保存：normalize 不补模板不改写，原文保持。"""
        order = _make_order(
            admin_client, source_requirement=PLAIN_TEXT, source_apply_mode="direct",
        )
        admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})

        edited = {"title": "手工改标题的需求书", "mode": "raw", "raw_text": PLAIN_TEXT + "\n附则：解释权归平台。"}
        resp = admin_client.put(f"/api/orders/{order['id']}/requirement", json={"document": edited})
        assert resp.status_code == 200, resp.text
        doc = resp.json()["document"]
        assert doc["mode"] == "raw"
        assert doc["raw_text"].endswith("解释权归平台。")
        assert "chapters" not in doc

        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_raw_doc_diff(self, admin_client):
        """原文模式的历史版本对比：给出全文差异，而不是误报“完全一致”。"""
        from app.services.docgen import build_raw_doc
        from app.services.reqdiff import diff_documents

        old_doc = build_raw_doc("题目", "第一版原文\n功能A")
        new_doc = build_raw_doc("题目", "第一版原文\n功能B")
        diffs = diff_documents(old_doc, new_doc)
        assert len(diffs) == 1
        assert diffs[0]["kind"] == "changed"
        assert "功能A" in diffs[0]["old"]
        assert "功能B" in diffs[0]["new"]
        # 相同原文 → 无差异
        assert diff_documents(old_doc, build_raw_doc("题目", "第一版原文\n功能A")) == []
