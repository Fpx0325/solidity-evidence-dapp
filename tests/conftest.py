"""共享测试替身：用内存对象替代 Ganache 与 MySQL，保证单元测试离线可跑。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.service import EvidenceService
from backend.utils import utc_iso


class FakeChain:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.owner = "0x00000000000000000000000000000000000000A1"
        self.next_block = 7

    def get(self, file_hash: str) -> dict[str, Any]:
        record = self.records.get(file_hash)
        if record is None:
            return {
                "exists": False,
                "owner": None,
                "timestamp": None,
                "chain_time": None,
                "network": "ganache",
            }
        return {
            "exists": True,
            "owner": record["owner"],
            "timestamp": record["timestamp"],
            "chain_time": utc_iso(record["timestamp"]),
            "network": "ganache",
        }

    def store(self, file_hash: str) -> dict[str, Any]:
        timestamp = 1_700_000_000 + len(self.records)
        record = {
            "owner": self.owner,
            "timestamp": timestamp,
            "tx_hash": "0x" + hashlib.sha256(file_hash.encode()).hexdigest(),
            "block_number": self.next_block,
        }
        self.records[file_hash] = record
        self.next_block += 1
        return {
            "tx_hash": record["tx_hash"],
            "block_number": record["block_number"],
            "block_hash": "0x" + "b" * 64,
            "owner": record["owner"],
            "timestamp": record["timestamp"],
            "chain_time": utc_iso(record["timestamp"]),
        }

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Ganache 与合约连接正常",
            "rpc_url": "http://127.0.0.1:7545",
            "expected_chain_id": 1337,
            "chain_id": 1337,
            "contract_address": "0x00000000000000000000000000000000000000A1",
            "block_number": self.next_block,
        }


class FakeDatabase:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.logs: list[dict[str, Any]] = []
        self.next_id = 1

    def insert_evidence(self, **kwargs: Any) -> dict[str, Any]:
        record = {
            "id": self.next_id,
            **kwargs,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.records[kwargs["file_hash"]] = record
        self.next_id += 1
        return dict(record)

    def get_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        record = self.records.get(file_hash)
        return dict(record) if record else None

    def list_evidence(self, limit: int = 10) -> list[dict[str, Any]]:
        records = sorted(
            self.records.values(), key=lambda item: item["id"], reverse=True
        )
        return [dict(item) for item in records[:limit]]

    def log_operation(
        self,
        *,
        action: str,
        file_hash: str,
        user_name: str,
        result: str,
        file_name: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.logs.append(
            {
                "action": action,
                "file_hash": file_hash,
                "user_name": user_name,
                "result": result,
                "file_name": file_name,
                "detail": detail,
            }
        )

    def ping(self) -> None:
        return None


@pytest.fixture()
def fake_chain() -> FakeChain:
    return FakeChain()


@pytest.fixture()
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture()
def service(fake_chain: FakeChain, fake_db: FakeDatabase) -> EvidenceService:
    return EvidenceService(fake_chain, fake_db, max_file_bytes=2 * 1024 * 1024)
