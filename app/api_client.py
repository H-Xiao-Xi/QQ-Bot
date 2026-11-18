from __future__ import annotations

import logging
from time import monotonic
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class QQBotAPI:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token = ""
        self._token_expire_at = 0.0
        self._client = httpx.AsyncClient(timeout=15.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_token(self) -> str:
        if self._token and monotonic() < self._token_expire_at:
            return self._token
        url = f"{self._settings.qq_bot_api_base.rstrip('/')}/app/getAppAccessToken"
        response = await self._client.post(
            url,
            json={
                "appId": self._settings.qq_bot_app_id,
                "clientSecret": self._settings.qq_bot_app_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        if "code" in data and not data.get("access_token"):
            raise RuntimeError(f"getAppAccessToken failed: {data}")
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"getAppAccessToken missing token: {data}")
        expires_in = int(data.get("expires_in") or 7200)
        self._token = token
        self._token_expire_at = monotonic() + max(expires_in - 60, 60)
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "X-Union-Appid": self._settings.qq_bot_app_id,
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._settings.qq_bot_api_base.rstrip('/')}{path}"
        response = await self._client.post(url, headers=await self._headers(), json=payload)
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            logger.error("OpenAPI %s failed: %s %s", path, response.status_code, data)
            raise RuntimeError(f"OpenAPI {path} failed: {response.status_code} {data}")
        return data

    async def send_group_text(self, group_openid: str, content: str, msg_id: str, msg_seq: int = 1) -> dict[str, Any]:
        return await self._post(
            f"/v2/groups/{group_openid}/messages",
            {"content": content, "msg_type": 0, "msg_id": msg_id, "msg_seq": msg_seq},
        )

    async def send_c2c_text(self, user_openid: str, content: str, msg_id: str, msg_seq: int = 1) -> dict[str, Any]:
        return await self._post(
            f"/v2/users/{user_openid}/messages",
            {"content": content, "msg_type": 0, "msg_id": msg_id, "msg_seq": msg_seq},
        )

    async def send_channel_text(self, channel_id: str, content: str, msg_id: str) -> dict[str, Any]:
        return await self._post(
            f"/channels/{channel_id}/messages",
            {"content": content, "msg_id": msg_id},
        )

    async def send_group_markdown(self, group_openid: str, content: str, msg_id: str, msg_seq: int = 1) -> dict[str, Any]:
        return await self._post(
            f"/v2/groups/{group_openid}/messages",
            {"msg_type": 2, "markdown": {"content": content}, "msg_id": msg_id, "msg_seq": msg_seq},
        )

    async def send_c2c_markdown(self, user_openid: str, content: str, msg_id: str, msg_seq: int = 1) -> dict[str, Any]:
        return await self._post(
            f"/v2/users/{user_openid}/messages",
            {"msg_type": 2, "markdown": {"content": content}, "msg_id": msg_id, "msg_seq": msg_seq},
        )
