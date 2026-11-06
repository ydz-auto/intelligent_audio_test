# -*- coding: utf-8 -*-
"""task_service 领域值对象（re-export 入口）"""
from task_service.domain.value_objects.task_config import (
    TaskConfig,
    TaskId,
    TaskProgress,
)

__all__ = ['TaskConfig', 'TaskId', 'TaskProgress']
