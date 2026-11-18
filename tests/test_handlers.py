from app.handlers import parse_incoming, reply_for_message


def test_group_at_message_strips_mention():
    message = parse_incoming(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": "msg-1",
            "content": "<@!123456> /help",
            "group_openid": "group-1",
            "author": {"member_openid": "user-1"},
        },
        "evt-1",
    )
    assert message is not None
    assert message.scene == "group"
    assert message.content == "/help"
    help_reply = reply_for_message(message)
    assert help_reply is not None
    assert "签到" in help_reply.text
    assert "查询" in help_reply.text
    assert "打劫" in help_reply.text
    assert "/ping" not in help_reply.text


def test_parse_incoming_reads_avatar():
    message = parse_incoming(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": "msg-avatar",
            "content": "/签到",
            "group_openid": "group-1",
            "author": {
                "member_openid": "user-1",
                "username": "小明",
                "avatar": "http://thirdqq.qlogo.cn/g?b=qq&s=100&nk=1",
            },
        },
        "evt-avatar",
    )
    assert message is not None
    assert message.nickname == "小明"
    assert message.avatar == "https://thirdqq.qlogo.cn/g?b=qq&s=100&nk=1"


def test_group_full_message_commands_only(monkeypatch, tmp_path):
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    chatter = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "msg-chat",
            "content": "今天天气不错",
            "group_openid": "group-1",
            "author": {"member_openid": "user-2"},
        },
        "evt-chat",
    )
    assert chatter is not None
    assert reply_for_message(chatter) is None

    command = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "msg-qd",
            "content": "/签到",
            "group_openid": "group-1",
            "author": {"member_openid": "user-2"},
        },
        "evt-qd",
    )
    assert command is not None
    reply = reply_for_message(command)
    assert reply is not None
    assert reply.text.startswith("签到成功")

    bare = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "msg-bare",
            "content": "签到",
            "group_openid": "group-1",
            "author": {"member_openid": "user-2"},
        },
        "evt-bare",
    )
    assert bare is not None
    again = reply_for_message(bare)
    assert again is not None
    assert again.text.startswith("今天已经签到")

    bot_msg = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "msg-bot",
            "content": "/help",
            "group_openid": "group-1",
            "author": {"member_openid": "bot-1", "bot": True},
        },
        "evt-bot",
    )
    assert bot_msg is not None
    assert reply_for_message(bot_msg) is None

    help_bare = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "msg-help-bare",
            "content": "help",
            "group_openid": "group-1",
            "author": {"member_openid": "user-2"},
        },
        "evt-help-bare",
    )
    assert help_bare is not None
    help_reply = reply_for_message(help_bare)
    assert help_reply is not None
    assert "查询" in help_reply.text


def test_default_reply():
    plain = parse_incoming(
        "AT_MESSAGE_CREATE",
        {"id": "m3", "content": "天气", "channel_id": "c1", "author": {"id": "u2"}},
        "e3",
    )
    assert plain is not None
    plain_reply = reply_for_message(plain)
    assert plain_reply is not None
    assert plain_reply.text == "收到\n天气"


def test_checkin_once_per_day(monkeypatch, tmp_path):
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    message = parse_incoming(
        "C2C_MESSAGE_CREATE",
        {"id": "m4", "content": "/签到", "author": {"user_openid": "u-checkin"}},
        "e4",
    )
    assert message is not None
    first = reply_for_message(message)
    assert first is not None
    assert first.text.startswith("签到成功")
    assert "连续 1 天" in first.text
    assert "今日第 1 名" in first.text
    assert "软妹币 +30" in first.text
    assert "钱包 30" in first.text
    assert first.markdown is not None
    assert first.markdown.startswith("# 签到成功")
    second = reply_for_message(message)
    assert second is not None
    assert second.text.startswith("今天已经签到")
    assert "累计 1 次" in second.text
    assert "今日第 1 名" in second.text
    assert "钱包 30" in second.text


