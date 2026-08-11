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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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


@dataclass(frozen=True)
class UpdateAlgorithmDefinitionCommand:
    """更新算法定义命令。

    - id: 算法定义ID
    - name: 算法名称
    - description: 算法描述
    """

    id: int
    name: str
    description: Optional[str] = None


@dataclass(frozen=True)
class DeleteAlgorithmDefinitionCommand:
    """删除算法定义命令（软删除）。

    - id: 算法定义ID
    """

    id: int


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
