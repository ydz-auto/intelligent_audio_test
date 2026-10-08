# 04 — ConcurrencyManager 动态类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/utils/concurrency.py`

---

## 背景

`ConcurrencyManager` 管理每种任务类型的并发限制（current/max）。当前实现不再硬编码两个类型，而是通过 `_ensure_initialized()` 懒加载初始化所有已知任务类型，并支持 `register_task_type` 动态注册未知类型。

> **类型清单口径（三处不一致，以代码为准）**：
>
> | 清单 | 数量 | 内容 |
> |------|------|------|
> | `concurrency.py` `_ensure_initialized` 硬编码 `all_types` | 14 | 含旧键 `env_judge`，**不含** `rejection_judge`/`interruption_judge` |
> | `config.CONCURRENCY_LIMITS` | 16 | 含 `env_judge` + `rejection_judge` + `interruption_judge`（多出的 2 键不会预置进 `_stats`） |
> | `calculators` 注册表 + `api.py` 白名单 | 18 键 / 15 白名单 | 见 `02_评估维度架构` 对照表 |
>
> `env_judge` 是**历史遗留命名**：真实计算维度已拆分注册为 `rejection_judge` / `interruption_judge`（见 02 文档 env_judge 域）。`_ensure_initialized` 只按 14 项预置；`_initialized=True` 后首次访问 `rejection_judge`/`interruption_judge` 时由 `can_start`/`increment` **就地动态注册**（默认 `DEFAULT_MAX_CONCURRENCY=10`，恰与 config 键一致，无行为差异）。

---

## 实际实现

### 1. 懒加载初始化 `_stats`

```python
class ConcurrencyManager:
    _stats = {}            # {task_type: {'current': int, 'max': int}}
    _lock = threading.Lock()
    _initialized = False

    @classmethod
    def _ensure_initialized(cls):
        """确保所有已知类型都已初始化（双重检查锁）"""
        if cls._initialized:
            return
        with cls._lock:
            if cls._initialized:
                return
            all_types = [
                'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer',
                'llm_judge',
                'turn_taking', 'interruption_metrics', 'non_interactive_latency',
                'noise_latency', 'env_judge',
                'high_freq_turn_taking', 'high_freq_llm_judge',
            ]
            limits = getattr(config, 'CONCURRENCY_LIMITS', {})
            default_max = getattr(config, 'DEFAULT_MAX_CONCURRENCY', 2)
            for task_type in all_types:
                if task_type not in cls._stats:
                    max_concurrency = limits.get(task_type, default_max)
                    cls._stats[task_type] = {'current': 0, 'max': max_concurrency}
            cls._initialized = True
```

> 所有已知类型 14 种，均从 `config.CONCURRENCY_LIMITS` 读取限制，缺失时回退 `DEFAULT_MAX_CONCURRENCY`（10）。`turn_taking` 主维度按一个并发键统一限流，其 7 个子维度（tor/false_takeover/takeover_latency 等）不单独占用并发键。

### 2. 动态注册新类型

```python
@classmethod
def register_task_type(cls, task_type: str, max_concurrency: int = None):
    """动态注册新的任务类型"""
    if max_concurrency is None:
        max_concurrency = getattr(config, 'DEFAULT_MAX_CONCURRENCY', 3)
    with cls._lock:
        if task_type not in cls._stats:
            cls._stats[task_type] = {'current': 0, 'max': max_concurrency}
```

### 3. can_start / increment / decrement 容错

```python
@classmethod
def can_start(cls, task_type):
    cls._ensure_initialized()
    with cls._lock:
        stats = cls._stats.get(task_type)
        if stats is None:
            # 未知类型：就地注册，默认允许
            cls._stats[task_type] = {
                'current': 0, 'max': getattr(config, 'DEFAULT_MAX_CONCURRENCY', 3),
            }
            stats = cls._stats[task_type]
        return stats['current'] < stats['max']

@classmethod
def increment(cls, task_type):
    cls._ensure_initialized()
    with cls._lock:
        if task_type not in cls._stats:
            cls.register_task_type(task_type)
        cls._stats[task_type]['current'] += 1

@classmethod
def decrement(cls, task_type):
    cls._ensure_initialized()
    with cls._lock:
        if task_type in cls._stats:
            cls._stats[task_type]['current'] = max(0, cls._stats[task_type]['current'] - 1)
```

### 4. get_stats 返回快照

```python
@classmethod
def get_stats(cls):
    cls._ensure_initialized()
    with cls._lock:
        return {k: v.copy() for k, v in cls._stats.items()}
```

返回浅拷贝快照（外层字典新对象，内层 dict 也复制），避免调用方直接改内部状态。

### 5. 实际并发配置（config.py）

```python
CONCURRENCY_LIMITS = {
    'wer': 10, 'ser': 10, 'der': 5,
    'cpwer': 10, 'tcpwer': 10, 'stm_wer': 10,
    'llm_judge': 10,
    'turn_taking': 10, 'interruption_metrics': 10,
    'non_interactive_latency': 10, 'noise_latency': 10,
    'env_judge': 10, 'rejection_judge': 10, 'interruption_judge': 10,
    'high_freq_turn_taking': 10, 'high_freq_llm_judge': 10,
}
DEFAULT_MAX_CONCURRENCY = 10
```

> 本地任务的真实上限由 `LOCAL_MAX_CONCURRENCY = 30`（api.py 的 LocalConcurrencyManager + 线程池）控制；`ConcurrencyManager` 用于后台 worker（`start_worker`）的按类型限流，两者职责不同。

### 6. 各类型并发建议

| 类型 | 并发 | 原因 |
|------|------|------|
| `wer`/`ser`/`cpwer`/`tcpwer`/`stm_wer` | 10 | 文本比较为主 |
| `der` | 5 | pyannote 内存占用大 |
| `llm_judge` | 10 | 外部 API 调用，受 rate limit |
| xiaoyi_metrics 系列 | 10 | 音频/文本混合计算（turn_taking 主维度整体占 1 键） |

---

## 不变部分

- 锁机制不变
- 基本接口（can_start/increment/decrement/get_stats）不变
- 装饰器 `@limit_task_concurrency` 不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_评估维度架构_策略模式与主从维度` | 18 键注册表 / 15 白名单（并发类型口径对比基准）、主维度子维度并发语义 |
| `01_create_task新任务类型` | 新类型任务入口 |
| `07_health动态类型` | 健康检查展示并发状态 |
| `03_LLM_Judge计算器` | llm_judge 计算实现 |