# -*- coding: utf-8 -*-
"""统一日志记录方法"""
from shared.utils.log_handler import log_and_emit


class LoggingMixin:
    """执行器基类日志相关方法"""

    def _log(self, level, content, task_id=None, test_case_id=None, device_id=None, api_id=None, category='execution', **kwargs):
        """统一日志记录方法"""
        final_test_case_id = test_case_id or getattr(self._thread_ctx, 'current_test_case_id', None) or self.current_test_case_id

        log_and_emit(
            level=level,
            module='Engine',
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            test_case_id=final_test_case_id,
            device_id=device_id,
            api_id=api_id,
            **kwargs
        )
