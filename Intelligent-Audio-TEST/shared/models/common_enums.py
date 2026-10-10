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


class VendorAdapterType(str, Enum):
    """厂商适配器类型枚举 — api_test_service infrastructure/adapters 注册表 key（INT-62 新增）

    新增厂商适配器 = 新增枚举成员 + @register_vendor_adapter 注册实现
    + 用例配置 vendor_adapter 选择，执行链（core/）零改动。
    """
    API_DRIVER = 'api_driver'  # 内置 HTTP/WS 协议适配器（原 clients/api_driver + api_client 迁移）
    MOCK = 'mock'              # mock 厂商适配器（扩展性验证 / 测试替身）


class RealtimeChannel(str, Enum):
    """Realtime 流式双通道枚举 — frame 逐帧 / summary 会话汇总（INT-61 新增）

    双通道经 REPORT_EVENTS 领域事件 + sse_events SSE 桥推前端，
    通道名即 SSE event 名，前端按通道订阅渲染。
    """
    FRAME = 'realtime_frame'
    SUMMARY = 'realtime_summary'


class RealtimeFrameType(str, Enum):
    """Realtime 归一化帧事件类型（INT-61 新增）

    厂商原始事件经 ACL 归一化（默认 OpenAI Realtime 事件协议），
    executor 与前端只消费本枚举类型，不接触厂商字段。
    """
    SESSION_CREATED = 'session_created'
    SESSION_UPDATED = 'session_updated'
    AI_AUDIO_DELTA = 'ai_audio_delta'
    AI_AUDIO_DONE = 'ai_audio_done'
    AI_TEXT_DELTA = 'ai_text_delta'
    AI_TEXT_DONE = 'ai_text_done'
    USER_SPEECH_STARTED = 'user_speech_started'
    USER_SPEECH_STOPPED = 'user_speech_stopped'
    RESPONSE_CANCELLED = 'response_cancelled'
    ERROR = 'error'
    CONNECTION_CLOSED = 'connection_closed'
    INPUT_COMMITTED = 'input_committed'


class RealtimeRoundMode(str, Enum):
    """Realtime 轮次模式枚举 — 正常轮 / 打断轮（barge-in）（INT-61 新增）"""
    NORMAL = 'normal'
    INTERRUPTION = 'interruption'


class OutputType(str, Enum):
    """API 输出类型枚举 — adapter 多模态输出采集（执行域 P0 新增）"""
    AUDIO = 'audio'
    TEXT = 'text'
    VIDEO = 'video'
    IMAGE = 'image'


class AudioBitDepth(str, Enum):
    """音频位深枚举 — api.audio_config 目标格式声明（08_混音与SPL映射.md §2.2）"""
    S16 = 's16'
    S24 = 's24'
    S32 = 's32'


class AudioContainer(str, Enum):
    """音频容器枚举 — api.audio_config 目标格式声明（08_混音与SPL映射.md §2.2）"""
    PCM = 'pcm'
    WAV = 'wav'


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
    # API 数字 SPL 校准互斥锁前缀: lock:spl:calibration:{api_id}（UC-0902）
    SPL_CALIBRATION_LOCK = 'lock:spl:calibration'
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
    # 登录体系改造（INT-51，category='auth'）
    AUTH_USER_REGISTERED = 'AUTH_USER_REGISTERED'
    AUTH_OAUTH_PROVIDER_CREATED = 'AUTH_OAUTH_PROVIDER_CREATED'
    AUTH_OAUTH_PROVIDER_UPDATED = 'AUTH_OAUTH_PROVIDER_UPDATED'
    AUTH_OAUTH_PROVIDER_DELETED = 'AUTH_OAUTH_PROVIDER_DELETED'
    # 设备管理审计（INT-80，category='device'）
    DEVICE_GROUP_CREATED = 'DEVICE_GROUP_CREATED'
    DEVICE_GROUP_UPDATED = 'DEVICE_GROUP_UPDATED'
    DEVICE_GROUP_DELETED = 'DEVICE_GROUP_DELETED'
    DEVICE_GROUP_MEMBERSHIP_CHANGED = 'DEVICE_GROUP_MEMBERSHIP_CHANGED'
    DEVICE_CONTROL_EXECUTED = 'DEVICE_CONTROL_EXECUTED'
    DEVICE_BATCH_ACTION_EXECUTED = 'DEVICE_BATCH_ACTION_EXECUTED'
    DEVICE_ALARM_RULE_CREATED = 'DEVICE_ALARM_RULE_CREATED'
    DEVICE_ALARM_RULE_UPDATED = 'DEVICE_ALARM_RULE_UPDATED'
    DEVICE_ALARM_RULE_DELETED = 'DEVICE_ALARM_RULE_DELETED'
    DEVICE_ALARM_TRIGGERED = 'DEVICE_ALARM_TRIGGERED'
    DEVICE_ALARM_ACKNOWLEDGED = 'DEVICE_ALARM_ACKNOWLEDGED'
    # 任务发布审计（INT-65，category='System'）
    PUBLISHED_TASK_CREATED = 'PUBLISHED_TASK_CREATED'
    PUBLISHED_TASK_VERSION_CREATED = 'PUBLISHED_TASK_VERSION_CREATED'
    PUBLISHED_TASK_EXECUTED = 'PUBLISHED_TASK_EXECUTED'
    PUBLISHED_TASK_ARCHIVED = 'PUBLISHED_TASK_ARCHIVED'


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
    # 自定义 OAuth 提供方（INT-51）
    OAUTH_PROVIDER_NOT_FOUND = 'OAUTH_PROVIDER_NOT_FOUND'
    OAUTH_SLUG_DUPLICATED = 'OAUTH_SLUG_DUPLICATED'
    OAUTH_PROVIDER_DISABLED = 'OAUTH_PROVIDER_DISABLED'


