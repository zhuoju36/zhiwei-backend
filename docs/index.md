# 文档目录

> SHM 平台后端 v0.3.0 · 更新于 2026-08-13

## 开发者文档

| 文档 | 内容 |
|------|------|
| [architecture.md](architecture.md) | 系统分层、数据流、技术选型理由、与全局架构说明书的对应关系 |
| [development/setup.md](development/setup.md) | 开发环境搭建、Docker 基础设施、`.env` 配置、常用命令 |
| [development/database.md](development/database.md) | 关系表与时序表设计、TimescaleDB hypertable / 连续聚合 / 保留策略、迁移流程 |
| [development/modules.md](development/modules.md) | `app/` 各子模块的技术细节：职责、关键类、调用关系 |
| [development/coding-standards.md](development/coding-standards.md) | 异步铁律、Pydantic / SQLAlchemy 用法、错误处理、提交前检查清单 |
| [development/testing.md](development/testing.md) | 测试分层、pytest 约定、fixture、集成测试数据库策略 |
| [development/simulation.md](development/simulation.md) | 无硬件模拟器使用指南（modbus_simulator / mqtt_injector / simulate_data） |
| [development/deployment.md](development/deployment.md) | Docker 镜像、Compose 服务清单、生产环境建议 |

## API 文档（使用者）

| 文档 | 内容 |
|------|------|
| [api/overview.md](api/overview.md) | 统一响应格式、错误码、鉴权机制、分页约定 |
| [api/auth.md](api/auth.md) | 登录、刷新令牌 |
| [api/projects.md](api/projects.md) | 项目 CRUD 与用户授权 |
| [api/devices.md](api/devices.md) | 设备 CRUD |
| [api/points.md](api/points.md) | 测点 CRUD、alert_rules 字段语义 |
| [api/protocols.md](api/protocols.md) | 协议元数据 + 各协议 config schema |
| [api/data.md](api/data.md) | 时序数据批量接入、查询、最新值、WebSocket 订阅、告警事件 |
| [api/alerts.md](api/alerts.md) | 告警列表 / 详情 / 确认 |
| [api/dashboard.md](api/dashboard.md) | 大屏聚合统计与最近告警 |

## 其他参考

- 全局架构说明书：`../架构说明书.md`（业务架构、技术选型、容量规划）
- `../AGENTS.md` — 项目级开发规范与目录约定（最高优先级）
- 实时 OpenAPI 文档：启动服务后访问 `http://localhost:8000/docs`