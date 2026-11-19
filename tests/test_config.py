from app.config import QQ_APP_PORTS, QQ_WEBHOOK_PORTS, Settings


def test_listen_ports_match_qq_app_ports():
    settings = Settings(port=8080)
    assert settings.listen_ports == [8080, 8443]
    assert tuple(settings.listen_ports) == QQ_APP_PORTS
    assert set(settings.listen_ports) <= set(QQ_WEBHOOK_PORTS)


def test_listen_ports_ignore_non_qq_port():
    settings = Settings(port=8888)
    assert 8888 not in settings.listen_ports
    assert settings.listen_ports == [8080, 8443]
