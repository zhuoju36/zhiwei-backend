# 代码审查 Issue 清单（2026-08-13）

审查范围：最近三次提交

- `121069ea` feat: protocol adapters v0.3.0
- `dd3a9f7b` feat: analysis task pipeline v0.6.0
- `dcc27d21` fix(ws): accept handshake before receive_text

图例：🔴 Critical ｜ 🟠 Major ｜ 🟡 Minor ｜ ⚪ Nit

---

## P0 — 阻塞交付，优先修复

### 1. 🔴 Modbus 适配器在 pymodbus 3.14 下完全无法读取数据

- **提交**: `121069ea`
- **位置**: `app/plugins/protocols/modbus_tcp_adapter.py:117`
- **问题**: `read_holding_registers(..., slave=...)` 中的 `slave` 参数在 pymodbus 3.14 已改名为 `device_id`，每次读取抛 `TypeError`，被单点 `except Exception` 吞掉，**所有测点永远返回 `value=0.0, quality="bad"`**。单测 mock 的签名编码了同样的错误假设，测不出来。
- **修复建议**: 改用 `device_id=`（或 pin `pymodbus<3.14`）；补充对真实 pymodbus 签名的测试（如修 simulator 后做 E2E 冒烟）。

### 2. 🔴 分析任务带时间范围参数必然失败

- **提交**: `dd3a9f7b`
- **位置**: `app/tasks/analysis_tasks.py:37-46`
- **问题**: `params.start`/`end` 的 ISO 字符串直接传给 asyncpg 查询 `timestamptz` 列，asyncpg 对 `str` 抛 `TypeError: expected a datetime...`。带时间范围的 job 必挂，且最终卡在 `running`（见 Issue 3）。无测试覆盖此路径。
- **修复建议**: 查询前解析 ISO 字符串为 `datetime`（参考 `alert_tasks._parse_ts` 已有模式）；在 `AnalysisJobCreate.params` 边界做校验。

### 3. 🟠 分析任务失败后永久卡在 running 状态

- **提交**: `dd3a9f7b`
- **位置**: `app/tasks/analysis_tasks.py:117-121`
- **问题**: `mark_failed` 只处理 plugin-not-found 和样本不足两种情况，其余异常经 `max_retries=2` 重试耗尽后，任务行不被更新，状态永久 `running`，`/result` 永远返回 409。
- **修复建议**: 最后一次重试（`self.request.retries >= self.max_retries`）时调用 `mark_failed` 再放弃。

### 4. 🟠 Alembic 迁移误删 TimescaleDB 三个索引

- **提交**: `dd3a9f7b`
- **位置**: `alembic/versions/6c0943361e16_add_analysis_jobs.py:39-41`
- **问题**: autogenerate 删除了 `idx_sensor_raw_device_point`、`sensor_raw_time_idx`、`sensor_feature_time_idx`——正是 `scripts/init_db.py:22` 为高频查询建的索引，且迁移已应用到开发库。违反 AGENTS.md「审查自动生成的 Alembic 迁移文件」规则。
- **修复建议**: 移除迁移中的 `drop_index` 语句；新写一个迁移恢复已被删的索引。

### 5. 🟠 GET /jobs 不做过滤，泄露跨项目任务元数据

- **提交**: `dd3a9f7b`
- **位置**: `app/routers/analysis.py:51-72`
- **问题**: 不传 `point_id` 时无任何项目过滤，任意登录用户可列出全系统任务（point_id、plugin、params、error），与路由注释声称的权限模型矛盾。现有权限测试只用了 admin，测不出来。
- **修复建议**: 非 admin 用户按有读权限的项目过滤 `list_jobs`；补非 admin 用户的权限测试。

---

## P1 — 应当修复

### 6. 🟠 nest_asyncio.apply() 污染 FastAPI 进程

