"""api_gateway 基础设施层 —— 统一存储

封装 shared.utils.storage.Storage，提供音频/报告/采集结果的上传、下载、预签名 URL。
OSS 不可用时自动降级到本地磁盘存储。
"""
import os
import uuid
from typing import Optional

from shared.infrastructure.storage import storage
from shared.utils.log_handler import log_and_emit


class AudioOSSStorage:
    """音频存储"""

    CATEGORY = 'audios'
    PREFIX = 'audios'

    @staticmethod
    def upload(local_path: str, file_name: Optional[str] = None) -> str:
        """上传音频到存储，返回带 scheme 前缀的 path"""
        if not file_name:
            file_name = os.path.basename(local_path)
        key = f'{AudioOSSStorage.PREFIX}/{file_name}'
        path = storage.save_file(local_path, AudioOSSStorage.CATEGORY, key)
        log_and_emit('INFO', 'audio', f'存储上传音频: {path}')
        return path

    @staticmethod
    def download(path: str, local_path: str) -> str:
        """从存储下载音频"""
        return storage.load_file(path, local_path)

    @staticmethod
    def get_presigned_url(path: str, expires: int = 3600) -> Optional[str]:
        """获取预签名下载 URL（本地降级模式返回 None）"""
        return storage.get_url(path, expires)

    @staticmethod
    def delete(path: str):
        """删除存储对象"""
        storage.delete(path)


class ReportOSSStorage:
    """报告存储"""

    CATEGORY = 'reports'
    PREFIX = 'reports'
    # 文件型独立报告（INT-1763 §6.2 / D0 A11-1）：复用 reports 类别，
    # 不得新造 category（多桶模式下未知 category 直接 ValueError）
    STUDIO_UPLOAD_PREFIX = 'studio_uploads'

    @staticmethod
    def upload_report_file(local_path: str, report_id: str, file_name: Optional[str] = None) -> str:
        """上传报告文件到存储"""
        if not file_name:
            file_name = os.path.basename(local_path)
        key = f'{report_id}/{file_name}'
        return storage.save_file(local_path, ReportOSSStorage.CATEGORY, key)

    @staticmethod
    def upload_studio_upload(data: bytes, file_name: str,
                             content_type: str = 'application/octet-stream') -> str:
        """上传文件型独立报告（md/html/pptx），key = studio_uploads/{uuid}.{ext}"""
        ext = os.path.splitext(file_name or '')[1].lower()
        key = f'{ReportOSSStorage.STUDIO_UPLOAD_PREFIX}/{uuid.uuid4().hex}{ext}'
        return storage.save_bytes(data, ReportOSSStorage.CATEGORY, key,
                                  content_type=content_type)

    @staticmethod
    def download_bytes(path: str) -> bytes:
        """读取存储对象字节（上传件预览/下载）"""
        return storage.load_bytes(path)

    @staticmethod
    def upload_report_bytes(data: bytes, report_id: str, file_name: str) -> str:
        """上传报告字节数据到存储"""
        key = f'{report_id}/{file_name}'
        return storage.save_bytes(data, ReportOSSStorage.CATEGORY, key)

    @staticmethod
    def get_presigned_url(path: str, expires: int = 3600) -> Optional[str]:
        """获取报告预签名下载 URL"""
        return storage.get_url(path, expires)

    @staticmethod
    def delete(path: str):
        """删除报告存储对象"""
        storage.delete(path)


class ResultOSSStorage:
    """测试结果存储"""

    CATEGORY = 'case_result'
    PREFIX = 'test-results'

    @staticmethod
    def upload_result(data: bytes, task_id: str, case_id: str, file_name: str) -> str:
        """上传测试结果到存储"""
        key = f'{task_id}/{case_id}/{file_name}'
        return storage.save_bytes(data, ResultOSSStorage.CATEGORY, key)

    @staticmethod
    def download_result(path: str, local_path: str) -> str:
        """从存储下载测试结果"""
        return storage.load_file(path, local_path)

    @staticmethod
    def get_presigned_url(path: str, expires: int = 3600) -> Optional[str]:
        """获取测试结果预签名 URL"""
        return storage.get_url(path, expires)
