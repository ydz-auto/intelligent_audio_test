# 04 — ConcurrencyManager 动态类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/utils/concurrency.py`

---

## 背景

`ConcurrencyManager` 管理每种任务类型的并发限制。当前 `_stats` 字典硬编码了 `wer` 和 `ser` 两种类型，新增的 `llm_judge` 以及已有的 `der`、`cpwer`、`tcpwer`、`stm_wer` 不在其中。对这些类型调用 `can_start()` 会因 `stats.get(task_type)` 返回 `None` 而返回 `False`。

---

## 改造内容

### 1. 动态初始化 `_stats`

```python
class ConcurrencyManager:
    _stats = {}  # 改为空字典，动态初始化
    _lock = threading.Lock()
    _initialized = False

    @classmethod
    def _ensure_initialized(cls):
        """确保所有已知类型都已初始化"""
        if cls._initialized:
            return

        with cls._lock:
            if cls._initialized:
                return

            from app.config import config
            default_max = getattr(config, 'DEFAULT_MAX_CONCURRENCY', 2)
            limits = getattr(config, 'CONCURRENCY_LIMITS', {})

            # 所有已知的任务类型
            all_types = [
                'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer',
                'llm_judge',
            ]

            for task_type in all_types:
                max_concurrency = limits.get(task_type, default_max)
                cls._stats[task_type] = {
                    'current': 0,
                    'max': max_concurrency,
                }

            cls._initialized = True
```

### 2. 动态注册新类型

```python
@classmethod
def register_task_type(cls, task_type: str, max_concurrency: int = 2):
    """动态注册新的任务类型"""
    with cls._lock:
        if task_type not in cls._stats:
            cls._stats[task_type] = {
                'current': 0,
                'max': max_concurrency,
            }
```

### 3. can_start 容错

```python
@classmethod
def can_start(cls, task_type: str) -> bool:
    cls._ensure_initialized()

    with cls._lock:
        stats = cls._stats.get(task_type)
        if stats is None:
            # 未知类型：动态注册，默认允许
            cls.register_task_type(task_type)
            stats = cls._stats[task_type]
        return stats['current'] < stats['max']
```

### 4. increment / decrement 容错

```python
@classmethod
def increment(cls, task_type: str):
    cls._ensure_initialized()

    with cls._lock:
        if task_type not in cls._stats:
            cls.register_task_type(task_type)
        cls._stats[task_type]['current'] += 1

@classmethod
def decrement(cls, task_type: str):
    cls._ensure_initialized()

    with cls._lock:
        if task_type in cls._stats:
            cls._stats[task_type]['current'] = max(
                0, cls._stats[task_type]['current'] - 1
            )
```

### 5. get_stats 返回完整信息

```python
@classmethod
def get_stats(cls) -> dict:
    cls._ensure_initialized()

    with cls._lock:
        import copy
        return copy.deepcopy(cls._stats)
```

### 6. 配置中的并发限制

```python
# config.py
class Config:
    CONCURRENCY_LIMITS = {
        'wer': 2,
        'ser': 1,
        'der': 1,
        'cpwer': 2,
        'tcpwer': 2,
        'stm_wer': 2,
        'llm_judge': 2,     # LLM API 调用慢，限制并发
    }
    DEFAULT_MAX_CONCURRENCY = 2
```

### 7. 各类型并发限制建议

| 类型 | 建议并发 | 原因 |
|------|---------|------|
| `wer` | 2 | CPU 密集型（Levenshtein） |
| `ser` | 1 | CPU 密集型 |
| `der` | 1 | pyannote 内存占用大 |
| `llm_judge` | 2 | 外部 API 调用，受 rate limit |
| `cpwer` | 2 | meeteval 计算 |

---

## 不变部分

- 锁机制不变
- 基本 API 接口（can_start/increment/decrement）不变
- 装饰器 `@limit_task_concurrency` 不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` | 新类型任务入口 |
| `06_health动态类型` | 健康检查展示 |
