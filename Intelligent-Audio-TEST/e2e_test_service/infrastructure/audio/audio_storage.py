# -*- coding: utf-8 -*-
"""音频存储基础设施。

封装 shared.utils.storage.Storage，为应用层提供统一的音频
文件上传/下载接口。音频文件统一存储在 'audios' 类目下。
OSS 不可用时自动降级到本地磁盘存储。
"""

from typing import Optional


class AudioStorage:
    """音频存储

    委托给 shared.utils.storage.Storage 单例。
    应用层通过本类访问音频存储，不直接依赖 Storage 实现。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._storage = None
        return cls._instance

    @property
    def storage(self):
        if self._storage is None:
            from shared.utils.storage import storage
            self._storage = storage
        return self._storage

    def upload_audio(self, local_path: str, task_id: str,
                     tc_rel_id: str, device_id: str,
                     filename: str = "audio.wav") -> str:
        """上传音频文件到存储

        :param local_path: 本地音频文件路径
        :param task_id: 任务 ID
        :param tc_rel_id: 测试用例关联 ID
        :param device_id: 设备 ID
        :param filename: 文件名
        :return: 带 scheme 前缀的存储路径
        """
        key = f"{task_id}/{tc_rel_id}/{device_id}/{filename}"
        return self.storage.save_file(local_path, 'audios', key)

    def upload_audio_bytes(self, data: bytes, task_id: str,
                          tc_rel_id: str, device_id: str,
                          filename: str = "audio.wav",
                          content_type: Optional[str] = None) -> str:
        """上传音频字节数据到存储"""
        key = f"{task_id}/{tc_rel_id}/{device_id}/{filename}"
        return self.storage.save_bytes(data, 'audios', key,
                                       content_type=content_type)

    def download_audio(self, path: str, local_path: str) -> str:
        """从存储下载音频文件到本地"""
        return self.storage.load_file(path, local_path)

    def get_audio_bytes(self, path: str) -> bytes:
        """从存储下载音频为字节数据"""
        return self.storage.load_bytes(path)
