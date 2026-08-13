# 开发环境

> SHM 平台后端 v0.3.0 · 更新于 2026-08-13

## 1. 工具要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 推荐 3.12，使用 `uv` 管理 |
| Docker Desktop | 最新 | 已开启 WSL 集成（Linux 用户直接装 docker-ce） |
| Git | 任意 | 仓库使用 git |
| `uv` | 最新 | `pip install uv` 或从 GitHub release 下载单文件 |

## 2. 首次克隆后

```bash
# 克隆与进入
git clone <repo> && cd shm-backend

# 安装托管 Python + 创建虚拟环境
uv python install 3.12
uv venv --python 3.12 .venv

# 安装依赖（中科大源，AGENTS.md 要求）
uv pip install -r requirements.txt -i https://mirrors.ustc.edu.cn/pypi/simple

# 启动基础设施
docker compose up -d postgres redis minio

# 等待 Postgres 健康
docker inspect -f '{{.State.Health.Status}}' shm-postgres
# healthy 后继续

# 应用迁移 + TimescaleDB 初始化 + 种子数据
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.init_db
.venv/bin/python -m scripts.seed

# 启动 API（开发模式）
.venv/bin/python -m uvicorn app.main:app --reload
```

启动后访问：
- `http://localhost:8000/health` — 健康检查
- `http://localhost:8000/docs` — Swagger UI
- `http://localhost:8000/redoc` — ReDoc

## 3. 环境变量

`.env` 文件由 `.env.example` 复制；详见 `app/config.py:Settings`。

| 变量 | 默认 | 说明 |
|------|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://shm_user:shm_pass@localhost:5432/shm_db` | SQLAlchemy 异步 DSN |
| `TIMESCALE_ENABLED` | `true` | 是否启用 TimescaleDB 特性 |
| `REDIS_URL` | `redis://localhost:6379/0` | 缓存 + Pub/Sub |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET` | 见 `.env.example` | 对象存储 |
| `SECRET_KEY` | `dev-only-secret-key-change-in-production` | JWT 签名密钥，生产必须替换 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | access token 过期时间 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | refresh token 过期时间 |
| `EDGE_API_KEY` | `edge-secret-key` | 边缘网关接入 API Key |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | redis db1 / db2 | Celery broker / result |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 前端域名列表；生产禁止 `["*"]` |

`Settings.asyncpg_dsn` 自动把 `postgresql+asyncpg://` 转为 `postgresql://`，供 asyncpg 原生使用。

## 4. 容器内服务清单（开发用）

| 服务 | 容器名 | 端口 | 用途 |
|------|--------|------|------|
| TimescaleDB | `shm-postgres` | 5432 | 主数据库（含 TimescaleDB 2.x 扩展） |
| Redis | `shm-redis` | 6379 | 缓存 / Pub/Sub / Celery broker |
| MinIO | `shm-minio` | 9000 / 9001 | 对象存储（控制台在 9001） |
| API | `shm-api` | 8000 | 仅在容器化部署时使用 |
| Worker | `shm-worker` | — | Celery 4 队列消费者 |

常用命令：

```bash
docker compose ps                    # 查看状态
docker compose logs -f postgres      # 查看日志
docker compose restart postgres      # 重启单个服务
docker compose down                  # 停止所有服务（保留卷）
docker compose down -v               # 停止并清理卷（数据丢失）
```

## 5. 常用开发命令

```bash
# 启动
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Celery worker（开发调试）
.venv/bin/celery -A app.tasks.celery_app:celery_app worker -Q alerts,analysis,reports,maintenance -c 4 -l info

# 测试
.venv/bin/python -m pytest                  # 全量
.venv/bin/python -m pytest tests/test_security.py  # 单文件
.venv/bin/python -m pytest -k "ingest"      # 按关键字

# 数据库
.venv/bin/alembic revision --autogenerate -m "msg"   # 生成迁移（审查后再应用）
.venv/bin/alembic upgrade head              # 应用迁移
.venv/bin/alembic downgrade -1              # 回退一步

# 工具脚本
.venv/bin/python -m scripts.init_db         # TimescaleDB 初始化（幂等）
.venv/bin/python -m scripts.seed            # 种子数据

# 代码质量
.venv/bin/ruff check --fix .
.venv/bin/ruff format .
```

## 6. IDE 配置建议

- **Pylance / mypy**：项目使用 SQLAlchemy 2.0 `Mapped[]` 注解，配置 `pythonVersion = "3.12"`
- **pytest**：自动发现，async 模式由 `pyproject.toml` 配置
- **Docker 扩展**：绑定 `docker-compose.yml` 直接管理容器