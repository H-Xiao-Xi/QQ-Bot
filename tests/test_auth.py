def test_health_and_login_page_are_public(client):
    health = client.get("/health")
    assert health.status_code == 200
    login = client.get("/login")
    assert login.status_code == 200
    assert "RELAY" in login.text
    assert "初始账号" not in login.text
    assert "初始密码" not in login.text
    assert "admin" not in login.text


def test_dashboard_redirects_to_login(client):
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 302
    assert home.headers["location"].endswith("/login")


def test_console_api_requires_login(client):
    status = client.get("/api/status")
    assert status.status_code == 401
    saved = client.post("/api/credentials", json={"app_id": "11111111", "app_secret": "DG5g3B4j9X2KOErG"})
    assert saved.status_code == 401


def test_login_rejects_wrong_password(client):
    response = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_first_login_must_change_account(client):
    logged = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert logged.status_code == 200
    body = logged.json()
    assert body["must_change"] is True
    assert body["redirect"] == "/account"

    blocked = client.get("/", follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["location"].endswith("/account")

    forbidden = client.get("/api/status")
    assert forbidden.status_code == 403

    keep_user = client.post(
        "/api/account",
        json={
            "current_password": "admin",
            "username": "admin",
            "password": "change-me-now",
            "confirm_password": "change-me-now",
        },
    )
    assert keep_user.status_code == 400

    changed = client.post(
        "/api/account",
        json={
            "current_password": "admin",
            "username": "keeper",
            "password": "change-me-now",
            "confirm_password": "change-me-now",
        },
    )
    assert changed.status_code == 200
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    assert "机器人密钥" in home.text


def test_logout_clears_session(authed_client):
    bye = authed_client.get("/logout", follow_redirects=False)
    assert bye.status_code == 302
    home = authed_client.get("/", follow_redirects=False)
    assert home.status_code == 302
    assert home.headers["location"].endswith("/login")
