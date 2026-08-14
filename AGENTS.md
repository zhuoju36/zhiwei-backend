# AGENTS.md - 后端开发规范与指南

> **项目**：止危结构健康监测（SHM）平台后端  
> **技术栈**：Python 3.11+ | FastAPI | SQLAlchemy 2.0(async) | asyncpg | Pydantic v2 | Celery | TimescaleDB  
> **核心约束**：**全异步**、**协议插件化**、**高频时序数据**、**1000测点级规模**
> 全局架构详见 ../架构说明书.md

## 0. 基本开发原则
### 0.1 基本原则
- 当前系统还在早期开发阶段，未上线，不需要考虑向后兼容。
- 优先使用能满足当前需求的最简单实现。不要预防性抽象，不要多此一举的配置层。
- 系统分层生长。先跑通一个最小的端到端版本，再往上加东西。绝不为了未完成的复杂度拆掉能跑的东西。
- 组件保持模块化，关注点分离。
- 优先使用成熟的、有人维护的库。没有明确理由不要自己重写。
- 先翻项目里已有的依赖能做什么，再考虑加新包或者自己写。
- 架构决策要有长远眼光。不接受“先这样以后再换”的临时方案。
- 先看成熟产品怎么解决同一个问题，用已验证的模式，不要从零发明。

### 0.2 必须做（Always do）
- **激活虚拟环境后再执行任何命令**
- 开始修改代码前必须先阅读文档，任务完成后必须更新文档
- 文档版本号保持与pyproject.toml的版本号一致
- 使用虚拟环境内的 Python 和 pip（`which python` 应指向 `.venv/bin/python`）
- 优先考虑使用国内pip源，比如中科大pip源
- 所有函数签名必须写类型注解
- 所有请求/响应必须使用 Pydantic 模型（**禁止**原始字典）
- 使用依赖注入获取数据库会话和认证信息
- 在系统边界验证输入（Pydantic schemas, `Field()` 约束）
- 提交前运行 `ruff check --fix . && ruff format .`
- 审查自动生成的 Alembic 迁移文件后再应用
- 为新接口和业务逻辑编写测试和文档
- 有异步 I/O 的路由用 `async def`，同步/阻塞 I/O 用 `def`

### 0.3 先请示（Ask first）
- 排查问题后，改动代码前先请示改动方案
- 添加新依赖（需更新 requirements.txt 或 pyproject.toml）
- 修改 Schema 或迁移文件
- 影响多个领域模块的变更
- 架构决策（新模式、缓存策略等）
- 超过 300 行或影响 3 个以上文件的变更
- 数据库结构变更（索引、约束、引擎变更）
- 连接池配置变更

### 0.4 禁止做（Never do）
- 在**未激活虚拟环境**的情况下运行项目命令
- 使用系统全局 pip 安装项目依赖（应使用虚拟环境内的 pip）
- 在应用代码中调用 `Base.metadata.create_all()`（应使用 Alembic）
- 在 `async def` 路由中使用阻塞调用（`time.sleep`, `requests.get`）
- 在生产环境 CORS 中使用 `allow_origins=["*"]`
- 使用原始 SQL 字符串拼接（应使用 ORM 或参数化查询）
- 提交 `.env` 文件或密钥
- 使用 `# type: ignore` 或 `# noqa` — 修复实际问题
- 强制推送或 rebase 共享分支
- 使用 `@app.on_event("startup")`（应使用 `lifespan` 上下文管理器）
- 在异步路由中使用同步 MySQL 驱动（mysql-connector-python, PyMySQL）
- 跳过 Alembic 迁移直接修改数据库结构

## 1. 项目结构（必须严格遵守）

