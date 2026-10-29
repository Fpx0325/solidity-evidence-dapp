"""通用工具：文件哈希、字段校验与时间格式化。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import BinaryIO

from .errors import FileTooLargeError, ValidationError

HASH_PATTERN = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")
CHUNK_SIZE = 1024 * 1024


def hash_stream(stream: BinaryIO, max_bytes: int) -> tuple[str, int]:
    """分块计算 SHA-256，避免把大文件整体读进内存，也不落盘。"""
    hasher = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise ValidationError("无法读取上传文件")
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(
                f"文件超过 {max_bytes // (1024 * 1024)} MB 上限",
                detail={"max_file_mb": max_bytes // (1024 * 1024)},
            )
        hasher.update(chunk)
    return hasher.hexdigest(), total


def normalize_hash(value: str | None) -> str:
    """把 0x 开头的 SHA-256 摘要规范为 64 位小写十六进制。"""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("请提供文件的 SHA-256 哈希")
    raw = value.strip()
    if not HASH_PATTERN.fullmatch(raw):
        raise ValidationError("哈希格式不正确，应为 64 位十六进制字符（可带 0x 前缀）")
    return raw.removeprefix("0x").removeprefix("0X").lower()


def normalize_filename(value: str | None) -> str:
    """只保留文件名本身，不信任浏览器传来的路径。"""
    name = (value or "").replace("\\", "/").split("/")[-1]
    name = "".join(char for char in name if char.isprintable()).strip()
    if not name:
        name = "未命名文件"
    return name[:180]


def normalize_user(value: str | None, *, default: str | None = None) -> str:
    user = (value or "").strip()
    if not user:
        if default is not None:
            return default
        raise ValidationError("请填写操作人")
    if len(user) > 40:
        raise ValidationError("操作人名称不能超过 40 个字符")
    if any(ord(char) < 32 for char in user):
        raise ValidationError("操作人名称包含非法控制字符")
    return user


def utc_iso(timestamp: int | float | None) -> str | None:
    if timestamp is None:
        return None
    return (
        datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def row_created_at(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)
