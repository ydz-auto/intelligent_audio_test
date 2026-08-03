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

    def is_available(self) -> bool:
        """探测 OSS 是否可用（head_bucket 探活）。"""
        try:
            self._ensure_init()
            self._client.head_bucket(Bucket=self._bucket('audios'))
            return True
        except Exception:
            return False

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

        # 单桶模式：OSS_BUCKET_NAME 非空时，所有 category 共用此桶，
        # key 统一拼成 {OSS_KEY_PREFIX}/{category}/{key}。
        # 不配置则回退到多桶模式（向后兼容）。
        self._single_bucket = BaseConfig.OSS_BUCKET_NAME or ''
        self._key_prefix = BaseConfig.OSS_KEY_PREFIX.strip('/')

        # 多桶模式 bucket 名称
        self._buckets = {
            'audios': BaseConfig.OSS_BUCKET_AUDIOS,
            'case_result': BaseConfig.OSS_BUCKET_CASE_RESULT,
            'ref_params': BaseConfig.OSS_BUCKET_REF_PARAMS,
            'reports': BaseConfig.OSS_BUCKET_REPORTS,
            'archives': BaseConfig.OSS_BUCKET_ARCHIVES,
            'temp': BaseConfig.OSS_BUCKET_TEMP,
            'raw_chunks': BaseConfig.OSS_BUCKET_RAW_CHUNKS,
        }

    def _bucket(self, category: str) -> str:
        """返回 category 对应的 bucket 名（单桶模式返回统一桶名）"""
        if self._single_bucket:
            return self._single_bucket
        bucket = self._buckets.get(category)
        if not bucket:
            raise ValueError(f"Unknown OSS category: {category}")
        return bucket

    def _full_key(self, category: str, key: str) -> str:
        """生成实际存储的 OSS key。

        单桶模式：{OSS_KEY_PREFIX}/{category}/{key}
        多桶模式：{key}（原样返回）
        """
        if not self._single_bucket:
            return key
        parts = []
        if self._key_prefix:
            parts.append(self._key_prefix)
        parts.append(category)
        parts.append(key.lstrip('/'))
        return '/'.join(parts)

    def _strip_key(self, category: str, full_key: str) -> str:
        """从实际存储的 OSS key 还原出逻辑 key（去掉前缀）。

        单桶模式：{OSS_KEY_PREFIX}/{category}/{key} → {key}
        多桶模式：原样返回
        """
        if not self._single_bucket:
            return full_key
        # 构造期望的前缀
        prefix_parts = []
        if self._key_prefix:
            prefix_parts.append(self._key_prefix)
        prefix_parts.append(category)
        prefix = '/'.join(prefix_parts) + '/'
        if full_key.startswith(prefix):
            return full_key[len(prefix):]
        return full_key

    # ---- 上传 ----

    def upload_file(self, local_path: str, category: str, key: str) -> str:
        """
        上传本地文件到 OSS

        :param local_path: 本地文件路径
        :param category: 存储类别（audios/case_result/ref_params/reports/archives/temp）
        :param key: 逻辑 key（如 task_123/case_456/device_sn/audio.wav）
        :return: 逻辑 key（单桶模式下实际存储 key 带前缀，返回值与输入一致）
        """
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        self._client.upload_file(local_path, bucket, full_key)
        return key

    def upload_bytes(self, data: bytes, category: str, key: str, content_type: Optional[str] = None) -> str:
        """上传字节数据到 OSS"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        extra_args = {'ContentType': content_type} if content_type else {}
        self._client.upload_fileobj(io.BytesIO(data), bucket, full_key, ExtraArgs=extra_args)
        return key

    def upload_stream(self, stream: BinaryIO, category: str, key: str, content_type: Optional[str] = None) -> str:
        """上传文件流到 OSS"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        extra_args = {'ContentType': content_type} if content_type else {}
        self._client.upload_fileobj(stream, bucket, full_key, ExtraArgs=extra_args)
        return key

    # ---- 下载 ----

    def download_file(self, category: str, key: str, local_path: str) -> str:
        """
        从 OSS 下载文件到本地

        :param category: 存储类别
        :param key: 逻辑 key
        :param local_path: 本地目标路径
        :return: 本地文件路径
        """
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self._client.download_file(bucket, full_key, local_path)
        return local_path

    def download_bytes(self, category: str, key: str) -> bytes:
        """从 OSS 下载文件为字节"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        obj = self._client.get_object(Bucket=bucket, Key=full_key)
        return obj['Body'].read()

    def download_stream(self, category: str, key: str) -> BinaryIO:
        """从 OSS 下载文件流（不读入内存）"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        obj = self._client.get_object(Bucket=bucket, Key=full_key)
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
        self._ensure_init()
        import tempfile
        local_path = tempfile.mktemp(suffix=suffix)
        return self.download_file(category, key, local_path)

    # ---- 管理 ----

    def exists(self, category: str, key: str) -> bool:
        """检查对象是否存在"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        try:
            self._client.head_object(Bucket=bucket, Key=full_key)
            return True
        except ClientError:
            return False

    def delete(self, category: str, key: str):
        """删除对象"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        self._client.delete_object(Bucket=bucket, Key=full_key)

    def list_objects(self, category: str, prefix: str = '') -> list:
        """列出对象 key 列表（返回逻辑 key，已去掉前缀）"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_prefix = self._full_key(category, prefix)
        resp = self._client.list_objects_v2(Bucket=bucket, Prefix=full_prefix)
        return [self._strip_key(category, obj['Key']) for obj in resp.get('Contents', [])]

    def get_presigned_url(self, category: str, key: str, expires: int = 3600) -> str:
        """
        生成预签名 URL（前端直传/直下）

        :param expires: 过期秒数（默认 1 小时）
        :return: 预签名 URL
        """
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': full_key},
            ExpiresIn=expires,
        )

    def get_upload_presigned_url(self, category: str, key: str, expires: int = 3600) -> str:
        """生成上传预签名 URL（前端直传）"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        return self._client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': full_key},
            ExpiresIn=expires,
        )

    # ---- S3 Multipart Upload（前端分片直传 OSS）----

    def create_multipart_upload(self, category: str, key: str) -> str:
        """初始化分片上传，返回 Upload ID"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        resp = self._client.create_multipart_upload(Bucket=bucket, Key=full_key)
        return resp['UploadId']

    def get_part_upload_presigned_url(self, category: str, key: str, upload_id: str,
                                       part_number: int, expires: int = 3600) -> str:
        """生成单个分片上传的预签名 URL（前端直传分片到 OSS）"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        return self._client.generate_presigned_url(
            'upload_part',
            Params={
                'Bucket': bucket,
                'Key': full_key,
                'UploadId': upload_id,
                'PartNumber': part_number,
            },
            ExpiresIn=expires,
        )

    def complete_multipart_upload(self, category: str, key: str, upload_id: str,
                                   parts: list) -> dict:
        """完成分片上传，合并 OSS 端的分片

        :param parts: [{'PartNumber': 1, 'ETag': '"xxx"'}, ...]
        :return: CompleteMultipartUpload 响应
        """
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        resp = self._client.complete_multipart_upload(
            Bucket=bucket,
            Key=full_key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts},
        )
        return resp

    def abort_multipart_upload(self, category: str, key: str, upload_id: str):
        """取消分片上传，清理已上传的分片"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        self._client.abort_multipart_upload(
            Bucket=bucket,
            Key=full_key,
            UploadId=upload_id,
        )

    def list_multipart_parts(self, category: str, key: str, upload_id: str) -> list:
        """列出已上传的分片（用于断点续传）"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        resp = self._client.list_parts(
            Bucket=bucket,
            Key=full_key,
            UploadId=upload_id,
        )
        return resp.get('Parts', [])

    def delete_object(self, category: str, key: str):
        """删除单个对象"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_key = self._full_key(category, key)
        self._client.delete_object(Bucket=bucket, Key=full_key)

    def delete_prefix(self, category: str, prefix: str):
        """批量删除指定前缀下的所有对象"""
        self._ensure_init()
        bucket = self._bucket(category)
        full_prefix = self._full_key(category, prefix)
        resp = self._client.list_objects_v2(Bucket=bucket, Prefix=full_prefix)
        objects = [{'Key': obj['Key']} for obj in resp.get('Contents', [])]
        if objects:
            self._client.delete_objects(Bucket=bucket, Delete={'Objects': objects})

    # ---- 便捷方法 ----

    def build_key(self, task_id, case_id, device_sn, filename) -> str:
        """构建标准 OSS key：{task_id}/{case_id}/{device_sn}/{filename}"""
        return f"{task_id}/{case_id}/{device_sn}/{filename}"


# 模块级单例
oss = OSSClient()
