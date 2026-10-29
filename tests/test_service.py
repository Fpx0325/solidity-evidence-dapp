from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

import pytest

from backend.errors import (
    AlreadyExistsError,
    FileTooLargeError,
    NotFoundError,
    ValidationError,
)
from backend.utils import (
    hash_stream,
    normalize_filename,
    normalize_hash,
    normalize_user,
    utc_iso,
)


def test_hash_stream_matches_hashlib():
    content = b"hello evidence" * 1000
    digest, size = hash_stream(io.BytesIO(content), max_bytes=10_000_000)
    assert digest == hashlib.sha256(content).hexdigest()
    assert size == len(content)


def test_hash_stream_enforces_limit():
    with pytest.raises(FileTooLargeError):
        hash_stream(io.BytesIO(b"x" * 33), max_bytes=32)


def test_normalize_hash_accepts_prefix_and_uppercase():
    digest = hashlib.sha256(b"abc").hexdigest()
    assert normalize_hash("0x" + digest.upper()) == digest
    assert normalize_hash(digest) == digest


@pytest.mark.parametrize("value", ["", None, "abc", "0x" + "z" * 64, "a" * 63])
def test_normalize_hash_rejects_invalid(value):
    with pytest.raises(ValidationError):
        normalize_hash(value)


def test_normalize_filename_strips_paths_and_controls():
    assert normalize_filename("../../etc/passwd") == "passwd"
    assert normalize_filename(r"C:\Users\demo\报告.pdf") == "报告.pdf"
    assert normalize_filename("bad\x00name.txt") == "badname.txt"
    assert normalize_filename("   ") == "未命名文件"
    assert len(normalize_filename("a" * 300)) == 180


def test_normalize_user():
    assert normalize_user(" 张三 ") == "张三"
    assert normalize_user(None, default="匿名访客") == "匿名访客"
    with pytest.raises(ValidationError):
        normalize_user("")
    with pytest.raises(ValidationError):
        normalize_user("a" * 41)


def test_utc_iso():
    assert utc_iso(0) == "1970-01-01T00:00:00Z"
    assert utc_iso(None) is None


def test_service_create_and_verify_roundtrip(service):
    content = b"the original file"
    result = service.create(io.BytesIO(content), "evidence.txt", "张三")

    assert result["status"] == "verified"
    assert result["exists_on_chain"] is True
    assert result["exists_in_database"] is True
    assert result["integrity_verified"] is True
    assert result["file_hash"] == hashlib.sha256(content).hexdigest()
    assert result["block_number"] == 7
    assert result["tx_hash"].startswith("0x")

    verified = service.verify_file(io.BytesIO(content), "renamed.txt", "李四")
    assert verified["status"] == "verified"
    assert verified["checked_file_name"] == "renamed.txt"

    changed = service.verify_file(io.BytesIO(b"tampered file"), "evidence.txt", "李四")
    assert changed["status"] == "not_found"
    assert changed["exists_on_chain"] is False
    assert changed["exists_in_database"] is False

    assert [log["action"] for log in service.db.logs] == ["upload", "verify", "verify"]
    assert service.db.logs[0]["file_hash"] == hashlib.sha256(content).hexdigest()
    assert service.db.logs[1]["result"] == "verified"


def test_duplicate_is_rejected_with_detail(service):
    content = b"same bytes"
    service.create(io.BytesIO(content), "a.txt", "张三")
    with pytest.raises(AlreadyExistsError) as exc_info:
        service.create(io.BytesIO(content), "a.txt", "张三")

    detail = exc_info.value.detail
    assert detail["status"] == "verified"
    assert detail["block_number"] == 7
    assert service.db.logs[-1]["result"] == "duplicate"


def test_changed_file_not_found(service):
    result = service.verify_hash("a" * 64, "访客")
    assert result["status"] == "not_found"
    assert result["integrity_verified"] is False
    assert result["message"]


def test_get_unknown_hash_raises_not_found(service):
    with pytest.raises(NotFoundError):
        service.get("b" * 64)


def test_chain_only_and_db_only(service, fake_chain, fake_db):
    db_only_hash = hashlib.sha256(b"db only").hexdigest()
    timestamp = int(datetime.now(timezone.utc).timestamp())
    fake_db.insert_evidence(
        file_name="db-only.txt",
        file_hash=db_only_hash,
        user_name="tester",
        block_number=3,
        tx_hash="0x" + "c" * 64,
        chain_owner="0x00000000000000000000000000000000000000A1",
        chain_timestamp=timestamp,
    )
    result = service.verify_hash(db_only_hash)
    assert result["status"] == "db_only"
    assert result["integrity_verified"] is False

    chain_only_hash = hashlib.sha256(b"chain only").hexdigest()
    fake_chain.store(chain_only_hash)
    result = service.verify_hash(chain_only_hash)
    assert result["status"] == "chain_only"
    assert result["integrity_verified"] is True


def test_inconsistent_metadata(service, fake_db):
    content = b"metadata may be changed"
    created = service.create(io.BytesIO(content), "a.txt", "张三")
    digest = created["file_hash"]
    fake_db.records[digest]["chain_owner"] = "0x00000000000000000000000000000000000000FF"
    result = service.verify_hash(digest)
    assert result["status"] == "inconsistent"
    assert result["integrity_verified"] is False


def test_service_health(service):
    health = service.health()
    assert health["ok"] is True
    assert health["database"]["ok"] is True
    assert health["chain"]["ok"] is True
