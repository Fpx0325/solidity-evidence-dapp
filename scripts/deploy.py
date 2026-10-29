#!/usr/bin/env python
"""把 EvidenceRegistry 合约部署到本地 Ganache，并保存部署信息。

用法：
    python scripts/deploy.py

部署成功后后端会自动读取 deployments/ganache.json 中的合约地址。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = PROJECT_ROOT / "artifacts" / "EvidenceRegistry.json"
DEPLOYMENT_PATH = PROJECT_ROOT / "deployments" / "ganache.json"

load_dotenv(PROJECT_ROOT / ".env")


def fail(message: str) -> None:
    print(f"[失败] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    try:
        from web3 import Web3
    except ImportError:
        fail("缺少 web3.py，请先执行 pip install -r requirements.txt")

    rpc_url = os.getenv("GANACHE_RPC_URL", "http://127.0.0.1:7545").strip()
    expected_chain_id = int(os.getenv("GANACHE_CHAIN_ID", "1337"))
    account_index = int(os.getenv("GANACHE_ACCOUNT_INDEX", "0"))

    if not ARTIFACT_PATH.exists():
        fail("未找到合约构建产物，请先执行 npm run compile")

    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    if not artifact.get("abi") or artifact.get("bytecode") in (None, "", "0x"):
        fail("合约构建产物不完整，请重新执行 npm run compile")

    print(f"[1/4] 连接 Ganache：{rpc_url}")
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
    if not web3.is_connected():
        fail(
            "无法连接 Ganache。请确认 Ganache 已启动，"
            f"且 RPC 地址为 {rpc_url}"
        )

    chain_id = web3.eth.chain_id
    print(f"[2/4] 已连接，Chain ID = {chain_id}，最新区块 #{web3.eth.block_number}")
    if chain_id != expected_chain_id:
        print(
            f"       [提示] 当前 Chain ID 与 .env 中的 {expected_chain_id} 不同，"
            "本项目本地演示通常使用 1337。"
        )

    accounts = web3.eth.accounts
    if not accounts:
        fail("Ganache 没有可用账户，请检查启动参数")
    if account_index < 0 or account_index >= len(accounts):
        fail(f"GANACHE_ACCOUNT_INDEX={account_index} 超出账户范围（共 {len(accounts)} 个）")

    deployer = accounts[account_index]
    balance = web3.eth.get_balance(deployer)
    print(f"[3/4] 部署账户：{deployer}（余额 {web3.from_wei(balance, 'ether')} ETH）")

    contract = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    try:
        tx_hash = contract.constructor().transact(
            {"from": deployer, "gas": 2_500_000}
        )
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    except Exception as exc:  # noqa: BLE001 - CLI 需要给出可读错误
        fail(f"部署交易失败：{exc}")

    if receipt.status != 1 or not receipt.contractAddress:
        fail("部署交易回滚或没有合约地址，请检查 Ganache 日志")

    contract_address = Web3.to_checksum_address(receipt.contractAddress)
    code = web3.eth.get_code(contract_address)
    if not code or code == b"\x00":
        fail("部署后未读到合约字节码，部署可能失败")

    deployment = {
        "network": "ganache",
        "rpc_url": rpc_url,
        "chain_id": chain_id,
        "contract_name": artifact.get("contractName", "EvidenceRegistry"),
        "contract_address": contract_address,
        "deployer": deployer,
        "transaction_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
    }
    DEPLOYMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEPLOYMENT_PATH.write_text(
        json.dumps(deployment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[4/4] 部署成功！区块 #{receipt.blockNumber}")
    print(f"       合约地址：{contract_address}")
    print(f"       部署记录：{DEPLOYMENT_PATH}")
    print("\n接下来启动后端：python run.py")

    env_address = os.getenv("CONTRACT_ADDRESS", "").strip()
    if env_address:
        print(
            "\n[注意] .env 中已设置 CONTRACT_ADDRESS，它会覆盖刚才的部署记录。"
            "\n       如需使用新合约，请清空 .env 中的 CONTRACT_ADDRESS 或填入上面的地址。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
