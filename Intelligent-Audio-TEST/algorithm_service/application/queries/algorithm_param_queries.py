# -*- coding: utf-8 -*-
"""参数/映射/维度关联读操作查询（CQRS - Query 侧）。

归属：algorithm_service.application.queries

说明：
- 所有查询均为 frozen dataclass，作为读操作的输入契约。
- 查询只承载"查什么"的意图，不包含业务逻辑。
- 实际处理由 handlers/algorithm_param_handlers.py 的
  AlgorithmParamQueryHandler 完成。
- 查询结果返回 dict / dict 列表（ACL DTO），由调用方或序列化层
  转换为 gRPC 响应。

查询清单：
- 设备/API 参数：GetParamQuery / ListParamsQuery / FindParamByCodeQuery
- 用例参数：GetCaseParamQuery / ListCaseParamsQuery / FindCaseParamByCodeQuery
- 参考参数：GetReferenceParamQuery / ListReferenceParamsQuery
            / FindReferenceParamQuery
- 参数映射：GetMappingQuery / ListMappingsQuery
- 维度关联：GetDimensionRelationQuery / ListDimensionRelationsQuery
            / FindDimensionRelationQuery
- 算法定义/分组（servicer 复用）：ListAlgorithmDefinitionsQuery
            / ListOnlineAlgorithmDefinitionsQuery / FindAlgorithmByTypeQuery
            / CountAlgorithmsInGroupQuery
            / ListAlgorithmDefinitionsForBulkDeleteQuery
            / FindGroupByNameQuery / GetGroupQuery / ListGroupsQuery
            / CountAlgorithmsInGroupForGroupQuery
- 评估维度参数：ListDimensionParamsQuery
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ========== 设备/API 参数查询 ==========

@dataclass(frozen=True)
class GetParamQuery:
    """按 ID 获取设备或 API 参数。

    - param_id: 参数ID
    - param_type_source: 参数来源（device/api，空值时自动探测）
    """

    param_id: int
    param_type_source: str = ""


@dataclass(frozen=True)
class ListParamsQuery:
    """查询参数列表（设备参数 / API 参数）。

    - algorithm_type: 算法类型代码（空值返回全部）
    - param_type: 参数来源（device/api）
    """

    algorithm_type: str = ""
    param_type: str = "device"


@dataclass(frozen=True)
class FindParamByCodeQuery:
    """按 算法/参数代码/方向 查找设备或 API 参数。

    - algorithm_type: 算法类型代码
    - param_code: 参数代码
    - direction: 参数方向（input/output）
    - param_type_source: 参数来源（device/api）
    """

    algorithm_type: str
    param_code: str
    direction: str
    param_type_source: str = "device"


# ========== 用例参数查询 ==========

@dataclass(frozen=True)
class GetCaseParamQuery:
    """按 ID 获取用例专属参数。

    - param_id: 参数ID
    """

    param_id: int


@dataclass(frozen=True)
class ListCaseParamsQuery:
    """查询用例专属参数列表。

    - algorithm_type: 算法类型代码（空值返回全部）
    - scope: 参数适用范围（common/api/e2e，空值不过滤）
    """

    algorithm_type: str = ""
    scope: Optional[str] = None


@dataclass(frozen=True)
class FindCaseParamByCodeQuery:
    """按 算法/参数代码 查找用例参数（可包含软删项）。

    - algorithm_type: 算法类型代码
    - param_code: 参数代码
    - include_deleted: 是否包含已软删项
    """

    algorithm_type: str
    param_code: str
    include_deleted: bool = False


# ========== 参考参数查询 ==========

@dataclass(frozen=True)
class GetReferenceParamQuery:
    """按 ID 获取参考参数。

    - param_id: 参数ID
    """

    param_id: int


@dataclass(frozen=True)
class ListReferenceParamsQuery:
    """查询参考参数列表。

    - algorithm_type: 算法类型代码（空值返回全部）
    """

    algorithm_type: str = ""


@dataclass(frozen=True)
class FindReferenceParamQuery:
    """按 算法/code 查找参考参数。

    - algorithm_type: 算法类型代码
    - code: 参数代码
    """

    algorithm_type: str
    code: str


# ========== 参数映射查询 ==========

@dataclass(frozen=True)
class GetMappingQuery:
    """按 ID 获取参数映射。

    - mapping_id: 映射ID
    """

    mapping_id: int


@dataclass(frozen=True)
class ListMappingsQuery:
    """查询参数映射列表。

    - algorithm_type: 算法类型代码（空值返回全部）
    - source_type: 参数来源过滤（case/reference/device/api）
    - dimension_id: 目标维度ID过滤
    """

    algorithm_type: str = ""
    source_type: Optional[str] = None
    dimension_id: Optional[int] = None


# ========== 维度关联查询 ==========

@dataclass(frozen=True)
class GetDimensionRelationQuery:
    """按 ID 获取维度关联（含软删项）。

    - relation_id: 关联ID
    """

    relation_id: int


@dataclass(frozen=True)
class ListDimensionRelationsQuery:
    """查询算法关联的未删除维度关联列表。

    - algorithm_type: 算法类型代码
    """

    algorithm_type: str


@dataclass(frozen=True)
class FindDimensionRelationQuery:
    """按 算法/维度 查找未删除的维度关联。

    - algorithm_type: 算法类型代码
    - dimension_id: 维度ID
    """

    algorithm_type: str
    dimension_id: int


# ========== 算法定义/分组查询（servicer 复用） ==========

@dataclass(frozen=True)
class ListAlgorithmDefinitionsQuery:
    """查询未删除的算法定义列表（可按 status / group_id 过滤）。

    - status: 算法状态过滤（online/offline）
    - group_id: 分组ID过滤
    """

    status: Optional[str] = None
    group_id: Optional[int] = None


@dataclass(frozen=True)
class ListOnlineAlgorithmDefinitionsQuery:
    """查询在线算法定义列表（按 display_order 排序）。"""


@dataclass(frozen=True)
class FindAlgorithmByTypeQuery:
    """按 type 查询未删除的算法定义。

    - algorithm_type: 算法类型代码
    """

    algorithm_type: str


@dataclass(frozen=True)
class CountAlgorithmsInGroupQuery:
    """统计分组下未删除的算法定义数量。

    - group_id: 分组ID
    """

    group_id: int


@dataclass(frozen=True)
class ListAlgorithmDefinitionsForBulkDeleteQuery:
    """按 type 列表查询未删除的算法定义（供批量删除）。

    - algorithm_types: 算法类型代码列表
    """

    algorithm_types: str = ""


@dataclass(frozen=True)
class FindGroupByNameQuery:
    """按 name 查询未删除的算法分组。

    - name: 分组名称
    """

    name: str


@dataclass(frozen=True)
class GetGroupQuery:
    """按 ID 查询未删除的算法分组。

    - group_id: 分组ID
    """

    group_id: int


@dataclass(frozen=True)
class ListGroupsQuery:
    """查询未删除的算法分组列表（按 display_order、id 排序）。"""


@dataclass(frozen=True)
class CountAlgorithmsInGroupForGroupQuery:
    """统计指定分组下未删除的算法定义数量。

    - group_id: 分组ID
    """

    group_id: int


# ========== 评估维度参数查询 ==========

@dataclass(frozen=True)
class ListDimensionParamsQuery:
    """查询评估维度的参数列表（按 ui_order 排序）。

    - dimension_id: 维度ID
    """

    dimension_id: int
