# -*- coding: utf-8 -*-
"""TaskOSSStorage - 任务相关文件 OSS 存储。

委托给 shared.clients.oss_client.OssClient 单例。
封装任务维度的文件存储语义：
- 采集结果上传/下载 (case_result)
- 报告归档 (reports/archives)
- 临时文件 (temp)
"""
from __future__ import annotations

from typing import List, Optional

from shared.clients.oss_client import oss as _oss_client


class TaskOSSStorage:
    """任务文件 OSS 存储。

    使用单例 OSSClient，按任务/用例维度组织 key。
    不维护状态，方法均为幂等操作。
    """

    # OSS 存储类别常量
    CATEGORY_CASE_RESULT = 'case_result'
    CATEGORY_REPORTS = 'reports'
    CATEGORY_ARCHIVES = 'archives'
    CATEGORY_TEMP = 'temp'

    def __init__(self, oss_client=_oss_client):
        self._oss = oss_client

    # ---- 采集结果 ----

    def upload_case_result_file(self, local_path: str, task_id: int,
                                 case_id: str, device_sn: str,
                                 filename: str) -> str:
        """上传采集结果文件到 OSS。

        Returns:
            逻辑 key。
        """
        key = self._oss.build_key(task_id, case_id, device_sn, filename)
        return self._oss.upload_file(local_path, self.CATEGORY_CASE_RESULT, key)

    def upload_case_result_bytes(self, data: bytes, task_id: int, case_id: str,
                                  device_sn: str, filename: str,
                                  content_type: Optional[str] = None) -> str:
        """上传采集结果字节数据。"""
        key = self._oss.build_key(task_id, case_id, device_sn, filename)
        return self._oss.upload_bytes(data, self.CATEGORY_CASE_RESULT, key,
                                       content_type)

    def download_case_result(self, task_id: int, case_id: str,
                              device_sn: str, filename: str,
                              local_path: str) -> str:
        """下载采集结果文件到本地路径。"""
        key = self._oss.build_key(task_id, case_id, device_sn, filename)
        return self._oss.download_file(self.CATEGORY_CASE_RESULT, key, local_path)

    def get_case_result_bytes(self, task_id: int, case_id: str,
                               device_sn: str, filename: str) -> bytes:
        """下载采集结果文件为字节。"""
        key = self._oss.build_key(task_id, case_id, device_sn, filename)
        return self._oss.download_bytes(self.CATEGORY_CASE_RESULT, key)

    # ---- 报告 ----

    def upload_report(self, local_path: str, task_id: int,
                      report_filename: str) -> str:
        """上传报告文件。"""
        key = f"task_{task_id}/{report_filename}"
        return self._oss.upload_file(local_path, self.CATEGORY_REPORTS, key)

    def get_report_url(self, task_id: int, report_filename: str,
                       expires: int = 3600) -> str:
        """获取报告预签名 URL。"""
        key = f"task_{task_id}/{report_filename}"
        return self._oss.get_presigned_url(self.CATEGORY_REPORTS, key, expires)

    def list_reports(self, task_id: int) -> List[str]:
        """列出任务下的所有报告文件 key。"""
        prefix = f"task_{task_id}/"
        return self._oss.list_objects(self.CATEGORY_REPORTS, prefix)

    # ---- 归档 ----

    def upload_archive(self, local_path: str, task_id: int,
                        archive_name: str) -> str:
        """上传归档文件（如完整结果压缩包）。"""
        key = f"task_{task_id}/{archive_name}"
        return self._oss.upload_file(local_path, self.CATEGORY_ARCHIVES, key)

    def get_archive_url(self, task_id: int, archive_name: str,
                        expires: int = 3600) -> str:
        """获取归档文件预签名 URL。"""
        key = f"task_{task_id}/{archive_name}"
        return self._oss.get_presigned_url(self.CATEGORY_ARCHIVES, key, expires)

    # ---- 临时文件 ----

    def upload_temp(self, data: bytes, task_id: int, filename: str,
                     content_type: Optional[str] = None) -> str:
        """上传临时文件（带 TTL 语义，由 OSS 生命周期策略清理）。"""
        key = f"task_{task_id}/{filename}"
        return self._oss.upload_bytes(data, self.CATEGORY_TEMP, key, content_type)

    # ---- 清理 ----

    def delete_task_files(self, task_id: int) -> None:
        """删除任务相关的所有文件（采集结果、报告、归档、临时）。

        用于任务删除时的级联清理。幂等操作。
        """
        prefix = f"task_{task_id}/"
        try:
            self._oss.delete_prefix(self.CATEGORY_CASE_RESULT, prefix)
        except Exception:
            pass
        try:
            self._oss.delete_prefix(self.CATEGORY_REPORTS, prefix)
        except Exception:
            pass
        try:
            self._oss.delete_prefix(self.CATEGORY_ARCHIVES, prefix)
        except Exception:
            pass
        try:
            self._oss.delete_prefix(self.CATEGORY_TEMP, prefix)
        except Exception:
            pass

    def case_result_exists(self, task_id: int, case_id: str,
                            device_sn: str, filename: str) -> bool:
        """检查采集结果文件是否存在。"""
        key = self._oss.build_key(task_id, case_id, device_sn, filename)
        return self._oss.exists(self.CATEGORY_CASE_RESULT, key)


# 模块级单例
task_oss_storage = TaskOSSStorage()
