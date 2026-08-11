# -*- coding: utf-8 -*-
"""TestCase 领域事件"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestCaseCreated:
    """用例创建事件"""
    case_id: str
    name: str
    algorithm_type: str
    test_type: str = "api"


@dataclass
class TestCaseUpdated:
    """用例更新事件"""
    case_id: str
    updated_fields: list = field(default_factory=list)


@dataclass
class TestCaseDeleted:
    """用例删除事件"""
    case_id: str


@dataclass
class TestCaseBatchAction:
    """用例批量操作事件"""
    case_ids: list
    action: str  # delete / move_group / etc
