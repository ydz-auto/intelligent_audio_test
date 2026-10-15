# -*- coding: utf-8 -*-
"""auth 登录/登出审计事件写入（INT-406）——api_gateway 侧旁路记录。

对齐 device_audit / auth_service.auth_audit 旁路模式：审计为旁路记录，
写入失败不影响业务结果。事件名取 shared.models.common_enums.AuditEvent
（拒绝魔法字符串），category 固定 'auth'（AuditLogCategory.AUTH，
emit 分流保证落 logs 表）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def write_auth_audit(event, module: str, content: Dict[str, Any]) -> None:
    """写一条 auth 审计事件到 logs（category='auth'，source='api_gateway'）。

    Args:
        event: AuditEvent 枚举成员（AUTH_LOGIN / AUTH_LOGOUT）
        module: 日志 module 标识（auth_login / auth_logout）
        content: 事件结构化负载（自动附加 event；约定携带 operator_id /
            operator 用户名；登录事件另带 provider 登录通道）
    """
    try:
        from shared.models.common_enums import AuditLogCategory
        from shared.utils.log_handler import log_not_emit

        payload = dict(content or {})
        payload['event'] = event.value
        log_not_emit(
            'INFO', module, json.dumps(payload, ensure_ascii=False, default=str),
            category=AuditLogCategory.AUTH.value, source='api_gateway',
        )
    except Exception:
        logger.warning('审计事件 %s 落库失败', getattr(event, 'value', event),
                       exc_info=True)
