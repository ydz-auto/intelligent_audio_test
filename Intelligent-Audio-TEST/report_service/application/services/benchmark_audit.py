# -*- coding: utf-8 -*-
"""Benchmark 审计事件写入（落库 logs，失败仅告警不阻断主流程）

对齐 task_service 发布审计模式：审计为旁路记录，写入失败不影响业务结果。
事件名统一取 shared.models.common_enums.AuditEvent（拒绝魔法字符串）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from shared.models.common_enums import AuditEvent, AuditLogCategory

logger = logging.getLogger(__name__)


def write_benchmark_audit(
    event: AuditEvent, module: str, content: Dict[str, Any],
) -> None:
    """写一条 Benchmark 审计事件到 logs（category=benchmark）。

    Args:
        event: AuditEvent 枚举成员
        module: 日志 module 标识（如 benchmark_ranking / benchmark_baseline）
        content: 事件结构化负载（自动附加 event 事件名）
    """
    try:
        from shared.utils.log_handler import log_not_emit
        payload = dict(content or {})
        payload['event'] = event.value
        log_not_emit(
            'INFO', module, json.dumps(payload, ensure_ascii=False, default=str),
            category=AuditLogCategory.BENCHMARK.value, source=module,
        )
    except Exception:
        logger.warning('审计事件 %s 落库失败', event.value, exc_info=True)
