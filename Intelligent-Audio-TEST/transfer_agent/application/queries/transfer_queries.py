# -*- coding: utf-8 -*-
"""transfer_agent 应用层查询（CQRS 读侧）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GetTransferStatusQuery:
    """查询传输状态与已收分片清单（断点续传依据）。"""
    transfer_id: str
    token: str = ''


@dataclass
class GetTransferQuery:
    """查询传输包完整元数据（审计流水视图）。"""
    transfer_id: str
    token: str = ''
