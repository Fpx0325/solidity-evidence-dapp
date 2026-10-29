"""统一的业务异常类型，供路由层转换为 JSON 响应。"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """可安全展示给客户端的业务异常。"""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        detail: Any | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class FileTooLargeError(ValidationError):
    status_code = 413
    code = "FILE_TOO_LARGE"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class AlreadyExistsError(AppError):
    status_code = 409
    code = "ALREADY_EXISTS"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class ChainUnavailableError(ServiceUnavailableError):
    code = "CHAIN_UNAVAILABLE"


class DatabaseUnavailableError(ServiceUnavailableError):
    code = "DATABASE_UNAVAILABLE"


class PartialWriteError(AppError):
    """链上交易成功，但链下落库失败。"""

    status_code = 500
    code = "CHAIN_WRITTEN_DB_FAILED"
