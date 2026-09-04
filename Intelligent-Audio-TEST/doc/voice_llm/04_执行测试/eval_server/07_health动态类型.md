# 07 — health 动态类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/controllers/health.py`

---

## 背景

`/health` 端点动态返回所有已注册任务类型及其并发状态（来自 `ConcurrencyManager`），不再硬编码类型列表。

---

## 实际实现

### 1. health 端点

```python
# health.py
from flask import Blueprint, jsonify
from ..services.task_service import TaskService
from ..utils.concurrency import ConcurrencyManager

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    stats = ConcurrencyManager.get_stats()
    supported_types = list(stats.keys())

    type_concurrency = {}
    for task_type, type_stats in stats.items():
        type_concurrency[task_type] = {
            'max_concurrency': type_stats['max'],
            'current_concurrency': type_stats['current'],
            'available': type_stats['max'] - type_stats['current'],
        }

    response_data = {
        "status": "healthy",
        "service": "wer-ser-calculator",
        "role": "master",
        "supported_task_types": supported_types,
        "concurrency": type_concurrency,
    }
    return jsonify(response_data), 200
```

### 2. 返回数据结构

```json
{
  "status": "healthy",
  "service": "wer-ser-calculator",
  "role": "master",
  "supported_task_types": [
    "wer", "ser", "der", "cpwer", "tcpwer", "stm_wer",
    "llm_judge", "turn_taking", "interruption_metrics",
    "non_interactive_latency", "noise_latency", "env_judge",
    "high_freq_turn_taking", "high_freq_llm_judge"
  ],
  "concurrency": {
    "wer": {"max_concurrency": 10, "current_concurrency": 1, "available": 9},
    "ser": {"max_concurrency": 10, "current_concurrency": 0, "available": 10},
    "der": {"max_concurrency": 5, "current_concurrency": 0, "available": 5},
    "llm_judge": {"max_concurrency": 10, "current_concurrency": 1, "available": 9}
  }
}
```

> 字段名为 `max_concurrency` / `current_concurrency` / `available`（注意不是 `current` / `max`）。`supported_task_types` 直接取 `ConcurrencyManager.get_stats().keys()`，当前返回 **14 项**（含历史遗留键 `env_judge`，不含 `rejection_judge`/`interruption_judge`/`tor`/`false_takeover`/`takeover_latency`——后者在首次访问时才动态注册）。**该口径 ≠ 注册表 18 键 ≠ API 白名单 15 项**，三处清单差异见 `04_ConcurrencyManager动态类型` 开头的口径对照表。

### 3. 主后端消费方式

主后端（`Intelligent-Audio-TEST/backend`）并不解析 `/health` 的 `supported_task_types`。其维度健康探测（`evaluation_controller.health_check`）仅对维度配置的 api_endpoints 逐条发起 `requests.get` **连通性探测**（2xx/3xx 视为 online，异常视为 offline），复杂度量只有响应耗时；评估任务并发依据由 `evaluation_api_client` 的本地 endpoint_semaphores/endpoint_configs 独立维护。因此 eval_server `/health` 主要用于进程存活与人工排查，接口兼容主后端连通性探测即可。

---

## 不变部分

- HTTP 端点路径 `/health` 不变
- 返回格式保持 JSON，`status: "healthy"` 不变
- `service`/`role` 固定值不变（兼容既有调用方）
- 不影响 `/api/status` 端点

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `04_ConcurrencyManager动态类型` | 提供类型和并发数据（口径对照表） |
| `02_评估维度架构_策略模式与主从维度` | 注册表 18 键 / 白名单 15 项（与 health 14 项口径的差异基准） |
| `01_create_task新任务类型` | 新增类型注册 |