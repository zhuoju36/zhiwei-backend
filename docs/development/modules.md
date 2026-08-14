# 模块技术说明

> SHM 平台后端 v0.9.0 · 更新于 2026-08-13
>
> 逐模块说明 `app/` 下各子包的关键类、职责与调用关系。

## 目录速览

```
app/
├── main.py               # FastAPI 应用工厂 + 中间件挂载 + 异常处理
├── lifespan.py           # 启动：插件发现、Redis 监听；关闭：释放连接
├── config.py             # Pydantic Settings（环境变量集中管理）
├── database.py           # SQLAlchemy async engine + async_sessionmaker
├── dependencies.py       # FastAPI Depends：DB 会话、JWT 用户、权限、API Key
├── core/
│   ├── constants.py      # 角色、设备状态、告警级别、分页常量
│   ├── exceptions.py     # BizException / AuthException
│   ├── security.py       # JWT 编解码、bcrypt（线程池异步化）
│   └── middleware.py     # EnvelopeMiddleware + 异常处理工厂
├── models/               # ORM 模型（每个表一个文件）
├── schemas/              # Pydantic 请求/响应模型（每个领域一个文件）
├── routers/              # API 路由（每个领域一个文件，统一注册到 /api/v1）
├── services/             # 业务逻辑层（路由薄、服务厚）
├── plugins/
│   ├── protocols/        # 协议适配器（base 契约 + registry 自动发现）
│   └── analyzers/        # 分析算法插件（同上）
├── tasks/                # Celery 应用 + 4 队列任务模块
├── ws/                   # WebSocket 连接管理、Redis Pub/Sub
└── utils/                # 纯工具函数
```

## 入口与生命周期

### `app/main.py:create_app()`

构建 `FastAPI(title="SHM 平台后端", version="0.1.0", lifespan=lifespan)`，依次：
1. `add_middleware(CORSMiddleware, ...)` — 跨域配置（生产禁止 `*`）
2. `add_middleware(EnvelopeMiddleware)` — 统一响应包装
3. `register_exception_handlers(app)` — `BizException` / `RequestValidationError` / `Exception`
4. `include_router(api_router)` — `/api/v1` 下所有业务路由
5. `include_router(ws_router)` — WebSocket `/ws/data`
6. 注册 `/health` 探针

### `app/lifespan.py`

启动期：
- `AdapterRegistry.discover()` + `AnalyzerRegistry.discover()`（懒注册，安全幂等）
- `manager.init_redis(redis_url)` — Redis 失败不阻塞启动（实时推送降级）

关闭期：`manager.close()` + `data_service.close()` + `engine.dispose()`。

### `app/config.py:Settings`

Pydantic BaseSettings，从 `.env` 加载（`env_file=".env"`）。`asyncpg_dsn` 属性把 `postgresql+asyncpg://` 转为 `postgresql://` 供 asyncpg 使用。

### `app/database.py`

`engine = create_async_engine(...)`：`pool_size=20, max_overflow=30, pool_pre_ping=True, pool_recycle=3600`（AGENTS.md 第 2.3 节）。

`AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`。

## 横切关注

### `app/core/security.py`

- `_create_token(subject, type, expires, extra)` — 内部 JWT 生成器
- `create_access_token(user_id, role)` / `create_refresh_token(user_id)`
- `decode_token(token, expected_type)` — 校验 + 类型隔离
- `hash_password` / `verify_password` — bcrypt 同步计算通过 `loop.run_in_executor` 异步化，避免阻塞事件循环

### `app/core/middleware.py`

- `envelope(data, code, message)` — 构造统一响应体
- `EnvelopeMiddleware` — ASGI 中间件，缓冲 `http.response.body` 后判断是否包装 2xx JSON 响应；204/空响应/非 JSON/文档与健康检查路径直通
- `biz_exception_handler` / `validation_exception_handler` / `unhandled_exception_handler`
- `create_router(**kwargs)` — 业务路由器工厂（仅做 `APIRouter(**kwargs)`；包装在中间件层完成）

