from app.checkin import (
    BASE_POINTS,
    RANK_BONUS,
    CheckinResult,
    check_in,
    adjust_score,
    bank_transfer,
    claim_interest,
    format_checkin_card,
    format_query_card,
    get_profile,
    interest_of,
    set_score,
    rob,
    summarize_checkins,
    start_brick,
    claim_wage,
    due_brick_jobs,
    mark_brick_notified,
    today,
)


def test_daily_rank_bonus(tmp_path):
    path = tmp_path / "checkins.json"
    first = check_in("u1", path)
    assert first.rank == 1
    assert first.bonus == RANK_BONUS[1]
    assert first.gained == BASE_POINTS + RANK_BONUS[1]
    assert first.points == first.gained

    second = check_in("u2", path)
    assert second.rank == 2
    assert second.gained == BASE_POINTS + RANK_BONUS[2]

    third = check_in("u3", path)
    assert third.rank == 3
    assert third.gained == BASE_POINTS + RANK_BONUS[3]

    fourth = check_in("u4", path)
    assert fourth.rank == 4
    assert fourth.bonus == 0
    assert fourth.gained == BASE_POINTS

    again = check_in("u1", path)
    assert again.already is True
    assert again.rank == 1
    assert again.points == first.points
    assert again.gained == 0


def test_checkin_card_shows_bonus():
    text, markdown = format_checkin_card(
        CheckinResult(
            already=False,
            total=1,
            streak=1,
            day="2026-11-18",
            points=30,
            gained=30,
            rank=1,
            bonus=20,
        )
    )
    assert "今日第 1 名" in text
    assert "软妹币 +30（基础 10 + 第1名 20）" in text
    assert "钱包 **30**" in markdown


def test_checkin_card_includes_avatar():
    _, markdown = format_checkin_card(
        CheckinResult(
            already=False,
            total=1,
            streak=1,
            day="2026-11-18",
            points=30,
            gained=30,
            rank=1,
            bonus=20,
        ),
        avatar="https://q.qlogo.cn/g?b=qq&s=100&nk=1",
        nickname="小明",
    )
    assert markdown.startswith("![头像 #80px #80px](https://q.qlogo.cn/g?b=qq&s=100&nk=1)")
    assert "**小明**" in markdown


