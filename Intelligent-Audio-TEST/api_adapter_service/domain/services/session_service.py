# -*- coding: utf-8 -*-
"""API 适配领域服务

说明：与同包 ``__init__`` 内已有的 ``AdapterSelector`` 并存。
本模块提供会话状态校验等无状态纯函数，供 application / interfaces 层复用。
"""

from typing import Optional


def validate_session_status(session_id: str, status: str) -> bool:
    """校验会话状态是否有效"""
    valid_statuses = {'active', 'closed', 'expired'}
    return status in valid_statuses


def can_send_message(session_status: str, turn_count: int, max_turns: int) -> bool:
    """检查是否可以发送消息"""
    if session_status != 'active':
        return False
    if turn_count >= max_turns:
        return False
    return True
