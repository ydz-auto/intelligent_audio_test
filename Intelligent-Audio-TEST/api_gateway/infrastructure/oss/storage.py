"""api_gateway 基础设施层 —— OSS 存储

统一封装 OSS 客户端，提供音频/报告/采集结果的上传、下载、预签名 URL。
"""
import os
from typing import Optional

from shared.clients.oss_client import oss
from shared.utils.log_handler import log_and_emit


class AudioOSSStorage:
    """音频 OSS 存储"""

    BUCKET = 'audios'
    PREFIX = 'audios'

    @staticmethod
    def upload(local_path: str, file_name: Optional[str] = None) -> str:
        """上传音频到 OSS，返回 object_key"""
        if not file_name:
            file_name = os.path.basename(local_path)
        object_key = f'{AudioOSSStorage.PREFIX}/{file_name}'
        oss.upload_file(local_path, object_key)
        log_and_emit('INFO', 'audio', f'OSS 上传音频: {object_key}')
        return object_key

    @staticmethod
    def download(object_key: str, local_path: str) -> str:
        """从 OSS 下载音频"""
        oss.download_file(object_key, local_path)
        return local_path

    @staticmethod
    def get_presigned_url(object_key: str, expires: int = 3600) -> str:
        """获取预签名下载 URL"""
        return oss.get_presigned_url(object_key, expires)

    @staticmethod
    def delete(object_key: str):
        """删除 OSS 对象"""
        oss.delete_object(object_key)


class ReportOSSStorage:
    """报告 OSS 存储"""

    PREFIX = 'reports'

    @staticmethod
    def upload_report_file(local_path: str, report_id: str, file_name: Optional[str] = None) -> str:
        """上传报告文件到 OSS"""
        if not file_name:
            file_name = os.path.basename(local_path)
        object_key = f'{ReportOSSStorage.PREFIX}/{report_id}/{file_name}'
        oss.upload_file(local_path, object_key)
        return object_key

    @staticmethod
    def upload_report_bytes(data: bytes, report_id: str, file_name: str) -> str:
        """上传报告字节数据到 OSS"""
        object_key = f'{ReportOSSStorage.PREFIX}/{report_id}/{file_name}'
        oss.upload_bytes(data, object_key)
        return object_key

    @staticmethod
    def get_presigned_url(object_key: str, expires: int = 3600) -> str:
        """获取报告预签名下载 URL"""
        return oss.get_presigned_url(object_key, expires)

    @staticmethod
    def delete(object_key: str):
        """删除报告 OSS 对象"""
        oss.delete_object(object_key)


class ResultOSSStorage:
    """测试结果 OSS 存储"""

    PREFIX = 'test-results'

    @staticmethod
    def upload_result(data: bytes, task_id: str, case_id: str, file_name: str) -> str:
        """上传测试结果到 OSS"""
        object_key = f'{ResultOSSStorage.PREFIX}/{task_id}/{case_id}/{file_name}'
        oss.upload_bytes(data, object_key)
        return object_key

    @staticmethod
    def download_result(object_key: str, local_path: str) -> str:
        """从 OSS 下载测试结果"""
        oss.download_file(object_key, local_path)
        return local_path

    @staticmethod
    def get_presigned_url(object_key: str, expires: int = 3600) -> str:
        """获取测试结果预签名 URL"""
        return oss.get_presigned_url(object_key, expires)
