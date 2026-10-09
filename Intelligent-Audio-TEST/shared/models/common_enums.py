# -*- coding: utf-8 -*-
"""跨服务共享枚举

这些枚举不是 PO（无 __tablename__），不归属任何单一服务，
作为跨服务共享的领域语义保持在本文件。

- ReportStatus  报告状态（归属 report_service 域，但被多处引用）
- TaskStatus    任务状态（归属 task_service 域，但被多处引用）
- ReportType    报告类型（归属 report_service 域，但被多处引用）

P5 改造：从 shared/models/models/user_models.py 中拆出（原 user_models
混入这三个枚举是历史遗留），user_models 的 PO 已下沉到 auth_service。
"""
from enum import Enum


class ReportStatus(str, Enum):
    """报告状态枚举"""
    DRAFT = 'draft'
    PUBLISHED = 'published'


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    MERGED = 'merged'


class ReportType(str, Enum):
    """报告类型枚举"""
    TASK = 'task'
    COMPARISON = 'comparison'
    SECONDARY_COMPARISON = 'secondary_comparison'


class TestType(str, Enum):
    """测试类型枚举（api 接口测试 / e2e 端到端测试）"""
    API = 'api'
    E2E = 'e2e'


class FieldType(str, Enum):
    """字段类型枚举（用于参数/结果字段的类型标识）"""
    RTTM = 'rttm'
    STM = 'stm'
    TEXT = 'text'
    AUDIO_FILE = 'audio_file'
    AUDIO = 'audio'
    NUMBER = 'number'
    BOOLEAN = 'boolean'
    JSON = 'json'
    TIMESTAMP = 'timestamp'


class ViewMode(str, Enum):
    """视图模式枚举（全部 / 按分组 / 按标签）"""
    ALL = 'all'
    GROUP = 'group'
    TAG = 'tag'


class DeviceType(str, Enum):
    """被测设备类型枚举 — 用例级决定执行路由（执行域 P0 新增）

    语义取代源单体的 task.type / test_type 分支：
    - PHYSICAL       物理设备       → e2e_test_service E2EExecutor
    - HTTP_API       HTTP API       → api_test_service APISessionExecutor
    - WEBSOCKET_API  WebSocket API  → api_test_service RealtimeSessionExecutor
    """
    PHYSICAL = 'physical'
    HTTP_API = 'http_api'
    WEBSOCKET_API = 'websocket_api'


class APIProtocol(str, Enum):
    """API 传输协议枚举 — Adapter 分型依据（执行域 P0 新增）"""
    HTTP = 'http'
    WEBSOCKET = 'websocket'


class OutputType(str, Enum):
    """API 输出类型枚举 — adapter 多模态输出采集（执行域 P0 新增）"""
    AUDIO = 'audio'
    TEXT = 'text'
    VIDEO = 'video'
    IMAGE = 'image'


class CalibrationStatus(str, Enum):
    """SPL 校准状态枚举（执行域 P0 新增）"""
    CALIBRATED = 'calibrated'
    UNCALIBRATED = 'uncalibrated'


class RedisKeyPrefix(str, Enum):
    """Redis Key 前缀枚举 — 禁止裸字符串拼接 Redis key

    各模块使用统一前缀，避免魔法字符串和 key 冲突。
    """
    # 端点任务队列前缀: eval:queue:{endpoint_url}
    EVAL_QUEUE = 'eval:queue'
    # 端点并发信号量前缀: eval:sem:{endpoint_url}
    EVAL_SEMAPHORE = 'eval:sem'
    # 评估结果回调频道前缀: eval:result:{eval_task_id}
    EVAL_RESULT = 'eval:result'
    # physical 设备互斥锁前缀: lock:task:physical:{device_id}
    TASK_PHYSICAL_LOCK = 'lock:task:physical'
    # 同 endpoint 并发信号量前缀: sem:api:endpoint:{host}
    API_ENDPOINT_SEMAPHORE = 'sem:api:endpoint'
    # Realtime 会话实例绑定前缀: session:bind:{task_id}
    SESSION_BIND = 'session:bind'


class EvalTaskStatus(str, Enum):
    """eval_server 任务状态枚举 — 替代裸字符串状态判断"""
    COMPLETED = 'completed'
    FAILED = 'failed'


class PublishedTaskStatus(str, Enum):
    """已发布任务状态枚举 — 发布/归档状态机（任务发布功能）"""
    PUBLISHED = 'published'
    ARCHIVED = 'archived'


class AuditEvent(str, Enum):
    """审计事件名枚举 — 落库到 logs（category=System），供审计查询过滤

    命名对齐设计文档《任务发布功能设计文档》§9 /《报告Benchmark排行功能设计文档》。
    """
    PUBLISHED_TASK_BENCHMARK_MARKED = 'PUBLISHED_TASK_BENCHMARK_MARKED'
    BENCHMARK_RANKING_COMPUTED = 'BENCHMARK_RANKING_COMPUTED'
    BENCHMARK_BASELINE_IMPORTED = 'BENCHMARK_BASELINE_IMPORTED'
    BENCHMARK_MAPPING_UPDATED = 'BENCHMARK_MAPPING_UPDATED'
    # 用户/角色/权限管理审计（INT-30，category='auth'）
    AUTH_USER_CREATED = 'AUTH_USER_CREATED'
    AUTH_USER_UPDATED = 'AUTH_USER_UPDATED'
    AUTH_USER_STATUS_CHANGED = 'AUTH_USER_STATUS_CHANGED'
    AUTH_USER_ROLE_ASSIGNED = 'AUTH_USER_ROLE_ASSIGNED'
    AUTH_USER_PERMISSION_GRANTED = 'AUTH_USER_PERMISSION_GRANTED'
    AUTH_USER_PERMISSION_REVOKED = 'AUTH_USER_PERMISSION_REVOKED'
    AUTH_ROLE_CREATED = 'AUTH_ROLE_CREATED'
    AUTH_ROLE_UPDATED = 'AUTH_ROLE_UPDATED'
    AUTH_ROLE_PERMISSIONS_SET = 'AUTH_ROLE_PERMISSIONS_SET'
    AUTH_ROLE_DELETED = 'AUTH_ROLE_DELETED'


