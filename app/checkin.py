from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from app.config import ROOT_DIR

TZ = ZoneInfo("Asia/Shanghai")
CHECKIN_PATH = ROOT_DIR / "data" / "checkins.json"
_lock = Lock()
DAILY_KEY = "_daily"
ROB_KEY = "_robs"
BANK_KEY = "_bank"
META_KEYS = {DAILY_KEY, ROB_KEY, BANK_KEY}
BASE_POINTS = 10
RANK_BONUS = {1: 20, 2: 10, 3: 5}
ROB_SUCCESS_RATE = 0.6
ROB_STEAL_CAP = 50
ROB_FAIL_CAP = 20
INTEREST_RATE = 0.05
STREAK_BONUS_CAP = 20
WORK_MIN = 10
WORK_MAX = 25
BRICK_MIN_SECS = 120
BRICK_MAX_SECS = 300


@dataclass
class CheckinResult:
    already: bool
    total: int
    streak: int
    day: str
    points: int = 0
    gained: int = 0
    rank: int = 0
    bonus: int = 0
    streak_bonus: int = 0


@dataclass
class UserProfile:
    found: bool
    total: int = 0
    streak: int = 0
    points: int = 0
    last_date: str = ""
    rank: int = 0
    points_rank: int = 0
    nickname: str = ""
    bank: int = 0
    last_interest: str = ""


@dataclass
class AdjustResult:
    points: int
    streak: int
    total: int
    points_delta: int
    days_delta: int
    nickname: str = ""
    bank: int = 0
    bank_delta: int = 0


@dataclass
class RobResult:
    status: str
    success: bool = False
    stolen: int = 0
    lost: int = 0
    attacker_points: int = 0
    victim_points: int = 0
    attacker_name: str = ""
    victim_name: str = ""
    victim_bank: int = 0


@dataclass
class BankResult:
    status: str
    action: str
    amount: int = 0
    points: int = 0
    bank: int = 0
    nickname: str = ""


@dataclass
class WorkResult:
    status: str
    seconds: int = 0
    gained: int = 0
    points: int = 0
    nickname: str = ""


@dataclass
class BrickJob:
    user_id: str
    scene: str
    target_id: str
    msg_id: str
    nickname: str = ""


def today() -> date:
    return _now().date()


def _now() -> datetime:
    return datetime.now(TZ)


def interest_of(bank: int) -> int:
    if bank <= 0:
        return 0
    return max(1, int(bank * INTEREST_RATE))


def streak_bonus_of(streak: int) -> int:
    return min(max(int(streak) - 1, 0), STREAK_BONUS_CAP)


def format_duration(seconds: int) -> str:
    secs = max(0, int(seconds))
    minutes, rest = divmod(secs, 60)
    if minutes and rest:
        return f"{minutes} 分 {rest} 秒"
    if minutes:
        return f"{minutes} 分钟"
    return f"{rest} 秒"


def _brick_state(record: dict, now: datetime | None = None) -> tuple[str, int]:
    start = record.get("work_start")
    secs = int(record.get("work_secs") or 0)
    if start in (None, "") or secs <= 0:
        return "idle", 0
    current = now or _now()
    remain = int(float(start) + secs - current.timestamp())
    if remain > 0:
        return "busy", remain
    return "ready", 0


def _clear_brick(record: dict) -> None:
    for key in ("work_start", "work_secs", "work_scene", "work_target", "work_msg_id", "work_notified"):
        record.pop(key, None)


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _daily_map(data: dict) -> dict:
    raw = data.get(DAILY_KEY) or {}
    return raw if isinstance(raw, dict) else {}


def _prune_daily(daily: dict, day_text: str) -> dict:
    keep_from = (date.fromisoformat(day_text) - timedelta(days=7)).isoformat()
    cleaned: dict = {}
    for key, value in daily.items():
        if isinstance(key, str) and key >= keep_from:
            cleaned[key] = value
    return cleaned


