from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api_client import QQBotAPI, probe_access_token
from app.auth import (
    authenticate,
    ensure_admin,
    get_session_secret,
    load_admin,
    update_account,
)
from app.checkin import set_score, summarize_checkins
from app.config import apply_credentials, get_settings
from app.handlers import dispatch_event, notify_brick_jobs
from app.proxy import start_tcp_proxy
from app.store import store
from app.webhook import (
    OP_DISPATCH,
    OP_URL_VALIDATION,
    ack_response,
    handle_validation,
    header,
    opcode,
    parse_body,
    verify_dispatch,
)

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("qqbot")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
api_client: QQBotAPI | None = None


class CredentialIn(BaseModel):
    app_id: str = Field(min_length=1, max_length=64)
    app_secret: str = Field(default="", max_length=256)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AccountIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)


class CheckinEditIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    points: int | None = Field(default=None, ge=0, le=1_000_000)
    streak: int | None = Field(default=None, ge=0, le=100_000)
    bank: int | None = Field(default=None, ge=0, le=1_000_000)


async def _brick_loop() -> None:
    while True:
        await asyncio.sleep(2)
        client = api_client
        if client is None:
            continue
        try:
            await notify_brick_jobs(client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("brick notify failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global api_client
    ensure_admin()
    api_client = QQBotAPI(settings)
    logger.info("QQ bot webhook ready, path=%s configured=%s", settings.webhook_path, settings.configured)
    watcher = asyncio.create_task(_brick_loop())
    proxy_server = None
    if settings.proxy_port:
        target_host = "127.0.0.1" if settings.host in ("0.0.0.0", "::") else settings.host
        try:
            proxy_server = await start_tcp_proxy(
                settings.proxy_host,
                settings.proxy_port,
                target_host,
                settings.port,
            )
        except OSError:
            logger.exception("reverse proxy bind failed on %s:%s", settings.proxy_host, settings.proxy_port)
    try:
        yield
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        if proxy_server is not None:
            proxy_server.close()
            await proxy_server.wait_closed()
        await api_client.aclose()


app = FastAPI(
    title="QQ Official Bot",
    version=__version__,
    lifespan=lifespan,
    redirect_slashes=False,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


PUBLIC_PATHS = {"/login", "/api/login", "/health", "/logout", "/api/logout"}


def _is_public_path(path: str) -> bool:
    webhook = settings.webhook_path.rstrip("/") or "/webhook"
    if path.rstrip("/") == webhook:
        return True
    if path.startswith("/static/"):
        return True
    if path.startswith("/.well-known/"):
        return True
    return path in PUBLIC_PATHS


def _wants_html(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    if request.url.path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept or accept == ""


def _set_session(request: Request, username: str, must_change: bool) -> None:
    request.session["user"] = username
    request.session["must_change"] = bool(must_change)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    user = request.session.get("user")
    if not user:
        if _wants_html(request):
            return RedirectResponse("/login", status_code=302)
        return JSONResponse({"detail": "未登录"}, status_code=401)

    if request.session.get("must_change") or load_admin().get("must_change"):
        if path not in {"/account", "/api/account"}:
            if _wants_html(request):
                return RedirectResponse("/account", status_code=302)
            return JSONResponse({"detail": "请先修改初始账号和密码", "must_change": True}, status_code=403)

    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret(),
    session_cookie="relay_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    snapshot = store.snapshot()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "username": request.session.get("user", ""),
            "configured": settings.configured,
            "app_id": settings.masked_app_id,
            "app_id_value": settings.qq_bot_app_id,
            "secret_len": settings.secret_len,
            "secret_suffix": settings.secret_suffix,
            "webhook_path": settings.webhook_path,
            "api_base": settings.qq_bot_api_base,
            "version": __version__,
            "stats": snapshot["stats"],
            "events": snapshot["events"],
            "uptime_seconds": snapshot["uptime_seconds"],
            "checkin": summarize_checkins(),
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        if request.session.get("must_change"):
            return RedirectResponse("/account", status_code=302)
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "version": __version__,
        },
    )


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    admin = load_admin()
    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "version": __version__,
            "must_change": bool(request.session.get("must_change") or admin.get("must_change")),
            "username": request.session.get("user", ""),
        },
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.post("/api/login")
async def api_login(request: Request, body: LoginIn) -> dict:
    admin = authenticate(body.username.strip(), body.password)
    if admin is None:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    must_change = bool(admin.get("must_change"))
    _set_session(request, admin["username"], must_change)
    return {
        "ok": True,
        "must_change": must_change,
        "username": admin["username"],
        "redirect": "/account" if must_change else "/",
    }


@app.post("/api/logout")
async def api_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True, "redirect": "/login"}


@app.post("/api/account")
async def api_account(request: Request, body: AccountIn) -> dict:
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    try:
        updated = update_account(body.current_password, body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_session(request, updated["username"], False)
    return {"ok": True, "username": updated["username"], "redirect": "/"}


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "configured": settings.configured,
        "webhook_path": settings.webhook_path,
        "version": __version__,
    }


