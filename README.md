# 止危——开源的结构健康监测平台后端

> 止危结构健康监测（Structural Health Monitoring）平台后端服务
> 版本：**0.8.0** · 文档同步于 2026-08-13

面向建筑结构监测场景，提供三维数字孪生所需的实时数据底座、多协议设备接入、高频时序数据治理与可扩展的分析引擎。全异步架构，基于 FastAPI + TimescaleDB + Redis。

## 核心能力

- **多协议设备接入**：协议适配器插件化（Modbus / MQTT / OPC-UA / HTTP JSON …），边缘网关与云端共用同一套接口契约
- **高频时序数据**：1000+ 测点级规模，asyncpg COPY 批量写入，TimescaleDB hypertable + 7 天保留策略
- **统一 RBAC**：管理员 / 普通用户两级，用户-子项授权控制数据访问范围
- **实时推送**：Redis Pub/Sub → WebSocket 广播，前端按子项订阅
- **模块化分析引擎**：FFT / 阈值告警 / 趋势预测等算法以插件形式注册

## 技术栈

| 层级 | 选型 |
|------|------|
| API 框架 | FastAPI（asyncio，Pydantic v2） |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| 时序存储 | PostgreSQL 15 + TimescaleDB 2.x |
| 缓存/队列 | Redis 7 |
| 对象存储 | MinIO（S3 兼容） |
| 异步任务 | Celery 4 队列（alerts / analysis / reports / maintenance） |
| 认证 | JWT (PyJWT) + bcrypt（线程池避免阻塞事件循环） |
| 测试 | pytest + pytest-asyncio，httpx AsyncClient |
| Lint | ruff（E/F/I/UP/B/ASYNC） |

## 快速开始

环境要求：Python ≥ 3.11、Docker Desktop（已开启 WSL 集成）、uv。

```bash
# 1. 安装依赖
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install -r requirements.txt -i https://mirrors.ustc.edu.cn/pypi/simple

# 2. 启动基础设施
docker compose up -d postgres redis minio

# 3. 应用数据库迁移 + TimescaleDB 初始化
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.init_db

# 4. 启动 API
.venv/bin/python -m uvicorn app.main:app --reload
# 浏览 http://localhost:8000/docs 看交互式 API 文档

# 5. 首次部署引导：创建第一个 admin（users 表为空时生效）
.venv/bin/python -m scripts.init_admin --base-url http://localhost:8000
# 完成后使用 admin/<your-password> 登录
```

Docker 用户可在 `docker-compose.yml` 的 `api` 服务设置 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 环境变量，entrypoint 会自动调 `init_admin.py`（生产推荐用 Docker Secrets）。

## 文档导航

- [docs/index.md](docs/index.md) — 文档总目录
- **开发者**
  - [架构设计](docs/architecture.md)
  - [开发环境](docs/development/setup.md)
  - [数据库与迁移](docs/development/database.md)
  - [模块技术说明](docs/development/modules.md)
  - [代码规范](docs/development/coding-standards.md)
  - [测试](docs/development/testing.md)
  - [模拟与冒烟（无硬件）](docs/development/simulation.md)
  - [部署](docs/development/deployment.md)
- **使用者**
  - [API 概览与鉴权](docs/api/overview.md)
  - [认证](docs/api/auth.md)
  - [子项](docs/api/projects.md)
  - [设备](docs/api/devices.md)
  - [测点](docs/api/points.md)
  - [传感器](docs/api/sensors.md)
  - [通道](docs/api/channels.md)
  - [协议](docs/api/protocols.md)
  - [时序数据](docs/api/data.md)
  - [告警](docs/api/alerts.md)
  - [大屏](docs/api/dashboard.md)
  - [分析](docs/api/analysis.md)
  - [通知](docs/api/notifications.md)
  - [首次部署引导（setup）](docs/api/setup.md)
  - [平台元数据](docs/api/platform.md)
  - [用户管理](docs/api/users.md)

## 子项状态

`v0.8.0` — 在 `v0.5.0` 基础上补齐**首次部署引导**：

- 后端 `GET/POST /api/v1/setup/*` 端点（无认证 + 严格 `users` 表空守卫）：前端 setup 页面或 CLI 创建首个 admin
- 密码策略：≥8 字符 + 至少一个字母 + 一个数字（Pydantic schema + service 双重校验）
- `scripts/init_admin.py` 替换 `scripts/seed.py`（已删除）：交互 / env 双模式，幂等
- `docker/entrypoint.sh` + compose 改 entrypoint：env 传入 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 时自动 init

`v0.8a` — **术语重构**：`project` 统一改名 `subitem`（子项）。数据库 `projects/user_projects` 重命名为 `subitems/user_subitems`，API 路径 `/projects` → `/subitems`，Redis 频道 `project:{id}` → `subitem:{id}`。

`v0.8b` — **多通道数据模型**：新增 `sensor`（传感器）/ `channel`（通道）/ `reading`（时序读数）三层，形成 `user → subitem → device → point → sensor → channel → readings` 七层树状拓扑：

- `point` 收敛为物理位置（移除 unit/sampling_rate/alert_rules）
- `channel` 承载单位、采样率、告警规则，一个 sensor 可有 1-N 个 channel，每个 channel 对应一组时序数据
- `readings`（替代原 `sensor_raw`/`sensor_feature`）按 channel 存储，ingest 改用 `channel_code` 寻址
- 新增 `/sensors`、`/channels` 路由与 service；告警、分析、实时推送全部下沉到 channel 粒度

`v0.5.0` 之前的累计能力：WS 子项权限校验、告警抑制（per-rule suppress_seconds）、多渠道通知（Webhook + Email）、modbus_tcp/mqtt 协议适配器、FFT 分析 + Celery `analysis` + MinIO、JWT 认证、阈值告警 + WebSocket 推送、TimescaleDB hypertable。

尚未实现：每子项通知通道配置（v0.7+）、钉钉/企微/Slack 专属 payload、modbus_rtu/opcua 适配器、3D 模型上传、模态/趋势预测分析插件、首次登录强制改密码、zxcvbn 密码强度评分、完整边缘网关进程、审计日志。