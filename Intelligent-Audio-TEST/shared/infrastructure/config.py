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

    # --- 数据库 ---
    DATABASE_URL: str = _get_env('DATABASE_URL', required=True)

    # --- Redis ---
    REDIS_URL: str = _get_env('REDIS_URL', 'redis://localhost:6379')

    # --- OSS (MinIO / S3 兼容) ---
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

    # --- 服务发现 ---
    SERVICE_HOST: str = _get_env('SERVICE_HOST', '0.0.0.0')
    SERVICE_NAME: str = _get_env('SERVICE_NAME', 'unknown')

    # --- 日志 ---
    LOG_LEVEL: str = _get_env('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED: bool = _get_bool('CONSOLE_LOG_ENABLED', True)

    # --- gRPC 服务发现 ---
    E2E_TEST_SERVICE_HOST: str = _get_env('E2E_TEST_SERVICE_HOST', 'localhost')
    E2E_TEST_SERVICE_GRPC_PORT: int = _get_int('E2E_TEST_SERVICE_GRPC_PORT', 50051)
    TASK_SERVICE_HOST: str = _get_env('TASK_SERVICE_HOST', 'localhost')
    TASK_SERVICE_GRPC_PORT: int = _get_int('TASK_SERVICE_GRPC_PORT', 50061)
    API_TEST_SERVICE_HOST: str = _get_env('API_TEST_SERVICE_HOST', 'localhost')
    API_TEST_SERVICE_PORT: int = _get_int('API_TEST_SERVICE_PORT', 5003)
    API_TEST_SERVICE_GRPC_PORT: int = _get_int('API_TEST_SERVICE_GRPC_PORT', 50071)

    # --- api_adapter_service gRPC ---
    ADAPTER_SERVICE_HOST: str = _get_env('ADAPTER_SERVICE_HOST', 'localhost')
    ADAPTER_SERVICE_GRPC_PORT: int = _get_int('ADAPTER_SERVICE_GRPC_PORT', 50081)

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
