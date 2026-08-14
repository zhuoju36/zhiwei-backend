# 架构设计

> SHM 平台后端 v0.8.0 · 更新于 2026-08-14
>
> 本文聚焦后端实现架构。全局业务架构、容量规划、性能目标参见 `../架构说明书.md`。

## 0. 数据拓扑（v0.8b）

```
user → subitem（子项）→ device（设备）→ point（测点=位置）
     → sensor（传感器）→ channel（通道）→ readings（时序）
```

时序 / 告警 / 分析全部按 **channel 粒度**。point 从 v0.7 的"一个传感器一个通道"退化为物理位置；`unit / sampling_rate / alert_rules` 下沉到 channel。

## 1. 分层与职责

```
┌─────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI routers/)                                   │
│  · 路由薄、业务参数校验、权限注入、调用 Service              │
├─────────────────────────────────────────────────────────────┤
│  服务层 (app/services/)                                     │
│  · 时序数据读写、子项/用户 CRUD、业务编排                    │
│  · DataService 持有 asyncpg Pool，绕开 ORM 走原生 SQL/COPY   │
├─────────────────────────────────────────────────────────────┤
│  持久化层                                                   │
│  · PostgreSQL + TimescaleDB（关系 + 时序，hypertable 分区）  │
│  · Redis（最新值缓存、Pub/Sub 实时推送、Celery broker）     │
│  · MinIO（3D 模型、报表、冷数据归档）                        │
├─────────────────────────────────────────────────────────────┤
│  横切关注                                                   │
│  · 协议适配器插件 (app/plugins/protocols/)                   │
│  · 分析算法插件 (app/plugins/analyzers/)                     │
│  · Celery 异步任务 (app/tasks/，4 队列)                      │
│  · WebSocket 实时推送 (app/ws/)                             │
└─────────────────────────────────────────────────────────────┘
```

后端单体进程，但通过以下方式支持横向扩展：
- WebSocket 广播走 Redis Pub/Sub，多实例间消息共享（`app/ws/manager.py`）
- 时序写入用 asyncpg COPY，单实例即可支撑 10万点/秒目标
- Celery 任务独立部署（`docker-compose.yml` 的 `worker` 服务）

## 2. 数据流

### 2.1 高频采集链路

```
边缘网关 ──HTTP/MQTT──▶ POST /api/v1/data/ingest (X-API-Key)
                            │
                            ▼
                  app/routers/data.py
                            │
                            ▼
              app/services/data_service.batch_ingest()
                            │
        ┌───────────────────┼─────────────────────────┐
        ▼                   ▼                         ▼
   asyncpg COPY          Redis SET              Redis PUBLISH
   readings (hypertable)  latest:{channel_id}     subitem:{subitem_id}
        │                   │                         │
        ▼                   ▼                         ▼
   TimescaleDB         GET /data/latest         WebSocket 广播
   （v0.9+ 连续聚合）
```

`DataService.batch_ingest` 在一次提交里完成：编码→ID 映射（一次 SELECT）、COPY 写入、Redis 缓存与发布；详见 `app/services/data_service.py`。

### 2.2 历史查询链路

```
前端 ──JWT──▶ GET /api/v1/data/timeseries?interval=1m
                       │
                       ▼
            check_channel_subitem → check_subitem_access
                       │
                       ▼
          DataService.query_timeseries 智能路由：
            · 全部 → readings 原始表
            · （v0.9+ 连续聚合视图）
```

## 3. 与全局架构说明书的对应

