# -*- coding: utf-8 -*-
"""task_service 系统日志 PO 定义

归属：task_service（系统审计上下文，task_service 持有 Log 写入）
表：logs

DDD 文档：Log CRUD 保留在网关，但 Log 表本身归属系统审计上下文。
当前 Log 的写入主要来自 task_service 执行引擎（_task_runner_mixin 等），
故 PO 归属 task_service。网关的 log CRUD 通过 gRPC 调 task_service。

P5 改造：从 shared/models/models/system_models.py 真正下沉到本服务。
shared 只保留 Log 的 re-export（SPLMapping/CalibrationHistory 归 e2e_test_service）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime,
    Index,
)


class Log(Base):
    """系统日志模型 (System Log Model)
    存储系统运行过程中的各类日志信息，用于审计和故障排查。
    """
    __tablename__ = 'logs'
    __table_args__ = (
        Index('idx_task_time', 'task_id', 'time'),
        Index('idx_time', 'time'),
        Index('idx_task_id', 'task_id'),
        Index('idx_level', 'level'),
        Index('idx_category', 'category'),
        Index('idx_module', 'module'),
        Index('idx_level_time', 'level', 'time'),
        Index('idx_category_time', 'category', 'time'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='日志唯一ID')
    time = Column(DateTime, nullable=False, comment='日志产生时间')
    level = Column(String(20), nullable=False, comment='日志级别 (DEBUG/INFO/WARN/ERROR)')
    category = Column(String(50), nullable=False, comment='日志分类 (System/Task/Device)')
    module = Column(String(100), nullable=False, comment='所属代码模块')
    source = Column(String(100), nullable=False, comment='日志来源标识')
    content = Column(Text, nullable=False, comment='日志正文内容')
    mark = Column(String(20), comment='特定标记')
    device_id = Column(Integer, comment='关联设备ID')
    task_id = Column(Integer, comment='关联任务ID')
    test_case_id = Column(String(50), comment='关联用例ID')
    api_id = Column(Integer, comment='关联API ID')
    thread_id = Column(String(50), comment='线程 ID')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='记录创建时间')
