# 分析

> v0.8d · 更新于 2026-08-14

异步分析任务链路：用户提交任务 → Celery `analysis` 队列消费 → 插件计算 → 结果存 MinIO + 摘要回写数据库。内置插件：**FFT**（频谱分析，v0.4）、**statistics**（基础统计，v0.8d）；第三方插件经 Python entry_points（组 `shm_analyzers`）自动发现，详见 [插件开发指南](../development/plugin-dev.md)。

## 数据模型

```json
{
  "id": 1,
  "channel_id": 1,
  "plugin": "fft",
  "params": { "sampling_rate": 100.0 },
  "status": "success",
  "result_key": "analysis/1/fft_1.npz",
  "result_summary": {
    "dominant_freq": 50.12,
    "dominant_magnitude": 0.4817,
    "num_samples": 400,
    "nyquist_freq": 50.0,
    "top_peaks": [...]
  },
  "error": null,
  "submitted_by": 1,
  "created_at": "2026-08-13T14:00:00Z",
  "started_at": "2026-08-13T14:00:00.100Z",
  "finished_at": "2026-08-13T14:00:00.250Z"
}
```

`status` 流转：`pending → running → success` 或 `pending → running → failed`。

## 权限

| 操作 | admin | 子项 write | 子项 read | 其他 |
|------|-------|-----------|-----------|------|
| `GET /analysis/plugins`（插件列表） | ✓ | ✓ | ✓ | ✗ |
| `POST /analysis/jobs`（提交） | ✓ | ✓ | ✗ | ✗ |
| `GET /analysis/jobs`（列表） | ✓ | ✓（限可见子项） | ✓ | ✗ |
| `GET /analysis/jobs/{id}`（详情） | ✓ | ✓ | ✓ | ✗ |
| `GET /analysis/jobs/{id}/result`（下载附件） | ✓ | ✓ | ✓ | ✗ |

---

## GET /api/v1/analysis/plugins

列出全部已注册分析插件的元信息（前端据此渲染"可用分析"列表与参数表单）。

### 响应 200

```json
[
  {
    "name": "fft",
    "display_name": "FFT 频谱分析",
    "description": "快速傅里叶变换，输出主频、幅值谱与峰值列表（附件含完整频谱）",
    "version": "2.0.0",
    "input_channels": 1,
    "min_samples": 2,
    "params_schema": { "type": "object", "properties": { "sampling_rate": { "type": "number" } } }
  }
]
```

---

## POST /api/v1/analysis/jobs

提交一个新分析任务。

### 请求

```json
{
  "channel_id": 1,
  "plugin": "fft",
  "params": { "sampling_rate": 100.0 }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `channel_id` | 是 | 目标通道 ID |
| `plugin` | 是 | 已注册插件名（v0.8d: `fft` / `statistics`） |
| `params` | 否 | 插件参数（各插件 `params_schema` 见 `/analysis/plugins`） |
| `params.channel_ids` | 多通道插件必填 | 参与分析的通道列表（须同一子项，数量 = 插件 `input_channels`） |
| `params.start` / `params.end` | 否 | ISO8601 时间窗；省略则用全量数据 |

### 响应 201

```json
{
  "code": "OK",
  "data": { "job_id": 42, "status": "pending" },
  "timestamp": "2026-08-13T14:00:00Z"
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无子项写权限 |
| 404 | `POINT_NOT_FOUND` | 通道不存在 |
| 422 | `PLUGIN_NOT_REGISTERED` | plugin 不在 `AnalyzerRegistry` 内 |

---

## GET /api/v1/analysis/jobs

分页列出任务。

### Query

| 参数 | 默认 | 说明 |
|------|------|------|
| `channel_id` | — | 按通道过滤 |
| `plugin` | — | 按插件过滤 |
| `status` | — | 按状态过滤 |
| `page` / `size` | 1 / 20 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "total": 5,
    "page": 1,
    "size": 20,
    "items": [ { "id": 42, "plugin": "fft", "status": "success", ... } ]
  }
}
```

---

## GET /api/v1/analysis/jobs/{job_id}

获取任务详情（含 `result_summary` 摘要）。

### 响应 200

返回 `AnalysisJobOut`，`result_summary` 含：

| 字段 | 说明 |
|------|------|
| `dominant_freq` | 主频率（Hz） |
| `dominant_magnitude` | 主频对应幅值 |
| `num_samples` | FFT 输入样本数 |
| `sampling_rate` | 采样率（Hz） |
| `nyquist_freq` | Nyquist 频率（= sr/2） |
| `freq_resolution` | 频率分辨率（= sr/N） |
| `top_peaks` | 前 3 个局部峰 [{freq, magnitude}, ...] |
| `warnings` | 警告列表（如样本数过少） |

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无权限 |
| 404 | `ANALYSIS_JOB_NOT_FOUND` | 不存在 |

---

## GET /api/v1/analysis/jobs/{job_id}/result

下载插件返回的完整附件（FFT 为 NPZ 二进制，含完整 `frequencies` 与 `magnitudes` 数组，用于前端绘图）。

### 响应 200

```
Content-Type: application/octet-stream（或插件声明的 artifact_type）
Content-Disposition: attachment; filename="<插件 artifact_name>"

<二进制附件>
```

可用 `numpy.load(BytesIO(resp.content))` 解析 NPZ。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 404 | `ANALYSIS_JOB_NOT_FOUND` | 任务不存在 |
| 409 | `ANALYSIS_RESULT_NOT_READY` | 任务未完成（status≠success） |

---

## FFT 插件说明

输入：等间隔采样的一维 numpy 数组 + 采样率（Hz）。

输出（JSON 摘要）：
- `dominant_freq` / `dominant_magnitude`
- 前 3 个局部峰
- 警告（样本数 < 64 时提示）

输出（NPZ 二进制）：
- `frequencies`: shape (N/2+1,) 的频率数组
- `magnitudes`: shape (N/2+1,) 的幅值数组（已归一化 / N）
- `sampling_rate`: 标量

示例 Python 客户端：
```python
import httpx, io, numpy as np

TOKEN = "..."
# 提交
r = httpx.post(
    "http://localhost:8000/api/v1/analysis/jobs",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"channel_id": 1, "plugin": "fft", "params": {"sampling_rate": 100}},
)
job_id = r.json()["data"]["job_id"]
# 等待完成
import time

while True:
    r = httpx.get(
        f"http://localhost:8000/api/v1/analysis/jobs/{job_id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    if r.json()["data"]["status"] in ("success", "failed"):
        break
    time.sleep(0.2)
# 下载 NPZ
r = httpx.get(
    f"http://localhost:8000/api/v1/analysis/jobs/{job_id}/result",
    headers={"Authorization": f"Bearer {TOKEN}"},
)
data = np.load(io.BytesIO(r.content))
plt.plot(data["frequencies"], data["magnitudes"])
```

## 插件开发指南

面向社区开发者的完整指南见 **[plugin-dev.md](../development/plugin-dev.md)**。

要点（接口契约 v2）：
1. 内置插件放 `app/plugins/analyzers/`（自动扫描）；第三方插件打包声明 entry point（组 `shm_analyzers`，pip install 即接入）
2. 继承 `AnalysisPlugin`，声明元信息（`name / display_name / input_channels / min_samples / params_schema`）
3. 实现 `async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput`
4. 插件是纯计算单元：不接触数据库与实时流；参数校验失败抛 `ValueError` 即任务标记 failed