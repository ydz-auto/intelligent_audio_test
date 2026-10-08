# 30 — execution_engine 多轮进度

> **所属步骤**：04_执行测试 → backend
> **改造类型**：修改
> **涉及文件**：`backend/services/execution/execution_engine.py`、`backend/utils/common/event_manager.py`

---

## 背景

`ExecutionEngine` 负责任务调度和进度管理。多轮对话场景下（用例配置了 `rounds`），单个 test case 的执行时间显著增加（可能 10-30 轮，每轮 5-60 秒），需要在进度报告中反映当前轮次信息。

**设计决策**：轮次进度存储在**进程内存缓存**中（`round_progress_cache`），而不是写入 `TaskCase.extra_data` 等 DB 字段——避免为此做数据库迁移，进度数据本身是临时态（任务结束即失效），内存缓存即可满足需求。

---

## 改造内容

### 1. 单例初始化：轮次进度缓存

```python
# execution_engine.py → cls.__new__() 单例初始化中
cls._instance.last_progress_update = {}   # 上次进度更新时间，{task_id: timestamp}
# 多轮进度内存缓存，{tc_rel_id: {'current': N, 'total': M}}
cls._instance.round_progress_cache = {}
# 任务完成事件，{task_id: threading.Event}，用于替代忙等待
cls._instance.task_completion_events = {}
```

缓存 key 为 **`tc_rel_id`（即 `TaskCase.id`）**，不是 test_case_id——同一 test_case 可能被多个任务引用。

### 2. `update_case_round_progress()` 方法

公开方法（供各 Executor 在多轮循环中调用），**纯内存操作**，无 DB 读写：

```python
def update_case_round_progress(self, task_id, tc_rel_id, current_round, total_rounds):
    """
    Update round progress for a multi-round test case (in-memory cache).

    The round progress is stored in memory and read by event_manager
    during progress emission. This avoids needing a DB migration for
    an extra_data column on TaskCase.
    """
    self.round_progress_cache[tc_rel_id] = {
        'current': current_round + 1,   # 0-indexed → 1-indexed 展示
        'total': total_rounds,
    }
    # Force progress push on round change（轮次变化强制推送，绕过节流）
    self._emit_progress(task_id, force=True)
```

### 3. `_emit_progress()` 适配

`_emit_progress` 接收 **task 对象或 task_id**（`isinstance(task, (str, int))` 时取 `str(task)`），内部节流逻辑（0.5 秒窗口）保持不变：

```python
def _emit_progress(self, task, force=False):
    task_id = None
    if isinstance(task, (str, int)):
        task_id = str(task)
    elif hasattr(task, 'id'):
        task_id = str(task.id)
        task_status = getattr(task, 'status', None)

    if task_id and not force:
        # 节流：非终态 0.5 秒内不重复推送；终态强制推送
        ...

    self.event_manager.emit_progress(task, force=force)
```

轮次更新调用时传入 `force=True`，保证每轮开始都立即推送。

### 4. Executor 侧调用（每轮开始时）

多轮循环的执行方是 `e2e_executor.py` 与 `api_session_executor.py`（而非 engine 自身）：

```python
# e2e_executor.py 多轮循环内
for round_idx, round_config in enumerate(rounds):
    round_number = round_config.get('round_number', round_idx + 1)
    self.execution_engine.update_case_round_progress(task_id, tc_rel_id, round_idx, len(rounds))
    ...
```

```python
# api_session_executor.py 多轮循环内
self._executor._handle_control(task_id)
round_number = round_config.get('round_number', round_idx + 1)
self._executor.execution_engine.update_case_round_progress(
    task_id, tc_rel_id, round_idx, len(rounds)
)
```

### 5. EventManager 侧读取轮次信息

`event_manager.py` 组装进度数据时，从内存缓存读取（**不查 DB**）：

```python
# event_manager.py → emit_progress 组装 test_cases_data 时
test_cases_data.append({
    "id": str(tc.test_case_id),
    "status": tc.status,
    "executionStatus": tc.execution_status,
    ...
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

注意 key 是 `tc.id`（TaskCase.id），与写入侧一致。

### 6. 进度数据中的轮次字段

```json
{
  "taskId": "task-001",
  "totalProgress": 45,
  "status": "running",
  "testCases": [
    {
      "id": "101",
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

未配置多轮 / 尚未开始的用例不含 `roundProgress` 字段（缓存无该 key）。

### 7. 缓存清理（防内存泄漏）

轮次缓存以 `tc_rel_id` 为 key，任务结束时需按任务查出其所有 `TaskCase.id` 逐个清理。两处清理点：

**a. `control_task()` 执行 stop 动作时**：

```python
tc_rel_ids = [
    tc_id for (tc_id,) in
    local_db_session.query(TaskCase.id).filter_by(task_id=task_id).all()
]
for tc_rel_id in tc_rel_ids:
    self.round_progress_cache.pop(tc_rel_id, None)
```

**b. `_run_task()` 的 finally 块**（正常完成 / 异常结束兜底）：

```python
# 清理线程和标志位
self.workers.pop(task_id, None)
self.stop_flags.pop(task_id, None)
self.pause_flags.pop(task_id, None)
self.task_completion_events.pop(task_id, None)
self.task_progress_cache.pop(task_id, None)
self.last_progress_update.pop(task_id, None)
# 清理多轮进度缓存（key 为 tc_rel_id，需查询当前任务的用例 ID）
try:
    cleanup_session = db.session()
    try:
        tc_rel_ids = [
            tc_id for (tc_id,) in
            cleanup_session.query(TaskCase.id).filter_by(task_id=task_id).all()
        ]
        for tc_rel_id in tc_rel_ids:
            self.round_progress_cache.pop(tc_rel_id, None)
    finally:
        cleanup_session.close()
except Exception:
    pass
```

---

## 数据流总览

```
Executor 多轮循环                     ExecutionEngine                    EventManager (emit_progress)
─────────────────                    ───────────────                    ──────────────────────────
round_idx 每轮开始 ──────────────►  update_case_round_progress()
                                       │ 写 round_progress_cache[tc_rel_id]
                                       └► _emit_progress(task_id, force=True)
                                             └► event_manager.emit_progress()
                                                  读 round_progress_cache[tc.id]
                                                  └► WebSocket 推送 roundProgress
任务结束（stop/完成/异常） ───────►  round_progress_cache.pop(tc_rel_id)（control_task / _run_task finally）
```

---

## 不变部分

- 任务调度逻辑（`_scheduler_loop`、`_schedule_pending_tasks`）不变
- 任务启动/停止/暂停控制不变
- 线程池管理不变
- 未配置 `rounds` 的用例进度报告不变（不写缓存，推送中无 `roundProgress` 字段）

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `31_event_manager多轮进度推送` | WebSocket 推送轮次信息（读取 `round_progress_cache`） |
| `18_TestExecutionComponent多轮进度` (frontend) | 前端显示轮次 |
