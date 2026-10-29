"""区块链访问层：连接 Ganache、读取合约、发送存证交易。"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted

from .config import Config
from .errors import ChainUnavailableError
from .utils import normalize_hash, utc_iso

logger = logging.getLogger(__name__)


class EvidenceChain:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._web3: Web3 | None = None
        self._contract: Any = None
        self._lock = threading.RLock()

    # ---------- 初始化 ----------

    def _abi(self) -> list[dict[str, Any]]:
        path: Path = self._config.abi_path
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ChainUnavailableError(
                "未找到合约 ABI，请先执行 npm run compile"
            ) from exc
        except (json.JSONDecodeError, OSError) as exc:
            raise ChainUnavailableError("合约 ABI 文件无法读取") from exc
        abi = artifact.get("abi")
        if not isinstance(abi, list) or not abi:
            raise ChainUnavailableError("合约 ABI 为空，请重新编译合约")
        return abi

    def _ensure_ready(self) -> tuple[Web3, Any]:
        if self._web3 is not None and self._contract is not None:
            return self._web3, self._contract

        with self._lock:
            if self._web3 is not None and self._contract is not None:
                return self._web3, self._contract

            address = self._config.contract_address
            if not address:
                raise ChainUnavailableError(
                    "尚未部署合约，请先运行 python scripts/deploy.py",
                    detail={"hint": "部署后重启后端"},
                )

            web3 = Web3(
                Web3.HTTPProvider(
                    self._config.rpc_url, request_kwargs={"timeout": 10}
                )
            )
            if not web3.is_connected():
                raise ChainUnavailableError(
                    "无法连接 Ganache，请确认本地链已启动且 RPC 地址正确"
                )

            try:
                checksum_address = Web3.to_checksum_address(address)
            except ValueError as exc:
                raise ChainUnavailableError(
                    "CONTRACT_ADDRESS 不是合法的以太坊地址"
                ) from exc

            code = web3.eth.get_code(checksum_address)
            if not code or code == b"\x00":
                raise ChainUnavailableError(
                    "合约地址上没有代码。若 Ganache 已重启，请重新执行部署脚本",
                    detail={"contract_address": checksum_address},
                )

            contract = web3.eth.contract(address=checksum_address, abi=self._abi())
            self._web3 = web3
            self._contract = contract
            return web3, contract

    # ---------- 查询 ----------

    def get(self, file_hash: str) -> dict[str, Any]:
        digest = normalize_hash(file_hash)
        web3, contract = self._ensure_ready()
        try:
            exists, owner, timestamp = contract.functions.getEvidence(
                bytes.fromhex(digest)
            ).call()
        except ContractLogicError as exc:
            logger.error("查询存证合约失败: %s", exc)
            raise ChainUnavailableError("链上查询失败：合约调用回滚") from exc
        except Exception as exc:  # noqa: BLE001 - RPC 异常类型较多，统一转业务错误
            logger.exception("查询存证合约异常")
            raise ChainUnavailableError(f"链上查询失败：{exc}") from exc

        return {
            "exists": bool(exists),
            "owner": owner if exists else None,
            "timestamp": int(timestamp) if exists else None,
            "chain_time": utc_iso(timestamp) if exists else None,
            "network": "ganache",
        }

    def latest_block(self) -> dict[str, Any]:
        web3, _ = self._ensure_ready()
        try:
            block = web3.eth.get_block("latest")
            return {
                "chain_id": web3.eth.chain_id,
                "block_number": int(block.number),
                "block_hash": block.hash.hex(),
                "block_time": utc_iso(block.timestamp),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("读取最新区块失败: %s", exc)
            raise ChainUnavailableError("读取最新区块失败") from exc

    # ---------- 写入 ----------

    def store(self, file_hash: str) -> dict[str, Any]:
        """使用 Ganache 解锁账户发送存证交易，等待回执后返回区块信息。"""
        digest = normalize_hash(file_hash)
        web3, contract = self._ensure_ready()

        try:
            accounts = web3.eth.accounts
        except Exception as exc:  # noqa: BLE001
            raise ChainUnavailableError("无法读取 Ganache 账户") from exc

        if not accounts:
            raise ChainUnavailableError("Ganache 没有可用账户")
        index = self._config.account_index
        if index < 0 or index >= len(accounts):
            raise ChainUnavailableError(
                "GANACHE_ACCOUNT_INDEX 超出可用账户范围",
                detail={"available_accounts": len(accounts)},
            )
        account = accounts[index]

        try:
            tx_hash = contract.functions.storeEvidence(
                bytes.fromhex(digest)
            ).transact({"from": account, "gas": 300_000})
            receipt = web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self._config.tx_timeout
            )
        except ContractLogicError as exc:
            logger.warning("存证交易回滚: %s", exc)
            raise ChainUnavailableError(
                "链上交易被合约拒绝，可能该哈希已经存证"
            ) from exc
        except TimeExhausted as exc:
            raise ChainUnavailableError(
                "等待链上交易确认超时，请检查 Ganache 状态"
            ) from exc
        except ValueError as exc:
            message = str(exc)
            logger.warning("发送存证交易失败: %s", message)
            if "already exists" in message.lower() or "EvidenceAlreadyExists" in message:
                raise ChainUnavailableError(
                    "该文件哈希已经存证", code="ALREADY_EXISTS", status_code=409
                ) from exc
            raise ChainUnavailableError(f"发送存证交易失败：{message}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("发送存证交易异常")
            raise ChainUnavailableError(f"发送存证交易失败：{exc}") from exc

        if receipt.status != 1:
            raise ChainUnavailableError("存证交易已回滚，链上未写入")

        try:
            block = web3.eth.get_block(receipt.blockNumber)
            timestamp = int(block.timestamp)
        except Exception as exc:  # noqa: BLE001
            logger.warning("交易成功但读取区块失败: %s", exc)
            timestamp = 0

        result = {
            "tx_hash": receipt.transactionHash.hex(),
            "block_number": int(receipt.blockNumber),
            "block_hash": receipt.blockHash.hex(),
            "owner": account,
            "timestamp": timestamp,
            "chain_time": utc_iso(timestamp) if timestamp else None,
        }
        logger.info(
            "存证上链成功 hash=%s tx=%s block=%s",
            digest,
            result["tx_hash"],
            result["block_number"],
        )
        return result

    # ---------- 健康检查 ----------

    def health(self) -> dict[str, Any]:
        """始终返回结构化状态，不向上抛异常，供健康检查接口使用。"""
        base: dict[str, Any] = {
            "ok": False,
            "rpc_url": self._config.rpc_url,
            "expected_chain_id": self._config.chain_id,
            "contract_address": self._config.contract_address,
        }
        try:
            web3 = Web3(
                Web3.HTTPProvider(
                    self._config.rpc_url, request_kwargs={"timeout": 5}
                )
            )
            if not web3.is_connected():
                base["message"] = "无法连接 Ganache"
                return base

            base["chain_id"] = web3.eth.chain_id
            base["block_number"] = int(web3.eth.block_number)
            base["chain_connected"] = True

            address = self._config.contract_address
            if not address:
                base["message"] = "尚未部署合约"
                return base

            code = web3.eth.get_code(Web3.to_checksum_address(address))
            if not code or code == b"\x00":
                base["message"] = "合约地址上没有代码，请重新部署"
                return base

            base["ok"] = True
            base["message"] = "Ganache 与合约连接正常"
            return base
        except Exception as exc:  # noqa: BLE001
            logger.warning("链健康检查失败: %s", exc)
            base["message"] = f"链连接检查失败：{exc}"
            return base
