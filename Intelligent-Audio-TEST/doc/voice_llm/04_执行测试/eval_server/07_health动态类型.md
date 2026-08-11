# 07 — health 动态类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/controllers/health.py`

---

## 背景

当前 `/health` 端点硬编码返回 `supported_task_types: ["wer", "ser"]`，不反映实际支持的所有类型。voice_llm 改造后需要动态返回所有已注册的任务类型及其并发状态。

---

## 改造内容

### 1. 改造后的 health 端点

```python
# health.py
from flask import Blueprint, jsonify
from app.utils.concurrency import ConcurrencyManager
from app.services.task_service import TaskService

health_bp = Blueprint('health', __name__)

@health_bp.route('/health')
def health():
    """健康检查端点"""
    stats = ConcurrencyManager.get_stats()

    # 动态构建支持的类型列表
    supported_types = list(stats.keys())

    # 构建每类型的并发信息
    type_concurrency = {}
    for task_type, type_stats in stats.items():
        type_concurrency[task_type] = {
            'current': type_stats['current'],
            'max': type_stats['max'],
            'available': type_stats['max'] - type_stats['current'],
        }

    return jsonify({
        'status': 'healthy',
        'service': 'wer-ser-calculator',
        'role': 'master',
        'supported_task_types': supported_types,
        'concurrency': type_concurrency,
    })
```

### 2. 返回数据结构

```json
{
  "status": "healthy",
  "service": "wer-ser-calculator",
  "role": "master",
  "supported_task_types": [
    "wer", "ser", "der", "cpwer", "tcpwer", "stm_wer",
    "llm_judge"
  ],
  "concurrency": {
    "wer": {"current": 1, "max": 2, "available": 1},
    "ser": {"current": 0, "max": 1, "available": 1},
    "der": {"current": 0, "max": 1, "available": 1},
    "llm_judge": {"current": 1, "max": 2, "available": 1}
  }
}
```

### 3. 主后端健康检查适配

主后端 `EvaluationService` 定期调用 eval_server 的 `/health` 端点检查可用性。改造后需要能识别新增类型：

```python
# evaluation_service.py → _load_all_endpoint_configs()
def _load_all_endpoint_configs(self):
    """加载评估端点配置"""
    # ... 现有逻辑 ...

    for endpoint in endpoints:
        # 查询端点健康状态
        try:
            resp = requests.get(f'{endpoint.url}/health', timeout=5)
            health_data = resp.json()

            # 动态获取支持的类型
            endpoint.supported_types = health_data.get(
                'supported_task_types', ['wer', 'ser']
            )
            endpoint.concurrency = health_data.get('concurrency', {})

        except Exception:
            endpoint.supported_types = ['wer', 'ser']
            endpoint.concurrency = {}
```

### 4. 改造对比

| 字段 | 改造前 | 改造后 |
|------|--------|--------|
| `supported_task_types` | `["wer", "ser"]`（硬编码） | 动态从 ConcurrencyManager 获取 |
| `concurrency` | 无 | 每类型的 current/max/available |
| `role` | `"master"`（不变） | `"master"` |
| `service` | `"wer-ser-calculator"` | 保持不变（兼容性） |

---

## 不变部分

- HTTP 端点路径 `/health` 不变
- 返回格式保持 JSON
- `status: "healthy"` 不变
- 不影响 `/api/status` 端点

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `04_ConcurrencyManager动态类型` | 提供类型和并发数据 |
| `01_create_task新任务类型` | 新增类型注册 |
