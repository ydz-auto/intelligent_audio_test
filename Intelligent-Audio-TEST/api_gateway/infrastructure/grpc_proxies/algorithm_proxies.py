"""算法查询/定义服务代理：_AlgorithmQueryProxy 及单例 algorithm_query_service。

封装 algorithm_service.AlgorithmQueryService 和 AlgorithmDefinitionService 的调用，
作为 api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
import json

from shared.clients.grpc_clients import (
    get_algorithm_definition_service_stub,
    algo_get_reference_text,
    algo_normalize_algorithm_params,
    algo_generate_reference_params,
    algo_get_all_reference_params,
)

from ._common import _grpc_call


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

    # ---- 算法定义全量保存 / 草稿（INT-589）----

    def save_algorithm_definition(self, data):
        """算法定义全量保存（聚合事务 + 乐观锁）。

        data: 完整定义 JSON（基础字段 + 六类子实体 + expected_updated_at）。
        返回信封含 code：SAVED / OK / CONFLICT / VALIDATION_FAILED。
        """
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.SaveAlgorithmDefinition(
                algo_pb.SaveAlgorithmDefinitionRequest(
                    data=json.dumps(data, ensure_ascii=False, default=str)
                )
            )
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code,
            }
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False,
                'message': f'算法定义全量保存失败: {e}',
                'data': None,
                'code': 500,
            },
            error_msg_prefix='算法定义全量保存失败',
        )

    def save_algorithm_definition_draft(self, data):
        """草稿自动保存（30s 快照，不落正式六表）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.SaveAlgorithmDefinitionDraft(
                algo_pb.SaveAlgorithmDefinitionDraftRequest(
                    data=json.dumps(data, ensure_ascii=False, default=str)
                )
            )
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code,
            }
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False,
                'message': f'保存草稿失败: {e}',
                'data': None,
                'code': 500,
            },
            error_msg_prefix='保存草稿失败',
        )

    def get_algorithm_definition_draft(self, algorithm_type):
        """读取草稿快照（前端编辑恢复）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.GetAlgorithmDefinitionDraft(
                algo_pb.GetAlgorithmDefinitionDraftRequest(
                    algorithm_type=algorithm_type or ''
                )
            )
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code,
            }
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False,
                'message': f'读取草稿失败: {e}',
                'data': None,
                'code': 500,
            },
            error_msg_prefix='读取草稿失败',
        )


# 算法查询代理模块级单例
algorithm_query_service = _AlgorithmQueryProxy()
