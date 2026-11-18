from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.api_client import QQBotAPI
from app.checkin import (
    adjust_score,
    bank_transfer,
    check_in,
    format_adjust_card,
    claim_interest,
    format_bank_card,
    format_bank_status,
    format_checkin_card,
    format_query_card,
    format_rob_card,
    get_profile,
    rob,
    find_user_id_by_nickname,
    start_brick,
    claim_wage,
    due_brick_jobs,
    mark_brick_notified,
    format_work_card,
    WorkResult,
)
from app.store import store

logger = logging.getLogger(__name__)

AT_PATTERN = re.compile(r"<@!?[^>\s]+>")
MENTION_ID_PATTERN = re.compile(r"<@!?([^>\s]+)>")

@dataclass
class IncomingMessage:
    event: str
    scene: str
    content: str
    msg_id: str
    event_id: str
    author_id: str
    target_id: str
    raw: dict
    avatar: str = ""
    nickname: str = ""
    mention_ids: list[str] = field(default_factory=list)


@dataclass
class Reply:
    text: str
    markdown: str | None = None


HELP_TEXT = (
    "可用指令：\n"
    "help  查看帮助\n"
    "签到  每日签到，前 3 名和连续天数额外加软妹币\n"
    "搬砖  开始搬砖，2~5 分钟后提醒领工资，不限次数\n"
    "领工资  领取搬砖工资，随机 10~25 软妹币\n"
    "查询  查看软妹币、连续天数和排名\n"
    "加软妹币 数量  增加钱包，省略数量为 1\n"
    "减软妹币 数量  减少钱包，最少到 0\n"
    "加天数 数量  增加连续天数\n"
    "减天数 数量  减少连续天数，最少到 0\n"
    "打劫@某人  每天一次，成功率 60%；不指定则随机\n"
    "存款 数量  钱包转入银行，省略则全部存入，银行里的不会被抢\n"
    "取款 数量  银行转入钱包，省略则全部取出\n"
    "银行  查看钱包和银行\n"
    "利息  银行存款每日领取 5% 利息\n"
    "前面加 / 也可以"
)

HELP_MARKDOWN = (
    "# RELAY 指令\n"
    "- `help` 查看帮助\n"
    "- `签到` 每日签到，前 3 名和连续天数额外加软妹币\n"
    "- `搬砖` 开始搬砖，2~5 分钟后提醒领工资，不限次数\n"
    "- `领工资` 领取搬砖工资，随机 10~25 软妹币\n"
    "- `查询` 查看软妹币、连续天数和排名\n"
    "- `加软妹币 数量` 增加钱包\n"
    "- `减软妹币 数量` 减少钱包\n"
    "- `加天数 数量` 增加连续天数\n"
    "- `减天数 数量` 减少连续天数\n"
    "- `打劫@某人` 每天一次，不指定则随机\n"
    "- `存款 数量` 存入银行，省略则全部存入\n"
    "- `取款 数量` 从银行取出，省略则全部取出\n"
    "- `银行` 查看钱包和银行\n"
    "- `利息` 银行存款每日领取 5% 利息\n"
    "前面加 `/` 也可以"
)


HELP_ALIASES = {"help", "帮助"}
CHECKIN_ALIASES = {"签到", "checkin", "qd"}
QUERY_ALIASES = {"查询", "query", "积分", "jf", "软妹币"}
POINT_ADD_ALIASES = {"加积分", "加分", "加软妹币", "加币"}
POINT_SUB_ALIASES = {"减积分", "扣积分", "减分", "减软妹币", "减币"}
DAY_ADD_ALIASES = {"加天数", "加天"}
DAY_SUB_ALIASES = {"减天数", "减天"}
ADJUST_ALIASES = POINT_ADD_ALIASES | POINT_SUB_ALIASES | DAY_ADD_ALIASES | DAY_SUB_ALIASES
ROB_ALIASES = {"打劫", "抢劫", "rob"}
DEPOSIT_ALIASES = {"存款", "存钱", "deposit"}
WITHDRAW_ALIASES = {"取款", "取钱", "withdraw"}
BANK_ALIASES = {"银行", "bank"}
INTEREST_ALIASES = {"利息", "领利息", "领取利息", "interest"}
WORK_ALIASES = {"搬砖", "打工", "工作", "work"}
WAGE_ALIASES = {"领工资", "领取工资", "领钱"}
KNOWN_COMMANDS = (
    HELP_ALIASES
    | CHECKIN_ALIASES
    | QUERY_ALIASES
    | ADJUST_ALIASES
    | ROB_ALIASES
    | DEPOSIT_ALIASES
    | WITHDRAW_ALIASES
    | BANK_ALIASES
    | INTEREST_ALIASES
    | WORK_ALIASES
    | WAGE_ALIASES
)
MAX_ADJUST = 10000