def _rank_of(order: list, user_id: str) -> int:
    try:
        return order.index(user_id) + 1
    except ValueError:
        return 0


def _now_stamp() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _as_user(record) -> dict:
    return dict(record) if isinstance(record, dict) else {}


def check_in(user_id: str, path: Path | None = None, nickname: str = "") -> CheckinResult:
    target = path or CHECKIN_PATH
    day = today()
    day_text = day.isoformat()
    with _lock:
        data = _load(target)
        record = data.get(user_id) or {}
        last_text = str(record.get("last_date") or "")
        total = int(record.get("total") or 0)
        streak = int(record.get("streak") or 0)
        points = int(record.get("points") or 0)
        name = (nickname or record.get("nickname") or "").strip()
        daily = _prune_daily(_daily_map(data), day_text)
        order = [item for item in (daily.get(day_text) or []) if isinstance(item, str)]
        if last_text == day_text:
            if name and name != record.get("nickname"):
                data[user_id] = {**record, "nickname": name}
                _save(data, target)
            return CheckinResult(
                already=True,
                total=total,
                streak=streak,
                day=day_text,
                points=points,
                rank=_rank_of(order, user_id),
            )
        try:
            last_day = date.fromisoformat(last_text) if last_text else None
        except ValueError:
            last_day = None
        if last_day == day - timedelta(days=1):
            streak += 1
        else:
            streak = 1
        total += 1
        order.append(user_id)
        rank = len(order)
        bonus = RANK_BONUS.get(rank, 0)
        extra = streak_bonus_of(streak)
        gained = BASE_POINTS + bonus + extra
        points += gained
        daily[day_text] = order
        data[DAILY_KEY] = daily
        data[user_id] = {
            **_as_user(record),
            "last_date": day_text,
            "total": total,
            "streak": streak,
            "points": points,
            "bank": int(record.get("bank") or 0),
            "nickname": name,
        }
        _save(data, target)
        return CheckinResult(
            already=False,
            total=total,
            streak=streak,
            day=day_text,
            points=points,
            gained=gained,
            rank=rank,
            bonus=bonus,
            streak_bonus=extra,
        )


def get_profile(user_id: str, path: Path | None = None) -> UserProfile:
    target = path or CHECKIN_PATH
    day_text = today().isoformat()
    with _lock:
        data = _load(target)
        record = data.get(user_id)
        if not isinstance(record, dict):
            return UserProfile(found=False)
        daily = _daily_map(data)
        order = [item for item in (daily.get(day_text) or []) if isinstance(item, str)]
        ranked = []
        for uid, rec in data.items():
            if uid in META_KEYS or not isinstance(rec, dict):
                continue
            ranked.append(
                (
                    uid,
                    int(rec.get("points") or 0) + int(rec.get("bank") or 0),
                    int(rec.get("total") or 0),
                    str(rec.get("nickname") or uid),
                )
            )
        ranked.sort(key=lambda item: (-item[1], -item[2], item[3]))
        points_rank = next((index for index, item in enumerate(ranked, 1) if item[0] == user_id), 0)
        return UserProfile(
            found=True,
            total=int(record.get("total") or 0),
            streak=int(record.get("streak") or 0),
            points=int(record.get("points") or 0),
            last_date=str(record.get("last_date") or ""),
            rank=_rank_of(order, user_id),
            points_rank=points_rank,
            nickname=str(record.get("nickname") or "").strip(),
            bank=int(record.get("bank") or 0),
            last_interest=str(record.get("last_interest") or ""),
        )


