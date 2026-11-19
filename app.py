from gunicorn.app.base import BaseApplication

from app.config import get_settings
from app.main import app


class StandaloneApplication(BaseApplication):
    def __init__(self, application, options):
        self.application = application
        self.options = options
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == "__main__":
    settings = get_settings()
    StandaloneApplication(
        app,
        {
            "bind": [f"{settings.host}:{port}" for port in settings.listen_ports],
            "workers": 1,
            "worker_class": "uvicorn.workers.UvicornWorker",
            "timeout": 30,
            "keepalive": 5,
            "accesslog": "-",
            "errorlog": "-",
            "graceful_timeout": 15,
        },
    ).run()
