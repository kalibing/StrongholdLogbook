# 卫戍协议 · 作战档案（Stronghold Logbook）

《明日方舟》卫戍协议（自动棋）的个人战绩档案：把导出的对局快照导入服务端，得到可筛选的对局记录、单局战报、盟约与干员统计。

仓库包含一个可以直接部署的小型全栈应用：

- **后端**：FastAPI + PostgreSQL + Alembic，负责登录、战绩导入队列与统计查询。
- **前端**：Vue 3 + TypeScript + Vite + Naive UI + ECharts，支持日间 / 夜间切换。
- **导入**：网页同步森空岛，API 接受 JSON 快照。独立 worker 异步写入，按 `(站点账号, 协议, 对局 ID)` 去重。

```
frontend (Vue 3)  ──/api/*──▶  FastAPI  ──▶  PostgreSQL
                                  ▲
                                  └── worker（导入写库）
浏览器 ← Caddy（静态文件 + 反向代理 + HTTPS）
```

## 功能

| 页面 | 内容 |
| --- | --- |
| 战绩总览 | 胜率、最近十局、盟约总层数 / 单项最高层数 / 金币 / 击杀 / 回合趋势，可按近 10 局、全部对局或按日期聚合；常用干员与常用盟约。 |
| 昨日战报 | 昨日胜负与对局明细、击破首领、盟约层数饼图、胜负对比与可选 AI 复盘。 |
| 对局记录 | 按协议期、模拟方式、难度、开局日期、战果筛选并分页；点开单局战报查看回合、击杀、金币、奖杯、盟约结算、首领和最终阵容与装备。 |
| 干员统计 | 出场局数、出场率、胜负与胜率，支持搜索和排序。 |
| 成就档案 | 绑定鹰角通行证（或粘贴成就页链接）后直连卫戍协议 `playerSummary`：六维成就、18 个称号、社交与获赞、策略纪录与**两种特殊标识**。见 [docs/achievements.md](docs/achievements.md)。 |
| 数据导入 | 同步森空岛战绩、复用已保存的鹰角 token，查看导入任务进度与错误。 |

| 通用 | 顶部导航带滑动指示器；筛选区使用 Naive UI 的下拉与范围日期选择；图表为 ECharts；主题可切换日间/夜间。 |

统一口径：疑似直接退出（0 回合、0 金币、0 击杀）默认排除，可在筛选里勾选纳入；日期一律按中国标准时间（UTC+8）归档。

昨日战报的饼图按盟约累计层数计算占比，胜负对比使用有对应数值的对局。需要启用 AI 分析时，在 API 进程环境（Compose 部署在 `.env`）设置 `LOGBOOK_AI_ENDPOINT`（兼容 Chat Completions 的完整 URL）、`LOGBOOK_AI_MODEL`，以及服务所需的 `LOGBOOK_AI_API_KEY`，再重启 API。点击「生成 AI 分析」才会发送战绩摘要。

## 目录结构

```
backend/
  logbook/            FastAPI 应用
    api.py            路由、登录会话、角色档案、导入上传
    records.py        导入格式校验（现代快照与旧版中文格式）、筛选 SQL
    stats.py          总览、趋势与干员统计
    hypergryph.py     鹰角通行证 → u8 token → playerSummary 取数
    achievements.py   成就档案归一化（六维 / 称号 / 社交 / 特殊标识）
    worker.py         导入队列消费进程（幂等 upsert）
    storage.py        存储适配层：PostgreSQL / SQLite 双后端
    sqlite_schema.py  SQLite 建表语句（与 Alembic 迁移逐列一致）
    errors.py         跨驱动的存储异常
    config.py         PUBLIC_ORIGIN 与数据库配置
    security.py       密码哈希与会话令牌
    admin.py          命令行账号管理
  migrations/         Alembic 迁移（PostgreSQL 表结构来源）
  tests/              pytest 用例（含 SQLite 端到端，无需外部数据库）
frontend/
  public/
    portraits/        干员头像（资源 ID 命名，来自旧版静态站）
    art/              盟约 / 首领 / 策略 / 装备图标
  src/
    views/            Overview / History / Operators / Archive
    components/       FiltersBar、TrendChart（原生 Canvas）、MatchReport
    assets.ts         由旧版资源生成的名称 → 图标映射
    icons.ts          图标缓存与头像路径
    api.ts            请求封装与资源加载
    style.css         设计系统（旧站结构 + PRTS 风格覆盖）
deploy/
  Caddyfile           静态托管 + /api 反代 + 安全响应头
  web.Dockerfile      前端构建产物打包
fixtures/             示例快照（导入演示与测试共用）
compose.yaml          PostgreSQL / API / worker / Caddy 编排
docs/ARCHITECTURE.md  架构与数据模型说明
docs/DATABASE.md      表结构、索引与方言映射
```

