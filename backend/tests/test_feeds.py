"""推送订阅指令、公告 / B 站动态解析、去重与按时段调度。"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from logbook import api, feeds, qqbot
from logbook.storage import connect

from test_qqbot import CONFIG, OPENID, post

GROUP = "G1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6"
NOW = datetime(2026, 11, 28, 12, 30, tzinfo=feeds.CHINA)


class FakeClient:
    def __init__(self):
        self.replies, self.sent = [], []

    def reply_c2c(self, openid, msg_id, content, seq=1):
        self.replies.append(("c2c", openid, content))

    def reply_group(self, group_openid, msg_id, content, seq=1):
        self.replies.append(("group", group_openid, content))

    def send_c2c(self, openid, content):
        self.sent.append(("c2c", openid, content))

    def send_group(self, group_openid, content):
        self.sent.append(("group", group_openid, content))


@pytest.fixture()
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    monkeypatch.delenv("FEED_LINKS", raising=False)
    client = FakeClient()
    with TestClient(api.app):
        pass
    yield TestClient(qqbot.create_app(CONFIG, client)), client


def group_at(content, event_id="g-1"):
    return {"op": 0, "id": event_id, "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {"id": "gm-" + event_id, "content": content, "group_openid": GROUP,
                  "author": {"member_openid": OPENID}}}


def c2c(content, event_id="c-1"):
    return {"op": 0, "id": event_id, "t": "C2C_MESSAGE_CREATE",
            "d": {"id": "m-" + event_id, "content": content, "author": {"user_openid": OPENID}}}


def test_group_subscribe_status_and_unsubscribe(bot):
    client, fake = bot
    post(client, group_at(" /订阅公告"))
    assert fake.replies[-1][:2] == ("group", GROUP) and "已订阅：明日方舟游戏公告" in fake.replies[-1][2]
    post(client, group_at("订阅动态", "g-2"))
    assert "B站状态" in fake.replies[-1][2]
    post(client, group_at("订阅状态", "g-3"))
    assert "明日方舟游戏公告、明日方舟 B 站动态" in fake.replies[-1][2]
    with connect() as database:
        assert feeds.targets(database, CONFIG.app_id, feeds.AK) == [("group", GROUP)]
    post(client, group_at("取消订阅", "g-4"))
    with connect() as database:
        assert feeds.subscribed(database, CONFIG.app_id, "group", GROUP) == []


def test_group_unknown_command_gets_help(bot):
    client, fake = bot
    post(client, group_at("你好"))
    assert fake.replies == [("group", GROUP, qqbot.GROUP_HELP_TEXT)]


def test_c2c_subscribe_does_not_issue_login_link(bot):
    client, fake = bot
    post(client, c2c("订阅全部"))
    assert len(fake.replies) == 1 and "已订阅" in fake.replies[0][2]
    with connect() as database:
        assert feeds.subscribed(database, CONFIG.app_id, "c2c", OPENID) == [feeds.AK, feeds.BILI]


AK_LIST = {"code": 0, "data": {"list": [
    {"cid": "0492", "title": "星星不愿入睡\\n活动即将开启", "displayTime": "2026-11-27"},
    {"cid": "0491", "title": "中坚寻访\\n干员出率上升", "displayTime": "2026-11-26"},
]}}
AK_DETAIL = {"code": 0, "data": {"header": "SideStory「星星不愿入睡」活动即将开启",
                                 "content": "<p><strong>活动时间：</strong>12月02日 12:00</p><p>&amp;更多</p>",
                                 "jumpLink": ""}}


def fake_fetch(responses):
    def fetch(url, headers=None):
        for prefix, response in responses.items():
            if url.startswith(prefix):
                return response
        raise AssertionError(url)
    return fetch


def test_ak_first_run_seeds_then_pushes_only_new(bot):
    _, fake = bot
    responses = {feeds.AK_LIST_URL: AK_LIST, feeds.AK_DETAIL_URL.format(cid=""): AK_DETAIL}
    poller = feeds.Poller(fake, CONFIG.app_id, fake_fetch(responses), sleep=lambda _: None)
    with connect() as database:
        feeds.subscribe(database, CONFIG.app_id, "group", GROUP, [feeds.AK])
        assert poller.run_ak(database) == 0  # 第一次只记录
        responses[feeds.AK_LIST_URL] = {"code": 0, "data": {"list": [
            {"cid": "0493", "title": "新公告", "displayTime": datetime.now(feeds.CHINA).strftime("%Y-%m-%d")},
            *AK_LIST["data"]["list"],
        ]}}
        assert poller.run_ak(database) == 1
        assert poller.run_ak(database) == 0
    assert len(fake.sent) == 1
    target_type, target, text = fake.sent[0]
    assert (target_type, target) == ("group", GROUP)
    assert text.startswith("【明日方舟公告】\nSideStory「星星不愿入睡」活动即将开启")
    assert "活动时间：12月02日 12:00 &更多" in text


def test_old_items_are_recorded_but_not_pushed(bot):
    with connect() as database:
        feeds.new_items(database, feeds.AK, [feeds.Item(feeds.AK, "a", "x")])
        old = feeds.Item(feeds.AK, "b", "y", published=datetime(2026, 11, 1, tzinfo=feeds.CHINA))
        assert feeds.new_items(database, feeds.AK, [old], now=NOW) == []
        assert feeds.new_items(database, feeds.AK, [old], now=NOW) == []


BILI_FEED = {"code": 0, "data": {"items": [
    {"id_str": "111", "type": "DYNAMIC_TYPE_AV", "modules": {
        "module_author": {"pub_ts": 1795660000},
        "module_dynamic": {"desc": None, "major": {"type": "MAJOR_TYPE_ARCHIVE", "archive": {
            "title": "《明日方舟》SideStory PV", "desc": "活动即将开启"}}}}},
    {"id_str": "112", "type": "DYNAMIC_TYPE_DRAW", "modules": {
        "module_author": {"pub_ts": 1795650000},
        "module_dynamic": {"desc": None, "major": {"type": "MAJOR_TYPE_OPUS", "opus": {
            "title": None, "summary": {"text": "#明日方舟# 新干员 [doge]"}}}}}},
    {"id_str": "113", "type": "DYNAMIC_TYPE_FORWARD", "modules": {
        "module_author": {"pub_ts": 1795640000}, "module_dynamic": {"desc": {"text": "转发抽奖"}}}},
]}}


def test_bili_parsing_and_links(monkeypatch):
    seen_headers = {}

    def fetch(url, headers=None):
        seen_headers.update(headers)
        return BILI_FEED

    items = feeds.fetch_bili("161775300", "SESSDATA=x", fetch)
    assert seen_headers["Cookie"] == "SESSDATA=x"
    assert [item.id for item in items] == ["111", "112", "113"]
    assert items[0].text == "发布了视频：《明日方舟》SideStory PV\n活动即将开启"
    assert items[1].text == "#明日方舟# 新干员 [doge]"
    assert items[2].text == "转发了动态\n转发抽奖"
    assert "t.bilibili.com" not in feeds.bili_message(items[0])
    monkeypatch.setenv("FEED_LINKS", "1")
    assert feeds.bili_message(items[0]).endswith("https://t.bilibili.com/111")


def test_bili_risk_control_raises():
    with pytest.raises(feeds.BiliBlocked):
        feeds.fetch_bili("1", "", lambda url, headers=None: {"code": -352, "message": "风控校验失败"})


def test_failed_push_does_not_stop_other_targets(bot):
    class Flaky(FakeClient):
        def send_group(self, group_openid, content):
            raise RuntimeError("closed")

    flaky = Flaky()
    with connect() as database:
        feeds.subscribe(database, CONFIG.app_id, "group", GROUP, [feeds.AK])
        feeds.subscribe(database, CONFIG.app_id, "c2c", OPENID, [feeds.AK])
        assert feeds.deliver(flaky, database, CONFIG.app_id, feeds.AK, "hi", sleep=lambda _: None) == 1
    assert flaky.sent == [("c2c", OPENID, "hi")]


def at(hour, minute, second=0):
    return datetime(2026, 11, 28, hour, minute, second, tzinfo=feeds.CHINA)


@pytest.mark.parametrize("moment, expected", [
    (at(12, 0), 30),        # 忙时段整点
    (at(12, 5), 30),
    (at(12, 59), 30),
    (at(9, 58), 30),        # 10 点整点窗口提前开始
    (at(12, 30), 120),      # 忙时段非整点
    (at(12, 57), 60),       # 不越过 :58 的整点窗口
    (at(20, 0), 600),       # 闲时整点也不加密
    (at(17, 58), 600),      # 18 点已不在忙时段
    (at(3, 10), 600),
    (at(3, 50), 480),       # 闲时也在 :58 重新判断
])
def test_schedule(moment, expected):
    schedule = feeds.Schedule(peak=30, busy=120, idle=600)
    assert schedule.delay(moment) == expected


def test_parse_hours():
    assert feeds.parse_hours("9-21") == (9, 21)
    with pytest.raises(RuntimeError):
        feeds.parse_hours("18-10")
