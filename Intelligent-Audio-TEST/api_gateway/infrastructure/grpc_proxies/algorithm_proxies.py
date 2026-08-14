"""算法查询/定义服务代理：_AlgorithmQueryProxy 及单例 algorithm_query_service。

封装 algorithm_service.AlgorithmQueryService 和 AlgorithmDefinitionService 的调用，
作为 api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
from shared.clients.grpc_clients import (
    get_algorithm_definition_service_stub,
    algo_get_reference_text,
    algo_normalize_algorithm_params,
    algo_generate_reference_params,
    algo_get_all_reference_params,
)


class _AlgorithmQueryProxy:
    """AlgorithmQueryService / AlgorithmDefinitionService 代理

    封装 algorithm_service 的 algo_* 便捷函数和 AlgorithmDefinitionService stub 调用，
    供 api_gateway application 层使用，替代直接 import shared.clients.grpc_clients。
    """

    def get_reference_text(self, reference_params_col=None, code=''):
        """获取参考文本"""
        return algo_get_reference_text(reference_params_col=reference_params_col, code=code)

    def normalize_algorithm_params(self, algorithm_params=None):
        """规范化算法参数为 dict"""
        return algo_normalize_algorithm_params(algorithm_params=algorithm_params)

    def generate_reference_params(self, test_case_config=None, round_data=None):
        """生成参考参数"""
        return algo_generate_reference_params(test_case_config=test_case_config, round_data=round_data)

    def get_all_reference_params(self, reference_params_col=None):
        """获取所有参考参数"""
        return algo_get_all_reference_params(reference_params_col=reference_params_col)

    @property
    def definition_stub(self):
        """获取 AlgorithmDefinitionService stub（供需要直接调 RPC 的场景使用）"""
        return get_algorithm_definition_service_stub()


# 算法查询代理模块级单例
algorithm_query_service = _AlgorithmQueryProxy()