class AuditLogCategory(str, Enum):
    """审计类日志 category 枚举 — log_handler emit 分流按此判定入 DB 队列

    审计事件（auth/benchmark）无 task_id/test_case_id，emit 分流不得按
    任务/用例条件降级为只写本地文件：凡 category 属于本枚举的日志必须
    落 logs 表（INT-30 P1 回归修复）。
    """
    AUTH = 'auth'
    BENCHMARK = 'benchmark'
    # 设备管理审计（INT-80：分组/操作/批量端点）
    DEVICE = 'device'


AUDIT_LOG_CATEGORIES = frozenset(item.value for item in AuditLogCategory)


class DeviceOperation(str, Enum):
    """设备操作枚举（INT-80 设备操作端点/批量操作）

    connect     连接设备（远程设备 adb connect / USB 设备唤醒校验）
    disconnect  断开设备连接
    reboot      重启设备
    shutdown    关闭设备
    install_app 安装应用（params: file_path）
    uninstall_app 卸载应用（params: package_name）
    """
    CONNECT = 'connect'
    DISCONNECT = 'disconnect'
    REBOOT = 'reboot'
    SHUTDOWN = 'shutdown'
    INSTALL_APP = 'install_app'
    UNINSTALL_APP = 'uninstall_app'


class DeviceGroupType(str, Enum):
    """设备分组类型枚举（INT-80 设备分组，区别于用例分组 group_bp）"""
    TEST = 'test'          # 测试设备组（被测设备）
    PLAYBACK = 'playback'  # 播放设备组


class AlarmMetricType(str, Enum):
    """设备告警指标枚举（INT-80 监控告警）"""
    OFFLINE_DURATION = 'offline_duration'    # 离线时长（秒）
    HEALTH_CHECK_FAILURES = 'health_check_failures'  # 连续健康检查失败次数
    CPU = 'cpu'                              # CPU 使用率（%）
    MEMORY = 'memory'                        # 内存使用率（%）
    BATTERY = 'battery'                      # 电量（%）


class AlarmSeverity(str, Enum):
    """告警级别枚举（INT-80）"""
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


class AlarmStatus(str, Enum):
    """告警状态枚举（INT-80 告警确认流）"""
    ACTIVE = 'active'
    ACKNOWLEDGED = 'acknowledged'
    RESOLVED = 'resolved'


class DeviceStatusEventType(str, Enum):
    """设备状态事件类型枚举（INT-80 状态历史）"""
    ONLINE = 'online'
    OFFLINE = 'offline'
    HEALTH_CHECK = 'health_check'
    OPERATION = 'operation'


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
    DELIVERED    出站交付完成（transit 暂存包已按第三方契约投递 C 并收到同步响应；
                 允许幂等重投，C 按 transfer_id 去重；ephemeral 暂存仍按 TTL 回收，
                 交付事实保留于流水 meta.delivery 与 TransferDelivered 事件）
    FAILED       传输失败（合并校验失败等终态，需新建 transfer_id 重传）
    EXPIRED      超过 TTL 被清理（分片/临时文件回收，流水保留供审计）
    """
    CREATED = 'CREATED'
    TRANSFERRING = 'TRANSFERRING'
    COMPLETED = 'COMPLETED'
    DELIVERED = 'DELIVERED'
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


class PlaybackQueryCode(int, Enum):
    """播放设备查询响应业务码枚举（INT-92）

    device_service GetPlaybackDeviceResponse.code 按失败原因填充，
    audio_service ACL 据此区分「设备不存在（合法降级返回 None）」与
    「服务故障（上抛 PlaybackDeviceQueryError 传递真实错误）」：
    - UNSPECIFIED(0)   旧版本 device_service 未透传 code——保持既有降级语义
    - OK(200)          查询成功
    - NOT_FOUND(404)   设备不存在/已删除——合法降级，返回 None
    - INTERNAL_ERROR(500) 服务故障——调用方必须上抛，不得伪装成业务空结果
    """
    UNSPECIFIED = 0
    OK = 200
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
