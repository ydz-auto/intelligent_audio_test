# -*- coding: utf-8 -*-
"""算法配置命令 Service（写侧 / CRUD）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 algorithm_service。
保留 Pydantic schema 校验。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import AlgorithmConfigAclRepositoryImpl

from api_gateway.schemas.algorithm import (
    AlgorithmDefinitionCreate,
    AlgorithmDefinitionSaveRequest,
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
from api_gateway.infrastructure.grpc_proxies.algorithm_proxies import (
    algorithm_query_service as _algorithm_service_proxy,
)
from api_gateway.infrastructure.grpc_proxies.api_config_proxies import (
    api_config_service,
)


_algorithm_acl = AlgorithmConfigAclRepositoryImpl()

logger = logging.getLogger(__name__)


def _validate_api_scope(api_id, algorithm_type):
    """写路径校验 ``api_id`` 作用域（INT-1756 C6a）。

    两张参数表的 ``api_id`` 指向 api_test_service 的 ``apis.id``，跨服务 DB 外键
    违反架构红线（父卡 INT-1751 硬错 1），存在性与归属只能在网关写路径保证：

    - ``api_id`` 为空 → 算法类型级默认，不校验；
    - 对应 API 不存在 → 400；
    - API 的 ``algorithm_type`` 与参数行不一致 → 400。

    返回 ``error_response(...)``，通过则返回 None。
    """
    if api_id is None:
        return None
    # 更新路径的载荷是裸 JSON（无 schema 兜底），非法值必须落 400 而不是
    # 未捕获的 ValueError/TypeError（审计 P3-1）。
    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        return error_response(f"api_id={api_id!r} 非法：应为正整数", 400)
    if api_id_int < 1:
        return error_response(f"api_id={api_id!r} 非法：应为正整数", 400)
    result = api_config_service.get_one(api_id_int) or {}
    data = result.get('data') or {}
    if not result.get('success') or not data:
        return error_response(
            f"api_id={api_id} 对应的 API 不存在或查询失败: "
            f"{result.get('message') or ''}", 400)
    api_algorithm_type = data.get('algorithm_type')
    if (algorithm_type and api_algorithm_type
            and str(api_algorithm_type) != str(algorithm_type)):
        return error_response(
            f"api_id={api_id} 属于算法类型 {api_algorithm_type}，"
            f"与 algorithm_type={algorithm_type} 不一致", 400)
    return None


def _clear_definition_draft(algo_type):
    """发布（新建/更新）或删除成功后清除该类型的草稿快照（INT-1514）。

    清除失败只记日志、不改变主操作结果——与 algorithm_service
    `handle_save_definition`「草稿清除失败不阻断发布」同口径；
    残留快照会在下次发布/删除时再次被清除。
    """
    if not algo_type:
        return
    try:
        result = _algorithm_service_proxy.clear_algorithm_definition_draft(algo_type)
    except Exception as e:  # 代理层已兜底，双保险
        logger.warning('清除算法草稿异常 algorithm_type=%s: %s', algo_type, e)
        return
    if not result.get('success'):
        logger.warning(
            '清除算法草稿失败 algorithm_type=%s: %s',
            algo_type, result.get('message'),
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
        result = _algorithm_acl.create_algorithm(data)

        if result.get('success'):
            # 新建同类型的算法时丢弃历史草稿快照，避免重开编辑回显旧草稿
            _clear_definition_draft(data.get('type') or data.get('algorithm_type'))
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
        result = _algorithm_acl.update_algorithm(algo_type, data)

        if result.get('success'):
            # 发布成功后清除草稿快照（INT-1514，与 clear_snapshot 口径一致）
            _clear_definition_draft(algo_type)
            return success_response(result.get('data'), result.get('message', 'Algorithm updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_algorithm(algo_type: str):
        """删除算法定义（软删除）"""
        result = _algorithm_acl.delete_algorithm(algo_type)

        if result.get('success'):
            # 算法删除级联清草稿，避免残留行指向已软删算法（INT-1514）
            _clear_definition_draft(algo_type)
            return success_response(result.get('data'), result.get('message', 'Algorithm deleted'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 算法定义全量保存 / 草稿（INT-589）==========

    @staticmethod
    def save_definition():
        """算法定义全量保存（聚合事务 + 乐观锁）。

        一次提交完整定义 + 六类子实体原子落库；并发覆盖返回 CONFLICT。
        """
        try:
            req = AlgorithmDefinitionSaveRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        if not data.get('algorithm_type'):
            data['algorithm_type'] = data.get('type')
        result = _algorithm_service_proxy.save_algorithm_definition(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Algorithm saved'))

        # 乐观锁冲突：409 + 机器可读 code 供前端分支提示
        if result.get('code') == 'CONFLICT':
            return error_response(
                '有他人改动，请刷新后重试',
                code=409, http_code=409, detail={'code': 'CONFLICT'},
            )
        if result.get('code') == 'VALIDATION_FAILED':
            return error_response(
                result.get('message', '校验失败'),
                code=422, http_code=422, detail={'code': 'VALIDATION_FAILED'},
            )
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def save_definition_draft():
        """草稿自动保存（30s 快照，不落正式六表）。"""
        json_data = request.get_json() or {}
        if not (json_data.get('algorithm_type') or json_data.get('type')):
            return error_response('algorithm_type 必填', 400)
        result = _algorithm_service_proxy.save_algorithm_definition_draft(json_data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Draft saved'))
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

        if param_type_source == 'api':
            scope_error = _validate_api_scope(
                getattr(req, 'api_id', None), getattr(req, 'algorithm_type', None))
            if scope_error is not None:
                return scope_error

        data = req.model_dump(by_alias=False, exclude_none=True)
        # 判别键必须显式回写：schema 是 extra="ignore"，param_type_source 不在字段里
        # 会被 model_dump 丢掉，algorithm_service 于是回落 "device" —— 带 api_id 的
        # 「API 参数」会被建进 algorithm_device_params（该表无 api_id 列，被静默忽略）。
        data['param_type_source'] = param_type_source
        result = _algorithm_acl.create_param(data)

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
        # INT-1756：载荷带 api_id 时校验作用域（更新载荷不含 algorithm_type 时
        # 只校验 API 存在性，类型一致性由创建/整份保存路径保证）
        scope_error = _validate_api_scope(
            data.get('api_id', data.get('apiId')), data.get('algorithm_type'))
        if scope_error is not None:
            return scope_error
        result = _algorithm_acl.update_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_param(param_id: int):
        """删除参数（软删除）"""
        result = _algorithm_acl.delete_param(param_id)

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

        scope_error = _validate_api_scope(
            getattr(req, 'api_id', None), req.algorithm_type)
        if scope_error is not None:
            return scope_error

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _algorithm_acl.create_mapping(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Mapping created'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update_mapping(mapping_id: int):
        """更新参数映射"""
        json_data = request.get_json() or {}
        try:
            req = MappingUpdateRequest.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        scope_error = _validate_api_scope(
            json_data.get('api_id', json_data.get('apiId')),
            json_data.get('algorithm_type'))
        if scope_error is not None:
            return scope_error

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _algorithm_acl.update_mapping(mapping_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Mapping updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_mapping(mapping_id: int):
        """删除参数映射"""
        result = _algorithm_acl.delete_mapping(mapping_id)

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
        result = _algorithm_acl.create_case_param(data)

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
        result = _algorithm_acl.update_case_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Case parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_case_param(param_id: int):
        """删除用例专属参数"""
        result = _algorithm_acl.delete_case_param(param_id)

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
        result = _algorithm_acl.create_reference_param(data)

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
        result = _algorithm_acl.update_reference_param(param_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Reference parameter updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_reference_param(param_id: int):
        """删除参考参数"""
        result = _algorithm_acl.delete_reference_param(param_id)

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
        result = _algorithm_acl.associate_dimensions(algo_type, data)

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
        result = _algorithm_acl.create_dimension_relation(data)

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
        result = _algorithm_acl.update_dimension_relation(relation_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Dimension relation updated'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete_dimension_relation(relation_id: int):
        """删除单条维度关联"""
        result = _algorithm_acl.delete_dimension_relation(relation_id)

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
        result = _algorithm_acl.import_algorithms(data)

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
        result = _algorithm_acl.bulk_delete(data)

        if result.get('success'):
            # 只清实际被删的类型（未删成功的保留其草稿），级联清残留快照
            payload = result.get('data') or {}
            deleted_types = payload.get('deleted_types') or data.get('algorithm_types') or []
            for algo_type in deleted_types:
                _clear_definition_draft(algo_type)
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
        result = _algorithm_acl.extract_params(data)

        if result.get('success'):
            return success_response(result.get('data'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    # ========== 配置热更新 ==========

    @staticmethod
    def reload_config():
        """重新加载配置（热更新）"""
        result = _algorithm_acl.reload_config()

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'Config reloaded'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))
