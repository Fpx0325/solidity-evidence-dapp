"""Flask 应用工厂：依赖装配、CORS、统一错误响应。"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .chain import EvidenceChain
from .config import Config
from .db import Database
from .errors import AppError
from .routes import api_bp
from .service import EvidenceService

logger = logging.getLogger(__name__)


def create_app(
    config: Config | None = None,
    service: EvidenceService | None = None,
) -> Flask:
    cfg = config or Config.from_env()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_content_length
    app.json.ensure_ascii = False

    origins: str | list[str] = (
        "*" if "*" in cfg.cors_origins else list(cfg.cors_origins)
    )
    CORS(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=False,
    )

    if service is None:
        db = Database(cfg)
        chain = EvidenceChain(cfg)
        service = EvidenceService(chain, db, cfg.max_file_bytes)

    app.extensions["config"] = cfg
    app.extensions["evidence_service"] = service
    app.register_blueprint(api_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.detail is not None:
            error["detail"] = exc.detail
        return jsonify({"success": False, "error": error}), exc.status_code

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_exc: RequestEntityTooLarge):
        return (
            jsonify(
                {
                    "success": False,
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": f"文件超过 {cfg.max_file_mb} MB 上限",
                        "detail": {"max_file_mb": cfg.max_file_mb},
                    },
                }
            ),
            413,
        )

    @app.errorhandler(404)
    def handle_not_found(exc: HTTPException):
        return (
            jsonify(
                {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "接口不存在"},
                }
            ),
            404,
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(exc: HTTPException):
        return (
            jsonify(
                {
                    "success": False,
                    "error": {
                        "code": "METHOD_NOT_ALLOWED",
                        "message": "请求方法不被允许",
                    },
                }
            ),
            405,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        # 保留 HTTPException 的状态码，但后端只提供 JSON API，因此统一返回 JSON
        if isinstance(exc, HTTPException):
            logger.warning("HTTP 错误: %s", exc)
            code = exc.name.upper().replace(" ", "_") if exc.name else "HTTP_ERROR"
            return (
                jsonify(
                    {
                        "success": False,
                        "error": {
                            "code": code,
                            "message": exc.description or "请求失败",
                        },
                    }
                ),
                exc.code or 500,
            )
        logger.exception("未处理的服务端异常")
        return (
            jsonify(
                {
                    "success": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "服务器内部错误，请查看后端日志",
                    },
                }
            ),
            500,
        )

    logging.basicConfig(
        level=logging.DEBUG if cfg.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not cfg.contract_address:
        logger.warning("尚未配置合约地址，请先运行 python scripts/deploy.py")

    return app
