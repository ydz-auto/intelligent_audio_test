# -*- coding: utf-8 -*-
"""逻辑音箱组聚合（跨实验室对应的音箱位置，N 实验室互相对应）。

纯领域模型，不依赖 SQLAlchemy。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class PlaybackSpeakerGroupItemEntity:
    """逻辑音箱在某实验室对应的实体播放设备"""
    id: Optional[int] = None
    group_id: int = 0
    lab_id: int = 0
    playback_device_id: int = 0
    created_at: Any = None
    updated_at: Any = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'lab_id': self.lab_id,
            'playback_device_id': self.playback_device_id,
        }


@dataclass
class PlaybackSpeakerGroupAggregate:
    """逻辑音箱组（组内每个实验室各对应一台实体播放设备）"""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    items: List[PlaybackSpeakerGroupItemEntity] = field(default_factory=list)
    created_at: Any = None
    updated_at: Any = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'items': [item.to_dict() for item in self.items],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