def test_summarize_checkins(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("user-aaaa", path, nickname="小明")
    check_in("user-bbbb", path, nickname="小红")
    data = summarize_checkins(path)
    assert data["today_count"] == 2
    assert data["user_count"] == 2
    assert data["today"][0]["nickname"] == "小明"
    assert data["today"][0]["rank"] == 1
    assert data["today"][0]["gained"] == BASE_POINTS + RANK_BONUS[1]
    assert data["leaderboard"][0]["points"] >= data["leaderboard"][1]["points"]
    assert data["rob_today"] == 0
    assert data["robs"] == []


def test_get_profile_and_query_card(tmp_path):
    path = tmp_path / "checkins.json"
    empty = get_profile("u1", path)
    assert empty.found is False
    text, markdown = format_query_card(empty, nickname="小明")
    assert "还没有签到记录" in text
    assert "发送 `/签到` 开始" in markdown

    check_in("u1", path, nickname="小明")
    check_in("u2", path, nickname="小红")
    profile = get_profile("u1", path)
    assert profile.found is True
    assert profile.rank == 1
    assert profile.points_rank == 1
    assert profile.points == BASE_POINTS + RANK_BONUS[1]
    card, md = format_query_card(profile, nickname="小明")
    assert card.startswith("查询结果")
    assert "今日第 1 名" in card
    assert "钱包 30" in card
    assert "银行 0" in card
    assert "软妹币排名 1" in card
    assert md.startswith("# 查询结果")


def test_adjust_score_clamps_at_zero(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    added = adjust_score("u1", points_delta=5, days_delta=2, path=path)
    assert added.points == 35
    assert added.streak == 3
    assert added.points_delta == 5
    assert added.days_delta == 2

    reduced = adjust_score("u1", points_delta=-100, days_delta=-10, path=path)
    assert reduced.points == 0
    assert reduced.streak == 0
    assert reduced.points_delta == -35
    assert reduced.days_delta == -3

    fresh = adjust_score("new-user", points_delta=8, path=path, nickname="新人")
    assert fresh.points == 8
    assert fresh.streak == 0
    assert fresh.nickname == "新人"


def test_set_score_updates_absolute_values(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("user-aaaa", path, nickname="小明")
    missing = set_score("nope", points=1, path=path)
    assert missing is None
    updated = set_score("user-aaaa", points=88, streak=4, path=path)
    assert updated is not None
    assert updated.points == 88
    assert updated.streak == 4
    profile = get_profile("user-aaaa", path)
    assert profile.points == 88
    assert profile.streak == 4
    data = summarize_checkins(path)
    assert data["leaderboard"][0]["user_id"] == "user-aaaa"
    assert data["leaderboard"][0]["points"] == 88


class _WinRng:
    def random(self):
        return 0.1

    def uniform(self, a, b):
        return 0.2

    def choice(self, seq):
        return seq[0]


class _FailRng:
    def random(self):
        return 0.9

    def uniform(self, a, b):
        return 0.2

    def choice(self, seq):
        return seq[0]


def test_rob_success_and_cooldown(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    check_in("u2", path, nickname="小红")
    won = rob("u1", "u2", path=path, nickname="小明", rng=_WinRng())
    assert won.status == "ok"
    assert won.success is True
    assert won.stolen == 4
    assert won.attacker_points == 34
    assert won.victim_points == 16
    again = rob("u1", "u2", path=path, rng=_WinRng())
    assert again.status == "cooldown"
    self_hit = rob("u2", "u2", path=path, rng=_WinRng())
    assert self_hit.status == "self"
    summary = summarize_checkins(path)
    assert summary["rob_today"] == 1
    assert summary["rob_wins"] == 1
    assert summary["robs"][0]["attacker"] == "小明"
    assert summary["robs"][0]["victim"] == "小红"
    assert summary["robs"][0]["stolen"] == 4
    assert summary["robs"][0]["success"] is True


def test_rob_fail_loses_points(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    check_in("u2", path, nickname="小红")
    lost = rob("u1", "u2", path=path, rng=_FailRng())
    assert lost.status == "ok"
    assert lost.success is False
    assert lost.lost == 3
    assert lost.attacker_points == 27
    summary = summarize_checkins(path)
    assert summary["rob_today"] == 1
    assert summary["rob_wins"] == 0
    assert summary["robs"][0]["lost"] == 3
    assert summary["robs"][0]["success"] is False


def test_bank_deposit_protects_from_rob(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    check_in("u2", path, nickname="小红")
    saved = bank_transfer("u2", "deposit", 0, path=path, nickname="小红")
    assert saved.status == "ok"
    assert saved.points == 0
    assert saved.bank == 20
    empty = rob("u1", "u2", path=path, nickname="小明", rng=_WinRng())
    assert empty.status == "empty"
    assert empty.victim_bank == 20
    taken = bank_transfer("u2", "withdraw", 5, path=path, nickname="小红")
    assert taken.status == "ok"
    assert taken.points == 5
    assert taken.bank == 15
    summary = summarize_checkins(path)
    assert summary["bank_sum"] == 15
    assert summary["banks"][0]["action"] == "withdraw"
    by_name = {row["nickname"]: row for row in summary["leaderboard"]}
    assert by_name["小红"]["bank"] == 15
    assert by_name["小红"]["points"] == 5


def test_claim_bank_interest_once_per_day(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    bank_transfer("u1", "deposit", 0, path=path, nickname="小明")
    profile = get_profile("u1", path)
    first = claim_interest("u1", path=path, nickname="小明")
    assert first.status == "ok"
    assert first.amount == interest_of(profile.bank)
    assert first.bank == profile.bank + first.amount
    again = claim_interest("u1", path=path, nickname="小明")
    assert again.status == "cooldown"
    none = claim_interest("u2", path=path, nickname="小红")
    assert none.status == "empty"
    summary = summarize_checkins(path)
    assert summary["banks"][0]["action"] == "interest"


def test_interest_has_no_cap(tmp_path):
    path = tmp_path / "checkins.json"
    check_in("u1", path, nickname="小明")
    set_score("u1", bank=10000, path=path)
    paid = claim_interest("u1", path=path, nickname="小明")
    assert paid.status == "ok"
    assert paid.amount == 500
    assert paid.bank == 10500


def test_streak_bonus_grows(tmp_path):
    import json
    from datetime import timedelta

    path = tmp_path / "checkins.json"
    yesterday = (today() - timedelta(days=1)).isoformat()
    path.write_text(
        json.dumps(
            {
                "u1": {
                    "last_date": yesterday,
                    "total": 1,
                    "streak": 1,
                    "points": 30,
                    "bank": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    second = check_in("u1", path)
    assert second.streak == 2
    assert second.streak_bonus == 1
    assert second.gained == BASE_POINTS + RANK_BONUS[1] + 1


class _BrickRng:
    def __init__(self, value):
        self.value = value

    def randint(self, low, high):
        return self.value


def test_brick_job_then_claim(tmp_path, monkeypatch):
    from datetime import timedelta

    path = tmp_path / "checkins.json"
    clock = {"t": today()}
    from app.checkin import TZ
    from datetime import datetime

    start_at = datetime(2026, 11, 18, 12, 0, 0, tzinfo=TZ)
    clock["t"] = start_at
    monkeypatch.setattr("app.checkin._now", lambda: clock["t"])
    started = start_brick(
        "u1",
        path,
        nickname="小明",
        scene="group",
        target_id="g1",
        msg_id="m1",
        rng=_BrickRng(120),
    )
    assert started.status == "started"
    assert started.seconds == 120
    busy = start_brick("u1", path, rng=_BrickRng(120))
    assert busy.status == "busy"
    assert 100 <= busy.seconds <= 120
    early = claim_wage("u1", path, rng=_BrickRng(15))
    assert early.status == "busy"
    assert due_brick_jobs(path) == []
    clock["t"] = start_at + timedelta(seconds=120)
    ready = start_brick("u1", path, rng=_BrickRng(120))
    assert ready.status == "ready"
    jobs = due_brick_jobs(path)
    assert len(jobs) == 1
    assert jobs[0].user_id == "u1"
    mark_brick_notified("u1", path)
    assert due_brick_jobs(path) == []
    paid = claim_wage("u1", path, nickname="小明", rng=_BrickRng(15))
    assert paid.status == "paid"
    assert paid.gained == 15
    assert paid.points == 15
    idle = claim_wage("u1", path, rng=_BrickRng(15))
    assert idle.status == "idle"
    again = start_brick("u1", path, rng=_BrickRng(180))
    assert again.status == "started"
    assert again.seconds == 180