## 存储后端

| 后端 | 开关 | 表结构来源 | 适用 |
| --- | --- | --- | --- |
| PostgreSQL 17（默认） | `LOGBOOK_DB=postgres` | `alembic upgrade head` | 正式部署、多用户、多 worker |
| SQLite（单文件） | `LOGBOOK_DB=sqlite` | 启动时按 `sqlite_schema.py` 自动建表 | 本机开发与单机部署，零外部依赖 |

两个后端跑同一套业务代码：`storage.py` 负责改写占位符、`now()`、`FOR UPDATE` 与事务语义，并把 `uuid / timestamptz / jsonb / bytea` 映射到 `TEXT / INTEGER / TEXT / BLOB`。细节见 [docs/DATABASE.md](docs/DATABASE.md)。

## 本地运行

### 0. 准备

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
```

装好依赖后可以用一键脚本起本地环境（SQLite + API + worker + Vite）：

```powershell
pwsh -File scripts\dev.ps1              # 三个窗口：API 8000 / worker / 网页 5173
pwsh -File scripts\dev.ps1 -NoWorker    # 只要 API 与网页
```

Linux / macOS 用 `scripts/dev.sh`（`--no-worker` 同上），虚拟环境路径是 `.venv/bin/python`。

### 1. 后端（SQLite，最省事）

```powershell
$env:LOGBOOK_DB = 'sqlite'
$env:LOGBOOK_SQLITE = "$PWD\.local\logbook.sqlite3"
$env:PUBLIC_ORIGIN = 'http://localhost:5173'

cd backend
python -m logbook.admin create-user alice        # 交互输入，或设置 LOGBOOK_ADMIN_PASSWORD 免交互
python -m uvicorn logbook.api:app --port 8000
```

另开终端跑导入 worker（同一个 `LOGBOOK_*` 环境）：

```powershell
cd backend
python -m logbook.worker
```

### 1'. 后端（PostgreSQL，正式环境）

```powershell
$env:LOGBOOK_DB = 'postgres'
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_USER = 'logbook'
$env:POSTGRES_DB   = 'logbook'
$env:POSTGRES_PASSWORD = '<数据库密码>'
$env:PUBLIC_ORIGIN = 'http://localhost:5173'
$env:LOGBOOK_CREDENTIAL_KEY = '<已生成并保存的凭据密钥>'

cd backend
python -m alembic upgrade head
python -m logbook.admin create-user alice
python -m uvicorn logbook.api:app --port 8000
```

`PUBLIC_ORIGIN` 必须与浏览器地址栏的源一致：Vite 开发服务器是 `http://localhost:5173`，Compose 部署默认是 `http://localhost:8080`。写请求会校验 `Origin` 头，不一致会被拒绝（403）。

### 2. 前端

```powershell
cd frontend
npm ci
npm run dev        # http://localhost:5173，/api 自动代理到 127.0.0.1:8000
```

生产构建：`npm run build`（先跑 `vue-tsc` 类型检查，输出到 `frontend/dist`）。

### 3. Docker Compose（PostgreSQL，可选）

