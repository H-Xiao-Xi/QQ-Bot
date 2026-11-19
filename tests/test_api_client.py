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


def test_message_body_includes_event_id():
    body = message_body(msg_type=0, msg_id="m1", msg_seq=1, event_id="e1", content="hi")
    assert body["event_id"] == "e1"
    assert body["content"] == "hi"
    assert "event_id" not in message_body(msg_type=0, msg_id="m1", msg_seq=1, content="hi")
