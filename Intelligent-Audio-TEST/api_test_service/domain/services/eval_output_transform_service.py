# -*- coding: utf-8 -*-
"""EvalOutputTransformService — 评估入参映射 transform_type 批量应用（INT-1749）

执行侧唯一变换点：轮次评估字段（``{target_param: value}``）在写入
``rounds[i].output`` **之前**按 ``param_mappings.transform_type`` 变换一次，
评估侧不再变换（C0 裁定 1，INT-1745）。

- 变换能力归 algorithm_service（``FieldTransformService`` /
  ``ConvertFieldValues`` RPC），本服务只做编排，不复制变换实现；
- 一次批量 gRPC 处理全部字段，不逐字段跨服务调用；
- 非法输入：保留原值（算法服务 errors 回传，本层 WARNING），不吞成空串；
- 算法服务不可达 / 返回长度不符：整体按原值保留，不中断用例执行。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class EvalOutputTransformService:
    """评估入参批量变换编排（域服务，变换实现经 ACL 端口注入）"""

    @staticmethod
    def _targets(fields, transform_types):
        """需要变换的字段名（transform_type 为空 / none 视为原值直传）"""
        return [target for target in fields
                if (transform_types.get(target) or 'none') != 'none']

    @classmethod
    def apply(cls, fields, transform_types, acl):
        """就地变换 ``fields`` 并返回它。

        Args:
            fields: ``{target_param: value}``（映射后的评估入参）
            transform_types: ``{target_param: transform_type}``
            acl: AlgorithmQueryAclRepository（``convert_field_values``）
        """
        targets = cls._targets(fields or {}, transform_types or {})
        if not targets:
            return fields
        items = [{'transform_type': transform_types[target],
                  'value': fields[target]} for target in targets]
        values = acl.convert_field_values(items)
        if values is None:
            logger.warning(
                "评估入参批量变换不可用，按原值保留（targets=%s）", targets)
            return fields
        for target, value in zip(targets, values):
            fields[target] = value
        return fields
