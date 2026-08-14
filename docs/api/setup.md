# 首次部署引导

> v0.9.1 · 更新于 2026-08-13

系统在**未初始化**（`users` 表为空）时开放以下端点供首次部署创建管理员。任意用户存在后端点返回 `409 ALREADY_INITIALIZED`。

## 数据模型

无（写入 `users` 表的标准 schema）。

## 端点

### GET /api/v1/setup/status

任意时刻可访问（无需鉴权）。前端 setup 页面可轮询。

**响应 200**
```json
{
  "code": "OK",
  "data": {
    "initialized": false,
    "password_requirements": {
      "min_length": 8,
      "require_letter": true,
      "require_digit": true,
      "description": "密码至少 8 个字符，且同时包含字母和数字"
    }
  }
}
```

### POST /api/v1/setup/init-admin

创建第一个 admin 用户。

**请求**
```json
{
  "username": "admin",
  "email": "admin@example.com",
  "password": "admin12345"
}
```

字段约束：
- `username`：3-64 字符，匹配 `^[A-Za-z0-9_.-]+$`
- `email`：标准邮箱
- `password`：≥8 字符 + 至少一个字母 + 至少一个数字

**响应 201**
```json
{
  "code": "OK",
  "data": {
    "admin_id": 1,
    "username": "admin",
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  }
}
```

**错误**

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | `users` 已有用户时 setup 阶段不应被任意请求触发（虽未做 IP 限制，但 v0.7+ 加 rate limit） |
| 409 | `ALREADY_INITIALIZED` | `users` 表非空 |
| 422 | `WEAK_PASSWORD` | 密码不满足策略（缺字母/缺数字） |
| 422 | `VALIDATION_ERROR` | Pydantic 字段校验失败（username pattern、email 格式、password 长度 < 8） |

## 守卫机制

- 路由**不**挂 `get_current_user` 依赖（setup 阶段无用户）
- service 内部 `select(func.count(User.id))` 严格判断 `count == 0`
- **并发防护**：service 二次检查 `count == 0`（防止两个 init 请求同时进入）
- **DB 唯一约束兜底**：`users.username` / `users.email` 唯一（已有 user_projects 引用外键）
- 端点**不删除**（删除路径会破坏脚本幂等性）；已初始化后永远 409

## CLI：scripts/init_admin.py

```bash
# 交互式
python -m scripts.init_admin --base-url http://localhost:8000

# 非交互（Docker / CI）
ADMIN_USERNAME=admin \
ADMIN_EMAIL=admin@example.com \
ADMIN_PASSWORD='admin12345' \
  python -m scripts.init_admin --base-url http://localhost:8000
```

退出码：
- 0  成功（新建 admin）或已初始化（幂等）
- 1  服务端拒绝（弱密码 / 已存在等）
- 2  网络错误（API 不可达）
- 3  参数错误

## Docker 首次部署

`docker-compose.yml` 的 `api` 服务用 `docker/entrypoint.sh`：
1. 等 Postgres 可达（最多 30s）
2. 若 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 环境变量已设置，调用 `init_admin.py`
3. 启动 uvicorn

**生产推荐用 Docker Secrets 注入凭据**，避免写入 compose 文件：

```yaml
api:
  environment:
    ADMIN_USERNAME: admin
    ADMIN_PASSWORD_FILE: /run/secrets/admin_password  # 挂载的 secret
```

## 安全建议（部署后）

1. 立即修改 `.env` 中的 `SECRET_KEY`（生产 256 位随机）
2. 立即修改 `EDGE_API_KEY`
3. 通过 admin 控制台添加额外的运维账号，禁用默认 admin
4. 开启 HTTPS（Nginx 终止 TLS）
5. 启用 audit log（v0.7+）

## 未实现（v0.7+）

- 首次登录强制修改密码
- 邮箱验证 / 找回密码
- zxcvbn 密码强度评分
- 多 admin 邀请
- 国际化 setup 错误消息