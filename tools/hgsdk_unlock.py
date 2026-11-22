# -*- coding: utf-8 -*-
"""hgsdk_unlock.py — 离线解出鹰角通行证 (HG) access token，不启动任何游戏进程。

用法
----
    .venv\\Scripts\\python.exe tools\\hgsdk_unlock.py
    .venv\\Scripts\\python.exe tools\\hgsdk_unlock.py --show-token      # 控制台也打印完整 token
    .venv\\Scripts\\python.exe tools\\hgsdk_unlock.py --out .local\\hgsdk_plain.json

产物
----
    .local\\hgsdk_plain.json   （含完整 token，仅本地文件，不要提交/上传）
    .local\\re\\mmkv_dump\\*   （可选，--dump-dir 时导出每个解密后的 MMKV 明文）

== 推断依据（全部来自 hgsdk.dll 1.30.0.2 静态反汇编，未运行进程）================

1) 密钥材料 = 注册表 REG_GUID，而不是 DPAPI 密文本身
   - QHgSdkImpl::checkREGEncrykey  @ RVA 0x70b70（.pdata 函数边界 0x180070b70-0x1800710d6）
     * 三个分支都返回 **REG_GUID 字符串** 给调用方；state==2 分支才读
       REG_GUID_V3_Encrypt → DecryptString(DPAPI) → 返回其明文。
     * state==1 分支（首次）：若出现 REG_GUID 但缺少 REG_GUID_V3_Encrypt，则调用
       QHgSdkImpl::EncryptString(@0x70190) 把 **REG_GUID** 做 CryptProtectData 回写，
       日志串 'step1 create REG_GUID_V3_Encrypt'。=> V3_Encrypt 只是 DPAPI 的
       一致性/防篡改副本（解开就是 REG_GUID 本身），不是 AES key 本体。
   - QHgSdkImpl::initLoginMMKV  @ 0x1800716f0-0x180071fab
     * 0x180071852 调 checkREGEncrykey → 得到 strEncrykey（= REG_GUID）
     * 0x180071dba（正常分支）/ 0x180071999（首次分支）都是同一条公式：

           tmp   = QString(REG_GUID) + "*6E39452-319B-409C-AB75-865FEA25EC3*"   (@0x18006ea60 = operator+)
           digest= QCryptographicHash::hash(tmp.toUtf8(), alg=1 /*Md5*/)
           hex   = digest.toHex().toLower()          # 32 字符，即 strEncrykey/std::string
           mmkv  = MMKV cryptKey = hex[0:16]          # MMKV 取前 16 字节做 AES-128

     * salt 常量位于 .rdata 0x1800e5728 = "*6E39452-319B-409C-AB75-865FEA25EC3*"（36 字节）
     * 该 hex 串写入内部 store 的 "login_cache" 键（0x180006990，r8d=2）

2) MMKV 文件布局（MMKV-1.2.15，路径串 "D:\\project\\3rd\\MMKV-1.2.15\\Core\\MMKV.cpp"）
   - 前 4 字节 = actualSize（小端，明文，不加密）
   - 其后 payload：明文实例以固定 4 字节 ff ff ff 07 开头（已在
     disable_onechannel_config / sdk_data_*/sdk_hgsdk_data_1 中直接观察到）
   - 记录循环：[varint klen][key][varint vlen][value]
     字符串值的 [0] 字节 = 数据长度，vlen = 1 + 该长度（如 token len=25 → 0x18=24+1）

3) AES 参数
   - 算法：AES-128-**CFB128**（MMKV 的 AESCrypt），key = hex[0:16] 的 ASCII 字节
   - **IV 不派生**：每个文件自己的 <file>.crc（MMKVMetaInfo）在 **偏移 12 处** 存了
     16 字节向量；用它解密后首块正好是 ff ff ff 07（本脚本据此校验密钥正确性）。
     meta 布局实测：+0 crcDigest, +4 version, +8 sequence, +12 m_vector[16], +28 actualSize。
   - 因此不要把 IV 猜成 key/全零——那样只有首块错，其余能读，容易误判。

4) token 落在哪个文件
   - sdk_data_<md5(REG_GUID?...)>/login_cache（本例 2789 字节）解出后含
     <uid>_user_token = 24 字符 HG access token，另有 <uid>_hypergryph_id、
     <uid>_Machine_guid、<uid>_login_time、<uid>_login_status、device_token、hgid_list 等。
   - .\\sdkdata\\sdk_hgsdk_data_1（全局实例）与 gameprotocol_cache 用别的 key，
     本脚本会如实报告为 unresolved，不要当成解密失败。

约束：全程只读写注册表 HKCU\\...\\sdk_data 的读取、只读游戏目录、不写入游戏目录。
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from Crypto.Cipher import AES

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SALT = "*6E39452-319B-409C-AB75-865FEA25EC3*"
REG_ROOT = r"SOFTWARE\Hypergryph\sdk_data"
LOCALLOW = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/Hypergryph/Arknights"
MMKV_MAGIC = b"\xff\xff\xff\x07"
TOKEN_FIELD = "user_token"
UID_FIELD = "hypergryph_id"


# --------------------------------------------------------------------------- DPAPI
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def dpapi_unprotect(data: bytes) -> bytes | None:
    out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out)
    )
    if not ok:
        return None
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def qt_bytearray(raw: bytes) -> bytes:
    """QSettings 把 QByteArray 写成 UTF-16 文本 '@ByteArray(<每字节一个宽字符>)'。"""
    if raw[:2] == b"@\x00":
        text = raw.decode("utf-16-le", "ignore")
        if text.startswith("@ByteArray(") and text.endswith(")"):
            return bytes(ord(c) & 0xFF for c in text[len("@ByteArray(") : -1])
    return raw


# ------------------------------------------------------------------------ registry
def read_groups() -> list[dict]:
    import winreg

    groups = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT) as root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            rec = {"group": name, "reg_guid": None, "v3_encrypt": None, "v3_dpapi_plain": None}
            with winreg.OpenKey(root, name) as k:
                for field, key in (("reg_guid", "REG_GUID"), ("v3_encrypt", "REG_GUID_V3_Encrypt")):
                    try:
                        val, _kind = winreg.QueryValueEx(k, key)
                    except OSError:
                        continue
                    if field == "reg_guid":
                        rec[field] = val if isinstance(val, str) else val.decode("utf-16-le", "ignore")
                    else:
                        rec[field] = val if isinstance(val, bytes) else str(val).encode()
            if rec["v3_encrypt"]:
                plain = dpapi_unprotect(qt_bytearray(rec["v3_encrypt"]))
                rec["v3_dpapi_plain"] = plain.decode("ascii", "replace") if plain else None
            groups.append(rec)
    return groups


def mmkv_key(guid: str) -> tuple[bytes, str]:
    hexd = hashlib.md5((guid + SALT).encode()).hexdigest()
    return hexd[:16].encode(), hexd


# ----------------------------------------------------------------------------- MMKV
def varint(buf: bytes, i: int) -> tuple[int, int]:
    v = 0
    shift = 0
    while True:
        b = buf[i]
        i += 1
        v |= (b & 0x7F) << shift
        if not b & 0x80:
            return v, i
        shift += 7


def parse_records(body: bytes, start: int = 4) -> tuple[list[tuple[bytes, bytes]], int]:
    i = start
    recs = []
    while i < len(body):
        try:
            klen, i = varint(body, i)
            if not 0 < klen <= 512 or i + klen > len(body):
                break
            k = body[i : i + klen]
            i += klen
            vlen, i = varint(body, i)
            if vlen > len(body) - i:
                break
            recs.append((k, body[i : i + vlen]))
            i += vlen
        except IndexError:
            break
    return recs, i


def _printable(b: bytes) -> bool:
    return bool(b) and all(0x20 <= c < 0x7F for c in b)


def decode_value(v: bytes):
    """MMKV 值编码（MiniPBCoder）：QString = varint 长度 + UTF-8，int = varint，bool = 1 字节。"""
    if len(v) == 1:
        return bool(v[0]) if v[0] <= 1 else v[0]
    if len(v) >= 2 and v[0] == len(v) - 1 and _printable(v[1:]):       # QString
        return v[1:].decode("utf-8", "replace")
    if _printable(v):
        return v.decode("utf-8", "replace")
    try:                                                               # varint int
        val, used = varint(v, 0)
        if used == len(v):
            return val
    except IndexError:
        pass
    runs = [r for r in re.findall(rb"[\x20-\x7e]{4,}", v)]              # 嵌套 list/bytearray
    if runs:
        best = max(runs, key=len)
        if len(best) * 2 >= len(v):
            return best.decode("utf-8", "replace")
    return "hex:" + v.hex()


def decrypt_file(path: Path, key: bytes) -> dict:
    blob = path.read_bytes()
    actual = int.from_bytes(blob[:4], "little")
    if actual == 0:
        return {"actual_size": 0, "state": "empty"}
    body = blob[4 : 4 + actual]
    if body[:4] == MMKV_MAGIC:  # 明文实例
        return {"actual_size": actual, "state": "plaintext", "body": body}
    meta = path.with_suffix(path.suffix + ".crc")
    iv = None
    if meta.exists():
        mb = meta.read_bytes()
        if len(mb) >= 28:
            iv = mb[12:28]
    tried = []
    for ivname, ivv in (("meta", iv), ("zero", b"\x00" * 16), ("key", key)):
        if ivv is None:
            continue
        pt = AES.new(key, AES.MODE_CFB, iv=ivv, segment_size=128).decrypt(body)
        tried.append(ivname)
        if pt[:4] == MMKV_MAGIC:
            return {"actual_size": actual, "state": "decrypted", "iv_source": ivname,
                    "iv": ivv.hex(), "body": pt}
    return {"actual_size": actual, "state": "unresolved", "iv_candidates": tried}


def scan_mmkv(root: Path) -> list[Path]:
    out = []
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".crc"):
            try:
                if p.read_bytes()[:4] and int.from_bytes(p.read_bytes()[:4], "little") <= 4096 * 16:
                    out.append(p)
            except OSError:
                pass
    return out


def unlock_file(path: Path, key: bytes) -> dict:
    info = decrypt_file(path, key)
    rec = {k: v for k, v in info.items() if k != "body"}
    if "body" not in info:
        return rec
    recs, consumed = parse_records(info["body"])
    fields: dict = {}
    history: dict = {}
    for k, v in recs:  # MMKV 是 append-only log：后者覆盖前者
        name = k.decode("utf-8", "replace")
        val = decode_value(v)
        if name in fields and fields[name] != val:
            history.setdefault(name, [fields[name]]).append(val)
        fields[name] = val
    rec["records"] = len(recs)
    rec["bytes_consumed"] = consumed
    rec["fields"] = fields
    if history:
        rec["overwritten_history"] = history
    stamps = {}
    for name, val in fields.items():
        if name.endswith("_login_time") and isinstance(val, int) and 1_500_000_000 < val < 2_100_000_000:
            stamps[name] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(val))
    if stamps:
        rec["login_time_local"] = stamps
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / ".local" / "hgsdk_plain.json"))
    ap.add_argument("--show-token", action="store_true")
    ap.add_argument("--dump-dir", action="store_true")
    ap.add_argument("--guid", action="append", help="强制使用指定 REG_GUID（可多次）")
    args = ap.parse_args()

    groups = read_groups()
    if not groups:
        print("[!] 注册表 HKCU\\%s 下没有子键" % REG_ROOT)
        return 2

    guids = args.guid or [g["reg_guid"] for g in groups if g["reg_guid"]]
    result = {"tool": "hgsdk_unlock.py", "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "salt": SALT, "source_dir": str(LOCALLOW), "accounts": [], "notes": []}

    files = scan_mmkv(LOCALLOW)
    print("[*] 候选 MMKV 文件: %d 个" % len(files))

    seen_keys = {}
    for guid in dict.fromkeys(guids):
        key, hexd = mmkv_key(guid)
        seen_keys[guid] = key
        print("\n[*] REG_GUID = %s" % guid)
        print("    md5(REG_GUID+salt) = %s" % hexd)
        print("    MMKV cryptKey       = %s  (hex[0:16])" % key.decode())
        acct = {"reg_guid": guid, "md5_hex": hexd, "mmkv_key": key.decode(), "files": {}}
        group = None
        for g in groups:
            if g["reg_guid"] == guid:
                group = g["group"]
                acct["registry_group"] = group
                acct["v3_encrypt_dpapi_plain"] = g["v3_dpapi_plain"]
                acct["v3_matches_reg_guid"] = (g["v3_dpapi_plain"] or "").strip("\x00") == guid
        # 每个账号只看自己的 sdk_data_<group> 目录 + 全局 sdkdata 目录
        scope = [f for f in files
                 if f.parent.name == "sdkdata" or (group and f.parent.name == "sdk_data_" + group)]
        for f in scope:
            rel = str(f.relative_to(LOCALLOW))
            info = unlock_file(f, key)
            if info["state"] in ("empty", "unresolved"):
                result["notes"].append("%s: %s" % (rel, info["state"]))
                continue
            acct["files"][rel] = info
            print("    OK  %-58s %-9s %s" % (rel, info["state"], info.get("iv_source", "-")))
            if args.dump_dir and "fields" in info:
                dd = Path(args.out).parent / "re" / "mmkv_dump" / rel.replace("\\", "__")
                dd.parent.mkdir(parents=True, exist_ok=True)
                dd.write_text(json.dumps(info["fields"], ensure_ascii=False, indent=1), encoding="utf-8")
        result["accounts"].append(acct)

    # ---- 报告：字段名 + 长度；token 仅本地落盘 ----
    for acct in result["accounts"]:
        toks, uids = {}, set()
        for rel, info in acct["files"].items():
            for k, v in info.get("fields", {}).items():
                if k.endswith("_" + TOKEN_FIELD) and isinstance(v, str):
                    toks[k] = v
                    uids.add(k[: -len(TOKEN_FIELD) - 1])
                if k.endswith("_" + UID_FIELD):
                    uids.add(str(v))
                if k == "hgid_list":
                    uids.add(str(v))
        acct["uid_candidates"] = sorted(u for u in uids if u)
        acct["tokens"] = toks
        if toks:
            acct["uid"] = acct["uid_candidates"][0] if acct["uid_candidates"] else None
            for k, v in toks.items():
                acct[TOKEN_FIELD] = v
                acct["token_field"] = k
                break
        print("\n=== 账号 %s (registry %s) ===" % (acct.get("uid"), acct.get("registry_group")))
        print("    REG_GUID_V3_Encrypt == REG_GUID ? %s" % acct.get("v3_matches_reg_guid"))
        for rel, info in acct["files"].items():
            fl = info.get("fields", {})
            print("    [%s] %s  records=%s consumed=%s" % (rel, info["state"],
                                                           info.get("records"), info.get("bytes_consumed")))
            for k in sorted(fl):
                v = fl[k]
                if isinstance(v, str) and k.endswith("_" + TOKEN_FIELD):
                    shown = v[:8] + "…(%d chars)" % len(v)
                elif isinstance(v, str):
                    shown = v if len(v) <= 40 else v[:20] + "…(%d)" % len(v)
                else:
                    shown = repr(v)
                print("       %-34s %s" % (k, shown))
        if toks:
            for k, v in toks.items():
                print("    >> %s = %s" % (k, v if args.show_token else v[:8] + "…（%d chars，完整值见输出 JSON）" % len(v)))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    print("\n[+] 写入 %s" % out)
    if result["notes"]:
        print("[i] 未能解开的实例（预期内，使用不同密钥）：")
        for n in sorted(set(result["notes"])):
            print("    -", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
