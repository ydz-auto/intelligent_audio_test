# -*- coding: utf-8 -*-
"""API 测试结果存储 — 封装结果归档与读取，基于 shared.utils.storage.Storage。

存储类目约定：
  case-result/  - 设备采集结果
  reports/      - 报告文件
  archives/     - 归档文件

本服务将 API 测试会话的最终结果（JSON 摘要 + 可选明细）归档至存储。
OSS 不可用时自动降级到本地磁盘存储。
"""
import json
from typing import Optional

from shared.utils.storage import storage


class ResultStorage:
    """API 测试结果存储

    职责：
    - 将会话结果摘要上传到存储（archives 类目）
    - 读取已归档的结果
    - 删除归档结果（清理）

    所有路径前缀统一为 `api-test-results/<task_id>/`。
    """

    CATEGORY = "archives"

    def __init__(self, storage_client=None):
        # Storage 为单例，延迟注入便于测试时替换
        self._storage = storage_client or storage

    @staticmethod
    def _build_key(task_id: int, session_id: str, name: str = "summary") -> str:
        return f"api-test-results/{task_id}/{session_id}/{name}.json"

    def save_summary(self, task_id: int, session_id: str,
                     summary: dict) -> str:
        """保存测试结果摘要到存储

        Returns:
            带 scheme 前缀的存储路径。
        """
        key = self._build_key(task_id, session_id, "summary")
        data = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        return self._storage.save_bytes(
            data, category=self.CATEGORY, key=key,
            content_type="application/json",
        )

    def load_summary(self, task_id: int, session_id: str) -> Optional[dict]:
        """读取测试结果摘要，不存在返回 None"""
        key = self._build_key(task_id, session_id, "summary")
        path = self._storage.build_path(self.CATEGORY, key)
        if not self._storage.exists(path):
            return None
        raw = self._storage.load_bytes(path)
        return json.loads(raw.decode("utf-8"))

    def summary_exists(self, task_id: int, session_id: str) -> bool:
        """判断测试结果摘要是否已归档"""
        key = self._build_key(task_id, session_id, "summary")
        path = self._storage.build_path(self.CATEGORY, key)
        return self._storage.exists(path)

    def delete_summary(self, task_id: int, session_id: str) -> None:
        """删除测试结果摘要"""
        key = self._build_key(task_id, session_id, "summary")
        path = self._storage.build_path(self.CATEGORY, key)
        self._storage.delete(path)

    def get_presigned_url(self, task_id: int, session_id: str,
                         expires: int = 3600) -> Optional[str]:
        """获取摘要文件的预签名下载 URL"""
        key = self._build_key(task_id, session_id, "summary")
        path = self._storage.build_path(self.CATEGORY, key)
        return self._storage.get_url(path, expires=expires)


# 模块级实例
result_storage = ResultStorage()
