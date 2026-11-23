# -*- coding: utf-8 -*-
"""
OSS/MinIO 客户端（可选能力）— 双模式文件传递支持

与主项目 Intelligent-Audio-TEST 的 OSS 双模式保持一致的键规则：
    单桶模式（OSS_BUCKET_NAME 非空）：
        S3 key = {OSS_KEY_PREFIX}/{category}/{key}
    多桶模式（OSS_BUCKET_NAME 为空，RustFS 默认）：
        bucket = {category}，S3 key = {key}
例如 oss://audios/task_1/case_2/dev_3/a.wav
    -> 单桶: bucket=intelligent-audio-test, key=intelligent_audio_test/audios/task_1/case_2/dev_3/a.wav
    -> 多桶: bucket=audios, key=task_1/case_2/dev_3/a.wav

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

# upload_stream 落盘中转的拷贝块大小（避免一次性读入大文件）
_UPLOAD_COPY_CHUNK = 1024 * 1024


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
                    # 键规则相关默认值，供 _split_oss_path 在懒初始化前独立使用
                    cls._instance._bucket = None
                    cls._instance._key_prefix = ''
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

    def _split_oss_path(self, oss_path: str):
        """解析 oss:// 路径 → (bucket, full_key, category, key)

        - 单桶模式（OSS_BUCKET_NAME 非空）：所有 category 共用该桶，
          key = {OSS_KEY_PREFIX}/{category}/{key}
        - 多桶模式（OSS_BUCKET_NAME 为空，RustFS 默认）：桶名即 category，
          key = {key}（与 Intelligent-Audio-TEST shared 存储约定一致）

        category/key 用于本地镜像目录结构（local_dir/category/key），
        bucket/full_key 用于 S3 读写。
        """
        rest = oss_path[len(_SCHEME_OSS):]
        category, _, key = rest.partition('/')
        if not category or not key:
            raise ValueError(f'非法 OSS 路径: {oss_path}')
        if self._bucket:
            parts = []
            if self._key_prefix:
                parts.append(self._key_prefix)
            parts.append(category)
            parts.append(key.lstrip('/'))
            return self._bucket, '/'.join(parts), category, key
        return category, key.lstrip('/'), category, key

    def download(self, oss_path: str, local_dir: str) -> str:
        """将 oss://{category}/{key} 下载到 local_dir 下的本地文件，返回本地路径。

        本地文件与 OSS key 目录结构保持一致（local_dir/category/key），便于排查；
        同目录存在时直接复用（幂等，避免同一任务重复下载）。
        """
        self._ensure_init()
        bucket, full_key, category, key = self._split_oss_path(oss_path)
        local_path = os.path.join(local_dir, category, key)
        if os.path.exists(local_path):
            return local_path
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self._client.download_file(bucket, full_key, local_path)
        return local_path

    def exists(self, oss_path: str) -> bool:
        """判断 oss:// 对象是否存在（head_object）。"""
        self._ensure_init()
        bucket, full_key, _, _ = self._split_oss_path(oss_path)
        try:
            self._client.head_object(Bucket=bucket, Key=full_key)
            return True
        except Exception:
            return False

    def get_size(self, oss_path: str) -> int:
        """返回 oss:// 对象字节数（head_object ContentLength）。"""
        self._ensure_init()
        bucket, full_key, _, _ = self._split_oss_path(oss_path)
        resp = self._client.head_object(Bucket=bucket, Key=full_key)
        return int(resp.get('ContentLength') or 0)

    def read_bytes(self, oss_path: str, limit: int = None) -> bytes:
        """将 oss:// 对象读入内存（不落盘）。

        limit 指定后只读前 limit 字节（boto3 Range 请求，用于读 wav 头等场景）。
        大文件请用 open_stream 流式读取，避免整对象进内存。
        """
        self._ensure_init()
        bucket, full_key, _, _ = self._split_oss_path(oss_path)
        kwargs = {}
        if limit:
            kwargs['Range'] = f'bytes=0-{max(0, int(limit) - 1)}'
        body = self._client.get_object(Bucket=bucket, Key=full_key, **kwargs)['Body']
        return body.read()

    def open_stream(self, oss_path: str, limit: int = None):
        """打开 oss:// 对象的流式读取句柄（boto3 StreamingBody，不整对象进内存）。

        可作文件对象传给 requests multipart 等按块读取的场景；
        使用后需调用 close()。
        """
        self._ensure_init()
        bucket, full_key, _, _ = self._split_oss_path(oss_path)
        kwargs = {}
        if limit:
            kwargs['Range'] = f'bytes=0-{max(0, int(limit) - 1)}'
        return self._client.get_object(Bucket=bucket, Key=full_key, **kwargs)['Body']

    def upload_bytes(self, data: bytes, oss_path: str) -> str:
        """将字节上传为 oss://{category}/{key}，返回 oss:// 引用。

        oss_path 可传完整 oss:// 引用或裸 {category}/{key}（自动补 scheme）。
        兼容单桶/多桶（RustFS）键规则。
        """
        self._ensure_init()
        full = oss_path if oss_path.startswith(_SCHEME_OSS) else f'{_SCHEME_OSS}{oss_path.lstrip("/")}'
        bucket, full_key, _, _ = self._split_oss_path(full)
        self._client.put_object(Bucket=bucket, Key=full_key, Body=data)
        return full

    def upload_stream(self, fileobj, oss_path: str) -> str:
        """将文件对象流式上传为 oss://{category}/{key}，返回 oss:// 引用。

        boto3 1.4x 对来源不可寻址/无 fileno 的流（如 Flask 上传的 SpooledTemporaryFile）
        走 multipart 分块上传时不会携带 Content-Length，COS/RustFS 会直接拒绝
        UploadPart(MissingContentLength)。这里先分块落临时文件，再用 upload_file
        按真实文件大小上传，保证大文件分段的 Content-Length 可靠；
        临时文件在 finally 中清理，不会长期占用磁盘。
        """
        self._ensure_init()
        full = oss_path if oss_path.startswith(_SCHEME_OSS) else f'{_SCHEME_OSS}{oss_path.lstrip("/")}'
        bucket, full_key, _, _ = self._split_oss_path(full)
        import shutil
        import tempfile

        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            try:
                fileobj.seek(0)
            except (AttributeError, OSError):
                pass
            with tmp:
                shutil.copyfileobj(fileobj, tmp, length=_UPLOAD_COPY_CHUNK)
            self._client.upload_file(tmp.name, bucket, full_key)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return full

    def upload_file(self, local_path: str, oss_path: str) -> str:
        """将本地文件上传为 oss://{category}/{key}，返回 oss:// 引用。

        oss_path 可传完整 oss:// 引用或裸 {category}/{key}（自动补 scheme）。
        """
        self._ensure_init()
        full = oss_path if oss_path.startswith(_SCHEME_OSS) else f'{_SCHEME_OSS}{oss_path.lstrip("/")}'
        bucket, full_key, _, _ = self._split_oss_path(full)
        self._client.upload_file(local_path, bucket, full_key)
        return full


oss_client = OSSClient()


def resolve_oss_paths(value, local_dir=None):
    """递归扫描 dict/list/str，把 oss:// 前缀的值下载为本地路径并替换。

    - 未启用 OSS 或值不是 oss:// 前缀：原样返回（与 multipart 上传 / 本地路径并存）。
    - 嵌套结构（rounds、played_audios 等）同样会被递归处理。
    - 下载失败会抛异常，让任务快速失败并返回明确错误信息。
    - OSS_RESOLVE_MODE=stream 时原样返回（保留 oss:// 引用），由消费方
      （ASR / LLM 裁判 / 音频元数据等）直接内存读取对象存储，不落盘。
    """
    if not oss_client.enabled:
        return value
    try:
        from ..config import config as _cfg
        if getattr(_cfg, 'OSS_RESOLVE_MODE', 'download') == 'stream':
            return value
    except Exception:
        pass

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
