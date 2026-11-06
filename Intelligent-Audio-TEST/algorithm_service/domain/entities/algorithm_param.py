# -*- coding: utf-8 -*-
"""算法参数实体集合。

归属：algorithm_service.domain.entities
对应 PO：AlgorithmDeviceParam / AlgorithmApiParam / AlgorithmReferenceParam
        / AlgorithmDimensionRelation / CaseAlgorithmParam / ParamMapping

说明：
- 本模块为纯领域层 dataclass，不依赖 SQLAlchemy / db.Model。
- AlgorithmParamEntity 为通用参数实体，覆盖 device/api/reference 三类参数
  （通过 param_kind 标识），避免为三张结构高度相似的表重复定义实体。
- 其余实体（维度关联、用例参数、参数映射）字段与 PO 对齐但去除审计列。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AlgorithmParamEntity:
    """通用算法参数实体。

    覆盖 device / api / reference 三类参数：
    - id: 参数ID
    - definition_id: 所属算法定义ID
    - param_name: 参数代码（param_code）
    - param_type: 参数类型（text/audio_stream/audio_file/json 等）
    - default_value: 默认值
    - is_required: 是否必填
    - sort_order: 界面排序
    - param_kind: 参数类别（device / api / reference）
    """

    id: int
    definition_id: int
    param_name: str
    param_type: str
    default_value: Any = None
    is_required: bool = False
    sort_order: int = 0
    param_kind: str = "device"


@dataclass
class AlgorithmDimensionRelationEntity:
    """算法与评估维度关联实体。

    - id: 关联ID
    - definition_id: 所属算法定义ID
    - dimension_id: 关联评估维度ID（跨域，仅持有ID）
    - mapping_type: 关联类型（默认 default）
    """

    id: int
    definition_id: int
    dimension_id: int
    mapping_type: str = "default"


@dataclass
class CaseAlgorithmParamEntity:
    """用例专属参数实体。

    - id: 参数ID
    - case_id: 用例ID
    - algorithm_type: 关联算法类型代码
    - params: 参数集合（键值对）
    """

    id: int
    case_id: int
    algorithm_type: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParamMappingEntity:
    """参数映射实体（源参数 → 目标维度参数）。

    - id: 映射ID
    - definition_id: 所属算法定义ID
    - source_field: 源字段代码
    - target_field: 目标字段代码
    - transform_rule: 转换规则（none/uppercase/lowercase/json_parse/base64）
    """

    id: int
    definition_id: int
    source_field: str
    target_field: str
    transform_rule: str = "none"
