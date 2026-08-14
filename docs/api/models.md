# 3D 模型

> v0.8c · 更新于 2026-08-14

项目（project）的 3D 模型管理：上传源模型（OBJ/STL/PLY/glTF/GLB）→ Celery `reports` 队列后台转换为 **GLB**（前端数字孪生加载格式）→ 按需下载。**一个项目可拥有多个模型**，每条记录独立转换、下载与删除。

## 数据模型

```json
{
  "id": 1,
  "project_id": 1,
  "original_name": "tower.obj",
  "source_format": "obj",
  "glb_key": "models/1/9f2c….glb",
  "status": "success",
  "error": null,
  "created_at": "2026-08-14T10:00:00Z",
  "finished_at": "2026-08-14T10:00:01.500Z"
}
```

`status` 流转：`pending → processing → success` 或 `pending → processing → failed`。

## 权限

| 操作 | admin | 项目 write | 项目 read | 其他 |
|------|-------|-----------|-----------|------|
| `POST /models/{project_id}/upload`（上传） | ✓ | ✓ | ✗ | ✗ |
| `GET /models`（列表） | ✓ | ✓ | ✓ | ✗ |
| `GET /models/{id}`（详情） | ✓ | ✓ | ✓ | ✗ |
| `GET /models/{id}/file`（下载 GLB） | ✓ | ✓ | ✓ | ✗ |
| `DELETE /models/{id}`（删除） | ✓ | ✗ | ✗ | ✗ |

---

## POST /api/v1/models/{project_id}/upload

上传源模型文件（`multipart/form-data`，字段名 `file`），触发后台转换任务。

**权限**：项目 write。

**请求**：

```http
POST /api/v1/models/1/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: tower.obj (application/octet-stream)
```

**成功 201**：

```json
{
  "code": "OK",
  "message": "success",
  "data": { "model_id": 3, "status": "pending" },
  "timestamp": "2026-08-14T10:00:00Z"
}
```

**约束**：
- 格式白名单：`.obj` / `.stl` / `.ply` / `.gltf` / `.glb`
- 文件 ≤ 200MB
- **IFC 暂不支持**（需 v0.9+ Blender/IfcOpenShell 转换器），返回 `MODEL_FORMAT_UNSUPPORTED`

**错误**：

| HTTP | code | 场景 |
|------|------|------|
| 400 | `MODEL_FORMAT_UNSUPPORTED` | 扩展名不在白名单（含 .ifc） |
| 400 | `MODEL_EMPTY` | 空文件 |
| 404 | `PROJECT_NOT_FOUND` | 项目不存在 |
| 413 | `MODEL_TOO_LARGE` | 超过 200MB |

---

## GET /api/v1/models?project_id={id}

按项目分页列出模型（一个项目多个模型）。

**权限**：项目 read。

**查询参数**：`project_id`（必填）、`page`、`size`。

**成功 200**：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "total": 2,
    "page": 1,
    "size": 20,
    "items": [ { "id": 3, "project_id": 1, "status": "success", "...": "..." } ]
  },
  "timestamp": "2026-08-14T10:00:00Z"
}
```

---

## GET /api/v1/models/{id}

模型详情（含当前转换状态与错误信息）。**权限**：项目 read。

---

## GET /api/v1/models/{id}/file

下载转换后的 **GLB** 文件（`Content-Type: model/gltf-binary`，`Content-Disposition: attachment`）。

**权限**：项目 read。

**错误**：`409 MODEL_NOT_READY` — 模型尚未转换完成（`status != success`）。

---

## DELETE /api/v1/models/{id}

删除模型记录，并清理 MinIO 中的源文件与 GLB 产物（清理失败仅记日志，不影响删除）。

**权限**：admin。**成功 204**；不存在 404。
