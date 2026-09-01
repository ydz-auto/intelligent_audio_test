# -*- coding: utf-8 -*-
"""算法仓储 PO ↔ Entity 转换层。

从 algorithm_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- _parse_json_value / _status_from_po / _status_to_po_str: 基础转换辅助
- _group_po_to_entity / _definition_po_to_entity: PO → Entity 聚合根转换
- _param_po_to_entity: 参数 PO → 参数实体转换（通过 param_kind 区分类别）
- _apply_group_to_po / _apply_definition_to_po: Entity → PO 可写字段写回

转换规则详见 algorithm_repository.py 模块 docstring。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from algorithm_service.infrastructure.persistence.models import (
    AlgorithmGroup as AlgorithmGroupPO,
    AlgorithmDefinition as AlgorithmDefinitionPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
    AlgorithmReferenceParam as AlgorithmReferenceParamPO,
)
from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate
from algorithm_service.domain.entities.algorithm_definition import (
    AlgorithmDefinitionAggregate,
    AlgorithmStatus,
)
from algorithm_service.domain.entities.algorithm_param import (
    AlgorithmParamEntity,
    AlgorithmDimensionRelationEntity,
)


# ========== 基础转换辅助 ==========

def _parse_json_value(raw):
    """解析 PO 中 JSON 文本字段为 Python 对象（空值返回 None）。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _status_from_po(po_status: Optional[str]) -> AlgorithmStatus:
    """PO status 字符串 → AlgorithmStatus 枚举。

    兼容历史数据：online → active，offline → deprecated，draft → draft。
    """
    if po_status == 'online':
        return AlgorithmStatus.ACTIVE
    if po_status == 'offline':
        return AlgorithmStatus.DEPRECATED
    if po_status == 'draft':
        return AlgorithmStatus.DRAFT
    # 容错：未知值按草稿处理
    return AlgorithmStatus.DRAFT


def _status_to_po_str(status: AlgorithmStatus) -> str:
    """AlgorithmStatus 枚举 → PO status 字符串（写回 PO）。"""
    if status == AlgorithmStatus.ACTIVE:
        return 'online'
    if status == AlgorithmStatus.DEPRECATED:
        return 'offline'
    return 'draft'


# ========== PO → Entity 转换 ==========

def _group_po_to_entity(po: AlgorithmGroupPO) -> AlgorithmGroupAggregate:
    """AlgorithmGroup PO → AlgorithmGroupAggregate 聚合根。

    说明：PO 表 algorithm_groups 无 algorithm_type 列，
    该字段在实体上加载为 None（分组本身不持有算法类型，
    由其下算法定义的 algorithm_type 间接关联）。
    """
    return AlgorithmGroupAggregate(
        id=po.id,
        name=po.name,
        description=po.description,
        algorithm_type=None,
        deleted=po.deleted or False,
    )


def _param_po_to_entity(po, definition_id: int = 0) -> AlgorithmParamEntity:
    """算法参数 PO → AlgorithmParamEntity 实体。

    兼容三类参数 PO（通过 isinstance 区分）：
    - AlgorithmDeviceParam: param_code / required / ui_order / default_value
    - AlgorithmApiParam:    param_code / required / ui_order / default_value
    - AlgorithmReferenceParam: code（无 required / ui_order / default_value 列）

    通过 param_kind 标识参数类别，供领域层区分来源。
    """
    if isinstance(po, AlgorithmApiParamPO):
        # API 参数
        param_kind = 'api'
        param_name = po.param_code
        is_required = po.required or False
        sort_order = po.ui_order or 0
        default_value = _parse_json_value(po.default_value)
    elif isinstance(po, AlgorithmReferenceParamPO):
        # 参考参数（字段结构与 device/api 不同）
        param_kind = 'reference'
        param_name = po.code
        is_required = False  # reference 参数无 required 列
        sort_order = 0       # reference 参数无 ui_order 列
        default_value = None
    else:
        # 设备参数（默认分支）
        param_kind = 'device'
        param_name = po.param_code
        is_required = po.required or False
        sort_order = po.ui_order or 0
        default_value = _parse_json_value(po.default_value)

    return AlgorithmParamEntity(
        id=po.id,
        definition_id=definition_id,
        param_name=param_name or '',
        param_type=po.param_type,
        default_value=default_value,
        is_required=is_required,
        sort_order=sort_order,
        param_kind=param_kind,
    )


def _definition_po_to_entity(po: AlgorithmDefinitionPO) -> AlgorithmDefinitionAggregate:
    """AlgorithmDefinition PO → AlgorithmDefinitionAggregate 聚合根。

    聚合内加载未删除的子实体：
    - device_params: 设备参数列表
    - api_params: API 参数列表
    - dimension_relations: 算法-维度关联列表
    - reference_params: PO 无直接 relationship，加载为空（如需可单独查询）
    """
    # 设备参数：过滤已删除项，回填 definition_id
    device_params = [
        _param_po_to_entity(p, definition_id=po.id)
        for p in (po.device_params or [])
        if not getattr(p, 'deleted', False)
    ]
    # API 参数：同上
    api_params = [
        _param_po_to_entity(p, definition_id=po.id)
        for p in (po.api_params or [])
        if not getattr(p, 'deleted', False)
    ]
    # 算法-维度关联：PO.is_default → Entity.mapping_type
    dimension_relations = [
        AlgorithmDimensionRelationEntity(
            id=r.id,
            definition_id=po.id,
            dimension_id=r.dimension_id,
            mapping_type='default' if r.is_default else 'normal',
        )
        for r in (po.dimension_relations or [])
        if not getattr(r, 'deleted', False)
    ]

    return AlgorithmDefinitionAggregate(
        id=po.id,
        group_id=po.group_id,
        name=po.name,
        algorithm_type=po.type,
        description=po.description,
        version='1.0.0',  # PO 无 version 列，使用实体默认值
        status=_status_from_po(po.status),
        device_params=device_params,
        api_params=api_params,
        reference_params=[],  # PO 无直接关联关系，单独加载
        dimension_relations=dimension_relations,
        deleted=po.deleted or False,
    )


# ========== Entity → PO 字段写回 ==========

def _apply_group_to_po(aggregate: AlgorithmGroupAggregate, po: AlgorithmGroupPO) -> None:
    """将 AlgorithmGroupAggregate 可写字段映射回 AlgorithmGroup PO。

    说明：PO 表无 algorithm_type 列，不写回该字段。
    只更新可变字段，不覆盖 id / created_at 等不可变元数据。
    """
    po.name = aggregate.name
    po.description = aggregate.description
    po.deleted = aggregate.deleted
    po.updated_at = datetime.now()


def _apply_definition_to_po(aggregate: AlgorithmDefinitionAggregate, po: AlgorithmDefinitionPO) -> None:
    """将 AlgorithmDefinitionAggregate 可写字段映射回 AlgorithmDefinition PO。

    说明：
    - PO 无 version 列，不写回该字段
    - status 做 AlgorithmStatus → PO 字符串映射
      （active→online / deprecated→offline / draft→draft）
    - 子实体（device_params / api_params / dimension_relations）的变更
      由调用方通过相应子仓储维护，本方法只同步聚合根自身字段
    """
    po.type = aggregate.algorithm_type
    po.name = aggregate.name
    po.group_id = aggregate.group_id
    po.description = aggregate.description
    po.status = _status_to_po_str(aggregate.status)
    po.deleted = aggregate.deleted
    po.updated_at = datetime.now()
