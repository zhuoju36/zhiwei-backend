# API 概览

> SHM 平台后端 v0.9.1 · 更新于 2026-08-13

Base URL：`http://<host>/api/v1`

完整的交互式文档：`http://<host>/docs`（Swagger UI）/ `http://<host>/redoc`（ReDoc）

## 1. 统一响应结构

所有成功响应都包在 `EnvelopeMiddleware` 中：

```json
{
  "code": "OK",
  "message": "success",
  "data": { ... },
  "timestamp": "2026-08-13T12:34:56.789+00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 业务码；成功为 `OK`，错误见下表 |
| `message` | string | 人类可读的说明 |
| `data` | any / null | 实际载荷；失败时为 `null` |
| `timestamp` | string (ISO8601) | 服务器响应时间（UTC） |

## 2. 错误码与 HTTP 状态

| HTTP | 业务 code | 含义 | 触发场景 |
|------|-----------|------|----------|
| 400 | `VALIDATION_ERROR` | 入参校验失败 | Pydantic Field 约束不满足 |
| 401 | `AUTH_ERROR` | 未认证 / 凭证无效 | 缺失或过期 token、密码错误 |
| 403 | `FORBIDDEN` | 已认证但无权限 | 非 admin 调用 admin-only 接口、非授权用户访问项目 |
| 404 | `PROJECT_NOT_FOUND` / `POINT_NOT_FOUND` / `USER_NOT_FOUND` | 资源不存在 | 路径 ID 无效 |
| 409 | `USER_EXISTS` | 资源冲突 | 用户名已存在 |
| 422 | `VALIDATION_ERROR` | 请求体验证失败 | 字段类型错误、必填缺失 |
| 500 | `INTERNAL_ERROR` | 未捕获异常 | 服务端 bug |
| 503 | `AGGREGATE_NOT_READY` | 连续聚合未初始化 | 调用 `timeseries?interval>=1m` 但未执行 `init_db.py` |

错误响应同样使用统一信封（`code` 为具体错误码，`message` 为说明，`data` 为 `null`）。`VALIDATION_ERROR` 的 `message` 字段会包含详细错误数组。

## 3. 鉴权机制

### 3.1 用户端：JWT Bearer

```http
Authorization: Bearer <access_token>
```

- access token 默认 15 分钟有效（`ACCESS_TOKEN_EXPIRE_MINUTES`）
- refresh token 默认 7 天有效，用于换取新令牌
- 过期或无效时返回 `401 AUTH_ERROR`

### 3.2 边缘网关：API Key

```http
X-API-Key: <edge_api_key>
```

- 仅用于 `POST /api/v1/data/ingest`
- 配置项：`EDGE_API_KEY`（默认 `edge-secret-key`，生产必须替换）
- 缺失或错误时返回 `401 AUTH_ERROR`

## 4. 分页约定

列表接口接受 `page` 与 `size`：

| 参数 | 类型 | 默认 | 约束 |
|------|------|------|------|
| `page` | int | 1 | ≥ 1 |
| `size` | int | 20 | 1 ≤ size ≤ 200 |

分页响应：

```json
{
  "code": "OK",
  "data": {
    "total": 123,
    "page": 1,
    "size": 20,
    "items": [ ... ]
  }
}
```

## 5. 时间格式

所有时间字段均为 ISO 8601 带时区（UTC）：

```
2026-08-13T12:34:56.789+00:00
```

请求时也必须使用同一格式（带 `Z` 或 `+00:00`），FastAPI 自动解析。

## 6. 限流

v0.1 未实现。生产建议在 Nginx 或 API Gateway 层加 IP 维度的限流，特别是 `/data/ingest`（防止边缘网关异常导致雪崩）。