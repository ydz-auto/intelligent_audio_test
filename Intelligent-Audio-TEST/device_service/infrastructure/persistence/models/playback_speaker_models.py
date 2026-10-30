# -*- coding: utf-8 -*-
"""播放设备「逻辑音箱组」PO（跨实验室互相对应）。

背景：用例里配置的播放设备只属于编写用例的那个实验室；N 个实验室里位置相同的
音箱应当互相对应。用「逻辑音箱组」表达这种 N 对 N 的对应关系：

- playback_speaker_groups       逻辑音箱（如「设备正面 0.5m 0°」）
- playback_speaker_group_items  组内每个实验室各自对应的实体播放设备

执行时解析：源音箱 → 所属逻辑组 → 目标实验室在该组的设备。
一只实体音箱最多归属一个逻辑组；同一实验室内一个逻辑组只能对应一台设备。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime,
    Index, UniqueConstraint,
)


class PlaybackSpeakerGroup(Base):
    """逻辑音箱（跨实验室对应的音箱位置）"""
    __tablename__ = 'playback_speaker_groups'
    __table_args__ = (
        # 同名逻辑音箱互斥（并发建重名兜底）
        UniqueConstraint('name', name='uq_playback_speaker_group_name'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    name = Column(String(100), nullable=False, comment='逻辑音箱名称（如 设备正面 0.5m 0°）')
    description = Column(Text, comment='描述')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        onupdate=utc8now, nullable=False, comment='更新时间')


class PlaybackSpeakerGroupItem(Base):
    """逻辑音箱在某实验室对应的实体播放设备"""
    __tablename__ = 'playback_speaker_group_items'
    __table_args__ = (
        UniqueConstraint('group_id', 'lab_id', name='uq_playback_speaker_item_group_lab'),
        # 一只实体音箱只能归属一个逻辑组（防止一台设备被映射到多个位置）
        UniqueConstraint('playback_device_id', name='uq_playback_speaker_item_device'),
        Index('ix_playback_speaker_item_lab', 'lab_id'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    group_id = Column(Integer, nullable=False, comment='逻辑音箱组ID')
    lab_id = Column(Integer, nullable=False, comment='实验室ID')
    playback_device_id = Column(Integer, nullable=False, comment='该实验室对应的播放设备ID')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        onupdate=utc8now, nullable=False, comment='更新时间')
