# -*- coding: utf-8 -*-
"""算法参数/映射/维度关联仓储实现 — 返回 dict（ACL DTO），做 PO ↔ dict 转换。

归属：algorithm_service.infrastructure.persistence

与 algorithm_repository.py 的区别：
- algorithm_repository.py: 旧式 DDD 仓储，返回领域聚合根（Aggregate），
  供 group/definition 领域服务用，做 PO ↔ Entity 显式转换。
- param_repository.py（本文件）: ACL 仓储，返回 dict，
  供 param/mapping/relation 命令/查询 handler 用，隔离 PO 与应用层。

PO ↔ dict 转换规则：
- AlgorithmDeviceParam / AlgorithmApiParam PO → dict（含 default_value/validation JSON 解析）
- AlgorithmReferenceParam PO → dict（type 字段重命名）
- CaseAlgorithmParam PO → dict（含 scope/min/max/step/unit 等扩展字段）
- ParamMapping PO → dict（source/source_param/target_param/transform_type）
- AlgorithmDimensionRelation PO → dict（is_default/weight）
- 所有 dict 通过 _po_to_dict(po) 生成：优先调用 po.to_dict()，
  否则回退到遍历 __table__.columns（与 servicers.py 中的 _po_to_dict 一致）

字段映射注意事项：
- AlgorithmReferenceParam PO.param_type → dict.type（to_dict 已映射）
- ParamMapping PO.source ← data.source_type（servicer 用 source_type 传参，
  PO 字段名为 source，映射时做转换）
- AlgorithmDimensionRelation 软删除按 algorithm_type 批量 update deleted=True

模块组织（原单文件 771 行，按职责拆分为多个实现模块，本文件保持对外导入路径稳定）：
- _param_converters.py: _po_to_dict / _resolve_param_model 转换辅助（模块私有）
- _algorithm_param_repository.py: AlgorithmParamRepository（设备/API 参数）
- _case_reference_param_repositories.py: 用例参数/参考参数仓储
- _mapping_relation_repositories.py: 参数映射/维度关联仓储

兼容性约定：
- 所有历史导入路径与符号保持不变（类与模块级单例）
- 模块私有辅助函数（_po_to_dict 等）随实现模块迁移，仅内部引用，不影响外部
"""
from __future__ import annotations

from algorithm_service.infrastructure.persistence._algorithm_param_repository import (
    AlgorithmParamRepository,
)
from algorithm_service.infrastructure.persistence._case_reference_param_repositories import (
    CaseParamRepository,
    ReferenceParamRepository,
)
from algorithm_service.infrastructure.persistence._mapping_relation_repositories import (
    MappingRepository,
    DimensionRelationRepository,
)


# ========== 模块级单例 ==========

algorithm_param_repository = AlgorithmParamRepository()
case_param_repository = CaseParamRepository()
reference_param_repository = ReferenceParamRepository()
mapping_repository = MappingRepository()
dimension_relation_repository = DimensionRelationRepository()
