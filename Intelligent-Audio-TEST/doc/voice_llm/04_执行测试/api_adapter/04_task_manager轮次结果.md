# 04 — task_manager 轮次结果

> **所属步骤**：04_执行测试 → api_adapter  
> **改造类型**：修改  
> **涉及文件**：`api_adaper_service/services/task_manager.py`

---

## 背景

现有 `TaskManager` 存储帧级结果（`frame_results: {task_id: [frame_result, ...]}`）和聚合后的最终结果。voice_llm 对话模式需要存储轮次级结果（每轮一个完整的请求-响应），而非帧级结果。

---

## 改造内容

### 1. 新增 `round_results` 存储

```python
class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.frame_results = defaultdict(list)   # 现有：帧级结果
        self.round_results = defaultdict(list)    # 新增：轮次结果
        self.final_results = {}

    def add_round_result(self, task_id: str, round_idx: int, result: dict):
        """
        添加轮次结果。

        Args:
            task_id: 任务 ID
            round_idx: 轮次编号
            result: {
                "asr_text": "...",
                "trans_text": "...",
                "latency": 1.5,
                "raw_response": {...}
            }
        """
        self.round_results[task_id].append({
            'round': round_idx,
            'result': result,
            'timestamp': time.time(),
        })

    def get_round_results(self, task_id: str) -> list:
        """获取任务的所有轮次结果"""
        return self.round_results.get(task_id, [])

    def get_round_result(self, task_id: str, round_idx: int) -> Optional[dict]:
        """获取指定轮次的结果"""
        results = self.round_results.get(task_id, [])
        for r in results:
            if r['round'] == round_idx:
                return r
        return None
```

### 2. 扩展 `get_final_result()`

```python
def get_final_result(self, task_id: str) -> Optional[dict]:
    """获取最终结果（兼容帧级和轮次级）"""
    task = self.tasks.get(task_id)
    if not task:
        return None

    # 如果有轮次结果（对话模式）
    if task_id in self.round_results:
        rounds = self.round_results[task_id]
        return {
            'task_id': task_id,
            'session_id': task.get('session_id', ''),
            'status': task['status'],
            'result_type': 'dialog',
            'total_rounds': len(rounds),
            'rounds': [
                {
                    'round': r['round'],
                    'asr_text': r['result'].get('asr_text', ''),
                    'trans_text': r['result'].get('trans_text', ''),
                    'latency': r['result'].get('latency', 0),
                }
                for r in sorted(rounds, key=lambda x: x['round'])
            ],
            'total_latency': sum(
                r['result'].get('latency', 0) for r in rounds
            ),
        }

    # 帧级结果（现有逻辑）
    if task_id in self.final_results:
        result = self.final_results[task_id]
        result['result_type'] = 'streaming'
        return result

    return None
```

### 3. `delete_task` 清理

```python
def delete_task(self, task_id: str):
    """删除任务及其所有结果"""
    self.tasks.pop(task_id, None)
    self.frame_results.pop(task_id, None)
    self.round_results.pop(task_id, None)
    self.final_results.pop(task_id, None)
```

### 4. 结果类型对比

| 字段 | streaming（帧级） | dialog（轮次级） |
|------|-------------------|-----------------|
| `result_type` | `"streaming"` | `"dialog"` |
| `final_asr_result` | 拼接的 ASR 文本 | — |
| `final_trans_result` | 拼接的翻译文本 | — |
| `rounds` | — | 轮次结果数组 |
| `total_rounds` | — | 轮次数 |
| `total_latency` | — | 总延迟 |
| `session_id` | — | 会话 ID |

---

## 不变部分

- `create_task()` 不变
- `add_frame_result()` 不变（帧级任务继续使用）
- `get_frame_results()` 不变
- 任务状态管理不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `03_create_task对话模式` | 对话任务入口 |
| `02_会话状态管理` | 会话状态 |
| `14_轮次请求构建` (主后端) | 请求方 |