def as_card(title: str, body: str = "") -> Reply:
    text = f"{title}\n{body}".strip()
    markdown = f"# {title}\n{body}".strip() if body else f"# {title}"
    return Reply(text=text, markdown=markdown)


def normalize_content(content: str) -> str:
    cleaned = AT_PATTERN.sub("", content or "")
    cleaned = " ".join(cleaned.split()).strip()
    return re.sub(r"(打劫|抢劫|rob)\s+@", r"\1@", cleaned, flags=re.IGNORECASE)


def mention_name(arg: str) -> str:
    text = (arg or "").strip()
    if text.startswith("@"):
        text = text[1:].strip()
    return text


def extract_mention_ids(event: str, data: dict, author_id: str) -> list[str]:
    ids = MENTION_ID_PATTERN.findall(str(data.get("content") or ""))
    extra = data.get("mentions") or []
    for item in extra:
        if isinstance(item, dict):
            mid = str(item.get("id") or item.get("member_openid") or item.get("user_openid") or "")
        else:
            mid = str(item)
        if mid:
            ids.append(mid)
    if event in {"GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE"} and ids:
        ids = ids[1:]
    unique: list[str] = []
    for mid in ids:
        if mid and mid != author_id and mid not in unique:
            unique.append(mid)
    return unique


def _author_avatar(author: dict) -> str:
    value = str(author.get("avatar") or author.get("avatar_url") or "").strip()
    if value.startswith("http://"):
        value = "https://" + value[7:]
    if not value.startswith("https://"):
        return ""
    if any(ch in value for ch in " \r\n)"):
        return ""
    return value


def _author_name(author: dict) -> str:
    return str(author.get("member_nickname") or author.get("username") or author.get("nick") or "").strip()


def parse_incoming(event: str, data: dict, event_id: str) -> IncomingMessage | None:
    content = normalize_content(str(data.get("content") or ""))
    msg_id = str(data.get("id") or "")
    author = data.get("author") or {}
    avatar = _author_avatar(author)
    nickname = _author_name(author)
    if event in {"GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"}:
        return IncomingMessage(
            event=event,
            scene="group",
            content=content,
            msg_id=msg_id,
            event_id=event_id,
            author_id=str(author.get("id") or author.get("member_openid") or ""),
            target_id=str(data.get("group_openid") or data.get("group_id") or ""),
            raw=data,
            avatar=avatar,
            nickname=nickname,
            mention_ids=extract_mention_ids(event, data, str(author.get("id") or author.get("member_openid") or "")),
        )
    if event == "C2C_MESSAGE_CREATE":
        return IncomingMessage(
            event=event,
            scene="c2c",
            content=content,
            msg_id=msg_id,
            event_id=event_id,
            author_id=str(author.get("user_openid") or author.get("id") or ""),
            target_id=str(author.get("user_openid") or author.get("id") or ""),
            raw=data,
            avatar=avatar,
            nickname=nickname,
            mention_ids=extract_mention_ids(event, data, str(author.get("user_openid") or author.get("id") or "")),
        )
    if event in {"AT_MESSAGE_CREATE", "MESSAGE_CREATE"}:
        return IncomingMessage(
            event=event,
            scene="channel",
            content=content,
            msg_id=msg_id,
            event_id=event_id,
            author_id=str(author.get("id") or ""),
            target_id=str(data.get("channel_id") or ""),
            raw=data,
            avatar=avatar,
            nickname=nickname,
            mention_ids=extract_mention_ids(event, data, str(author.get("id") or "")),
        )
    return None


