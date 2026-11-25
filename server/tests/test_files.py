from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.main import app
from app.models import Notification, OperationLog, OrderFile
from helpers import ADMIN_PASSWORD


def test_upload_rejects_unknown_extension(admin_client, order_factory):
    order = order_factory("上传扩展名测试")
    resp = admin_client.post(
        f"/api/orders/{order['id']}/files",
        files={"file": ("bad.exe", b"x", "application/octet-stream")},
        data={"category": "package"},
    )
    assert resp.status_code == 400


def test_chunk_upload_permissions_and_size(admin_client, agent_client, order_factory):
    order = order_factory("分片上传测试")
    oid = order["id"]
    create = admin_client.post(f"/api/orders/{oid}/chunk-uploads", json={
        "filename": "note.txt", "category": "doc", "size": 10,
    })
    assert create.status_code == 200, create.text
    upload_id = create.json()["upload_id"]
    assert create.json()["total_chunks"] == 1

    assert agent_client.get(f"/api/orders/{oid}/chunk-uploads/{upload_id}").status_code == 403

    too_big = admin_client.put(f"/api/orders/{oid}/chunk-uploads/{upload_id}/0", content=b"x" * 20)
    assert too_big.status_code == 413

    chunk = admin_client.put(f"/api/orders/{oid}/chunk-uploads/{upload_id}/0", content=b"0123456789")
    assert chunk.status_code == 200, chunk.text
    status = admin_client.get(f"/api/orders/{oid}/chunk-uploads/{upload_id}")
    assert status.json()["received"] == [0]

    finish = admin_client.post(f"/api/orders/{oid}/chunk-uploads/{upload_id}/finish")
    assert finish.status_code == 200, finish.text
    file_id = finish.json()["file"]["id"]
    download = admin_client.get(f"/api/files/{file_id}/download")
    assert download.status_code == 200
    assert download.content == b"0123456789"


