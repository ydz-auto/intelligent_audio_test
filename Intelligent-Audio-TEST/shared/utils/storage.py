# -*- coding: utf-8 -*-
"""
统一存储抽象层 — 对应用层屏蔽 OSS / 本地磁盘差异。

设计目标：
  1. 应用层只调用 storage.save_file / load_file 等语义化方法，
     不感知文件最终落在 OSS 还是本地磁盘。
  2. OSS 可用时优先写 OSS；OSS 不可用时自动降级到本地磁盘
     （STORAGE_FALLBACK_ENABLED=True 时）。
  3. file_path 字段带 scheme 前缀（oss:// 或 local://），读取时自动
     路由到对应后端；历史数据无前缀时默认按 OSS 处理。

典型用法：
    from shared.utils.storage import storage

    # 保存
    path = storage.save_file('/tmp/audio.wav', 'audios',
                             'task_1/case_2/dev_3/audio.wav')
    # path = 'oss://audios/task_1/case_2/dev_3/audio.wav'

    # 读取
    local_path = storage.load_file(path)         # 下载到本地临时文件
    data = storage.load_bytes(path)              # 读取为 bytes

    # 预签名 URL（仅 OSS 模式有意义，本地降级时返回 None）
    url = storage.get_url(path)

    # 删除
    storage.delete(path)

    # 直接保存 bytes
    path = storage.save_bytes(b'...', 'case_result', 'task_1/summary.json',
                              content_type='application/json')
"""

import os
import shutil
import tempfile
import threading
from typing import Optional, BinaryIO

from shared.infrastructure.config import BaseConfig
from shared.utils.log_handler import log_not_emit

# scheme 前缀
_SCHEME_OSS = 'oss://'
_SCHEME_LOCAL = 'local://'

_MODULE_NAME = 'storage'