- **提交**: `dd3a9f7b`
- **位置**: `app/tasks/analysis_tasks.py:28`
- **问题**: 模块顶层 `nest_asyncio.apply()` 随 router import 在 uvicorn 进程内执行，全局替换 `asyncio.Task/Future` 为纯 Python 实现并 patch 事件循环策略——web 进程根本不需要它（router 只调 `.delay()`）。与 `alert_tasks.py:9-11` 确立的约定相反。
- **修复建议**: 挪到 Celery worker 入口（如 `worker_process_init` signal）。

### 7. 🟠 分析任务无时间范围时全表拉取 sensor_raw，可能 OOM worker

- **提交**: `dd3a9f7b`
- **位置**: `app/tasks/analysis_tasks.py:48-49`
- **问题**: `SELECT value FROM sensor_raw WHERE point_id = $1` 无 `LIMIT`，长历史测点的全量数据进入 worker 内存。
- **修复建议**: 强制时间范围或加行数上限。

### 8. 🟠 WebSocket 订阅无项目级授权

- **提交**: `dcc27d21`（旧有问题，本次重构该路径时未处理）
- **位置**: `app/ws/endpoints.py:39`
- **问题**: 任何有效 token 持有者可订阅任意 `project_id` 的实时数据流。代码里只有 TODO，但这是该端点唯一的实质安全缺口。
- **修复建议**: subscribe 时校验用户对该项目的读权限；不应只留 TODO，需排期实现。

### 9. 🟠 MQTT connect() 假连接 + 状态永不更新

- **提交**: `121069ea`
- **位置**: `app/plugins/protocols/mqtt_adapter.py:53-68`
- **问题**: `connect()` 只创建后台任务就置 `_connected=True`；broker 不可达时 `connect()` 不抛 `ConnectionError`（违反基类契约）；listener 挂掉后无重连、状态不更新，`health_check` 永远误报 connected。
- **修复建议**: `connect()` 等待首次连接成功/失败信号；listener 退出时重置 `_connected` 并考虑重连。

### 10. 🟠 MQTT use_tls: true 静默不启用 TLS

- **提交**: `121069ea`
- **位置**: `app/plugins/protocols/mqtt_adapter.py:60-61`
- **问题**: 传 `tls_context=None`，aiomqtt 仅在有真实 `ssl.SSLContext` 时启用 TLS，用户得到明文连接且无警告。
- **修复建议**: `use_tls` 时用 `ssl.create_default_context()` 或直接报错。

### 11. 🟠 run_edge_adapter 默认模式（无限循环）实际运行零次

- **提交**: `121069ea`
- **位置**: `scripts/run_edge_adapter.py:97`
- **问题**: `--max-iterations` 默认 0 意为「无限」，但 `range(0)` 直接退出，默认调用读不到任何数据。
- **修复建议**: `0` 时改 `while True` / `itertools.count()`。

### 12. 🟠 simulate_data.py 无 JWT，对真实 API 永远 401

- **提交**: `121069ea`
- **位置**: `scripts/simulate_data.py:38-58`
- **问题**: `GET /devices`、`/points` 需要 JWT，脚本只有 edge `X-API-Key`，`fetch_points` 永远失败返回空。该「最快端到端演示」路径未冒烟验证过；另硬编码 `project_id=1`。
- **修复建议**: 增加登录步骤获取 token，或提供专用只读端点。

---

## P2 — 建议修复

### 13. 🟡 GET /api/v1/protocols 无认证

- **提交**: `121069ea`
- **位置**: `app/routers/protocols.py:13`
- **问题**: 全项目唯一无认证的 `/api/v1` 业务端点，偏离项目模式（载荷低敏感）。

### 14. 🟡 未知 data_type 静默按 uint16 解码且标 quality="good"

- **提交**: `121069ea`
- **位置**: `app/plugins/protocols/modbus_tcp_adapter.py:111`
- **问题**: 配置笔误（如 `"float"`）变成自信的错误数据。应标 `quality="bad"` 或配置期报错。

### 15. 🟡 ProtocolConfig.register_map 传递但从未被读取

- **提交**: `121069ea`
- **位置**: `scripts/run_edge_adapter.py:31-33`，`app/plugins/protocols/modbus_tcp_adapter.py:87`
- **问题**: 两个新适配器实际从 `config.extra` 读寄存器/topic，与 AGENTS.md 示例矛盾。统一契约。

