# -*- coding: utf-8 -*-
"""api_test_service API 配置 PO 定义

归属：api_test_service（API 测试上下文，被测 API 配置所有权）
表：apis

P5 改造：从 shared/models/models/api_models.py 真正下沉到本服务。
"""
from shared.models.common_enums import CalibrationStatus
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
)


class API(Base):
    """API 配置模型 (API Configuration Model)
    存储被测翻译 API 或语音识别 API 的连接配置及性能约束。
    """
    __tablename__ = 'apis'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='API唯一ID')
    name = Column(String(255), nullable=False, comment='API显示名称')
    vendor = Column(String(50), nullable=True, comment='供应商名称 (如 volc_ast, ali, tencent)')
    api_url = Column(String(512), comment='API微服务主入口URL')
    description = Column(Text, comment='详细描述')
    status = Column(String(20), nullable=False, default='online', comment='服务状态 (online/offline)')
    meta = Column(JSON, nullable=False, comment='API元数据 (鉴权信息、额外参数等)')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    max_process = Column(Integer, nullable=False, default=5, comment='最大并发处理数')
    max_timeout = Column(Integer, nullable=False, default=30, comment='最大超时时间 (秒)')
    max_audio_duration = Column(Integer, nullable=False, default=60, comment='支持的最大音频时长 (秒)')
    health_score = Column(Float, nullable=False, default=100.0, comment='健康度评分 (0-100)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    default_max_process = Column(Integer, nullable=False, default=5, comment='默认最大并发处理数')
    default_max_timeout = Column(Integer, nullable=False, default=30, comment='默认最大超时时间 (秒)')
    default_max_audio_duration = Column(Integer, nullable=False, default=60, comment='默认支持的最大音频时长 (秒)')
    api_endpoints = Column(JSON, nullable=False, default=list, comment='API接入点配置列表 (JSON格式)')
    output_types = Column(JSON, nullable=False, default=list, comment='API输出类型列表 (OutputType 枚举值, INT-74)')
    rms_spl_mapping_id = Column(Integer, nullable=True, comment='当前默认 RMS→SPL 映射 ID (api_rms_spl_mappings，INT-61)')


class ApiRmsSplMappingPO(Base):
    """被测 API RMS→SPL 映射 PO (INT-61)

    与 E2E SPLMapping（物理设备）对称：挂在被测 API 上（1:N），
    语义为被测 API 数字域 dB → gain（校准 API 输入灵敏度）。
    """
    __tablename__ = 'api_rms_spl_mappings'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='映射唯一ID')
    name = Column(String(255), comment='配置名称')
    description = Column(Text, comment='配置描述')
    api_id = Column(Integer, nullable=False, index=True, comment='关联被测API (1:N)')
    vendor = Column(String(50), comment='API 供应商')
    protocol = Column(String(20), default='websocket', comment='API 协议')
    reference_spl = Column(Float, nullable=False, default=65.0, comment='参考声压级 (dB SPL)')
    reference_gain_linear = Column(Float, nullable=False, default=1.0, comment='参考线性增益')
    calibration_status = Column(String(20), nullable=False, default=CalibrationStatus.UNCALIBRATED.value, comment='校准状态 (CalibrationStatus 枚举: calibrated/uncalibrated)')
    calibration_data = Column(JSON, default=dict, comment='校准测量点 {"points": [{target_spl, gain_linear, rms_dbfs}]}')
    min_gain_linear = Column(Float, nullable=False, default=0.001, comment='增益下限')
    max_gain_linear = Column(Float, nullable=False, default=10.0, comment='增益上限')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间')
