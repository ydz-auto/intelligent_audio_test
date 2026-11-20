# -*- coding: utf-8 -*-
"""Agent 模型供应商管理审计（INT-2488）。

对齐 auth_audit / device_audit 旁路模式：审计写入失败不影响业务结果。
事件名取 ``shared.models.common_enums.AuditEvent``，category 固定
``system``（AuditLogCategory.SYSTEM）。

硬约束（§6.4-6 / §13-7）：payload 只含 provider_id、操作类型、操作人与
结果状态码；**绝不写请求体**（里面有明文 Key），也不写密文。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def write_agent_provider_audit(event, *, request: Any,
                               provider_id: Optional[str],
                               operation: str,
                               status_code: Optional[int] = None) -> None:
    try:
        from shared.models.common_enums import AuditLogCategory
        from shared.utils.log_handler import log_not_emit

        payload = {
            'event': event.value,
            'provider_id': provider_id or '',
            'operation': operation,
            'operator_id': getattr(request.state, 'user_id', None),
            'operator': getattr(request.state, 'username', '') or '',
            'status_code': status_code,
        }
        log_not_emit(
            'INFO', 'agent_provider',
            json.dumps(payload, ensure_ascii=False, default=str),
            category=AuditLogCategory.SYSTEM.value, source='api_gateway',
            audit_event=event,
        )
    except Exception:  # noqa: BLE001 - 审计为旁路
        logger.warning('审计事件 %s 落库失败', getattr(event, 'value', event),
                       exc_info=True)


__all__ = ['write_agent_provider_audit']