def test_missing_file_returns_404(admin_client, order_factory, db):
    order = order_factory("缺文件记录测试")
    record = OrderFile(
        order_id=order["id"], category="doc", original_name="missing.txt",
        stored_name=f"{order['id']}/doc/{'0' * 32}", size=1, mime="text/plain",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    resp = admin_client.get(f"/api/files/{record.id}/download")
    assert resp.status_code == 404


# ==================== 演示视频 / 程序包：一单一份，再传即替换 ====================

def _upload(client, oid, name, category, content=b"0123456789"):
    resp = client.post(
        f"/api/orders/{oid}/files",
        files={"file": (name, content, "application/octet-stream")},
        data={"category": category},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _names(client, oid, category):
    order = client.get(f"/api/orders/{oid}").json()["order"]
    return sorted(f["original_name"] for f in order["files"] if f["category"] == category)


def _chunk_upload(client, oid, name, category, content):
    create = client.post(f"/api/orders/{oid}/chunk-uploads",
                         json={"filename": name, "category": category, "size": len(content)})
    assert create.status_code == 200, create.text
    upload_id, chunk_size = create.json()["upload_id"], create.json()["chunk_size"]
    for index in range(create.json()["total_chunks"]):
        part = content[index * chunk_size:(index + 1) * chunk_size]
        put = client.put(f"/api/orders/{oid}/chunk-uploads/{upload_id}/{index}", content=part)
        assert put.status_code == 200, put.text
    finish = client.post(f"/api/orders/{oid}/chunk-uploads/{upload_id}/finish")
    assert finish.status_code == 200, finish.text
    return finish.json()


def _replaced_names(body):
    return sorted(f["original_name"] for f in body["replaced"])


def _stored(db, file_id: int) -> OrderFile:
    # 先结束只读事务再查：REPEATABLE READ 下，旧事务看不到之后才提交的行（例如本次测试里刚上传的文件）
    db.rollback()
    return db.get(OrderFile, file_id)


def _on_disk(db, file_id: int) -> bool:
    """该文件记录对应的磁盘文件是否还在。"""
    return UPLOAD_DIR.joinpath(*_stored(db, file_id).stored_name.split("/")).is_file()


def test_video_and_package_replace_previous_upload(admin_client, order_factory, db):
    """演示视频/程序包一单一份：再传即替换；文档、其他附件仍可多份并存。"""
    oid = order_factory("替换上传测试")["id"]

    first = _upload(admin_client, oid, "演示-v1.mp4", "video")
    assert first["replaced"] == []
    # 测试环境没有 ffmpeg，手动放一张缩略图，验证替换时缩略图会一并删除
    v1 = _stored(db, first["file"]["id"])
    thumb = UPLOAD_DIR.joinpath(v1.stored_name.split("/")[0], "thumb", v1.stored_name.split("/")[2] + ".jpg")
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"thumb")

    second = _upload(admin_client, oid, "演示-v2.mp4", "video")
    assert _replaced_names(second) == ["演示-v1.mp4"]
    assert _names(admin_client, oid, "video") == ["演示-v2.mp4"]
    assert not _on_disk(db, first["file"]["id"]) and not thumb.exists()
    assert _on_disk(db, second["file"]["id"])

    _upload(admin_client, oid, "源码-v1.zip", "package")
    third = _upload(admin_client, oid, "源码-v2.zip", "package")
    assert _replaced_names(third) == ["源码-v1.zip"]
    # 替换程序包不影响演示视频
    assert _names(admin_client, oid, "package") == ["源码-v2.zip"]
    assert _names(admin_client, oid, "video") == ["演示-v2.mp4"]

    _upload(admin_client, oid, "说明.txt", "doc")
    assert _upload(admin_client, oid, "补充.txt", "doc")["replaced"] == []
    _upload(admin_client, oid, "附图.png", "other")
    _upload(admin_client, oid, "附图2.png", "other")
    assert _names(admin_client, oid, "doc") == ["补充.txt", "说明.txt"]
    assert _names(admin_client, oid, "other") == ["附图.png", "附图2.png"]


def test_replaced_file_removed_from_download_and_deliver_link(admin_client, order_factory):
    """被替换的旧文件不可再下载，客户交付链接里也只剩新文件。"""
    oid = order_factory("替换后交付链接测试")["id"]
    old = _upload(admin_client, oid, "旧版.zip", "package")["file"]
    new = _upload(admin_client, oid, "新版.zip", "package", content=b"new-package")["file"]

    assert admin_client.get(f"/api/files/{old['id']}/download").status_code == 404
    download = admin_client.get(f"/api/files/{new['id']}/download")
    assert download.status_code == 200 and download.content == b"new-package"

    token = admin_client.get(f"/api/orders/{oid}/deliver-link").json()["token"]
    files = admin_client.get(f"/api/deliver/{token}").json()["files"]
    assert [f["name"] for f in files] == ["新版.zip"]


def test_chunk_upload_replaces_previous_package(admin_client, order_factory, db):
    """分片上传（大文件）同样替换：旧文件不可下载，新文件内容完整。"""
    oid = order_factory("分片替换测试")["id"]
    old = _upload(admin_client, oid, "交付-v1.zip", "package")["file"]
    payload = bytes(range(256)) * (6 * 1024 * 4)  # 6 MiB，跨多个分片
    result = _chunk_upload(admin_client, oid, "交付-v2.zip", "package", payload)

    assert _replaced_names(result) == ["交付-v1.zip"]
    assert admin_client.get(f"/api/files/{old['id']}/download").status_code == 404
    download = admin_client.get(f"/api/files/{result['file']['id']}/download")
    assert download.status_code == 200 and download.content == payload
    assert _names(admin_client, oid, "package") == ["交付-v2.zip"]
    assert not _on_disk(db, old["id"]) and _on_disk(db, result["file"]["id"])


def test_replacement_recorded_in_operation_log_and_notification(
    admin_client, staff_client, order_factory, db
):
    """替换不限定上传者角色；操作日志记下被替换的文件名与 ID，通知点明替换了哪个文件。"""
    oid = order_factory("替换留痕测试")["id"]
    old = _upload(admin_client, oid, "演示.mp4", "video")["file"]
    _upload(staff_client, oid, "演示-重录.mp4", "video")  # 写手替换管理员上传的视频

    db.expire_all()
    entries = (db.query(OperationLog)
               .filter(OperationLog.entity_type == "order", OperationLog.entity_id == oid,
                       OperationLog.action == "file_upload")
               .all())
    details = [json.loads(e.detail) for e in entries if e.detail]
    replaced = [d for d in details if d.get("replaced")]
    assert len(replaced) == 1
    assert replaced[0]["file"] == "演示-重录.mp4"
    assert replaced[0]["replaced"] == ["演示.mp4"]
    assert replaced[0]["replaced_ids"] == [old["id"]]

    note = (db.query(Notification)
            .filter(Notification.order_id == oid, Notification.title.like("%替换了演示视频"))
            .first())
    assert note is not None
    assert "演示-重录.mp4" in note.body and "演示.mp4" in note.body


def test_concurrent_uploads_of_same_category_leave_single_file(admin_client, order_factory, db):
    """同一订单并发上传两个演示视频：都成功，且最终只留一份（后提交者替换先提交者）。"""
    oid = order_factory("并发替换测试")["id"]
    start = threading.Barrier(2)

    def send(name):
        start.wait(timeout=10)
        return admin_client.post(
            f"/api/orders/{oid}/files",
            files={"file": (name, b"\x11" * (2 * 1024 * 1024), "video/mp4")},
            data={"category": "video"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [fut.result() for fut in (pool.submit(send, "并发-a.mp4"), pool.submit(send, "并发-b.mp4"))]

    assert sorted(r.status_code for r in responses) == [200, 200], [r.text for r in responses]
    assert sorted(len(r.json()["replaced"]) for r in responses) == [0, 1]
    assert _names(admin_client, oid, "video") in (["并发-a.mp4"], ["并发-b.mp4"])
    # 先提交的那份被后提交的替换、已从磁盘删除；后提交的那份才是最终保留的
    earlier, final = sorted((r.json() for r in responses), key=lambda body: len(body["replaced"]))
    assert not _on_disk(db, earlier["file"]["id"]) and _on_disk(db, final["file"]["id"])


def test_manual_delete_removes_file_from_disk(admin_client, order_factory, db):
    """手动删除文件：记录标记删除的同时，磁盘上的文件一并清掉。"""
    oid = order_factory("手动删除清磁盘")["id"]
    doc = _upload(admin_client, oid, "待删.txt", "doc")["file"]
    assert _on_disk(db, doc["id"])

    resp = admin_client.delete(f"/api/files/{doc['id']}", headers={"X-Confirm-Password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    assert not _on_disk(db, doc["id"])
    assert admin_client.get(f"/api/files/{doc['id']}/download").status_code == 404


def test_api_upload_replaces_unless_replace_zero(admin_client, staff_client, order_factory, db):
    """开放 API 同样默认替换；传 replace=0 时保留旧文件、追加为新文件。"""
    oid = order_factory("API 替换测试")["id"]
    api_key = staff_client.get("/api/me/api-key").json()["api_key"]
    api = TestClient(app)

    def api_upload(name, **form):
        resp = api.post(f"/api/v1/orders/{oid}/files", headers={"X-API-Key": api_key},
                        files={"file": (name, b"content", "application/octet-stream")},
                        data={"category": form.pop("category", "video"), **form})
        assert resp.status_code == 200, resp.text
        return resp.json()

    # replace=1 对文档无效：只会追加，不会替换掉已有附件
    assert api_upload("说明-1.txt", category="doc")["replaced"] == []
    assert api_upload("说明-2.txt", category="doc", replace="1")["replaced"] == []
    docs = api.get(f"/api/v1/orders/{oid}/files?category=doc", headers={"X-API-Key": api_key}).json()["files"]
    assert sorted(f["original_name"] for f in docs) == ["说明-1.txt", "说明-2.txt"]

    a = api_upload("a.mp4")
    assert a["replaced"] == []
    b = api_upload("b.mp4")
    assert _replaced_names(b) == ["a.mp4"]
    assert not _on_disk(db, a["file"]["id"]) and _on_disk(db, b["file"]["id"])

    c = api_upload("c.mp4", replace="0")
    assert c["replaced"] == []
    listed = api.get(f"/api/v1/orders/{oid}/files?category=video", headers={"X-API-Key": api_key}).json()["files"]
    assert sorted(f["original_name"] for f in listed) == ["b.mp4", "c.mp4"]
    # replace=0 不替换，旧文件都还在磁盘上
    assert _on_disk(db, b["file"]["id"]) and _on_disk(db, c["file"]["id"])

    # 恢复默认：已有的两份一起被替换，磁盘上也一并删除
    d = api_upload("d.mp4")
    assert _replaced_names(d) == ["b.mp4", "c.mp4"]
    assert not _on_disk(db, b["file"]["id"]) and not _on_disk(db, c["file"]["id"])
    assert _on_disk(db, d["file"]["id"])
