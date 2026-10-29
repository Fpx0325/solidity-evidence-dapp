#!/usr/bin/env python
"""启动 Flask API 服务。"""

from __future__ import annotations

from backend.app import create_app
from backend.config import Config

app = create_app()


if __name__ == "__main__":
    cfg: Config = app.extensions["config"]
    print("=" * 58)
    print("  Solidity 智能合约存证 DApp - 后端 API")
    print(f"  API:  http://{cfg.host}:{cfg.port}/api")
    print(f"  链:   {cfg.rpc_url} (Chain ID {cfg.chain_id})")
    print(f"  合约: {cfg.contract_address or '未部署，请先运行 python scripts/deploy.py'}")
    print(f"  MySQL: {cfg.mysql_user}@{cfg.mysql_host}:{cfg.mysql_port}/{cfg.mysql_database}")
    print("=" * 58)
    app.run(
        host=cfg.host,
        port=cfg.port,
        debug=cfg.debug,
        use_reloader=cfg.debug,
        threaded=True,
    )
