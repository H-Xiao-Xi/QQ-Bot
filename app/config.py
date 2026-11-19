from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# QQ Open Platform webhook callbacks only accept these ports.
QQ_WEBHOOK_PORTS = (80, 443, 8080, 8443)
# 80/443 need root and TLS at the reverse proxy; the app binds these two.
QQ_APP_PORTS = (8080, 8443)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qq_bot_app_id: str = ""
    qq_bot_app_secret: str = ""
    qq_bot_webhook_path: str = "/webhook"
    qq_bot_api_base: str = "https://api.bot.qq.com"
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"

    @field_validator("qq_bot_app_id", "qq_bot_app_secret", "qq_bot_webhook_path", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.replace("\ufeff", "").replace("\r", "").strip()
        return value

    @property
    def configured(self) -> bool:
        return bool(self.qq_bot_app_id and self.qq_bot_app_secret)

    @property
    def listen_ports(self) -> list[int]:
        ports: list[int] = []
        preferred = self.port if self.port in QQ_APP_PORTS else QQ_APP_PORTS[0]
        for port in (preferred, *QQ_APP_PORTS):
            if port not in ports:
                ports.append(port)
        return ports

    @property
    def webhook_path(self) -> str:
        path = self.qq_bot_webhook_path.strip() or "/webhook"
        if not path.startswith("/"):
            path = f"/{path}"
        return path

    @property
    def masked_app_id(self) -> str:
        app_id = self.qq_bot_app_id.strip()
        if len(app_id) <= 6:
            return app_id or "(未配置)"
        return f"{app_id[:3]}****{app_id[-3:]}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _env_value(value: str) -> str:
    if any(ch in value for ch in [' ', '#', '"', "'", '=', "\t"]):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def upsert_env(updates: dict[str, str], path: Path | None = None) -> None:
    target = path or ENV_PATH
    lines: list[str] = []
    seen: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={_env_value(updates[key])}")
                    seen.add(key)
                    continue
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={_env_value(value)}")
    if lines and lines[-1] != "":
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")


def apply_credentials(settings: Settings, app_id: str, app_secret: str, path: Path | None = None) -> None:
    settings.qq_bot_app_id = app_id.strip()
    if app_secret.strip():
        settings.qq_bot_app_secret = app_secret.strip()
    upsert_env(
        {
            "QQ_BOT_APP_ID": settings.qq_bot_app_id,
            "QQ_BOT_APP_SECRET": settings.qq_bot_app_secret,
        },
        path=path,
    )
