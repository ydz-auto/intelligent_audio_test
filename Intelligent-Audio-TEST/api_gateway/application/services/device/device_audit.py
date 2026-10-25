# -*- coding: utf-8 -*-
"""device 审计事件写入（INT-80：分组/操作/批量端点审计）。

旁路模式对齐 auth_audit / benchmark_audit：审计为旁路记录，
写入失败不影响业务结果。事件名取 shared.models.common_enums.AuditEvent，
category 固定 'device'（AuditLogCategory.DEVICE，emit 分流保证落 logs 表）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def write_device_audit(event, module: str, content: Dict[str, Any]) -> None:
    """写一条 device 审计事件到 logs（category='device'）。

    Args:
        event: AuditEvent 枚举成员（DEVICE_*）
        module: 日志 module 标识（device_group / device_control / device_batch）
        content: 事件结构化负载（自动附加 event / operator）
    """
    try:
        from api_gateway.infrastructure.request_adapter import request
        from shared.models.common_enums import AuditLogCategory
        from shared.utils.log_handler import log_not_emit

        payload = dict(content or {})
        payload['event'] = event.value
        payload['operator'] = request.username or ''
        log_not_emit(
            'INFO', module, json.dumps(payload, ensure_ascii=False, default=str),
            category=AuditLogCategory.DEVICE.value, source='api_gateway',
        )
    except Exception:
        logger.warning('审计事件 %s 落库失败', getattr(event, 'value', event), exc_info=True)
