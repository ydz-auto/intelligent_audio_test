import threading
from ..config import config

class ConcurrencyManager:
    _stats = {}
    _lock = threading.Lock()
    _initialized = False

    @classmethod
    def _ensure_initialized(cls):
        """Lazily initialize all known task types from config."""
        if cls._initialized:
            return
        with cls._lock:
            if cls._initialized:
                return
            all_types = [
                'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer',
                'llm_judge',
            ]
            limits = getattr(config, 'CONCURRENCY_LIMITS', {})
            default_max = getattr(config, 'DEFAULT_MAX_CONCURRENCY', 2)
            for task_type in all_types:
                if task_type not in cls._stats:
                    max_concurrency = limits.get(task_type, default_max)
                    cls._stats[task_type] = {
                        'current': 0,
                        'max': max_concurrency,
                    }
            cls._initialized = True

    @classmethod
    def register_task_type(cls, task_type: str, max_concurrency: int = 2):
        """Dynamically register a new task type."""
        with cls._lock:
            if task_type not in cls._stats:
                cls._stats[task_type] = {
                    'current': 0,
                    'max': max_concurrency,
                }

    @classmethod
    def get_stats(cls):
        cls._ensure_initialized()
        with cls._lock:
            return {k: v.copy() for k, v in cls._stats.items()}

    @classmethod
    def can_start(cls, task_type):
        cls._ensure_initialized()
        with cls._lock:
            stats = cls._stats.get(task_type)
            if stats is None:
                cls._stats[task_type] = {
                    'current': 0,
                    'max': getattr(config, 'DEFAULT_MAX_CONCURRENCY', 2),
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
                cls._stats[task_type]['current'] = max(
                    0, cls._stats[task_type]['current'] - 1
                )