```powershell
Copy-Item .env.example .env       # 填写 POSTGRES_PASSWORD 和 LOGBOOK_CREDENTIAL_KEY
docker compose up -d --build      # http://localhost:8080
docker compose exec api python -m logbook.admin create-user alice
```

Compose 会先跑 `alembic upgrade head`（`migrate` 服务），再启动 API 与 worker；Caddy 只在 `HOST_BIND` 上发布端口，默认 `127.0.0.1`。对外提供 HTTPS 时把 `SITE_ADDRESS` 设成域名，Caddy 自动申请证书，并把 `PUBLIC_ORIGIN` 改成同一个 `https://` 源。

## Linux 服务器部署

服务端按 Linux 设计：镜像基于 Debian（`python:3.13-slim`、`caddy:2-alpine`），CI 也跑在 Ubuntu 上。只有「本机助手」是给用户电脑用的 Windows 程序，服务器只负责提供下载。

### 方式一：Docker Compose（推荐）

需要 Docker Engine 24+ 与 Compose 插件。域名先解析到服务器，防火墙放行 80 / 443（TCP，443 另放 UDP 以启用 HTTP/3）。

```bash
git clone <仓库地址> /opt/logbook && cd /opt/logbook
scripts/init-env.sh logbook.example.com   # 生成 .env：随机数据库密码与凭据密钥，权限 600
docker compose up -d --build
docker compose exec api python -m logbook.admin create-user alice
```

- `init-env.sh` 不带参数时生成仅本机可访问的 `http://localhost:8080` 配置；带域名时监听 `0.0.0.0:80/443`，`PUBLIC_ORIGIN` 设为 `https://域名`，Caddy 自动申请证书。
- `.env` 里的 `LOGBOOK_CREDENTIAL_KEY` 务必另外备份；丢失后已保存的森空岛 / 成就令牌无法解密，需要用户重新绑定。
- 本机助手：在 Windows 上运行 `scripts/build-agent.ps1`，把生成的 `ArknightsAchvAgent.exe` 拷到服务器 `deploy/download/`，无需重建镜像。目录里没有文件时下载地址返回 404。
- 升级：`git pull && docker compose up -d --build`，`migrate` 服务会先执行数据库迁移。
- 备份：`docker compose exec -T db pg_dump -U logbook -Fc logbook > logbook-$(date +%F).dump`。

Compose 里的安全布置：

| 项 | 做法 |
| --- | --- |
| 网络 | `data` 为内部网络（无出网），只有 db / migrate / api / worker；`edge` 连接 Caddy 与 api。只有 Caddy 对宿主机发布端口。 |
| 容器 | api / worker / migrate / Caddy 均 `read_only`、`no-new-privileges`、`cap_drop: ALL`（Caddy 只保留 `NET_BIND_SERVICE`），后端以 UID 10001 运行。 |
| 日志 | json-file 轮转，单容器最多 30 MB。 |
| 来源 IP | uvicorn 启用 `--proxy-headers`，从 Caddy 的 `X-Forwarded-For` 取真实客户端 IP 用于登录限速；api 不对外发布端口，客户端无法绕过 Caddy 伪造该头。 |

### 方式二：裸机 + systemd

适合不想装 Docker 的小机器。以 Debian / Ubuntu 为例：

