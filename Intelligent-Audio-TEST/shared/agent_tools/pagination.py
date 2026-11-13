# -*- coding: utf-8 -*-
"""查询类意图工具的分页边界（INT-2552）。

所有读侧意图工具的 ``page`` / ``per_page`` 共用同一组边界：

- ``page >= PAGE_MIN``（页码从 1 开始，无上界）；
- ``PAGE_MIN <= per_page <= PER_PAGE_MAX``。

为什么要在工具层拦：网关对 ``page=0`` 与超大 ``per_page`` **不报错**（实测
``page=0`` 返回首页、``per_page=100000`` 一次返回全量），放过去会让模型用一次
调用拉全表；超量结果进入 Loop 后被 ``run_orchestrator`` 的 8000 字符硬截断成
不可解析文本回灌模型（INT-2547 审计 P2-2）。

Schema 的 ``minimum`` / ``maximum`` 与工具层校验共用本模块的常量，不允许各工具
另写一份数字：``intent_tools.validate_arguments`` 按 Schema 先校验一次，
``resolve_rest_call`` / ``device_tools.normalize_arguments`` 再按同一常量兜一次。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# 页码下界（REST 网关自身不校验，见模块 docstring）
PAGE_MIN = 1
# 单次返回条数上界（与报告域既有口径一致）
PER_PAGE_MAX = 200


def check_page_bounds(action: str, merged: Dict[str, Any]) -> Optional[str]:
    """校验 ``page`` / ``per_page`` 边界，返回可读错误文本或 None。

    不发起任何上游请求；``action`` 只用于错误文案定位。
    """
    page = merged.get('page')
    if page is not None:
        if isinstance(page, bool) or not isinstance(page, int) \
                or page < PAGE_MIN:
            return (f'参数 page 必须是 ≥{PAGE_MIN} 的整数'
                    f'（action={action} 收到 {page!r}）')
    per_page = merged.get('per_page')
    if per_page is not None:
        if isinstance(per_page, bool) or not isinstance(per_page, int) \
                or per_page < PAGE_MIN:
            return (f'参数 per_page 必须是 ≥{PAGE_MIN} 的整数'
                    f'（action={action} 收到 {per_page!r}）')
        if per_page > PER_PAGE_MAX:
            return (f'参数 per_page 上限 {PER_PAGE_MAX}'
                    f'（action={action} 收到 {per_page}）；需要更多请分页取')
    return None


__all__ = ['PAGE_MIN', 'PER_PAGE_MAX', 'check_page_bounds']
