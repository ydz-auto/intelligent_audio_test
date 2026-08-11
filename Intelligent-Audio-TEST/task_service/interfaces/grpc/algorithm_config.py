# -*- coding: utf-8 -*-
# ======================================================================
# TODO(algorithm-migration): 本 servicer 当前仍委托 task_service.application.algorithm
# 旧 CRUD（DEPRECATED）。待 algorithm_service 的 proto 接口就绪后，应改为通过 gRPC stub
# 调用 algorithm_service（shared.clients.grpc_clients.get_algorithm_definition_service_stub /
# get_algorithm_group_service_stub）。
#
# 现状评估（algorithm_service_pb2 / algorithm_service_pb2_grpc）：
#  - AlgorithmDefinitionService 已提供大部分对齐 RPC：
#    CreateAlgorithm / UpdateAlgorithm / DeleteAlgorithm / ListAlgorithms /
#    GetAlgorithm / GetAlgorithmOptions / ListParams / GetParam / ListCaseParams /
#    CreateCaseParam / UpdateCaseParam / DeleteCaseParam /
#    CreateReferenceParam / UpdateReferenceParam / DeleteReferenceParam /
#    ListMappings / CreateMapping / UpdateMapping / DeleteMapping /
#    GetDimensionParams / GetAlgorithmDimensions /
#    CreateDimensionRelation / UpdateDimensionRelation / DeleteDimensionRelation /
#    ImportAlgorithms / BulkDeleteAlgorithms / ReloadAlgorithmConfig
#  - 但本 servicer 暴露的以下 3 个 RPC 在 algorithm_service proto 中尚不存在：
#      * ExtractParams
#      * AssociateDimensions
#      * GetFormSchema
#    因此无法整体切换，需 algorithm_service 补齐这 3 个 RPC 后再迁移。
#  - AlgorithmGroupService 的 RPC 名（CreateAlgorithmGroup 等）与
#    AlgorithmDefinitionService 的分组 RPC 名（CreateGroup 等）不一致，
#    切换时需做方法名映射。
# ======================================================================
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class AlgorithmConfigServiceServicer(task_grpc.AlgorithmConfigServiceServicer):
    """算法定义及关联配置 CRUD servicer，委托给 AlgorithmCrudService（DEPRECATED）。"""

    def __init__(self):
        self._svc = None

    @property
    def svc(self):
        if self._svc is None:
            from task_service.application.algorithm.algorithm_crud_service import algorithm_crud_service
            self._svc = algorithm_crud_service
        return self._svc

    @staticmethod
    def _resp(result):
        """统一包装返回结果为 AlgorithmConfigResponse"""
        return task_pb.AlgorithmConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- 算法定义 写操作 ----

    def CreateAlgorithm(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_algorithm(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateAlgorithm(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_algorithm(request.algo_type, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteAlgorithm(self, request, context=None):
        try:
            return self._resp(self.svc.delete_algorithm(request.algo_type))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 算法分组 写操作 ----

    def CreateAlgorithmGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_group(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateAlgorithmGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_group(request.group_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteAlgorithmGroup(self, request, context=None):
        try:
            return self._resp(self.svc.delete_group(request.group_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 参数(device/api) 写操作 ----

    def CreateParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_param(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_param(request.param_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteParam(self, request, context=None):
        try:
            return self._resp(self.svc.delete_param(request.param_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 用例专属参数 写操作 ----

    def CreateCaseParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_case_param(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateCaseParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_case_param(request.param_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteCaseParam(self, request, context=None):
        try:
            return self._resp(self.svc.delete_case_param(request.param_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 参考参数 写操作 ----

    def CreateReferenceParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_reference_param(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateReferenceParam(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_reference_param(request.param_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteReferenceParam(self, request, context=None):
        try:
            return self._resp(self.svc.delete_reference_param(request.param_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 参数映射 写操作 ----

    def CreateMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_mapping(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_mapping(request.mapping_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteMapping(self, request, context=None):
        try:
            return self._resp(self.svc.delete_mapping(request.mapping_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 维度关联 写操作 ----

    def AssociateDimensions(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.associate_dimensions(request.algo_type, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def CreateDimensionRelation(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.create_dimension_relation(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def UpdateDimensionRelation(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.update_dimension_relation(request.relation_id, data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def DeleteDimensionRelation(self, request, context=None):
        try:
            return self._resp(self.svc.delete_dimension_relation(request.relation_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 批量操作 ----

    def ImportAlgorithms(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.import_algorithms(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def BulkDeleteAlgorithms(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.bulk_delete(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ExtractParams(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.svc.extract_params(data))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ReloadAlgorithmConfig(self, request, context=None):
        try:
            return self._resp(self.svc.reload_config())
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListAlgorithms(self, request, context=None):
        try:
            return self._resp(self.svc.list_algorithms(
                status=request.status or None,
                group_id=request.group_id or None,
            ))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetAlgorithm(self, request, context=None):
        try:
            return self._resp(self.svc.get_algorithm(request.algo_type))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetAlgorithmOptions(self, request, context=None):
        try:
            return self._resp(self.svc.get_algorithm_options())
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ListAlgorithmGroups(self, request, context=None):
        try:
            return self._resp(self.svc.list_groups())
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetAlgorithmGroup(self, request, context=None):
        try:
            return self._resp(self.svc.get_group(request.group_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ListParams(self, request, context=None):
        try:
            return self._resp(self.svc.list_params(
                algorithm_type=request.algorithm_type or None,
                param_type=request.param_type or None,
            ))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetParam(self, request, context=None):
        try:
            return self._resp(self.svc.get_param(request.param_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ListCaseParams(self, request, context=None):
        try:
            return self._resp(self.svc.list_case_params(
                algorithm_type=request.algorithm_type or None,
                scope=request.scope or None,
            ))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetCaseParam(self, request, context=None):
        try:
            return self._resp(self.svc.get_case_param(request.param_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ListReferenceParams(self, request, context=None):
        try:
            return self._resp(self.svc.list_reference_params(
                algorithm_type=request.algorithm_type or None,
            ))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def ListMappings(self, request, context=None):
        try:
            return self._resp(self.svc.list_mappings(
                algorithm_type=request.algorithm_type or None,
                source_type=request.source_type or None,
                dimension_id=request.dimension_id or None,
            ))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetFormSchema(self, request, context=None):
        try:
            return self._resp(self.svc.get_form_schema(request.algo_type))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetAlgorithmDimensions(self, request, context=None):
        try:
            return self._resp(self.svc.get_algorithm_dimensions(request.algo_type))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")

    def GetDimensionParams(self, request, context=None):
        try:
            return self._resp(self.svc.get_dimension_params(request.dimension_id))
        except Exception as e:
            return task_pb.AlgorithmConfigResponse(success=False, message=str(e), data="")
