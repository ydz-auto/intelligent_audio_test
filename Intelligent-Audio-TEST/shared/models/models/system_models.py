"""
系统模型 (System Models)

包含系统日志、声压级映射、校准历史模型。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, utc8now,
)


# 10. 日志管理 (Log Management)

class Log(db.Model):
    """
    系统日志模型 (System Log Model)
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

# 11. 扩展功能 (Extensions)

class SPLMapping(db.Model):
    """
    声压级映射模型 (SPL Mapping Model)
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
    calibration_data = Column(JSON) # 详细校准测量点数据 (JSON)

    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False)
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False)
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

class CalibrationHistory(db.Model):
    __tablename__ = 'calibration_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    mapping_id = Column(Integer, nullable=False)
    distance = Column(Float) # 校准时的距离
    test_frequency = Column(Integer) # 校准时的频率
    calibration_data = Column(JSON)
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False)
