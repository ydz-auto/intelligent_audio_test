# -*- coding: utf-8 -*-
"""算法参数处理 mixin（_execute_extra_params 已移除，用例参数通过 round_algo_params 透传）"""


class ParamsMixin:
    """执行器基类算法参数处理方法"""

    def _get_result_mapper(self):
        """获取结果映射器 — 由子类实现，返回各自的 ACL 仓储"""
        raise NotImplementedError(
            "_get_result_mapper 必须由子类实现，返回 DeviceResultAclRepository 实例"
        )
