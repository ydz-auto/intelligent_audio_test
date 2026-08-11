# -*- coding: utf-8 -*-
"""播放设备聚合 - PlaybackDevice 聚合根。

PlaybackDevice 是用于播放测试音频的外设（如声卡通道、音箱）聚合根。
本模块为纯领域模型，不依赖 SQLAlchemy/db.Model，亦不包含任何 IO 调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PlaybackDeviceAggregate:
    """播放设备聚合根

    持有播放设备唯一标识及核心属性。config 为播放配置（JSON 兼容字典），
    deleted 表示逻辑删除标志（与 PO 中 is_deleted 对应，此处统一为布尔语义）。
    """
    id: Optional[int] = None
    name: str = ""
    device_type: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    deleted: bool = False
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    model: str = ""
    sample_rate: Optional[int] = None
    channel_index: int = 0
    device_unique_id: str = ""
    description: str = ""
    status: str = "online"
    current_spl_mapping_id: Optional[int] = None
    created_at: Any = None
    updated_at: Any = None

    # --- PO 字段名兼容属性 ---

    @property
    def is_deleted(self) -> int:
        """PO.is_deleted (0/1) 的兼容访问"""
        return 1 if self.deleted else 0

    def mark_deleted(self) -> None:
        """逻辑删除"""
        self.deleted = True

    def to_snapshot(self) -> "PlaybackDeviceSnapshot":
        """生成不可变快照"""
        return PlaybackDeviceSnapshot(
            id=self.id,
            name=self.name,
            device_type=self.device_type,
            config=dict(self.config),
            deleted=self.deleted,
        )

    def to_dict(self) -> dict:
        """序列化为 dict（供接口层响应使用）"""
        return {
            'id': self.id,
            'name': self.name,
            'model': self.model,
            'device_type': self.device_type,
            'sample_rate': self.sample_rate,
            'channel_index': self.channel_index,
            'device_unique_id': self.device_unique_id,
            'description': self.description,
            'status': self.status,
            'current_spl_mapping_id': self.current_spl_mapping_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class PlaybackDeviceSnapshot:
    """播放设备不可变快照值对象"""
    id: Optional[int]
    name: str
    device_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    deleted: bool = False