```bash
sudo apt install python3 python3-venv fonts-noto-cjk caddy postgresql   # SQLite 部署可不装 postgresql
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin logbook
sudo git clone <仓库地址> /opt/logbook
sudo python3 -m venv /opt/logbook/.venv
sudo /opt/logbook/.venv/bin/pip install -r /opt/logbook/backend/requirements.txt

# 环境变量（属主 root、权限 600，systemd 读取后再以 logbook 用户启动服务）
sudo install -d -m 755 /etc/logbook
sudo install -m 600 /opt/logbook/deploy/systemd/logbook.env.example /etc/logbook/logbook.env
sudoedit /etc/logbook/logbook.env

# PostgreSQL：建库后执行迁移（SQLite 跳过这一步，启动时自动建表）
sudo -u postgres createuser -P logbook && sudo -u postgres createdb -O logbook logbook
# 与服务相同的用户、环境与目录执行一次性命令
lb() { sudo systemd-run --pty --wait --collect -q -p User=logbook -p EnvironmentFile=/etc/logbook/logbook.env   -p WorkingDirectory=/opt/logbook/backend -p StateDirectory=logbook /opt/logbook/.venv/bin/python -m "$@"; }
lb alembic upgrade head

sudo cp /opt/logbook/deploy/systemd/logbook-{api,worker}.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now logbook-api logbook-worker

# 前端：任意机器上 npm ci && npm run build，把 frontend/dist 拷到 /var/www/logbook
# Caddy：改好 caddy-logbook.conf 里的域名后
sudo install -d /etc/systemd/system/caddy.service.d
sudo cp /opt/logbook/deploy/systemd/caddy-logbook.conf /etc/systemd/system/caddy.service.d/logbook.conf
sudo cp /opt/logbook/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload && sudo systemctl restart caddy
```

- API 只监听 `127.0.0.1:8000`，由 Caddy 反代；同一份 `deploy/Caddyfile` 通过 `API_UPSTREAM` / `SITE_ROOT` 环境变量切换 Compose 与裸机。
- 两个 unit 带完整的 systemd 沙箱（`ProtectSystem=strict`、`NoNewPrivileges`、系统调用过滤、无任何 capability），唯一可写目录是 `/var/lib/logbook`（权限 700）。SQLite 部署把 `LOGBOOK_SQLITE` 指到该目录。
- 建账号：`lb logbook.admin create-user alice`（`lb` 为上面定义的 shell 函数，交互输入密码）。
- 本机助手 exe 放在 `/var/www/logbook/download/`。
- 日志：`journalctl -u logbook-api -u logbook-worker -f`。

## 成就档案（鹰角通行证）

「成就档案」页直连卫戍协议 H5 的 `playerSummary` 接口，把成就页上的内容搬进本站：

- **六维成就**：盟约理解 / 补救能力 / 人力调度 / 装备活用 / 资金管理 / 领袖挑战（0–100）
- **18 个称号**：每维 3 个（特殊 / T1 / T2）与数值
- **社交**：已获赞、好友数、特别关注、最常共同游玩的队友与胜场
- **策略与分队纪录**：TOP3 分队 + **两种特殊标识**（`master` 精通角标 / `base` 基础标识）

网页通过 [Windows 本机助手](agent/README.md) 绑定成就档案。已登录的账号也可以用游戏内成就链接或令牌调用 `POST /api/achv/session`。

链路、字段字典、两种标识的判定依据与已知限制见 [docs/achievements.md](docs/achievements.md)。
令牌按天失效，过期后页面继续展示上次快照并提示。

## 站内通知

侧栏左下角的铃铛显示未读数，点开即可查看并全部标为已读。通知是纯文本，网页没有写通知的接口，只能由站长在服务端发布：

```bash
python -m logbook.admin announce "维护通知" '今晚 23:00 停机维护
期间无法导入战绩'   # 全站公告，
 表示换行
python -m logbook.admin notify 123456789 "账号提醒" "……"                          # 发给单个账号
python -m logbook.admin list-notices                                              # 最近 50 条及其 ID
python -m logbook.admin remove-notice <通知 ID>
```

Compose 部署在前面加 `docker compose exec api`。新用户注册时会自动收到一条欢迎通知（说明用户名即 QQ 号、密码不会再次显示）。标题最多 60 字，正文最多 2000 字。

## 昨日战报图片

`GET /api/daily-review/image` 返回当前登录账号的战报 PNG（宽 1080，高度随内容变化），口径与网页「昨日战报」一致：北京时间按开局时间归档，默认排除疑似直接退出。

