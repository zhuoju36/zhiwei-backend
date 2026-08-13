# SHM 平台后端

> 结构健康监测（Structural Health Monitoring）平台后端服务
> 版本：**0.2.0** · 文档同步于 2026-08-13

面向建筑结构监测场景，提供三维数字孪生所需的实时数据底座、多协议设备接入、高频时序数据治理与可扩展的分析引擎。全异步架构，基于 FastAPI + TimescaleDB + Redis。

## 核心能力

- **多协议设备接入**：协议适配器插件化（Modbus / MQTT / OPC-UA / HTTP JSON …），边缘网关与云端共用同一套接口契约
- **高频时序数据**：1000+ 测点级规模，asyncpg COPY 批量写入，1 分钟连续聚合自动降采样
- **统一 RBAC**：管理员 / 普通用户两级，用户-项目授权控制数据访问范围
- **实时推送**：Redis Pub/Sub → WebSocket 广播，前端按项目订阅
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

# 3. 应用数据库迁移 + TimescaleDB 初始化 + 种子数据
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.init_db
.venv/bin/python -m scripts.seed

# 4. 启动 API
.venv/bin/python -m uvicorn app.main:app --reload
# 浏览 http://localhost:8000/docs 看交互式 API 文档
```

种子数据：管理员 `admin` / `admin123456`，演示项目、网关 `GW-001`、测点 `ACC-X`。

## 文档导航

- [docs/index.md](docs/index.md) — 文档总目录
- **开发者**
  - [架构设计](docs/architecture.md)
  - [开发环境](docs/development/setup.md)
  - [数据库与迁移](docs/development/database.md)
  - [模块技术说明](docs/development/modules.md)
  - [代码规范](docs/development/coding-standards.md)
  - [测试](docs/development/testing.md)
  - [部署](docs/development/deployment.md)
- **使用者**
  - [API 概览与鉴权](docs/api/overview.md)
  - [认证](docs/api/auth.md)
  - [项目](docs/api/projects.md)
  - [设备](docs/api/devices.md)
  - [测点](docs/api/points.md)
  - [时序数据](docs/api/data.md)
  - [告警](docs/api/alerts.md)
  - [大屏](docs/api/dashboard.md)

## 项目状态

`v0.2.0` — 在 `v0.2.0` 基础上补齐**采集→告警→推送**闭环：

- 设备 / 测点完整 CRUD（含 `alert_rules` 配置）
- 阈值评估（`alert_service.evaluate_thresholds`）+ 告警生命周期（`upsert_alert` / `close_open_alerts`）
- Celery `alerts` 队列异步评估（`app/tasks/alert_tasks.py`）
- WebSocket `data:alert` 实时推送
- 告警列表 / 详情 / 确认（`/api/v1/alerts`）
- 大屏聚合（`/api/v1/dashboard/stats`、`/recent-alerts`）

尚未实现：协议适配器扩展（modbus/mqtt/opcua）、3D 模型上传与分析插件（FFT/趋势预测）、多渠道通知（邮件/钉钉）。这些模块在后续迭代按 AGENTS.md 规划补全。