设计动机见 AGENTS.md 第 3.3 节"响应格式统一"。注意：**FastAPI 0.141 新版 `include_router` 采用延迟挂载，子路由器的 `route_class` 不会传播到父路由器，且带 `response_model` 的路由会被物化为新的 APIRoute**，因此原本基于 `route_class` 的包装方案失效，改在 ASGI 中间件层实现。

### `app/dependencies.py`

依赖注入标识（Annotated）：

- `DbSession = Annotated[AsyncSession, Depends(get_db)]` — 自动 commit/rollback/close
- `CurrentUser = Annotated[User, Depends(get_current_user)]` — JWT 解析 + 用户加载
- `AdminUser = Annotated[User, Depends(require_admin)]` — 角色校验
- `verify_api_key` — 边缘网关 `X-API-Key` Header 校验
- `check_project_access(db, user, project_id)` — 普通用户必须有 `user_projects` 记录，admin 放行

OAuth2 password flow 使用 `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)`，未带 token 抛 AuthException(401)。

## 数据模型

### `app/models/`

- `user.py:User` — `username/email/hashed_password/role/is_active/created_at`
- `project.py:Project` + `UserProject`（关联表，独立 permission 字段）
- `device.py:Device` — `project_id/device_code(唯一)/protocol/config(JSONB)/status/last_seen`
- `sensor.py:Sensor`（v0.9 合一）— `device_id/sensor_code(同 device 内唯一)/position(JSONB)/sensor_name/sensor_type` + 仪器元数据 `model/manufacturer/install_date/last_calibration/metadata_`（原 point 与 sensor 合并）
- `channel.py:Channel` — `sensor_id/channel_code(同 sensor 内唯一)/channel_type/unit/sampling_rate/position_offset/axis/alert_rules(JSONB)/is_active`（v0.8b 新增，一个 sensor 可有 1-N 个 channel）
- `reading.py:Reading` — 时序数据（TimescaleDB hypertable）：`(time, channel_id)` 复合主键 / value / quality / metadata_（v0.8b 替代 sensor_raw/sensor_feature）
- `alert.py:Alert` — `channel_id/level/value/threshold/started_at/ended_at/is_resolved/resolved_by`
- `analysis.py:AnalysisJob` — `channel_id/plugin/params/status/result_key/result_summary/error`
- `platform.py:PlatformSettings` — 单行表（`id=1`）：`platform_name/contact_email/description/logo_url`

`metadata` 字段在 Python 侧统一为 `metadata_` 避免与 SQLAlchemy `MetaData` 冲突，Pydantic 侧用 `validation_alias/serialization_alias` 还原为 `metadata`。

所有模型通过 `app/models/__init__.py` 统一导出，供 Alembic autogenerate 自动发现。

### `app/schemas/`

严格分离 Request / Response 模型：

- `user.py` — `UserCreate / UserUpdate / UserOut / UserLogin / TokenOut / RefreshIn`
- `project.py` — `ProjectCreate / ProjectUpdate / ProjectOut / ProjectAssignIn`
- `sensor.py` — `SensorCreate / SensorOut` + `ChannelCreate / ChannelOut` + `AlertRule`（v0.8b：传感器/通道 Schema 同文件；`AlertRule` 的 operator/level 用 `Field(pattern=...)` 约束）
- `data.py` — `ReadingIn / DataBatchIngest / TimeSeriesPoint / TimeSeriesOut`
- `base.py` — `PageParams / PageSchema[T] / ResponseSchema[T]`

字段约束全部在 schema 层（`Field(min_length=, ge=, le=)`），`EmailStr` 校验来自 `email-validator`。

## 业务逻辑

### `app/services/user_service.py:UserService`

- `get_by_username(db, username)` — 单行查询
- `authenticate(db, username, password)` — `verify_password` + 活跃校验
- `create_user(db, payload)` — 哈希 + 唯一性校验

### `app/services/device_service.py:DeviceService`

