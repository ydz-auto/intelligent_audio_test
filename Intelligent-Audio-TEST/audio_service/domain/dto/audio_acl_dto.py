# -*- coding: utf-8 -*-
"""audio_service ACL DTO 定义。

供 audio_service/infrastructure/acl 下的仓储使用，
将 gRPC 返回的 dict 转换为 dataclass DTO。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TestCaseDTO:
    """测试用例 DTO（用于 check_audio_in_testcases 返回的 tc）

    差异#2 收尾：用例不再承载 test_type/执行口径，DTO 只保留数据本身。
    """
    id: Optional[int] = None
    name: Optional[str] = None
    config: Any = None


@dataclass
class TaskItemDTO:
    """任务列表项 DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    config: Any = None
