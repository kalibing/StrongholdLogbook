# 成就档案：数据怎么来，字段怎么解

> 目标：把卫戍协议 H5「成就」页上的**六维成就、18 个称号、社交、已获赞、昵称、策略/分队特殊标识**搬进本站，
> 并且尽量用**鹰角通行证**登录，而不是让用户每次手动抓包。
>
> 本文所有「已实测」结论都来自本机真机抓包 + 真实账号跑通（2026-11-22）。

---

## 1. 一个接口就够

成就页（`ak-webview.hypergryph.com/autoChess/index?…&u8_token=…`）加载完成后只请求一次数据接口：

```http
GET https://ak-webview.hypergryph.com/api/autoChess/act3autochess/playerSummary?code=<u8_token>
```

- `code` 就是入口链接里的 `u8_token`，**同一串**，必须 URL 编码（`%2F` `%2B` `%3D`）。
- 原样传（不编码）→ `{"status":10008,"msg":"找不到玩家角色"}`（已实测）。
- 响应 `data` 下 15 个顶层字段，本页需要的全在里面：

| 字段 | 内容 |
|---|---|
| `data.player` | `uid` / `nickname` / `nickNumber` / `level` / `avatar` / `nameCard` |
| `data.title.achievements` | 六维评分 `{BOND,KILL,EQUIP,COIN,CHAR,DAMAGE}`，0–100 |
| `data.title.list` / `specialList` | 12 个「称号一览」+ 6 个「特殊称号」的 `{id, value}` |
| `data.season.titles` | 18 个称号的定义：`type` / `rank` / `txt` / `picId` |
| `data.beLike` | 已获赞 |
| `data.friend` | `friendList`（92）与 `starFriendList`（特别关注） |
| `data.teammate` + `data.teammatePlayers` | 最常同玩 / 最多胜场同伴及其昵称等级 |
| `data.trophy` / `trophyLevel` / `careerTrophy` | 奖杯总数、等级、图标 id |
| `data.band.top` / `data.band.pass` | 策略 TOP3 与 6 个特殊标识（见 §3） |
| `data.bond` / `data.mode` / `data.max` | 盟约、模拟战绩、单局纪录（顺带取用） |
| `data.season` | 赛季版本 `V3_1`、主数据字典（bands/bonds/chesses/items…） |

六维与称号的**中文名**不在接口里，来自前端 i18n 包（`act1autochess_i18n.*.js`）：

```
achievement.BOND=盟约理解  achievement.KILL=补救能力  achievement.CHAR=人力调度
achievement.EQUIP=装备活用 achievement.COIN=资金管理  achievement.DAMAGE=领袖挑战
```

`title.achievements` 的取值在渲染时被 `Math.min(100, x)` 截断，所以口径就是 **0–100 分**。

---

## 2. 怎么拿到 `code`：三条路

### 2.1 粘贴链接 / 令牌（100% 可用，已实测）

游戏内打开「卫戍协议 · 成就」→ 复制地址栏 → 粘到本站「成绩档案 → 绑定」里的第二个标签。
服务端会从链接里抽 `code`/`u8_token`，也接受 `playerSummary?code=…` 整行或裸令牌。

有效期：**按天更新**（游戏每次登录重开 H5 都会换新），过期后本站继续展示上次快照并提示刷新。

### 2.2 鹰角通行证账密（已实现，需要真机验证一次）

```
POST https://as.hypergryph.com/user/auth/v1/token_by_phone_password   {"phone","password"}
        └─ data.token                     ← 鹰角 access token（接口已实测存在，错误码 100 = 账号密码错误）
POST https://as.hypergryph.com/u8/user/v1/getToken
        body: {appId:"1", platform:1, channelId:"1", subChannel:"1", worldId:"1",
               deviceId, deviceId2, deviceId3, extension:'{"uid","access_token"}', sign}
        └─ data.token                     ← u8 token，即 playerSummary 的 code
GET  https://ak-webview.hypergryph.com/api/autoChess/act3autochess/playerSummary?code=<上面那个>
```

细节：

- `getToken` 的字段校验已实测确认（缺 `subChannel`/`deviceId`/`deviceId2`/`deviceId3`/`extension` 会 400 并逐条报错；
  `appCode` 与 `extension` 互斥，传了会报 `excluded_with`）。
- `sign` = `urlencode(sorted(body))` 做 **HMAC-SHA1，固定密钥 `91240f70c09a08a6bc72af1a5c8d4670`**，取小写 hex。
- 卡点：`extension.uid` 需要**鹰角账号 uid**。`token_by_phone_password` 的响应里能读到就直接用，
  读不到时本站会退化为空 uid 重试一次；仍失败就明确报错并引导走 §2.1（不猜、不静默成功）。
