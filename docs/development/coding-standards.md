# 代码规范

> SHM 平台后端 v0.1.0 · 更新于 2026-08-13
>
> 本文补充 `../AGENTS.md` 中已给出的规则，给出更具体的实施细节与示例。AGENTS.md 是最高优先级；本文不与之冲突时可直接遵循。

## 1. 异步铁律

`async def` 路由/函数中**禁止**调用同步 I/O：

| 同步调用 | 异步替代 |
|----------|----------|
| `requests.get` | `httpx.AsyncClient` |
| `time.sleep` | `asyncio.sleep` |
| `open()` / 文件读写 | `aiofiles` |
| `psycopg2` / 同步 SQLAlchemy | `asyncpg` / `sqlalchemy.ext.asyncio` |
| `redis-py` 同步 | `redis.asyncio` |
| `bcrypt` 同步 | `loop.run_in_executor(None, fn, ...)`（参见 `app/core/security.py`） |

正确示例：

```python
async def hash_password(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _hash_password, password)
```

## 2. 类型注解

所有公开函数必须写类型注解（参数 + 返回）。复杂结构优先用 `TypedDict` 或 `dataclass`，SQLAlchemy 2.0 实体用 `Mapped[T]`：

```python
class Device(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    device_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

循环引用处理（`app/models/*.py`）：

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.device import Device
```

## 3. Pydantic 模型

- 所有请求/响应必须用 Pydantic 模型，**禁止直接返回原始字典**
- 严格区分 Request / Response（不同生命周期）
- 字段约束在模型层声明：`Field(min_length=, ge=, le=)` / `EmailStr`
- 复杂序列化用 `model_config = ConfigDict(from_attributes=True)` + `Model.model_validate(orm_obj)`

## 4. 数据库操作

查询统一使用 `select()` + `async session`（SQLAlchemy 2.0 风格），**禁止** `db.query()`（1.x 同步 API）：

```python
stmt = select(Project).where(Project.id == project_id)
result = await db.execute(stmt)
project = result.scalar_one_or_none()
```

依赖注入（`app/dependencies.py`）：

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

热路径写时序数据**绕开 ORM**，直接用 asyncpg COPY（参见 `DataService.batch_ingest`），ORM 仅用于关系表 CRUD。

## 5. 错误处理

业务异常继承 `BizException`，由 `biz_exception_handler` 统一包装为 4xx/5xx envelope：

```python
class BizException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400): ...

class AuthException(BizException):
    def __init__(self, message: str = "未认证或凭证无效", status_code: int = 401):
        super().__init__(code="AUTH_ERROR", message=message, status_code=status_code)
```

路由层只 `raise`，由框架统一捕获；服务层不要返回 `Optional[Model]` 让路由判 None，要么 raise 要么给默认值。

## 6. 路由组织

- 路由文件放在 `app/routers/<domain>.py`
- 使用 `app.core.middleware.create_router(**kwargs)` 创建（业务路由只是 `APIRouter` 工厂；统一响应包装由 `EnvelopeMiddleware` 在应用级处理）
- 路由薄（< 20 行）：参数解析、权限检查、调用 Service、返回 Pydantic
- 业务逻辑下沉到 `app/services/`

## 7. 插件开发

### 协议适配器

新增协议 = 新增一个 `app/plugins/protocols/<protocol>_adapter.py`：

```python
class FooAdapter(ProtocolAdapter):
    name = "foo"  # 必须与 devices.protocol 字段值一致
    supports_batch = False

    async def connect(self) -> None: ...
    async def read_batch(self) -> list[RawReading]: ...
    async def disconnect(self) -> None: ...
```

**禁止修改 `base.py` 中的 `ProtocolAdapter` 契约**（稳定性约束）。Registry 通过 `pkgutil` 自动扫描，无需手动注册。

### 分析算法

新增分析插件同协议模式，继承 `AnalysisPlugin`（`app/plugins/analyzers/base.py`）。

## 8. 导入排序与 Lint

项目使用 ruff，配置在 `pyproject.toml`：

- `select = ["E", "F", "I", "UP", "B", "ASYNC"]`
- `line-length = 100`
- `target-version = "py311"`
- `flake8-bugbear.extend-immutable-calls` 把 `fastapi.Query/Depends/...` 加入白名单（FastAPI 惯用法）
- `exclude = ["alembic/versions"]` —— 自动生成的迁移脚本不参与 lint/format

提交前必须：

```bash
.venv/bin/ruff check --fix .
.venv/bin/ruff format .
```

## 9. 反模式清单

| 反模式 | 后果 | 正确做法 |
|--------|------|----------|
| `async def` 中调用 `requests.get` | 阻塞事件循环，所有请求排队 | `httpx.AsyncClient` |
| 逐条 INSERT 时序数据 | 连接池耗尽，吞吐 < 100点/秒 | 批量 COPY（1000~5000/批） |
| 协议适配器硬编码设备参数 | 新增设备必须改代码发版 | 通过 `ProtocolConfig.register_map` 配置化 |
| WebSocket 直接广播不经过 Redis | 多实例部署时消息丢失 | Redis Pub/Sub 作为跨实例广播层 |
| 返回 ORM 对象给前端 | 暴露敏感字段、循环引用序列化失败 | 必须通过 Pydantic Schema 转换 |
| 路由中写复杂业务逻辑 | 难以测试、职责混乱 | 路由薄、服务厚 |
| 在 Celery task 中创建新 DB 连接而不关闭 | 连接泄漏，PostgreSQL 拒绝连接 | 使用上下文管理器或 SQLAlchemy session |

## 10. Git 提交建议

提交信息格式：`<scope>: <verb> <object>`，例如：

```
data: add batch_ingest with asyncpg COPY
auth: switch to PyJWT for token signing
plugins: add http_json adapter example
```

变更范围广或涉及迁移时，单独一个提交描述文档更新。