#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""解密 U8 SDK 的 `.bin` 配置文件（AES-256-CBC，key/IV 为 U8SDK.dll .rdata 硬编码常量）。

逆向结论（U8SDK.dll 2.35.0，imagebase 0x180000000）：
  * `U8SDKData::ParseEncryptionFile` @ RVA 0x18004e350
      0x18004e525  call EVP_aes_256_cbc
      0x18004e52e  lea  rax, [0x1800952b0]      -> IV  (16B, 栈上传参)
      0x18004e53a  lea  r9,  [0x180095290]      -> KEY (32B, r9)
      0x18004e547  call EVP_DecryptInit_ex
    => 整文件 AES-256-CBC，无文件头 wrapper，无 KDF。
  * 另一个实现 `CryptoUtils::AesCbcDecrypt` @ 0x180011f00 是「密文前 16 字节当 IV」的
    通用版（错误串 `cannot extra IV`），只被 0x180011950（先 base64 解码输入）调用，
    与本目录的 .bin 无关；其 24 字符 key 由 0x180012530 用 .rdata 0x180094a60 处的
    48 字节表 XOR 0x5a / 0xa5 生成（与 config.bin 无关）。

用法：
  python tools/decrypt_u8_config.py                 # 解 U8Data\\config 下三个 bin
  python tools/decrypt_u8_config.py --out .local/u8config
  python tools/decrypt_u8_config.py --keys          # 只打印 key/IV 及其来源地址
"""
import argparse
import json
import os
import sys

try:
    from Crypto.Cipher import AES
except ImportError:                                             # pragma: no cover
    sys.exit("需要 pycryptodome: pip install pycryptodome")

GAME = r"C:\Program Files\Hypergryph Launcher\games\Arknights Game"
DLL = os.path.join(GAME, "U8SDK.dll")

# U8SDK.dll .rdata 里的常量（文件偏移 == RVA - 0x180000000 - 0x1000 + 0x400）
KEY_VA = 0x180095290
IV_VA = 0x1800952B0
KEY = bytes.fromhex("c0f30e1ce763bbc21cc355a34303ac50399444bff68c4a22af398c0a166ee143")
IV = bytes.fromhex("33467861192750649501937264608400")

TARGETS = [
    ("U8Data/config/config.bin", "config.json"),
    ("U8Data/config/u8ExtraConfig.bin", "u8ExtraConfig.json"),
    ("sdkdata/sdk_hgsdk_config.bin", "sdk_hgsdk_config.json"),
    ("WebviewConfig/WebviewConfig.bin", "WebviewConfig.bin.plain"),
]
SKIP = ("WebviewConfig",)          # 不同密钥族，默认跳过

# 从 RVA 读原始字节，用来证明 KEY/IV 不是编的
SECTIONS_FALLBACK = {"rdata_rva": 0x8D000, "rdata_raw": 0x8BA00}


def read_rva(va, n):
    """EXE/DLL 里按 VA 读字节（用 pefile 找节，失败则用已知 .rdata 映射）。"""
    try:
        import pefile
        pe = pefile.PE(DLL, fast_load=True)
        base = pe.OPTIONAL_HEADER.ImageBase
        for s in pe.sections:
            start = base + s.VirtualAddress
            if start <= va < start + max(s.SizeOfRawData, s.Misc_VirtualSize):
                off = s.PointerToRawData + (va - start)
                with open(DLL, "rb") as fh:
                    fh.seek(off)
                    return fh.read(n)
    except Exception:                                           # noqa: BLE001
        pass
    with open(DLL, "rb") as fh:
        off = SECTIONS_FALLBACK["rdata_raw"] + (va - 0x180000000 - SECTIONS_FALLBACK["rdata_rva"])
        fh.seek(off)
        return fh.read(n)


def decrypt(raw, key=KEY, iv=IV):
    if len(raw) % 16:
        raise ValueError("长度 %d 不是 16 的倍数" % len(raw))
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(raw)
    pad = pt[-1]
    if 0 < pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
        pt = pt[:-pad]
    return pt.rstrip(b"\x00")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".local/u8config")
    ap.add_argument("--keys", action="store_true")
    ap.add_argument("--all", action="store_true", help="连 WebviewConfig 也试")
    args = ap.parse_args()

    print("key@%#x = %s" % (KEY_VA, KEY.hex()))
    print("iv @%#x = %s" % (IV_VA, IV.hex()))
    got_key, got_iv = read_rva(KEY_VA, 32), read_rva(IV_VA, 16)
    print("read-back: key %s / iv %s" % ("OK" if got_key == KEY else "MISMATCH " + got_key.hex(),
                                         "OK" if got_iv == IV else "MISMATCH " + got_iv.hex()))
    if args.keys:
        return 0

    os.makedirs(args.out, exist_ok=True)
    for rel, name in TARGETS:
        if not args.all and rel.startswith(SKIP):
            continue
        path = os.path.join(GAME, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            continue
        raw = open(path, "rb").read()
        try:
            pt = decrypt(raw)
        except Exception as exc:                                # noqa: BLE001
            print("!! %-32s %s" % (rel, exc))
            continue
        text = pt.decode("utf-8", "replace")
        dst = os.path.join(args.out, name)
        open(dst, "w", encoding="utf-8", newline="").write(text)
        print("== %-34s %4dB -> %s" % (rel, len(raw), dst))
        try:
            doc = json.loads(text)
        except Exception:                                       # noqa: BLE001
            print(text[:400])
            continue
        u8 = (doc.get("globalConfig") or {}).get("u8")
        if u8:
            print("   globalConfig.u8: " + json.dumps(u8, ensure_ascii=False))
        if "configs" in doc:
            print("   configs keys   : " + ",".join(doc["configs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
