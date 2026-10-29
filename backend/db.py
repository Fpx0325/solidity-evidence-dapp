"""MySQL 数据访问层：连接池、建表、存证记录与操作日志。"""

from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import mysql.connector
from mysql.connector import pooling

from .config import Config
from .errors import DatabaseUnavailableError
from .utils import row_created_at

logger = logging.getLogger(__name__)

CREATE_EVIDENCE_TABLE = """
CREATE TABLE IF NOT EXISTS evidence_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  file_name VARCHAR(255) NOT NULL,
  file_hash CHAR(64) NOT NULL,
  user_name VARCHAR(64) NOT NULL,
  block_number BIGINT UNSIGNED NOT NULL,
  tx_hash CHAR(66) NOT NULL,
  chain_owner VARCHAR(42) NOT NULL,
  chain_timestamp BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_file_hash (file_hash),
  KEY idx_created_at (created_at),
  KEY idx_user_name (user_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS operation_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  action VARCHAR(20) NOT NULL,
  file_name VARCHAR(255) NULL,
  file_hash CHAR(64) NOT NULL,
  user_name VARCHAR(64) NOT NULL,
  result VARCHAR(32) NOT NULL,
  detail VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_hash (file_hash),
  KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

RECORD_COLUMNS = """
  id, file_name, file_hash, user_name, block_number, tx_hash,
  chain_owner, chain_timestamp, created_at
"""


class Database:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._pool: pooling.MySQLConnectionPool | None = None
        self._schema_ready = False
        self._lock = threading.RLock()

    # ---------- 连接管理 ----------

    def _get_pool(self) -> pooling.MySQLConnectionPool:
        if self._pool is not None:
            return self._pool
        with self._lock:
            if self._pool is not None:
                return self._pool
            cfg = self._config
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name=f"evidence_{uuid.uuid4().hex[:8]}",
                    pool_size=max(1, min(cfg.mysql_pool_size, 20)),
                    pool_reset_session=True,
                    host=cfg.mysql_host,
                    port=cfg.mysql_port,
                    user=cfg.mysql_user,
                    password=cfg.mysql_password,
                    database=cfg.mysql_database,
                    charset="utf8mb4",
                    autocommit=False,
                    connection_timeout=5,
                )
            except mysql.connector.Error as exc:
                logger.error("MySQL 连接池创建失败: %s", exc)
                raise DatabaseUnavailableError(
                    "无法连接 MySQL，请检查服务是否启动以及 .env 配置"
                ) from exc
            return self._pool

    def _get_connection(self):
        try:
            return self._get_pool().get_connection()
        except mysql.connector.Error as exc:
            logger.error("从连接池获取 MySQL 连接失败: %s", exc)
            self._pool = None
            raise DatabaseUnavailableError(
                "数据库连接失败，请检查 MySQL 服务"
            ) from exc

    @contextmanager
    def _cursor(self, *, commit: bool = False) -> Iterator[Any]:
        self._ensure_schema()
        conn = self._get_connection()
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            yield cursor
            if commit:
                conn.commit()
        except mysql.connector.Error as exc:
            try:
                conn.rollback()
            except mysql.connector.Error:
                pass
            logger.error("MySQL 操作失败: %s", exc)
            raise DatabaseUnavailableError(
                "数据库操作失败，请查看后端日志"
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._lock:
            if self._schema_ready:
                return
            conn = None
            cursor = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(CREATE_EVIDENCE_TABLE)
                cursor.execute(CREATE_LOG_TABLE)
                conn.commit()
                self._schema_ready = True
                logger.info("MySQL 表结构检查完成")
            except mysql.connector.Error as exc:
                logger.error("MySQL 初始化表结构失败: %s", exc)
                try:
                    if conn is not None:
                        conn.rollback()
                except mysql.connector.Error:
                    pass
                raise DatabaseUnavailableError(
                    "MySQL 初始化失败，请确认数据库存在且账号有建表权限"
                ) from exc
            finally:
                if cursor is not None:
                    cursor.close()
                if conn is not None:
                    conn.close()

    # ---------- 记录操作 ----------

    @staticmethod
    def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["created_at"] = row_created_at(item.get("created_at"))
        return item

    def ping(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            cursor.fetchone()

    def insert_evidence(
        self,
        *,
        file_name: str,
        file_hash: str,
        user_name: str,
        block_number: int,
        tx_hash: str,
        chain_owner: str,
        chain_timestamp: int,
    ) -> dict[str, Any]:
        with self._cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO evidence_records
                  (file_name, file_hash, user_name, block_number, tx_hash,
                   chain_owner, chain_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_name,
                    file_hash,
                    user_name,
                    block_number,
                    tx_hash,
                    chain_owner,
                    chain_timestamp,
                ),
            )
            record_id = cursor.lastrowid
            cursor.execute(
                f"SELECT {RECORD_COLUMNS} FROM evidence_records WHERE id = %s",
                (record_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise DatabaseUnavailableError("写入成功但无法读回存证记录")
        return self._serialize(row)  # type: ignore[return-value]

    def get_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {RECORD_COLUMNS} FROM evidence_records WHERE file_hash = %s",
                (file_hash,),
            )
            return self._serialize(cursor.fetchone())

    def list_evidence(self, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {RECORD_COLUMNS} FROM evidence_records "
                "ORDER BY id DESC LIMIT %s",
                (safe_limit,),
            )
            rows = cursor.fetchall()
        return [self._serialize(row) for row in rows]  # type: ignore[misc]

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
        with self._cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO operation_logs
                  (action, file_name, file_hash, user_name, result, detail)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    action[:20],
                    file_name[:255] if file_name else None,
                    file_hash,
                    user_name[:64],
                    result[:32],
                    detail[:255] if detail else None,
                ),
            )

    def close(self) -> None:
        with self._lock:
            self._pool = None
            self._schema_ready = False
