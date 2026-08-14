# 部署

> SHM 平台后端 v0.9.1 · 更新于 2026-08-13

## 1. 镜像构建

`Dockerfile` 基于 `python:3.12-slim`：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建：

```bash
docker build -t shm-backend:0.1.0 .
```

镜像较大时考虑多阶段构建 + `pip install --user`；当前单阶段 + `--no-cache-dir` 已足够。

## 2. Compose 服务清单（`docker-compose.yml`）

| 服务 | 镜像 | 端口 | 健康检查 |
|------|------|------|----------|
| `postgres` | `timescale/timescaledb:latest-pg15` | 5432 | `pg_isready` |
| `redis` | `redis:7-alpine` | 6379 | `redis-cli ping` |
| `minio` | `minio/minio:latest` | 9000 / 9001 | — |
| `api` | `Dockerfile` | 8000 | depends_on |
| `worker` | `Dockerfile` | — | depends_on |

启动：

```bash
docker compose up -d postgres redis minio   # 仅基础设施
docker compose up -d api worker            # 容器化运行时再加
```

## 3. 环境变量

容器启动时由 `.env` 注入；生产部署建议用 Docker Secrets / Kubernetes ConfigMap / Vault 注入敏感字段（特别是 `SECRET_KEY` 和 `EDGE_API_KEY`）。

容器内服务的 DSN 必须用容器名（而非 `localhost`）：

```yaml
environment:
  DATABASE_URL: postgresql+asyncpg://shm_user:shm_pass@postgres:5432/shm_db
  REDIS_URL: redis://redis:6379/0
```

开发机的 `.env` 用 `localhost`。

## 4. Worker 启动

```bash
celery -A app.tasks.celery_app:celery_app worker \
    -Q alerts,analysis,reports,maintenance -c 4 -l info
```

注意：Celery task 函数内**必须自己管理 DB 连接**（不能复用 FastAPI 的 session 注入），用 `with engine.connect()` 或独立 async_session。

## 5. 数据库迁移流水线

建议部署顺序：

```bash
1. docker compose up -d postgres redis minio
2. 等待 postgres health: healthy
3. .venv/bin/alembic upgrade head
4. .venv/bin/python -m scripts.init_db
5. docker compose up -d api worker
```

生产推荐用独立 migration job 容器（一次性执行后退出），不要让 API 容器启动时自动跑迁移。

## 6. 反向代理 / Nginx

架构说明书第 3.1 节给出 Nginx 拓扑。关键点：

- `/api/*` 反代到 `api:8000`
- `/ws/data` 反代到 `api:8000/ws/data`，并设置 `Upgrade` / `Connection` 头
- `/` 托管前端静态资源

最小 Nginx 片段（仅 API + WS）：

```nginx
upstream shm_api { server api:8000; }

server {
    listen 80;
    location /api/ {
        proxy_pass http://shm_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /ws/ {
        proxy_pass http://shm_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 6. 边缘网关接入

架构说明书第 10.1 节定义边缘网关为独立 Docker / 工控机进程。`v0.3` 提供**参考实现** `scripts/run_edge_adapter.py`，演示完整调用模式：

- 接收 `--device-code`、`--protocol`、`--host`、`--port` 参数
- 从 `AdapterRegistry.get(protocol)` 实例化适配器
- 循环 `connect → read_batch → POST /api/v1/data/ingest → sleep`
- Ctrl+C 优雅关闭

**生产部署时不应直接使用参考脚本**，应：
1. 拆为独立服务（FastAPI 进程外 / 独立 Docker / 工控机部署）
2. 实现断网本地缓存（SQLite/Redis）与恢复后补发
3. 接入设备健康监控与配置热更新

参考运行命令（配合 modbus_simulator 演示）：

```bash
.venv/bin/python -m scripts.modbus_simulator --port 5020 --rate-hz 2 &
.venv/bin/python -m scripts.run_edge_adapter \
    --device-code GW-MODBUS-DEMO \
    --protocol modbus_tcp \
    --host 127.0.0.1 --port 5020
```

## 告警配置（.env，v0.5+）

```bash
# Webhook 通道
WEBHOOK_URL=                     # 例: https://oapi.dingtalk.com/robot/send?access_token=...
WEBHOOK_HEADERS=                 # JSON 字符串，如 '{"X-Custom":"v1"}'
WEBHOOK_TIMEOUT_SECONDS=10

# Email 通道
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_FROM=                        # 默认等于 SMTP_USER
ALERT_EMAIL_TO=                  # 逗号分隔
```

任一通道未配置则跳过；告警新建 / 重开时多通道并发派发，失败隔离。详见 [notifications.md](../../api/notifications.md)。

## 7. 安全清单

部署前必须确认：

- [ ] `SECRET_KEY` 已替换为 256 位随机字符串
- [ ] `EDGE_API_KEY` 已替换
- [ ] `CORS_ORIGINS` 收敛到生产前端域名（删除 `*`）
- [ ] 数据库密码 / MinIO 密码已替换为强密码
- [ ] HTTPS / WSS 终止由 Nginx 完成
- [ ] Postgres / Redis / MinIO 仅监听内网端口
- [ ] `pg_hba.conf` 仅允许应用网段
- [ ] 数据库启用定期备份（`pg_dump` + MinIO / S3 归档）

## 8. 监控建议（v0.5+）

- 应用 metrics：`prometheus-fastapi-instrumentator` + `/metrics`
- 数据库：`pg_stat_statements` + TimescaleDB 官方仪表盘
- Redis：`redis_exporter`
- 业务：自定义告警（阈值越界、写入延迟、连接池饱和度）

## 9. 容量规划基线

来自架构说明书第 12 节：

| 指标 | 目标 |
|------|------|
| 高频写入 | 10万点/秒 |
| 实时查询延迟 | < 100ms |
| 历史查询（1天） | < 2s |
| 3D 模型加载 | < 5s（100MB GLB） |
| WebSocket 并发 | 500+ |
| 可用性 | 99.9% |

垂直扩展（更强机器）到一定阶段后瓶颈在 Postgres，可水平扩展为读副本；时序写入保留主库即可。