- `get(db, id)` / `list_by_project(db, project_id, page, size)` / `create / update / delete`
- 创建时校验项目存在 + `device_code` 全局唯一（409 `DEVICE_CODE_EXISTS`）

### `app/services/sensor_service.py:SensorService`（v0.9 合一）

- `get / list_by_device / create / update / delete`（v0.9：原 point 与 sensor 合并，挂 device 下）
- 创建时校验 `sensor_code` 在同 `device_id` 下唯一（409 `SENSOR_CODE_EXISTS`）
- 位置字段（position / sensor_name）与仪器元数据（model/厂商/校准日期）同一行

### `app/services/channel_service.py:ChannelService`（v0.8b 新增）

- `get / list_by_sensor / list_by_device / create / update / delete`
- 创建时校验 `channel_code` 在同 `sensor_id` 下唯一（409 `CHANNEL_CODE_EXISTS`）
- `create` 时将 `alert_rules` 的 Pydantic 子模型序列化为 dict 存 JSONB
- `list_by_device` 走 `channel → sensor → device` JOIN，供设备视图聚合

### `app/services/alert_service.py`

- `TriggerEvent` dataclass：`{level, threshold, operator, value, message}`
- `evaluate_thresholds(value, rules) -> list[TriggerEvent]` — 单条读数 vs 多个规则
  - 运算符：`gt / lt / ge / le / eq / ne`
  - 规则字段缺失或 operator 非法 → 跳过该规则（不抛错）
- `trigger_alert(db, channel_id, event, ts) -> (Alert, created)` —— 触发/更新 upsert 逻辑：
  - 已存在未恢复告警 → 更新 `value/threshold`，不重置 `started_at`
  - 无 → 创建新告警
- `close_open_alerts(db, channel_id, level, ts)` — 关闭一条未恢复告警（值回到正常），幂等
- `list_alerts(db, query)` / `get_alert` / `acknowledge_alert` — 列表（支持 project_id/channel_id/level/is_resolved/时间窗）、详情、确认（设置 `ended_at/resolved_by/is_resolved`，并发二次确认返回 `409 ALERT_ALREADY_RESOLVED`）
- `to_out_dict(alert)` — 模型 → JSON 安全的 dict

### `app/services/project_service.py:ProjectService`

- `list_projects(db, user, page, size)` — admin 看全量，普通用户 join `user_projects` 过滤
- `get_project / create_project / update_project / delete_project` — 基础 CRUD
- `assign_user(db, project_id, user_id, permission)` — 重复授权更新 permission

### `app/services/data_service.py`

模块级单例（连接池懒初始化）：

- `get_pool()` / `get_redis()` / `close()`
- `batch_ingest(readings)` — 一次连接内完成编码映射 + COPY + Redis 发布
- `_resolve_code_map(conn, readings)` — 单 SELECT JOIN 解析所有 device_code/channel_code（device→sensor→channel）
- `_publish_realtime(readings, code_map)` — Redis pipeline 批量 SET + PUBLISH
- `get_latest(channel_id)` — 读 Redis latest
- `query_timeseries(channel_id, start, end, interval)` — 从 readings 读取
- `check_channel_project(channel_id)` — 路由层权限校验前置

## API 路由

### `app/routers/auth.py`

- `POST /auth/login` — OAuth2PasswordRequestForm → TokenOut
- `POST /auth/refresh` — RefreshIn → 新 TokenOut

### `app/routers/projects.py`

- `GET /projects` — 分页列表（admin 全量 / 用户受限）
- `POST /projects` — admin 创建
- `GET /projects/{id}` — 受限详情
- `PUT /projects/{id}` — admin 更新
- `DELETE /projects/{id}` — admin 删除（204）
- `POST /projects/{id}/users` — admin 授权（204）

### `app/routers/devices.py`

- `GET /devices?project_id=...` — 按项目分页列表（项目成员可见）
- `POST /devices` — 创建（项目写权限）
- `GET /devices/{id}` / `PUT /devices/{id}` / `DELETE /devices/{id}`（删除需 admin）