- 不带参数取北京时间的昨天；`?day=2026-11-20` 取指定日期（标题会写成「每日战报」）。
- 需要登录会话；响应带 `Cache-Control: private, no-store`。
- 渲染用 Pillow，服务器必须有中文字体：Docker 镜像已安装 `fonts-noto-cjk`；裸机部署可安装同名包，或用 `LOGBOOK_CARD_FONT` / `LOGBOOK_CARD_FONT_BOLD` 指定字体文件。找不到字体时返回 503。
- 战报里的策略名由 `backend/logbook/bands.py` 换算（森空岛记录存的是分队干员名），该表从 `frontend/src/bands.ts` 生成，两边需同步。

```powershell
curl.exe -b cookies.txt -o daily.png "http://localhost:8000/api/daily-review/image"
```

## 昵称与头像

登录账号（`username`）只用于登录、不可修改；页面显示的是昵称，没设置时回落到账号名。两者分开存在 `user_profiles` 表（PostgreSQL 迁移 `0004_user_profiles`）。

- 昵称：去掉首尾空白、合并连续空白后 1–16 个字，不允许控制字符；传空串或 `null` 清除。
- 头像：`PUT /api/profile/avatar`，`Content-Type` 必须是 `image/*`，请求体为图片字节，最大 2 MB、边长不超过 4096。服务端只接受 PNG / JPEG / WebP / GIF，按 EXIF 摆正后居中裁成 256×256 PNG 再入库，原图与元数据不保存。
- 头像只对本人可读；地址带版本号（`?v=`），换头像后地址会变，所以响应可以长缓存（`Cache-Control: private, max-age=31536000, immutable`）。

## 导入战绩

在「数据导入」页同步森空岛，或通过 API 补录 JSON 快照：

```powershell
curl.exe -X POST "http://localhost:8000/api/imports" `
  -H "Content-Type: application/json" `
  -H "Origin: http://localhost:5173" `
  -b cookies.txt --data-binary "@fixtures/sample-snapshot.json"
