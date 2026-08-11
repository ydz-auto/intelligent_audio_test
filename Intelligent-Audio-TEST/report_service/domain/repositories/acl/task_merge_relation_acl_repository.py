# -*- coding: utf-8 -*-
"""任务合并关系跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from report_service.domain.dto import TaskMergeRelationDTO


class TaskMergeRelationAclRepository(ABC):
    """task_service.TaskMergeRelation 跨域只读查询接口。"""

    @abstractmethod
    def get_task_merge_relations(self, merged_task_id) -> List[TaskMergeRelationDTO]:
        """按 merged_task_id 查询合并关系。"""
        ...

    @abstractmethod
    def get_task_merge_relations_by_source(self, source_task_id) -> List[TaskMergeRelationDTO]:
        """按 source_task_id 查询合并关系。"""
        ...
