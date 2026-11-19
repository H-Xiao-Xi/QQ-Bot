from app.crypto import sign_hex, validation_signature


def test_health_and_dashboard(authed_client):
    health = authed_client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    home = authed_client.get("/")
    assert home.status_code == 200
    assert "RELAY" in home.text
    assert "机器人密钥" in home.text
    assert "签到数据" in home.text
    assert "保存" in home.text
    assert "打劫记录" in home.text
    assert "银行管理" in home.text
    assert "软妹币榜" in home.text
    status = authed_client.get("/api/status")
    assert status.status_code == 200
    assert "today_count" in status.json()["checkin"]
    assert "robs" in status.json()["checkin"]


def test_validation_requires_credentials(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", "")
    response = client.post(
        "/webhook",
        json={"op": 13, "d": {"plain_token": "t", "event_ts": "1"}},
    )
    assert response.status_code == 503

def test_url_validation(client, monkeypatch):
    secret = "DG5g3B4j9X2KOErG"
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "11111111")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", secret)
    body = {"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}}
    response = client.post("/webhook", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["plain_token"] == "Arq0D5A61EgUu4OxUvOp"
    assert data["signature"] == validation_signature(secret, "1725442341", "Arq0D5A61EgUu4OxUvOp")
    assert list(data.keys()) == ["plain_token", "signature"]


def test_url_validation_trailing_slash_and_string_op(client, monkeypatch):
    secret = "DG5g3B4j9X2KOErG"
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "11111111")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", secret)
    response = client.post(
        "/webhook/",
        json={"op": "13", "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}},
        headers={"User-Agent": "QQBot-Callback", "X-Bot-Appid": "11111111"},
    )
    assert response.status_code == 200
    assert response.json()["plain_token"] == "Arq0D5A61EgUu4OxUvOp"


def test_url_validation_numeric_event_ts(client, monkeypatch):
    secret = "DG5g3B4j9X2KOErG"
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "11111111")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", secret)
    response = client.post(
        "/webhook",
        json={"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": 1725442341}},
    )
    assert response.status_code == 200
    assert response.json()["signature"] == validation_signature(secret, "1725442341", "Arq0D5A61EgUu4OxUvOp")


def test_webhook_hint_includes_version(client):
    response = client.get("/webhook")
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "/webhook"
    assert "version" in body

def test_dispatch_ack_with_signature(client, monkeypatch):
    secret = "naOC0ocQE3shWLAfffVLB1rhYPG7"
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "11111111")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", secret)
    raw = b'{"id":"evt-1","op":0,"t":"GROUP_ADD_ROBOT","d":{"group_openid":"g1"}}'
    timestamp = "1725442341"
    signature = sign_hex(secret, timestamp.encode() + raw)
    response = client.post(
        "/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": timestamp,
            "X-Bot-Appid": "11111111",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"op": 12}


def test_web_save_credentials(authed_client, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.config.ENV_PATH", env_file)
    monkeypatch.setattr("app.main.settings.qq_bot_app_id", "")
    monkeypatch.setattr("app.main.settings.qq_bot_app_secret", "")
    missing = authed_client.post("/api/credentials", json={"app_id": "11111111", "app_secret": ""})
    assert missing.status_code == 400
    secret = "DG5g3B4j9X2KOErG"
    saved = authed_client.post("/api/credentials", json={"app_id": "11111111", "app_secret": secret})
    assert saved.status_code == 200
    body = saved.json()
    assert body["ok"] is True
    assert body["configured"] is True
    assert secret not in saved.text
    assert "QQ_BOT_APP_SECRET=" in env_file.read_text(encoding="utf-8")
    check = authed_client.post(
        "/webhook",
        json={"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}},
    )
    assert check.status_code == 200


def test_web_edit_checkin_requires_login(client):
    response = client.post("/api/checkin", json={"user_id": "u1", "points": 1})
    assert response.status_code == 401


def test_web_edit_checkin(authed_client, monkeypatch, tmp_path):
    from app.checkin import check_in, get_profile

    path = tmp_path / "checkins.json"
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", path)
    check_in("user-aaaa", path, nickname="小明")
    missing = authed_client.post("/api/checkin", json={"user_id": "nope", "points": 1})
    assert missing.status_code == 404
    empty = authed_client.post("/api/checkin", json={"user_id": "user-aaaa"})
    assert empty.status_code == 400
    updated = authed_client.post("/api/checkin", json={"user_id": "user-aaaa", "points": 88, "streak": 4})
    assert updated.status_code == 200
    body = updated.json()
    assert body["ok"] is True
    assert body["points"] == 88
    assert body["streak"] == 4
    profile = get_profile("user-aaaa", path)
    assert profile.points == 88
    assert profile.streak == 4
    banked = authed_client.post("/api/checkin", json={"user_id": "user-aaaa", "bank": 12})
    assert banked.status_code == 200
    assert banked.json()["bank"] == 12
    profile = get_profile("user-aaaa", path)
    assert profile.bank == 12
    assert profile.points == 88
