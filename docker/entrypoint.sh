#!/bin/sh
# Docker entrypoint：等 Postgres 健康 → 数据库迁移/初始化 → 可选 init-admin → 启动 CMD
set -e

# 容器内使用项目 venv（.venv/bin/），与本地开发布局一致
export PATH="/app/.venv/bin:$PATH"

# 等 Postgres 可达（compose healthcheck 已确保 readiness，这里做双保险）
for i in $(seq 1 30); do
  if .venv/bin/python -c "import socket; s=socket.socket(); s.connect(('postgres', 5432)); s.close()" 2>/dev/null; then
    break
  fi
  sleep 1
done

# 数据库迁移（幂等：已到最新版本则无操作）+ TimescaleDB 初始化（hypertable/保留策略，幂等可重入）。
# 迁移失败直接退出（表结构不对时启动服务没有意义）；init_db 依赖 DATABASE_URL 环境变量。
echo "[entrypoint] 应用数据库迁移 (alembic upgrade head)..."
.venv/bin/alembic upgrade head
echo "[entrypoint] TimescaleDB 初始化 (hypertable / 保留策略)..."
.venv/bin/python -m scripts.init_db

# 仅当 env 提供 ADMIN_USERNAME + ADMIN_PASSWORD 时自动调 init_admin
# （生产建议用 Docker Secrets / Vault 注入，参考 docs/development/deployment.md）
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  echo "[entrypoint] 检测到 ADMIN_USERNAME/ADMIN_PASSWORD，自动调用 init_admin.py"
  ADMIN_USERNAME="$ADMIN_USERNAME" \
  ADMIN_EMAIL="${ADMIN_EMAIL:-${ADMIN_USERNAME}@shm.local}" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    .venv/bin/python -m scripts.init_admin --base-url "http://127.0.0.1:8000" || {
      echo "[entrypoint] init_admin 返回非零退出码，继续启动（用户可手动调端点）" >&2
    }
fi

exec "$@"
