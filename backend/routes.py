"""REST API 路由。"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .errors import ValidationError
from .service import EvidenceService

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _service() -> EvidenceService:
    return current_app.extensions["evidence_service"]


def _ok(data, status: int = 200):
    return jsonify({"success": True, "data": data}), status


@api_bp.get("")
def api_index():
    return _ok(
        {
            "name": "Solidity 智能合约存证 API",
            "version": "1.0.0",
            "endpoints": [
                "POST /api/evidence",
                "POST /api/verify",
                "GET /api/evidence/<hash>",
                "GET /api/records",
                "GET /api/health",
            ],
        }
    )


@api_bp.post("/evidence")
def create_evidence():
    if "file" not in request.files:
        raise ValidationError("请选择要存证的文件", detail={"field": "file"})
    upload = request.files["file"]
    if not upload.filename:
        raise ValidationError("文件名为空，请重新选择")
    user_name = request.form.get("user_name", "")
    result = _service().create(upload.stream, upload.filename, user_name)
    return _ok(result, 201)


@api_bp.post("/verify")
def verify_evidence():
    user_name = request.form.get("user_name")
    upload = request.files.get("file")

    if upload is not None and upload.filename:
        result = _service().verify_file(upload.stream, upload.filename, user_name)
        return _ok(result)

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        hash_value = payload.get("hash")
        user_name = payload.get("user_name") or user_name
    else:
        hash_value = request.form.get("hash")

    if not hash_value:
        raise ValidationError("请上传文件，或提供要查验的 SHA-256 哈希")
    result = _service().verify_hash(str(hash_value), user_name)
    return _ok(result)


@api_bp.get("/evidence/<string:file_hash>")
def get_evidence(file_hash: str):
    return _ok(_service().get(file_hash))


@api_bp.get("/records")
def list_records():
    raw_limit = request.args.get("limit", "10")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ValidationError("limit 必须是正整数") from exc
    if limit < 1 or limit > 50:
        raise ValidationError("limit 必须在 1 到 50 之间")
    return _ok({"items": _service().list_records(limit), "limit": limit})


@api_bp.get("/health")
def health():
    # 契约：始终返回 200，客户端根据 data.ok 判断健康状况
    return _ok(_service().health())
