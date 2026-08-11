# -*- coding: utf-8 -*-
"""algorithm_service 算法领域查询 gRPC servicer

CQRS 读侧 servicer，实现 AlgorithmQueryService。
委托 application/queries 层处理器，不直接 import PO 或 db.session。
"""
from __future__ import annotations

from typing import Any

from shared.proto import algorithm_service_pb2 as _pb
from shared.proto import algorithm_service_pb2_grpc as _pb_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


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


class AlgorithmQueryServicer(_pb_grpc.AlgorithmQueryServiceServicer):
    """算法领域查询 gRPC servicer（CQRS 读侧）。

    委托 application/queries 层处理器完成读取操作，不直接 import PO 或
    db.session。处理器实例按需懒加载。
    """

    def __init__(self) -> None:
        # 延迟导入，避免循环依赖与启动期开销
        self._config_handler = None
        self._field_mapping_handler = None
        self._result_field_mapping_handler = None
        self._case_parameter_handler = None
        self._reference_params_handler = None
        self._param_normalizer = None

    # ---- handler 懒加载 ----

    @property
    def config_handler(self):
        """配置加载器查询处理器"""
        if self._config_handler is None:
            from algorithm_service.application.queries.algorithm_config_queries import (
                AlgorithmConfigQueryHandler,
            )
            self._config_handler = AlgorithmConfigQueryHandler()
        return self._config_handler

    @property
    def field_mapping_handler(self):
        """字段映射器查询处理器"""
        if self._field_mapping_handler is None:
            from algorithm_service.application.queries.field_mapping_queries import (
                FieldMappingQueryHandler,
            )
            self._field_mapping_handler = FieldMappingQueryHandler()
        return self._field_mapping_handler

    @property
    def result_field_mapping_handler(self):
        """结果字段映射器查询处理器"""
        if self._result_field_mapping_handler is None:
            from algorithm_service.application.queries.result_field_mapping_queries import (
                ResultFieldMappingQueryHandler,
            )
            self._result_field_mapping_handler = ResultFieldMappingQueryHandler()
        return self._result_field_mapping_handler

    @property
    def case_parameter_handler(self):
        """用例参数提取器查询处理器"""
        if self._case_parameter_handler is None:
            from algorithm_service.application.queries.case_parameter_queries import (
                CaseParameterQueryHandler,
            )
            self._case_parameter_handler = CaseParameterQueryHandler()
        return self._case_parameter_handler

    @property
    def reference_params_handler(self):
        """参考参数生成器查询处理器"""
        if self._reference_params_handler is None:
            from algorithm_service.application.queries.reference_params_queries import (
                ReferenceParamsQueryHandler,
            )
            self._reference_params_handler = ReferenceParamsQueryHandler()
        return self._reference_params_handler

    @property
    def param_normalizer(self):
        """参数归一化领域服务"""
        if self._param_normalizer is None:
            from algorithm_service.domain.services.param_normalizer import (
                ParamNormalizerService,
            )
            self._param_normalizer = ParamNormalizerService()
        return self._param_normalizer

    # ============================================================
    # 配置加载器（原 algorithm_config_loader）
    # ============================================================

    def GetAlgorithmConfig(self, request, context=None):
        """获取算法配置（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_algorithm_config(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetAllAlgorithmsList(self, request, context=None):
        """获取全部算法列表。"""
        try:
            data = self.config_handler.get_all_algorithms()
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetAlgorithmParamsMerged(self, request, context=None):
        """获取算法合并参数（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_algorithm_params(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetDeviceParamsList(self, request, context=None):
        """获取设备参数列表（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_device_params(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetApiParamsList(self, request, context=None):
        """获取 API 参数列表（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_api_params(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetCaseParamsList(self, request, context=None):
        """获取用例参数列表（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_case_params(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetReferenceParamsList(self, request, context=None):
        """获取参考参数列表（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_reference_params(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetParamMappingForComponent(self, request, context=None):
        """获取组件参数映射（按 algorithm_type + component_type）。"""
        try:
            data = self.config_handler.get_param_mapping(
                request.algorithm_type, request.component_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetEvaluationDimensionParams(self, request, context=None):
        """获取评测维度参数（按 dimension_id）。"""
        try:
            data = self.config_handler.get_evaluation_dimension_params(
                int(request.dimension_id)
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetAlgorithmDefinitionInfo(self, request, context=None):
        """获取算法定义信息（按 algorithm_type）。"""
        try:
            data = self.config_handler.get_algorithm_definition(request.algorithm_type)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def ReloadConfig(self, request, context=None):
        """重新加载配置，返回 {success, reload_time}。"""
        try:
            self.config_handler.reload_config()
            reload_time = self.config_handler.get_last_reload_time()
            return _success({"success": True, "reload_time": reload_time})
        except Exception as e:
            return _failure(str(e))

    # ============================================================
    # 字段映射器（原 field_mapper）
    # ============================================================

    def GetFieldMappings(self, request, context=None):
        """获取字段映射定义（按 algorithm_type）。"""
        try:
            data = self.field_mapping_handler.get_field_definitions(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetEvaluationFieldMappings(self, request, context=None):
        """获取评测输出字段映射（按 algorithm_type）。"""
        try:
            data = self.field_mapping_handler.get_evaluation_output_fields(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def BuildApiRequestData(self, request, context=None):
        """构建 API 请求数据。

        解析 request.data JSON 为 device_params + api_params + case_config + kwargs，
        调用 FieldMappingQueryHandler.build_api_request_data(...)。
        """
        try:
            payload = _loads(request.data, {})
            device_params = payload.get("device_params")
            api_params = payload.get("api_params")
            case_config = payload.get("case_config")
            kwargs = payload.get("kwargs") or {}
            data = self.field_mapping_handler.build_api_request_data(
                device_params, api_params, case_config, **kwargs
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def ConvertFieldValue(self, request, context=None):
        """转换字段值。

        解析 request.data 中的 value，调用
        FieldMappingQueryHandler.convert_field_value(transform_type, value)。
        """
        try:
            payload = _loads(request.data, {})
            value = payload.get("value")
            data = self.field_mapping_handler.convert_field_value(
                request.transform_type, value
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    # ============================================================
    # 结果字段映射器（原 algorithm_result_field_mapper）
    # ============================================================

    def GetOutputFields(self, request, context=None):
        """获取输出字段（按 algorithm_type + 可选 test_type）。"""
        try:
            test_type = request.test_type or None
            data = self.result_field_mapping_handler.get_output_fields(
                request.algorithm_type, test_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetReferenceOutputFields(self, request, context=None):
        """获取参考输出字段（按 algorithm_type）。"""
        try:
            data = self.result_field_mapping_handler.get_reference_output_fields(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def ExtractResultFields(self, request, context=None):
        """提取结果字段。

        解析 algorithm_result 与 result_data JSON，调用
        ResultFieldMappingQueryHandler.extract_all_result_fields(...)。
        """
        try:
            algorithm_result = _loads(request.algorithm_result, {})
            result_data = _loads(request.result_data, {})
            data = self.result_field_mapping_handler.extract_all_result_fields(
                algorithm_result, result_data
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetTimelineFields(self, request, context=None):
        """获取时间线字段（按 algorithm_type）。"""
        try:
            data = self.result_field_mapping_handler.get_timeline_fields(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetFullFieldMapping(self, request, context=None):
        """获取完整字段映射（按 algorithm_type）。"""
        try:
            data = self.result_field_mapping_handler.get_field_mapping(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def MapApiResults(self, request, context=None):
        """映射 API 结果。

        解析 raw_results JSON，调用
        ResultFieldMappingQueryHandler.map_api_results(...)。
        """
        try:
            raw_results = _loads(request.raw_results, {})
            data = self.result_field_mapping_handler.map_api_results(raw_results)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def ExtractRoundResults(self, request, context=None):
        """提取单轮结果。

        解析 algorithm_result JSON，调用
        ResultFieldMappingQueryHandler.extract_round_results(...)。
        """
        try:
            algorithm_result = _loads(request.algorithm_result, {})
            data = self.result_field_mapping_handler.extract_round_results(
                algorithm_result
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    # ============================================================
    # 用例参数提取器（原 case_parameter_extractor）
    # ============================================================

    def ExtractCaseAllParams(self, request, context=None):
        """提取用例全部参数。

        解析 case_config JSON，调用
        CaseParameterQueryHandler.get_all_params(...)。
        """
        try:
            case_config = _loads(request.case_config, {})
            data = self.case_parameter_handler.get_all_params(case_config)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def NormalizeAlgorithmParams(self, request, context=None):
        """归一化算法参数（返回 dict）。

        解析 algorithm_params JSON，调用
        ParamNormalizerService.normalize_algorithm_params(...)。
        """
        try:
            algorithm_params = _loads(request.algorithm_params, {})
            data = self.param_normalizer.normalize_algorithm_params(algorithm_params)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def NormalizeAlgorithmParamsToList(self, request, context=None):
        """归一化算法参数（返回 list）。

        解析 algorithm_params JSON，调用
        ParamNormalizerService.normalize_algorithm_params_to_list(...)。
        """
        try:
            algorithm_params = _loads(request.algorithm_params, {})
            data = self.param_normalizer.normalize_algorithm_params_to_list(
                algorithm_params
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetRoundAlgoParams(self, request, context=None):
        """获取指定轮次算法参数。

        解析 algorithm_params_col JSON，调用
        ParamNormalizerService.get_round_algo_params(..., round_number)。
        """
        try:
            algorithm_params_col = _loads(request.algorithm_params_col, {})
            data = self.param_normalizer.get_round_algo_params(
                algorithm_params_col, request.round_number
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetAlgoParam(self, request, context=None):
        """获取单个算法参数。

        解析 algorithm_params JSON，调用
        ParamNormalizerService.get_algo_param(..., field_code)。
        """
        try:
            algorithm_params = _loads(request.algorithm_params, {})
            data = self.param_normalizer.get_algo_param(
                algorithm_params, request.field_code
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def BuildCaseFormSchema(self, request, context=None):
        """构建用例表单 schema（按 algorithm_type）。"""
        try:
            data = self.case_parameter_handler.build_form_schema(
                request.algorithm_type
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    # ============================================================
    # 参考参数生成器（原 reference_params_generator）
    # ============================================================

    def GenerateReferenceParams(self, request, context=None):
        """生成参考参数。

        解析 request.data JSON 为 {test_case_config, round_data}，调用
        ReferenceParamsQueryHandler.generate_for_round(...)。
        """
        try:
            payload = _loads(request.data, {})
            test_case_config = payload.get("test_case_config")
            round_data = payload.get("round_data")
            data = self.reference_params_handler.generate_for_round(
                test_case_config, round_data
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def LoadReferenceParamsFile(self, request, context=None):
        """从文件加载参考参数（按 filepath）。"""
        try:
            data = self.reference_params_handler.load_from_file(request.filepath)
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetReferenceTextValue(self, request, context=None):
        """获取参考文本值。

        解析 reference_params_col JSON，调用
        ReferenceParamsQueryHandler.get_reference_text(..., code)。
        """
        try:
            reference_params_col = _loads(request.reference_params_col, {})
            data = self.reference_params_handler.get_reference_text(
                reference_params_col, request.code
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetAllReferenceParams(self, request, context=None):
        """获取全部参考参数。

        解析 reference_params_col JSON，调用
        ReferenceParamsQueryHandler.get_all_reference_params(...)。
        """
        try:
            reference_params_col = _loads(request.reference_params_col, {})
            data = self.reference_params_handler.get_all_reference_params(
                reference_params_col
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))

    def GetReferenceParamsForReport(self, request, context=None):
        """获取用于报告的参考参数。

        解析 reference_params_col JSON，调用
        ReferenceParamsQueryHandler.get_reference_params_for_report(...)。
        """
        try:
            reference_params_col = _loads(request.reference_params_col, {})
            data = self.reference_params_handler.get_reference_params_for_report(
                reference_params_col
            )
            return _success(data)
        except Exception as e:
            return _failure(str(e))
