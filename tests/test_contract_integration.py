"""真实 Ganache 合约集成测试（默认跳过）。

运行方式：先启动 Ganache，再执行
    RUN_CHAIN_TESTS=1 pytest -m integration
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

web3 = pytest.importorskip("web3")
from web3 import Web3  # noqa: E402

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "artifacts" / "EvidenceRegistry.json"
RPC_URL = os.getenv("GANACHE_RPC_URL", "http://127.0.0.1:7545")


@pytest.fixture(scope="module")
def deployed():
    if os.getenv("RUN_CHAIN_TESTS") != "1":
        pytest.skip("设置 RUN_CHAIN_TESTS=1 后才运行真实链测试")
    if not ARTIFACT.exists():
        pytest.skip("缺少合约构建产物，请先 npm run compile")

    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 5}))
    if not w3.is_connected():
        pytest.skip(f"无法连接 Ganache: {RPC_URL}")

    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    account = w3.eth.accounts[0]
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = contract.constructor().transact({"from": account, "gas": 2_500_000})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    instance = w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])
    return w3, instance, account


def test_store_and_query(deployed):
    w3, contract, account = deployed
    digest = Web3.keccak(text=f"pytest-{time.time_ns()}")
    assert contract.functions.verifyEvidence(digest).call() is False

    tx_hash = contract.functions.storeEvidence(digest).transact(
        {"from": account, "gas": 200_000}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    assert receipt.status == 1

    exists, owner, timestamp = contract.functions.getEvidence(digest).call()
    assert exists is True
    assert owner.lower() == account.lower()
    assert timestamp > 0
    assert contract.functions.verifyEvidence(digest).call() is True


def test_duplicate_reverts(deployed):
    w3, contract, account = deployed
    digest = Web3.keccak(text=f"duplicate-{time.time_ns()}")
    first = contract.functions.storeEvidence(digest).transact(
        {"from": account, "gas": 200_000}
    )
    assert w3.eth.wait_for_transaction_receipt(first, timeout=60).status == 1

    duplicate = contract.functions.storeEvidence(digest).transact(
        {"from": account, "gas": 200_000}
    )
    receipt = w3.eth.wait_for_transaction_receipt(duplicate, timeout=60)
    assert receipt.status == 0


def test_empty_hash_reverts(deployed):
    w3, contract, account = deployed
    tx_hash = contract.functions.storeEvidence(b"\x00" * 32).transact(
        {"from": account, "gas": 200_000}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    assert receipt.status == 0
