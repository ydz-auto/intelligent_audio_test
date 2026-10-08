# -*- coding: utf-8 -*-
"""transfer_agent 仓储与端口抽象接口（ABC）。

DDD 规则：领域层定义接口，infrastructure/persistence 与 infrastructure/acl、
infrastructure/storage 提供具体实现，上层依赖注入使用。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from transfer_agent.domain.entities.transfer_package import (
    TransferChunkRecord,
    TransferPackage,
)


class TransferRecordRepositoryABC(ABC):
    """传输流水仓储抽象（幂等唯一键 transfer_id，审计层落点）。"""

    @abstractmethod
    def find_by_transfer_id(self, transfer_id: str) -> Optional[TransferPackage]:
        """按 transfer_id 查询传输包聚合，不存在返回 None。"""

    @abstractmethod
    def add(self, package: TransferPackage) -> None:
        """新增传输包流水。"""

    @abstractmethod
    def save(self, package: TransferPackage) -> None:
        """按 transfer_id 回写聚合状态变更（状态/最终路径）。"""

    @abstractmethod
    def list_expired(self, now: datetime, limit: int = 100) -> List[TransferPackage]:
        """列出已过 TTL 且需要回收的包：

        - 未完成包（CREATED/TRANSFERRING）超时
        - COMPLETED 且 ephemeral=true 的包（中转临时数据到期回收）
        - FAILED 包的残留分片同样纳入清理
        """


class TransferChunkRepositoryABC(ABC):
    """已收分片仓储抽象（断点续传依据）。"""

    @abstractmethod
    def list_records(self, transfer_id: str) -> List[TransferChunkRecord]:
        """列出该传输会话全部已收分片。"""

    @abstractmethod
    def find(self, transfer_id: str, chunk_index: int) -> Optional[TransferChunkRecord]:
        """查询某个分片是否已收。"""

    @abstractmethod
    def add(self, record: TransferChunkRecord) -> None:
        """记录已收分片（(transfer_id, chunk_index) 唯一）。"""

    @abstractmethod
    def delete_all(self, transfer_id: str) -> None:
        """删除该会话全部分片记录（完成/过期回收时调用）。"""


class TransferStorageABC(ABC):
    """传输存储端口 — 分片暂存、合并落桶、清理，屏蔽底层存储差异。"""

    @abstractmethod
    def save_chunk(self, transfer_id: str, chunk_index: int, data: bytes) -> None:
        """写入一个分片到中转暂存。"""

    @abstractmethod
    def chunk_exists(self, transfer_id: str, chunk_index: int) -> bool:
        """分片文件是否已存在（断点续传校验）。"""

    @abstractmethod
    def delete_chunks(self, transfer_id: str, total_chunks: int) -> None:
        """删除该会话全部分片文件（幂等，容忍缺失）。"""

    @abstractmethod
    def merge_chunks(self, transfer_id: str, total_chunks: int) -> Tuple[str, str]:
        """按序合并分片到 transit 暂存区（不触碰终桶），返回 (staged_path, sha256_hex)。

        合并流式进行并同步计算整体 sha256（内容校验层）；
        终桶写入由调用方在 file_hash 校验通过后经 promote_file 完成。
        """

    @abstractmethod
    def promote_file(self, staged_path: str, dest_category: str, dest_key: str) -> str:
        """将 transit 暂存文件提升（移动）到目标桶，返回 final_path。

        仅在内容校验通过后调用，保证终桶不被未验证内容覆盖。
        """

    @abstractmethod
    def delete_transit_file(self, path: str) -> None:
        """删除中转暂存文件（仅允许删除 transit 域内路径，持久桶拒绝删除）。"""


class RemoteTransferClientABC(ABC):
    """远端 transfer_agent 出站端口（ACL 防腐层实现，发送侧编排依赖）。

    方法与接收侧 HTTP /internal/transfer/* 契约一一对应；
    实现负责把远端错误响应转译为 transfer_agent.domain.errors。
    """

    @abstractmethod
    def create_transfer(self, fields: Dict) -> Dict:
        """创建远端传输会话，返回远端响应 data。"""

    @abstractmethod
    def get_transfer_status(self, transfer_id: str) -> Dict:
        """查询远端已收分片清单（断点续传依据）。"""

    @abstractmethod
    def upload_chunk(self, transfer_id: str, chunk_index: int,
                     data: bytes, checksum: str) -> Dict:
        """上传一个分片。"""

    @abstractmethod
    def complete_transfer(self, transfer_id: str) -> Dict:
        """通知远端合并并校验。"""
