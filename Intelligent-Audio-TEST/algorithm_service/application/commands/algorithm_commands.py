# -*- coding: utf-8 -*-
"""算法写操作命令（CQRS - Command 侧）。

归属：algorithm_service.application.commands

说明：
- 所有命令均为 frozen dataclass，作为写操作的输入契约。
- 命令只承载"做什么"的意图，不携带领域对象，不包含业务逻辑。
- 实际处理由 handlers/algorithm_handlers.py 的 AlgorithmCommandHandler 完成。
- 命令字段与领域聚合根对齐，便于 Handler 构造聚合根后调用 repository。

命令清单：
- 算法分组：CreateAlgorithmGroupCommand / UpdateAlgorithmGroupCommand / DeleteAlgorithmGroupCommand
- 算法定义：CreateAlgorithmDefinitionCommand / UpdateAlgorithmDefinitionCommand / DeleteAlgorithmDefinitionCommand
- 算法状态：ActivateAlgorithmCommand / DeprecateAlgorithmCommand
- 算法全量保存：SaveAlgorithmDefinitionCommand（INT-589）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ========== 算法分组命令 ==========

@dataclass(frozen=True)
class CreateAlgorithmGroupCommand:
    """创建算法分组命令。

    - name: 分组名称（唯一）
    - description: 分组描述
    - algorithm_type: 分组对应的算法类型代码
    """

    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None


@dataclass(frozen=True)
class UpdateAlgorithmGroupCommand:
    """更新算法分组命令。

    - id: 分组ID
    - name: 分组名称
    - description: 分组描述
    """

    id: int
    name: str
    description: Optional[str] = None


@dataclass(frozen=True)
class DeleteAlgorithmGroupCommand:
    """删除算法分组命令（软删除）。

    - id: 分组ID
    """

    id: int


# ========== 算法定义命令 ==========

@dataclass(frozen=True)
class CreateAlgorithmDefinitionCommand:
    """创建算法定义命令。

    - group_id: 所属分组ID
    - name: 算法名称
    - algorithm_type: 算法类型代码
    - description: 算法描述
    """

    group_id: Optional[int]
    name: str
    algorithm_type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = None


@dataclass(frozen=True)
class UpdateAlgorithmDefinitionCommand:
    """更新算法定义命令（PATCH 语义：字段为 None 时不改动现值）。

    - id: 算法定义ID
    - name: 算法名称（None=不改；部分更新如仅切换状态时不携带）
    - description: 算法描述
    - group_id: 分组ID
    - status: 状态（PO 口径字符串 online/offline/draft）
    - icon: 图标URL
    - display_order: 排序权重
    """

    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    group_id: Optional[int] = None
    status: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = None


@dataclass(frozen=True)
class DeleteAlgorithmDefinitionCommand:
    """删除算法定义命令（软删除）。

    - id: 算法定义ID
    """

    id: int


@dataclass(frozen=True)
class SaveAlgorithmDefinitionCommand:
    """算法定义全量保存命令（INT-589）。

    一次提交完整定义（基础字段 + 六类子实体），聚合事务原子落库。
    - id: 定义ID（None/0 → 新建；有值 → 按 id 更新）
    - algorithm_type: 算法类型代码
    - name / group_id / description / status / icon / display_order: 基础字段
    - device_params / api_params / case_params / reference_params: 参数列表
    - mappings: 参数映射（平铺列表或按 source 分组的 dict，见 handler 归一）
    - associated_dimensions: 关联评估维度列表
    - expected_updated_at: 乐观锁版本（ISO 字符串，更新路径必填，由前端
      从上一次读取的 definition.updated_at 带回）
    """

    id: Optional[int] = None
    algorithm_type: str = ""
    name: str = ""
    group_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = "online"
    icon: Optional[str] = None
    display_order: Optional[int] = 0
    device_params: List[Dict[str, Any]] = field(default_factory=list)
    api_params: List[Dict[str, Any]] = field(default_factory=list)
    case_params: List[Dict[str, Any]] = field(default_factory=list)
    reference_params: List[Dict[str, Any]] = field(default_factory=list)
    mappings: Any = field(default_factory=list)
    associated_dimensions: List[Dict[str, Any]] = field(default_factory=list)
    expected_updated_at: Optional[str] = None


# ========== 算法状态变更命令 ==========

@dataclass(frozen=True)
class ActivateAlgorithmCommand:
    """上线算法命令。

    将算法定义状态置为 active。

    - id: 算法定义ID
    """

    id: int


@dataclass(frozen=True)
class DeprecateAlgorithmCommand:
    """废弃算法命令。

    将算法定义状态置为 deprecated。

    - id: 算法定义ID
    """

    id: int
