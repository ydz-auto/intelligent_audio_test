# 31 — event_manager 多轮进度推送

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/common/event_manager.py`

---

## 背景

`EventManager.emit_progress()` 通过 Socket.IO 向前端推送 `task_progress` 事件。多轮对话（用例配置了 `rounds`）需要在进度推送中包含当前轮次信息（"第 N/M 轮"），让前端能够展示多轮进度。

**设计决策**：轮次进度存储在 `ExecutionEngine` 的**进程内存缓存**（`round_progress_cache`）中，而不是写入 `TaskCase.extra_data` 等 DB 字段——避免为此做数据库迁移，进度数据本身是临时态（任务结束即失效）。EventManager 组装进度时只读内存缓存，不查额外 DB。

---

## 改造内容

### 1. 进度数据扩展：roundProgress

在 `emit_progress()` 构建 `test_cases_data` 时，为每个 test case 尝试附加 `roundProgress` 字段（来源：`execution_engine.round_progress_cache`，key 为 `tc.id` 即 `TaskCase.id`）：

```python
# emit_progress() 内部，构建 test_cases_data 时
for tc in all_task_cases:
    test_cases_data.append({
        "id": str(tc.test_case_id),
        "status": tc.status,
        "executionStatus": tc.execution_status,
        "evaluationStatus": tc.evaluation_status,
        "duration": duration,
        "errorMessage": tc.error_message
    })

    # Multi-round progress: read from execution_engine in-memory cache
    from backend.services.execution.execution_engine import execution_engine
    round_progress = execution_engine.round_progress_cache.get(tc.id)
    if round_progress:
        test_cases_data[-1]['roundProgress'] = {
            'current': round_progress.get('current', 0),
            'total': round_progress.get('total', 0),
        }
```

注意：
- 写入侧（`ExecutionEngine.update_case_round_progress`）与读取侧 key **一致为 `tc_rel_id`（TaskCase.id）**，不是 test_case_id
- `current` 已是 1-indexed（写入侧 `current_round + 1`）
- 未配置多轮 / 尚未开始的用例缓存无该 key，`roundProgress` 字段不出现在推送中

### 2. WebSocket 推送数据结构

实际 `progress_data` 顶层字段：

```json
{
  "taskId": "1",
  "totalProgress": 45,
  "status": "running",
  "completedCount": 2,
  "inProgressCount": 1,
  "executionFailedCount": 0,
  "evaluationFailedCount": 0,
  "totalCount": 5,
  "currentCase": {
    "caseId": "101",
    "name": "多轮对话_场景A",
    "step": "playing",
    "startTime": 1717500000000
  },
  "testCases": [
    {
      "id": "101",
      "status": "running",
      "executionStatus": "running",
      "evaluationStatus": "queued",
      "duration": 32,
      "errorMessage": null,
      "roundProgress": {
        "current": 5,
        "total": 10
      }
    },
    {
      "id": "102",
      "status": "completed",
      "executionStatus": "completed",
      "evaluationStatus": "completed"
    }
  ],
  "logs": [],
  "apiResources": [],
  "expectedTotalTime": 1200,
  "expectedCompleteTime": "2026-09-03 17:30:00",
  "usedTime": "5分钟"
}
```

字段说明：
- `testCases[].id` 是 `test_case_id`（字符串），`roundProgress` 的读写 key 才是 `TaskCase.id`
- `totalProgress` 按 `TaskCase.status in [completed, failed, skipped]` 统计；任务终态强制 100%
- `inProgressCount` 统计运行/排队（execution）+ 评估运行/计算（evaluation）中用例
- `step`：`e2e` 任务为 `"playing"`，`api` 任务为 `"evaluating"`
- `usedTime`：任务已结束用 `completed_at/updated_at - started_at`，运行中用 `now - started_at`

### 3. 日志输出扩展

多轮执行时（用例配置了 `rounds`），执行器日志带轮次信息（以执行器实际格式为准）：

```python
# e2e_executor.py
self._log(level='INFO', content=f"执行第 {round_number} 轮", task_id=task_id, ...)

# api_session_executor.py
self._log(level='INFO', content=f"执行第 {round_number}/{len(rounds)} 轮", ...)
```

`round_number` 取自 `round_config.get('round_number', round_idx + 1)`。这些日志经 `logs_data`（最近 20 条）随 `task_progress` 推送，前端可直接显示。

### 4. 时间预估（calculate_time_estimate）

`calculate_time_estimate(task)` 目前**不感知轮次**，多轮用例没有专门的时间预估逻辑：

- API 任务：优先用最近 3 个完成任务的用例平均耗时 × 当前用例数；历史数据不足时按流程公式（健康检查/建任务/轮询/取结果/清理 + 音频总时长）估算
- E2E 任务：同样优先历史均值；不足时按公式（设备预处理/提示音/背景噪声/设备操作/后处理/系统开销 + 音频总时长估算）估算
- 兜底：每个用例至少 2 秒；异常时默认 60 秒

> 注：多轮场景下公式各项未乘以轮次数，时间预估偏保守。如需优化可挂 TODO：按 `rounds` 数量折算单用例时长。

### 5. 节流策略

两级节流叠加：

| 层级 | 机制 | 说明 |
|------|------|------|
| ExecutionEngine._emit_progress | 0.5s 窗口（非终态） | `last_progress_update`；终态（running/completed/failed/stopped/paused）force=True |
| EventManager.emit_progress | 50ms 间隔 + 0.1s 缓存 | 非 force 时 `_progress_throttle_interval=0.05`，0.1s 内重复发送缓存数据；force 时跳过 |
| 多轮轮次切换 | force=True | `update_case_round_progress` 每次轮次变化调用 `_emit_progress(task_id, force=True)` |

```python
# execution_engine.py → update_case_round_progress
self.round_progress_cache[tc_rel_id] = {'current': current_round + 1, 'total': total_rounds}
# Force progress push on round change
self._emit_progress(task_id, force=True)
```

轮次切换走 force 强制推送，绕过节流，保证前端及时看到"第 N/M 轮"。

---

## 数据流总览

```
Executor 多轮循环                     ExecutionEngine                    EventManager (emit_progress)
─────────────────                    ───────────────                    ──────────────────────────
round_idx 每轮开始 ──────────────►  update_case_round_progress()
                                       │ 写 round_progress_cache[tc_rel_id]
                                       └► _emit_progress(task_id, force=True)
                                             └► event_manager.emit_progress()
                                                  读 execution_engine.round_progress_cache[tc.id]
                                                  └► WebSocket 推送 roundProgress
任务结束（stop/完成/异常） ───────►  round_progress_cache.pop(tc_rel_id)（control_task / _run_task finally）
```

---

## 不变部分

- Socket.IO 连接管理与 `task_progress` 事件名不变
- `task_log` 日志推送不变
- 未配置 `rounds` 的用例推送不变（缓存无 key，无 `roundProgress` 字段）
- `calculate_time_estimate` 既有逻辑不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `30_execution_engine多轮进度` | 轮次进度数据来源（`round_progress_cache`），两级节流的上游 |
| `19_useTaskProgress多轮显示` (frontend) | 前端接收并展示轮次信息 |