# -*- coding: utf-8 -*-
"""命令对象 — 应用层用例输入，纯数据载体。"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class CreateAPITestCommand:
    """创建（启动）API 测试会话命令

    与 APITestService.start_task 的签名对齐。
    """

    task_id: int
    case_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class StopAPITestCommand:
    """停止 API 测试会话命令"""

    task_id: int


@dataclass(frozen=True)
class CreateAPICommand:
    """创建 API 配置命令

    通过 repository 创建 APIAggregate 聚合根。
    data 为 API 配置参数字典（name/meta/endpoints 等）。
    """

    data: Dict


@dataclass(frozen=True)
class UpdateAPICommand:
    """更新 API 配置命令

    通过 repository 更新指定 API 的字段。
    """

    api_id: int
    data: Dict


@dataclass(frozen=True)
class DeleteAPICommand:
    """删除 API 配置命令（软删除）

    通过 repository 软删除指定 API。
    """

    api_id: int
