# -*- coding: utf-8 -*-
"""task_service 测试结果 PO 定义

归属：task_service（测试执行上下文，TestResult 元数据所有权）
表：test_results

注意：TestResultDimension（test_result_dimensions 表）归属 evaluation_service，
不在本文件定义。跨服务访问通过 evaluation_service.EvaluationDataService gRPC。

P5 改造：从 shared/models/models/result_models.py 真正下沉到本服务。
shared 只保留 TestResult 的 re-export（TestResultDimension 从 evaluation_service re-export）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, JSON,
)


class TestResult(Base):
    """测试结果模型 (Test Result Model)
    记录单个测试用例在特定设备和 API 上的执行详细结果。
    支持多种算法类型 (translation, asr, tts, speaker_recognition 等)。
    所有算法结果统一使用 algorithm_result (JSON) 存储。
    """
    __tablename__ = 'test_results'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='结果唯一ID')
    task_id = Column(Integer, comment='关联测试任务ID')
    test_case_id = Column(String(50), comment='关联测试用例ID')
    device_id = Column(Integer, nullable=True, comment='关联被测设备ID')
    api_id = Column(Integer, comment='关联 API ID')
    algorithm_type = Column(String(50), comment='算法类型 (如: translation, asr, tts, speaker_recognition)')
    execution_status = Column(String(20), default='pending', nullable=False, comment='执行过程状态 (pending/running/completed/stopped/failed)')
    response_time = Column(Integer, comment='API 响应时间 (ms)')
    algorithm_result = Column(JSON, comment='算法执行结果 (JSON，不同算法类型结构不同)')
    execution_steps = Column(JSON, default=list, comment='执行步骤详细日志 (JSON)')
    result_data = Column(JSON, nullable=True, comment='轻量结果元数据 (JSON)，大字段存 result_data_path 文件')
    result_data_path = Column(String(500), nullable=True, comment='结果数据文件路径 (大字段存文件，DB仅存轻量元数据)')
    error_message = Column(Text, comment='错误信息描述')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='生成时间')
