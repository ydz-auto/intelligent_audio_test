# -*- coding: utf-8 -*-
"""visibility 审计事件写入（INT-466）——api_gateway 侧旁路记录。

对齐 auth_audit / device_audit 旁路模式：审计为旁路记录，写入失败不影响业务
结果。事件名取 shared.models.common_enums.AuditEvent（PRIVATE_RESOURCE_ACCESS），
category 固定 'visibility'（AuditLogCategory.VISIBILITY，emit 分流保证落 logs 表）。

触发语义（数据可见性设计文档 §五/§六）：
- PRIVATE_RESOURCE_ACCESS：admin 访问/修改私有资源，或任何可见性切换操作触碰
  私有态（资源由 private 改出 / 改入 private）时落审计，含资源类型 / ID /
  操作人 / 动作。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def write_visibility_audit(event, module: str, content: Dict[str, Any]) -> None:
    """写一条 visibility 审计事件到 logs（category='visibility'，source='api_gateway'）。

    Args:
        event: AuditEvent 枚举成员（PRIVATE_RESOURCE_ACCESS）
        module: 日志 module 标识（visibility_access / visibility_update）
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
            category=AuditLogCategory.VISIBILITY.value, source='api_gateway',
        )
    except Exception:
        logger.warning('审计事件 %s 落库失败', getattr(event, 'value', event),
                       exc_info=True)


def write_private_access_audit(
    resource_type: str,
    resource_id: Any,
    action: str,
    operator_id: Optional[int] = None,
) -> None:
    """写一条 PRIVATE_RESOURCE_ACCESS 审计事件。

    Args:
        resource_type: 资源类型（task / testcase / group / tag / report / dimension / audio）
        resource_id: 资源 ID
        action: 动作（read / update / delete / update_visibility）
        operator_id: 操作人 user_id（缺省从 request.state 取）
    """
    from shared.models.common_enums import AuditEvent

    if operator_id is None:
        from api_gateway.infrastructure.request_adapter import get_current_request
        req = get_current_request()
        operator_id = getattr(req.state, 'user_id', None) if req else None

    write_visibility_audit(
        AuditEvent.PRIVATE_RESOURCE_ACCESS,
        'visibility_access',
        {
            'resource_type': resource_type,
            'resource_id': resource_id,
            'action': action,
            'operator_id': operator_id,
        },
    )


def maybe_audit_private_detail(resource_type: str, resource_id: Any, data: Optional[Dict]) -> None:
    """admin 访问私有资源详情 → PRIVATE_RESOURCE_ACCESS（旁路，失败不影响业务）。

    仅当当前用户为 admin 且资源 visibility='private' 时落审计（设计文档 §五）。
    data 为详情响应 data dict（须含 visibility 字段）；缺失按非私有处理。
    """
    try:
        from shared.models.common_enums import Visibility
        from api_gateway.application.services.visibility.visibility_service import (
            VisibilityService,
        )

        user_id, is_admin = VisibilityService.get_identity()
        if not is_admin:
            return
        vis = (data or {}).get('visibility')
        if vis != Visibility.PRIVATE.value:
            return
        write_private_access_audit(resource_type, resource_id, 'read', operator_id=user_id)
    except Exception:
        logger.warning('PRIVATE_RESOURCE_ACCESS 读审计失败 resource_type=%s id=%s',
                       resource_type, resource_id, exc_info=True)


def maybe_audit_private_write(resource_type: str, resource_id: Any, action: str,
                              data: Optional[Dict]) -> None:
    """admin 修改/删除私有资源 → PRIVATE_RESOURCE_ACCESS（旁路，失败不影响业务）。

    写路径（update/delete）调用：调用方在写前经 preload_private_state 预取资源
    data（须含 visibility 字段）；当前用户为 admin 且资源 visibility='private' 时
    落 action='update'/'delete' 审计。data 缺失或非 private 无操作；旁路失败
    不影响业务结果。
    """
    try:
        from shared.models.common_enums import Visibility
        from api_gateway.application.services.visibility.visibility_service import (
            VisibilityService,
        )

        user_id, is_admin = VisibilityService.get_identity()
        if not is_admin:
            return
        vis = (data or {}).get('visibility')
        if vis != Visibility.PRIVATE.value:
            return
        write_private_access_audit(resource_type, resource_id, action, operator_id=user_id)
    except Exception:
        logger.warning('PRIVATE_RESOURCE_ACCESS %s 审计失败 resource_type=%s id=%s',
                       action, resource_type, resource_id, exc_info=True)


def preload_private_state(fetch_data) -> Optional[Dict]:
    """写路径预取目标资源 data（含 visibility）——仅 admin 取数，旁路。

    返回 dict 或 None：非 admin / 取数失败返回 None；否则返回 fetch_data() 的
    dict 结果，供 maybe_audit_private_write 判定。避免非 admin 写路径产生额外
    gRPC 往返。
    """
    from api_gateway.application.services.visibility.visibility_service import (
        VisibilityService,
    )

    _, is_admin = VisibilityService.get_identity()
    if not is_admin:
        return None
    try:
        return fetch_data() or {}
    except Exception:
        logger.warning('写路径私有态预取失败', exc_info=True)
        return None
