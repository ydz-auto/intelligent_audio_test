"""api_gateway 领域层 —— 实体

api_gateway 作为胖网关，其领域实体主要是：
- TestCase 聚合根（CRUD 代理）
- Report 聚合根（报告生成/查询）
- 代理实体（通过 gRPC 转发到各服务）
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class CaseStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    ARCHIVED = 'archived'


@dataclass
class TestCaseEntity:
    """测试用例聚合根（网关侧代理）
    
    写操作通过 gRPC 转发到 task_service / e2e_test_service，
    读操作直接查本地 DB。
    """
    id: str
    name: str
    description: str = ''
    group_id: Optional[str] = None
    algorithm_type: str = 'default'
    status: CaseStatus = CaseStatus.ACTIVE
    config: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def can_modify(self) -> bool:
        """是否可修改"""
        return self.status != CaseStatus.ARCHIVED

    def archive(self):
        """归档"""
        self.status = CaseStatus.ARCHIVED


@dataclass
class ReportEntity:
    """报告聚合根（网关侧代理）
    
    报告生成通过 gRPC 转发到 task_service，
    查询直接读本地 DB。
    """
    id: str
    task_id: str
    name: str
    type: str = 'task'
    status: str = 'pending'
    created_at: Optional[datetime] = None

    def is_generating(self) -> bool:
        return self.status == 'generating'

    def mark_completed(self):
        self.status = 'completed'

    def mark_failed(self):
        self.status = 'failed'
