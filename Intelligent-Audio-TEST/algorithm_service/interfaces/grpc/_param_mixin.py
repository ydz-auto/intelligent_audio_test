# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的参数/映射/维度关系/分组/事务方法 mixin（聚合入口）。

本模块由 servicers.py 导入，对外保持 ``_ParamMethodsMixin`` / ``_success`` /
``_failure`` 三个名称不变。原 921+ 行单文件已按职责拆分为多个子 mixin：

- ``_param_helpers``           公共工具（_success/_failure）+ 基础 mixin（缓存刷新）
- ``_param_query_mixin``       参数/映射/维度/算法定义/分组查询（读操作）
- ``_param_command_mixin``     设备/API/用例/参考参数写 + 映射写 + 批量删除
- ``_dimension_mixin``         维度关系 CRUD + 评估维度参数 + 参数映射同步
- ``_algorithm_definition_mixin`` 算法定义/分组 CRUD + 导入/重载 + 事务控制

``_ParamMethodsMixin`` 通过多重继承聚合上述子 mixin，供
``AlgorithmDefinitionServicer(_ParamMethodsMixin, ...ServiceServicer)`` 继承。
"""
from __future__ import annotations

# 对外保持兼容：servicers.py 直接从本模块导入 _success / _failure
from algorithm_service.interfaces.grpc._param_helpers import (
    _success,
    _failure,
    _ParamBaseMixin,
)
from algorithm_service.interfaces.grpc._param_query_mixin import _ParamQueryMixin
from algorithm_service.interfaces.grpc._param_command_mixin import _ParamCommandMixin
from algorithm_service.interfaces.grpc._dimension_mixin import _DimensionMixin
from algorithm_service.interfaces.grpc._algorithm_definition_mixin import (
    _AlgorithmDefinitionMixin,
)


class _ParamMethodsMixin(
    _ParamQueryMixin,
    _ParamCommandMixin,
    _DimensionMixin,
    _AlgorithmDefinitionMixin,
    _ParamBaseMixin,
):
    """参数/映射/维度关系/分组/事务方法 mixin（聚合）。

    被 AlgorithmDefinitionServicer 继承，提供以下方法组：
    - 参数查询（device/api/case/reference）
    - 映射查询
    - 维度关系 CRUD + 批量管理
    - 导入/重载
    - 评估维度参数管理
    - 参数映射同步
    - 设备/API/用例/参考参数写操作
    - 参数映射写操作
    - 算法定义写操作
    - 算法分组写操作
    - 维度关联写操作
    - 事务控制

    实际方法实现分布于各子 mixin，本类仅做多重继承聚合。
    """
