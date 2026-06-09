# 30 — execution_engine 多轮进度

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/execution_engine.py`

---

## 背景

`ExecutionEngine` 负责任务调度和进度管理。多轮对话场景下（用例配置了 `rounds`），单个 test case 的执行时间显著增加（可能 10-30 轮，每轮 5-60 秒），需要在进度报告中反映当前轮次信息。

---

## 改造内容

### 1. 任务状态扩展

在 `TaskCase` 状态中增加轮次进度信息：

```python
# execute_task() 中，多轮循环内（case_config.rounds 非空时）
# 更新 TaskCase 状态，记录轮次进度
self._update_case_round_progress(
    task_id, tc_rel_id,
    current_round=round_idx,
    total_rounds=total_rounds,
)
```

### 2. `_update_case_round_progress()` 方法

```python
def _update_case_round_progress(self, task_id, tc_rel_id,
                                  current_round, total_rounds):
    """更新用例的轮次进度信息"""
    from flask import current_app
    app = current_app._get_current_object()

    with app.app_context():
        tc_rel = TaskCase.query.filter_by(id=tc_rel_id).first()
        if tc_rel:
            # 在 extra_data JSON 中存储轮次信息
            extra = tc_rel.extra_data or {}
            extra['round_progress'] = {
                'current': current_round + 1,
                'total': total_rounds,
            }
            tc_rel.extra_data = extra
            db.session.commit()

            # 触发进度推送
            self._emit_progress(task_id, force=True)
```

### 3. `_emit_progress` 适配

```python
def _emit_progress(self, task_id, force=False):
    # 现有节流逻辑不变
    # ...

    # 在 progress_data 中附加轮次信息
    progress_data = self.event_manager.emit_progress(
        task_id=task_id,
        force=force,
    )
    # emit_progress 内部会查询 TaskCase.extra_data 获取轮次信息
```

### 4. EventManager 侧查询轮次信息

```python
# event_manager.py → emit_progress() 中
# 查询当前正在执行的用例及其轮次进度
running_cases = TaskCase.query.filter(
    TaskCase.task_id == task_id,
    TaskCase.execution_status == 'running',
).all()

for case in running_cases:
    extra = case.extra_data or {}
    round_progress = extra.get('round_progress')
    if round_progress:
        case_data['roundProgress'] = {
            'current': round_progress['current'],
            'total': round_progress['total'],
        }
```

### 5. 进度数据中的轮次字段

```json
{
  "taskId": "task-001",
  "totalProgress": 45,
  "status": "running",
  "testCases": [
    {
      "id": 101,
      "name": "voice_llm_多轮对话",
      "status": "running",
      "executionStatus": "running",
      "roundProgress": {
        "current": 3,
        "total": 10
      }
    }
  ]
}
```

### 6. 调度逻辑不变

```python
# ExecutionEngine 的调度规则不变：
# - E2E 任务互斥（同时只能运行一个 E2E 任务）
# - API 任务可并行（但同一 API 端点不重叠）
# - 轮次进度是"信息层"的扩展，不影响调度逻辑
```

---

## 不变部分

- 任务调度逻辑（`_scheduler_loop`、`_schedule_pending_tasks`）不变
- 任务启动/停止/暂停控制不变
- 线程池管理不变
- 未配置 `rounds` 的用例进度报告不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `31_event_manager多轮进度推送` | WebSocket 推送轮次信息 |
| `18_TestExecutionComponent多轮进度` (frontend) | 前端显示轮次 |
