# 分析插件开发指南（社区版）

> v0.8d · 更新于 2026-08-14

本指南面向想在 SHM 平台发布自定义分析算法的开发者。读完本文（约 10 分钟）+ 复制一个示例即可完成首个插件。

## 1. 插件是什么

分析插件 = **纯计算单元**：输入"数组 + 参数"，输出"JSON 摘要 + 可选附件"。

```
提交任务 → 框架拉取历史数据 → 你的插件 analyze() → 摘要入库 / 附件存 MinIO → 前端展示
```

框架负责：数据访问、权限校验、任务状态机、结果存储。**你的插件不需要接触数据库、网络、实时流**——只需写数学。

## 2. 最小插件（5 分钟）

在 `app/plugins/analyzers/` 下新建 `my_plugin.py`：

```python
from typing import Any

import numpy as np

from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin


class MyPlugin(AnalysisPlugin):
    # —— 元信息（注册表 / 前端列表与表单用）——
    name = "my_plugin"  # 唯一标识，提交任务时用这个名字
    display_name = "我的分析"  # 前端展示名
    description = "一句话说明这个算法干什么"
    version = "1.0.0"
    input_channels = 1  # 需要几个通道的数据（模态分析可设为 N）
    min_samples = 2  # 每个通道最少样本数（不足则任务失败）
    result_view = "generic"  # 前端结果展示视图：generic（摘要+下载）/ fft（频谱图）
    params_schema = {  # JSON Schema：前端据此生成参数表单
        "type": "object",
        "properties": {
            "window": {"type": "integer", "minimum": 1, "default": 10},
        },
    }

    async def analyze(self, data: AnalysisInput, config: dict[str, Any]) -> AnalysisOutput:
        arr = np.asarray(data.data, dtype=np.float64)  # 单通道时 data.data 是数组
        window = int(config.get("window", 10))  # 参数从 config 读，自行校验
        if window <= 0:
            raise ValueError("window 必须 > 0")  # 抛 ValueError → 任务标记 failed

        return AnalysisOutput(
            summary={
                "channel_id": data.channel_ids[0],
                "window": window,
                "mean": float(arr.mean()),
            },
            # 可选：二进制附件（NPZ/PNG/CSV...）→ MinIO，前端可下载
            # artifact=np.savez(...).tobytes(),
            # artifact_name=f"my_{data.channel_ids[0]}.npz",
        )
```

保存后无需任何注册动作——**进程启动时自动扫描发现**。重启服务，`GET /api/v1/analysis/plugins` 就能看到它。

## 3. 接口契约（v2）

### AnalysisInput（框架构造，你只读）

| 字段 | 说明 |
|------|------|
| `channel_ids: list[int]` | 参与分析的通道 ID（多通道插件由提交者经 `params.channel_ids` 指定） |
| `time_range: tuple[str, str]` | 时间窗（ISO 字符串，可空） |
| `sampling_rate: float` | 采样率（Hz），取自通道配置；fft 等可通过 config 覆盖 |
| `data` | `input_channels=1`：`np.ndarray`（等间隔采样）；`input_channels=N`：`dict[int, np.ndarray]`（channel_id → 数组） |

### AnalysisOutput（你返回）

| 字段 | 说明 |
|------|------|
| `summary: dict` | JSON 摘要 → 存入任务 `result_summary`（必须 JSON 可序列化） |
| `artifact: bytes \| None` | 可选二进制附件 → 存 MinIO，`GET /analysis/jobs/{id}/result` 可下载 |
| `artifact_name: str` | 附件文件名（含扩展名，决定下载文件名） |
| `artifact_type: str` | 附件 Content-Type |

### 规则

- `analyze` 必须返回 `AnalysisOutput`（不是裸 dict）
- 参数校验失败抛 `ValueError`（框架捕获后任务标记 `failed` 并记录错误信息）
- 摘要/附件都要**JSON/二进制友好**，不要返回 numpy 对象直接入库

## 4. 多通道插件（模态分析等）

声明 `input_channels = N`，提交任务时 `params.channel_ids` 给出 N 个通道：

```python
class ModalPlugin(AnalysisPlugin):
    name = "modal"
    input_channels = 4  # 同子项 4 个通道同步分析

    async def analyze(self, data: AnalysisInput, config):
        arrays = data.data  # {channel_id: np.ndarray}
        # 各通道样本数可能不同，自行对齐/截断
        return AnalysisOutput(summary={...})
```

约束：多通道必须属于**同一子项**（框架校验，防止越权跨项目拉数据）。

## 5. 发布为第三方包（pip install 即接入）

不想改核心仓库？把你的插件打包成独立 Python 包，声明 entry point：

```toml
# pyproject.toml
[project]
name = "shm-plugin-myanalysis"
version = "1.0.0"
requires-python = ">=3.11"

[project.entry-points."shm_analyzers"]
myanalysis = "myanalysis:MyPlugin"   # 模块:类
```

部署端 `pip install shm-plugin-myanalysis` 后，后端启动时通过 `importlib.metadata.entry_points(group="shm_analyzers")` 自动注册——**无需改任何核心代码**。

### 版本守卫

- 插件须声明 `plugin_api_version = "1"`（当前框架接口版本，见 `app/plugins/analyzers/base.py` 的 `PLUGIN_API_VERSION`）
- 版本不匹配的插件会被拒绝加载并记 warning（防止框架升级后插件静默出错）
- 同名插件：先注册的生效（内置优先），重复的记 warning 跳过

## 6. 本地测试

```python
import asyncio
import numpy as np
from app.plugins.analyzers.my_plugin import MyPlugin
from app.plugins.analyzers.base import AnalysisInput


async def main():
    out = await MyPlugin().analyze(
        AnalysisInput(
            channel_ids=[1],
            time_range=("", ""),
            sampling_rate=100.0,
            data=np.sin(2 * np.pi * 5 * np.arange(200) / 100),
        ),
        {"window": 10},
    )
    print(out.summary)


asyncio.run(main())
```

插件是纯函数，单测喂假数组即可，无需数据库/Redis/MinIO。

## 7. 内置换 / 换清单

| 任务 | 位置 |
|------|------|
| 接口契约 | `app/plugins/analyzers/base.py`（**契约变更需同步本指南与文档**） |
| 注册表 | `app/plugins/analyzers/registry.py`（内置扫描 + entry_points） |
| 数据拉取/调度 | `app/tasks/analysis_tasks.py` |
| 元信息接口 | `GET /api/v1/analysis/plugins` |
| 示例插件 | `statistics.py`（最小）、`fft_analysis.py`（带附件） |

## 8. 常见问题

- **插件没出现在 `/analysis/plugins`**：检查类是否继承 `AnalysisPlugin`、`name` 是否重复、`plugin_api_version` 是否匹配
- **任务一直 failed**：`GET /analysis/jobs/{id}` 的 `error` 字段有具体原因；参数校验失败时确认 `ValueError` 消息
- **多通道数据长度不一致**：框架不强行对齐，插件自行处理（可 `min` 截断或重采样）