class Storage:
    """统一存储抽象（单例）。

    所有方法均幂等，线程安全。
    OSS 不可用时自动降级到本地磁盘存储（可通过配置关闭）。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._oss_client = None
                    cls._oss_checked = False
                    cls._oss_ok = False
        return cls._instance

    # ---- OSS 客户端管理 ----

    @property
    def _oss(self):
        """延迟加载 OSSClient 单例"""
        if self._oss_client is None:
            from shared.clients.oss_client import OSSClient
            self._oss_client = OSSClient()
        return self._oss_client

    def _oss_available(self) -> bool:
        """探测 OSS 是否可用。

        首次探测后缓存结果；探测失败后每隔一段时间重试
        （避免 OSS 恢复后一直走本地降级）。
        """
        if self._oss_checked and self._oss_ok:
            return True
        try:
            ok = self._oss.is_available()
        except Exception:
            ok = False
        self._oss_ok = ok
        # _oss_checked 仅在首次有意义；失败后允许下次重新探测
        if ok:
            self._oss_checked = True
        return ok

    def _use_oss(self) -> bool:
        """决定本次操作是否走 OSS。"""
        if not BaseConfig.STORAGE_FALLBACK_ENABLED:
            # 未开启降级：强制走 OSS（不可用则由调用方处理异常）
            return True
        return self._oss_available()

    # ---- 本地降级存储路径 ----

    def _local_path(self, category: str, key: str) -> str:
        """构建本地降级存储的完整路径：{STORAGE_LOCAL_ROOT}/{category}/{key}"""
        return os.path.join(BaseConfig.STORAGE_LOCAL_ROOT, category, key)

    # ---- scheme 解析 ----

    @staticmethod
    def _parse_path(path: str):
        """解析 file_path，返回 (scheme, category, key)。

        scheme: 'oss' | 'local' | ''（无前缀，默认 oss）
        历史数据无前缀时，按 OSS 处理，category 从 key 第一段推断。
        """
        if not path:
            return '', '', ''
        if path.startswith(_SCHEME_OSS):
            rest = path[len(_SCHEME_OSS):]
            parts = rest.split('/', 1)
            category = parts[0] if parts else ''
            key = parts[1] if len(parts) > 1 else ''
            return 'oss', category, key
        if path.startswith(_SCHEME_LOCAL):
            rest = path[len(_SCHEME_LOCAL):]
            parts = rest.split('/', 1)
            category = parts[0] if parts else ''
            key = parts[1] if len(parts) > 1 else ''
            return 'local', category, key
        # 无前缀的历史数据：默认 OSS，category 从 key 首段推断
        parts = path.split('/', 1)
        category = parts[0] if parts else ''
        key = parts[1] if len(parts) > 1 else ''
        return 'oss', category, key

    # ---- 公开 API：保存 ----

    def save_file(self, local_path: str, category: str, key: str) -> str:
        """保存本地文件到存储，返回带 scheme 前缀的 path。

        OSS 可用 → 上传到 OSS，返回 'oss://{category}/{key}'
        OSS 不可用 → 复制到本地降级目录，返回 'local://{category}/{key}'
        """
        try:
            if self._use_oss():
                self._oss.upload_file(local_path, category, key)
                return f'{_SCHEME_OSS}{category}/{key}'
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'save_file OSS failed, fallback to local: {e}',
                         category=category)
            if not BaseConfig.STORAGE_FALLBACK_ENABLED:
                raise
        # 降级到本地
        dst = self._local_path(category, key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(local_path, dst)
        return f'{_SCHEME_LOCAL}{category}/{key}'

    def save_bytes(self, data: bytes, category: str, key: str,
                   content_type: Optional[str] = None) -> str:
        """保存字节数据到存储，返回带 scheme 前缀的 path。"""
        try:
            if self._use_oss():
                self._oss.upload_bytes(data, category, key,
                                       content_type=content_type)
                return f'{_SCHEME_OSS}{category}/{key}'
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'save_bytes OSS failed, fallback to local: {e}',
                         category=category)
            if not BaseConfig.STORAGE_FALLBACK_ENABLED:
                raise
        # 降级到本地
        dst = self._local_path(category, key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(data)
        return f'{_SCHEME_LOCAL}{category}/{key}'

    def save_stream(self, stream: BinaryIO, category: str, key: str,
                    content_type: Optional[str] = None) -> str:
        """保存文件流到存储，返回带 scheme 前缀的 path。"""
        try:
            if self._use_oss():
                self._oss.upload_stream(stream, category, key,
                                        content_type=content_type)
                return f'{_SCHEME_OSS}{category}/{key}'
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'save_stream OSS failed, fallback to local: {e}',
                         category=category)
            if not BaseConfig.STORAGE_FALLBACK_ENABLED:
                raise
        # 降级到本地
        dst = self._local_path(category, key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            shutil.copyfileobj(stream, f)
        return f'{_SCHEME_LOCAL}{category}/{key}'

    # ---- 公开 API：读取 ----

    def load_file(self, path: str, local_path: Optional[str] = None) -> str:
        """从存储下载文件到本地路径。

        :param path: 带 scheme 前缀的存储路径
        :param local_path: 本地目标路径，None 则用临时文件
        :return: 本地文件路径
        """
        scheme, category, key = self._parse_path(path)
        if not local_path:
            suffix = os.path.splitext(key)[-1] or '.tmp'
            local_path = tempfile.mktemp(suffix=suffix)

        if scheme == 'local':
            src = self._local_path(category, key)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            shutil.copy2(src, local_path)
            return local_path

        # scheme == 'oss' 或无前缀（默认 OSS）
        try:
            return self._oss.download_file(category, key, local_path)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'load_file OSS failed, try local: {e}',
                         category=category)
            # 尝试从本地降级副本读取
            src = self._local_path(category, key)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                shutil.copy2(src, local_path)
                return local_path
            raise FileNotFoundError(f'文件不存在（OSS 和本地均无）: {path}')

    def load_bytes(self, path: str) -> bytes:
        """从存储读取文件为字节数据。"""
        scheme, category, key = self._parse_path(path)

        if scheme == 'local':
            src = self._local_path(category, key)
            with open(src, 'rb') as f:
                return f.read()

        # scheme == 'oss' 或无前缀
        try:
            return self._oss.download_bytes(category, key)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'load_bytes OSS failed, try local: {e}',
                         category=category)
            src = self._local_path(category, key)
            if os.path.exists(src):
                with open(src, 'rb') as f:
                    return f.read()
            raise FileNotFoundError(f'文件不存在（OSS 和本地均无）: {path}')

    def load_stream(self, path: str) -> BinaryIO:
        """从存储读取文件流。

        注意：本地降级模式下返回文件句柄，调用方负责关闭。
        """
        scheme, category, key = self._parse_path(path)

        if scheme == 'local':
            src = self._local_path(category, key)
            return open(src, 'rb')

        return self._oss.download_stream(category, key)

    # ---- 公开 API：管理 ----

    def exists(self, path: str) -> bool:
        """检查文件是否存在。"""
        scheme, category, key = self._parse_path(path)

        if scheme == 'local':
            return os.path.exists(self._local_path(category, key))

        # OSS
        try:
            if self._oss.exists(category, key):
                return True
        except Exception:
            pass
        # 也检查本地降级副本
        return os.path.exists(self._local_path(category, key))

    def delete(self, path: str) -> None:
        """删除文件（OSS 和本地降级副本都会清理）。"""
        scheme, category, key = self._parse_path(path)

        # 先删 OSS
        if scheme != 'local':
            try:
                self._oss.delete_object(category, key)
            except Exception as e:
                log_not_emit('DEBUG', _MODULE_NAME,
                             f'delete OSS object failed (may not exist): {e}',
                             category=category)
        # 再删本地降级副本
        local = self._local_path(category, key)
        if os.path.exists(local):
            try:
                os.remove(local)
            except Exception:
                pass

    def get_url(self, path: str, expires: int = 3600) -> Optional[str]:
        """获取文件访问 URL。

        OSS 模式：返回预签名 URL
        本地降级模式：返回 None（调用方应改用 load_file/load_bytes）
        """
        scheme, category, key = self._parse_path(path)

        if scheme == 'local':
            return None

        try:
            return self._oss.get_presigned_url(category, key, expires=expires)
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'get_url OSS failed: {e}', category=category)
            return None

    # ---- 便捷方法 ----

    def build_path(self, category: str, key: str, prefer_oss: bool = True) -> str:
        """构建带 scheme 前缀的存储路径。

        :param prefer_oss: True 返回 oss:// 前缀（默认）；
                            False 返回 local:// 前缀
        """
        scheme = _SCHEME_OSS if prefer_oss else _SCHEME_LOCAL
        return f'{scheme}{category}/{key}'

    @staticmethod
    def build_key(task_id, case_id, device_sn, filename) -> str:
        """构建标准存储 key：{task_id}/{case_id}/{device_sn}/{filename}"""
        return f"{task_id}/{case_id}/{device_sn}/{filename}"


# 模块级单例
storage = Storage()
