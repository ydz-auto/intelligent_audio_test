# -*- coding: utf-8 -*-
"""算法定义全量保存（INT-589）——聚合事务 + 乐观锁 + 六类子实体 upsert。

本模块承载 AlgorithmDefinitionRepository.save_full 的全部落库逻辑：

- 同 session 内 upsert 根（algorithm_definitions）+ 六类子实体
  （device/api/case/reference 参数、mappings、associated_dimensions），
  单次 commit/rollback，任一步失败整体回滚；
- 乐观锁：更新路径按 id + deleted=false + updated_at=<expected> 做 CAS
  条件更新，rowcount=0 返回 CONFLICT（并发双写后提交者被拒）；
- 幂等：六张子表按自然键 find-or-upsert、排除软删项。命中活跃行 → 更新；
  命中软删行 → 复活（deleted=False + 更新字段）；未命中 → 插入。同版本
  重放不产生重复子实体，且天然兼容 SQLite（部分唯一索引仅 PG 生效，
  SQLite 全列唯一，软删行不复活会撞唯一约束）；
- 提交集外的活跃行按「全量保存」语义软删（整体替换）。

不直接暴露 ORM：外部只通过 AlgorithmDefinitionRepository.save_full 调用。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared.infrastructure.user_context import get_current_user_id
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDefinition as AlgorithmDefinitionPO,
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
    CaseAlgorithmParam as CaseAlgorithmParamPO,
    AlgorithmReferenceParam as AlgorithmReferenceParamPO,
    ParamMapping as ParamMappingPO,
    AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
)
from algorithm_service.infrastructure.persistence._algorithm_converters import (
    _status_to_po_str,
)
from algorithm_service.domain.value_objects.algorithm_save_code import AlgorithmSaveCode


# ========== 辅助 ==========

def _text_or_json(value: Any) -> Optional[str]:
    """Text 列写值归一：非字符串（dict/list/bool/number）JSON 序列化为文本。

    与读侧 parse_json_or_raw 对称：存 JSON 文本，读时宽松解析。
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _parse_dt(value: Any) -> Optional[datetime]:
    """乐观锁版本解析：ISO 字符串/ datetime → naive datetime。

    服务端 updated_at 为 naive 本地时间（datetime.now），客户端经
    to_dict() 的 isoformat() 往返得到同型字符串；解析后剥除 tzinfo，
    与列值同型比较（SQLite/PG 均按时间等值匹配）。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
        return parsed.replace(tzinfo=None)
    return None


def _split_rows(rows: List[Any], key_of) -> Tuple[Dict[Any, Any], Dict[Any, Any]]:
    """按自然键拆分活跃行/软删行映射。

    Returns:
        (active_by_key, deleted_by_key)：排除/包含软删项的两张查找表。
    """
    active, deleted = {}, {}
    for row in rows:
        key = key_of(row)
        if getattr(row, 'deleted', False):
            deleted[key] = row
        else:
            active[key] = row
    return active, deleted


def _pick_target(active, deleted, key):
    """取 upsert 目标行：活跃命中 / 软删复活 / 新建（返回 None 表示插入）。"""
    if key in active:
        return active[key], False
    if key in deleted:
        return deleted[key], True  # 复活软删行
    return None, False


# ========== 六类子实体 upsert（自然键 find-or-upsert + 提交集外软删） ==========

def _upsert_device_api_params(session, algorithm_type: str, items: List[Dict[str, Any]], po_cls) -> None:
    """设备/API 参数 upsert（自然键：algorithm_type + param_code + direction）。

    INT-1756：本 upsert 的载荷是算法级定义（自然键不含 api_id），只管理
    ``api_id IS NULL`` 的算法级行；API 实例级行由独立写路径维护，不能被
    这里的「提交集外软删」当成未提交行清掉。
    """
    query = session.query(po_cls).filter_by(algorithm_type=algorithm_type)
    if hasattr(po_cls, 'api_id'):
        query = query.filter_by(api_id=None)
    all_rows = query.all()
    active, deleted = _split_rows(
        all_rows, lambda r: (r.param_code, r.direction)
    )
    submitted_keys = set()

    for item in items or []:
        param_code = item.get('param_code') or item.get('code')
        if not param_code:
            raise ValueError('设备/API 参数缺少 param_code')
        direction = item.get('direction') or 'input'
        key = (param_code, direction)
        submitted_keys.add(key)
        row, revive = _pick_target(active, deleted, key)
        if row is None:
            create_kwargs = dict(
                algorithm_type=algorithm_type,
                param_code=param_code,
                param_name=item.get('param_name') or param_code,
                label=item.get('label'),
                param_type=item.get('param_type') or 'text',
                direction=direction,
                required=bool(item.get('required')) or False,
                default_value=_text_or_json(item.get('default_value')),
                validation_rules=_text_or_json(
                    item.get('validation_rules') or item.get('validation')
                ),
                help_text=item.get('help_text'),
                ui_order=item.get('ui_order') or 0,
                hidden=bool(item.get('hidden')) or False,
            )
            # 输出字段取值路径仅 API 参数有该列（INT-1747）；设备参数不带此键
            if 'field_path' in po_cls.__table__.columns:
                create_kwargs['field_path'] = item.get('field_path')
            row = po_cls(**create_kwargs)
            session.add(row)
            continue
        row.deleted = False
        row.param_name = item.get('param_name') or row.param_name
        row.label = item.get('label') if item.get('label') is not None else row.label
        row.param_type = item.get('param_type') or row.param_type
        row.required = bool(item.get('required')) or False
        if item.get('default_value') is not None:
            row.default_value = _text_or_json(item.get('default_value'))
        if item.get('validation_rules') is not None or item.get('validation') is not None:
            row.validation_rules = _text_or_json(
                item.get('validation_rules') or item.get('validation')
            )
        if item.get('help_text') is not None:
            row.help_text = item.get('help_text')
        row.ui_order = item.get('ui_order') if item.get('ui_order') is not None else row.ui_order
        row.hidden = bool(item.get('hidden')) or False
        if 'field_path' in po_cls.__table__.columns and item.get('field_path') is not None:
            row.field_path = item.get('field_path')
        if revive:
            row.updated_at = datetime.now()

    for r in all_rows:
        if not r.deleted and (r.param_code, r.direction) not in submitted_keys:
            r.deleted = True


def _upsert_case_params(session, algorithm_type: str, items: List[Dict[str, Any]]) -> None:
    """用例参数 upsert（自然键：algorithm_type + param_code）。"""
    all_rows = session.query(CaseAlgorithmParamPO).filter_by(
        algorithm_type=algorithm_type
    ).all()
    active, deleted = _split_rows(all_rows, lambda r: r.param_code)
    submitted_keys = set()

    for item in items or []:
        param_code = item.get('param_code')
        if not param_code:
            raise ValueError('用例参数缺少 param_code')
        submitted_keys.add(param_code)
        row, revive = _pick_target(active, deleted, param_code)
        if row is None:
            row = CaseAlgorithmParamPO(
                algorithm_type=algorithm_type,
                param_code=param_code,
                param_name=item.get('param_name') or param_code,
                label=item.get('label'),
                param_type=item.get('param_type') or 'text',
                required=bool(item.get('required')) or False,
                default_value=_text_or_json(item.get('default_value')),
                help_text=item.get('help_text'),
                ui_order=item.get('ui_order') or 0,
                hidden=bool(item.get('hidden')) or False,
                scope=item.get('scope') or 'common',
                min_value=item.get('min_value'),
                max_value=item.get('max_value'),
                step=item.get('step'),
                unit=item.get('unit'),
                annotation_code=item.get('annotation_code'),
                field_path=item.get('field_path'),
            )
            session.add(row)
            continue
        row.deleted = False
        row.param_name = item.get('param_name') or row.param_name
        row.label = item.get('label') if item.get('label') is not None else row.label
        row.param_type = item.get('param_type') or row.param_type
        row.required = bool(item.get('required')) or False
        if item.get('default_value') is not None:
            row.default_value = _text_or_json(item.get('default_value'))
        if item.get('help_text') is not None:
            row.help_text = item.get('help_text')
        row.ui_order = item.get('ui_order') if item.get('ui_order') is not None else row.ui_order
        row.hidden = bool(item.get('hidden')) or False
        if item.get('scope') is not None:
            row.scope = item.get('scope')
        row.min_value = item.get('min_value') if item.get('min_value') is not None else row.min_value
        row.max_value = item.get('max_value') if item.get('max_value') is not None else row.max_value
        row.step = item.get('step') if item.get('step') is not None else row.step
        if item.get('unit') is not None:
            row.unit = item.get('unit')
        if item.get('annotation_code') is not None:
            row.annotation_code = item.get('annotation_code')
        if item.get('field_path') is not None:
            row.field_path = item.get('field_path')
        if revive:
            row.updated_at = datetime.now()

    for r in all_rows:
        if not r.deleted and r.param_code not in submitted_keys:
            r.deleted = True


def _upsert_reference_params(session, algorithm_type: str, items: List[Dict[str, Any]]) -> None:
    """参考参数 upsert（自然键：algorithm_type + code）。"""
    all_rows = session.query(AlgorithmReferenceParamPO).filter_by(
        algorithm_type=algorithm_type
    ).all()
    active, deleted = _split_rows(all_rows, lambda r: r.code)
    submitted_keys = set()

    for item in items or []:
        code = item.get('code')
        if not code:
            raise ValueError('参考参数缺少 code')
        submitted_keys.add(code)
        row, revive = _pick_target(active, deleted, code)
        if row is None:
            row = AlgorithmReferenceParamPO(
                algorithm_type=algorithm_type,
                code=code,
                name=item.get('name') or code,
                param_type=item.get('param_type') or item.get('type') or 'text',
                annotation_code=item.get('annotation_code'),
                annotation_format=item.get('annotation_format'),
                field_path=item.get('field_path'),
                merge_mode=item.get('merge_mode') or 'join',
                help_text=item.get('help_text') or '',
            )
            session.add(row)
            continue
        row.deleted = False
        row.name = item.get('name') if item.get('name') is not None else row.name
        if item.get('param_type') is not None or item.get('type') is not None:
            row.param_type = item.get('param_type') or item.get('type')
        if item.get('annotation_code') is not None:
            row.annotation_code = item.get('annotation_code')
        if item.get('annotation_format') is not None:
            row.annotation_format = item.get('annotation_format')
        if item.get('field_path') is not None:
            row.field_path = item.get('field_path')
        if item.get('merge_mode') is not None:
            row.merge_mode = item.get('merge_mode')
        if item.get('help_text') is not None:
            row.help_text = item.get('help_text')
        if revive:
            row.updated_at = datetime.now()

    for r in all_rows:
        if not r.deleted and r.code not in submitted_keys:
            r.deleted = True


def _upsert_mappings(session, algorithm_type: str, items: List[Dict[str, Any]]) -> None:
    """参数映射 upsert（自然键：algorithm_type + source + source_param + dimension_id）。

    兼容 payload 两种形态：平铺列表（item 自带 source）或
    按 source 分组的 dict（{"device": [...]}，已由 handler 归一为列表）。

    INT-1756：同 _upsert_device_api_params，只管理算法级行（api_id IS NULL），
    API 实例级映射不受算法定义整份保存影响。
    """
    all_rows = session.query(ParamMappingPO).filter_by(
        algorithm_type=algorithm_type, api_id=None
    ).all()
    active, deleted = _split_rows(
        all_rows, lambda r: (r.source, r.source_param, r.dimension_id)
    )
    submitted_keys = set()

    for item in items or []:
        source = item.get('source') or item.get('source_type')
        if not source:
            raise ValueError('参数映射缺少 source')
        source_param = item.get('source_param')
        if not source_param:
            raise ValueError('参数映射缺少 source_param')
        dimension_id = item.get('dimension_id')
        if dimension_id is not None:
            try:
                dimension_id = int(dimension_id)
            except (TypeError, ValueError):
                dimension_id = None
        key = (source, source_param, dimension_id)
        submitted_keys.add(key)
        row, revive = _pick_target(active, deleted, key)
        if row is None:
            row = ParamMappingPO(
                algorithm_type=algorithm_type,
                source=source,
                source_param=source_param,
                source_direction=item.get('source_direction') or 'output',
                dimension_id=dimension_id,
                target_param=item.get('target_param') or '',
                transform_type=item.get('transform_type') or 'none',
            )
            session.add(row)
            continue
        row.deleted = False
        row.source_direction = item.get('source_direction') or row.source_direction
        if item.get('target_param') is not None:
            row.target_param = item.get('target_param')
        if item.get('transform_type') is not None:
            row.transform_type = item.get('transform_type')
        if revive:
            row.updated_at = datetime.now()

    for r in all_rows:
        if not r.deleted and (
            r.source, r.source_param, r.dimension_id
        ) not in submitted_keys:
            r.deleted = True


def _upsert_dimension_relations(session, algorithm_type: str, items: List[Dict[str, Any]]) -> None:
    """维度关联 upsert（自然键：algorithm_type + dimension_id，即 associated_dimensions）。"""
    all_rows = session.query(AlgorithmDimensionRelationPO).filter_by(
        algorithm_type=algorithm_type
    ).all()
    active, deleted = _split_rows(all_rows, lambda r: r.dimension_id)
    submitted_keys = set()

    for item in items or []:
        dimension_id = item.get('dimension_id')
        if dimension_id is None:
            raise ValueError('associated_dimensions 缺少 dimension_id')
        try:
            dimension_id = int(dimension_id)
        except (TypeError, ValueError):
            raise ValueError(f'associated_dimensions 的 dimension_id 非法: {dimension_id}')
        submitted_keys.add(dimension_id)
        row, revive = _pick_target(active, deleted, dimension_id)
        if row is None:
            row = AlgorithmDimensionRelationPO(
                algorithm_type=algorithm_type,
                dimension_id=dimension_id,
                is_default=bool(item.get('is_default')) or False,
                weight=item.get('weight') if item.get('weight') is not None else 1.0,
            )
            session.add(row)
            continue
        row.deleted = False
        row.is_default = bool(item.get('is_default')) or row.is_default
        if item.get('weight') is not None:
            row.weight = item.get('weight')
        if revive:
            row.updated_at = datetime.now()

    for r in all_rows:
        if not r.deleted and r.dimension_id not in submitted_keys:
            r.deleted = True


def _upsert_all_sub_entities(session, algorithm_type: str, sub_entities: Dict[str, Any]) -> None:
    """按固定顺序 upsert 六类子实体（任一步失败由调用方整体回滚）。"""
    _upsert_device_api_params(session, algorithm_type, sub_entities.get('device_params'), AlgorithmDeviceParamPO)
    _upsert_device_api_params(session, algorithm_type, sub_entities.get('api_params'), AlgorithmApiParamPO)
    _upsert_case_params(session, algorithm_type, sub_entities.get('case_params'))
    _upsert_reference_params(session, algorithm_type, sub_entities.get('reference_params'))
    _upsert_mappings(session, algorithm_type, sub_entities.get('mappings'))
    _upsert_dimension_relations(session, algorithm_type, sub_entities.get('associated_dimensions'))


def _apply_root_fields(po, aggregate) -> None:
    """聚合根基础字段 → PO（与 _apply_definition_to_po 对齐）。"""
    po.type = aggregate.algorithm_type
    po.name = aggregate.name
    po.group_id = aggregate.group_id
    po.description = aggregate.description
    po.status = _status_to_po_str(aggregate.status)
    if aggregate.icon is not None:
        po.icon = aggregate.icon
    po.display_order = aggregate.display_order
    po.deleted = False


def save_full(
    session,
    aggregate,
    sub_entities: Dict[str, Any],
    expected_updated_at: Optional[str] = None,
) -> str:
    """全量保存（供 AlgorithmDefinitionRepository.save_full 委托）。

    Returns:
        AlgorithmSaveCode 字符串（SAVED / OK / CONFLICT）。
        异常路径抛 ValueError 由调用方映射 VALIDATION_FAILED。
    """
    is_create = not aggregate.id
    if is_create:
        # 新建：algorithm_type 唯一约束冲突在 DB 层抛，先显式查一次给出明确报错
        existing = session.query(AlgorithmDefinitionPO).filter_by(
            type=aggregate.algorithm_type, deleted=False
        ).first()
        if existing is not None:
            raise ValueError(
                f"algorithm_type '{aggregate.algorithm_type}' 已存在，无法新建"
            )
        po = AlgorithmDefinitionPO(
            type=aggregate.algorithm_type,
            name=aggregate.name,
            group_id=aggregate.group_id,
            description=aggregate.description,
            status=_status_to_po_str(aggregate.status),
            icon=aggregate.icon,
            display_order=aggregate.display_order,
            deleted=False,
            created_by_user_id=get_current_user_id(),
        )
        session.add(po)
        session.flush()
        aggregate.id = po.id
        _upsert_all_sub_entities(session, aggregate.algorithm_type, sub_entities)
        session.commit()
        return AlgorithmSaveCode.SAVED.value

    # 更新路径：CAS 条件更新（id + deleted=false + updated_at=<expected>）
    expected_dt = _parse_dt(expected_updated_at)
    update_values = {
        'type': aggregate.algorithm_type,
        'name': aggregate.name,
        'group_id': aggregate.group_id,
        'description': aggregate.description,
        'status': _status_to_po_str(aggregate.status),
        'display_order': aggregate.display_order,
        'deleted': False,
        'updated_at': datetime.now(),
        'updated_by_user_id': get_current_user_id(),
    }
    if aggregate.icon is not None:
        update_values['icon'] = aggregate.icon
    query = session.query(AlgorithmDefinitionPO).filter_by(
        id=aggregate.id, deleted=False
    )
    if expected_dt is not None:
        query = query.filter(AlgorithmDefinitionPO.updated_at == expected_dt)
    updated = query.update(update_values, synchronize_session=False)
    if updated == 0:
        # 行不存在或版本过期 → 乐观锁冲突
        session.rollback()
        return AlgorithmSaveCode.CONFLICT.value

    _upsert_all_sub_entities(session, aggregate.algorithm_type, sub_entities)
    session.commit()
    return AlgorithmSaveCode.OK.value