| 架构说明书章节 | 后端实现 |
|----------------|----------|
| 3.1 整体拓扑 | `docker-compose.yml` 服务清单 |
| 3.2 高频数据流 | `app/services/data_service.py` |
| 4.1 关系模型 | `app/models/`（user / project / user_projects / device / point / alert） |
| 4.2 时序模型 | `app/models/timeseries.py`（sensor_raw / sensor_feature） + `scripts/init_db.py`（hypertable、连续聚合、保留策略） |
| 5.2 协议抽象 | `app/plugins/protocols/base.py`（契约稳定，禁止修改） |
| 5.3 动态加载 | `app/plugins/protocols/registry.py`（pkgutil 自动扫描） |
| 6.2 模型转换 | `app/services/model_service.py` 占位，待实现 |
| 7.2 云端写入优化 | `DataService.batch_ingest` 使用 `copy_records_to_table` |
| 7.3 查询优化 | `DataService.query_timeseries` 智能路由 |
| 8 WebSocket | `app/ws/manager.py`（Redis Pub/Sub 跨实例广播） |
| 9 分析引擎 | `app/plugins/analyzers/` + `app/tasks/` |

## 4. 关键技术决策与权衡

| 决策 | 理由 |
|------|------|
| 全异步 + asyncpg | 与边缘网关高频上报节奏匹配；单进程可支撑 10万点/秒目标 |
| ORM 用 SQLAlchemy 2.0 async + `Mapped[]` 风格 | 类型提示与 IDE 友好；时序热路径（COPY）绕开 ORM 用 asyncpg 原生 |
| 时序数据独立 hypertable，不复用关系表 | TimescaleDB 分区、自动压缩、按 chunk 生命周期管理 |
| 协议适配器通过 pkgutil 自动发现 | 新增协议 = 新增一个模块文件，无需改注册代码（OCP） |
| JWT + bcrypt | 简单、标准化；bcrypt 同步计算走 `loop.run_in_executor` 避免阻塞事件循环 |
| 统一响应包装 | 在 ASGI 中间件层实现（`app/core/middleware.py:EnvelopeMiddleware`），与 FastAPI 路由机制解耦 |
| Celery 分 4 队列 | 实时告警低延迟、分析计算可慢、报表可离线、维护任务低优先级 |
| 测试使用 session 级 event loop | 避免 `data_service` 全局连接池跨 loop 复用导致的 `attached to a different loop` 错误 |

## 5. 演进路径

短期（v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 / v0.8，**已交付**）：
- v0.2：设备/测点/告警/大屏路由；阈值告警评估 + Celery `alerts` 队列异步触发；WebSocket `data:alert` 实时推送
- v0.3：modbus_tcp + mqtt 适配器；服务器端协议元数据 API + 校验；三套模拟器脚本 + 边缘网关参考运行脚本
- v0.4：FFT 分析插件；`analysis_jobs` 表 + 迁移；MinIO 客户端；Celery `analysis` 队列异步任务；`/analysis/jobs` CRUD + NPZ 结果下载
- v0.5：WS 子项权限校验（关闭 v0.1 TODO）；告警抑制（per-rule suppress_seconds，复用最近已关闭告警重开）；多渠道通知（Webhook + Email 全局配置，集成进 alert_tasks）
- v0.6：首次部署引导（setup 端点 + CLI + Docker entrypoint）；删除 seed.py（默认 admin/admin123456）
- v0.7：平台元数据（`platform_settings` 单行表，admin PUT）；用户管理（6 个 admin CRUD 端点 + SELF_PROTECTED + LAST_ADMIN 守卫）
- v0.8a：project → subitem 术语重命名（schema 不变）
- v0.8b：全量重构 —— 新增 `sensors` / `channels` / `readings` 表；point 退化为物理位置；`unit / sampling_rate / alert_rules` 下沉到 channel；alerts / analysis_jobs 改按 channel_id；drop sensor_raw / sensor_feature；ingest / timeseries / latest / WS 全按 channel 寻址

中期（v0.9）：readings 上重建 1min/1h 连续聚合；每子项通知通道配置；用户自服务（`/auth/me`、改自己密码、忘记密码）；钉钉/企微/Slack 专属 payload 包装；modbus_rtu / opcua 适配器；模态分析 / 趋势预测等其它分析插件与 MinIO 存储；3D 模型上传与转换；完整边缘网关进程；审计日志；首次登录强制改密码；zxcvbn 密码强度评分。

长期（v1.0）：K8s 化、HTTPS 终止、跨区域复制。