### `app/routers/sensors.py`（v0.9 重写：挂 device 下）

- `GET /sensors?device_id=...` — 按设备分页列表（device 必填，缺失 400）
- `POST /sensors` / `GET /sensors/{id}` / `PUT /sensors/{id}` / `DELETE /sensors/{id}`（删除需 admin）
- 字段：sensor_code / sensor_name / sensor_type / position（三维坐标）+ model / manufacturer 等仪器元数据

### `app/routers/channels.py`（v0.8b 新增）

- `GET /channels?sensor_id=...` — 按传感器分页列表
- `POST /channels` / `GET /channels/{id}` / `PUT /channels/{id}` / `DELETE /channels/{id}`（删除需 admin）
- 写操作沿 `channel → sensor → device → project` 链校验项目权限

### `app/routers/alerts.py`

- `GET /alerts` — 列表（分页 + `project_id/channel_id/level/is_resolved/start/end` 过滤）
- `GET /alerts/{id}` — 详情
- `POST /alerts/{id}/acknowledge` — 确认（项目 admin 权限）

### `app/routers/dashboard.py`

- `GET /dashboard/stats?project_id=...` — `{active_alerts, alerts_24h, by_level, project_id}`
- `GET /dashboard/recent-alerts?project_id=...&limit=10`

### `app/routers/data.py`

- `POST /data/ingest` — `X-API-Key` 认证，DataBatchIngest，返回 `{written: n}`
- `GET /data/timeseries` — JWT 认证，channel_id + start/end/interval
- `GET /data/latest/{channel_id}` — JWT 认证，Redis latest

### `app/routers/users.py`

- 用户管理，全部需 `AdminUser`：列表 / 创建 / 详情 / 更新 / 启停用

### `app/routers/setup.py`（v0.8 新增）

- `GET /setup/status` — 首次部署状态（是否已初始化）
- `POST /setup/init-admin` — 无鉴权，创建初始管理员账户

### `app/routers/platform.py`（v0.8 新增）

- `GET /platform` — 平台信息（名称/logo/联系方式）
- `PUT /platform` — admin 修改平台名称等

### `app/routers/protocols.py`（v0.8 新增）

- `GET /protocols` — 已注册协议适配器元信息（name/version/supports_batch）

### `app/routers/models.py`（v0.8c 实现）

- `POST /models/{project_id}/upload` — multipart 上传（项目写权限），格式白名单 obj/stl/ply/gltf/glb（**IFC 返回 400** `MODEL_FORMAT_UNSUPPORTED`），≤200MB；源文件存 MinIO 后建 `3d_models` 记录并触发转换任务，返回 `{model_id, status}`
- `GET /models?project_id=...` — 一个项目多个模型的分页列表（读权限）
- `GET /models/{id}` — 详情
- `GET /models/{id}/file` — 返回转换后的 GLB（`model/gltf-binary`）；未完成 409 `MODEL_NOT_READY`
- `DELETE /models/{id}` — admin；删记录 + 清理 MinIO 两个对象（失败仅记日志）

### `app/services/model_service.py:ModelService`（v0.8c 新增）

- `create / get / list_by_project / delete` — `3d_models` 表 CRUD
- `mark_running / mark_success / mark_failed` — 状态机 pending → processing → success/failed

### `app/tasks/model_tasks.py:convert_model_task`（v0.8c 新增）

- `queue="reports"`，**不自动重试**（格式问题重试无意义；意外异常也回写 failed 避免悬挂）
- 流程：下载 MinIO 源文件 → `scripts.model_convert.convert_bytes` → 上传 GLB → mark_success

## 插件体系

### `app/notifications/`（v0.5）

- `base.py` — `AlertPayload` TypedDict + `NotificationChannel` Protocol
- `webhook.py` — `WebhookChannel`（httpx 异步 POST，10s 超时，失败仅记日志）
- `email.py` — `EmailChannel`（smtplib in executor，HTML 模板，按 level 着色）
- `app/services/notification_service.py` — `dispatch_alert` 并发派发，通道故障隔离