def adjust_score(
    user_id: str,
    points_delta: int = 0,
    days_delta: int = 0,
    path: Path | None = None,
    nickname: str = "",
) -> AdjustResult:
    target = path or CHECKIN_PATH
    with _lock:
        data = _load(target)
        record = data.get(user_id) if isinstance(data.get(user_id), dict) else {}
        points = int(record.get("points") or 0)
        streak = int(record.get("streak") or 0)
        total = int(record.get("total") or 0)
        name = (nickname or record.get("nickname") or "").strip()
        new_points = max(0, points + int(points_delta))
        new_streak = max(0, streak + int(days_delta))
        data[user_id] = {
            **_as_user(record),
            "last_date": str(record.get("last_date") or ""),
            "total": total,
            "streak": new_streak,
            "points": new_points,
            "bank": int(record.get("bank") or 0),
            "nickname": name,
        }
        _save(data, target)
        return AdjustResult(
            points=new_points,
            streak=new_streak,
            total=total,
            points_delta=new_points - points,
            days_delta=new_streak - streak,
            nickname=name,
            bank=int(record.get("bank") or 0),
        )


def set_score(
    user_id: str,
    points: int | None = None,
    streak: int | None = None,
    bank: int | None = None,
    path: Path | None = None,
) -> AdjustResult | None:
    if points is None and streak is None and bank is None:
        return None
    target = path or CHECKIN_PATH
    with _lock:
        data = _load(target)
        record = data.get(user_id)
        if not isinstance(record, dict):
            return None
        old_points = int(record.get("points") or 0)
        old_streak = int(record.get("streak") or 0)
        new_points = old_points if points is None else max(0, int(points))
        new_streak = old_streak if streak is None else max(0, int(streak))
        old_bank = int(record.get("bank") or 0)
        new_bank = old_bank if bank is None else max(0, int(bank))
        data[user_id] = {**record, "points": new_points, "streak": new_streak, "bank": new_bank}
        if new_bank != old_bank:
            logs = _bank_log(data)
            logs.append(
                {
                    "time": _now_stamp(),
                    "day": today().isoformat(),
                    "user": _label(user_id, data[user_id]),
                    "action": "set",
                    "amount": new_bank - old_bank,
                    "points": new_points,
                    "bank": new_bank,
                }
            )
            data[BANK_KEY] = logs[-100:]
        _save(data, target)
        return AdjustResult(
            points=new_points,
            streak=new_streak,
            total=int(record.get("total") or 0),
            points_delta=new_points - old_points,
            days_delta=new_streak - old_streak,
            nickname=str(record.get("nickname") or "").strip(),
            bank=new_bank,
            bank_delta=new_bank - old_bank,
        )


def _rob_candidates(data: dict, attacker_id: str) -> list[str]:
    found = []
    for user_id, record in data.items():
        if user_id in META_KEYS or user_id == attacker_id or not isinstance(record, dict):
            continue
        if int(record.get("points") or 0) > 0:
            found.append(user_id)
    return found


def find_user_id_by_nickname(name: str, path: Path | None = None, exclude: str = "") -> str:
    key = (name or "").strip()
    if not key:
        return ""
    target = path or CHECKIN_PATH
    with _lock:
        data = _load(target)
        for user_id, record in data.items():
            if user_id in META_KEYS or user_id == exclude or not isinstance(record, dict):
                continue
            if str(record.get("nickname") or "").strip() == key:
                return user_id
        return ""


def _ensure_user(data: dict, user_id: str, nickname: str = "") -> dict:
    record = data.get(user_id)
    if not isinstance(record, dict):
        record = {
            "last_date": "",
            "total": 0,
            "streak": 0,
            "points": 0,
            "bank": 0,
            "nickname": nickname,
        }
        data[user_id] = record
    elif nickname and not str(record.get("nickname") or "").strip():
        record["nickname"] = nickname
    return record