def test_query_command(monkeypatch, tmp_path):
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    empty = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "q1",
            "content": "查询",
            "group_openid": "group-1",
            "author": {"member_openid": "user-q", "username": "小明"},
        },
        "eq1",
    )
    assert empty is not None
    before = reply_for_message(empty)
    assert before is not None
    assert "还没有签到记录" in before.text

    checkin = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "q2",
            "content": "/签到",
            "group_openid": "group-1",
            "author": {"member_openid": "user-q", "username": "小明"},
        },
        "eq2",
    )
    assert checkin is not None
    reply_for_message(checkin)

    query = parse_incoming(
        "C2C_MESSAGE_CREATE",
        {"id": "q3", "content": "/查询", "author": {"user_openid": "user-q", "username": "小明"}},
        "eq3",
    )
    assert query is not None
    result = reply_for_message(query)
    assert result is not None
    assert result.text.startswith("查询结果")
    assert "钱包 30" in result.text
    assert "软妹币排名 1" in result.text
    assert result.markdown is not None
    assert result.markdown.startswith("# 查询结果")


def test_adjust_commands(monkeypatch, tmp_path):
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    add_points = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "a1",
            "content": "加积分 5",
            "group_openid": "group-1",
            "author": {"member_openid": "user-a", "username": "小明"},
        },
        "ea1",
    )
    assert add_points is not None
    added = reply_for_message(add_points)
    assert added is not None
    assert added.text.startswith("软妹币已调整")
    assert "软妹币 +5 → 5" in added.text

    sub_days = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "a2",
            "content": "减天数 2",
            "group_openid": "group-1",
            "author": {"member_openid": "user-a", "username": "小明"},
        },
        "ea2",
    )
    assert sub_days is not None
    reduced = reply_for_message(sub_days)
    assert reduced is not None
    assert "连续天数 +0 → 0" in reduced.text

    bad = parse_incoming(
        "C2C_MESSAGE_CREATE",
        {"id": "a3", "content": "加积分 abc", "author": {"user_openid": "user-a"}},
        "ea3",
    )
    assert bad is not None
    failed = reply_for_message(bad)
    assert failed is not None
    assert failed.text.startswith("调整失败")


def test_parse_mentions_for_rob():
    group = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "r1",
            "content": "打劫 <@!victim-1>",
            "group_openid": "group-1",
            "author": {"member_openid": "attacker"},
        },
        "er1",
    )
    assert group is not None
    assert group.mention_ids == ["victim-1"]

    at = parse_incoming(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": "r2",
            "content": "<@!bot-id> 打劫 <@!victim-1>",
            "group_openid": "group-1",
            "author": {"member_openid": "attacker"},
        },
        "er2",
    )
    assert at is not None
    assert at.mention_ids == ["victim-1"]


def test_rob_command(monkeypatch, tmp_path):
    from app.checkin import check_in

    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    check_in("attacker", tmp_path / "checkins.json", nickname="小明")
    check_in("victim-1", tmp_path / "checkins.json", nickname="小红")

    class WinRng:
        def random(self):
            return 0.1

        def uniform(self, a, b):
            return 0.2

        def choice(self, seq):
            return "victim-1"

    monkeypatch.setattr("app.checkin.random.Random", lambda: WinRng())
    message = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "r3",
            "content": "打劫 <@!victim-1>",
            "group_openid": "group-1",
            "author": {"member_openid": "attacker", "username": "小明"},
        },
        "er3",
    )
    assert message is not None
    reply = reply_for_message(message)
    assert reply is not None
    assert reply.text.startswith("打劫成功")
    assert "抢到 4 软妹币" in reply.text


