# -*- coding: utf-8 -*-
"""transfer_agent 应用层命令（CQRS 写侧）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CreateTransferCommand:
    """创建传输会话命令（字段即传输包协议）。"""
    transfer_id: str
    pkg_type: str
    src_zone: str
    dst_zone: str
    category: str
    key: str
    file_hash: str
    file_size: int
    ttl_seconds: int
    timestamp: str
    signature: str
    ephemeral: bool = False
    token: str = ''
    meta: dict = field(default_factory=dict)
    chunk_size: Optional[int] = None     # 缺省用服务端配置（默认 4MB）


@dataclass
class UploadChunkCommand:
    transfer_id: str
    chunk_index: int
    data: bytes
    checksum: str
    token: str = ''


@dataclass
class CompleteTransferCommand:
    transfer_id: str
    token: str = ''


@dataclass
class ExpirePackagesCommand:
    """TTL 过期清理命令（sweeper / 测试触发）。"""
    now: Optional[object] = None         # datetime，None 取当前时间
    limit: int = 100