```
backend/
+-- app/
|   +-- __init__.py
|   +-- main.py                 # FastAPI 应用工厂， lifespan 管理启动/关闭
|   +-- config.py               # Pydantic Settings，环境变量集中管理
|   +-- database.py             # SQLAlchemy async engine + async_sessionmaker
|   +-- dependencies.py         # FastAPI Depends 注入：DB session、当前用户、权限检查
|   +-- lifespan.py             # 启动：建表检查、插件加载；关闭：连接池释放
|   |
|   +-- core/                   # 基础设施，禁止引入业务模型
|   |   +-- __init__.py
|   |   +-- security.py         # JWT 编码/解码、密码哈希（bcrypt）
|   |   +-- exceptions.py       # 自定义异常类：BizException、AuthException
|   |   +-- middleware.py       # 请求日志、异常捕获、CORS、耗时统计
|   |   +-- constants.py        # 全局常量：角色枚举、状态枚举、默认分页大小
|   |
|   +-- models/                 # SQLAlchemy ORM 模型，一文件一表
|   |   +-- __init__.py         # 统一导出，方便 Alembic 自动发现
|   |   +-- base.py             # Base = declarative_base()，所有模型继承
|   |   +-- user.py
|   |   +-- project.py
|   |   +-- device.py
|   |   +-- point.py
|   |   +-- timeseries.py       # sensor_raw / sensor_feature 模型（TimescaleDB）
|   |   +-- alert.py
|   |
|   +-- schemas/                # Pydantic v2 模型，严格分离 Request/Response
|   |   +-- __init__.py
|   |   +-- base.py             # 通用：PageSchema、ResponseSchema
|   |   +-- user.py             # UserCreate, UserUpdate, UserOut, UserLogin
|   |   +-- device.py
|   |   +-- point.py
|   |   +-- data.py             # DataQuery, DataBatchIngest, TimeSeriesOut
|   |   +-- alert.py
|   |
|   +-- routers/                # API 路由，一模块一文件
|   |   +-- __init__.py         # 统一注册 router，前缀 /api/v1
|   |   +-- auth.py             # POST /auth/login, POST /auth/refresh
|   |   +-- users.py            # 用户 CRUD，仅 admin
|   |   +-- projects.py         # 项目 CRUD + 用户授权
|   |   +-- devices.py          # 设备管理
|   |   +-- points.py           # 测点管理 + 三维坐标绑定
|   |   +-- data.py             # 时序数据查询 + 批量接入 (/ingest)
|   |   +-- alerts.py           # 告警查询 + 确认
|   |   +-- analysis.py         # 分析任务提交 + 结果查询
|   |   +-- dashboard.py        # 大屏聚合数据（最新值、统计卡片）
|   |   +-- models.py           # 3D 模型文件上传/转换状态查询
|   |
|   +-- services/               # 业务逻辑层，路由薄、服务厚
|   |   +-- __init__.py
|   |   +-- user_service.py
|   |   +-- device_service.py
|   |   +-- data_service.py     # 时序数据读写核心：批量插入、降采样查询
|   |   +-- alert_service.py    # 告警规则检查、告警生命周期
|   |   +-- analysis_service.py # 分析任务编排、结果存储
|   |   +-- model_service.py    # 3D 模型文件处理、转换任务触发
|   |
|   +-- plugins/                # 插件化扩展目录
|   |   +-- __init__.py
|   |   +-- protocols/          # 协议适配器（边缘网关复用）
|   |   |   +-- __init__.py
|   |   |   +-- base.py         # ProtocolAdapter 抽象基类（绝对禁止修改接口）
|   |   |   +-- registry.py     # 动态发现与注册
|   |   |   +-- modbus_tcp.py
|   |   |   +-- modbus_rtu.py
|   |   |   +-- mqtt_adapter.py
|   |   |   +-- opcua_adapter.py
|   |   |   +-- http_json.py
|   |   +-- analyzers/          # 分析算法插件
|   |       +-- __init__.py
|   |       +-- base.py         # AnalysisPlugin 抽象基类
|   |       +-- registry.py
|   |       +-- fft_analysis.py
|   |       +-- threshold_alert.py
|   |       +-- trend_predict.py
|   |
|   +-- tasks/                  # Celery 异步任务定义
|   |   +-- __init__.py
|   |   +-- celery_app.py       # Celery 应用实例配置
|   |   +-- alert_tasks.py      # 告警检查任务
|   |   +-- analysis_tasks.py   # FFT/模态分析等耗时计算
|   |   +-- report_tasks.py     # PDF/Excel 报表生成
|   |   +-- maintenance_tasks.py # 数据归档、连续聚合刷新
|   |
|   +-- ws/                     # WebSocket 实时推送
|   |   +-- __init__.py
|   |   +-- manager.py          # ConnectionManager：project_id -> [WebSocket]
|   |   +-- publisher.py        # Redis Pub/Sub 发布端（数据服务调用）
|   |   +-- endpoints.py        # FastAPI WebSocket endpoint /ws/data
|   |
|   +-- utils/                  # 纯工具函数，无业务依赖
|       +-- __init__.py
|       +-- time_utils.py       # 时区处理、时间戳转换
|       +-- minio_client.py     # MinIO 异步客户端封装
|       +-- validators.py       # 自定义 Pydantic 校验器
|
+-- alembic/                    # 数据库迁移
|   +-- versions/               # 迁移脚本（禁止手动修改已有脚本）
|   +-- env.py                  # 异步 Alembic 环境配置
|
+-- tests/
|   +-- conftest.py             # pytest fixture：async db session、test client
|   +-- test_auth.py
|   +-- test_data_ingest.py     # 重点：批量写入性能测试
|   +-- test_protocols.py       # 协议适配器单元测试
|
+-- scripts/
|   +-- init_db.py              # 初始化：创建 hypertable、连续聚合、RLS 策略
|   +-- model_convert.py        # IFC/OBJ -> GLB 转换脚本（Blender/IfcOpenShell）
|
+-- Dockerfile
+-- requirements.txt
+-- pyproject.toml              # 项目元数据 + pytest/black 配置
+-- docker-compose.yml          # 本地开发环境
```

