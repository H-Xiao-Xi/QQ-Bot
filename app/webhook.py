"""QQ Open Platform webhook protocol, API v2."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response

from nacl.exceptions import BadSignatureError
from app.crypto import validation_signature, verify_callback_signature, verify_key_from_secret

logger = logging.getLogger("qqbot.webhook")

OP_DISPATCH = 0
OP_HTTP_ACK = 12
OP_URL_VALIDATION = 13
ACK_BODY = b'{"op":12}'


def json_response(data: dict[str, Any], status_code: int = 200) -> Response:
    body = json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return Response(content=body, media_type="application/json", status_code=status_code)


def ack_response() -> Response:
    return Response(content=ACK_BODY, media_type="application/json", status_code=200)


def parse_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json")
    return payload


def opcode(payload: dict[str, Any]) -> int | None:
    op = payload.get("op")
    if op is None:
        return None
    try:
        return int(op)
    except (TypeError, ValueError):
        return None


def field_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value)


def validation_fields(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("d", payload)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    plain_token = field_text(data.get("plain_token") or payload.get("plain_token"))
    event_ts = field_text(data.get("event_ts") or payload.get("event_ts"))
    return plain_token, event_ts


def header(request: Request, name: str) -> str:
    return (request.headers.get(name) or "").strip()


def handle_validation(secret: str, payload: dict[str, Any]) -> Response:
    if not secret:
        raise HTTPException(status_code=503, detail="bot credentials are not configured")
    plain_token, event_ts = validation_fields(payload)
    if not plain_token or not event_ts:
        raise HTTPException(status_code=400, detail="invalid validation payload")
    signature = validation_signature(secret, event_ts, plain_token)
    message = f"{event_ts}{plain_token}".encode("utf-8")
    try:
        verify_key_from_secret(secret).verify(message, bytes.fromhex(signature))
    except (BadSignatureError, ValueError) as exc:
        logger.exception("local validation signature failed")
        raise HTTPException(status_code=500, detail="validation signature failed") from exc
    logger.info(
        "webhook url validation secret_len=%s event_ts=%s token_len=%s sig_prefix=%s",
        len(secret),
        event_ts,
        len(plain_token),
        signature[:16],
    )
    response = json_response({"plain_token": plain_token, "signature": signature})
    response.headers["X-QQBot-Protocol"] = "url-validation"
    return response


def verify_dispatch(secret: str, request: Request, raw: bytes) -> None:
    if not secret:
        raise HTTPException(status_code=503, detail="bot credentials are not configured")
    signature = header(request, "X-Signature-Ed25519")
    timestamp = header(request, "X-Signature-Timestamp")
    if not verify_callback_signature(secret, timestamp, raw, signature):
        raise HTTPException(status_code=401, detail="invalid signature")
