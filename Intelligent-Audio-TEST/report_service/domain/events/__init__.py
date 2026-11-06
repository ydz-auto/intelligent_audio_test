# -*- coding: utf-8 -*-
"""report_service 领域事件（re-export 入口）"""
from report_service.domain.events.report_events import (
    ReportDeleted,
    ReportEvent,
    ReportFailed,
    ReportGenerated,
)

__all__ = [
    'ReportEvent',
    'ReportGenerated',
    'ReportFailed',
    'ReportDeleted',
]