def command_name(content: str) -> tuple[str, str]:
    if not content:
        return "", ""
    text = content[1:] if content.startswith("/") else content
    at = text.find("@")
    if at > 0 and " " not in text[:at]:
        return text[:at].lower(), text[at:]
    parts = text.split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    return name, arg


def parse_amount(arg: str) -> int | None:
    token = (arg or "1").split(maxsplit=1)[0]
    if token.startswith("+") or token.startswith("-"):
        token = token[1:]
    if not token.isdigit():
        return None
    value = int(token)
    if value < 1 or value > MAX_ADJUST:
        return None
    return value


def parse_bank_amount(arg: str) -> int | None:
    parts = (arg or "").split(maxsplit=1)
    if not parts:
        return 0
    token = parts[0]
    if not token:
        return 0
    if token.startswith("+") or token.startswith("-"):
        token = token[1:]
    if not token.isdigit():
        return None
    value = int(token)
    if value < 1 or value > MAX_ADJUST:
        return None
    return value


def reply_for_message(message: IncomingMessage) -> Reply | None:
    author = message.raw.get("author") or {}
    if author.get("bot"):
        return None
    name, arg = command_name(message.content)
    if message.event == "GROUP_MESSAGE_CREATE":
        if name not in KNOWN_COMMANDS:
            return None
    if name in HELP_ALIASES:
        return Reply(text=HELP_TEXT, markdown=HELP_MARKDOWN)
    if name in CHECKIN_ALIASES:
        if not message.author_id:
            return as_card("签到失败", "无法识别用户")
        text, markdown = format_checkin_card(
            check_in(message.author_id, nickname=message.nickname),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in WORK_ALIASES:
        if not message.author_id:
            return as_card("搬砖失败", "无法识别用户")
        text, markdown = format_work_card(
            start_brick(
                message.author_id,
                nickname=message.nickname,
                scene=message.scene,
                target_id=message.target_id,
                msg_id=message.msg_id,
            ),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in WAGE_ALIASES:
        if not message.author_id:
            return as_card("领取失败", "无法识别用户")
        text, markdown = format_work_card(
            claim_wage(message.author_id, nickname=message.nickname),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in QUERY_ALIASES:
        if not message.author_id:
            return as_card("查询失败", "无法识别用户")
        text, markdown = format_query_card(
            get_profile(message.author_id),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in ADJUST_ALIASES:
        if not message.author_id:
            return as_card("调整失败", "无法识别用户")
        amount = parse_amount(arg)
        if amount is None:
            return as_card("调整失败", f"数量必须是 1 到 {MAX_ADJUST} 的整数")
        points_delta = 0
        days_delta = 0
        if name in POINT_ADD_ALIASES:
            points_delta = amount
        elif name in POINT_SUB_ALIASES:
            points_delta = -amount
        elif name in DAY_ADD_ALIASES:
            days_delta = amount
        else:
            days_delta = -amount
        text, markdown = format_adjust_card(
            adjust_score(
                message.author_id,
                points_delta=points_delta,
                days_delta=days_delta,
                nickname=message.nickname,
            ),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in ROB_ALIASES:
        if not message.author_id:
            return as_card("打劫失败", "无法识别用户")
        victim_id = message.mention_ids[0] if message.mention_ids else ""
        if not victim_id:
            looked = mention_name(arg)
            if looked:
                victim_id = find_user_id_by_nickname(looked, exclude=message.author_id) or "_"
        text, markdown = format_rob_card(
            rob(
                message.author_id,
                victim_id=victim_id,
                nickname=message.nickname,
            ),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in DEPOSIT_ALIASES or name in WITHDRAW_ALIASES:
        if not message.author_id:
            return as_card("银行失败", "无法识别用户")
        amount = parse_bank_amount(arg)
        if amount is None:
            return as_card("银行失败", f"数量必须是 1 到 {MAX_ADJUST} 的整数，省略则全部")
        action = "deposit" if name in DEPOSIT_ALIASES else "withdraw"
        text, markdown = format_bank_card(
            bank_transfer(message.author_id, action, amount, nickname=message.nickname),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in BANK_ALIASES:
        if not message.author_id:
            return as_card("银行失败", "无法识别用户")
        text, markdown = format_bank_status(
            get_profile(message.author_id),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if name in INTEREST_ALIASES:
        if not message.author_id:
            return as_card("领取失败", "无法识别用户")
        text, markdown = format_bank_card(
            claim_interest(message.author_id, nickname=message.nickname),
            avatar=message.avatar,
            nickname=message.nickname,
        )
        return Reply(text=text, markdown=markdown)
    if message.event == "GROUP_MESSAGE_CREATE":
        return None
    if message.content:
        return as_card("收到", message.content)
    return as_card("在的", "发送 help 查看指令")


async def send_reply(api: QQBotAPI, message: IncomingMessage, reply: Reply, msg_seq: int = 1) -> None:
    text = reply.text[:1800]
    markdown = (reply.markdown or "")[:1800]
    if message.scene in {"group", "c2c"} and markdown:
        try:
            if message.scene == "group":
                await api.send_group_markdown(message.target_id, markdown, message.msg_id, msg_seq=msg_seq)
            else:
                await api.send_c2c_markdown(message.target_id, markdown, message.msg_id, msg_seq=msg_seq)
            return
        except Exception:
            logger.warning("markdown card failed, fallback to text", exc_info=True)
    if message.scene == "group":
        await api.send_group_text(message.target_id, text, message.msg_id, msg_seq=msg_seq)
        return
    if message.scene == "c2c":
        await api.send_c2c_text(message.target_id, text, message.msg_id, msg_seq=msg_seq)
        return
    await api.send_channel_text(message.target_id, text, message.msg_id)


async def notify_brick_jobs(api: QQBotAPI) -> None:
    for job in due_brick_jobs():
        text, markdown = format_work_card(WorkResult(status="ready", nickname=job.nickname))
        message = IncomingMessage(
            event="GROUP_MESSAGE_CREATE" if job.scene == "group" else "C2C_MESSAGE_CREATE",
            scene=job.scene,
            content="",
            msg_id=job.msg_id,
            event_id="",
            author_id=job.user_id,
            target_id=job.target_id,
            raw={},
            nickname=job.nickname,
        )
        try:
            await send_reply(api, message, Reply(text=text, markdown=markdown), msg_seq=2)
        except Exception:
            logger.exception("brick remind failed for %s", job.user_id)
        mark_brick_notified(job.user_id)


async def dispatch_event(api: QQBotAPI, payload: dict) -> None:
    event = str(payload.get("t") or "")
    event_id = str(payload.get("id") or "")
    data = payload.get("d") or {}
    message_id = str(data.get("id") or "")
    if store.seen_before(message_id or event_id or f"{event}:unknown"):
        store.bump("ignored")
        store.remember(event or "DUP", "重复事件已忽略")
        return

    if event in {"GROUP_ADD_ROBOT", "FRIEND_ADD"}:
        store.remember(event, "机器人被添加")
        return
    if event in {"GROUP_DEL_ROBOT", "FRIEND_DEL"}:
        store.remember(event, "机器人被移除")
        return

    message = parse_incoming(event, data, event_id)
    if message is None:
        store.bump("ignored")
        store.remember(event or "UNKNOWN", "未处理的事件类型")
        return
    if not message.msg_id or not message.target_id:
        store.bump("ignored")
        store.remember(event, "缺少回复目标，已跳过", ok=False)
        return

    reply = reply_for_message(message)
    if not reply:
        store.bump("ignored")
        return
    try:
        await send_reply(api, message, reply)
        store.bump("replied")
        store.remember(event, f"{message.scene} 回复：{reply.text[:80]}")
    except Exception:
        logger.exception("failed to reply %s", event)
        store.bump("errors")
        store.remember(event, "回复失败", ok=False)
