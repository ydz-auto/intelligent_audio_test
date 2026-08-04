"""
数据模型定义模块 (Data Models Definition)

本包定义了系统的所有核心实体模型，基于 SQLAlchemy ORM 构建。
涵盖了用户管理、测试用例、设备、音频、API 配置、测试任务及结果等核心业务领域。

架构层次: Flask Model Layer (MVC - Model)
统一规范:
- 时间戳统一使用东八区时间 (datetime.now(timezone(timedelta(hours=8))))
- 逻辑删除使用 deleted 或 is_deleted 标志
- 所有模型继承自 db.Model

本包为 models.py 的拆分版本，所有公有名称均在此重新导出，
保持向后兼容：`from shared.models.models import Task, TestCase, API` 等仍可用。

子模块组织：
- _base.py             : db 导入、SQLAlchemy 列类型、relationship、utc8now
- user_models.py       : ReportStatus/TaskStatus/ReportType 枚举 + Role/Permission/UserPermission/User/OAuthClient/OAuthRefreshToken
- testcase_models.py   : TagCategory/Tag/TestCaseGroup/TestCase/TestCaseTag
- device_models.py     : Device/PlaybackDevice/DeviceTag
- audio_models.py      : Audio/AudioAnnotation/AudioTag/AudioAlgorithmRelation
- api_models.py        : API
- task_models.py       : Task/TaskTag/TaskCase/TaskDevice/TaskAPI/TaskMergeRelation
- result_models.py     : TestResult/TestResultDimension
- report_models.py     : Report/ReportSummary/ReportSummaryMeta/ReportRawData/ReportCase/ReportMetricStats/ReportComparisonMatrix
- evaluation_models.py: Category/Dimension
- system_models.py     : Log/SPLMapping/CalibrationHistory
- upload_models.py     : UploadTask/UploadFile/UploadChunk
- cache_models.py      : StatsCache
"""
# 1. 用户与权限管理 (User & Permission Management) + 枚举
from .user_models import (
    ReportStatus, TaskStatus, ReportType,
    Role, Permission, RolePermission, UserPermission, User,
    OAuthClient, OAuthRefreshToken,
)

# 2/3. 标签与测试用例管理 (Tag & Test Case Management)
from .testcase_models import (
    TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
)

# 4. 设备管理 (Device Management)
from .device_models import (
    Device, PlaybackDevice, DeviceTag,
)

# 5. 音频文件管理 (Audio Management)
from .audio_models import (
    Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
)

# 6. API 配置管理 (API Configuration)
from .api_models import (
    API,
)

# 7. 测试任务管理 (Test Task Management)
from .task_models import (
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
)

# 8. 测试结果管理 (Test Result Management)
from .result_models import (
    TestResult, TestResultDimension,
)

# 9. 报告管理 (Report Management)
from .report_models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData,
    ReportCase, ReportMetricStats, ReportComparisonMatrix,
)

# 10. 评估维度管理 (Evaluation Dimension Management)
from .evaluation_models import (
    Category, Dimension,
)

# 11/12. 系统日志与扩展功能 (System & Extensions)
from .system_models import (
    Log, SPLMapping, CalibrationHistory,
)

# 13. 文件上传任务管理 (File Upload Management)
from .upload_models import (
    UploadTask, UploadFile, UploadChunk,
)

# 14. 统计缓存管理 (Stats Cache Management)
from .cache_models import (
    StatsCache,
)

# 东八区时间辅助函数
from ._base import utc8now


# 确保 AlgorithmDefinition 等算法模型注册到同一个 Base.metadata，
# 使 AudioAlgorithmRelation.algorithm relationship('AlgorithmDefinition') 可解析
from shared.models.algorithm_models import AlgorithmDefinition  # noqa: E402,F401


__all__ = [
    # 枚举
    'ReportStatus', 'TaskStatus', 'ReportType',
    # 用户与权限
    'Role', 'Permission', 'RolePermission', 'UserPermission', 'User',
    'OAuthClient', 'OAuthRefreshToken',
    # 标签与测试用例
    'TagCategory', 'Tag', 'TestCaseGroup', 'TestCase', 'TestCaseTag',
    # 设备
    'Device', 'PlaybackDevice', 'DeviceTag',
    # 音频
    'Audio', 'AudioAnnotation', 'AudioTag', 'AudioAlgorithmRelation',
    # API
    'API',
    # 任务
    'Task', 'TaskTag', 'TaskCase', 'TaskDevice', 'TaskAPI', 'TaskMergeRelation',
    # 测试结果
    'TestResult', 'TestResultDimension',
    # 报告
    'Report', 'ReportSummary', 'ReportSummaryMeta', 'ReportRawData',
    'ReportCase', 'ReportMetricStats', 'ReportComparisonMatrix',
    # 评估
    'Category', 'Dimension',
    # 系统
    'Log', 'SPLMapping', 'CalibrationHistory',
    # 上传
    'UploadTask', 'UploadFile', 'UploadChunk',
    # 缓存
    'StatsCache',
    # 辅助函数
    'utc8now',
]
