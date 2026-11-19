from app.api_client import IP_WHITELIST_HINT, message_body, openapi_failure


def test_openapi_failure_treats_business_code_as_error():
    text = openapi_failure(200, {"code": 11298, "message": "接口访问源IP不在白名单"})
    assert "11298" in text
    assert IP_WHITELIST_HINT in text


def test_openapi_failure_ignores_success_payload():
    assert openapi_failure(200, {"id": "msg-1", "timestamp": "2026-01-01"}) == ""
    assert openapi_failure(200, {"access_token": "tok", "expires_in": 7200}) == ""
    assert openapi_failure(200, {}) == ""


def test_openapi_failure_http_error():
    text = openapi_failure(401, {"message": "unauthorized"})
    assert "unauthorized" in text


def test_openapi_failure_async_success():
    assert openapi_failure(201, {"err_code": 304024, "message": "等待人工审核"}) == ""
    assert openapi_failure(202, {"code": 304023, "message": "async ok"}) == ""


def test_openapi_failure_includes_trace_id():
    text = openapi_failure(200, {"err_code": 40034005, "message": "回复消息msg_id已过期", "trace_id": "abc123"})
    assert "40034005" in text
    assert "trace=abc123" in text


def test_message_body_prefers_msg_id_over_event_id():
    body = message_body(msg_type=0, msg_id="m1", msg_seq=1, event_id="e1", content="hi")
    assert body["msg_id"] == "m1"
    assert "event_id" not in body
    assert body["content"] == "hi"
    assert "event_id" not in message_body(msg_type=0, msg_id="m1", msg_seq=1, content="hi")


def test_message_body_uses_event_id_without_msg_id():
    body = message_body(msg_type=0, msg_id="", msg_seq=1, event_id="e1", content="hi")
    assert body["event_id"] == "e1"
    assert "msg_id" not in body
