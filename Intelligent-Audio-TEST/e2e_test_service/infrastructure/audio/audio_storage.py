# -*- coding: utf-8 -*-
"""OSS 音频存储基础设施。

封装 shared.clients.oss_client.OSSClient，为应用层提供统一的音频
文件上传/下载接口。音频文件统一存储在 OSS 的 'audios' 类目下。
"""

from typing import Optional


class AudioStorage:
    """OSS 音频存储

    委托给 shared.clients.oss_client.OSSClient 执行实际的 OSS 上传/下载。
    应用层通过本类访问音频存储，不直接依赖 OSSClient 实现。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._oss_client = None
        return cls._instance

    @property
    def oss_client(self):
        if self._oss_client is None:
            from shared.clients.oss_client import OSSClient
            self._oss_client = OSSClient()
        return self._oss_client

    def upload_audio(self, local_path: str, task_id: str,
                     tc_rel_id: str, device_id: str,
                     filename: str = "audio.wav") -> str:
        """上传音频文件到 OSS

        :param local_path: 本地音频文件路径
        :param task_id: 任务 ID
        :param tc_rel_id: 测试用例关联 ID
        :param device_id: 设备 ID
        :param filename: 文件名
        :return: OSS 逻辑 key
        """
        oss_key = f"{task_id}/{tc_rel_id}/{device_id}/{filename}"
        return self.oss_client.upload_file(
            local_path=local_path,
            category='audios',
            key=oss_key,
        )

    def upload_audio_bytes(self, data: bytes, task_id: str,
                          tc_rel_id: str, device_id: str,
                          filename: str = "audio.wav",
                          content_type: Optional[str] = None) -> str:
        """上传音频字节数据到 OSS"""
        oss_key = f"{task_id}/{tc_rel_id}/{device_id}/{filename}"
        return self.oss_client.upload_bytes(
            data=data,
            category='audios',
            key=oss_key,
            content_type=content_type,
        )

    def download_audio(self, oss_key: str, local_path: str) -> str:
        """从 OSS 下载音频文件到本地"""
        return self.oss_client.download_file(
            category='audios',
            key=oss_key,
            local_path=local_path,
        )

    def get_audio_bytes(self, oss_key: str) -> bytes:
        """从 OSS 下载音频为字节数据"""
        return self.oss_client.download_bytes(
            category='audios',
            key=oss_key,
        )
