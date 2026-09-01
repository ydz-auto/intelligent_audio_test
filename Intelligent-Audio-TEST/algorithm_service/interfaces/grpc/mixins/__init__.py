# -*- coding: utf-8 -*-
"""algorithm_service.interfaces.grpc.mixins — 参数 Servicer Mixin 子包。

由原平铺文件 ``_param_mixin.py`` 及其 5 个拆分模块整合而来（P7-3）：

- ``param_helpers``              公共工具（_success/_failure）+ 基础 mixin（缓存刷新）
- ``param_query_mixin``          参数/映射/维度/算法定义/分组查询（读操作）
- ``param_command_mixin``        设备/API/用例/参考参数写 + 映射写 + 批量删除
- ``dimension_mixin``            维度关系 CRUD + 评估维度参数 + 参数映射同步
- ``algorithm_definition_mixin`` 算法定义/分组 CRUD + 导入/重载 + 事务控制
- ``param_mixin``                聚合入口（_ParamMethodsMixin 多重继承）
"""
from algorithm_service.interfaces.grpc.mixins.param_helpers import (
    _success,
    _failure,
    _ParamBaseMixin,
)
from algorithm_service.interfaces.grpc.mixins.param_query_mixin import _ParamQueryMixin
from algorithm_service.interfaces.grpc.mixins.param_command_mixin import _ParamCommandMixin
from algorithm_service.interfaces.grpc.mixins.dimension_mixin import _DimensionMixin
from algorithm_service.interfaces.grpc.mixins.algorithm_definition_mixin import (
    _AlgorithmDefinitionMixin,
)
from algorithm_service.interfaces.grpc.mixins.param_mixin import _ParamMethodsMixin

__all__ = [
    '_ParamMethodsMixin',
    '_ParamBaseMixin',
    '_ParamQueryMixin',
    '_ParamCommandMixin',
    '_DimensionMixin',
    '_AlgorithmDefinitionMixin',
    '_success',
    '_failure',
]
