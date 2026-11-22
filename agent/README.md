# 本机助手（Arknights 成就档案）

在你的 Windows 机器上，静态解出「明日方舟 PC 端」的登录态，换一枚 u8 token，把成就数据推给站点。
不抓包、不启动游戏、不改游戏目录。

## 下载

站点「成就档案 → 拿令牌」面板底部有 **本机助手** 下载入口，或直接取
`frontend/public/download/ArknightsAchvAgent.exe`（自行打包见下）。

## 用法

```powershell
# 交互式
.\ArknightsAchvAgent.exe --api http://127.0.0.1:8000

# 全参数
.\ArknightsAchvAgent.exe --api https://your.site --user demo --password ******

# 只打印 token（自己贴到网页）
.\ArknightsAchvAgent.exe --print-token
```

前提：这台机器上**用明日方舟 PC 端登录过**（否则没有本地登录态可用）。

## 它做了什么

```
HKCU\SOFTWARE\HyperGryph\sdk_data\<hash>\REG_GUID
    └─ MMKV key = MD5(REG_GUID + salt)[:16]
%USERPROFILE%\AppData\LocalLow\Hypergryph\Arknights\sdk_data_*\login_cache
    └─ AES-128-CFB 解密（IV 取同名 .crc 偏移 12）→ <hgid>_user_token
POST as.hypergryph.com/user/oauth2/v2/grant      {type:1, appCode, token}
    └─ data.token = access_token
POST as.hypergryph.com/u8/user/v1/getToken
    appId=1 / channelId=1 / worldId=1 / subChannel=1 / platform=2
    extension = {"code":<access_token>,"type":2,"isSuc":true}
    sign = HMAC-SHA1(salt, 除 sign 外按键名升序 k=v 用 & 连接，值不编码)
    └─ data.token = u8 token
POST <站点>/api/session → POST <站点>/api/achv/session  {token:"code=<u8 token>"}
```

`appId/channelId/worldId/subChannel` 来自游戏自带 `U8Data\config\config.bin`
（AES-256-CBC，key/IV 硬编码在 `U8SDK.dll` 的 `.rdata`；见 `tools/decrypt_u8_config.py`）。


## 风险与免责（务必先读）

本工具是**非官方**的个人研究工具，与鹰角网络（Hypergryph）无任何关联、未获授权。使用前请确认你能接受以下全部风险：

1. **账号风险**：取数链路绕开了官方开放接口，靠的是解析本机客户端登录态换取令牌。
   这属于非官方用法，**可能触发服务端风控，最坏情况导致账号被限制或封禁**。使用者自行承担全部后果。
2. **隐私风险**：工具会读取本机注册表（`HKCU\SOFTWARE\HyperGryph`）与游戏本地登录数据
   （`%LocalAppData%Low\Hypergryph\Arknights`），在**本机内存**里解密出登录令牌。
   工具本身不上传这些内容，但：**请勿在他人或不信任的机器上运行，也不要把解出的令牌交给任何人**。
3. **可用性风险**：u8 令牌有时效（小时级），常量（appCode / sign salt / `config.bin` 的 AES key 与 IV）
   随游戏版本变化，**随时可能失效**，届时需要重新定位。
4. **分发风险**：只用本仓库源码自行构建的版本。他人二次打包的 exe 可能被植入恶意代码，
   不要把来源不明的 exe 当成本工具。
5. **使用范围**：仅限**自己的账号、自己的机器、个人研究自用**。
   禁止代跑他人账号、批量采集、对外提供服务或任何商业用途。
6. **数据归属**：游戏内容、商标、数据版权归鹰角网络所有；本项目只处理使用者本人的账号数据。

## 实现边界

- 只读本机文件与注册表，不写注册表、不改游戏目录。
- 只把换到的 u8 token 发给你在 `--api` 里指定的站点，不发往任何第三方。
- 仅适用于**自己的账号 + 自己的机器**；不能用于代跑他人账号。
- 这些常量（appCode / sign salt / config.bin 的 key 与 IV）来自客户端，游戏大版本更新后可能变化，
  需要重新定位并更新本文件顶部的常量。

## 自行打包

```powershell
python -m pip install pyinstaller pycryptodome
pyinstaller --onefile --name ArknightsAchvAgent agent/achv_agent.py
# 产物：dist/ArknightsAchvAgent.exe
```
