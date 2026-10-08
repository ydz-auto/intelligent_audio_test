# -*- coding: utf-8 -*-
"""transfer_agent 领域事件。

描述传输链路中已发生的事实（审计层依据之一），由应用层 handler 在命令成功后产生。
事件仅落传输流水表与日志，不进跨服务事件通道（五通道契约不涉及传输域）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


def utc8now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


@dataclass
class TransferEvent:
    """传输事件基类。"""
    transfer_id: str
    occurred_at: datetime = field(default_factory=utc8now)


@dataclass
class TransferCreated(TransferEvent):
    """传输会话创建（含幂等命中复现）。"""
    pkg_type: str = ''
    src_zone: str = ''
    dst_zone: str = ''
    dedup: bool = False


@dataclass
class TransferChunkReceived(TransferEvent):
    """分片接收（含去重命中）。"""
    chunk_index: int = 0
    checksum: str = ''
    dedup: bool = False


@dataclass
class TransferCompleted(TransferEvent):
    """传输完成（合并 + file_hash 校验通过）。"""
    pkg_type: str = ''
    file_size: int = 0
    final_path: str = ''


@dataclass
class TransferFailed(TransferEvent):
    """传输失败（终态，通常为内容校验不过）。"""
    reason: str = ''


@dataclass
class TransferExpired(TransferEvent):
    """传输过期回收（分片/临时文件清理）。"""
    status_before: str = ''
