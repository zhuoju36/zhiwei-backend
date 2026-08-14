# 止危——开源的结构健康监测平台后端

> 止危结构健康监测（Structural Health Monitoring）平台后端服务
> 版本：**0.9.2** · 文档同步于 2026-08-14

面向建筑结构监测场景，提供三维数字孪生所需的实时数据底座、多协议设备接入、高频时序数据治理与可扩展的分析引擎。全异步架构，基于 FastAPI + TimescaleDB + Redis。

## 核心能力

- **多协议设备接入**：协议适配器插件化（Modbus / MQTT / OPC-UA / HTTP JSON …），边缘网关与云端共用同一套接口契约；**DTU 透传监听**（Modbus RTU over TCP）由独立进程 `dtu_server` 接入
- **高频时序数据**：1000+ 测点级规模，asyncpg COPY 批量写入，TimescaleDB hypertable + 7 天保留策略
- **统一 RBAC**：管理员 / 普通用户两级，用户-项目授权控制数据访问范围
- **实时推送**：Redis Pub/Sub → WebSocket 广播，前端按项目订阅
- **3D 模型管理**：项目多模型上传（OBJ/STL/PLY/glTF/GLB），后台自动转 GLB 供数字孪生加载
- **模块化分析引擎**：FFT / 基础统计等算法以插件形式注册，社区可经 entry_points 接入自定义算法

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
  - [项目](docs/api/projects.md)
  - [设备](docs/api/devices.md)
  - [传感器](docs/api/sensors.md)
  - [通道](docs/api/channels.md)
  - [协议](docs/api/protocols.md)
  - [时序数据](docs/api/data.md)
  - [告警](docs/api/alerts.md)
  - [大屏](docs/api/dashboard.md)
  - [分析](docs/api/analysis.md)
  - [3D 模型](docs/api/models.md)
  - [通知](docs/api/notifications.md)
  - [首次部署引导（setup）](docs/api/setup.md)
  - [平台元数据](docs/api/platform.md)
  - [用户管理](docs/api/users.md)

## 项目状态

`v0.8.0` — 在 `v0.5.0` 基础上补齐**首次部署引导**：

- 后端 `GET/POST /api/v1/setup/*` 端点（无认证 + 严格 `users` 表空守卫）：前端 setup 页面或 CLI 创建首个 admin
- 密码策略：≥8 字符 + 至少一个字母 + 一个数字（Pydantic schema + service 双重校验）
- `scripts/init_admin.py` 替换 `scripts/seed.py`（已删除）：交互 / env 双模式，幂等
- `docker/entrypoint.sh` + compose 改 entrypoint：env 传入 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 时自动 init

`v0.8a` — **术语调整**：监测范围术语一度从 `project` 改为 `subitem`（v0.8a），v0.9 回退为 `project`（见 v0.9 小节）。

`v0.8b` — **多通道数据模型**：新增 `sensor` / `channel` / `reading` 分层（v0.9 起 point 并入 sensor，见下）：

- `channel` 承载单位、采样率、告警规则，一个 sensor 可有 1-N 个 channel，每个 channel 对应一组时序数据
- `readings`（替代原 `sensor_raw`/`sensor_feature`）按 channel 存储，ingest 改用 `channel_code` 寻址
- 新增 `/sensors`、`/channels` 路由与 service；告警、分析、实时推送全部下沉到 channel 粒度

`v0.8c` — **3D 模型上传与转换**：一个项目可上传多个模型（OBJ/STL/PLY/glTF/GLB → GLB）：

- 新增 `3d_models` 表 + `/api/v1/models/*` 路由（上传 / 列表 / 详情 / GLB 下载 / 删除）
- Celery `reports` 队列后台转换（trimesh），`scripts/model_convert.py` 可独立 CLI 转换
- IFC（BIM 格式）暂不支持，需 v0.9+ Blender/IfcOpenShell 转换器
- 移除 `projects.model_file_key` 冗余列，模型统一走 `3d_models` 表

`v0.8d` — **分析插件接口 v2（面向社区）**：

- `AnalysisPlugin` 契约升级：自描述元信息（`params_schema` 供前端动态表单）+ `AnalysisInput`/`AnalysisOutput` 显式数据结构，替代裸 dict 与 `_internal_*` 魔法字段
- 插件 = 纯计算单元（数组 + 参数 → 摘要/附件），不接触数据库与实时流；阈值告警保持系统基础功能（数据驱动，不插件化）
- **双层注册表**：内置目录扫描 + Python entry_points（组 `shm_analyzers`），社区 `pip install` 即接入，含版本守卫（`plugin_api_version`）
- **多通道支持**：`input_channels=N` 声明式拉取（限同项目），为模态分析铺路
- 新增 `GET /api/v1/analysis/plugins` 元信息接口；内置 `statistics` 示例插件；社区开发指南见 `docs/development/plugin-dev.md`

`v0.9.0` — **DTU 监听接入（拓扑 A：DTU 直连云）**：

- 独立进程 `app/dtu_server`（同镜像、docker-compose 一个 service）：接收 DTU 透传的 Modbus RTU 帧，解析后经 `data_service.batch_ingest` 直写时序库 + Redis 实时推送 + 告警，与 API 进程完全解耦
- 新增监听型适配器契约（`supports_listen` + `decode_stream`，不破坏现有主动轮询适配器）与 `modbus_rtu_over_tcp` 协议（自研 CRC16 帧解析，粘包/半包/坏帧处理）
- 一监听端口 = 一台设备（`Device.config.port`）；缓冲队列攒批入库 + 优雅停机排空，DTU 断线续传兜底

`v0.9.0` — **数据模型重构 + DTU 监听接入**：

- **point 与 sensor 合一**：实际一测点一传感器，删除 `points` 表，`sensor` 挂 device 下并携带位置字段（position / sensor_name）+ 仪器元数据；拓扑变为六层 `user → project → device → sensor → channel → readings`
- **术语回退**：`subitem` 改回 `project`（v0.8a 曾改名，v0.9 回退），表 `projects/user_projects`、Redis 频道 `project:{id}`
- **DTU 监听接入（拓扑 A）**：独立进程 `app/dtu_server`（同镜像、compose 一个 service）：接收 DTU 透传的 Modbus RTU 帧，解析后直写时序库 + Redis 实时推送 + 告警，与 API 进程完全解耦
- 新增监听型适配器契约（`supports_listen` + `decode_stream`）与 `modbus_rtu_over_tcp` 协议（自研 CRC16 帧解析）；缓冲队列攒批入库 + 优雅停机，DTU 断线续传兜底

`v0.5.0` 之前的累计能力：WS 项目权限校验、告警抑制（per-rule suppress_seconds）、多渠道通知（Webhook + Email）、modbus_tcp/mqtt 协议适配器、FFT 分析 + Celery `analysis` + MinIO、JWT 认证、阈值告警 + WebSocket 推送、TimescaleDB hypertable。

尚未实现：每项目通知通道配置（v0.7+）、钉钉/企微/Slack 专属 payload、modbus_rtu/opcua 适配器、IFC→GLB 转换（Blender/IfcOpenShell）、模态/趋势预测分析插件、首次登录强制改密码、zxcvbn 密码强度评分、完整边缘网关进程、审计日志。