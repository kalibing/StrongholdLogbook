# 卫戍协议 · 作战档案（Stronghold Logbook）

《明日方舟》卫戍协议（自动棋）的个人战绩档案：把导出的对局快照导入服务端，得到可筛选的对局记录、单局战报、盟约与干员统计。

仓库包含一个可以直接部署的小型全栈应用：

- **后端**：FastAPI + PostgreSQL + Alembic，负责登录、角色档案、战绩导入队列与统计查询。
- **前端**：Vue 3 + TypeScript + Vite + Chart.js，深色单页界面，三页数据视图加一页档案管理。
- **导入**：网页上传 JSON 快照，写入由独立 worker 进程异步完成，同一局按 `(角色, 协议, 对局 ID)` 幂等。

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
| 对局记录 | 按协议期、模拟方式、难度、开局日期、战果筛选并分页；点开单局战报查看回合、击杀、金币、奖杯、盟约结算、首领和最终阵容与装备。 |
| 干员统计 | 出场局数、出场率、胜负与胜率，支持搜索和排序。 |
| 档案管理 | 创建 / 重命名 / 删除角色档案，上传战绩 JSON，查看导入任务进度与错误。 |

统一口径：疑似直接退出（0 回合、0 金币、0 击杀）默认排除，可在筛选里勾选纳入；日期一律按中国标准时间（UTC+8）归档。

## 目录结构

```
backend/
  logbook/            FastAPI 应用
    api.py            路由、登录会话、角色档案、导入上传
    records.py        导入格式校验（现代快照与旧版中文格式）、筛选 SQL
    stats.py          总览、趋势与干员统计
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
  src/
    views/            Overview / History / Operators / Archive
    components/       FiltersBar、TrendChart、MatchReport、Feedback
    api.ts            请求封装与资源加载
    style.css         设计系统
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
Copy-Item .env.example .env       # 填写 POSTGRES_PASSWORD
docker compose up -d --build      # http://localhost:8080
docker compose exec api python -m logbook.admin create-user alice
```

Compose 会先跑 `alembic upgrade head`（`migrate` 服务），再启动 API 与 worker；Caddy 只在 `HOST_BIND` 上发布端口，默认 `127.0.0.1`。对外提供 HTTPS 时把 `SITE_ADDRESS` 设成域名，Caddy 自动申请证书，并把 `PUBLIC_ORIGIN` 改成同一个 `https://` 源。

## 导入战绩

在「档案管理」页选择 JSON 文件即可，也支持直接调用接口：

```powershell
curl.exe -X POST "http://localhost:8000/api/roles/$ROLE_ID/imports" `
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
- 单文件不超过 8 MB、1–5000 局；同一角色同时最多 3 个待处理导入任务。
- 重复导入同一局不会新增记录，只会覆盖该局的字段。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 存活与数据库连通性 |
| GET / POST / DELETE | `/api/session` | 读取当前登录、登录、退出 |
| GET / POST | `/api/roles` | 角色档案列表 / 新建（上限 20 个） |
| PATCH / DELETE | `/api/roles/{role_id}` | 重命名 / 删除档案（级联删除战绩） |
| GET | `/api/roles/{role_id}/facets` | 可用协议期、方式、难度 |
| GET | `/api/roles/{role_id}/overview` | 总览与趋势，`scope=recent\|all\|day` |
| GET | `/api/roles/{role_id}/matches` | 分页对局列表，`result=win\|loss`、`page`、`limit` |
| GET | `/api/roles/{role_id}/matches/{match_id}` | 单局战报 |
| GET | `/api/roles/{role_id}/operators` | 干员统计，`sort=count\|win\|name`、`q` |
| GET / POST | `/api/roles/{role_id}/imports` | 导入任务列表 / 上传快照 |

筛选参数在总览、对局、干员三处通用：`protocol`、`play`、`difficulty`、`start`、`end`、`include_exits`。

## 测试与检查

```powershell
.\.venv\Scripts\python.exe -m pytest          # 后端：80 个用例，无需外部数据库
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
| `PATCH / DELETE /api/roles/{id}` | 200 / 204，级联清理后列表为空 |
| `http://localhost:5173/api/health` | Vite 代理转发正常

## 数据来源说明

对局数据来自本人账号在森空岛可见的战绩。采集脚本、原始抓包、会话凭据和个人战绩文件都只保留在本地，不进入本仓库；`fixtures/` 里是与真实账号无关的示例数据。正式版计划接入官方授权绑定与增量同步，详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 安全要点

- 密码用 Argon2 哈希，会话令牌只存 SHA-256 摘要；Cookie 为 `HttpOnly` + `SameSite=Strict`，HTTPS 下自动加 `__Host-` 前缀与 `Secure`。
- 同一账号连续 8 次密码错误锁定 15 分钟；登录失败分支仍会执行一次哈希校验以避免时序泄露。
- 所有写请求校验 `Origin`，所有响应带 `Cache-Control: no-store`，Caddy 追加 CSP、`X-Frame-Options` 等头。
- 上传体积、局数、待处理任务数和档案数量都有上限；导入在独立进程写库，接口不阻塞。