def rob(
    attacker_id: str,
    victim_id: str = "",
    path: Path | None = None,
    nickname: str = "",
    rng: random.Random | None = None,
) -> RobResult:
    dice = rng or random.Random()
    target = path or CHECKIN_PATH
    day_text = today().isoformat()
    with _lock:
        data = _load(target)
        attacker = _ensure_user(data, attacker_id, nickname)
        attacker_name = (nickname or attacker.get("nickname") or "").strip()
        attacker_points = int(attacker.get("points") or 0)
        if str(attacker.get("last_rob") or "") == day_text:
            return RobResult(
                status="cooldown",
                attacker_points=attacker_points,
                attacker_name=attacker_name,
            )
        if victim_id == attacker_id:
            return RobResult(status="self", attacker_points=attacker_points, attacker_name=attacker_name)
        if not victim_id:
            options = _rob_candidates(data, attacker_id)
            if not options:
                return RobResult(status="no_target", attacker_points=attacker_points, attacker_name=attacker_name)
            victim_id = dice.choice(options)
        victim = data.get(victim_id)
        if not isinstance(victim, dict) or int(victim.get("points") or 0) <= 0:
            victim_rec = victim if isinstance(victim, dict) else {}
            return RobResult(
                status="empty",
                attacker_points=attacker_points,
                attacker_name=attacker_name,
                victim_name=str(victim_rec.get("nickname") or "").strip(),
                victim_bank=int(victim_rec.get("bank") or 0),
            )
        victim_name = str(victim.get("nickname") or "").strip()
        victim_points = int(victim.get("points") or 0)
        success = dice.random() < ROB_SUCCESS_RATE
        stolen = 0
        lost = 0
        if success:
            ratio = dice.uniform(0.1, 0.3)
            stolen = min(ROB_STEAL_CAP, victim_points, max(1, int(victim_points * ratio)))
            attacker_points += stolen
            victim_points -= stolen
        elif attacker_points:
            lost = min(ROB_FAIL_CAP, attacker_points, max(1, int(attacker_points * 0.1) or 1))
            attacker_points -= lost
        attacker["points"] = attacker_points
        attacker["nickname"] = attacker_name or attacker.get("nickname") or ""
        attacker["last_rob"] = day_text
        victim["points"] = victim_points
        data[attacker_id] = attacker
        data[victim_id] = victim
        logs = _rob_log(data)
        logs.append(
            {
                "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "day": day_text,
                "success": success,
                "attacker": attacker_name or attacker_id[:8],
                "victim": victim_name or victim_id[:8],
                "stolen": stolen,
                "lost": lost,
            }
        )
        data[ROB_KEY] = logs[-100:]
        _save(data, target)
        return RobResult(
            status="ok",
            success=success,
            stolen=stolen,
            lost=lost,
            attacker_points=attacker_points,
            victim_points=victim_points,
            attacker_name=attacker_name,
            victim_name=victim_name,
        )


def bank_transfer(
    user_id: str,
    action: str,
    amount: int = 0,
    path: Path | None = None,
    nickname: str = "",
) -> BankResult:
    target = path or CHECKIN_PATH
    with _lock:
        data = _load(target)
        record = _ensure_user(data, user_id, nickname)
        name = (nickname or record.get("nickname") or "").strip()
        points = int(record.get("points") or 0)
        bank = int(record.get("bank") or 0)
        if action == "deposit":
            if points <= 0:
                return BankResult(status="empty", action=action, points=points, bank=bank, nickname=name)
            moved = points if amount <= 0 else min(int(amount), points)
            points -= moved
            bank += moved
        else:
            if bank <= 0:
                return BankResult(status="empty", action=action, points=points, bank=bank, nickname=name)
            moved = bank if amount <= 0 else min(int(amount), bank)
            bank -= moved
            points += moved
        record["points"] = points
        record["bank"] = bank
        record["nickname"] = name or record.get("nickname") or ""
        data[user_id] = record
        logs = _bank_log(data)
        logs.append(
            {
                "time": _now_stamp(),
                "day": today().isoformat(),
                "user": name or user_id[:8],
                "action": action,
                "amount": moved,
                "points": points,
                "bank": bank,
            }
        )
        data[BANK_KEY] = logs[-100:]
        _save(data, target)
        return BankResult(
            status="ok",
            action=action,
            amount=moved,
            points=points,
            bank=bank,
            nickname=name,
        )


