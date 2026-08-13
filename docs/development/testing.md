# 测试

> SHM 平台后端 v0.2.0 · 更新于 2026-08-13

## 1. 测试金字塔

```
       /\
      /  \      E2E（冒烟 curl + uvicorn 真实启动）
     /____\
    /      \    集成（httpx AsyncClient + 真实 TimescaleDB/Redis）
   /________\
  /          \  单元（security / registry / adapters 等纯逻辑）
 /____________\
```

当前覆盖：
- 单元：`tests/test_security.py`（JWT + bcrypt）、`tests/test_protocols.py`（registry + http_json）
- 集成：`tests/test_auth_api.py`、`tests/test_projects_api.py`、`tests/test_data_ingest.py`（含 1 万条写入 < 2s 性能断言）
- E2E：见 `docs/development/setup.md` 第 2 节手工冒烟

## 2. pytest 配置（`pyproject.toml`）

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
testpaths = ["tests"]
```

**为什么用 session 级 event loop**：`app/services/data_service.py` 的全局 asyncpg/redis 连接池在首个测试里创建。若每个测试独立 loop，连接池会在第二个测试报 "attached to a different loop"。Session 级 loop 让连接池跨测试复用。

**Celery eager 模式**：`tests/conftest.py` 的 autouse fixture 临时开启 `task_always_eager=True` 与 `task_eager_propagates=True`，让 `check_threshold_batch.delay()` 在调用现场同步执行，配合 `nest_asyncio.apply()` 在已有事件循环内复用同一 loop，连接池正常工作。

## 3. Fixture（`tests/conftest.py`）

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `client` | function | `httpx.AsyncClient(ASGITransport(app))` 直连 ASGI，不启 uvicorn |
| `admin_user` | function | 在 DB 创建唯一 admin 用户（UUID 后缀），yield 后清理 |

辅助函数：

```python
async def login_headers(client, username, password) -> dict[str, str]:
    """登录并返回 {'Authorization': 'Bearer <token>'}。"""
```

集成测试**不**显式启动 lifespan（ASGITransport 不会触发），但 `data_service` 的全局资源是懒初始化的，访问接口时自动建池；多个测试间复用同一池。

## 4. 写测试的最佳实践

- 单元测试不依赖 DB / 网络；mock 外部协议响应（如 http_json 用 `httpx.MockTransport`）
- 集成测试使用唯一标识（UUID 后缀的 username / device_code），避免相互污染
- 时序数据插入用 `now - timedelta` 作为基线时间，重复运行不冲突
- 性能测试标记：当前未启用 marker；如需选择性执行，配置 `addopts = "-m 'not performance"`

## 5. 常用命令

```bash
.venv/bin/python -m pytest                         # 全量
.venv/bin/python -m pytest -v                      # 详细
.venv/bin/python -m pytest tests/test_security.py  # 单文件
.venv/bin/python -m pytest -k "ingest"             # 按名字匹配
.venv/bin/python -m pytest -x                      # 遇失败立即停止
```

## 6. 新增测试

- 新接口：在对应 `tests/test_<domain>_api.py` 加测试，参考 `test_auth_api.py` 的模式
- 新协议适配器：在 `tests/plugins/` 下创建 `test_<protocol>.py`（AGENTS.md 第 8.2 节要求）
- 新分析插件：在 `tests/plugins/` 下加解码 / 边界用例

## 7. 测试数据库策略

集成测试**直接连** `docker compose` 拉起的 `shm_db`（同一份开发库）。优点：与迁移脚本同源；缺点：测试残留数据。

清理策略：
- 用户/项目/设备/测点：fixture yield 后通过 `db.delete` 清理
- 时序数据：用唯一时间窗口（`now - timedelta`）避免 PK 冲突，长期保留不影响测试

生产化建议（v0.5+）：
- 引入 `shm_db_test` 独立库，CI 中跑迁移
- 用 `pytest-postgresql` / `testcontainers` 自动管理生命周期