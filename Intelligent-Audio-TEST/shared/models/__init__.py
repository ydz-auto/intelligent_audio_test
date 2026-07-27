"""
数据模型包 (Models Package)

该包定义了系统的核心业务模型及其数据库访问配置。
遵循 MVC 架构中的 Model 层规范，提供端到端的类型安全与一致的数据流定义。

导出内容:
- db: SQLAlchemy 数据库实例
- 各类业务实体模型 (User, TestCase, Device, Task, etc.)
"""

from shared.models.database import db
from shared.models.models import (
    User, Permission, UserPermission,
    Tag,
    TestCaseGroup, TestCase, TestCaseTag,
    Device, PlaybackDevice, DeviceTag,
    Audio, AudioAnnotation, AudioTag,
    API,
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI,
    TestResult, TestResultDimension, Report,
    Category, Dimension,
    Log,
    SPLMapping
)
from shared.models.algorithm_models import (
    AlgorithmGroup,
    AlgorithmDefinition,
    AlgorithmDeviceParam,
    AlgorithmApiParam,
    ParamMapping,
    AlgorithmDimensionRelation
)

__all__ = [
    'db',
    'User', 'Permission', 'UserPermission',
    'Tag',
    'TestCaseGroup', 'TestCase', 'TestCaseTag',
    'Device', 'PlaybackDevice', 'DeviceTag',
    'Audio', 'AudioAnnotation', 'AudioTag',
    'API',
    'Task', 'TaskTag', 'TaskCase', 'TaskDevice', 'TaskAPI',
    'TestResult', 'TestResultDimension', 'Report',
    'Category', 'Dimension',
    'Log',
    'SPLMapping',
    'AlgorithmGroup', 'AlgorithmDefinition', 'AlgorithmDeviceParam', 'AlgorithmApiParam', 'ParamMapping', 'AlgorithmDimensionRelation'
]