```

快照结构（`fixtures/sample-snapshot.json` 可直接导入试用）：

```jsonc
{
  "operators": { "char_002_amiya": { "name": "阿米娅" } },   // 可选字典
  "equipment": { "chess_item_1_01": { "name": "锋锐之矛" } }, // 可选字典
  "matches": [
    {
      "external_id": "10000000-act3autochess-1794132482",
      "played_at": "2026-11-20T21:12:05+08:00",  // 必须带时区
      "protocol": "V3_1",                        // 默认规程协议 1
      "play": "独立模拟",
      "difficulty": "规程等级 8",
      "result": "win",                           // win | loss
      "scenario": "维多利亚分队", "strategy": "精英作战", "initiator": "队友",
      "rounds": 14, "kills": 138, "coins": 96,
      "sync_count": 7, "trophies": 42, "duration_seconds": 1620,
      "bonds": [{ "name": "维多利亚", "layers": 6 }],
      "squad": [{ "id": "char_1012_skadi2", "name": "浊心斯卡蒂", "items": ["chess_item_4_09"] }],
      "bosses": ["霜星"]
    }
  ]
}
```

- 也接受顶层就是数组的写法，或旧版中文键（`时间 / 方式 / 模式 / 结果 / 回合 / 击杀 / 金币 / 盟约 / 干员 / 阵容 / 首领`），旧格式会按「时间 + 方式 + 模式」生成稳定 ID 用于去重。
- 省略 `suspected_exit` 时按 0 回合、0 击杀、0 金币推断；省略 `operators` 时由 `squad` 派生。
- 单文件不超过 8 MB、1–5000 局；同一账号同时最多 3 个待处理导入任务。
- 重复导入会更新同一局。新增数据中缺失的字段保留已有值，明确上报的零值和空列表会更新。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 存活与数据库连通性 |
| GET / POST / DELETE | `/api/session` | 读取当前登录（含昵称、头像地址）、登录、退出 |
| GET | `/api/notifications` | 站内通知（全站公告 + 发给本人的通知，最近 50 条）与未读数 |
| POST | `/api/notifications/read` | 标记已读：`{"ids": [...]}`，省略 `ids` 表示全部 |
| GET | `/api/registration` | 是否开放注册、是否需要邀请码 |
| POST | `/api/register` | 按 QQ 号注册（`{"qq": "…", "invite_code": "…"}`），返回账号与一次性显示的随机密码，并直接登录 |
| GET / PATCH | `/api/profile` | 个人主页资料 / 修改昵称（`{"display_name": "…"}`，空串清除） |
| GET / PUT / DELETE | `/api/profile/avatar` | 读取 / 上传（请求体为图片字节）/ 移除头像 |
| GET | `/api/career` | 生涯档案：最高通关、连胜、生涯纪录、近一年活跃度 |
| GET | `/api/facets` | 可用协议期、方式、难度 |
| GET | `/api/overview` | 总览与趋势，`scope=recent\|all\|day` |
| GET | `/api/distribution` | 按模拟方式和难度汇总对局 |
| GET | `/api/matches` | 分页对局列表，`result=win\|loss`、`page`、`limit` |
| GET | `/api/matches/{match_id}` | 单局战报 |
| GET | `/api/operators` | 干员统计，`sort=count\|win\|name`、`q` |
| GET | `/api/strategies` | 完整策略列表 |
| GET / POST | `/api/imports` | 导入任务列表 / 上传快照 |
| POST | `/api/imports/skland` | 同步森空岛 |
| GET / DELETE | `/api/imports/skland/token` | 查询当前账号是否已保存令牌 / 清除令牌 |

筛选参数在总览、生涯档案、对局、干员与策略几处通用：`protocol`、`play`、`difficulty`、`start`、`end`、`include_exits`。

## 测试与检查

```powershell
.\.venv\Scripts\python.exe -m pytest          # 后端：135 个用例，无需外部数据库
cd frontend; npm run typecheck                # vue-tsc
cd frontend; npm run build                    # 生产构建
```

`backend/tests` 覆盖导入格式（现代 / 旧版 / 异常）、统计口径、筛选 SQL、`PUBLIC_ORIGIN` 校验、会话与密码、上传防护、worker 的成功 / 失败状态迁移，以及 SQLite 后端的完整链路（登录 → 建档 → 上传 → worker 写库 → 查询 → 删除）和「SQLite 建表语句与 Alembic 迁移逐列一致」的对比。CI 在 `.github/workflows/ci.yml` 里跑同样的命令。

本机已验证（SQLite 后端 + Vite 开发服务器）：

| 步骤 | 结果 |
| --- | --- |
| `POST /api/session` 登录 | 200，Cookie 下发 |
| 建档 → 上传 `fixtures/sample-snapshot.json` | 202，`total=6` |
| worker 消费导入任务 | `status=done`，`processed=6`，`completed_at` 为当前时间 |
| `GET /overview?scope=all` | `matches=5 wins=3 excluded=1 max_layers=11 total_coins=451` |
| `GET /matches?limit=4` | `total=5 pages=2`，分队、盟约层数、时间正确 |
| `GET /operators` | `with_squad=5`，出场排序正确 |
| `http://localhost:5173/api/health` | Vite 代理转发正常

## 数据来源说明

对局数据来自本人账号在森空岛可见的战绩。采集脚本、原始抓包、会话凭据和个人战绩文件都只保留在本地，不进入本仓库；`fixtures/` 里是与真实账号无关的示例数据。正式版计划接入官方授权绑定与增量同步，详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 安全要点

