"""评估服务代理：_ReevaluationExecutorProxy、_EvaluationConfigProxy 及单例 evaluation_config_service。"""
import json

from shared.clients.grpc_clients import (
    get_evaluation_service_stub,
    get_evaluation_config_service_stub,
)

from ._common import _grpc_call


class _ReevaluationExecutorProxy:
    """ReevaluationExecutor 代理：把方法调用转发到 gRPC evaluation_service.EvaluationService"""

    @classmethod
    def get_instance(cls):
        return cls()

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all'):
        from shared.proto import evaluation_service_pb2

        def _call():
            stub = get_evaluation_service_stub()
            resp = stub.Reevaluate(evaluation_service_pb2.ReevaluateRequest(
                task_id=str(task_id),
                reextract_device_output=reextract_device_output,
                reevaluate_type=reevaluate_type,
            ))
            return resp.success, resp.message

        return _grpc_call(
            _call,
            default_return=lambda e: (False, f"重新评估失败: {e}"),
            error_msg_prefix="重新评估失败",
        )

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result,
                                 test_type, algorithm_type):
        """多轮用例重新评估"""
        from shared.proto import evaluation_service_pb2

        def _call():
            stub = get_evaluation_service_stub()
            resp = stub.ReevaluateMultiRound(evaluation_service_pb2.ReevaluateMultiRoundRequest(
                task_id=str(task_id),
                result_json=json.dumps(result or {}, ensure_ascii=False, default=str),
                test_case_id=str(test_case_id or ''),
                algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
                test_type=test_type or 'api',
                algorithm_type=algorithm_type or 'translation',
            ))
            return resp.success, resp.message

        return _grpc_call(
            _call,
            default_return=lambda e: (False, f"多轮重新评估失败: {e}"),
            error_msg_prefix="多轮重新评估失败",
        )

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result,
                           reference_params, test_type, algorithm_type):
        """单轮用例重新评估"""
        from shared.proto import evaluation_service_pb2

        def _call():
            stub = get_evaluation_service_stub()
            resp = stub.ReevaluateSingle(evaluation_service_pb2.ReevaluateSingleRequest(
                task_id=str(task_id),
                result_id=str(result_id or ''),
                test_case_id=str(test_case_id or ''),
                algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
                reference_params=json.dumps(reference_params or {}, ensure_ascii=False, default=str),
                test_type=test_type or 'api',
                algorithm_type=algorithm_type or 'translation',
            ))
            return resp.success, resp.message

        return _grpc_call(
            _call,
            default_return=lambda e: (False, f"单轮重新评估失败: {e}"),
            error_msg_prefix="单轮重新评估失败",
        )


class _EvaluationConfigProxy:
    """评估维度及分类 CRUD 代理

    注：已从 task_service.EvaluationConfigService 迁移至 evaluation_service.EvaluationConfigService。
    使用 evaluation_service_pb2 消息类型。
    """

    @property
    def stub(self):
        """获取 EvaluationConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_evaluation_config_service_stub()

    def _resp(self, resp):
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---- 分类 CRUD ----

    def create_category(self, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.CreateCategory(eval_pb.CreateCategoryRequest(data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建分类失败',
        )

    def update_category(self, cat_id, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.UpdateCategory(eval_pb.UpdateCategoryRequest(cat_id=cat_id, data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新分类失败',
        )

    def delete_category(self, cat_id):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.DeleteCategory(eval_pb.DeleteCategoryRequest(cat_id=cat_id))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除分类失败',
        )

    def list_categories(self):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.ListCategories(eval_pb.ListCategoriesRequest())
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取分类列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取分类列表失败',
        )

    # ---- 维度 CRUD ----

    def create_dimension(self, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.CreateDimension(eval_pb.CreateDimensionRequest(data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建维度失败',
        )

    def update_dimension(self, dim_id, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.UpdateDimension(eval_pb.UpdateDimensionRequest(dim_id=dim_id, data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新维度失败',
        )

    def delete_dimension(self, dim_id):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.DeleteDimension(eval_pb.DeleteDimensionRequest(dim_id=dim_id))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除维度失败',
        )

    def batch_action(self, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.BatchActionDimension(eval_pb.BatchActionDimensionRequest(data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量操作失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量操作失败',
        )

    def calculate_score(self, dim_id, data):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.CalculateScore(eval_pb.CalculateScoreRequest(dim_id=dim_id, data=json.dumps(data, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'分值计算失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='分值计算失败',
        )

    # ---- 读操作 ----

    def list_dimensions(self, category_id=None, page=1, per_page=10, search=''):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                category_id=category_id or 0,
                page=page,
                per_page=per_page,
                search=search or '',
            ))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取维度列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取维度列表失败',
        )

    def get_dimension_options(self, algorithm_type=None):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionOptions(eval_pb.GetDimensionOptionsRequest(algorithm_type=algorithm_type or ''))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取维度选项失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取维度选项失败',
        )

    def get_dimension_by_ids(self, dim_ids):
        """按 ID 批量查询维度，返回 dict: {success, message, data}
        data 为 dict: {dim_id_str: dimension_dict, ...} 供调用方按 ID 取维度。
        """
        import json as _json
        from shared.proto import evaluation_service_pb2 as eval_pb
        ids_list = [int(d) for d in dim_ids if d is not None]
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=_json.dumps(ids_list, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)
        result = _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按ID获取维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='按ID获取维度失败',
        )
        if result.get('success') and result.get('data'):
            items = result['data'].get('items') if isinstance(result['data'], dict) else result['data']
            if isinstance(items, list):
                dim_map = {str(d.get('id')): d for d in items if isinstance(d, dict) and d.get('id') is not None}
                result['data'] = dim_map
            elif isinstance(items, dict):
                result['data'] = items
        return result

    def health_check(self, dim_id):
        from shared.proto import evaluation_service_pb2 as eval_pb
        def _call():
            stub = get_evaluation_config_service_stub()
            resp = stub.HealthCheck(eval_pb.HealthCheckRequest(dim_id=dim_id))
            return self._resp(resp)
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'健康检查失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='健康检查失败',
        )


# 评估维度配置 CRUD 模块级单例
evaluation_config_service = _EvaluationConfigProxy()
