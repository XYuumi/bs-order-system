"""数据库备份（JSON 逻辑备份，Fernet 加密落盘，供后台一键备份与脚本共用）。

备份包含密码哈希/API Key/TOTP 密钥等敏感数据，因此默认加密：
- 优先使用 BACKUP_ENCRYPTION_KEY（Fernet key，base64 urlsafe 44 字符）；
- 未配置时从 JWT_SECRET 派生，便于本机开箱即用；更换 JWT_SECRET 前请先导出备份密钥。
旧版明文 .json 备份仍可读取和恢复，新备份写为 .json.enc。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import struct
import tempfile
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import MetaData, select

from ..config import BACKUP_DIR as CONFIG_BACKUP_DIR, BACKUP_ENCRYPTION_KEY, JWT_SECRET
from ..database import SessionLocal, engine

BACKUP_DIR = CONFIG_BACKUP_DIR
FILE_PREFIX = "bs-backup"
KEEP = 14

STAMP_RE = re.compile(r"^\d{8}-\d{6}$")
SAFE_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _fernet_key() -> bytes:
    if BACKUP_ENCRYPTION_KEY:
        key = BACKUP_ENCRYPTION_KEY.encode()
    else:
        digest = hashlib.sha256(f"backup:{JWT_SECRET}".encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    try:
        Fernet(key)  # 只做格式校验，密钥非法时立即报错
    except (ValueError, TypeError) as exc:
        raise ValueError("BACKUP_ENCRYPTION_KEY 不是合法的 Fernet key") from exc
    return key


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return {"__hex__": value.hex()}
    return value


def _safe_path(name: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.\-]+$", name or ""):
        raise ValueError("备份文件名非法")
    root = BACKUP_DIR.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("备份路径越界")
    return target


def _backup_files() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    root = BACKUP_DIR.resolve()
    return sorted(
        (p for p in BACKUP_DIR.glob(FILE_PREFIX + "-*") if p.is_file() and p.resolve().is_relative_to(root)),
        reverse=True,
    )


def read_backup_payload(name: str) -> dict:
    """读取备份（自动区分 .enc / 明文 .json），返回 payload。"""
    path = _safe_path(name)
    raw = path.read_bytes()
    if path.suffix == ".enc":
        try:
            raw = _fernet().decrypt(raw)
        except InvalidToken as exc:
            raise ValueError("备份解密失败：加密密钥不匹配或文件损坏") from exc
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise ValueError("备份格式不正确")
    return data


ROW_CHUNK = 1000
READ_CHUNK = 1024 * 1024


class _B64Sink:
    """把二进制分块写成无换行的 urlsafe base64，跨块按 3 字节对齐。"""

    def __init__(self, fp):
        self.fp = fp
        self._pending = b""

    def write(self, data: bytes) -> None:
        buf = self._pending + data
        cut = len(buf) - len(buf) % 3
        if cut:
            self.fp.write(base64.urlsafe_b64encode(buf[:cut]))
        self._pending = buf[cut:]

    def close(self) -> None:
        if self._pending:
            self.fp.write(base64.urlsafe_b64encode(self._pending))
            self._pending = b""


def _encrypt_stream(src, dst) -> None:
    """按 Fernet token 格式分块加密 src 到 dst，避免把整份备份读进内存。

    只接收调用方已打开的二进制文件对象（src 可读、dst 可写）：本函数不打开、不关闭任何文件，因此不涉及路径。
    """
    raw_key = base64.urlsafe_b64decode(_fernet_key())
    signing_key, encryption_key = raw_key[:16], raw_key[16:]
    header = b"\x80" + struct.pack(">Q", int(time.time())) + os.urandom(16)
    signer = hmac.new(signing_key, header, hashlib.sha256)
    encryptor = Cipher(algorithms.AES(encryption_key), modes.CBC(header[9:25])).encryptor()
    padder = padding.PKCS7(128).padder()
    sink = _B64Sink(dst)
    sink.write(header)
    while True:
        chunk = src.read(READ_CHUNK)
        if not chunk:
            break
        ciphertext = encryptor.update(padder.update(chunk))
        if ciphertext:
            signer.update(ciphertext)
            sink.write(ciphertext)
    ciphertext = encryptor.update(padder.finalize()) + encryptor.finalize()
    if ciphertext:
        signer.update(ciphertext)
        sink.write(ciphertext)
    sink.write(signer.digest())
    sink.close()


def _write_backup_json(db, tables, created_at: str, fp) -> int:
    """把 {"format":2,"created_at":...,"tables":{...}} 分块写入 fp，返回总行数。

    逐表按 ROW_CHUNK 批读取，空表不写入 tables（与旧实现一致），内存中只保留一个批次。
    只接收调用方已打开的二进制文件对象：本函数不打开、不关闭任何文件，因此不涉及路径。
    """
    total = 0
    head = '{"format":2,"created_at":' + json.dumps(created_at, ensure_ascii=False) + ',"tables":{'
    fp.write(head.encode("utf-8"))
    first_table = True
    for table in tables:
        cols = [c.name for c in table.columns]
        opened = False
        rows = db.execute(select(table).execution_options(yield_per=ROW_CHUNK))
        try:
            for row in rows:
                mapping = row._mapping
                item = {name: _jsonable(mapping[name]) for name in cols}
                if not opened:
                    if not first_table:
                        fp.write(b",")
                    fp.write((json.dumps(table.name, ensure_ascii=False) + ":[").encode("utf-8"))
                    opened = True
                    first_table = False
                else:
                    fp.write(b",")
                fp.write(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8"))
                total += 1
        finally:
            rows.close()
        if opened:
            fp.write(b"]")
    fp.write(b"}}")
    return total


def backup_now() -> dict:
    """立即备份到 server/backups/，保留最近 KEEP 份，返回备份信息。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = BACKUP_DIR / f"{FILE_PREFIX}-{stamp}.json.enc"

    meta = MetaData()
    meta.reflect(bind=engine)
    tables = [t for t in reversed(meta.sorted_tables) if SAFE_TABLE_RE.match(t.name or "")]

    created_at = datetime.now().isoformat(" ")
    # 明文只写进备份目录内的匿名临时文件：目录里不出现明文文件名，关闭即消失。
    with tempfile.TemporaryFile(dir=BACKUP_DIR) as plain:
        db = SessionLocal()
        try:
            # 同一事务内读取，InnoDB REPEATABLE READ 提供一致性快照。
            total_rows = _write_backup_json(db, tables, created_at, plain)
        finally:
            db.close()
        plain.seek(0)
        # 密文先写进备份目录内随机命名的临时文件，写完原子改名为成品；中途出错则删除临时文件。
        fd, enc_tmp = tempfile.mkstemp(dir=BACKUP_DIR, prefix=f".{out.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as enc:
                _encrypt_stream(plain, enc)
            # mkstemp 固定建成 0600；改回此前直接写文件时的 0644，保证由其他身份
            # （如以 root 运行的计划任务）生成的备份仍可被应用进程读取（下载 / 恢复 / 同步）。
            os.chmod(enc_tmp, 0o644)
            os.replace(enc_tmp, out)
        finally:
            Path(enc_tmp).unlink(missing_ok=True)  # 成功改名后已不存在；出错时清掉半截密文

    files = _backup_files()  # 新→旧排序；保留最新 KEEP 份，删除更旧的
    removed = 0
    for old in files[KEEP:]:
        old.unlink(missing_ok=True)
        removed += 1
    return {"name": out.name, "size": out.stat().st_size, "rows": total_rows, "removed_old": removed,
            "encrypted": True, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def list_backups() -> list[dict]:
    items = []
    for p in _backup_files():
        st = p.stat()
        items.append({
            "name": p.name,
            "size": st.st_size,
            "encrypted": p.suffix == ".enc",
            "created_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items


def backup_file(name: str) -> Path:
    return _safe_path(name)


def sync_backup(db, name: str) -> dict:
    """备份完成后的自动同步：复制到 backup_sync_dir（如网盘同步目录）+ webhook 通知。"""
    from .settings_svc import get_setting
    from .webhook import send_text

    result: dict = {}
    sync_dir = (get_setting(db, "backup_sync_dir") or "").strip()
    if sync_dir:
        src = _safe_path(name)
        if src.exists():
            target_dir = Path(sync_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / name
            shutil.copy2(src, target)
            result["synced_to"] = str(target)
            olds = sorted(target_dir.glob(FILE_PREFIX + "-*"))
            for old in olds[:-KEEP]:
                old.unlink(missing_ok=True)

    if (get_setting(db, "backup_notify_webhook") or "").strip().lower() in ("1", "true", "yes", "on"):
        size_kb = _safe_path(name).stat().st_size / 1024 if _safe_path(name).exists() else 0
        try:
            send_text(db, f"📦 数据备份完成：{name}（{size_kb:.1f} KB，已加密）"
                      + (f"，已同步至 {result.get('synced_to')}" if result.get("synced_to") else ""))
            result["notified"] = True
        except Exception as exc:  # noqa: BLE001 —— webhook 失败不阻塞
            result["notify_error"] = str(exc)[:200]
    return result