### `app/plugins/protocols/`

- `base.py` — `ProtocolAdapter` 抽象基类（**接口契约，禁止修改**）+ `RawReading` / `ProtocolConfig` dataclass；v0.9 增加**可选**监听能力：`supports_listen` 类属性 + `decode_stream(data) -> list[RawReading]`（默认 `NotImplementedError`，不破坏主动轮询适配器）
- `registry.py` — `AdapterRegistry.discover()` 扫描包目录，注册所有 `ProtocolAdapter` 子类
- `http_json_adapter.py` — 示例适配器：HTTP GET 返回 JSON 数组，httpx 实现
- `modbus_tcp_adapter.py`（v0.3 新增）— `ModbusTcpAdapter`（pymodbus）
  - 支持 `uint16` / `int16` / `uint32` / `int32` / `float32` / `float64` 字节序解码
  - 单点错误隔离（quality="bad"）
- `mqtt_adapter.py`（v0.3 新增）— `MqttAdapter`（aiomqtt）
  - 后台订阅协程 + 内部 `asyncio.Queue` 缓冲
  - JSON payload 容错（字段缺失 / 格式错误丢弃）
- `modbus_rtu_tcp.py`（v0.9 新增，监听型）— `ModbusRtuOverTcpAdapter`：DTU 透传接入
  - `supports_listen = True`，`decode_stream` 切帧（CRC16 校验、粘包/半包/坏帧重同步）+ 解码
  - RTU 帧解析自研（~50 行），不依赖 pymodbus 易变 framer API；解码复用 `modbus_tcp_adapter._DECODERS`

新增协议步骤（AGENTS.md 第 4.2 节）：
1. 在 `app/plugins/protocols/` 下新建 `<protocol>_adapter.py`
2. 继承 `ProtocolAdapter`，实现 `connect / read_batch / disconnect`；监听型额外设 `supports_listen = True` + `decode_stream`
3. 类属性 `name` 必须与 `devices.protocol` 字段值匹配
4. 无需手动注册，自动扫描

## DTU 监听接入（v0.9）

### `app/dtus/server.py:TcpServerManager`

- 拓扑 A（DTU 直连云）：独立 asyncio 进程 `python -m app.dtu_server` 接收 DTU 透传的 Modbus RTU 帧，与 FastAPI 解耦（docker-compose 同镜像独立 service）
- `start()`：拉取 `protocol="modbus_rtu_over_tcp"` 的设备 → 每设备 `asyncio.start_server`（**一端口一设备**，`config.port`）
- 连接处理：字节流缓冲 → `split_rtu_frames` 切帧 → `adapter.decode_stream` → `ReadingIn` 入队
- 攒批消费：`asyncio.Queue` + 消费者（`dtu_batch_size` 条或 `dtu_flush_interval_s` 秒 flush）→ `data_service.batch_ingest`（COPY 直写 readings + Redis 实时推送 + Celery 告警）
- `stop()` 优雅停机：停 accept → 排空队列 → 取消消费者

### `app/dtu_server.py`

进程入口（`python -m app.dtu_server`）：预热 asyncpg 池 → `TcpServerManager.start()` → SIGTERM/SIGINT 优雅退出。

### `app/plugins/analyzers/`（v0.8d 接口 v2）

- `base.py` — `AnalysisPlugin` 抽象基类（接口契约 v2）+ `AnalysisInput` / `AnalysisOutput` dataclass
  - 自描述元信息：`name / display_name / description / version / plugin_api_version / input_channels / min_samples / params_schema / result_view`（前端据此渲染列表、参数表单与结果视图）
  - 插件 = 纯计算单元（输入数组 + 参数 → 摘要/附件），不接触数据库与实时流；面向社区开发者的指南见 [plugin-dev.md](plugin-dev.md)