- 风控：账密直登可能被鹰角人机验证拦住（森空岛文档里已记录过数美风控）。被拦时同样回退到 §2.1。

实现见 `backend/logbook/hypergryph.py`（`token_by_password` / `u8_token` / `player_summary` / `extract_code`）。

### 2.3 网页登录（本站已实现，推荐）

不碰账密：让用户在**鹰角官方登录页**上登录（人机验证由官方页面自己处理），服务端只取登录结果。

```
浏览器                    本站后端（反代）                 鹰角
  │ 打开 /hg/user/login  →  /hg/user/* → user.hypergryph.com   ← HTML（改写 CDN / API 地址）
  │ 页面 bundle          →  /hg/cdn/*  → web.hycdn.cn           ← JS（把 https://as.hypergryph.com 改写成 /hg/as）
  │ 表单登录 POST        →  /hg/as/user/auth/v1/token_by_phone_password
  │                          └─ 转发并读取响应里的 data.token（HG access token）
  │ 轮询 /api/hg/capture ←  内存槽（按浏览器 nonce，10 分钟）
  │ POST /api/achv/session {access_token}
  │                          ├─ GET as/user/info/v1/basic?token=…      → data.hgId（channel uid）
  │                          ├─ POST as/u8/user/v1/getToken {uid, access_token} → u8 token
  │                          └─ GET …/playerSummary?code=<u8 token>    → 成就档案
```

为什么必须反代：HG 前端的 axios `baseURL` 是四个绝对域名（`as` / `u8` / `binding` / `web`），
跨域直连会被 CORS 拦。反代后页面与 API 同源，浏览器的 `Set-Cookie` 也被改写成同源 cookie。

实现：`backend/logbook/hgproxy.py`（`/hg/user`、`/hg/cdn`、`/hg/as`、`/hg/u8`、`/hg/binding`、`/hg/web`、`/api/hg/capture`）。
请求体不落盘、不写日志；只有登录接口**成功响应**里的 `data.token` / `data.uid` 会进 10 分钟内存槽。

配套改动：Vite 的 dev proxy 与 Caddyfile 都要把 `/hg` 转发到 API（已加）。
`u8/oauth2/auth/v1/channel_token` 目前返回 404（官方前端里仍留着调用），所以这条只作为兜底候选。

### 2.4 WebView 授权（未实现）

用系统 WebView 打开 `https://user.hypergryph.com/login`，登录后拦 `web-api.skland.com/account/info/hg`
的响应（`data.content` 就是 HG token）。桌面端打包时可选。

---

## 3. 「特殊标识」为什么是两种

`data.band.pass` 里 6 条记录，每条只有 `{id, name, masterVictor}`，前端渲染时：

```js
className = classNames('jDhW1o', 'GajVs2', extra)      // 所有 6 个都有底色标识
<div data-master-victor={masterVictor}> … </div>        // 命中 CSS 才换图
```

```css
.jDhW1o.GajVs2:after                      { background: url(底色标识.png) }
.jDhW1o.GajVs2[data-master-victor=true]:after {
  background-image: url('…/assets/img/mark_pro.fda48b.png');  /* 右上角 pro 角标 */
}
```

所以两种形态是**同一枚标识的两种状态**：

| 站点字段 | 含义 | 来源 |
|---|---|---|
| `variant: "master"` | 精通标识（带 `mark_pro` 角标），`masterVictor = true` | `data.band.pass[].masterVictor` |
| `variant: "base"` | 基础标识（只有底图，未精通），`masterVictor = false` | 同上 |

样例（当前赛季 6 枚：4 精通 / 2 未精通）：复奏、昆图斯、森蚺、歌蕾蒂娅 = master；Pith、鸭爵 = base。

另外每枚标识还带**分队所属类型** `type`（`GENERAL` 通用 44 个 / `BONDRELEVANT` 盟约相关 17 个），
它来自 `data.season.bands[id].type`，页面上用来说明这枚标识属于哪一类策略——和「精通/基础」是两个维度，别混。

---

## 4. 站点落地

### 4.1 数据表

```sql
CREATE TABLE achv_links (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    source text NOT NULL CHECK (source IN ('hypergryph', 'token')),
    phone_masked text,        -- 138****1234，只为展示
    u8_token text NOT NULL,   -- 换来的 u8 token，刷新时复用
    uid text, nickname text,
    payload jsonb NOT NULL,   -- 归一化后的成就档案
    fetched_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
```

