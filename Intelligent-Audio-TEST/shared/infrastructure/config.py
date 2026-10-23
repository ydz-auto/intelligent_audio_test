"""
基础设施配置基类（Shared Kernel）
所有服务的公共配置：数据库、Redis、OSS、gRPC 服务发现、日志
"""
import os
from typing import Optional


class ConfigValidationError(RuntimeError):
    """配置校验异常"""


def _get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """读取环境变量，required=True 时缺失则报错"""
    val = os.environ.get(key, default)
    if required and not val:
        raise ConfigValidationError(f'环境变量 {key} 未配置')
    return val


def _get_int(key: str, default: int = 0, required: bool = False) -> int:
    val = _get_env(key, str(default) if default else None, required)
    return int(val) if val else 0


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ('true', '1', 'yes')


class BaseConfig:
    """基础设施配置（所有服务共用）"""

    # --- 平台版本（/health 暴露，供 tests/api 健康检查区分 V9.7.10/V9.7.31，避免误连）---
    PLATFORM_VERSION: str = _get_env('PLATFORM_VERSION', 'V9.7.31')

    # --- 数据库 ---
    AUDIO_STORAGE_PATH: str = os.environ.get(
        'AUDIO_STORAGE_PATH',
        os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios')
    )
    # 本地静态资源根（音频上传临时目录/历史数据重映射基准）
    LOCAL_STORAGE_ROOT: str = os.environ.get('LOCAL_STORAGE_ROOT', './storage')
    # 历史静态根（逗号分隔）：存量绝对路径音频的旧存储根，解析时重映射到
    # LOCAL_STORAGE_ROOT 下同相对路径（存储根迁移后救活旧记录，INT-106）
    AUDIO_LEGACY_STATIC_ROOTS: str = _get_env('AUDIO_LEGACY_STATIC_ROOTS', '')

    DATABASE_URL: str = _get_env('DATABASE_URL', required=True)

    # --- Redis ---
    REDIS_URL: str = _get_env('REDIS_URL', 'redis://localhost:6379')

    # --- Redis 事件总线频道前缀（INT-1235）---
    # 真实库栈与 5000 段开发栈共用同一 Redis 实例时，pub/sub 通道名跨 DB index
    # 全局共享：真实栈 SSE 会转发测试栈发布的 task_log / task_progress 等事件，
    # 事件里的 task_id/report_id 在主库不存在，前端名称解析逐个 404（INT-1227）。
    # 真实栈经 real_stack.py 设置非空前缀（如 real_）把通道隔离成
    # real_task_events 等；默认空 = 保持原通道名，5000 段等其它栈不受影响。
    EVENT_CHANNEL_PREFIX: str = _get_env('EVENT_CHANNEL_PREFIX', '')

    # --- OSS (RustFS / S3 兼容) ---
    OSS_ENDPOINT: str = _get_env('OSS_ENDPOINT', 'http://localhost:9000')
    OSS_ACCESS_KEY: str = _get_env('OSS_ACCESS_KEY', required=True)
    OSS_SECRET_KEY: str = _get_env('OSS_SECRET_KEY', required=True)
    OSS_REGION: str = _get_env('OSS_REGION', 'us-east-1')

    # 单桶模式：所有数据存同一桶，用 OSS_BUCKET_NAME + OSS_KEY_PREFIX 区分。
    # 配置了 OSS_BUCKET_NAME 后，下面各 category 的桶名被忽略，key 统一加前缀：
    #   {OSS_KEY_PREFIX}/{category}/{原key}
    # 不配置则回退到多桶模式（向后兼容）。
    OSS_BUCKET_NAME: str = _get_env('OSS_BUCKET_NAME', '')  # 单桶名，空则用多桶
    OSS_KEY_PREFIX: str = _get_env('OSS_KEY_PREFIX', '')    # 桶内统一前缀，如 intelligent_audio_test

    # 多桶模式（向后兼容，OSS_BUCKET_NAME 为空时生效）
    OSS_BUCKET_AUDIOS: str = _get_env('OSS_BUCKET_AUDIOS', 'audios')
    OSS_BUCKET_CASE_RESULT: str = _get_env('OSS_BUCKET_CASE_RESULT', 'case-result')
    OSS_BUCKET_REF_PARAMS: str = _get_env('OSS_BUCKET_REF_PARAMS', 'ref-params')
    OSS_BUCKET_REPORTS: str = _get_env('OSS_BUCKET_REPORTS', 'reports')
    OSS_BUCKET_ARCHIVES: str = _get_env('OSS_BUCKET_ARCHIVES', 'archives')
    OSS_BUCKET_TEMP: str = _get_env('OSS_BUCKET_TEMP', 'temp')
    OSS_BUCKET_RAW_CHUNKS: str = _get_env('OSS_BUCKET_RAW_CHUNKS', 'raw-chunks')  # 前端直传分片临时存储，带 TTL

    # --- 统一存储降级 ---
    STORAGE_FALLBACK_ENABLED: bool = _get_bool('STORAGE_FALLBACK_ENABLED', True)  # OSS 不可用时降级到本地磁盘
    STORAGE_LOCAL_ROOT: str = _get_env('STORAGE_LOCAL_ROOT', './storage_local')   # 本地降级存储根目录

    # --- 任务数据导入导出（INT-25）---
    # 网关与 task_service 共享磁盘读写导出/导入 ZIP：docker 部署时两容器需挂载同一卷
    DATA_TRANSFER_TMP_DIR: str = _get_env(
        'DATA_TRANSFER_TMP_DIR',
        os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'data_transfer')
    )
    # 网关 ZIP 上传大小上限（MB），显式设置防超大包拖垮网关
    DATA_TRANSFER_MAX_UPLOAD_MB: int = _get_int('DATA_TRANSFER_MAX_UPLOAD_MB', 2048)

    # --- 服务发现 ---
    SERVICE_HOST: str = _get_env('SERVICE_HOST', '0.0.0.0')
    SERVICE_NAME: str = _get_env('SERVICE_NAME', 'unknown')

    # --- 日志 ---
    LOG_LEVEL: str = _get_env('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED: bool = _get_bool('CONSOLE_LOG_ENABLED', True)

    # --- 日志体系（INT-81）：服务运行日志与业务日志全部落文件 ---
    LOG_ROOT_DIR: str = _get_env('LOG_ROOT_DIR', './logs')
    # 环境标识（dev/prod）：prod 下 DEBUG 级日志不落业务文件
    LOG_ENVIRONMENT: str = _get_env('LOG_ENVIRONMENT', 'dev').lower()
    # 服务运行日志：logs/{service_name}/ 单文件上限与保留天数（按天+按大小双条件轮转）
    LOG_SERVICE_MAX_MB: int = _get_int('LOG_SERVICE_MAX_MB', 50)
    LOG_SERVICE_RETENTION_DAYS: int = _get_int('LOG_SERVICE_RETENTION_DAYS', 30)
    # 业务日志（执行/评估/设备）：去库化落文件开关与阈值
    LOG_BUSINESS_ENABLED: bool = _get_bool('LOG_BUSINESS_ENABLED', True)
    # 回滚开关：True 时业务日志同时保留入库（历史行为），默认仅落文件
    LOG_BUSINESS_DB_ENABLED: bool = _get_bool('LOG_BUSINESS_DB_ENABLED', False)
    LOG_BUSINESS_MAX_MB: int = _get_int('LOG_BUSINESS_MAX_MB', 50)
    LOG_BUSINESS_RETENTION_DAYS: int = _get_int('LOG_BUSINESS_RETENTION_DAYS', 30)
    # 读取侧单次查询最大物化条数（0 = 不限）：大任务轮询兜底，total 变下界语义
    LOG_BUSINESS_MAX_SCAN_ENTRIES: int = _get_int('LOG_BUSINESS_MAX_SCAN_ENTRIES', 100000)
    # 读取侧同参数查询结果短 TTL 缓存秒数（0 = 关闭，INT-100）：TTL 窗口内
    # list 与 stats 共享一次文件扫描，消除任务维度轮询双遍扫描；只缓存查询
    # 结果（CQRS 查询侧只读），新写入行在 TTL 内不可见（有界展示时延）
    LOG_BUSINESS_SCAN_CACHE_TTL_SECONDS: int = _get_int('LOG_BUSINESS_SCAN_CACHE_TTL_SECONDS', 3)
    # TTL 缓存单条条目物化上限（0 = 不限，INT-128）：单条缓存最多物化该条数
    # （与扫描上限取小生效），超限结果不缓存（命中/未命中结果一致，仅失去
    # TTL 内复扫豁免）；防大任务单条缓存数十 MB、32 条最坏 GB 级驻留
    LOG_BUSINESS_SCAN_CACHE_ENTRY_MAX_ENTRIES: int = _get_int('LOG_BUSINESS_SCAN_CACHE_ENTRY_MAX_ENTRIES', 10000)
    # 任务维度合并视图 DB 侧单次拉取行数上限（0 = 不限，INT-100）：替代
    # per_page=100000 全量拉取，与文件侧 MAX_SCAN_ENTRIES 同为下界语义兜底
    LOG_DB_MERGE_MAX_ROWS: int = _get_int('LOG_DB_MERGE_MAX_ROWS', 100000)
    # DB 侧计数/统计短 TTL 缓存秒数（0 = 关闭，INT-1468）：logs 表为最大增长
    # 表（30 万行级），列表 total 的 count(*) 与 stats 的 group by 每次请求全表
    # 扫描；TTL 窗口内同过滤条件共享一次聚合结果（只缓存聚合值，不缓存行数据），
    # 新写入日志在 TTL 内不计入（与文件侧扫描缓存同为有界展示时延）
    LOG_DB_AGGREGATE_CACHE_TTL_SECONDS: int = _get_int(
        'LOG_DB_AGGREGATE_CACHE_TTL_SECONDS', 3)
    # 聚合缓存条目上限（防过滤条件组合把内存撑爆，超出按最早写入淘汰）
    LOG_DB_AGGREGATE_CACHE_MAX_ENTRIES: int = _get_int(
        'LOG_DB_AGGREGATE_CACHE_MAX_ENTRIES', 256)

    # --- gRPC 服务发现 ---
    E2E_TEST_SERVICE_HOST: str = _get_env('E2E_TEST_SERVICE_HOST', 'localhost')
    E2E_TEST_SERVICE_GRPC_PORT: int = _get_int('E2E_TEST_SERVICE_GRPC_PORT', 50051)
    # --- audio_service gRPC（P2.5 从 e2e_test_service 拆出）---
    AUDIO_SERVICE_HOST: str = _get_env('AUDIO_SERVICE_HOST', 'localhost')
    AUDIO_SERVICE_GRPC_PORT: int = _get_int('AUDIO_SERVICE_GRPC_PORT', 50052)
    # --- device_service gRPC（P2.5 从 e2e_test_service 拆出）---
    DEVICE_SERVICE_HOST: str = _get_env('DEVICE_SERVICE_HOST', 'localhost')
    DEVICE_SERVICE_GRPC_PORT: int = _get_int('DEVICE_SERVICE_GRPC_PORT', 50053)
    TASK_SERVICE_HOST: str = _get_env('TASK_SERVICE_HOST', 'localhost')
    TASK_SERVICE_GRPC_PORT: int = _get_int('TASK_SERVICE_GRPC_PORT', 50061)
    API_TEST_SERVICE_HOST: str = _get_env('API_TEST_SERVICE_HOST', 'localhost')
    API_TEST_SERVICE_PORT: int = _get_int('API_TEST_SERVICE_PORT', 5003)
    API_TEST_SERVICE_GRPC_PORT: int = _get_int('API_TEST_SERVICE_GRPC_PORT', 50071)

    # --- evaluation_service gRPC ---
    EVALUATION_SERVICE_HOST: str = _get_env('EVALUATION_SERVICE_HOST', 'localhost')
    EVALUATION_SERVICE_GRPC_PORT: int = _get_int('EVALUATION_SERVICE_GRPC_PORT', 50091)

    # --- algorithm_service gRPC（端口 50067 预留，proto 待接入）---
    ALGORITHM_SERVICE_HOST: str = _get_env('ALGORITHM_SERVICE_HOST', 'localhost')
    ALGORITHM_SERVICE_GRPC_PORT: int = _get_int('ALGORITHM_SERVICE_GRPC_PORT', 50067)

    # --- report_service gRPC ---
    REPORT_SERVICE_HOST: str = _get_env('REPORT_SERVICE_HOST', 'localhost')
    REPORT_SERVICE_GRPC_PORT: int = _get_int('REPORT_SERVICE_GRPC_PORT', 51068)

    # --- auth_service gRPC（51069，INT-926 平移避开 Windows Hyper-V 排除端口段）---
    AUTH_SERVICE_HOST: str = _get_env('AUTH_SERVICE_HOST', 'localhost')
    AUTH_SERVICE_GRPC_PORT: int = _get_int('AUTH_SERVICE_GRPC_PORT', 51069)

    # --- gRPC 客户端默认 deadline（INT-54）---
    # 未显式传 timeout 的 gRPC 客户端调用统一注入该 deadline（秒）。
    # 依赖服务「接受连接但不响应」时，无 deadline 的调用在 grpc._channel._blocking
    # 永久阻塞，调用点 try/except 的失败收敛路径永不执行（INT-54：StartTaskLifecycle
    # 内 RegisterTaskEvents → 假死 device_service → 集成回归全量悬挂 25 分钟+）。
    # 注入后 DEADLINE_EXCEEDED 与 UNAVAILABLE 同为 RpcError，走既有失败收敛路径。
    # 显式传 timeout 的调用不受影响；已知长耗时调用点应显式传更大的 timeout。
    GRPC_CLIENT_DEADLINE_SECONDS: int = _get_int('GRPC_CLIENT_DEADLINE_SECONDS', 60)

    # --- gRPC 显式长调用 deadline（INT-54 打回修复）---
    # StartE2ETask 在 e2e_test_service 处理器内同步执行整个 E2E 用例
    # （多轮设备准备/播放/采集/评估），总时长结构性可超默认 deadline，须显式放宽。
    GRPC_E2E_SYNC_TIMEOUT_SECONDS: int = _get_int('GRPC_E2E_SYNC_TIMEOUT_SECONDS', 600)
    # 设备长时操作 gRPC 显式 deadline（INT-616）：device_service 侧 post_process
    # 含回复等待（BASE_REPLY_END_TIMEOUT 默认 60s）+ 录屏收尾，initialize/pre_process
    # 含 UI RPC/唤醒解锁，CollectResult(mode=round) 含 OSS 上传——均结构性可超默认
    # deadline（60s），默认 deadline 与之相等会竞态击杀合法慢轮次（真机走查实测
    # post_process 60,016ms 被 DEADLINE_EXCEEDED 掐断）。已知长耗时设备操作调用点
    # 显式传本值；其余调用维持默认 deadline（INT-54 防假死悬挂的失败收敛路径不变）。
    GRPC_DEVICE_OP_DEADLINE_SECONDS: int = _get_int('GRPC_DEVICE_OP_DEADLINE_SECONDS', 180)

    # --- gRPC 客户端收发消息上限（MB，INT-1292）---
    # grpcio 客户端默认收包上限 4MiB：大响应 RPC（任务导出 23MB 包、报告/评估
    # 只读导出）在客户端收不下 → RESOURCE_EXHAUSTED。统一放大到
    # GRPC_MAX_MESSAGE_MB。默认 64MB：INT-1292 实测任务 419 导出跨服务响应
    # ExportDimensionsForTasks 23,448,131B / ExportReportsForTasks 20,439,856B，
    # 16MB（对齐 transfer_agent 分片口径 TRANSFER_GRPC_MAX_MESSAGE_MB）仍收不下；
    # 64MB 覆盖最大实测单响应并留余量。服务端 send 上限默认不受 4MB 限制
    # （实测可发送 >30MB），故只需客户端侧放开。
    GRPC_MAX_MESSAGE_MB: int = _get_int('GRPC_MAX_MESSAGE_MB', 64)

    # --- 回收站保留期（INT-141）：软删除记录保留天数，过期由各服务
    # SoftDeleteCleaner 守护线程硬清理（定时调度走既有执行引擎/守护线程，
    # 不走五通道事件）；环境变量可覆盖默认 60 天 ---
    TRASH_RETENTION_DAYS: int = _get_int('TRASH_RETENTION_DAYS', 60)

    # --- 工具 ---
    FFMPEG_PATH: str = _get_env('FFMPEG_PATH', 'ffmpeg')
    FFPROBE_PATH: str = _get_env('FFPROBE_PATH', 'ffprobe')

    # --- 邮件通知 SMTP（INT-80 设备告警通知渠道，未配置=禁用）---
    SMTP_HOST: str = _get_env('SMTP_HOST', '')
    SMTP_PORT: int = _get_int('SMTP_PORT', 465)
    SMTP_USER: str = _get_env('SMTP_USER', '')
    SMTP_PASSWORD: str = _get_env('SMTP_PASSWORD', '')
    SMTP_USE_SSL: bool = _get_env('SMTP_USE_SSL', 'true').lower() in ('true', '1', 'yes')
    SMTP_FROM: str = _get_env('SMTP_FROM', '')  # 发件人，空则回退 SMTP_USER
    ALERT_EMAIL_RECIPIENTS: str = _get_env('ALERT_EMAIL_RECIPIENTS', '')  # 逗号分隔收件人列表

    @classmethod
    def validate(cls):
        """启动时调用，校验必填项"""
        for attr in dir(cls):
            if attr.isupper():
                val = getattr(cls, attr)
                if val is None:
                    raise ConfigValidationError(f'配置 {attr} 未设置')