- `registry.py` — 双层发现：内置目录扫描 + Python entry_points（组 `shm_analyzers`，pip install 即接入）；版本守卫（`plugin_api_version` 不匹配拒绝加载）、同名保留先注册者
- `fft_analysis.py` — `FftAnalysis`（v2 改造）：JSON 摘要 + NPZ 附件显式返回（`AnalysisOutput.artifact`）；`sampling_rate` 缺省取通道配置
- `statistics.py`（v0.8d 新增）— `StatisticsAnalysis`：基础统计（均值/峰值/RMS），社区插件最小示例

`GET /api/v1/analysis/plugins` 返回全部插件元信息（含 `params_schema`，前端动态表单）。trend_predict / modal_analysis 待社区或后续版本补充。

## 异步任务

### `app/tasks/celery_app.py`

`Celery("shm", broker=settings.celery_broker_url, backend=settings.celery_result_backend)`，include 4 个任务模块，task_routes 映射到 4 队列：

| 队列 | 模块 | 用途 |
|------|------|------|
| `alerts` | `alert_tasks` | 实时阈值检查（低延迟） |
| `analysis` | `analysis_tasks` | FFT / 模态 / ML（CPU 密集） |
| `reports` | `report_tasks` | PDF / Excel 报表 |
| `maintenance` | `maintenance_tasks` | 连续聚合刷新、数据归档 |

### `app/tasks/alert_tasks.py`

- `@shared_task(queue="alerts", max_retries=3) def check_threshold_batch(readings)`
- 由 `data_service.batch_ingest` 在写入完成后调用（`.delay()`）
- 处理流程：
  1. 收集所有涉及的 `channel_id`，一次性 JOIN 取出 `alert_rules` 和 `device.project_id`（channel→sensor→device）
  2. 逐条评估 `evaluate_thresholds`
  3. 触发 upsert / 关闭已存在的 open alert
  4. 通过 Redis Pub/Sub 向 `project:{id}` 频道推送 `{"type": "data:alert", "payload": {...}}`
- 测试用 `task_always_eager=True`（`tests/conftest.py` autouse fixture 开启）
- 文件顶部 `nest_asyncio.apply()` 允许在已有事件循环中运行 `asyncio.run()`（兼容测试异步上下文）

### `app/tasks/analysis_tasks.py`

- `@shared_task(queue="analysis") def run_analysis_job(job_id)`
- 流程（v0.8d 接口 v2）：按插件 `input_channels` 拉取通道数据（多通道限同项目，JOIN channel→sensor→device 校验）→ `plugin.analyze(AnalysisInput, config)` → `AnalysisOutput.summary` 回写 `result_summary`、`artifact` 上传 MinIO（`analysis/{job_id}/{artifact_name}`）
- 前置校验：`plugin_api_version`、通道数量、`min_samples`；插件参数校验失败（`ValueError`）→ 任务 `failed` 并记录错误

## WebSocket

### `app/ws/manager.py:ConnectionManager`

- `active_connections: dict[int, list[WebSocket]]` — project_id → 连接列表
- `init_redis(url)` / `close()`
- `_broadcast_listener()` — 监听 `project:*` 频道，向本地连接推送；离线/异常连接自动清理
- 单例 `manager`，由 `lifespan` 管理

### `app/ws/endpoints.py:ws_data`

- `/ws/data?token=<access_token>`：手动校验 JWT（WebSocket 不支持 Depends）
- 接收 `{"type": "cmd:subscribe", "project_id": 1}` 注册订阅
- 后续 Redis 推送自动转发给该连接
- 断连时 `manager.disconnect` 清理

## 工具与脚本

### `app/utils/`

- `time_utils.py` — `utc_now()` / `to_utc(dt)`：统一 UTC aware 处理
- `validators.py` / `minio_client.py` — 占位

### `scripts/`

- `init_db.py` — TimescaleDB 初始化（幂等，可重入）
- `seed.py` — 种子数据（admin/演示项目/设备/传感器）

**注意**：脚本需以模块方式运行（`python -m scripts.init_db`），因为脚本需要项目根在 `sys.path`。