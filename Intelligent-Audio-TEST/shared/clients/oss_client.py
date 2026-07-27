"""
OSS 客户端封装 - S3 兼容（开发环境 MinIO / 生产环境 AWS S3）

通过环境变量切换：
  开发：OSS_ENDPOINT=http://localhost:9000  (MinIO)
  生产：OSS_ENDPOINT=https://s3.amazonaws.com (S3)

所有服务通过此客户端上传/下载文件，不直接操作本地磁盘路径。
"""
import os
import io
import threading
from typing import Optional, BinaryIO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from shared.infrastructure.config import BaseConfig


class OSSClient:
    """
    S3 兼容对象存储客户端（单例）

    Bucket 命名约定：
      audios/        - 音频文件（原始上传、重采样后）
      case-result/  - E2E 测试设备采集结果
      ref-params/    - 参考参数文件
      reports/      - 生成的报告文件
      archives/     - 归档文件
      temp/          - 临时文件（重采样中间文件等，带 TTL）
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        endpoint = BaseConfig.OSS_ENDPOINT
        access_key = BaseConfig.OSS_ACCESS_KEY
        secret_key = BaseConfig.OSS_SECRET_KEY
        if not access_key or not secret_key:
            raise RuntimeError('未配置 OSS_ACCESS_KEY 或 OSS_SECRET_KEY 环境变量')

        self._client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                retries={'max_attempts': 3, 'mode': 'standard'},
                connect_timeout=5,
                read_timeout=60,
            ),
            region_name=BaseConfig.OSS_REGION,
        )

        # bucket 名称从配置读取
        self._buckets = {
            'audios': BaseConfig.OSS_BUCKET_AUDIOS,
            'case_result': BaseConfig.OSS_BUCKET_CASE_RESULT,
            'ref_params': BaseConfig.OSS_BUCKET_REF_PARAMS,
            'reports': BaseConfig.OSS_BUCKET_REPORTS,
            'archives': BaseConfig.OSS_BUCKET_ARCHIVES,
            'temp': BaseConfig.OSS_BUCKET_TEMP,
        }

    def _bucket(self, category: str) -> str:
        bucket = self._buckets.get(category)
        if not bucket:
            raise ValueError(f"Unknown OSS category: {category}")
        return bucket

    # ---- 上传 ----

    def upload_file(self, local_path: str, category: str, key: str) -> str:
        """
        上传本地文件到 OSS

        :param local_path: 本地文件路径
        :param category: 存储类别（audios/case_result/ref_params/reports/archives/temp）
        :param key: OSS 对象 key（如 task_123/case_456/device_sn/audio.wav）
        :return: OSS key
        """
        bucket = self._bucket(category)
        self._client.upload_file(local_path, bucket, key)
        return key

    def upload_bytes(self, data: bytes, category: str, key: str, content_type: Optional[str] = None) -> str:
        """上传字节数据到 OSS"""
        bucket = self._bucket(category)
        extra_args = {'ContentType': content_type} if content_type else {}
        self._client.upload_fileobj(io.BytesIO(data), bucket, key, ExtraArgs=extra_args)
        return key

    def upload_stream(self, stream: BinaryIO, category: str, key: str, content_type: Optional[str] = None) -> str:
        """上传文件流到 OSS"""
        bucket = self._bucket(category)
        extra_args = {'ContentType': content_type} if content_type else {}
        self._client.upload_fileobj(stream, bucket, key, ExtraArgs=extra_args)
        return key

    # ---- 下载 ----

    def download_file(self, category: str, key: str, local_path: str) -> str:
        """
        从 OSS 下载文件到本地

        :param category: 存储类别
        :param key: OSS 对象 key
        :param local_path: 本地目标路径
        :return: 本地文件路径
        """
        bucket = self._bucket(category)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self._client.download_file(bucket, key, local_path)
        return local_path

    def download_bytes(self, category: str, key: str) -> bytes:
        """从 OSS 下载文件为字节"""
        bucket = self._bucket(category)
        obj = self._client.get_object(Bucket=bucket, Key=key)
        return obj['Body'].read()

    def download_stream(self, category: str, key: str) -> BinaryIO:
        """从 OSS 下载文件流（不读入内存）"""
        bucket = self._bucket(category)
        obj = self._client.get_object(Bucket=bucket, Key=key)
        return obj['Body']

    # ---- 临时文件（下载→处理→上传）----

    def download_to_temp(self, category: str, key: str, suffix: str = '.tmp') -> str:
        """
        从 OSS 下载文件到本地临时路径，处理后上传回 OSS

        典型用法（音频重采样）：
            tmp = oss.download_to_temp('audios', key, '.wav')
            # ffmpeg 重采样 tmp -> resampled.wav
            oss.upload_file(resampled_path, 'audios', new_key)
            os.remove(tmp); os.remove(resampled_path)
        """
        import tempfile
        local_path = tempfile.mktemp(suffix=suffix)
        return self.download_file(category, key, local_path)

    # ---- 管理 ----

    def exists(self, category: str, key: str) -> bool:
        """检查对象是否存在"""
        bucket = self._bucket(category)
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, category: str, key: str):
        """删除对象"""
        bucket = self._bucket(category)
        self._client.delete_object(Bucket=bucket, Key=key)

    def list_objects(self, category: str, prefix: str = '') -> list:
        """列出对象 key 列表"""
        bucket = self._bucket(category)
        resp = self._client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [obj['Key'] for obj in resp.get('Contents', [])]

    def get_presigned_url(self, category: str, key: str, expires: int = 3600) -> str:
        """
        生成预签名 URL（前端直传/直下）

        :param expires: 过期秒数（默认 1 小时）
        :return: 预签名 URL
        """
        bucket = self._bucket(category)
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expires,
        )

    def get_upload_presigned_url(self, category: str, key: str, expires: int = 3600) -> str:
        """生成上传预签名 URL（前端直传）"""
        bucket = self._bucket(category)
        return self._client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expires,
        )

    # ---- 便捷方法 ----

    def build_key(self, task_id, case_id, device_sn, filename) -> str:
        """构建标准 OSS key：{task_id}/{case_id}/{device_sn}/{filename}"""
        return f"{task_id}/{case_id}/{device_sn}/{filename}"


# 模块级单例
oss = OSSClient()
