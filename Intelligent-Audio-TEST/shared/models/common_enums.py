# -*- coding: utf-8 -*-
"""跨服务共享枚举

这些枚举不是 PO（无 __tablename__），不归属任何单一服务，
作为跨服务共享的领域语义保持在本文件。

- ReportStatus  报告状态（归属 report_service 域，但被多处引用）
- TaskStatus    任务状态（归属 task_service 域，但被多处引用）
- ReportType    报告类型（归属 report_service 域，但被多处引用）

P5 改造：从 shared/models/models/user_models.py 中拆出（原 user_models
混入这三个枚举是历史遗留），user_models 的 PO 已下沉到 auth_service。
"""
from enum import Enum


class ReportStatus(str, Enum):
    """报告状态枚举"""
    DRAFT = 'draft'
    PUBLISHED = 'published'


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    MERGED = 'merged'


class ReportType(str, Enum):
    """报告类型枚举"""
    TASK = 'task'
    COMPARISON = 'comparison'
    SECONDARY_COMPARISON = 'secondary_comparison'
