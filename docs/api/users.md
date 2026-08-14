# 用户管理

> v0.9.3 · 更新于 2026-08-14

**仅 admin** 可调用。普通用户调用全部返回 `403 FORBIDDEN`。v0.7 不实现用户自服务（`/auth/me`、改自己密码）——留给 v0.9+。

## 数据模型

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-08-14T09:00:00+00:00"
}
```

## 端点

### GET /api/v1/users

列表（分页 + 过滤）。

**Query**

| 参数 | 默认 | 说明 |
|------|------|------|
| `username` | — | 精确匹配 |
| `role` | — | `admin` / `user` |
| `is_active` | — | true / false |
| `page` | 1 | ≥1 |
| `size` | 20 | 1-200 |

**响应 200** 标准 `PageSchema[UserOut]`。

### POST /api/v1/users

创建用户（admin 可指定 role）。

**请求**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "alice12345",
  "role": "user"
}
```

字段约束：username 3-64 / email 邮箱 / password ≥8 / role 默认 user。

**错误**

| HTTP | code | 说明 |
|------|------|------|
| 409 | `USER_EXISTS` | username 重复 |
| 409 | `EMAIL_EXISTS` | email 重复 |

### GET /api/v1/users/{id}

详情。`404 USER_NOT_FOUND` 若不存在。

### PUT /api/v1/users/{id}

更新 email / role / is_active（密码走单独端点）。所有字段可选。

**自保护守卫**（admin 操作自己）

| 操作 | 结果 |
|------|------|
| `role=user` 改自己 | `409 SELF_PROTECTED` |
| `is_active=false` 改自己 | `409 SELF_PROTECTED` |
| DELETE 自己 | `409 SELF_PROTECTED` |

**最后 admin 守卫**（admin 操作其他 admin → 让自己变非 admin）

| 场景 | 结果 |
|------|------|
| 仅剩 1 个 admin 时把它降级 / 停用 / 删除 | `409 LAST_ADMIN` |

> SELF_PROTECTED 检查优先于 LAST_ADMIN；admin 操作自己时先返回 SELF_PROTECTED。

### DELETE /api/v1/users/{id}

删除用户。`204 No Content`。禁止：自己 + 最后 admin（见上）。

### POST /api/v1/users/{id}/password

重置密码（admin 无需原密码）。

**请求**
```json
{ "new_password": "new-pass-123" }
```

**响应 204**。`422` 若密码不满足 ≥8 字符。

## 完整错误码

| code | HTTP | 说明 |
|------|------|------|
| `AUTH_ERROR` | 401 | 未登录 / token 无效 |
| `FORBIDDEN` | 403 | 非 admin |
| `USER_NOT_FOUND` | 404 | 用户不存在 |
| `USER_EXISTS` | 409 | 创建时 username 重复 |
| `EMAIL_EXISTS` | 409 | 创建/更新 email 重复 |
| `SELF_PROTECTED` | 409 | admin 操作自己（改 role / 停用 / 删除） |
| `LAST_ADMIN` | 409 | 操作会让系统失去最后一个 admin |

## 自服务（未实现，v0.9+ 候选）

- `GET /api/v1/auth/me` — 获取自己的资料
- `PUT /api/v1/auth/me` — 改自己 email / display name
- `POST /api/v1/auth/password` — 改自己密码（需原密码）

## 审计

修改 role / 重置密码 / 删除 / 停用 全部在 `app.services.user_service` 记 warning 日志（含 operator / target）。v0.9+ 加 `audit_logs` 表。