迁移：`backend/migrations/versions/0002_achievements.py`；SQLite 侧同步在 `sqlite_schema.py`。
密码**不入库**，只在请求内存里走一次换取。

### 4.2 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/achv/status` | `{connected, source, uid, nickname, fetched_at, stale, phone}` |
| POST | `/api/achv/session` | `{phone,password}` 或 `{token}`；成功返回归一化档案 |
| GET | `/api/achv/summary?refresh=true` | 读快照；超过 10 分钟或显式 refresh 时用存的 token 重拉，失败则回退旧快照 + `warning` |
| DELETE | `/api/achv/session` | 解绑并删除 token |

归一化在 `backend/logbook/achievements.py`：`normalize()` 只依赖 `data`，缺字段一律降级为 `null`/`[]`，
不会因为赛季字段变动整块白屏。

### 4.3 页面

`frontend/src/views/Achievements.vue`（导航「成就档案」）：

1. 绑定区：鹰角通行证（手机号+密码）/ 粘贴链接两个标签页；
2. 头部：头像、昵称 `#编号`、Lv、UID、数据时间、刷新 / 解绑；
3. 指标：已获奖杯 + 等级、已获赞、好友数、特殊标识精通数；
4. 六维条形图，每维下面挂该维度的 3 个称号（特殊 / T1 / T2）与数值；
5. 策略纪录 TOP3 + **两种特殊标识分组**（`master` 组带 PRO 角标，`base` 组半透明）；
6. 社交（最常同玩、好友、特别关注 UID）、战果与单局纪录。

图标走本地 `/art/strategy-<bandId>.png`，缺失时回退到 `data.season.bands[id].image.icon`（hycdn）。
分队卡是「头像在左、名字 + 胜率/场次在右」的横版卡：海报图 180×180，用径向遮罩裁成圆形头像贴到卡片左侧，
右上角 TOP 角标，底部细条是胜率填充。

**已获赞的图标取自游戏本体**：H5 的 `act1autochess.*.css` 里 `.GMDJVs .VMRzld`（点赞框图）是内联 base64，
已落盘成 `frontend/public/art/like-box.png`（104×104）；标签旁的小灰色点赞手势另存为 `like-glyph.png`（24×21）。
同法可取到 `.kL1JwC` 的奖杯小图标，奖杯大图仍用 `trophy_level8_icon.png`。

---

## 5. 已知限制

1. `code` 按天过期：过期后只能展示旧快照，需要重新授权（通行证路径能自动续，令牌路径不能）。
2. 通行证直登的最后一步（`getToken` 的 `extension.uid`）需要真实账号验证一次；
   服务端会把鹰角原文错误回传，不静默成功。
3. 称号的 `value` 接口没给语义说明，页面按「数值」原样展示，没有硬编码成「已获得」。
4. 数据更新口径是**每日 10:00 完成昨日数据更新**（H5 自己的提示），不是实时。

---

## 6. 复查 / 自测

```powershell
# 归一化 + 链路（离线）
cd backend; ..\.venv\Scripts\python.exe -m pytest tests\test_achievements.py -q

# 用真实 token 打一次接口（不落库）
..\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from logbook import hypergryph as h;print(h.player_summary(h.extract_code(open('..\\..\\token.txt').read()))['trophy'])"

# 起服务后跑一遍端到端
pwsh -File tools\verify_achv_api.ps1     # 需要先把 $base 指到运行中的 API
```

---

## 9. u8 token 到底从哪来（2026-11-22 定论）

### 9.1 `getToken` 这条路走不通的原因

`POST https://as.hypergryph.com/u8/user/v1/getToken` 的 `extension` **不是明文 JSON**，而是
`U8SDK.dll` 里 `CryptoUtils` 加密后的 blob。实测：

- 字段校验能过：`appCode`(与 `appId` 互斥) / `subChannel` / `deviceId` / `deviceId2` / `deviceId3` / `extension` 必填；
- 但 `extension` 用任何明文形态（`{uid,access_token}`、`{uid,token}`、`{uid,code}`、`{hgId,token}`、
  `grant.token`、`grant.code`）都会得到 `400 {"message":"verify fail"}`；
- 客户端头也必须用 u8 那套（`X-DeviceId` = u8 设备号，**不要**带 `X-AppCode`/`X-DeviceId2`/`X-OSVer`），
  这套头只影响能否进入校验，不改变 `verify fail`。

结论：**要自动换 u8 token，必须先逆 `U8SDK.dll` 的 extension 加密**，否则这条路永远 400。

### 9.2 桌面端为什么能拿到

PC 客户端登录后由 SDK 内部向 u8 换 token，换到的 token 同时用于两件事：

