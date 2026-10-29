#!/usr/bin/env python
"""对已经启动的 DApp 做一次端到端冒烟测试（仅依赖标准库）。

前置条件：Ganache、MySQL、后端服务均已启动，合约已部署。

用法：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --file README.md --user demo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path


def build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----EvidenceSmoke{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                f"{value}\r\n".encode(),
            ]
        )
    filename = file_path.name
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post(url: str, data: bytes, content_type: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def get(url: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(description="存证 DApp 端到端冒烟测试")
    parser.add_argument("--api", default="http://127.0.0.1:5000/api")
    parser.add_argument("--file", default=None, help="用于存证和查验的文件")
    parser.add_argument("--user", default="smoke-test")
    args = parser.parse_args()

    api = args.api.rstrip("/")
    temporary: tempfile.NamedTemporaryFile | None = None
    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.is_file():
            print(f"[失败] 文件不存在：{file_path}")
            return 1
    else:
        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="evidence-smoke-",
            delete=False,
            encoding="utf-8",
        )
        temporary.write(
            f"evidence smoke test\n{datetime.now().isoformat()}\n{uuid.uuid4()}\n"
        )
        temporary.close()
        file_path = Path(temporary.name)

    local_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    print(f"文件：{file_path}")
    print(f"本地 SHA-256：{local_hash}")

    status, health = get(f"{api}/health")
    print(f"\n[健康检查] HTTP {status}")
    print(json.dumps(health, ensure_ascii=False, indent=2))
    if status != 200 or not health.get("data", {}).get("ok"):
        print("\n[失败] 服务健康检查未通过，请先修复链或数据库连接。")
        return 1

    body, content_type = build_multipart({"user_name": args.user}, file_path)
    status, upload_response = post(f"{api}/evidence", body, content_type)
    print(f"\n[上传存证] HTTP {status}")

    if status == 201:
        record = upload_response.get("data", {})
        print(f"  区块高度：{record.get('block_number')}")
        print(f"  交易哈希：{record.get('tx_hash')}")
    elif status == 409:
        error = upload_response.get("error", {})
        print(f"  已存在：{error.get('message')}")
        detail = error.get("detail")
        if detail:
            print(f"  已有记录区块：{detail.get('block_number')}")
    else:
        print(json.dumps(upload_response, ensure_ascii=False, indent=2))
        print("\n[失败] 存证写入失败。")
        return 1

    body, content_type = build_multipart({"user_name": args.user}, file_path)
    status, verify_response = post(f"{api}/verify", body, content_type)
    print(f"\n[文件查验] HTTP {status}")
    data = verify_response.get("data", {})
    print(f"  状态：{data.get('status')}")
    print(f"  说明：{data.get('message')}")
    print(f"  链上存在：{data.get('exists_on_chain')}")
    print(f"  区块高度：{data.get('block_number')}")

    if temporary is not None:
        Path(temporary.name).unlink(missing_ok=True)

    if status != 200 or data.get("status") not in {"verified", "chain_only"}:
        print("\n[失败] 查验未通过。")
        return 1
    if data.get("file_hash") != local_hash:
        print("\n[失败] 后端返回的哈希与本地计算结果不一致。")
        return 1

    print("\n[通过] 上传、上链、链下记录与文件查验全链路正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
