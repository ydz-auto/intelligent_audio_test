# -*- coding: utf-8 -*-
"""TaskOSSStorage - 任务相关文件存储。

委托给 shared.utils.storage.Storage 单例。
封装任务维度的文件存储语义：
- 采集结果上传/下载 (case_result)
- 报告归档 (reports/archives)
- 临时文件 (temp)

OSS 不可用时自动降级到本地磁盘存储。
"""
from __future__ import annotations

from typing import List, Optional

from shared.infrastructure.storage import storage


class TaskOSSStorage:
    """任务文件存储。

    使用 Storage 单例，按任务/用例维度组织 key。
    不维护状态，方法均为幂等操作。
    """

    # 存储类别常量
    CATEGORY_CASE_RESULT = 'case_result'
    CATEGORY_REPORTS = 'reports'
    CATEGORY_ARCHIVES = 'archives'
    CATEGORY_TEMP = 'temp'

    def __init__(self, storage_client=storage):
        self._storage = storage_client

    # ---- 采集结果 ----

    def upload_case_result_file(self, local_path: str, task_id: int,
                                 case_id: str, device_sn: str,
                                 filename: str) -> str:
        """上传采集结果文件。

        Returns:
            带 scheme 前缀的存储路径。
        """
        key = self._storage.build_key(task_id, case_id, device_sn, filename)
        return self._storage.save_file(local_path, self.CATEGORY_CASE_RESULT, key)

    def upload_case_result_bytes(self, data: bytes, task_id: int, case_id: str,
                                  device_sn: str, filename: str,
                                  content_type: Optional[str] = None) -> str:
        """上传采集结果字节数据。"""
        key = self._storage.build_key(task_id, case_id, device_sn, filename)
        return self._storage.save_bytes(data, self.CATEGORY_CASE_RESULT, key,
                                        content_type=content_type)

    def download_case_result(self, task_id: int, case_id: str,
                              device_sn: str, filename: str,
                              local_path: str) -> str:
        """下载采集结果文件到本地路径。"""
        key = self._storage.build_key(task_id, case_id, device_sn, filename)
        path = self._storage.build_path(self.CATEGORY_CASE_RESULT, key)
        return self._storage.load_file(path, local_path)

    def get_case_result_bytes(self, task_id: int, case_id: str,
                               device_sn: str, filename: str) -> bytes:
        """下载采集结果文件为字节。"""
        key = self._storage.build_key(task_id, case_id, device_sn, filename)
        path = self._storage.build_path(self.CATEGORY_CASE_RESULT, key)
        return self._storage.load_bytes(path)

    # ---- 报告 ----

    def upload_report(self, local_path: str, task_id: int,
                      report_filename: str) -> str:
        """上传报告文件。"""
        key = f"task_{task_id}/{report_filename}"
        return self._storage.save_file(local_path, self.CATEGORY_REPORTS, key)

    def get_report_url(self, task_id: int, report_filename: str,
                       expires: int = 3600) -> Optional[str]:
        """获取报告预签名 URL。"""
        key = f"task_{task_id}/{report_filename}"
        path = self._storage.build_path(self.CATEGORY_REPORTS, key)
        return self._storage.get_url(path, expires)

    def list_reports(self, task_id: int) -> List[str]:
        """列出任务下的所有报告文件 key。

        注意：此操作依赖 OSS list_objects，OSS 不可用时返回空列表。
        """
        from shared.clients.oss_client import oss
        prefix = f"task_{task_id}/"
        try:
            return oss.list_objects(self.CATEGORY_REPORTS, prefix)
        except Exception:
            return []

    # ---- 归档 ----

    def upload_archive(self, local_path: str, task_id: int,
                        archive_name: str) -> str:
        """上传归档文件（如完整结果压缩包）。"""
        key = f"task_{task_id}/{archive_name}"
        return self._storage.save_file(local_path, self.CATEGORY_ARCHIVES, key)

    def get_archive_url(self, task_id: int, archive_name: str,
                        expires: int = 3600) -> Optional[str]:
        """获取归档文件预签名 URL。"""
        key = f"task_{task_id}/{archive_name}"
        path = self._storage.build_path(self.CATEGORY_ARCHIVES, key)
        return self._storage.get_url(path, expires)

    # ---- 临时文件 ----

    def upload_temp(self, data: bytes, task_id: int, filename: str,
                     content_type: Optional[str] = None) -> str:
        """上传临时文件（带 TTL 语义，由 OSS 生命周期策略清理）。"""
        key = f"task_{task_id}/{filename}"
        return self._storage.save_bytes(data, self.CATEGORY_TEMP, key,
                                        content_type=content_type)

    # ---- 清理 ----

    def delete_task_files(self, task_id: int) -> None:
        """删除任务相关的所有文件（采集结果、报告、归档、临时）。

        用于任务删除时的级联清理。幂等操作。
        """
        from shared.clients.oss_client import oss
        prefix = f"task_{task_id}/"
        for category in [self.CATEGORY_CASE_RESULT, self.CATEGORY_REPORTS,
                         self.CATEGORY_ARCHIVES, self.CATEGORY_TEMP]:
            try:
                keys = oss.list_objects(category, prefix)
                for key in keys:
                    try:
                        self._storage.delete(f'{category}/{key}')
                    except Exception:
                        pass
            except Exception:
                pass

    def case_result_exists(self, task_id: int, case_id: str,
                            device_sn: str, filename: str) -> bool:
        """检查采集结果文件是否存在。"""
        key = self._storage.build_key(task_id, case_id, device_sn, filename)
        path = self._storage.build_path(self.CATEGORY_CASE_RESULT, key)
        return self._storage.exists(path)


# 模块级单例
task_oss_storage = TaskOSSStorage()
