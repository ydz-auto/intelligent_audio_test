# -*- coding: utf-8 -*-
"""
OSS/MinIO 客户端（可选能力）— 双模式文件传递支持

与主项目 Intelligent-Audio-TEST 的单桶模式保持一致的键规则：
    S3 key = {OSS_KEY_PREFIX}/{category}/{key}
例如 oss://audios/task_1/case_2/dev_3/a.wav
    -> bucket=intelligent-audio-test
    -> key=intelligent_audio_test/audios/task_1/case_2/dev_3/a.wav

用法：
    1. 未配置 OSS_ENDPOINT：oss_client.enabled = False，
       resolve_oss_paths 原样返回，不影响既有 multipart 上传 / 本地路径两种传参方式。
       此时 boto3 未被导入，未安装 boto3 的环境下 multipart 模式依然正常工作。
    2. 配置后：create_task 的 task_params 中任意层级形如 oss://... 的字符串
       会在计算前自动下载为本地文件路径并替换。
"""
import os
import threading
import logging

logger = logging.getLogger(__name__)

_SCHEME_OSS = 'oss://'


class OSSClient:
    """S3 兼容对象存储客户端（单例，懒初始化）。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._client = None
        return cls._instance

    @property
    def enabled(self) -> bool:
        """是否启用了 OSS 能力（是否配置了 OSS_ENDPOINT）。"""
        from ..config import config
        return bool(config.OSS_ENDPOINT)

    def _ensure_init(self):
        """懒初始化 boto3 客户端（双重检查锁）。

        boto3 在未启用 OSS 时不会被导入，避免可选依赖缺失导致 ImportError。
        """
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            from ..config import config
            if not config.OSS_ENDPOINT:
                raise RuntimeError('OSS_ENDPOINT 未配置，OSS 能力未启用')
            # 懒导入 boto3：仅在 OSS 配置存在时引入
            try:
                import boto3
                from botocore.config import Config as BotoConfig
            except ImportError:
                raise RuntimeError(
                    'boto3 未安装，无法使用 OSS 能力。请安装：pip install boto3>=1.34.0'
                )
            self._bucket = config.OSS_BUCKET_NAME
            self._key_prefix = (config.OSS_KEY_PREFIX or '').strip('/')
            self._client = boto3.client(
                's3',
                endpoint_url=config.OSS_ENDPOINT,
                aws_access_key_id=config.OSS_ACCESS_KEY,
                aws_secret_access_key=config.OSS_SECRET_KEY,
                config=BotoConfig(
                    retries={'max_attempts': 3, 'mode': 'standard'},
                    connect_timeout=5,
                    read_timeout=120,
                ),
                region_name=config.OSS_REGION,
            )
            self._initialized = True

    def download(self, oss_path: str, local_dir: str) -> str:
        """将 oss://{category}/{key} 下载到 local_dir 下的本地文件，返回本地路径。

        本地文件与 OSS key 目录结构保持一致（local_dir/category/key），便于排查；
        同目录存在时直接复用（幂等，避免同一任务重复下载）。
        """
        self._ensure_init()
        rest = oss_path[len(_SCHEME_OSS):]
        category, _, key = rest.partition('/')
        if not category or not key:
            raise ValueError(f'非法 OSS 路径: {oss_path}')

        # 单桶模式：{OSS_KEY_PREFIX}/{category}/{key}
        parts = []
        if self._key_prefix:
            parts.append(self._key_prefix)
        parts.append(category)
        parts.append(key.lstrip('/'))
        full_key = '/'.join(parts)

        local_path = os.path.join(local_dir, category, key)
        if os.path.exists(local_path):
            return local_path
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self._client.download_file(self._bucket, full_key, local_path)
        return local_path


oss_client = OSSClient()


def resolve_oss_paths(value, local_dir=None):
    """递归扫描 dict/list/str，把 oss:// 前缀的值下载为本地路径并替换。

    - 未启用 OSS 或值不是 oss:// 前缀：原样返回（与 multipart 上传 / 本地路径并存）。
    - 嵌套结构（rounds、played_audios 等）同样会被递归处理。
    - 下载失败会抛异常，让任务快速失败并返回明确错误信息。
    """
    if not oss_client.enabled:
        return value

    if isinstance(value, str):
        if value.startswith(_SCHEME_OSS):
            if not local_dir:
                raise ValueError('resolve_oss_paths 需要 local_dir 参数')
            try:
                return oss_client.download(value, local_dir)
            except Exception as e:
                logger.exception(f'OSS 下载失败: {value}: {e}')
                raise
        return value
    if isinstance(value, dict):
        return {k: resolve_oss_paths(v, local_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_oss_paths(item, local_dir) for item in value]
    return value
