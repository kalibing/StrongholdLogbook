"""管理员配置群推送、公告与动态解析、去重和轮询调度。"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from logbook import accounts, api, feeds, qqbot
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
    monkeypatch.setenv("QQBOT_APP_ID", CONFIG.app_id)
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


def test_only_site_admins_can_configure_detected_push_groups(bot):
    client, fake = bot
    headers = {"Origin": "http://localhost:8080"}
    route = "/api/admin/qq-groups"
    details = {"group_number": "123456789", "sources": ["ak", "bili"]}
    post(client, group_at(" /订阅全部"))
    assert "日报" in fake.replies[-1][2]
    with connect() as database:
        user = accounts.create_with_password(database, "admin-user", "test-user-password")
        assert feeds.targets(database, CONFIG.app_id, feeds.AK) == []
    with TestClient(api.app) as web:
        assert web.get(route).status_code == 401
        assert web.post("/api/session", json={"username": "admin-user", "password": "test-user-password"},
                        headers=headers).status_code == 200
        assert web.get(route).status_code == 403
        assert web.put(f"{route}/{GROUP}", json=details, headers=headers).status_code == 403
        with connect() as database:
            database.execute("INSERT INTO admins (user_id) VALUES (%s)", (user["id"],))
        assert web.put(f"{route}/unknown", json=details, headers=headers).status_code == 404
        assert web.put(f"{route}/{GROUP}", json=details, headers=headers).status_code == 204
        group, = web.get(route).json()["items"]
        assert group["group_openid"] == GROUP and group["group_number"] == "123456789"
        assert group["sources"] == ["ak", "bili"]
        post(client, group_at("取消订阅", "cancel-from-group"))
        post(client, c2c("取消订阅", "cancel-from-private"))
        assert web.get(route).json()["items"][0]["sources"] == ["ak", "bili"]
        assert web.put(f"{route}/{GROUP}", json={**details, "sources": []}, headers=headers).status_code == 204
    with connect() as database:
        assert feeds.targets(database, CONFIG.app_id, feeds.AK) == []


def test_group_unknown_command_gets_help(bot):
    client, fake = bot
    post(client, group_at("你好"))
    assert fake.replies == [("group", GROUP, "@我发送「日报」查看自己的昨日战报。")]


def test_c2c_subscribe_does_not_create_a_push_destination(bot):
    client, fake = bot
    post(client, c2c("订阅全部"))
    assert fake.replies == [("c2c", OPENID, qqbot.HELP_TEXT)]
    with connect() as database:
        assert database.execute("SELECT 1 FROM feed_subscriptions").fetchone() is None


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
        feeds.observe_group(database, CONFIG.app_id, GROUP)
        assert feeds.configure_group(database, CONFIG.app_id, GROUP, None, [feeds.AK])
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
            if group_openid == GROUP:
                raise RuntimeError("closed")
            super().send_group(group_openid, content)

    flaky = Flaky()
    with connect() as database:
        for group in (GROUP, "second-group"):
            feeds.observe_group(database, CONFIG.app_id, group)
            assert feeds.configure_group(database, CONFIG.app_id, group, None, [feeds.AK])
        database.execute("""
            INSERT INTO feed_subscriptions (bot_app_id, target_type, target_openid, source)
            VALUES (%s, 'c2c', %s, %s)
        """, (CONFIG.app_id, OPENID, feeds.AK))
        assert feeds.deliver(flaky, database, CONFIG.app_id, feeds.AK, "hi", sleep=lambda _: None) == 1
    assert flaky.sent == [("group", "second-group", "hi")]


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