def test_rob_glues_at_mention(monkeypatch, tmp_path):
    from app.checkin import check_in

    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    check_in("attacker2", tmp_path / "checkins.json", nickname="小刚")
    check_in("victim-1", tmp_path / "checkins.json", nickname="小红")

    class WinRng:
        def random(self):
            return 0.1

        def uniform(self, a, b):
            return 0.2

        def choice(self, seq):
            return "other"

    monkeypatch.setattr("app.checkin.random.Random", lambda: WinRng())
    message = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "r5",
            "content": "打劫 @小红",
            "group_openid": "group-1",
            "author": {"member_openid": "attacker2", "username": "小刚"},
        },
        "er5",
    )
    assert message is not None
    assert message.content == "打劫@小红"
    reply = reply_for_message(message)
    assert reply is not None
    assert reply.text.startswith("打劫成功")
    assert "小红" in reply.text

    glued = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "r6",
            "content": "打劫@小红",
            "group_openid": "group-1",
            "author": {"member_openid": "attacker3", "username": "小李"},
        },
        "er6",
    )
    assert glued is not None
    assert glued.content == "打劫@小红"
    again = reply_for_message(glued)
    assert again is not None
    assert again.text.startswith("打劫成功")
    assert "小红" in again.text


def test_bank_commands(monkeypatch, tmp_path):
    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    checkin = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "b1",
            "content": "签到",
            "group_openid": "group-1",
            "author": {"member_openid": "user-b", "username": "小明"},
        },
        "eb1",
    )
    assert checkin is not None
    reply_for_message(checkin)
    deposit = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "b2",
            "content": "存款",
            "group_openid": "group-1",
            "author": {"member_openid": "user-b", "username": "小明"},
        },
        "eb2",
    )
    assert deposit is not None
    saved = reply_for_message(deposit)
    assert saved is not None
    assert saved.text.startswith("存款成功")
    assert "钱包 0" in saved.text
    bank = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "b3",
            "content": "银行",
            "group_openid": "group-1",
            "author": {"member_openid": "user-b", "username": "小明"},
        },
        "eb3",
    )
    assert bank is not None
    status = reply_for_message(bank)
    assert status is not None
    assert status.text.startswith("银行")
    assert "银行 30" in status.text

    interest = parse_incoming(
        "GROUP_MESSAGE_CREATE",
        {
            "id": "b4",
            "content": "利息",
            "group_openid": "group-1",
            "author": {"member_openid": "user-b", "username": "小明"},
        },
        "eb4",
    )
    assert interest is not None
    paid = reply_for_message(interest)
    assert paid is not None
    assert paid.text.startswith("领取利息")
    assert "银行利息 +1" in paid.text
    again = reply_for_message(interest)
    assert again is not None
    assert again.text.startswith("今天已经领过利息")


def test_brick_command(monkeypatch, tmp_path):
    from datetime import datetime, timedelta

    from app.checkin import TZ

    monkeypatch.setattr("app.checkin.CHECKIN_PATH", tmp_path / "checkins.json")
    clock = {"t": datetime(2026, 11, 18, 12, 0, 0, tzinfo=TZ)}
    monkeypatch.setattr("app.checkin._now", lambda: clock["t"])
    monkeypatch.setattr("app.checkin.random.randint", lambda a, b: 120 if a >= 120 else 15)

    def incoming(content, msg_id):
        return parse_incoming(
            "GROUP_MESSAGE_CREATE",
            {
                "id": msg_id,
                "content": content,
                "group_openid": "group-1",
                "author": {"member_openid": "user-w", "username": "小明"},
            },
            f"e-{msg_id}",
        )

    start_msg = incoming("搬砖", "w1")
    assert start_msg is not None
    first = reply_for_message(start_msg)
    assert first is not None
    assert first.text.startswith("开始搬砖")
    assert "2 分钟" in first.text
    busy = reply_for_message(incoming("搬砖", "w2"))
    assert busy is not None
    assert busy.text.startswith("还在搬砖")
    early = reply_for_message(incoming("领工资", "w3"))
    assert early is not None
    assert early.text.startswith("还在搬砖")
    clock["t"] = clock["t"] + timedelta(seconds=120)
    paid = reply_for_message(incoming("领工资", "w4"))
    assert paid is not None
    assert paid.text.startswith("领取工资")
    assert "软妹币 +15" in paid.text
