"""应用配置：从项目根目录的 .env 读取，未配置项使用本地开发默认值。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值为 {raw!r}") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    debug: bool
    cors_origins: tuple[str, ...]
    rpc_url: str
    chain_id: int
    account_index: int
    tx_timeout: int
    max_file_mb: int
    contract_address: str | None
    abi_path: Path
    deployment_path: Path
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_pool_size: int

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    @property
    def max_content_length(self) -> int:
        # 给 multipart 边界和表单字段留出余量
        return self.max_file_bytes + 2 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env", override=False)

        deployment_path = PROJECT_ROOT / "deployments" / "ganache.json"
        contract_address = os.getenv("CONTRACT_ADDRESS", "").strip() or None
        if contract_address is None:
            # 部署脚本生成的地址作为默认值，方便“部署后直接启动”
            try:
                data = json.loads(deployment_path.read_text(encoding="utf-8"))
                address = str(data.get("contract_address", "")).strip()
                contract_address = address or None
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                contract_address = None

        raw_origins = os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080"
        ).strip()
        cors_origins = tuple(
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        )

        max_file_mb = _env_int("MAX_FILE_MB", 10)
        if max_file_mb < 1 or max_file_mb > 100:
            raise ValueError("MAX_FILE_MB 必须在 1 到 100 之间")

        return cls(
            host=os.getenv("FLASK_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_env_int("FLASK_PORT", 5000),
            debug=_env_bool("FLASK_DEBUG", False),
            cors_origins=cors_origins or ("http://127.0.0.1:8080",),
            rpc_url=os.getenv("GANACHE_RPC_URL", "http://127.0.0.1:7545").strip(),
            chain_id=_env_int("GANACHE_CHAIN_ID", 1337),
            account_index=_env_int("GANACHE_ACCOUNT_INDEX", 0),
            tx_timeout=_env_int("CHAIN_TX_TIMEOUT", 90),
            max_file_mb=max_file_mb,
            contract_address=contract_address,
            abi_path=PROJECT_ROOT / "artifacts" / "EvidenceRegistry.json",
            deployment_path=deployment_path,
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1").strip(),
            mysql_port=_env_int("MYSQL_PORT", 3306),
            mysql_user=os.getenv("MYSQL_USER", "evidence_app").strip(),
            mysql_password=os.getenv("MYSQL_PASSWORD", ""),
            mysql_database=os.getenv("MYSQL_DATABASE", "evidence_dapp").strip(),
            mysql_pool_size=_env_int("MYSQL_POOL_SIZE", 5),
        )