---

## 2. 编码规范

### 2.1 Python 基础
- **版本**：Python 3.11+，必须使用 `async`/`await`，**禁止在 I/O 路径使用同步阻塞调用**
- **类型注解**：所有函数参数和返回值必须标注类型，复杂结构用 `TypedDict` 或 `dataclass`
- **导入排序**：标准库 -> 第三方 -> 本地模块，每组空一行
- **代码风格**：Black (`line-length=100`) + isort + ruff

### 2.2 异步铁律（违反者直接阻塞整个服务）

```python
# 绝对禁止：在 async 函数中使用同步 I/O
import requests  # 同步 HTTP
import time  # 同步睡眠


def bad_func():
    requests.get("http://example.com")  # 阻塞事件循环！
    time.sleep(1)


# 正确做法
import httpx  # 异步 HTTP 客户端
import asyncio


async def good_func():
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://example.com")
    await asyncio.sleep(1)
```

**常见陷阱清单**：
| 同步操作 | 异步替代方案 |
|----------|-------------|
| `requests` | `httpx.AsyncClient` / `aiohttp` |
| `time.sleep` | `asyncio.sleep` |
| `open()` 文件读写 | `aiofiles` |
| `psycopg2` | `asyncpg` / `sqlalchemy.ext.asyncio` |
| `pymongo` | `motor` |
| `redis-py` | `redis.asyncio` |
| `bcrypt` (同步) | 使用线程池 `await loop.run_in_executor(None, bcrypt.hashpw, ...)` |

### 2.3 数据库操作规范

```python
# database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = "postgresql+asyncpg://user:pass@postgres:5432/shm_db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,  # 高频场景需要大连接池
    max_overflow=30,
    pool_pre_ping=True,  # 自动检测断连
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


# dependencies.py
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**查询规范**：
```python
# 使用 select + async session
from sqlalchemy import select
from app.models.point import Point


async def get_points_by_project(db: AsyncSession, project_id: int):
    stmt = select(Point).where(Point.project_id == project_id, Point.is_active == True)
    result = await db.execute(stmt)
    return result.scalars().all()


# 禁止：使用 Query（SQLAlchemy 1.x 风格）
# db.query(Point).filter(...).all()  # 这是同步 API！
```

**高频批量写入（TimescaleDB）**：
```python
# 使用 asyncpg copy 或 executemany，禁止逐条 INSERT
import asyncpg


