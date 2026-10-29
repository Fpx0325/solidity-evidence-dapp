"""存证业务编排：哈希计算、链上写入、链下记录与一致性判断。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .chain import EvidenceChain
from .db import Database
from .errors import (
    AlreadyExistsError,
    ConflictError,
    DatabaseUnavailableError,
    NotFoundError,
    PartialWriteError,
)
from .utils import (
    hash_stream,
    normalize_filename,
    normalize_hash,
    normalize_user,
    utc_iso,
)

logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    "verified": "文件哈希与链上记录一致，文件未被篡改",
    "inconsistent": "链上记录与链下记录不一致，请检查数据库是否被修改",
    "chain_only": "链上存证存在，但链下业务记录缺失（文件完整性仍可证明）",
    "db_only": "链下数据库有记录，但链上没有对应存证，存在篡改风险",
    "not_found": "未找到该哈希的存证记录（可能从未存证，或文件内容已被修改）",
}


class EvidenceService:
    def __init__(
        self, chain: EvidenceChain, db: Database, max_file_bytes: int
    ) -> None:
        self.chain = chain
        self.db = db
        self._max_bytes = max_file_bytes

    # ---------- 业务方法 ----------

    def create(
        self, stream: Any, raw_filename: str, raw_user: str
    ) -> dict[str, Any]:
        """计算哈希 -> 检查重复 -> 上链 -> 写入 MySQL，返回完整存证信息。"""
        file_name = normalize_filename(raw_filename)
        user_name = normalize_user(raw_user)

        digest, file_size = hash_stream(stream, self._max_file_bytes())
        chain_record = self.chain.get(digest)
        db_record = self.db.get_by_hash(digest)

        if chain_record.get("exists") or db_record is not None:
            summary = self._summarize(digest, chain_record, db_record)
            if chain_record.get("exists") and db_record is not None:
                message = "该文件已经存证，请直接查验"
            elif chain_record.get("exists"):
                message = "链上已存在该哈希，但链下业务记录缺失，请检查数据库"
            else:
                message = "数据库已有该哈希，但链上不存在对应存证，数据不一致"
            self._safe_log(
                action="upload",
                file_hash=digest,
                user_name=user_name,
                result="duplicate",
                file_name=file_name,
                detail=summary["status"],
            )
            raise AlreadyExistsError(message, detail=summary)

        stored = self.chain.store(digest)
        try:
            db_record = self.db.insert_evidence(
                file_name=file_name,
                file_hash=digest,
                user_name=user_name,
                block_number=stored["block_number"],
                tx_hash=stored["tx_hash"],
                chain_owner=stored["owner"],
                chain_timestamp=stored["timestamp"],
            )
        except DatabaseUnavailableError as exc:
            logger.error(
                "链上写入成功但 MySQL 记录失败 hash=%s tx=%s",
                digest,
                stored["tx_hash"],
            )
            raise PartialWriteError(
                "链上交易已成功，但 MySQL 记录失败；请修复数据库后用该哈希查验",
                detail={
                    "file_hash": digest,
                    "tx_hash": stored["tx_hash"],
                    "block_number": stored["block_number"],
                },
            ) from exc

        chain_record = {
            "exists": True,
            "owner": stored["owner"],
            "timestamp": stored["timestamp"],
            "chain_time": stored["chain_time"],
            "network": "ganache",
        }
        summary = self._summarize(digest, chain_record, db_record)
        summary["file_size"] = file_size

        self._safe_log(
            action="upload",
            file_hash=digest,
            user_name=user_name,
            result=summary["status"],
            file_name=file_name,
            detail=f"block={stored['block_number']}",
        )
        return summary

    def verify_file(
        self, stream: Any, raw_filename: str, raw_user: str | None
    ) -> dict[str, Any]:
        file_name = normalize_filename(raw_filename)
        user_name = normalize_user(raw_user, default="匿名访客")
        digest, file_size = hash_stream(stream, self._max_file_bytes())
        result = self.verify_hash(digest, user_name)
        result["checked_file_name"] = file_name
        result["checked_file_size"] = file_size
        return result

    def verify_hash(self, raw_hash: str, raw_user: str | None = None) -> dict[str, Any]:
        digest = normalize_hash(raw_hash)
        user_name = normalize_user(raw_user, default="匿名访客")
        chain_record = self.chain.get(digest)
        db_record = self.db.get_by_hash(digest)
        summary = self._summarize(digest, chain_record, db_record)
        self._safe_log(
            action="verify",
            file_hash=digest,
            user_name=user_name,
            result=summary["status"],
            file_name=summary.get("file_name"),
            detail=summary["message"],
        )
        return summary

    def get(self, raw_hash: str) -> dict[str, Any]:
        digest = normalize_hash(raw_hash)
        chain_record = self.chain.get(digest)
        db_record = self.db.get_by_hash(digest)
        if not chain_record.get("exists") and db_record is None:
            raise NotFoundError("未找到该哈希的存证记录")
        return self._summarize(digest, chain_record, db_record)

    def list_records(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.db.list_evidence(limit)

    def health(self) -> dict[str, Any]:
        database_status: dict[str, Any] = {"ok": False}
        try:
            self.db.ping()
            database_status = {"ok": True, "message": "MySQL 连接正常"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("数据库健康检查失败: %s", exc)
            database_status["message"] = getattr(exc, "message", str(exc))

        chain_status = self.chain.health()
        return {
            "ok": bool(database_status["ok"] and chain_status.get("ok")),
            "service": "solidity-evidence-dapp",
            "version": "1.0.0",
            "time": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "database": database_status,
            "chain": chain_status,
        }

    # ---------- 内部方法 ----------

    def _max_file_bytes(self) -> int:
        return self._max_bytes

    def _safe_log(self, **kwargs: Any) -> None:
        """审计日志失败不应影响主流程，只记录后端日志。"""
        try:
            self.db.log_operation(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入操作日志失败: %s", exc)

    @staticmethod
    def _summarize(
        digest: str,
        chain_record: dict[str, Any] | None,
        db_record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        chain_exists = bool(chain_record and chain_record.get("exists"))
        db_exists = db_record is not None

        if chain_exists and db_exists:
            owner_match = str(chain_record.get("owner", "")).lower() == str(
                db_record.get("chain_owner", "")
            ).lower()
            timestamp_match = int(chain_record.get("timestamp") or 0) == int(
                db_record.get("chain_timestamp") or 0
            )
            status = "verified" if owner_match and timestamp_match else "inconsistent"
        elif chain_exists:
            status = "chain_only"
        elif db_exists:
            status = "db_only"
        else:
            status = "not_found"

        record = db_record or {}
        chain_owner = (
            chain_record.get("owner") if chain_exists else record.get("chain_owner")
        )
        chain_timestamp = (
            chain_record.get("timestamp")
            if chain_exists
            else record.get("chain_timestamp")
        )
        chain_time = (
            chain_record.get("chain_time")
            if chain_exists
            else utc_iso(chain_timestamp)
        )

        return {
            "file_hash": digest,
            "file_name": record.get("file_name"),
            "user_name": record.get("user_name"),
            "exists_on_chain": chain_exists,
            "exists_in_database": db_exists,
            "status": status,
            "message": STATUS_MESSAGES[status],
            "integrity_verified": status in {"verified", "chain_only"},
            "chain_owner": chain_owner,
            "chain_timestamp": chain_timestamp,
            "chain_time": chain_time,
            "block_number": record.get("block_number"),
            "tx_hash": record.get("tx_hash"),
            "created_at": record.get("created_at"),
            "network": "ganache",
        }
