#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""u8 getToken 完整链路（appId/channelId/worldId/subChannel 取自解密后的 config.bin）。

链路：
  1. 读 .local/hgsdk_plain.json 里的 hgsdk user_token / hg uid
  2. POST https://as.hypergryph.com/user/oauth2/v2/grant
       {"type":1,"appCode":"7318def77669979d","token":"<user_token>"}
     -> data.token = 鹰角 app 级 access_token
  3. POST https://as.hypergryph.com/u8/user/v1/getToken
       {"appId":"1","channelId":"1","worldId":"1","subChannel":"1","platform":2,
        "deviceId","deviceId2":"","deviceId3":"",
        "extension":"{\"uid\":<uid>,\"access_token\":<access_token>}","sign"}
     -> data.token = u8 token
  4. GET https://ak-webview.hypergryph.com/api/autoChess/act3autochess/playerSummary?code=<u8 token>

用法: python tools/u8_gettoken_from_hgsdk.py [--dry]
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAIN = os.path.join(ROOT, ".local", "hgsdk_plain.json")
OUT = os.path.join(ROOT, ".local", "u8_gettoken_hgsdk.json")

APP_CODE = "7318def77669979d"
SIGN_KEY = b"91240f70c09a08a6bc72af1a5c8d4670"
GRANT_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
U8_URL = "https://as.hypergryph.com/u8/user/v1/getToken"
WEBVIEW = "https://ak-webview.hypergryph.com/api/autoChess/act3autochess/playerSummary?code="
DEVICE = __import__("secrets").token_hex(16)  # 实测 deviceId 不绑定账号，随机即可

# config.bin -> globalConfig.u8（tools/decrypt_u8_config.py 解出的真值）
CFG = {"appId": "1", "channelId": "1", "worldId": "1", "subChannel": "1"}

HDRS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept-Encoding": "identity",
    "X-AppCode": APP_CODE,
    "X-DeviceId": DEVICE,
    "X-DeviceType": "2",
    "X-DeviceModel": "DESKTOP-D59UCI1",
}


def call(url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in HDRS.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                       # noqa: BLE001
        return -1, "%s: %s" % (type(e).__name__, e)


def load_login():
    for a in json.load(open(PLAIN, encoding="utf-8"))["accounts"]:
        if a.get("user_token"):
            return a["uid"], a["user_token"]
    raise SystemExit("no user_token in .local/hgsdk_plain.json")


def grant(uid, user_token):
    st, txt = call(GRANT_URL, {"type": 1, "appCode": APP_CODE, "token": user_token})
    doc = json.loads(txt) if txt.startswith("{") else {}
    tok = (doc.get("data") or {}).get("token")
    print("grant  HTTP %s uid=%s access_token len=%s head=%s" %
          (st, (doc.get("data") or {}).get("uid"), len(tok or ""), (tok or "")[:8]))
    return st, tok, doc


def make_extension(uid, access_token):
    """type=2 = 官服 access_token 通道，access_token 放在 `code` 里 (实测 200)。

    对照（全部 appId=1/channelId=1/worldId=1/subChannel=1，sign 不变）：
      {"code":<hgsdk user_token>,"type":1,"isSuc":true}      -> 400 invalid appId or channel param
      {"uid":..,"access_token":..}                            -> 400 verify fail
      {"code":<access_token>,"type":1,"isSuc":true}           -> 400 verify fail (签名写错也是这条)
      {"code":<access_token>,"type":2,"isSuc":true}           -> 200 + data.token
    """
    return json.dumps({"code": access_token, "type": 2, "isSuc": True},
                      separators=(",", ":"))


def u8_sign(params):
    msg = "&".join("%s=%s" % (k, params[k]) for k in sorted(params) if k != "sign")
    return hmac.new(SIGN_KEY, msg.encode(), hashlib.sha1).hexdigest(), msg


def u8_body(uid, access_token):
    b = {
        "appId": CFG["appId"],
        "channelId": CFG["channelId"],
        "worldId": CFG["worldId"],
        "subChannel": CFG["subChannel"],
        "platform": 2,
        "deviceId": DEVICE,
        "deviceId2": "",
        "deviceId3": "",
        "extension": make_extension(uid, access_token),
    }
    b["sign"], msg = u8_sign(b)
    return b, msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    uid, user_token = load_login()
    print("hgsdk uid=%s user_token len=%d head=%s" % (uid, len(user_token), user_token[:8]))
    st, access_token, gdoc = grant(uid, user_token)
    if not access_token:
        print(gdoc)
        return 1

    body, msg = u8_body(uid, access_token)
    print("sign-msg:", msg[:160] + ("..." if len(msg) > 160 else ""))
    if args.dry:
        print(json.dumps({k: (v[:24] + "..." if k == "extension" else v) for k, v in body.items()},
                         ensure_ascii=False, indent=2))
        return 0

    st2, txt2 = call(U8_URL, body)
    doc = json.loads(txt2) if txt2.startswith("{") else {}
    # 实测成功响应是 {"result":0,"uid":...,"channelUid":...,"token":"..."}，token 在顶层
    u8_token = doc.get("token") or (doc.get("data") or {}).get("token")
    print("getToken HTTP %s  %s" % (st2, txt2[:180].replace("\n", " ")))
    rec = {"grant_http": st, "uid": uid, "access_token_len": len(access_token),
           "access_token_head": access_token[:8], "request": body, "sign_msg": msg,
           "gettoken_http": st2, "gettoken_resp": txt2[:2000]}
    if u8_token:
        print("u8 token len=%d head=%s" % (len(u8_token), u8_token[:8]))
        rec.update(u8_token_len=len(u8_token), u8_token_head=u8_token[:8], u8_token=u8_token)
        code = urllib.parse.quote(u8_token, safe="")
        st3, txt3 = call(WEBVIEW + code)
        print("playerSummary HTTP %s" % st3)
        print(txt3[:600])
        rec.update(webview_http=st3, webview=txt3[:4000])
        try:
            wj = json.loads(txt3)
            rec["webview_status"] = wj.get("status")
            rec["nickname"] = ((wj.get("data") or {}).get("player") or {}).get("nickname")
        except Exception:                                        # noqa: BLE001
            pass
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("saved ->", OUT)
    return 0 if u8_token else 1


if __name__ == "__main__":
    sys.exit(main())