async def batch_insert_sensor_raw(pool: asyncpg.Pool, records: list[tuple]):
    # records: [(time, device_id, point_id, value, quality, metadata), ...]
    async with pool.acquire() as conn:
        await conn.copy_records_to_table(
            "sensor_raw",
            records=records,
            columns=["time", "device_id", "point_id", "value", "quality", "metadata"],
        )


# 批量大小建议：1000-5000 条/批，根据网络延迟调整
```

---

## 3. FastAPI 开发规范

### 3.1 路由组织

```python
# routers/data.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db, get_current_user, require_admin
from app.schemas.data import DataQuery, TimeSeriesOut
from app.services.data_service import DataService

router = APIRouter(prefix="/data", tags=["时序数据"])


@router.get("/timeseries", response_model=TimeSeriesOut)
async def get_timeseries(
    point_id: int = Query(..., description="测点ID"),
    start: datetime = Query(..., description="开始时间 ISO8601"),
    end: datetime = Query(..., description="结束时间 ISO8601"),
    interval: str = Query("1m", description="聚合间隔: 1s/1m/1h/1d"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 权限检查：用户是否有该测点所属项目的权限
    await DataService.check_permission(db, current_user, point_id)

    data = await DataService.query_timeseries(db, point_id, start, end, interval)
    return TimeSeriesOut(point_id=point_id, data=data)


@router.post("/ingest", status_code=204)
async def ingest_batch(
    payload: DataBatchIngest,
    db: AsyncSession = Depends(get_db),
    # 边缘网关使用 API Key 认证，非 JWT
    api_key: str = Header(..., alias="X-API-Key"),
):
    # 边缘网关批量数据接入端点，高频调用，必须极致轻量
    await DataService.verify_api_key(db, api_key)
    await DataService.batch_ingest(db, payload.readings)
    return
```

### 3.2 异常处理统一化

```python
# core/exceptions.py
from fastapi import HTTPException, status


class BizException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


# middleware.py 中全局捕获
@app.exception_handler(BizException)
async def biz_exception_handler(request, exc: BizException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )
```

### 3.3 响应格式统一

```python
# 所有 API 返回统一结构
{
    "code": "OK",  # 业务码，非 HTTP status
    "message": "success",
    "data": {...},  # 实际载荷
    "timestamp": "2026-08-13T10:15:00Z",
}

# core/middleware.py 中通过自定义 APIRoute 自动包装
```

---

## 4. 协议适配器开发规范

### 4.1 接口契约（绝对稳定）

```python
# plugins/protocols/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any


@dataclass
class RawReading:
    device_code: str  # 设备唯一编码，对应 devices.device_code
    point_code: str  # 测点编码，对应 points.point_code
    timestamp: datetime  # 采样时间戳（UTC）
    value: float
    unit: str = ""
    quality: str = "good"  # good | bad | uncertain
    raw_bytes: bytes = field(repr=False, default=b"")
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProtocolConfig:
    host: str = ""
    port: int = 0
    sample_interval_ms: int = 1000
    timeout_ms: int = 5000
    register_map: Dict[str, Any] = field(default_factory=dict)
    auth: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


class ProtocolAdapter(ABC):
    # 协议适配器抽象基类，所有具体适配器必须继承并实现
    name: str = "base"
    version: str = "1.0.0"
    supports_batch: bool = False  # 是否支持批量读取

    def __init__(self, config: ProtocolConfig):
        self.config = config
        self._connected = False
        self._last_error: str = ""

    @abstractmethod
    async def connect(self) -> None:
        # 建立异步连接，失败抛出 ConnectionError
        pass

    @abstractmethod
    async def read_batch(self) -> List[RawReading]:
        # 读取一轮数据，返回 RawReading 列表。
        # 必须在 sample_interval_ms 内完成，否则丢弃或标记 quality='late'
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        # 优雅关闭连接，释放资源
        pass

    async def health_check(self) -> Dict[str, Any]:
        return {"connected": self._connected, "last_error": self._last_error}

    def _now(self) -> datetime:
        return datetime.utcnow()
```

### 4.2 新增协议步骤

1. 在 `plugins/protocols/` 下新建 `{protocol_name}_adapter.py`
2. 继承 `ProtocolAdapter`，实现 `connect/read_batch/disconnect`
3. 类属性 `name` 必须与数据库 `devices.protocol` 字段值匹配
4. 在 `registry.py` 中无需手动注册，自动扫描发现
5. 必须提供单元测试：`tests/plugins/test_{protocol_name}.py`

### 4.3 示例：Modbus TCP 适配器

```python
# plugins/protocols/modbus_tcp.py
from pymodbus.client import AsyncModbusTcpClient
from .base import ProtocolAdapter, ProtocolConfig, RawReading


class ModbusTcpAdapter(ProtocolAdapter):
    name = "modbus_tcp"
    supports_batch = True

    def __init__(self, config: ProtocolConfig):
        super().__init__(config)
        self.client: AsyncModbusTcpClient | None = None

    async def connect(self):
        self.client = AsyncModbusTcpClient(
            host=self.config.host,
            port=self.config.port,
            timeout=self.config.timeout_ms / 1000,
        )
        await self.client.connect()
        self._connected = self.client.connected

    async def read_batch(self) -> list[RawReading]:
        if not self.client or not self.client.connected:
            raise ConnectionError("Modbus not connected")

        readings = []
        ts = self._now()

        for reg in self.config.register_map.get("registers", []):
            resp = await self.client.read_holding_registers(
                address=reg["address"], count=reg["count"], slave=reg.get("slave", 1)
            )
            if resp.isError():
                readings.append(
                    RawReading(
                        device_code=self.config.extra.get("device_code", ""),
                        point_code=reg["point_code"],
                        timestamp=ts,
                        value=0.0,
                        quality="bad",
                        raw_bytes=resp.encode(),
                    )
                )
                continue

            value = self._decode(resp.registers, reg["data_type"], reg.get("scale", 1.0))
            readings.append(
                RawReading(
                    device_code=self.config.extra.get("device_code", ""),
                    point_code=reg["point_code"],
                    timestamp=ts,
                    value=value,
                    unit=reg.get("unit", ""),
                    quality="good",
                )
            )
        return readings

    async def disconnect(self):
        if self.client:
            self.client.close()
            self._connected = False

    def _decode(self, registers: list[int], dtype: str, scale: float) -> float:
        if dtype == "uint16":
            return registers[0] * scale
        elif dtype == "float32":
            import struct

            b = struct.pack(">HH", registers[0], registers[1])
            return struct.unpack(">f", b)[0] * scale
        return 0.0
```

---

## 5. 时序数据服务开发规范

### 5.1 写入路径（高频优化）

```python
# services/data_service.py
import asyncpg
from datetime import datetime
from typing import List


class DataService:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    async def init_pool(self, dsn: str):
        self._pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )

    async def batch_ingest(self, readings: List[RawReading]):
        # 批量写入 sensor_raw，要求：
        # 1. 校验 device_code/point_code 存在性（可缓存到 Redis）
        # 2. 按 device_id/point_id 映射（避免前端传 ID）
        # 3. 使用 COPY 批量写入
        if not readings:
            return

        # 批量映射 code -> id（Redis 缓存加速）
        records = []
        for r in readings:
            records.append(
                (
                    r.timestamp,
                    r.device_code,  # 实际应映射为 device_id，此处简化
                    r.point_code,
                    r.value,
                    r.quality,
                    r.extra,
                )
            )

        async with self._pool.acquire() as conn:
            await conn.copy_records_to_table(
                "sensor_raw",
                records=records,
                columns=["time", "device_id", "point_id", "value", "quality", "metadata"],
            )

        # 同步写入 Redis 最新值（供实时查询）
        await self._update_redis_latest(readings)

        # 触发告警检查（异步 Celery，不阻塞写入）
        from app.tasks.alert_tasks import check_threshold_batch

        check_threshold_batch.delay([r.dict() for r in readings])
```

### 5.2 查询路径（智能路由）

```python
async def query_timeseries(
    self, db: AsyncSession, point_id: int, start: datetime, end: datetime, interval: str
) -> list[dict]:
    # 根据时间范围和间隔，自动选择最优数据源：
    # - interval <= 1s 且 时间跨度 < 1小时 -> sensor_raw
    # - interval >= 1m 或 时间跨度 > 1小时 -> sensor_feature_1min 连续聚合
    span_hours = (end - start).total_seconds() / 3600

    if interval in ("1s", "100ms") and span_hours <= 1:
        table = "sensor_raw"
        time_col = "time"
    else:
        table = "sensor_feature_1min"
        time_col = "bucket"

    # 使用 text() 执行优化后的原生 SQL，避免 ORM 开销
    sql = f"""
        SELECT {time_col} as ts, avg_val, max_val, min_val, rms_val
        FROM {table}
        WHERE point_id = $1 AND {time_col} BETWEEN $2 AND $3
        ORDER BY {time_col} ASC
    """
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(sql, point_id, start, end)
    return [dict(r) for r in rows]
```

---

## 6. Celery 任务开发规范

### 6.1 任务分类

| 类型 | 队列名 | 并发 | 说明 |
|------|--------|------|------|
| 实时告警 | `alerts` | 4 | 低延迟，检查阈值 |
| 分析计算 | `analysis` | 2 | CPU 密集型，FFT/ML |
| 报表生成 | `reports` | 2 | 可能耗时数分钟 |
| 系统维护 | `maintenance` | 1 | 数据归档、清理 |

### 6.2 任务定义模板

```python
# tasks/analysis_tasks.py
from celery import shared_task
from app.plugins.analyzers.registry import AnalyzerRegistry
import numpy as np


@shared_task(bind=True, queue="analysis", max_retries=3)
def run_fft_analysis(self, point_id: int, start_iso: str, end_iso: str, config: dict):
    # 执行 FFT 频谱分析任务
    try:
        # 1. 从数据库拉取原始数据（同步代码在 worker 中运行，使用同步 SQLAlchemy 或 psycopg2）
        raw_data = fetch_raw_data_sync(point_id, start_iso, end_iso)

        # 2. 执行分析
        analyzer = AnalyzerRegistry.get("fft")
        result = analyzer.analyze(
            data=np.array([r["value"] for r in raw_data]),
            sampling_rate=config.get("sampling_rate", 100),
        )

        # 3. 结果存入 MinIO / 数据库
        save_analysis_result(point_id, "fft", result)

        # 4. 推送完成通知（Redis Pub/Sub -> WebSocket）
        notify_completion(point_id, "fft", "success")

        return {"status": "success", "result_id": result.id}
    except Exception as exc:
        # Celery 自动重试
        raise self.retry(exc=exc, countdown=60)
```

---

## 7. WebSocket 开发规范

### 7.1 连接管理

```python
# ws/manager.py
from fastapi import WebSocket
from collections import defaultdict
import json
import redis.asyncio as redis


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)
        self._redis: redis.Redis | None = None

    async def init_redis(self, url: str):
        self._redis = await redis.from_url(url, decode_responses=True)
        # 启动广播监听协程
        asyncio.create_task(self._broadcast_listener())

    async def connect(self, websocket: WebSocket, project_id: int):
        await websocket.accept()
        self.active_connections[project_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, project_id: int):
        self.active_connections[project_id].remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_project(self, project_id: int, message: dict):
        # 通过 Redis Pub/Sub 实现多实例广播
        if self._redis:
            await self._redis.publish(f"project:{project_id}", json.dumps(message))

    async def _broadcast_listener(self):
        # 监听 Redis 频道，向本地 WebSocket 连接推送
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("project:*")
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                project_id = int(message["channel"].split(":")[1])
                data = json.loads(message["data"])
                # 向该项目的所有本地连接推送
                disconnected = []
                for ws in self.active_connections.get(project_id, []):
                    try:
                        await ws.send_text(json.dumps(data))
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    await self.disconnect(ws, project_id)
```

### 7.2 消息协议

```json
// 服务端 -> 客户端：实时数据
{
    "type": "data:realtime",
    "payload": {
        "point_id": 123,
        "value": 0.0234,
        "unit": "m/s2",
        "status": "normal",
        "timestamp": "2026-08-13T10:15:00.123Z"
    }
}

