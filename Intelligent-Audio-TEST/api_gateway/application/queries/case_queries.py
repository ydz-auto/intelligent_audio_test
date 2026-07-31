"""api_gateway 应用层 —— 查询（读操作）

CQRS Query 侧：所有读操作直接查本地 DB，不走 gRPC。

包括：
- 测试用例查询（列表、详情、统计）
- 任务查询
- 报告查询
- 音频查询
- 首页统计
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class GetTestCaseQuery:
    """获取单个测试用例"""
    tc_id: str


@dataclass
class ListTestCasesQuery:
    """测试用例列表"""
    page: int = 1
    page_size: int = 20
    group_id: Optional[str] = None
    keyword: Optional[str] = None
    tag_ids: Optional[List[str]] = None


@dataclass
class GetTestCaseStatsQuery:
    """测试用例统计"""
    group_id: Optional[str] = None


@dataclass
class GetTaskQuery:
    """获取任务"""
    task_id: str


@dataclass
class ListTasksQuery:
    """任务列表"""
    page: int = 1
    page_size: int = 20
    status: Optional[str] = None
    task_type: Optional[str] = None


@dataclass
class GetReportQuery:
    """获取报告"""
    report_id: str


@dataclass
class ListReportsQuery:
    """报告列表"""
    page: int = 1
    page_size: int = 20
    task_id: Optional[str] = None


@dataclass
class GetAudioQuery:
    """获取音频"""
    audio_id: str


@dataclass
class ListAudiosQuery:
    """音频列表"""
    page: int = 1
    page_size: int = 20
    keyword: Optional[str] = None


@dataclass
class GetHomeStatsQuery:
    """首页统计"""
    pass
