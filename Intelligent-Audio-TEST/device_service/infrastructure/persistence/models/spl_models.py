# -*- coding: utf-8 -*-
"""device_service 声压级映射与校准 PO 定义

归属：device_service（e2e 测试上下文，物理校准所有权）
表：spl_mappings / calibration_history

P5 改造：从 shared/models/models/system_models.py 拆出（system_models 中
还有 Log 归属 task_service，已被 task_service 持有）。
shared 只保留 Log 的 re-export（从 task_service），SPLMapping/CalibrationHistory
改为从这里 re-export。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
)


class SPLMapping(Base):
    """声压级映射模型 (SPL Mapping Model)
    存储播放设备在特定距离下，目标声压级与数字增益之间的对应关系，用于音频校准。
    """
    __tablename__ = 'spl_mappings'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='映射唯一ID')
    name = Column(String(100), nullable=False, comment='映射配置名称')
    description = Column(Text, comment='映射配置详细描述')
    device_id = Column(Integer, comment='关联播放设备ID')
    device_type = Column(String(50), comment='适用的设备类型')
    distance = Column(Float, default=1.0, comment='测试时的物理距离 (米)')
    target_spl = Column(Float, comment='目标声压级 (dB SPL)')
    digital_gain = Column(Float, comment='对应的数字增益值 (dB)')

    calibration_status = Column(String(20), default='uncalibrated', comment='校准状态 (calibrated/uncalibrated)')
    test_frequency = Column(Integer, default=1000, comment='校准时使用的测试频率 (Hz)')
    calibration_data = Column(JSON)  # 详细校准测量点数据 (JSON)

    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False)
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False)
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')


class CalibrationHistory(Base):
    __tablename__ = 'calibration_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    mapping_id = Column(Integer, nullable=False)
    distance = Column(Float)  # 校准时的距离
    test_frequency = Column(Integer)  # 校准时的频率
    calibration_data = Column(JSON)
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False)