def claim_interest(
    user_id: str,
    path: Path | None = None,
    nickname: str = "",
) -> BankResult:
    target = path or CHECKIN_PATH
    day_text = today().isoformat()
    with _lock:
        data = _load(target)
        record = _ensure_user(data, user_id, nickname)
        name = (nickname or record.get("nickname") or "").strip()
        points = int(record.get("points") or 0)
        bank = int(record.get("bank") or 0)
        if bank <= 0:
            return BankResult(status="empty", action="interest", points=points, bank=bank, nickname=name)
        if str(record.get("last_interest") or "") == day_text:
            return BankResult(status="cooldown", action="interest", points=points, bank=bank, nickname=name)
        gained = interest_of(bank)
        bank += gained
        record["bank"] = bank
        record["nickname"] = name or record.get("nickname") or ""
        record["last_interest"] = day_text
        data[user_id] = record
        logs = _bank_log(data)
        logs.append(
            {
                "time": _now_stamp(),
                "day": day_text,
                "user": name or user_id[:8],
                "action": "interest",
                "amount": gained,
                "points": points,
                "bank": bank,
            }
        )
        data[BANK_KEY] = logs[-100:]
        _save(data, target)
        return BankResult(
            status="ok",
            action="interest",
            amount=gained,
            points=points,
            bank=bank,
            nickname=name,
        )


def start_brick(
    user_id: str,
    path: Path | None = None,
    nickname: str = "",
    scene: str = "",
    target_id: str = "",
    msg_id: str = "",
    rng: random.Random | None = None,
) -> WorkResult:
    target = path or CHECKIN_PATH
    dice = rng or random
    with _lock:
        data = _load(target)
        record = _ensure_user(data, user_id, nickname)
        name = (nickname or record.get("nickname") or "").strip()
        points = int(record.get("points") or 0)
        state, remain = _brick_state(record)
        if state == "busy":
            return WorkResult(status="busy", seconds=remain, points=points, nickname=name)
        if state == "ready":
            return WorkResult(status="ready", points=points, nickname=name)
        secs = int(dice.randint(BRICK_MIN_SECS, BRICK_MAX_SECS))
        record["nickname"] = name or record.get("nickname") or ""
        record["work_start"] = _now().timestamp()
        record["work_secs"] = secs
        record["work_scene"] = scene
        record["work_target"] = target_id
        record["work_msg_id"] = msg_id
        record["work_notified"] = False
        data[user_id] = record
        _save(data, target)
        return WorkResult(status="started", seconds=secs, points=points, nickname=name)


def claim_wage(
    user_id: str,
    path: Path | None = None,
    nickname: str = "",
    rng: random.Random | None = None,
) -> WorkResult:
    target = path or CHECKIN_PATH
    dice = rng or random
    with _lock:
        data = _load(target)
        record = _ensure_user(data, user_id, nickname)
        name = (nickname or record.get("nickname") or "").strip()
        points = int(record.get("points") or 0)
        state, remain = _brick_state(record)
        if state == "idle":
            return WorkResult(status="idle", points=points, nickname=name)
        if state == "busy":
            return WorkResult(status="busy", seconds=remain, points=points, nickname=name)
        gained = int(dice.randint(WORK_MIN, WORK_MAX))
        points += gained
        record["points"] = points
        record["nickname"] = name or record.get("nickname") or ""
        _clear_brick(record)
        data[user_id] = record
        _save(data, target)
        return WorkResult(status="paid", gained=gained, points=points, nickname=name)


