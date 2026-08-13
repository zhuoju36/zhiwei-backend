#!/bin/sh
# Docker entrypoint：等 Postgres 健康 + 可选自动 init-admin + 启动 CMD
set -e

# 等 Postgres 可达（compose healthcheck 已确保 readiness，这里做双保险）
for i in $(seq 1 30); do
  if .venv/bin/python -c "import socket; s=socket.socket(); s.connect(('postgres', 5432)); s.close()" 2>/dev/null; then
    break
  fi
  sleep 1
done

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
