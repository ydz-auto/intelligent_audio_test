# -*- coding: utf-8 -*-
"""算法定义及关联配置 CRUD 代理（从 task_config_proxies.py 拆分，P4-4）。

算法定义/分组/参数/用例参数/参考参数/映射/维度关联的 gRPC 代理类
及模块级单例，作为 api_gateway 的 ACL 层。
"""
import json

from shared.clients.grpc_clients import get_algorithm_config_service_stub

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _AlgorithmConfigProxy:
    """算法定义及关联配置 CRUD 代理"""

    def _resp(self, resp):
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    @property
    def stub(self):
        """获取 AlgorithmConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_algorithm_config_service_stub()

    # ---- 算法定义 写操作 ----

    def create_algorithm(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateAlgorithm(task_pb.CreateAlgorithmRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建算法定义失败',
        )

    def update_algorithm(self, algo_type, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateAlgorithm(task_pb.UpdateAlgorithmRequest(algo_type=algo_type, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新算法定义失败',
        )

    def delete_algorithm(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteAlgorithm(task_pb.DeleteAlgorithmRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除算法定义失败',
        )

    # ---- 算法分组 写操作 ----

    def create_group(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateAlgorithmGroup(task_pb.CreateAlgorithmGroupRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建算法分组失败',
        )

    def update_group(self, group_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateAlgorithmGroup(task_pb.UpdateAlgorithmGroupRequest(group_id=group_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新算法分组失败',
        )

    def delete_group(self, group_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteAlgorithmGroup(task_pb.DeleteAlgorithmGroupRequest(group_id=group_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除算法分组失败',
        )

    # ---- 参数(device/api) 写操作 ----

    def create_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateParam(task_pb.CreateParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建参数失败',
        )

    def update_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateParam(task_pb.UpdateParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新参数失败',
        )

    def delete_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteParam(task_pb.DeleteParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除参数失败',
        )

    # ---- 用例专属参数 写操作 ----

    def create_case_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateCaseParam(task_pb.CreateCaseParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建用例参数失败',
        )

    def update_case_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateCaseParam(task_pb.UpdateCaseParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新用例参数失败',
        )

    def delete_case_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteCaseParam(task_pb.DeleteCaseParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除用例参数失败',
        )

    # ---- 参考参数 写操作 ----

    def create_reference_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateReferenceParam(task_pb.CreateReferenceParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建参考参数失败',
        )

    def update_reference_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateReferenceParam(task_pb.UpdateReferenceParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新参考参数失败',
        )

    def delete_reference_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteReferenceParam(task_pb.DeleteReferenceParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除参考参数失败',
        )

    # ---- 参数映射 写操作 ----

    def create_mapping(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateMapping(task_pb.CreateMappingRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建映射失败',
        )

    def update_mapping(self, mapping_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateMapping(task_pb.UpdateMappingRequest(mapping_id=mapping_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新映射失败',
        )

    def delete_mapping(self, mapping_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteMapping(task_pb.DeleteMappingRequest(mapping_id=mapping_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除映射失败',
        )

    # ---- 维度关联 写操作 ----

    def associate_dimensions(self, algo_type, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.AssociateDimensions(task_pb.AssociateDimensionsRequest(algo_type=algo_type, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'关联维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='关联维度失败',
        )

    def create_dimension_relation(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateDimensionRelation(task_pb.CreateDimensionRelationRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建维度关联失败',
        )

    def update_dimension_relation(self, relation_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateDimensionRelation(task_pb.UpdateDimensionRelationRequest(relation_id=relation_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新维度关联失败',
        )

    def delete_dimension_relation(self, relation_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteDimensionRelation(task_pb.DeleteDimensionRelationRequest(relation_id=relation_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除维度关联失败',
        )

    # ---- 批量操作 ----

    def import_algorithms(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ImportAlgorithms(task_pb.ImportAlgorithmsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'导入算法失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='导入算法失败',
        )

    def bulk_delete(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.BulkDeleteAlgorithms(task_pb.BulkDeleteAlgorithmsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量删除算法失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量删除算法失败',
        )

    def extract_params(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ExtractParams(task_pb.ExtractParamsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'提取参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='提取参数失败',
        )

    def reload_config(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ReloadAlgorithmConfig(task_pb.ReloadAlgorithmConfigRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重载配置失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='重载配置失败',
        )

    # ---- 读操作 ----

    def list_algorithms(self, status=None, group_id=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListAlgorithms(task_pb.ListAlgorithmsRequest(status=status or '', group_id=group_id or 0)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法列表失败',
        )

    def get_algorithm(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithm(task_pb.GetAlgorithmRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法详情失败',
        )

    def get_algorithm_options(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmOptions(task_pb.GetAlgorithmOptionsRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法选项失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法选项失败',
        )

    def list_groups(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListAlgorithmGroups(task_pb.ListAlgorithmGroupsRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法分组列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法分组列表失败',
        )

    def get_group(self, group_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmGroup(task_pb.GetAlgorithmGroupRequest(group_id=group_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法分组详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法分组详情失败',
        )

    def list_params(self, algorithm_type=None, param_type=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListParams(task_pb.ListParamsRequest(algorithm_type=algorithm_type or '', param_type=param_type or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参数列表失败',
        )

    def get_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetParam(task_pb.GetParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参数详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参数详情失败',
        )

    def list_case_params(self, algorithm_type=None, scope=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListCaseParams(task_pb.ListCaseParamsRequest(algorithm_type=algorithm_type or '', scope=scope or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例参数列表失败',
        )

    def get_case_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetCaseParam(task_pb.GetCaseParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例参数详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例参数详情失败',
        )

    def list_reference_params(self, algorithm_type=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListReferenceParams(task_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参考参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参考参数列表失败',
        )

    def list_mappings(self, algorithm_type=None, source_type=None, dimension_id=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListMappings(task_pb.ListMappingsRequest(algorithm_type=algorithm_type or '', source_type=source_type or '', dimension_id=dimension_id or 0)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取映射列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取映射列表失败',
        )

    def get_form_schema(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetFormSchema(task_pb.GetFormSchemaRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取表单Schema失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取表单Schema失败',
        )

    def get_algorithm_dimensions(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmDimensions(task_pb.GetAlgorithmDimensionsRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法维度失败',
        )

    def get_dimension_params(self, dimension_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetDimensionParams(task_pb.GetDimensionParamsRequest(dimension_id=dimension_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取维度参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取维度参数失败',
        )


# 算法配置 CRUD 模块级单例
algorithm_config_service = _AlgorithmConfigProxy()
