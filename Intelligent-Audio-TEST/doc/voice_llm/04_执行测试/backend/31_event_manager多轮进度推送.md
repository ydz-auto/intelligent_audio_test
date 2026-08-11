# 31 — event_manager 多轮进度推送

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/event_manager.py`

---

## 背景

`EventManager.emit_progress()` 通过 Socket.IO 向前端推送 `task_progress` 事件。多轮对话（用例配置了 `rounds`）需要在进度推送中包含当前轮次信息（"第 N/M 轮"），让前端能够展示多轮进度。

---

## 改造内容

### 1. 进度数据扩展

在 `emit_progress()` 构建的 `progress_data` 中，为每个 test case 增加 `roundProgress` 字段：

```python
# emit_progress() 内部，构建 test_cases_data 时
for tc in task_cases:
    case_data = {
        'id': tc.id,
        'name': tc.test_case.name if tc.test_case else '',
        'status': tc.status,
        'executionStatus': tc.execution_status,
        'evaluationStatus': tc.evaluation_status,
        'duration': tc.duration,
        'errorMessage': tc.error_message,
    }

    # 新增：轮次进度
    extra = tc.extra_data or {}
    round_progress = extra.get('round_progress')
    if round_progress:
        case_data['roundProgress'] = {
            'current': round_progress['current'],
            'total': round_progress['total'],
        }

    test_cases_data.append(case_data)
```

### 2. WebSocket 推送数据结构

```json
{
  "taskId": "task-001",
  "totalProgress": 45,
  "status": "running",
  "completedCount": 2,
  "inProgressCount": 1,
  "executionFailedCount": 0,
  "evaluationFailedCount": 0,
  "totalCount": 5,
  "testCases": [
    {
      "id": 101,
      "name": "多轮对话_场景A",
      "status": "running",
      "executionStatus": "running",
      "roundProgress": {
        "current": 5,
        "total": 10
      }
    },
    {
      "id": 102,
      "name": "单轮翻译_场景B",
      "status": "completed",
      "executionStatus": "completed"
    }
  ],
  "logs": [...],
  "usedTime": "5分钟",
  "expectedTotalTime": 1200,
  "expectedCompleteTime": "2026-06-05T17:30:00"
}
```

### 3. 日志输出扩展

多轮执行时（用例配置了 `rounds`），EventManager 推送的日志中应包含轮次信息：

```python
# 在执行器中记录带轮次的日志
self._log(
    'info',
    f'[第 {round_idx + 1}/{total_rounds} 轮] 开始播放音频 {audio_name}',
    task_id=task_id
)
```

日志格式：`[第 N/M 轮] 操作描述`，前端可直接显示。

### 4. 时间预估适配

```python
def calculate_time_estimate(self, task_id, task_cases):
    # ... 现有逻辑 ...

    # 多轮场景的时间预估（case_config.rounds 非空时）
    rounds = case_config.get('rounds', [])
    if rounds:
        # 基于轮次配置估算
        total_rounds = len(rounds)
        per_round_time = self._estimate_per_round_time(algorithm_type, test_type)
        estimated_per_case = total_rounds * per_round_time
    else:
        # 现有逻辑
        estimated_per_case = self._estimate_case_time(...)

    expected_total_time = estimated_per_case * len(task_cases)
    return expected_total_time, expected_complete_time
```

### 5. 节流策略

多轮场景下进度推送频率调整：

| 场景 | 最小间隔 | 说明 |
|------|---------|------|
| 普通任务 | 50ms（不变） | 保持现有节流 |
| 多轮轮次切换 | 0ms（force=True） | 轮次变化时立即推送 |
| 多轮轮次内 | 500ms | 减少高频更新 |

```python
# 轮次切换时强制推送
if round_changed:
    self._emit_progress(task_id, force=True)
```

---

## 不变部分

- Socket.IO 连接管理不变
- `task_progress` 事件名称不变
- `task_log` 日志推送不变
- 节流框架不变
- 未配置 `rounds` 的用例推送不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `30_execution_engine多轮进度` | 轮次进度数据来源 |
| `19_useTaskProgress多轮显示` (frontend) | 前端接收并展示轮次信息 |