1. 塞给内嵌 webview：`GET ak-webview.hypergryph.com/autoChess/index?u8_token=<token>`；
2. 自己调协议接口：`GET as.hypergryph.com/u8/user/info/v2/agreement_version?token=<token>`（带 `X-DeviceId: <u8设备号>`）。

也就是说 **u8 token 只存在于这一次会话里**，本地不落明文（`login_cache` 里只有 hgsdk 的 `user_token`）。
想拿到它，只有两条路：抓一次包，或者逆 `U8SDK.dll` 的 extension 加密。

### 9.3 目前最省事的自动化：`tools/u8_watch.py`

```powershell
python tools\u8_watch.py --dir "<用户目录>\Desktop\新建文件夹" `
  --api http://127.0.0.1:8000 --user demo --password <站点密码> [--once] [--interval 15]
```

- 盯住导出目录（含子目录）的 `*request_*.txt`（自动解 gzip），从首行提取 `u8_token=` / `playerSummary?code=`；
- 用站点账号登录后 `POST /api/achv/session` 直接绑定，页面立刻更新；
- 幂等：`(文件, mtime)` 记在 `.local\u8_watch_state.json`，token 去重，重复跑输出 `新提交 0`；
- 仅标准库，cookie 用 `http.cookiejar`，写请求带 `Origin: http://localhost:5173`。

实测：

```
[+] 绑定成功 NM1AMRfK…(584)  昵称=示例博士 奖杯=470 uid=10000000
[=] 跳过重复 token NM1AMRfK…(584)
[*] 本轮结束：新提交 1，失败 0
```

所以现在的日常流程是：**游戏里点开一次成就页 → Reqable 导出到 `新建文件夹` → 脚本自动入库**，
不需要再从链接里抠参数。

### 9.4 hgsdk 登录态（静态可得，已解）

`LocalLow\Hypergryph\Arknights\sdk_data_70613…\login_cache`（MMKV）里有
`1000000000_user_token`，可用 `tools\hgsdk_unlock.py` 直接解出（key = `MD5(REG_GUID + salt)[:16]`，
AES-128-CFB128，IV 取 `.crc` 偏移 12）。它能：查账号信息（`user/info/v1/basic`）、换 oauth `grant`。
但它**换不出 u8 token**（见 9.1），所以只作为账号身份校验的旁路，不作为取数主路径。

`sdkdata\sdk_hgsdk_data_1` 与 `gameprotocol_cache` 用的是另一套密钥（24 组尝试全部失败），
且内容与 u8 token 无关，已放弃。

### 9.5 关于 Reqable「报告服务器」

Reqable 部分版本（含本机 3.3.12）没有「报告服务器」入口，所以页面上的「从 Reqable 抓包导入」按钮已移除。
后端 `/api/hg/report` 与 `/api/achv/import-capture` 仍保留（只认回环调用、HAR 整段正则捞 token），
但不再作为主路径。现在推荐：

1. 手动：游戏内打开成就页 → 复制链接 → 粘到页面「拿令牌」；
2. 自动：`python tools\u8_watch.py --dir <导出目录> --api http://127.0.0.1:8000 --user <账号> --password <密码>`。

### 9.6 全自动链路（**已打通，推荐**）

不需要抓包、不需要开游戏：

```powershell
python tools\auto_achv.py            # 解 hgsdk → grant → getToken → 绑定站点
```

内部三步：

1. `tools\hgsdk_unlock.py` 静态解出 hgsdk 登录态（MMKV：key = `MD5(REG_GUID+salt)[:16]`，IV 取 `.crc` 偏移 12）；
2. `POST /user/oauth2/v2/grant`（`{"type":1,"appCode":"7318def77669979d","token":"<hgsdk user_token>"}`）拿 **access_token**；
3. `POST /u8/user/v1/getToken`，`extension = {"code":"<access_token>","type":2,"isSuc":true}`（**type 必须是 2**），
   `appId=1 / channelId=1 / worldId=1 / subChannel="1" / platform=2`，`deviceId` 用 u8 设备号，
   `sign = HMAC-SHA1(91240f70…, 除 sign 外按键名升序 k=v 用 & 连接、值不编码)`。

关键常量来源：`U8Data\config\config.bin` 是 AES-256-CBC 密文，key/IV 硬编码在 `U8SDK.dll` 的 `.rdata`
（`0x180095290` / `0x1800952b0`），解密脚本 `tools\decrypt_u8_config.py`。

> 之前一直 `verify fail` 的根因：直接把 hgsdk token 塞进 `extension.code`，且 `type` 写成 1；
> 真实链路必须先走 `grant` 换 access_token，`extension.type` 用 2。
