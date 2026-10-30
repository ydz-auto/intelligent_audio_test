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

    def clear_algorithm_definition_draft(self, algorithm_type):
        """清除草稿快照（INT-1514：发布 / 删除成功后调用）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.ClearAlgorithmDefinitionDraft(
                algo_pb.ClearAlgorithmDefinitionDraftRequest(
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
                'message': f'清除草稿失败: {e}',
                'data': None,
                'code': 500,
            },
            error_msg_prefix='清除草稿失败',
        )

    # ---- 参数策略（API 参数/映射的可复用声明）----

    @staticmethod
    def _unwrap(resp):
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
            'code': resp.code,
        }

    def list_param_profiles(self, algorithm_type=None, scope=None):
        """策略列表（AlgorithmQueryService.ListParamProfiles）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb
        from shared.clients.grpc_clients import get_algorithm_query_service_stub

        def _call():
            stub = get_algorithm_query_service_stub()
            return self._unwrap(stub.ListParamProfiles(
                algo_pb.ListParamProfilesRequest(
                    algorithm_type=algorithm_type or '',
                    scope=scope or '',
                )))
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'读取参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='读取参数策略失败',
        )

    def get_param_profile(self, profile_id):
        """策略详情（AlgorithmQueryService.GetParamProfile）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb
        from shared.clients.grpc_clients import get_algorithm_query_service_stub

        def _call():
            stub = get_algorithm_query_service_stub()
            return self._unwrap(stub.GetParamProfile(
                algo_pb.GetParamProfileRequest(profile_id=int(profile_id))))
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'读取参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='读取参数策略失败',
        )

    def save_param_profile(self, data):
        """整份保存策略（AlgorithmDefinitionService.SaveParamProfile）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.SaveParamProfile(
                algo_pb.SaveParamProfileRequest(
                    data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._unwrap(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'保存参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='保存参数策略失败',
        )

    def clone_param_profile(self, source_profile_id, name, description=None):
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.CloneParamProfile(
                algo_pb.CloneParamProfileRequest(data=json.dumps({
                    'source_profile_id': int(source_profile_id),
                    'name': name,
                    'description': description,
                }, ensure_ascii=False)))
            return self._unwrap(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'克隆参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='克隆参数策略失败',
        )

    def delete_param_profile(self, profile_id):
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.DeleteParamProfile(
                algo_pb.DeleteParamProfileRequest(profile_id=int(profile_id)))
            return self._unwrap(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'删除参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='删除参数策略失败',
        )

    def bind_api_param_profile(self, api_id, profile_id=None):
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.BindApiParamProfile(
                algo_pb.BindApiParamProfileRequest(data=json.dumps({
                    'api_id': int(api_id),
                    'profile_id': int(profile_id) if profile_id else None,
                }, ensure_ascii=False)))
            return self._unwrap(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'绑定参数策略失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='绑定参数策略失败',
        )

    def save_api_scope_overrides(self, api_id, algorithm_type, api_params, mappings):
        """按 api_id 原子保存实例覆盖行（AlgorithmDefinitionService.SaveApiScopeOverrides）。"""
        from shared.proto import algorithm_service_pb2 as algo_pb

        def _call():
            resp = self.definition_stub.SaveApiScopeOverrides(
                algo_pb.SaveApiScopeOverridesRequest(data=json.dumps({
                    'api_id': int(api_id),
                    'algorithm_type': algorithm_type or '',
                    'api_params': api_params or [],
                    'mappings': mappings or [],
                }, ensure_ascii=False, default=str)))
            return self._unwrap(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {
                'success': False, 'message': f'保存 API 覆盖配置失败: {e}',
                'data': None, 'code': 500},
            error_msg_prefix='保存 API 覆盖配置失败',
        )


# 算法查询代理模块级单例
algorithm_query_service = _AlgorithmQueryProxy()
