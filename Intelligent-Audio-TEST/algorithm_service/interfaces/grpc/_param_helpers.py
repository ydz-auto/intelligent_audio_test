# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的公共工具与基础 mixin。

从 _param_mixin.py 拆分，提供：
- _success / _failure：构造 AlgorithmResponse 的模块级工具函数
- _ParamBaseMixin：提供写操作后刷新缓存的能力，供各子 mixin 继承
"""
from __future__ import annotations

from typing import Any

import logging

from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import dumps as _dumps

logger = logging.getLogger(__name__)


def _success(data: Any = None, message: str = "ok"):
    """构造成功响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=True,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


def _failure(message: str, data: Any = None):
    """构造失败响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=False,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


class _ParamBaseMixin:
    """参数方法基础 mixin，仅提供写操作后的缓存刷新能力。

    各子 mixin（CRUD/映射/维度关系/算法定义）继承本类，从而获得
    ``self._invalidate_cache``；最终由 ``_ParamMethodsMixin`` 多重继承聚合。
    """

    @staticmethod
    def _invalidate_cache():
        """写操作后刷新缓存（L1 重载 + Redis pubsub 通知其他进程）"""
        try:
            from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
            get_config_cache().invalidate()
        except Exception:
            logger.exception("刷新缓存失败（_invalidate_cache）")
