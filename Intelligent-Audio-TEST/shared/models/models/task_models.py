"""
测试任务管理模型 (Test Task Management)

包含测试任务、任务-标签/用例/设备/API 关联及任务合并关系模型。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, JSON,
    Index, relationship, utc8now,
)


# 7. 测试任务管理 (Test Task Management)

class Task(db.Model):
    """
    测试任务模型 (Test Task Model)
    代表一次完整的测试执行过程，关联了用例、设备、API、算法配置及最终结果。
    """
    __tablename__ = 'test_tasks'
    __table_args__ = (
        Index('idx_task_status', 'status'),
        Index('idx_task_algorithm_type', 'algorithm_type'),
        Index('idx_task_created_at', 'created_at'),
        Index('idx_task_status_deleted', 'status', 'deleted'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='任务唯一ID')
    name = Column(String(255), nullable=False, comment='任务名称')
    description = Column(Text, comment='任务描述')
    type = Column(String(50), nullable=False, comment='任务类型 (api/e2e)')
    status = Column(String(20), nullable=False, default='pending', comment='任务状态 (pending/queued/running/evaluating/reevaluate_queued/reevaluating/completed/failed/stopped/paused/skipped)')
    config = Column(JSON, comment='任务执行时的特定配置')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    algorithm_params = Column(JSON, comment='算法参数配置 (JSON格式)')
    total_cases = Column(Integer, nullable=False, default=0, comment='总测试用例数量')
    completed_cases = Column(Integer, nullable=False, default=0, comment='已执行完成的用例数量')
    failed_cases = Column(Integer, nullable=False, default=0, comment='执行失败的用例数量')
    created_by = Column(Integer, comment='创建者用户ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    started_at = Column(DateTime, comment='任务实际开始执行时间')
    completed_at = Column(DateTime, comment='任务执行结束时间')
    estimated_time = Column(Integer, comment='预计执行耗时 (秒)')
    actual_duration = Column(Integer, comment='实际执行耗时 (秒)')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

    tags = relationship('Tag', secondary='task_tags',
        primaryjoin='Task.id == TaskTag.task_id',
        secondaryjoin='Tag.id == TaskTag.tag_id',
        backref='tasks')
    cases = relationship('TestCase', secondary='task_case_relations',
        primaryjoin='Task.id == TaskCase.task_id',
        secondaryjoin='TestCase.id == TaskCase.test_case_id',
        backref='tasks')
    devices = relationship('Device', secondary='task_device_relations',
        primaryjoin='Task.id == TaskDevice.task_id',
        secondaryjoin='Device.id == TaskDevice.device_id',
        backref='tasks')
    apis = relationship('API', secondary='task_api_relations',
        primaryjoin='Task.id == TaskAPI.task_id',
        secondaryjoin='API.id == TaskAPI.api_id',
        backref='tasks')

class TaskTag(db.Model):
    """
    任务标签关联模型 (Task-Tag Relation)
    维护测试任务与标签之间的多对多映射关系。
    """
    __tablename__ = 'task_tags'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(BigInteger, comment='关联测试任务ID')
    tag_id = Column(BigInteger, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

class TaskCase(db.Model):
    """
    任务-用例执行状态模型 (Task-Case Relation)
    记录特定任务中每个用例的执行状态和耗时。
    """
    __tablename__ = 'task_case_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(BigInteger, comment='关联测试任务ID')
    test_case_id = Column(String(50), comment='关联测试用例ID')
    status = Column(String(50), default='pending', nullable=True, comment='该用例在任务中的最终结果 (pending/completed/failed/skipped)')
    execution_status = Column(String(20), default='pending', nullable=False, comment='执行过程状态 (pending/running/completed/stopped/failed)')
    evaluation_status = Column(String(20), default='pending', nullable=False, comment='评估过程状态 (queued/pending/running/calculating/completed/stopped/failed)')
    started_at = Column(DateTime, comment='开始执行时间')
    completed_at = Column(DateTime, comment='执行结束时间')
    duration = Column(Integer, comment='执行耗时 (秒)')
    error_message = Column(Text, comment='执行过程中的错误信息')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

class TaskDevice(db.Model):
    """
    任务设备关联模型 (Task-Device Relation)
    定义任务执行时所使用的被测设备。
    """
    __tablename__ = 'task_device_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(Integer, comment='关联测试任务ID')
    device_id = Column(Integer, comment='关联被测设备ID')

class TaskAPI(db.Model):
    """
    任务 API 关联模型 (Task-API Relation)
    定义任务执行时所调用的 API 服务。
    """
    __tablename__ = 'task_api_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(Integer, comment='关联测试任务ID')
    api_id = Column(Integer, comment='关联 API ID')

class TaskMergeRelation(db.Model):
    """
    任务合并关联模型 (Task Merge Relation)
    记录合并任务与源任务之间的多对多映射关系。
    """
    __tablename__ = 'task_merge_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    merged_task_id = Column(Integer, nullable=False, comment='合并后的任务ID')
    source_task_id = Column(Integer, nullable=False, comment='源任务ID')
    source_result_count = Column(Integer, default=0, comment='该源任务贡献的结果数量')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

    merged_task = relationship('Task', foreign_keys=[merged_task_id], backref='source_relations')
    source_task = relationship('Task', foreign_keys=[source_task_id], backref='target_relations')
