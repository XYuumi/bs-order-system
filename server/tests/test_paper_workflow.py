"""论文进度（项目类型 + 任务书/开题/初稿/终稿留档）回归测试。"""
from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from helpers import ADMIN_PASSWORD


def _docx_bytes(name: str = "论文文档") -> bytes:
    """构造一个最小合法 docx（zip 包），通过 paper 分类的扩展名白名单。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", f"<doc>{name}</doc>")
    return buf.getvalue()


def _upload(client: TestClient, oid: str, doc_type: str, note: str | None = None, name: str = "论文文档"):
    data = {"doc_type": doc_type}
    if note:
        data["note"] = note
    return client.post(
        f"/api/orders/{oid}/paper/docs",
        data=data,
        files={"file": (f"{name}.docx", _docx_bytes(name), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )


class TestProjectType:
    def test_create_with_project_type(self, admin_client, order_factory):
        order = order_factory("论文类型订单", project_type="thesis_program")
        assert order["project_type"] == "thesis_program"

    def test_legacy_order_without_project_type(self, admin_client):
        """完全不带分类字段：建单成功，project_type 为 null，不启用论文进度（向后兼容）。"""
        resp = admin_client.post("/api/orders", json={"title": "旧式订单", "quality_code": "white"})
        assert resp.status_code == 200, resp.text
        order = resp.json()["order"]
        assert order["project_type"] is None
        paper = admin_client.get(f"/api/orders/{order['id']}/paper")
        assert paper.status_code == 200
        assert paper.json()["enabled"] is False
        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_legacy_category_alias_mapped(self, admin_client):
        """旧工种值兼容：code→program、thesis→thesis（启用论文进度）。"""
        resp = admin_client.post("/api/orders", json={
            "title": "旧工种别名映射", "quality_code": "white", "category": "thesis",
        })
        assert resp.status_code == 200, resp.text
        order = resp.json()["order"]
        assert order["project_type"] == "thesis"
        assert admin_client.get(f"/api/orders/{order['id']}/paper").json()["enabled"] is True
        admin_client.delete(f"/api/orders/{order['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})

    def test_invalid_project_type_rejected(self, admin_client):
        resp = admin_client.post("/api/orders", json={
            "title": "非法类型", "quality_code": "white", "category": "code", "project_type": "paperwork",
        })
        assert resp.status_code == 422

    def test_update_project_type(self, admin_client, order_factory):
        order = order_factory("类型变更订单", project_type="program")
        resp = admin_client.patch(f"/api/orders/{order['id']}", json={"project_type": "thesis"})
        assert resp.status_code == 200
        assert resp.json()["order"]["project_type"] == "thesis"

    def test_cannot_remove_paper_when_docs_exist(self, admin_client, order_factory):
        order = order_factory("已留档订单", project_type="thesis")
        assert _upload(admin_client, order["id"], "task_book").status_code == 200
        resp = admin_client.patch(f"/api/orders/{order['id']}", json={"project_type": "program"})
        assert resp.status_code == 400
        assert "留档" in resp.json()["detail"]

    def test_list_filter_by_project_type(self, admin_client, order_factory):
        order_factory("筛选纯论文", project_type="thesis")
        order_factory("筛选纯程序", project_type="program")
        resp = admin_client.get("/api/orders", params={"project_type": "thesis"})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["project_type"] == "thesis"


class TestPaperUpload:
    def test_program_order_rejects_paper_doc(self, admin_client, order_factory):
        order = order_factory("纯程序订单", project_type="program")
        resp = _upload(admin_client, order["id"], "task_book")
        assert resp.status_code == 400

    def test_agent_cannot_upload_but_can_view(self, agent_client, admin_client, order_factory):
        order = order_factory(
            "代理论文订单", project_type="thesis", agent_username="agent1"
        )
        assert _upload(agent_client, order["id"], "task_book").status_code == 403
        resp = agent_client.get(f"/api/orders/{order['id']}/paper")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_doc_type_validated(self, admin_client, order_factory):
        order = order_factory("非法文档类型", project_type="thesis")
        assert _upload(admin_client, order["id"], "abstract").status_code == 422

    def test_versions_append_with_round(self, admin_client, order_factory):
        order = order_factory("任务书多版", project_type="thesis")
        r1 = _upload(admin_client, order["id"], "task_book", note="首版")
        assert r1.status_code == 200
        assert r1.json()["uploaded"]["round"] == 1
        r2 = _upload(admin_client, order["id"], "task_book", note="按导师意见修订")
        assert r2.status_code == 200
        assert r2.json()["uploaded"]["round"] == 2

        docs = admin_client.get(f"/api/orders/{order['id']}/paper/docs", params={"doc_type": "task_book"}).json()["docs"]
        assert len(docs) == 2
        assert [d["round"] for d in docs] == [2, 1]

    def test_progress_payload(self, admin_client, order_factory):
        order = order_factory("进度总览", project_type="thesis_program")
        _upload(admin_client, order["id"], "task_book")
        data = admin_client.get(f"/api/orders/{order['id']}/paper").json()
        labels = [d["label"] for d in data["docs"]]
        assert labels == ["任务书", "开题报告", "论文初稿", "论文终稿"]
        counts = {d["doc_type"]: d["count"] for d in data["docs"]}
        assert counts == {"task_book": 1, "proposal": 0, "draft": 0, "final": 0}
        assert data["min_revisions"] == 5
        assert data["all_done"] is False

    def test_generic_file_upload_rejects_paper_category(self, admin_client, order_factory):
        """论文留档必须走论文进度接口，通用上传入口拒绝 paper 分类。"""
        order = order_factory("通用入口校验", project_type="thesis")
        resp = admin_client.post(
            f"/api/orders/{order['id']}/files",
            data={"category": "paper"},
            files={"file": ("绕过.docx", _docx_bytes(), "application/octet-stream")},
        )
        assert resp.status_code == 400


class TestDraftRevisionGate:
    def test_final_requires_min_revisions(self, admin_client, order_factory):
        order = order_factory("初稿修改门槛", project_type="thesis")

        # 没有任何初稿：不能交终稿
        resp = _upload(admin_client, order["id"], "final")
        assert resp.status_code == 400

        # 初稿 1 版 = 0 次修改，仍不够
        assert _upload(admin_client, order["id"], "draft", note="初稿首版").status_code == 200
        resp = _upload(admin_client, order["id"], "final")
        assert resp.status_code == 400
        assert "还差 5 次" in resp.json()["detail"]

        # 修满 5 次（共 6 版）后可交终稿
        for i in range(2, 7):
            assert _upload(admin_client, order["id"], "draft", note=f"第{i}次修改").status_code == 200
        data = admin_client.get(f"/api/orders/{order['id']}/paper").json()
        assert data["draft_revisions"] == 5
        draft = next(d for d in data["docs"] if d["doc_type"] == "draft")
        assert draft["revision_progress"] == 100
        final = next(d for d in data["docs"] if d["doc_type"] == "final")
        assert final["ready"] is True

        resp = _upload(admin_client, order["id"], "final", note="定稿")
        assert resp.status_code == 200
        data = admin_client.get(f"/api/orders/{order['id']}/paper").json()
        assert data["final_submitted"] is True
        assert data["all_done"] is False  # 任务书/开题报告还没交

    def test_archived_file_cannot_be_deleted(self, admin_client, order_factory):
        """留档文件删除被拒，保证修改链条完整。"""
        order = order_factory("留档不可删", project_type="thesis")
        resp = _upload(admin_client, order["id"], "draft", note="初稿首版")
        file_id = resp.json()["uploaded"]["file"]["id"]
        del_resp = admin_client.delete(
            f"/api/files/{file_id}", headers={"X-Confirm-Password": ADMIN_PASSWORD}
        )
        assert del_resp.status_code == 400
        assert "留档" in del_resp.json()["detail"]

    def test_paper_file_download_by_agent(self, agent_client, admin_client, order_factory):
        """代理（本单）可下载留档文件，转发给客户。"""
        order = order_factory("代理下载留档", project_type="thesis", agent_username="agent1")
        resp = _upload(admin_client, order["id"], "task_book")
        file_id = resp.json()["uploaded"]["file"]["id"]
        dl = agent_client.get(f"/api/files/{file_id}/download")
        assert dl.status_code == 200
        assert dl.content == _docx_bytes()

    def test_draft_version_chain_preserved(self, admin_client, order_factory):
        """初稿每次修改都有独立留档记录，历史不覆盖。"""
        order = order_factory("留档链", project_type="thesis")
        for i in range(1, 4):
            assert _upload(admin_client, order["id"], "draft", note=f"第{i}版").status_code == 200
        docs = admin_client.get(f"/api/orders/{order['id']}/paper/docs", params={"doc_type": "draft"}).json()["docs"]
        assert [d["round"] for d in docs] == [3, 2, 1]
        assert [d["note"] for d in docs] == ["第3版", "第2版", "第1版"]
        files = {d["file"]["id"] for d in docs}
        assert len(files) == 3  # 三个版本各自对应独立文件
