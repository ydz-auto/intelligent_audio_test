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
