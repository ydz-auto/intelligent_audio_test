# -*- coding: utf-8 -*-
"""算法配置命令 Service（写侧 / CRUD）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 algorithm_service。
保留 Pydantic schema 校验。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.grpc_proxies import algorithm_config_service

from api_gateway.schemas.algorithm import (
    AlgorithmDefinitionCreate,
    AlgorithmDefinitionUpdate,
    AlgorithmDeviceParamCreate,
    AlgorithmDeviceParamUpdate,
    AlgorithmApiParamCreate,
    AlgorithmApiParamUpdate,
    CaseAlgorithmParamCreate,
    CaseAlgorithmParamUpdate,
    MappingCreateRequest,
    MappingUpdateRequest,
    ReferenceParamCreateRequest,
    ReferenceParamUpdateRequest,
    AssociateDimensionsRequest,
    DimensionRelationCreateRequest,
    DimensionRelationUpdateRequest,
    ExtractParamsRequest,
    AlgorithmImportRequest,
    BulkDeleteRequest,
)


class AlgorithmCommandService:
    # ========== 算法定义 CRUD ==========

    @staticmethod
    def create_algorithm():
        """创建算法定义"""
        try:
            req = AlgorithmDefinitionCreate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_algorithm(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Algorithm created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_algorithm(algo_type: str):
        """更新算法定义"""
        try:
            req = AlgorithmDefinitionUpdate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.update_algorithm(algo_type, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Algorithm updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_algorithm(algo_type: str):
        """删除算法定义（软删除）"""
        result = algorithm_config_service.delete_algorithm(algo_type)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Algorithm deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 参数 CRUD ==========

    @staticmethod
    def create_param():
        """创建参数（支持设备参数和API参数）"""
        json_data = request.get_json()
        param_type_source = json_data.get('param_type_source', 'device')

        if param_type_source == 'api':
            try:
                req = AlgorithmApiParamCreate.model_validate(json_data)
            except Exception as e:
                return error_response(f"请求数据验证失败: {str(e)}", 400)
        else:
            try:
                req = AlgorithmDeviceParamCreate.model_validate(json_data)
            except Exception as e:
                return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_param(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Parameter created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_param(param_id: int):
        """更新参数

        原实现需要先查 DB 判断 device / api 参数类型再选择 schema 校验，
        现在该判断逻辑下沉到微服务。网关侧直接把原始 JSON 传给代理。
        """
        data = request.get_json() or {}
        result = algorithm_config_service.update_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_param(param_id: int):
        """删除参数（软删除）"""
        result = algorithm_config_service.delete_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Parameter deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 映射 CRUD ==========

    @staticmethod
    def create_mapping():
        """创建参数映射"""
        try:
            req = MappingCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_mapping(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Mapping created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_mapping(mapping_id: int):
        """更新参数映射"""
        try:
            req = MappingUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.update_mapping(mapping_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Mapping updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_mapping(mapping_id: int):
        """删除参数映射"""
        result = algorithm_config_service.delete_mapping(mapping_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Mapping deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 用例专属参数 CRUD ==========

    @staticmethod
    def create_case_param():
        """创建用例专属参数"""
        try:
            req = CaseAlgorithmParamCreate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_case_param(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Case parameter created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_case_param(param_id: int):
        """更新用例专属参数"""
        try:
            req = CaseAlgorithmParamUpdate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.update_case_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Case parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_case_param(param_id: int):
        """删除用例专属参数"""
        result = algorithm_config_service.delete_case_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Case parameter deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 参考参数 CRUD ==========

    @staticmethod
    def create_reference_param():
        """创建参考参数"""
        try:
            req = ReferenceParamCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_reference_param(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Reference parameter created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_reference_param(param_id: int):
        """更新参考参数"""
        try:
            req = ReferenceParamUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.update_reference_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Reference parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_reference_param(param_id: int):
        """删除参考参数"""
        result = algorithm_config_service.delete_reference_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Reference parameter deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 维度关联 ==========

    @staticmethod
    def associate_dimensions(algo_type: str):
        """关联评估维度"""
        try:
            req = AssociateDimensionsRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.associate_dimensions(algo_type, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Dimensions associated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def create_dimension_relation():
        """创建单条维度关联"""
        try:
            req = DimensionRelationCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.create_dimension_relation(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Dimension relation created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_dimension_relation(relation_id: int):
        """更新单条维度关联"""
        try:
            req = DimensionRelationUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.update_dimension_relation(relation_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Dimension relation updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_dimension_relation(relation_id: int):
        """删除单条维度关联"""
        result = algorithm_config_service.delete_dimension_relation(relation_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Dimension relation deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 导入 / 批量 / 提取 ==========

    @staticmethod
    def import_algorithms():
        """导入算法配置"""
        try:
            req = AlgorithmImportRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.import_algorithms(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Import completed'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def bulk_delete():
        """批量删除算法"""
        try:
            req = BulkDeleteRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.bulk_delete(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Bulk delete completed'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def extract_params():
        """提取用例算法参数（供执行引擎使用）"""
        try:
            req = ExtractParamsRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = algorithm_config_service.extract_params(data)

        if result.get('success'):
            return success_response(result.get('data'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 配置热更新 ==========

    @staticmethod
    def reload_config():
        """重新加载配置（热更新）"""
        result = algorithm_config_service.reload_config()

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Config reloaded'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))