// 服务端 -> 客户端：告警
{
    "type": "data:alert",
    "payload": {
        "alert_id": 456,
        "point_id": 123,
        "level": "danger",
        "message": "加速度峰值超过阈值 0.5 m/s2",
        "value": 0.62,
        "threshold": 0.5
    }
}

// 客户端 -> 服务端：订阅项目
{
    "type": "cmd:subscribe",
    "project_id": 1
}
```

---

## 8. 测试规范

### 8.1 测试金字塔

```
        /\
       /  \      E2E 测试 (pytest + httpx.AsyncClient)
      /____\
     /      \    集成测试 (数据库 + Redis + MinIO)
    /________\
   /          \  单元测试 (协议适配器、分析算法、工具函数)
  /____________\
```

### 8.2 关键测试用例

```python
# tests/test_data_ingest.py
import pytest
import asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_batch_ingest_performance(client: AsyncClient, db_session):
    # 性能测试：验证 10000 条批量写入耗时 < 2s
    readings = generate_mock_readings(count=10000)

    start = asyncio.get_event_loop().time()
    resp = await client.post("/api/v1/data/ingest", json={"readings": readings})
    elapsed = asyncio.get_event_loop().time() - start

    assert resp.status_code == 204
    assert elapsed < 2.0


# tests/plugins/test_modbus_tcp.py
@pytest.mark.asyncio
async def test_modbus_adapter_decode():
    adapter = ModbusTcpAdapter(
        ProtocolConfig(
            host="mock",
            port=502,
            register_map={
                "registers": [
                    {
                        "address": 0,
                        "count": 2,
                        "data_type": "float32",
                        "point_code": "ACC-X",
                        "scale": 0.001,
                    }
                ]
            },
        )
    )
    # 使用 mock 的 Modbus 响应测试解码逻辑
    value = adapter._decode([0x4040, 0x0000], "float32", 0.001)
    assert abs(value - 3.0) < 0.001  # 3.0 * 0.001 = 0.003
