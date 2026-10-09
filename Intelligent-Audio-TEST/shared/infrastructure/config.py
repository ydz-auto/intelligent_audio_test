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

    DATABASE_URL: str = _get_env('DATABASE_URL', required=True)

    # --- Redis ---
    REDIS_URL: str = _get_env('REDIS_URL', 'redis://localhost:6379')

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

    # --- api_adapter_service gRPC ---
    ADAPTER_SERVICE_HOST: str = _get_env('ADAPTER_SERVICE_HOST', 'localhost')
    ADAPTER_SERVICE_GRPC_PORT: int = _get_int('ADAPTER_SERVICE_GRPC_PORT', 50081)

    # --- evaluation_service gRPC ---
    EVALUATION_SERVICE_HOST: str = _get_env('EVALUATION_SERVICE_HOST', 'localhost')
    EVALUATION_SERVICE_GRPC_PORT: int = _get_int('EVALUATION_SERVICE_GRPC_PORT', 50091)

    # --- algorithm_service gRPC（端口 50067 预留，proto 待接入）---
    ALGORITHM_SERVICE_HOST: str = _get_env('ALGORITHM_SERVICE_HOST', 'localhost')
    ALGORITHM_SERVICE_GRPC_PORT: int = _get_int('ALGORITHM_SERVICE_GRPC_PORT', 50067)

    # --- report_service gRPC ---
    REPORT_SERVICE_HOST: str = _get_env('REPORT_SERVICE_HOST', 'localhost')
    REPORT_SERVICE_GRPC_PORT: int = _get_int('REPORT_SERVICE_GRPC_PORT', 50068)

    # --- auth_service gRPC ---
    AUTH_SERVICE_HOST: str = _get_env('AUTH_SERVICE_HOST', 'localhost')
    AUTH_SERVICE_GRPC_PORT: int = _get_int('AUTH_SERVICE_GRPC_PORT', 50069)

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
    # SendRound 同步执行被测请求：deadline = 请求单轮上限（request.timeout，
    # 即 session_timeout，默认 60s）+ 本余量；余量覆盖适配器渲染/序列化/网络开销。
    GRPC_SENDROUND_DEADLINE_MARGIN_SECONDS: int = _get_int('GRPC_SENDROUND_DEADLINE_MARGIN_SECONDS', 30)

    # --- 工具 ---
    FFMPEG_PATH: str = _get_env('FFMPEG_PATH', 'ffmpeg')
    FFPROBE_PATH: str = _get_env('FFPROBE_PATH', 'ffprobe')

    @classmethod
    def validate(cls):
        """启动时调用，校验必填项"""
        for attr in dir(cls):
            if attr.isupper():
                val = getattr(cls, attr)
                if val is None:
                    raise ConfigValidationError(f'配置 {attr} 未设置')
