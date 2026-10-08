# -*- coding: utf-8 -*-
"""auth 审计事件写入（落库 logs，失败仅告警不阻断主流程）

对齐 benchmark_audit 旁路模式：审计为旁路记录，写入失败不影响业务结果。
事件名统一取 shared.models.common_enums.AuditEvent（拒绝魔法字符串），
category 固定 'auth'。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from shared.models.common_enums import AuditEvent, AuditLogCategory

logger = logging.getLogger(__name__)


def write_auth_audit(
    event: AuditEvent, module: str, content: Dict[str, Any],
) -> None:
    """写一条 auth 审计事件到 logs（category='auth'）。

    Args:
        event: AuditEvent 枚举成员
        module: 日志 module 标识（如 user_management / role_management）
        content: 事件结构化负载（自动附加 event 事件名；
            约定携带 operator_id / target_id / delta 字段）
    """
    try:
        from shared.utils.log_handler import log_not_emit
        payload = dict(content or {})
        payload['event'] = event.value
        log_not_emit(
            'INFO', module, json.dumps(payload, ensure_ascii=False, default=str),
            category=AuditLogCategory.AUTH.value, source=module,
        )
    except Exception:
        logger.warning('审计事件 %s 落库失败', event.value, exc_info=True)