### 16. 🟡 分析路由 broker 失败静默吞掉

- **提交**: `dd3a9f7b`
- **位置**: `app/routers/analysis.py:43-47`
- **问题**: `except Exception: pass`，注释声称「回滚状态」实际什么都没做，任务永远 pending；也吞掉 eager 模式异常。至少 `logger.exception`。

### 17. 🟡 minio_client.close() 未重置 _initialized

- **提交**: `dd3a9f7b`
- **位置**: `app/utils/minio_client.py:58-61`
- **问题**: `close()` 内 `_initialized = False` 只绑定了局部变量，之后 `init()` 会直接 return。补 `global _initialized`。

### 18. 🟡 分析任务硬编码 FFT 私有键，对未来插件不健壮

- **提交**: `dd3a9f7b`
- **位置**: `app/tasks/analysis_tasks.py:95-98`
- **问题**: `result.pop("_internal_frequencies")` 和 `params["sampling_rate"]` 对不遵守该私有约定的插件抛 `KeyError` 进重试循环。用 `.pop(key, None)` 加守卫。

### 19. 🟡 WS 新测试文件含死代码且硬编码凭据

- **提交**: `dcc27d21`
- **位置**: `tests/test_ws_handshake.py:24-31`
- **问题**: `_get_token()` 引用不存在的 `app.main.full_app`，硬编码 `admin/admin123456`。直接删除。

### 20. 🟡 测试质量问题（多个）

- **提交**: `121069ea`
- `tests/test_mqtt_adapter.py:84-101` — disconnect 测试空转：MagicMock 不可 await，`TypeError` 被吞，await 路径从未执行。
- `tests/test_simulators.py:50` — `isoform=` 拼写错误，断言从未真正生效。
- 无测试覆盖 MQTT connect/_listen 生命周期、`run_loop` 默认参数路径。

### 21. ⚪ 其他小项

- `app/routers/analysis.py:63-64` — 重复调用 `check_point_project(point_id)`，多一次 DB 往返。
- `app/routers/analysis.py:81-82, 90-91` — point/device 在任务创建后被删时 `.device_id` 抛 `AttributeError` 500，应返回 404/410。
- `app/schemas/analysis.py:14` — `params` 完全无校验，`sampling_rate` 应边界校验返回 422。
- `alembic/versions/6c0943361e16_add_analysis_jobs.py` — `analysis_jobs(point_id)`、`status` 无索引（当前规模可接受，记录备查）。
- `tests/test_minio_client.py` — 依赖真实 MinIO 无 skip guard，无服务环境下 CI 失败而非跳过。
- `app/services/device_service.py:77-81` — update 的 422 消息缺少 create 有的可用协议列表。
- `scripts/run_edge_adapter.py:6-9` — docstring 示例缺必需参数；`fetch_device_config` 是 `NotImplementedError` 死代码。
- `scripts/modbus_simulator.py:104-107` — cancel 后未 await，退出时有 pending task 警告。
- `app/ws/endpoints.py:36-38` — 一条畸形消息静默断开整个连接（pre-existing），建议 per-message try/except。
- `app/ws/manager.py:50-56` — 广播遍历时列表可能被并发修改（pre-existing），建议快照迭代。
- `AGENTS.md` §7.1 — `ConnectionManager.connect()` 示例仍含 `accept()`，与 dcc27d21 确立的新约定矛盾，需同步更新。

---

## 共性根因与建议

1. **Mock 测试编码假设而非真实库契约**：Issue 1、20 都是 mock 照着错误假设写，真实调用签名从未被测试触达。建议对协议适配器增加基于真实库（或修好的 simulator/broker）的冒烟测试。
2. **E2E 冒烟缺失**：v0.3 的演示链路（simulate_data、run_edge_adapter 默认模式）交付时从未真正跑通。
3. **Alembic autogenerate 未审查**：Issue 4 正是 AGENTS.md 已有规则要防的事故，建议迁移 review 列入 checklist。
