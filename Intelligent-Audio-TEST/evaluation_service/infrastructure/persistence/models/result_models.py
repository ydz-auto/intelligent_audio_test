# -*- coding: utf-8 -*-
"""evaluation_service 测试结果维度得分 PO 定义

归属：evaluation_service（评估上下文）
表：test_result_dimensions

注意：TestResult（test_results 表）归属 task_service，不在本服务定义。
跨服务访问 TestResult 通过 gRPC 调 task_service.TaskDataService。

P5 改造：从 shared/models/models/result_models.py 真正下沉到本服务。
shared/models/models/result_models.py 中的 TestResultDimension 改为从这里 re-export。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index,
)
from shared.utils.status_constants import EvaluationStatus


class TestResultDimension(Base):
    """测试结果维度得分模型 (Test Result Dimension Score Model)
    存储单个测试结果在各个评估维度上的具体得分和状态。
    支持多种算法类型 (translation, asr, tts, speaker_recognition 等)。
    """
    __tablename__ = 'test_result_dimensions'
    __table_args__ = (
        Index('idx_trd_round', 'test_result_id', 'round_number'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    test_result_id = Column(BigInteger, comment='关联测试结果ID')
    dimension_id = Column(BigInteger, comment='关联评估维度ID')
    algorithm_type = Column(String(50), comment='算法类型 (如: translation, asr, tts, speaker_recognition)')
    round_number = Column(Integer, nullable=True, default=None, comment='轮次编号 (NULL=整体评估, 0-indexed)')
    dimension_value = Column(Float, comment='维度计算出的原始值 (如 BLEU 分数)')
    score = Column(Float, comment='维度最终得分')
    status = Column(String(20), nullable=True, comment='维度评估结果状态 (passed/failed)')
    evaluation_status = Column(String(20), default=EvaluationStatus.PENDING, nullable=False, comment='评估过程状态 (pending/running/completed/stopped)')
    error_message = Column(Text, comment='评估过程中的错误信息')
    api_raw_response = Column(JSON, comment='评测API的原始响应数据')
    api_request_body = Column(JSON, comment='评测API的原始请求体数据')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='生成时间')
