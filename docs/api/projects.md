# 项目

> v0.2.0 · 更新于 2026-08-13

管理结构健康监测中的"建筑/工地/项目"实体，配置 RBAC 数据隔离。

## 数据模型

```json
{
  "id": 1,
  "name": "演示项目",
  "description": "开发联调演示",
  "location": { "lat": 31.2, "lng": 121.5, "address": "..." },
  "model_file_key": "models/1/building.glb",
  "created_by": 1,
  "created_at": "2026-08-13T12:00:00Z"
}
```

## 权限矩阵

| 接口 | admin | 普通用户 |
|------|-------|----------|
| `GET /projects` 列表 | 全量 | 仅自己被授权的项目 |
| `GET /projects/{id}` | ✓ | 仅被授权项目 |
| `POST /projects` 创建 | ✓ | ✗ |
| `PUT /projects/{id}` 更新 | ✓ | ✗ |
| `DELETE /projects/{id}` 删除 | ✓ | ✗ |
| `POST /projects/{id}/users` 授权 | ✓ | ✗ |

普通用户未授权访问时返回 `403 FORBIDDEN`。

---

## GET /api/v1/projects

分页列出可见项目。

### Query

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码（≥ 1） |
| `size` | int | 20 | 每页条数（1-200） |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "total": 1,
    "page": 1,
    "size": 20,
    "items": [
      { "id": 1, "name": "演示项目", "...": "..." }
    ]
  }
}
```

---

## POST /api/v1/projects

创建项目。需要 admin。

### 请求

```json
{
  "name": "南京长江大桥监测",
  "description": "二期扩建",
  "location": { "lat": 32.1, "lng": 118.8, "address": "..." }
}
```

字段约束：
- `name`：1-128 字符，必填
- `description`：可选
- `location`：可选 JSON 对象（建议含 lat/lng/address）

### 响应 201

```json
{
  "code": "OK",
  "data": { "id": 2, "name": "...", "...": "..." }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 未登录 |
| 403 | `FORBIDDEN` | 非 admin |
| 422 | `VALIDATION_ERROR` | 字段校验失败 |

---

## GET /api/v1/projects/{project_id}

获取项目详情。需要登录且对项目有访问权限。

### 路径参数

- `project_id`：整数

### 响应 200

```json
{
  "code": "OK",
  "data": { "id": 1, "name": "...", "...": "..." }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 未被授权访问该 |
| 404 | `PROJECT_NOT_FOUND` | 不存在 |

---

## PUT /api/v1/projects/{project_id}

更新项目。需要 admin。

### 请求

所有字段可选（PATCH 语义，只更新传入字段）：

```json
{
  "name": "新名称",
  "description": "新描述",
  "location": { "lat": 32.1, "lng": 118.8 },
  "model_file_key": "models/1/building.glb"
}
```

### 响应 200

返回更新后的 `ProjectOut`。

---

## DELETE /api/v1/projects/{project_id}

删除项目（级联删除 user_projects / devices / points）。需要 admin。

### 响应 204

无 body。

---

## POST /api/v1/projects/{project_id}/users

为项目授权用户，或更新已有授权的权限级别。需要 admin。

### 请求

```json
{
  "user_id": 5,
  "permission": "write"
}
```

| 字段 | 类型 | 必填 | 取值 |
|------|------|------|------|
| `user_id` | int | 是 | 目标用户 ID |
| `permission` | enum | 是 | `read` / `write` / `admin` |

幂等：已存在时更新 `permission`。

### 响应 204

无 body。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 404 | `PROJECT_NOT_FOUND` / `USER_NOT_FOUND` | 项目或用户不存在 |

---

## curl 示例

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -d 'username=admin&password=admin123456' | jq -r '.data.access_token')

# 创建
curl -X POST http://localhost:8000/api/v1/projects \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"name":"新项目","description":"测试"}'

# 列表
curl http://localhost:8000/api/v1/projects -H "Authorization: Bearer $TOKEN"

# 详情
curl http://localhost:8000/api/v1/projects/1 -H "Authorization: Bearer $TOKEN"

# 授权用户
curl -X POST http://localhost:8000/api/v1/projects/1/users \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"user_id":2,"permission":"read"}'

# 删除
curl -X DELETE http://localhost:8000/api/v1/projects/1 -H "Authorization: Bearer $TOKEN"
```