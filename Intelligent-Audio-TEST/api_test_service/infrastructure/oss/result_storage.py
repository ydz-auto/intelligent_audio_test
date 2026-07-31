# -*- coding: utf-8 -*-
"""API 测试结果 OSS 存储 — 封装结果归档与读取，基于 shared.clients.oss_client.OSSClient。

OSS bucket 命名约定：
  case-result/  - 设备采集结果
  reports/      - 报告文件
  archives/     - 归档文件

本服务将 API 测试会话的最终结果（JSON 摘要 + 可选明细）归档至 OSS。
"""
import json
from typing import Optional

from shared.clients.oss_client import OSSClient


class ResultStorage:
    """API 测试结果 OSS 存储

    职责：
    - 将会话结果摘要上传到 OSS（bucket: archives/）
    - 读取已归档的结果
    - 删除归档结果（清理）

    所有路径前缀统一为 `api-test-results/<task_id>/`。
    """

    CATEGORY = "archives"

    def __init__(self, client: Optional[OSSClient] = None):
        # OSSClient 为单例，延迟注入便于测试时替换
        self._client = client or OSSClient()

    @staticmethod
    def _build_key(task_id: int, session_id: str, name: str = "summary") -> str:
        return f"api-test-results/{task_id}/{session_id}/{name}.json"

    def save_summary(self, task_id: int, session_id: str,
                     summary: dict) -> str:
        """保存测试结果摘要到 OSS

        Returns:
            OSS 对象 key（不含 bucket）。
        """
        key = self._build_key(task_id, session_id, "summary")
        data = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        self._client.upload_bytes(
            data, category=self.CATEGORY, key=key,
            content_type="application/json",
        )
        return key

    def load_summary(self, task_id: int, session_id: str) -> Optional[dict]:
        """读取测试结果摘要，不存在返回 None"""
        key = self._build_key(task_id, session_id, "summary")
        if not self._client.exists(category=self.CATEGORY, key=key):
            return None
        raw = self._client.download_bytes(category=self.CATEGORY, key=key)
        return json.loads(raw.decode("utf-8"))

    def summary_exists(self, task_id: int, session_id: str) -> bool:
        """判断测试结果摘要是否已归档"""
        key = self._build_key(task_id, session_id, "summary")
        return self._client.exists(category=self.CATEGORY, key=key)

    def delete_summary(self, task_id: int, session_id: str) -> None:
        """删除测试结果摘要"""
        key = self._build_key(task_id, session_id, "summary")
        self._client.delete_object(category=self.CATEGORY, key=key)

    def get_presigned_url(self, task_id: int, session_id: str,
                         expires: int = 3600) -> str:
        """获取摘要文件的预签名下载 URL"""
        key = self._build_key(task_id, session_id, "summary")
        return self._client.get_presigned_url(
            category=self.CATEGORY, key=key, expires=expires,
        )


# 模块级实例
result_storage = ResultStorage()
