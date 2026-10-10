# -*- coding: utf-8 -*-
"""查询对象 — 应用层只读用例输入，纯数据载体。"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetAPITestStatusQuery:
    """查询 API 测试任务状态"""

    task_id: int


@dataclass(frozen=True)
class GetAPIQuery:
    """查询单个 API 配置详情

    通过 repository 加载 APIAggregate 聚合根。
    """

    api_id: int


@dataclass(frozen=True)
class ListAPIsQuery:
    """分页查询 API 配置列表

    通过 repository 分页查询 APIAggregate 聚合根列表。
    """

    page: int = 1
    per_page: int = 10
    keyword: Optional[str] = None
    status: Optional[str] = None
    algorithm_type: Optional[str] = None


# ==================== UC-0902 API RMS→SPL 映射查询 ====================

@dataclass(frozen=True)
class GetRmsSplMappingQuery:
    """查询单个 RMS→SPL 映射详情"""

    mapping_id: int


@dataclass(frozen=True)
class ListRmsSplMappingsQuery:
    """分页查询 RMS→SPL 映射列表（可按 API / 校准状态过滤）"""

    page: int = 1
    per_page: int = 10
    api_id: Optional[int] = None
    calibration_status: Optional[str] = None


@dataclass(frozen=True)
class GetRmsSplMappingsByApiQuery:
    """按被测 API 查询全部映射（API 编辑页关联选择，UC-0901 步骤7）"""

    api_id: int


@dataclass(frozen=True)
class GetSplGainQuery:
    """执行期查询：目标 SPL → 推送线性增益（UC-0902 验收 spl_to_gain(api_id, spl)）

    无映射时返回线性近似 gain = 10^((target_spl - 65) / 20)。
    """

    api_id: int
    target_spl: float
