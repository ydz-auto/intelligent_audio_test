# -*- coding: utf-8 -*-
"""被测设备聚合 - Device 聚合根 + DeviceTag 实体。

Device 是 e2e 测试上下文中的被测终端设备聚合根，统一管理设备本身的属性
以及其关联的标签（DeviceTagEntity）。本模块为纯领域模型，不依赖
SQLAlchemy/db.Model，亦不包含任何 IO 调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeviceTagEntity:
    """设备标签实体 - 被测设备与标签的多对多映射条目。

    归属于 Device 聚合内，本身拥有唯一标识但不独立成聚合。
    """
    id: Optional[int] = None
    device_id: Optional[int] = None
    name: str = ""


@dataclass
class DeviceAggregate:
    """被测设备聚合根 (Device Under Test)

    持有设备唯一标识及核心属性，并通过 tags 维护其边界内的标签集合。
    config 为设备配置（JSON 兼容字典），deleted 表示逻辑删除标志。
    """
    id: Optional[int] = None
    name: str = ""
    device_type: str = ""
    status: str = "offline"
    config: Dict[str, Any] = field(default_factory=dict)
    deleted: bool = False
    tags: List[DeviceTagEntity] = field(default_factory=list)
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    model: str = ""
    description: str = ""
    system: str = ""
    system_version: str = ""
    app_name: str = ""
    app_version: str = ""
    location: str = ""
    max_audio_duration: Optional[int] = None
    needs_prompt_audio: bool = False
    prompt_config: Any = None
    connection_type: str = ""
    keywords: Any = None
    serial_number: str = ""
    ip: Optional[str] = None
    last_online_at: Any = None
    supported_algorithms: List[str] = field(default_factory=list)
    created_at: Any = None
    updated_at: Any = None

    # --- PO 字段名兼容属性 ---

    @property
    def type(self) -> str:
        """PO.type 的兼容访问，映射到 entity.device_type"""
        return self.device_type

    def add_tag(self, tag: DeviceTagEntity) -> None:
        """向设备追加一个标签，并回填 device_id"""
        tag.device_id = self.id
        self.tags.append(tag)

    def remove_tag(self, tag_id: int) -> Optional[DeviceTagEntity]:
        """按标签 id 移除并返回被移除的标签；不存在则返回 None"""
        for idx, tag in enumerate(self.tags):
            if tag.id == tag_id:
                return self.tags.pop(idx)
        return None

    def mark_deleted(self) -> None:
        """逻辑删除"""
        self.deleted = True

    def to_snapshot(self) -> "DeviceSnapshot":
        """生成不可变快照，便于跨层传递"""
        return DeviceSnapshot(
            id=self.id,
            name=self.name,
            device_type=self.device_type,
            status=self.status,
            config=dict(self.config),
            deleted=self.deleted,
            tag_names=[t.name for t in self.tags],
        )


@dataclass(frozen=True)
class DeviceSnapshot:
    """被测设备不可变快照值对象

    用于跨聚合/跨层传递设备当前状态，避免外部修改聚合内部字段。
    tags 以名称列表形式快照，不暴露内部实体引用。
    """
    id: Optional[int]
    name: str
    device_type: str
    status: str
    config: Dict[str, Any] = field(default_factory=dict)
    deleted: bool = False
    tag_names: List[str] = field(default_factory=list)
