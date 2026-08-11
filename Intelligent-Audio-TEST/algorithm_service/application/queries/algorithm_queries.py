# -*- coding: utf-8 -*-
"""算法读操作查询（CQRS - Query 侧）。

归属：algorithm_service.application.queries

说明：
- 所有查询均为 frozen dataclass，作为读操作的输入契约。
- 查询只承载"查什么"的意图，不包含业务逻辑。
- 实际处理由 handlers/algorithm_handlers.py 的 AlgorithmQueryHandler 完成。
- 查询结果返回领域聚合根/快照，由调用方或序列化层转换为 DTO。

查询清单：
- 算法分组：GetAlgorithmGroupQuery / ListAlgorithmGroupsQuery
- 算法定义：GetAlgorithmDefinitionQuery / ListAlgorithmDefinitionsByGroupQuery
            / GetAlgorithmDefinitionByTypeQuery / ListActiveAlgorithmDefinitionsQuery
"""
from __future__ import annotations

from dataclasses import dataclass


# ========== 算法分组查询 ==========

@dataclass(frozen=True)
class GetAlgorithmGroupQuery:
    """按 ID 查询算法分组。

    - id: 分组ID
    """

    id: int


@dataclass(frozen=True)
class ListAlgorithmGroupsQuery:
    """分页查询算法分组列表。

    - page: 页码（从 1 开始）
    - page_size: 每页条数
    """

    page: int = 1
    page_size: int = 20


# ========== 算法定义查询 ==========

@dataclass(frozen=True)
class GetAlgorithmDefinitionQuery:
    """按 ID 查询算法定义。

    - id: 算法定义ID
    """

    id: int


@dataclass(frozen=True)
class ListAlgorithmDefinitionsByGroupQuery:
    """按分组 ID 查询算法定义列表。

    - group_id: 分组ID
    """

    group_id: int


@dataclass(frozen=True)
class GetAlgorithmDefinitionByTypeQuery:
    """按算法类型代码查询算法定义。

    - algorithm_type: 算法类型代码
    """

    algorithm_type: str


@dataclass(frozen=True)
class ListActiveAlgorithmDefinitionsQuery:
    """查询全部上线状态的算法定义。"""