@app.get("/api/status")
async def status() -> dict:
    snapshot = store.snapshot()
    return {
        "configured": settings.configured,
        "app_id": settings.masked_app_id,
        "secret_configured": bool(settings.qq_bot_app_secret),
        "secret_len": settings.secret_len,
        "secret_suffix": settings.secret_suffix,
        "webhook_path": settings.webhook_path,
        "api_base": settings.qq_bot_api_base,
        "version": __version__,
        **snapshot,
        "checkin": summarize_checkins(),
    }


@app.post("/api/checkin")
async def edit_checkin(body: CheckinEditIn) -> dict:
    if body.points is None and body.streak is None and body.bank is None:
        raise HTTPException(status_code=400, detail="请填写软妹币、银行或连续天数")
    result = set_score(body.user_id.strip(), points=body.points, streak=body.streak, bank=body.bank)
    if result is None:
        raise HTTPException(status_code=404, detail="没有这个用户的签到记录")
    store.remember(
        "CHECKIN",
        f"网页修改 {result.nickname or body.user_id[:8]} 钱包 {result.points} / 银行 {result.bank} / 连续 {result.streak} 天",
    )
    return {
        "ok": True,
        "user_id": body.user_id.strip(),
        "nickname": result.nickname,
        "points": result.points,
        "streak": result.streak,
        "total": result.total,
        "bank": result.bank,
        "checkin": summarize_checkins(),
    }


@app.post("/api/credentials")
async def save_credentials(body: CredentialIn) -> dict:
    app_id = body.app_id.strip()
    app_secret = body.app_secret.strip()
    if any(ch in app_id or ch in app_secret for ch in "\r\n"):
        raise HTTPException(status_code=400, detail="凭证不能包含换行")
    if not app_secret and not settings.qq_bot_app_secret:
        raise HTTPException(status_code=400, detail="请填写 AppSecret")
    apply_credentials(settings, app_id, app_secret)
    await replace_api_client()
    store.remember("CREDENTIALS", "网页已更新机器人密钥")
    logger.info("bot credentials updated from web console, app_id=%s", settings.masked_app_id)
    return {
        "ok": True,
        "configured": settings.configured,
        "app_id": settings.masked_app_id,
        "secret_configured": bool(settings.qq_bot_app_secret),
        "secret_len": settings.secret_len,
        "secret_suffix": settings.secret_suffix,
    }


@app.post("/api/credentials/check")
async def check_credentials() -> dict:
    probe = await probe_access_token(settings)
    return {
        "ok": True,
        "configured": settings.configured,
        "app_id": settings.masked_app_id,
        "secret_len": settings.secret_len,
        "secret_suffix": settings.secret_suffix,
        **probe,
    }


def _webhook_paths() -> list[str]:
    path = settings.webhook_path.rstrip("/") or "/webhook"
    return [path, f"{path}/"]


async def webhook_hint() -> dict:
    return {
        "message": "QQ 开放平台应使用 POST 调用此回调地址",
        "path": settings.webhook_path,
        "configured": settings.configured,
        "version": __version__,
    }


async def webhook(request: Request, background_tasks: BackgroundTasks):
    raw = await request.body()
    payload = parse_body(raw)
    op = opcode(payload)
    logger.info(
        "webhook op=%s ua=%s has_sig=%s appid=%s",
        op,
        header(request, "User-Agent"),
        bool(header(request, "X-Signature-Ed25519")),
        header(request, "X-Bot-Appid"),
    )
    if op == OP_URL_VALIDATION:
        response = handle_validation(settings.qq_bot_app_secret, payload)
        store.bump("validated")
        store.remember("URL_VALIDATION", "回调地址校验成功")
        return response

    try:
        verify_dispatch(settings.qq_bot_app_secret, request, raw)
    except HTTPException:
        store.bump("errors")
        store.remember("SIGNATURE", "签名校验失败", ok=False)
        raise

    appid = header(request, "X-Bot-Appid")
    if appid and appid != settings.qq_bot_app_id:
        raise HTTPException(status_code=401, detail="appid mismatch")

    store.bump("received")
    if op == OP_DISPATCH:
        background_tasks.add_task(run_dispatch, payload)
    return ack_response()


for _webhook_path in _webhook_paths():
    app.add_api_route(_webhook_path, webhook_hint, methods=["GET", "HEAD"], include_in_schema=False)
    app.add_api_route(_webhook_path, webhook, methods=["POST"], include_in_schema=False)


async def run_dispatch(payload: dict) -> None:
    client = api_client
    if client is None:
        store.bump("errors")
        store.remember("DISPATCH", "API 客户端未就绪", ok=False)
        return
    await dispatch_event(client, payload)


async def replace_api_client() -> None:
    global api_client
    old = api_client
    api_client = QQBotAPI(settings)
    if old is not None:
        await old.aclose()