class AuthErrorCode(str, Enum):
    """认证/权限管理错误码枚举（INT-30）

    auth_service gRPC 失败响应 data 返回 {"error_code": "<成员值>"}，
    api_gateway 按此映射 HTTP 状态码（400/403/404/409，未知一律 400）。
    """
    USER_NOT_FOUND = 'USER_NOT_FOUND'
    ROLE_NOT_FOUND = 'ROLE_NOT_FOUND'
    PERMISSION_NOT_FOUND = 'PERMISSION_NOT_FOUND'
    USERNAME_DUPLICATED = 'USERNAME_DUPLICATED'
    ROLE_NAME_DUPLICATED = 'ROLE_NAME_DUPLICATED'
    ROLE_IS_SYSTEM = 'ROLE_IS_SYSTEM'
    ROLE_IN_USE = 'ROLE_IN_USE'
    WILDCARD_FORBIDDEN = 'WILDCARD_FORBIDDEN'
    SELF_OPERATION_FORBIDDEN = 'SELF_OPERATION_FORBIDDEN'
    PERMISSION_NOT_GRANTED = 'PERMISSION_NOT_GRANTED'


class AuditLogCategory(str, Enum):
    """审计类日志 category 枚举 — log_handler emit 分流按此判定入 DB 队列

    审计事件（auth/benchmark）无 task_id/test_case_id，emit 分流不得按
    任务/用例条件降级为只写本地文件：凡 category 属于本枚举的日志必须
    落 logs 表（INT-30 P1 回归修复）。
    """
    AUTH = 'auth'
    BENCHMARK = 'benchmark'


AUDIT_LOG_CATEGORIES = frozenset(item.value for item in AuditLogCategory)


class PkgType(str, Enum):
    """跨区传输包类型枚举 — transfer_agent 传输包协议（设计文档 09_跨区网络传输方案 §4.2.1）

    EVAL_REQUEST  A/B→B→C  评估输入包（算法结果 JSON + 所需文件，C 侧临时处理不落持久盘）
    EVAL_RESULT   C→B      评估结果包（随第三方 API 同步响应返回）
    REPORT_SYNC   A↔B      报告同步
    DATA_SYNC     A↔B      A/B 之间任务数据同步
    C_REPORT      C→B→A    C 自产报告推送（备选方案）
    C_RESULT      C→B→A    C 自产评估结果推送（备选方案）
    """
    EVAL_REQUEST = 'EVAL_REQUEST'
    EVAL_RESULT = 'EVAL_RESULT'
    REPORT_SYNC = 'REPORT_SYNC'
    DATA_SYNC = 'DATA_SYNC'
    C_REPORT = 'C_REPORT'
    C_RESULT = 'C_RESULT'


class TransferStatus(str, Enum):
    """跨区传输包状态枚举 — transfer_agent 传输流水状态机

    CREATED      会话已创建（收到 CreateTransfer）
    TRANSFERRING 分片传输中（已收到至少一个分片）
    COMPLETED    传输完成（分片合并 + file_hash 校验通过）
    FAILED       传输失败（合并校验失败等终态，需新建 transfer_id 重传）
    EXPIRED      超过 TTL 被清理（分片/临时文件回收，流水保留供审计）
    """
    CREATED = 'CREATED'
    TRANSFERRING = 'TRANSFERRING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    EXPIRED = 'EXPIRED'


class EvalCapabilityTarget(str, Enum):
    """评估能力归属枚举 — 评估能力注册表路由目标（设计文档 09_跨区网络传输方案 §4.1.1）

    LOCAL          本区 evaluation_service gRPC（现有 EvaluateCase 链路不变）
    THIRD_PARTY_C  经 transfer_agent 传输链路调 C 第三方评估 API（B 为评估中枢）
    """
    LOCAL = 'LOCAL'
    THIRD_PARTY_C = 'THIRD_PARTY_C'


class ThirdPartyAdapterKind(str, Enum):
    """B→C 第三方评估适配形态枚举 — ThirdPartyEvalPort 适配器策略（设计文档 §4.3）

    MULTIPART       支持 multipart/form-data + 同步响应，流式上传文件
    FEATURE_EXTRACT B 预处理大文件→提取特征向量→只传特征（C 仅接受小参数字段）
    PRESIGNED_URL   B 生成预签名 URL→C 主动拉取→携带对象引用评估
    """
    MULTIPART = 'multipart'
    FEATURE_EXTRACT = 'feature_extract'
    PRESIGNED_URL = 'presigned_url'
