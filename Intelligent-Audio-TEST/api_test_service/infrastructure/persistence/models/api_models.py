# -*- coding: utf-8 -*-
"""api_test_service API 配置 PO 定义

归属：api_test_service（API 测试上下文，被测 API 配置所有权）
表：apis

P5 改造：从 shared/models/models/api_models.py 真正下沉到本服务。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
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
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    default_max_process = Column(Integer, nullable=False, default=5, comment='默认最大并发处理数')
    default_max_timeout = Column(Integer, nullable=False, default=30, comment='默认最大超时时间 (秒)')
    default_max_audio_duration = Column(Integer, nullable=False, default=60, comment='默认支持的最大音频时长 (秒)')
    api_endpoints = Column(JSON, nullable=False, default=list, comment='API接入点配置列表 (JSON格式)')
