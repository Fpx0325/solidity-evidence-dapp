# API 参考

后端默认监听 `http://127.0.0.1:5000`，所有接口前缀为 `/api`，请求与响应均为 UTF-8 JSON（上传接口除外）。

## 通用响应

成功：

```json
{
  "success": true,
  "data": {}
}
```

失败：

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请提供文件的 SHA-256 哈希",
    "detail": null
  }
}
```

`detail` 可选，用于返回字段错误或已存在的存证信息。

| HTTP 状态 | `error.code` | 含义 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 参数、文件名、哈希或操作人校验失败 |
| 404 | `NOT_FOUND` | 指定哈希没有存证记录 |
| 409 | `ALREADY_EXISTS` | 同一哈希已经存证 |
| 409 | `CONFLICT` | 链上链下数据存在冲突 |
| 413 | `FILE_TOO_LARGE` | 文件超出 `MAX_FILE_MB` |
| 500 | `CHAIN_WRITTEN_DB_FAILED` | 交易已上链，但 MySQL 写入失败 |
| 503 | `CHAIN_UNAVAILABLE` | Ganache/合约不可用 |
| 503 | `DATABASE_UNAVAILABLE` | MySQL 不可用 |

## POST `/api/evidence`

上传文件并发起存证。`Content-Type: multipart/form-data`。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 单个文件，默认上限 10 MB |
| `user_name` | 是 | 操作人业务标签，1–40 字符，非登录身份 |

请求示例：

```bash
curl -F "file=@README.md" -F "user_name=张三" \
  http://127.0.0.1:5000/api/evidence
```

成功响应 `201`：

```json
{
  "success": true,
  "data": {
    "file_hash": "58e5a8fb1b1b8f0ed2c26d6b4d8f0e2f6b1d7ac4dd25f4d3ad9e1be31f2c8a11",
    "file_name": "README.md",
    "user_name": "张三",
    "exists_on_chain": true,
    "exists_in_database": true,
    "status": "verified",
    "message": "文件哈希与链上记录一致，文件未被篡改",
    "integrity_verified": true,
    "chain_owner": "0x9A3A8eD08cE1a5a0cB1d362f99F6E12e9B85bC21",
    "chain_timestamp": 1761744000,
    "chain_time": "2026-10-29T08:00:00Z",
    "block_number": 8,
    "tx_hash": "0x4f1d36e2e8a9a3143e7b0f784e890f7a52ab73c0cd87e802cb26e063fb5e0c58",
    "created_at": "2026-10-29T16:00:00",
    "network": "ganache",
    "file_size": 2384
  }
}
```

如果同一文件已存在，返回 `409`，`error.detail` 是已有的存证摘要，可直接用于展示。

## POST `/api/verify`

重新计算并查验文件，或按哈希查询。支持两种请求：

### 上传文件

`multipart/form-data`：`file`（必填）、`user_name`（可选）。

```bash
curl -F "file=@README.md" -F "user_name=核验员" \
  http://127.0.0.1:5000/api/verify
```

### 直接查询哈希

`application/json`：

```bash
curl -H "Content-Type: application/json" \
  -d '{"hash":"58e5a8...8a11","user_name":"核验员"}' \
  http://127.0.0.1:5000/api/verify
```

成功响应 `200`，字段与存证接口基本一致，并增加：

```json
{
  "checked_file_name": "README.md",
  "checked_file_size": 2384
}
```

文件未找到不是 HTTP 错误：接口仍返回 `200`，`data.status` 为 `not_found`。

### `status` 取值

| `status` | `integrity_verified` | 含义 |
| --- | --- | --- |
| `verified` | `true` | 链上与链下记录一致，文件完整 |
| `chain_only` | `true` | 链上存在，链下记录缺失；完整性仍成立 |
| `inconsistent` | `false` | 链上写入账户/时间戳与数据库不一致 |
| `db_only` | `false` | 数据库有记录，但链上找不到对应存证 |
| `not_found` | `false` | 未找到记录，可能从未存证或文件被修改 |

## GET `/api/evidence/<hash>`

按 64 位 SHA-256 查询单条存证，`0x` 前缀可选。不存在返回 `404`。

```bash
curl http://127.0.0.1:5000/api/evidence/58e5a8...8a11
```

## GET `/api/records?limit=10`

返回 MySQL 中最近的存证记录，`limit` 取值 1–50。

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "file_name": "README.md",
        "file_hash": "58e5a8...",
        "user_name": "张三",
        "block_number": 8,
        "tx_hash": "0x4f1d...",
        "chain_owner": "0x9A3A...",
        "chain_timestamp": 1761744000,
        "created_at": "2026-10-29T16:00:00"
      }
    ],
    "limit": 10
  }
}
```

## GET `/api/health`

用于前端显示服务状态。接口始终返回 HTTP 200，根据 `data.ok` 判断整体状态。

```json
{
  "success": true,
  "data": {
    "ok": true,
    "service": "solidity-evidence-dapp",
    "version": "1.0.0",
    "time": "2026-10-29T08:00:00Z",
    "database": { "ok": true, "message": "MySQL 连接正常" },
    "chain": {
      "ok": true,
      "message": "Ganache 与合约连接正常",
      "rpc_url": "http://127.0.0.1:7545",
      "expected_chain_id": 1337,
      "chain_id": 1337,
      "block_number": 9,
      "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    }
  }
}
```

## CORS

默认允许的来源在 `.env` 的 `CORS_ORIGINS` 中配置，默认是：

```text
http://127.0.0.1:8080,http://localhost:8080
```

本地演示可以设为 `*`，生产环境应收紧为明确域名。
