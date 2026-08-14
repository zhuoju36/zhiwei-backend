# 认证

> v0.8.0 · 更新于 2026-08-13

## POST /api/v1/auth/login

使用 OAuth2 Password Flow 获取令牌对。

### 请求

`Content-Type: application/x-www-form-urlencoded`

| 字段 | 必填 | 说明 |
|------|------|------|
| `username` | 是 | 用户名 |
| `password` | 是 | 密码 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  },
  "timestamp": "2026-08-13T12:34:56.789+00:00"
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 用户名或密码错误 / 用户已停用 |

### curl 示例

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
    -d 'username=admin&password=admin123456'
```

---

## POST /api/v1/auth/refresh

用 refresh token 换取新令牌对（access 重新计时，refresh 重置）。

### 请求

`Content-Type: application/json`

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### 响应 200

同 `/auth/login`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | refresh token 无效、过期或类型错误 |

---

## 后续请求携带令牌

```http
Authorization: Bearer <access_token>
```

access token 默认 15 分钟过期；过期前主动调用 `/auth/refresh` 续期。客户端实现建议：

- 拦截 401 响应，先尝试 refresh，重试原请求
- refresh 失败再清除本地凭证跳登录页

## Token 内含字段

JWT payload：

```json
{
  "sub": "1",          // user_id
  "type": "access",    // 或 "refresh"
  "iat": 1755000000,
  "exp": 1755000900,   // 默认 access: 15min, refresh: 7d
  "jti": "uuid",
  "role": "admin"      // 仅 access token
}
```

服务端不会强制撤销已签发的 token（v0.1 不实现黑名单）；若需要立即失效，需等待 token 自然过期。