def due_brick_jobs(path: Path | None = None) -> list[BrickJob]:
    target = path or CHECKIN_PATH
    now = _now()
    with _lock:
        data = _load(target)
        jobs = []
        for user_id, record in data.items():
            if user_id in META_KEYS or not isinstance(record, dict):
                continue
            state, _remain = _brick_state(record, now)
            if state != "ready" or record.get("work_notified"):
                continue
            scene = str(record.get("work_scene") or "")
            target_id = str(record.get("work_target") or "")
            msg_id = str(record.get("work_msg_id") or "")
            if not scene or not target_id or not msg_id:
                continue
            jobs.append(
                BrickJob(
                    user_id=user_id,
                    scene=scene,
                    target_id=target_id,
                    msg_id=msg_id,
                    nickname=str(record.get("nickname") or "").strip(),
                )
            )
        return jobs


def mark_brick_notified(user_id: str, path: Path | None = None) -> None:
    target = path or CHECKIN_PATH
    with _lock:
        data = _load(target)
        record = data.get(user_id)
        if not isinstance(record, dict):
            return
        record["work_notified"] = True
        data[user_id] = record
        _save(data, target)


def format_rob_card(result: RobResult, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or result.attacker_name).strip()
    victim = result.victim_name or "对方"
    if result.status == "cooldown":
        title, body = "今天已经打劫过", "明天再来"
    elif result.status == "self":
        title, body = "打劫失败", "换个人下手"
    elif result.status == "no_target":
        title, body = "打劫失败", "现在没有可下手的人"
    elif result.status == "empty":
        if result.victim_bank:
            title, body = "打劫失败", f"{victim} 的软妹币都在银行里"
        else:
            title, body = "打劫失败", f"{victim} 没有软妹币"
    elif result.success:
        title = "打劫成功"
        body = f"从{victim}手上抢到 {result.stolen} 软妹币"
    else:
        title = "打劫失败"
        body = f"失手丢掉 {result.lost} 软妹币" if result.lost else "两手空空"
    text_lines = [title, name, body]
    md_lines = [f"# {title}", f"**{name}**" if name else "", body]
    if result.status == "ok":
        text_lines.append(f"钱包 {result.attacker_points}")
        md_lines.append(f"钱包 **{result.attacker_points}**")
        if result.success:
            text_lines.append(f"{victim} 剩余 {result.victim_points}")
            md_lines.append(f"{victim} 剩余 **{result.victim_points}**")
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def format_bank_card(result: BankResult, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or result.nickname).strip()
    if result.action == "interest":
        if result.status == "cooldown":
            title, body = "今天已经领过利息", "明天再来"
        elif result.status == "empty":
            title, body = "领取失败", "银行没有存款"
        else:
            title, body = "领取利息", f"银行利息 +{result.amount}"
    elif result.status == "empty" and result.action == "deposit":
        title, body = "存款失败", "钱包是空的"
    elif result.status == "empty":
        title, body = "取款失败", "银行没有软妹币"
    elif result.action == "deposit":
        title, body = "存款成功", f"存入 {result.amount} 软妹币"
    else:
        title, body = "取款成功", f"取出 {result.amount} 软妹币"
    text_lines = [title, name, body, f"钱包 {result.points}", f"银行 {result.bank}"]
    md_lines = [
        f"# {title}",
        f"**{name}**" if name else "",
        body,
        f"钱包 **{result.points}**",
        f"银行 **{result.bank}**",
    ]
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def format_bank_status(profile: UserProfile, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or profile.nickname).strip()
    points = profile.points if profile.found else 0
    bank = profile.bank if profile.found else 0
    text_lines = ["银行", name, f"钱包 {points}", f"银行 {bank}", f"合计 {points + bank}"]
    md_lines = [
        "# 银行",
        f"**{name}**" if name else "",
        f"钱包 **{points}**",
        f"银行 **{bank}**",
        f"合计 **{points + bank}**",
    ]
    if bank:
        expect = interest_of(bank)
        if profile.last_interest == today().isoformat():
            hint = "今日利息已领"
        else:
            hint = f"发送 利息 可领 {expect}"
        text_lines.append(hint)
        md_lines.append(hint)
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def format_work_card(result: WorkResult, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or result.nickname).strip()
    wallet = ""
    extra = ""
    if result.status == "started":
        title = "开始搬砖"
        body = f"大约 {format_duration(result.seconds)} 后完成"
        extra = "到点会提醒领工资"
    elif result.status == "busy":
        title = "还在搬砖"
        body = f"还剩 {format_duration(result.seconds)}"
    elif result.status == "ready":
        title = "搬砖完成"
        body = "发送 领工资 领取"
    elif result.status == "paid":
        title = "领取工资"
        body = f"软妹币 +{result.gained}"
        wallet = f"钱包 {result.points}"
    else:
        title = "没有待领工资"
        body = "发送 搬砖 开始干活"
    text_lines = [title, name, body, extra, wallet]
    md_lines = [
        f"# {title}",
        f"**{name}**" if name else "",
        body,
        extra,
        f"钱包 **{result.points}**" if wallet else "",
    ]
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def format_checkin(result: CheckinResult) -> str:
    text, _ = format_checkin_card(result)
    return text


