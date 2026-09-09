# -*- coding: utf-8 -*-
"""
OSS 客户端封装 - S3 兼容（开发环境 MinIO / 生产环境 AWS S3）

与 V9.7.31 的 shared/clients/oss_client.py 保持相同的协议语义（单桶模式）：
  开发：OSS_ENDPOINT=http://localhost:9000  (MinIO)
  生产：OSS_ENDPOINT=https://s3.amazonaws.com (S3)

单桶模式：所有 category 共用 OSS_BUCKET_NAME，实际 key = {OSS_KEY_PREFIX}/{category}/{key}
路径 URI 约定：oss://{category}/{key}

仅提供评估链路下载所需的最小能力（exists / load_file / download_bytes）。
"""
import os
import logging
import tempfile
import threading

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_SCHEME_OSS = 'oss://'


class OSSClient:
    """S3 兼容对象存储客户端（单例，延迟初始化）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def _ensure_init(self):
        """延迟初始化（双重检查锁），首次使用时才连接 OSS。"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._init()
            self._initialized = True

    def _init(self):
        from backend.config.config import Config  # 内联导入避免循环依赖
        self._endpoint = Config.OSS_ENDPOINT or 'http://localhost:9000'
        access_key = Config.OSS_ACCESS_KEY
        secret_key = Config.OSS_SECRET_KEY
        self._bucket = Config.OSS_BUCKET_NAME or ''
        self._key_prefix = (Config.OSS_KEY_PREFIX or '').strip('/')
        self._region = Config.OSS_REGION or 'us-east-1'
        if not access_key or not secret_key:
            raise RuntimeError('未配置 OSS_ACCESS_KEY / OSS_SECRET_KEY 环境变量')
        if not self._bucket:
            raise RuntimeError('未配置 OSS_BUCKET_NAME 环境变量（当前仅支持单桶模式）')

        self._client = boto3.client(
            's3',
            endpoint_url=self._endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                retries={'max_attempts': 3, 'mode': 'standard'},
                connect_timeout=5,
                read_timeout=60,
            ),
            region_name=self._region,
        )

    @staticmethod
    def _parse_path(path):
        """解析存储 URI，返回 (category, key)。无前缀的按 OSS 处理，category 从首段推断。"""
        rest = path[len(_SCHEME_OSS):] if path.startswith(_SCHEME_OSS) else path
        parts = rest.split('/', 1)
        category = parts[0] if parts else ''
        key = parts[1] if len(parts) > 1 else ''
        return category, key

    def _full_key(self, category, key):
        """单桶模式：{OSS_KEY_PREFIX}/{category}/{key}"""
        parts = []
        if self._key_prefix:
            parts.append(self._key_prefix)
        parts.append(category)
        parts.append(key.lstrip('/'))
        return '/'.join(parts)

    # ---- 下载 ----

    def download_bytes(self, path: str) -> bytes:
        """按 URI（oss://category/key）下载对象为字节。"""
        self._ensure_init()
        category, key = self._parse_path(path)
        obj = self._client.get_object(Bucket=self._bucket, Key=self._full_key(category, key))
        return obj['Body'].read()

    def load_file(self, path: str, local_path: str = None) -> str:
        """按 URI 下载到本地路径（默认临时文件），返回本地文件路径；对象不存在返回 None。"""
        self._ensure_init()
        category, key = self._parse_path(path)
        if not local_path:
            suffix = os.path.splitext(key)[-1] or '.tmp'
            local_path = tempfile.mktemp(suffix=suffix)
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        try:
            self._client.download_file(self._bucket, self._full_key(category, key), local_path)
        except ClientError:
            if os.path.exists(local_path):
                os.remove(local_path)
            return None
        return local_path

    def exists(self, path: str) -> bool:
        """检查对象是否存在。"""
        self._ensure_init()
        category, key = self._parse_path(path)
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full_key(category, key))
            return True
        except ClientError:
            return False


# 模块级单例
oss = OSSClient()