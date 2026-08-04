"""
测试结果管理模型 (Test Result Management)

包含测试结果及测试结果维度得分模型。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, utc8now,
)


# 8. 测试结果管理 (Test Result Management)

class TestResult(db.Model):
    """
    测试结果模型 (Test Result Model)
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

class TestResultDimension(db.Model):
    """
    测试结果维度得分模型 (Test Result Dimension Score Model)
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
    evaluation_status = Column(String(20), default='pending', nullable=False, comment='评估过程状态 (pending/running/completed/stopped)')
    error_message = Column(Text, comment='评估过程中的错误信息')
    api_raw_response = Column(JSON, comment='评测API的原始响应数据')
    api_request_body = Column(JSON, comment='评测API的原始请求体数据')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='生成时间')