def format_checkin_card(result: CheckinResult, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    title = "今天已经签到" if result.already else "签到成功"
    rank_text = f"今日第 {result.rank} 名" if result.rank else ""
    rank_md = f"今日第 **{result.rank}** 名" if result.rank else ""
    stats = f"连续 {result.streak} 天 · 累计 {result.total} 次"
    points_now = f"钱包 {result.points}"
    text_lines = [title, rank_text, stats]
    md_lines = [f"# {title}", rank_md, f"连续 **{result.streak}** 天", f"累计 **{result.total}** 次"]
    name = nickname.strip()
    if name:
        text_lines.insert(1, name)
        md_lines.insert(1, f"**{name}**")
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    if not result.already:
        extra = ""
        parts = [f"基础 {BASE_POINTS}"]
        if result.bonus:
            parts.append(f"第{result.rank}名 {result.bonus}")
        if result.streak_bonus:
            parts.append(f"连续 {result.streak_bonus}")
        if result.bonus or result.streak_bonus:
            extra = "（" + " + ".join(parts) + "）"
        text_lines.append(f"软妹币 +{result.gained}{extra}")
        md_lines.append(f"软妹币 **+{result.gained}**{extra}")
    text_lines.append(points_now)
    md_lines.append(f"钱包 **{result.points}**")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def format_query_card(profile: UserProfile, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or profile.nickname).strip()
    if not profile.found:
        text_lines = ["查询结果", name, "还没有签到记录", "发送 /签到 开始"]
        md_lines = ["# 查询结果"]
        if name:
            md_lines.append(f"**{name}**")
        md_lines.extend(["还没有签到记录", "发送 `/签到` 开始"])
        if avatar:
            md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
        text = "\n".join(line for line in text_lines if line)
        markdown = "\n".join(line for line in md_lines if line)
        return text, markdown
    rank_text = f"今日第 {profile.rank} 名" if profile.rank else "今天还未签到"
    rank_md = f"今日第 **{profile.rank}** 名" if profile.rank else "今天还未签到"
    text_lines = [
        "查询结果",
        name,
        rank_text,
        f"连续 {profile.streak} 天 · 累计 {profile.total} 次",
        f"钱包 {profile.points}",
        f"银行 {profile.bank}",
        f"合计 {profile.points + profile.bank}",
    ]
    md_lines = [
        "# 查询结果",
        f"**{name}**" if name else "",
        rank_md,
        f"连续 **{profile.streak}** 天",
        f"累计 **{profile.total}** 次",
        f"钱包 **{profile.points}**",
        f"银行 **{profile.bank}**",
        f"合计 **{profile.points + profile.bank}**",
    ]
    if profile.points_rank:
        text_lines.append(f"软妹币排名 {profile.points_rank}")
        md_lines.append(f"软妹币排名 **{profile.points_rank}**")
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def _signed(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def format_adjust_card(result: AdjustResult, avatar: str = "", nickname: str = "") -> tuple[str, str]:
    name = (nickname or result.nickname).strip()
    if result.points_delta and result.days_delta:
        title = "已调整"
    elif result.points_delta:
        title = "软妹币已调整"
    elif result.days_delta:
        title = "天数已调整"
    else:
        title = "未变化"
    text_lines = [title, name]
    md_lines = [f"# {title}", f"**{name}**" if name else ""]
    text_lines.append(f"软妹币 {_signed(result.points_delta)} → {result.points}")
    text_lines.append(f"连续天数 {_signed(result.days_delta)} → {result.streak}")
    md_lines.append(f"软妹币 **{_signed(result.points_delta)}** → **{result.points}**")
    md_lines.append(f"连续天数 **{_signed(result.days_delta)}** → **{result.streak}**")
    if avatar:
        md_lines.insert(0, f"![头像 #80px #80px]({avatar})")
    text = "\n".join(line for line in text_lines if line)
    markdown = "\n".join(line for line in md_lines if line)
    return text, markdown


def _label(user_id: str, record: dict) -> str:
    name = str(record.get("nickname") or "").strip()
    return name or user_id[:8]


def _rob_log(data: dict) -> list:
    raw = data.get(ROB_KEY)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _bank_log(data: dict) -> list:
    raw = data.get(BANK_KEY)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def summarize_checkins(path: Path | None = None) -> dict:
    target = path or CHECKIN_PATH
    day_text = today().isoformat()
    with _lock:
        data = _load(target)
        daily = _daily_map(data)
        order = [item for item in (daily.get(day_text) or []) if isinstance(item, str)]
        users = []
        for user_id, record in data.items():
            if user_id in META_KEYS or not isinstance(record, dict):
                continue
            users.append(
                {
                    "user_id": user_id,
                    "nickname": _label(user_id, record),
                    "total": int(record.get("total") or 0),
                    "streak": int(record.get("streak") or 0),
                    "points": int(record.get("points") or 0),
                    "bank": int(record.get("bank") or 0),
                    "last_date": str(record.get("last_date") or ""),
                }
            )
        today_rows = []
        for rank, user_id in enumerate(order, 1):
            record = data.get(user_id) if isinstance(data.get(user_id), dict) else {}
            today_rows.append(
                {
                    "rank": rank,
                    "nickname": _label(user_id, record),
                    "streak": int(record.get("streak") or 0),
                    "total": int(record.get("total") or 0),
                    "points": int(record.get("points") or 0),
                    "gained": BASE_POINTS + RANK_BONUS.get(rank, 0) + streak_bonus_of(int(record.get("streak") or 0)),
                }
            )
        leaderboard = sorted(
            users,
            key=lambda item: (-(item["points"] + item["bank"]), -item["points"], -item["total"], item["nickname"]),
        )[:100]
        logs = _rob_log(data)
        today_robs = [item for item in logs if str(item.get("day") or "") == day_text]
        banks = _bank_log(data)
        today_banks = [item for item in banks if str(item.get("day") or "") == day_text]
        return {
            "day": day_text,
            "today_count": len(today_rows),
            "user_count": len(users),
            "checkin_count": sum(item["total"] for item in users),
            "points_sum": sum(item["points"] for item in users),
            "bank_sum": sum(item["bank"] for item in users),
            "today": today_rows[:50],
            "leaderboard": leaderboard,
            "rob_today": len(today_robs),
            "rob_wins": sum(1 for item in today_robs if item.get("success")),
            "robs": list(reversed(logs[-50:])),
            "bank_today": len(today_banks),
            "banks": list(reversed(banks[-50:])),
        }
