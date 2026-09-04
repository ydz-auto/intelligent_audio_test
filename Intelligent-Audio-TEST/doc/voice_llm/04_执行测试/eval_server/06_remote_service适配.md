# 06 — remote_service 适配

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/services/remote_service.py`

---

## 背景

`RemoteService` 负责将评估任务分发到远程 worker 端点。当前实现支持**按 task_type 的端点能力匹配 + 内存级并发跟踪**，并适配了 llm_judge 的长超时与长轮询、文件字段的 multipart 转传（create_task_upload）、本地任务记录登记与后台轮询回写。

---

## 实际实现

### 1. create_remote_task 签名与端点选择

```python
def create_remote_task(self, task_type, task_params=None,
                       endpoints=None, caller_task_id=None) -> str:
```

端点选择在锁内遍历：

1. `endpoints` 为空时从 `TaskModel.get_all_endpoints()` 取数据库配置
2. 配置对象有两种形态：传入的 dict（`ep_config['endpoint']/['name']/['capabilities']/['task_types']/['max_process']`）与数据库记录；**传入端点优先查库合并**（`config_to_use = db_config if db_config else ep_config`）
3. 能力判定优先级：`capabilities[task_type].max_process` → 命中 `task_types` 用默认 `max_process` → capabilities 与 task_types 都为空时通配允许
4. 内存并发 `_endpoint_concurrency[url][task_type]` 未达到该端点该类型 limit 时选中，并立即 `+1`
5. 无可用端点 → `RuntimeError(f"没有可用的远程端点可以处理类型为 '{task_type}' 的任务（并发已满或不支持）")`，上层转 `CODE_CONCURRENCY_EXCEEDED`

### 2. llm_judge 特殊超时与轮询

```python
timeout = selected_endpoint_config.get('max_timeout', 30)
if task_type == 'llm_judge':
    timeout = max(timeout, 180)      # LLM 推理较慢
```

`_poll_task_status` 轮询节奏同样区分类型：

| 类型 | poll_interval | max_attempts |
|------|--------------|--------------|
| `llm_judge` | 5s | 60（≈300s） |
| 其他 | 2s | 30（≈60s） |

### 3. 文件/JSON 分流转发

转发前遍历 `task_params` 检测文件字段（`isinstance(value, str) and os.path.isabs(value) and os.path.exists(value)`）：

- **含文件** → multipart：表单值 dict/list 转 JSON 字符串，文件字段以 `(filename, bytes, 'application/octet-stream')` 随 `data` + `files` POST 到 `{endpoint}/api/create_task_upload`
- **无文件** → JSON：`task_params` **平铺到 payload 顶层**（`payload.update(task_params)`，非嵌套 `task_params` 字段），携带 `task_id`（caller_task_id）POST 到 `{endpoint}/api/create_task`

响应校验：`status_code == 200` 且 `result.get('code') == 0`，取 `data.eval_task_id`；缺失抛 `RuntimeError`。

### 4. 本地登记与轮询回写

转发成功后：

1. `TaskModel.create_task(eval_task_id=remote_eval_task_id, ..., endpoint_url=selected_endpoint, task_id=caller_task_id)` 本地登记（`endpoint_url` 标记该任务归属端点）
2. `update_task_status(..., 'processing', started_at=...)`
3. 启动守护线程 `_poll_task_status(endpoint, remote_eval_task_id, task_type)`：轮询 `get_status`，`completed` 时拉 `get_final_result` 回写 result；`failed` 回写 error_msg；404 标记失败；超时（attempts 用尽）标记超时失败；**finally 中 `_decrement_concurrency` 释放端点槽位**
4. 转发异常（抛错）时先 `_decrement_concurrency` 再上抛

### 5. 端点并发统计

- `_endpoint_concurrency: dict[url][task_type] = current`，`get_endpoints_stats()` 返回其浅拷贝，供 `GET /api/status` 展示各端点按类型 current

### 6. 端点 capabilities 示例

```json
{
  "url": "http://worker-1:5001",
  "name": "Worker 1",
  "capabilities": {
    "wer": {"max_process": 2},
    "ser": {"max_process": 1},
    "llm_judge": {"max_process": 2},
    "turn_taking": {"max_process": 1}
  },
  "task_types": ["wer", "ser", "llm_judge", "turn_taking"]
}
```

> **维度口径**：远端分发的 `task_type` 走 `api.py` 白名单（15 项）。`turn_taking` 主维度的子维度（`tor`/`false_takeover`/`takeover_latency`）通过 `task_params['sub_tasks']` 在端点**内部**路由分发，不进 remote_service 的并发跟踪键；端点只需为 `turn_taking` 配置一个 capability 键即可（详见 `02_评估维度架构`）。

---

## 不变部分

- 端点 CRUD 接口不变
- 并发跟踪数据结构（`_endpoint_concurrency`）形态不变
- `get_endpoints_stats()` 对外行为不变
- 轮询完成后释放并发槽位的行为不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_评估维度架构_策略模式与主从维度` | 主维度 `sub_tasks` 子维度分发、远端端点能力配置口径 |
| `01_create_task新任务类型` | 任务入口与参数校验 |
| `04_ConcurrencyManager动态类型` | 本地并发管理 |
| `03_LLM_Judge计算器` | llm_judge 计算实现 |