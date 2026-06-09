import threading
from ..config import config

class ConcurrencyManager:
    _stats = {
        'wer': {'current': 0, 'max': config.CONCURRENCY_LIMITS.get('wer', config.DEFAULT_MAX_CONCURRENCY)},
        'ser': {'current': 0, 'max': config.CONCURRENCY_LIMITS.get('ser', config.DEFAULT_MAX_CONCURRENCY)}
    }
    _lock = threading.Lock()

    @classmethod
    def get_stats(cls):
        with cls._lock:
            return {k: v.copy() for k, v in cls._stats.items()}

    @classmethod
    def can_start(cls, task_type):
        with cls._lock:
            stats = cls._stats.get(task_type)
            if stats and stats['current'] < stats['max']:
                return True
            return False

    @classmethod
    def increment(cls, task_type):
        with cls._lock:
            if task_type in cls._stats:
                cls._stats[task_type]['current'] += 1

    @classmethod
    def decrement(cls, task_type):
        with cls._lock:
            if task_type in cls._stats:
                cls._stats[task_type]['current'] -= 1
