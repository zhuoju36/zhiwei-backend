# 模块技术说明

> SHM 平台后端 v0.1.0 · 更新于 2026-08-13
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
- `point.py:Point` — `device_id/point_code(同 device 内唯一)/position(JSONB)/alert_rules(JSONB)/sampling_rate`
- `alert.py:Alert` — `point_id/level/value/threshold/started_at/ended_at/is_resolved/resolved_by`
- `timeseries.py` — `SensorRaw`、`SensorFeature`（`metadata` 字段在 Python 侧为 `metadata_` 避免与 SQLAlchemy `MetaData` 冲突）

所有模型通过 `app/models/__init__.py` 统一导出，供 Alembic autogenerate 自动发现。

### `app/schemas/`

严格分离 Request / Response 模型：

- `user.py` — `UserCreate / UserUpdate / UserOut / UserLogin / TokenOut / RefreshIn`
- `project.py` — `ProjectCreate / ProjectUpdate / ProjectOut / ProjectAssignIn`
- `data.py` — `ReadingIn / DataBatchIngest / TimeSeriesPoint / TimeSeriesOut`
- `base.py` — `PageParams / PageSchema[T] / ResponseSchema[T]`

字段约束全部在 schema 层（`Field(min_length=, ge=, le=)`），`EmailStr` 校验来自 `email-validator`。

## 业务逻辑

### `app/services/user_service.py:UserService`

- `get_by_username(db, username)` — 单行查询
- `authenticate(db, username, password)` — `verify_password` + 活跃校验
- `create_user(db, payload)` — 哈希 + 唯一性校验

### `app/services/project_service.py:ProjectService`

- `list_projects(db, user, page, size)` — admin 看全量，普通用户 join `user_projects` 过滤
- `get/create/update/delete` — 基础 CRUD
- `assign_user(db, project_id, user_id, permission)` — 重复授权更新 permission

### `app/services/data_service.py`

模块级单例（连接池懒初始化）：

- `get_pool()` / `get_redis()` / `close()`
- `batch_ingest(readings)` — 一次连接内完成编码映射 + COPY + Redis 发布
- `_resolve_code_map(conn, readings)` — 单 SELECT JOIN 解析所有 device_code/point_code
- `_publish_realtime(readings, code_map)` — Redis pipeline 批量 SET + PUBLISH
- `get_latest(point_id)` — 读 Redis latest
- `query_timeseries(point_id, start, end, interval)` — 智能路由到 sensor_raw 或 sensor_feature_1min
- `check_point_project(point_id)` — 路由层权限校验前置

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

### `app/routers/data.py`

- `POST /data/ingest` — `X-API-Key` 认证，DataBatchIngest，返回 `{written: n}`
- `GET /data/timeseries` — JWT 认证，point_id + start/end/interval
- `GET /data/latest/{point_id}` — JWT 认证，Redis latest

### 占位路由

`users.py / devices.py / points.py / alerts.py / analysis.py / dashboard.py / models.py` —— 已创建 router 与 prefix，等 v0.2+ 补业务。

## 插件体系

### `app/plugins/protocols/`

- `base.py` — `ProtocolAdapter` 抽象基类（**接口契约，禁止修改**）+ `RawReading` / `ProtocolConfig` dataclass
- `registry.py` — `AdapterRegistry.discover()` 扫描包目录，注册所有 `ProtocolAdapter` 子类
- `http_json_adapter.py` — 示例适配器：HTTP GET 返回 JSON 数组，httpx 实现

新增协议步骤（AGENTS.md 第 4.2 节）：
1. 在 `app/plugins/protocols/` 下新建 `<protocol>_adapter.py`
2. 继承 `ProtocolAdapter`，实现 `connect / read_batch / disconnect`
3. 类属性 `name` 必须与 `devices.protocol` 字段值匹配
4. 无需手动注册，自动扫描

### `app/plugins/analyzers/`

- `base.py` — `AnalysisPlugin` 抽象基类（接口契约）
- `registry.py` — `AnalyzerRegistry.discover()` 同上

具体插件（FFT / threshold_alert / trend_predict）在 v0.2+ 补。

## 异步任务

### `app/tasks/celery_app.py`

`Celery("shm", broker=settings.celery_broker_url, backend=settings.celery_result_backend)`，include 4 个任务模块，task_routes 映射到 4 队列：

| 队列 | 模块 | 用途 |
|------|------|------|
| `alerts` | `alert_tasks` | 实时阈值检查（低延迟） |
| `analysis` | `analysis_tasks` | FFT / 模态 / ML（CPU 密集） |
| `reports` | `report_tasks` | PDF / Excel 报表 |
| `maintenance` | `maintenance_tasks` | 连续聚合刷新、数据归档 |

模块当前为占位，按需在对应文件加 `@shared_task(queue="...")` 函数。

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
- `seed.py` — 种子数据（admin/演示项目/设备/测点）

**注意**：脚本需以模块方式运行（`python -m scripts.init_db`），因为脚本需要项目根在 `sys.path`。