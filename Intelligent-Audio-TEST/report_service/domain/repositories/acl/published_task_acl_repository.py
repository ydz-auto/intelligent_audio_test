# -*- coding: utf-8 -*-
"""task_service.PublishedTaskConfigService 跨域 ACL 仓储接口。

Benchmark 排行实测轨（platform_test）数据源：report_service 通过 gRPC 只读
访问 task_service 的已发布任务（benchmark=true 且 status=published）及其
冻结报告快照（report_snapshot，含 summary.dimensionValues 平台实测得分）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PublishedTaskAclRepository(ABC):
    """task_service.PublishedTaskConfigService 跨域只读查询接口。"""

    @abstractmethod
    def list_benchmark_published_tasks(self) -> List[Dict[str, Any]]:
        """列出全部参与 Benchmark 的已发布任务（status=published, benchmark=true）。

        Returns:
            已发布任务列表项 dict 列表（snake_case 契约：id/version/benchmark/
            name/task_group_id/snapshot_config 等）
        """
        ...

    @abstractmethod
    def get_published_task_detail(self, published_task_id: int) -> Optional[Dict[str, Any]]:
        """查询单个已发布任务详情（含 snapshot_config 与 report_snapshot）。"""
        ...