- 密码用 Argon2 哈希，会话令牌只存 SHA-256 摘要；Cookie 为 `HttpOnly` + `SameSite=Strict`，HTTPS 下自动加 `__Host-` 前缀与 `Secure`。
- 注册默认关闭（`LOGBOOK_REGISTRATION=off`），可设为 `open` 或 `invite`（配合 `LOGBOOK_INVITE_CODE`，至少 8 位）。注册只填 QQ 号（5–11 位数字），用户名即 QQ 号；密码是 16 位随机字符，只在注册响应里出现一次，库里只存 Argon2 哈希。注意网页无法验证 QQ 号归属，公开站点建议用邀请码。
- 注册按来源 IP 限制：同一 IP（IPv6 按 /64 网段归并）24 小时内最多注册 2 个账号；失败尝试（QQ 号已注册、邀请码错误）每小时最多 10 次；全站每小时最多 20 个新账号。
- 按账号限额（24 小时滑动窗口，只有成功的调用计数）：AI 复盘、战报图片、森空岛同步各每天 2 次；成就绑定每小时 20 次。限速计数在 API 进程内存中，重启后清零。
- 同一账号连续 8 次密码错误锁定 15 分钟；同一来源 IP 1 小时内失败 5 次后拒绝继续尝试，直到最早那次失败满 1 小时（防止换账号名撞库）；登录失败分支仍会执行一次哈希校验以避免时序泄露。
- 所有写请求校验 `Origin`，所有响应带 `Cache-Control: no-store`。Caddy 追加严格 CSP（脚本只允许同源文件，不允许内联脚本）、HSTS、`X-Frame-Options`、`Permissions-Policy`、COOP / CORP 等头。
- 任何请求体在后端统一限制为 9 MB（Caddy 再兜底 10 MB），上传体积、局数和待处理任务数另有各自的上限。导入由独立进程写库。
- 部署层的隔离（内部网络、只读容器、systemd 沙箱）见「Linux 服务器部署」。

### 凭据密钥

森空岛复用令牌和成就令牌分别按站点账号及用途用 AES-256-GCM 加密入库。已有明文行会在 API 首次启动时自动转换，原有战报和成就快照保留。升级时一同更新 API 与 worker。

PostgreSQL 部署应生成一次随机密钥并通过受限的 `LOGBOOK_CREDENTIAL_KEY` 环境变量交给 API。Compose 可从本机的 `.env` 读取该值。

```powershell
python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

密钥应与数据库备份分开保管，恢复时使用原密钥。本地 SQLite 在未配置环境变量时会用数据库旁的 `<数据库文件名>.credentials.key`，首次启动自动生成。将密钥文件和数据库一起限制为运行账号可读，分别备份。升级前的备份或存储快照可能含原始令牌，按敏感数据保管。怀疑令牌泄露时应撤销上游授权并重新绑定。

## 界面设计

界面按旧版静态站的结构重做，再叠加 PRTS 风格的视觉收紧：

| 层 | 说明 |
| --- | --- |
| 结构 | 顶部导航 + 英雄区横幅；总览为「作战表现 / 盟约与资金」并排 + 双列趋势图；对局为结算表 + 战报弹窗；干员为出场榜表格。 |
| 视觉 | 近黑底、锐角（2–4px）、发丝级描边、区块标题左侧强调条、表头小写字距、数字用压缩字体对齐。 |
| 图表 | 原生 Canvas 手绘：网格、折线、胜圆点 / 负菱形、数值标注、盟约名与图标、悬停回读。 |
| 资源 | `frontend/public/portraits`（125 张 180×180 干员头像）与 `frontend/public/art`（盟约 / 首领 / 策略 / 装备图标）来自旧站；`src/assets.ts` 提供名称到图标的映射，缺图时组件自动隐藏。
| 干员卡 | 构图取自旧快照（6px 圆角、110px 高、头像 `height:104%` 右贴边、文字压底 `24px 9px 8px`），配色跟随本站深色主题。 |

导入时会把装备 ID 按快照里的 `equipment` 字典解析成中文名，因此在战报里直接显示「疾行靴」这类名称；旧版中文快照同样处理。

头像缺失时用 `node scripts/fetch-portraits.mjs <干员ID>` 从公开的明日方舟资源镜像（默认 Aceship `Arknight-Images`）补齐 180×180 头像；`--from online/dist/operators.json` 可批量补全整个字典。
