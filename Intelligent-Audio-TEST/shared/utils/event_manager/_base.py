from shared.utils.log_handler import log_and_emit


class BaseEventManagerMixin:
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='EventManager', **kwargs):
        kwargs_to_use = kwargs.copy()
        kwargs_to_use.pop('source', None)
        log_and_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs_to_use
        )

    def _format_duration(self, seconds_value):
        try:
            seconds = float(seconds_value or 0)
        except Exception:
            return None
        if seconds <= 0:
            return "0分钟"
        seconds_int = int(seconds)
        if seconds_int < 60:
            return f"{seconds_int}秒"
        if seconds_int < 3600:
            minutes = seconds_int // 60
            remain_seconds = seconds_int % 60
            if remain_seconds > 0:
                return f"{minutes}分钟{remain_seconds}秒"
            return f"{minutes}分钟"
        hours = seconds_int // 3600
        minutes = (seconds_int % 3600) // 60
        if minutes > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{hours}小时"

    def __init__(self, execution_engine):
        self.execution_engine = execution_engine
        self._last_progress = {}
        try:
            import os
            self._min_update_interval = float(os.environ.get('WEBSOCKET_MIN_UPDATE_INTERVAL', '0.1'))
        except Exception as e:
            self._min_update_interval = 0.1

        self._progress_throttle_interval = 0.05
        self._last_progress_time = {}
        self._progress_cache = {}  # 进度缓存，减少数据库查询