```

---

## 9. 环境变量清单（.env 模板）

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://shm_user:shm_pass@postgres:5432/shm_db
TIMESCALE_ENABLED=true

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=shm-storage

# 安全
SECRET_KEY=your-256-bit-secret-key-here-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Celery
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# 边缘网关（仅在 edge-gateway 服务中使用）
EDGE_API_ENDPOINT=http://api:8000/api/v1/ingest
EDGE_API_KEY=edge-secret-key
```

---

## 10. 常见反模式（禁止清单）

| 反模式 | 后果 | 正确做法 |
|--------|------|----------|
| 在 async 路由中调用同步 ORM `db.query()` | 阻塞事件循环，所有请求排队 | 使用 `select()` + `await db.execute()` |
| 逐条 INSERT 高频数据 | 数据库连接耗尽，吞吐 < 100点/秒 | 批量 COPY，每批 1000-5000 条 |
| 在 Celery task 中创建新的 DB 连接而不关闭 | 连接泄漏，PostgreSQL 拒绝连接 | 使用上下文管理器确保关闭 |
| 协议适配器硬编码设备参数 | 新增设备必须改代码发版 | 通过 `ProtocolConfig.register_map` 配置化 |
| WebSocket 直接广播不经过 Redis | 多实例部署时消息丢失 | Redis Pub/Sub 作为跨实例广播层 |
| 返回数据库模型对象给前端 | 暴露敏感字段、循环引用序列化失败 | 必须通过 Pydantic Schema 转换 |
| 在路由中写复杂业务逻辑 | 难以测试、职责混乱 | 路由 < 20 行，逻辑下沉到 Service |
| 忽略数据库连接池配置 | 默认 pool_size=5，高频场景直接崩溃 | 显式配置 pool_size=20+, max_overflow=30 |
