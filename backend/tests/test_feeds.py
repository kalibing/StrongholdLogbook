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
        self.outbound = []

    def reply_c2c(self, openid, msg_id, content, seq=1):
        self.replies.append(("c2c", openid, content))

    def reply_group(self, group_openid, msg_id, content, seq=1):
        self.replies.append(("group", group_openid, content))

    def send_c2c(self, openid, content):
        self.sent.append(("c2c", openid, content))

    def send_group(self, group_openid, content):
        self.sent.append(("group", group_openid, content))
        self.outbound.append((group_openid, "text", content))

    def send_group_markdown(self, group_openid, content):
        self.outbound.append((group_openid, "markdown", content))


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
    assert fake.replies == [("group", GROUP, "@我发送「日报」查看自己的昨日战报，发送「战绩」查看最近 10 局战绩。")]


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
            "title": "《明日方舟》SideStory PV", "desc": "活动即将开启", "cover": "//i1.hdslb.com/cover.jpg"}}}}},
    {"id_str": "112", "type": "DYNAMIC_TYPE_DRAW", "modules": {
        "module_author": {"pub_ts": 1795650000},
        "module_dynamic": {"desc": None, "major": {"type": "MAJOR_TYPE_OPUS", "opus": {
            "title": None, "summary": {"text": "#明日方舟# 新干员 [doge]"},
            "pics": [{"url": "https://invalid.example/cover.jpg"}, {"url": "https://i0.hdslb.com/first.png"},
                     {"url": "https://i0.hdslb.com/second.png"}]}}}}},
    {"id_str": "113", "type": "DYNAMIC_TYPE_FORWARD", "modules": {
        "module_author": {"pub_ts": 1795640000}, "module_dynamic": {"desc": {"text": "转发抽奖"}}},
        "orig": {"modules": {"module_dynamic": {"major": {"draw": {
            "items": [{"src": "http://i2.hdslb.com/original.jpg"}]}}}}}},
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
    assert [[image.url for image in item.images] for item in items] == [
        ["https://i1.hdslb.com/cover.jpg"],
        ["https://i0.hdslb.com/first.png", "https://i0.hdslb.com/second.png"],
        ["https://i2.hdslb.com/original.jpg"],
    ]
    _, footer = feeds.bili_message(items[0])
    assert "t.bilibili.com" not in footer
    monkeypatch.setenv("FEED_LINKS", "1")
    _, footer = feeds.bili_message(items[0])
    assert footer.endswith("https://t.bilibili.com/111")


def test_bili_preserves_original_paragraphs_and_long_caption():
    text = "第一段\r\n\r\n　第二段：" + "没有截断" * 50 + "\n最后一段\n"
    item = {"modules": {"module_dynamic": {"major": {"opus": {"summary": {"text": text}}}}}}
    assert feeds.bili_text(item) == text.replace("\r\n", "\n")


def test_bili_poller_sends_all_images_in_one_message_per_group(bot):
    class Flaky(FakeClient):
        def send_group_markdown(self, group_openid, content):
            super().send_group_markdown(group_openid, content)
            if group_openid == GROUP:
                raise RuntimeError("message rejected")

    client = Flaky()
    entries = list(BILI_FEED["data"]["items"])
    poller = feeds.Poller(client, CONFIG.app_id, lambda *_: {"code": 0, "data": {"items": entries}}, sleep=lambda _: None)
    with connect() as database:
        for group in (GROUP, "second-group"):
            feeds.observe_group(database, CONFIG.app_id, group)
            assert feeds.configure_group(database, CONFIG.app_id, group, None, [feeds.BILI])
        assert poller.run_bili(database, "161775300", "SESSDATA=x") == 0
        item = entries[1]
        timestamp = datetime.now(feeds.CHINA).replace(microsecond=0)
        pics = [{"url": f"//i0.hdslb.com/{index}.png", "width": 1000, "height": 2100} for index in range(1, 8)]
        entries.insert(0, {
            **item, "id_str": "114",
            "modules": {
                "module_author": {"pub_ts": timestamp.timestamp()},
                "module_dynamic": {"major": {"opus": {
                    "summary": {"text": "第一行\n\n#明日方舟# 新干员 [doge]"},
                    "pics": [*pics, pics[0]],
                }}},
            },
        })
        assert poller.run_bili(database, "161775300", "SESSDATA=x") == 1
        assert poller.run_bili(database, "161775300", "SESSDATA=x") == 0
    markdown = "\n\n".join([
        "【明日方舟 B 站动态】", "第一行", "\u200b", r"\#明日方舟\# 新干员 \[doge\]",
        *(f"![配图 {index} #600px #1260px](https://i0.hdslb.com/{index}.png)" for index in range(1, 8)),
        timestamp.strftime("%Y-%m-%d %H:%M"),
    ])
    assert client.outbound == [
        (GROUP, "markdown", markdown),
        ("second-group", "markdown", markdown),
    ]


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
    (at(20, 0), 1800),      # 闲时整点也不加密
    (at(17, 58), 1800),     # 18 点已不在忙时段
    (at(3, 10), 1800),
    (at(3, 50), 1800),      # 不为闲时整点提前唤醒
    (at(9, 47), 660),       # 09:58 进入首个忙时整点窗口
])
def test_schedule(moment, expected):
    schedule = feeds.Schedule(peak=30, busy=120, idle=1800)
    assert schedule.delay(moment) == expected


def test_bilibili_idle_wait_can_cross_an_inactive_hour_boundary():
    assert feeds.Schedule(peak=60, busy=180, idle=3600).delay(at(21, 31)) == 3600
    assert feeds.Schedule(peak=60, busy=180, idle=3600, busy_start=0, busy_end=6).delay(at(23, 30)) == 1680


def test_parse_hours():
    assert feeds.parse_hours("9-21") == (9, 21)
    with pytest.raises(RuntimeError):
        feeds.parse_hours("18-10")


def test_unexpected_poll_errors_do_not_stop_the_poller():
    class Broken(feeds.Poller):
        def run_ak(self, database):
            raise AttributeError("'list' object has no attribute 'get'")

        def run_bili(self, database, uid, cookie):
            raise TypeError("unexpected payload")

    poller = Broken(FakeClient(), CONFIG.app_id)
    feeds.poll_ak(poller, None)
    assert feeds.poll_bili(poller, None, "1", "SESSDATA=x") is False


def test_malformed_bili_payload_counts_as_failed_poll():
    payload = {"code": 0, "data": {"items": [{"id_str": "1", "modules": "oops"}]}}
    poller = feeds.Poller(FakeClient(), CONFIG.app_id, fetch=lambda *_args: payload)
    assert feeds.poll_bili(poller, None, "1", "SESSDATA=x") is False


def test_storage_errors_still_reach_the_main_loop():
    class Down(feeds.Poller):
        def run_ak(self, database):
            raise feeds.StorageUnavailable("down")

        run_bili = lambda self, *args: self.run_ak(None)  # noqa: E731

    poller = Down(FakeClient(), CONFIG.app_id)
    with pytest.raises(feeds.StorageUnavailable):
        feeds.poll_ak(poller, None)
    with pytest.raises(feeds.StorageUnavailable):
        feeds.poll_bili(poller, None, "1", "SESSDATA=x")
