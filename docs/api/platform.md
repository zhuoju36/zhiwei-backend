# 平台元数据

> v0.9.0 · 更新于 2026-08-14

平台级配置：名称、联系邮箱、描述、Logo URL。存于 `platform_settings` 单行表（`id=1` CheckConstraint 约束单行）。

## 数据模型

```json
{
  "platform_name": "SHM Platform",
  "contact_email": "ops@example.com",
  "description": "结构健康监测平台",
  "logo_url": "https://cdn.example.com/logo.png",
  "updated_at": "2026-08-14T10:00:00+00:00",
  "updated_by": 1
}
```

启动时 `app/lifespan.py` 自动 `ensure_singleton`：若表空，插入默认行 `{platform_name: "SHM Platform", ...}`。

## 端点

### GET /api/v1/platform

**公开**（无需认证）。前端 setup 页面 / 登录页 / 大屏可读取平台名称展示。

**响应 200**
```json
{
  "code": "OK",
  "data": {
    "platform_name": "SHM Platform",
    "contact_email": null,
    "description": null,
    "logo_url": null,
    "updated_at": "2026-08-14T09:59:16.123+00:00",
    "updated_by": null
  }
}
```

### PUT /api/v1/platform

**仅 admin**。所有字段可选；至少传一个字段。

**请求**
```json
{
  "platform_name": "My SHM",
  "contact_email": "ops@example.com",
  "description": "结构健康监测平台",
  "logo_url": "https://cdn.example.com/logo.png"
}
```

字段约束：
- `platform_name`：1-128 字符
- `contact_email`：≤128 字符
- `logo_url`：≤512 字符
- `description`：不限长度

**响应 200** 返回更新后的完整对象。

**错误**

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 未登录 |
| 403 | `FORBIDDEN` | 非 admin |
| 422 | `EMPTY_UPDATE` | 请求体为空（至少一个字段） |

## 守卫

- 路由**无认证**（GET 是公开信息）
- 路由**不**挂 `get_current_user`，GET 直接通过 `DbSession` 读；PUT 用 `AdminUser` 守卫

## 变更审计

当前 v0.7 不上 audit log 表，但 `platform_service.update_settings` 留了扩展位（updated_by 字段已记录最后操作者）。v0.9+ 可加 `audit_logs` 表记录完整变更历史。