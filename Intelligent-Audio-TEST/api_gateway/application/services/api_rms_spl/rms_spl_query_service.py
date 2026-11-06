# -*- coding: utf-8 -*-
"""数字域 RMS→SPL 映射查询 Service（读侧 / UC-0902）。

网关不直接操作 DB，经 ACL 走 gRPC 调用 api_test_service.ApiRmsSplConfigService。
保留对路由层的签名约定（静态方法 + success_response/error_response 包装）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.query_validator import (
    IntParamRule,
    QueryParamValidationError,
    parse_int_args,
)
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import ApiRmsSplConfigAclRepositoryImpl


_rms_spl_acl = ApiRmsSplConfigAclRepositoryImpl()

# 列表端点 query 参数清洗规则（INT-165）：缺省值与钳制区间集中声明
_LIST_INT_RULES = (
    IntParamRule('page', default=1, min_value=1),
    # per_page 钳制 [1,100]，防止超大分页拖垮列表查询
    IntParamRule('per_page', default=10, min_value=1, max_value=100),
    IntParamRule('api_id', default=None),
)


class RmsSplQueryService:
    """数字域 RMS→SPL 映射读操作 Service —— 通过 gRPC 代理调用微服务"""

    @staticmethod
    def get_all():
        params = request.args
        try:
            parsed = parse_int_args(params, _LIST_INT_RULES)
        except QueryParamValidationError as exc:
            return error_response(
                str(exc), code=ErrorCode.INVALID_TYPE,
                detail={'param': exc.param, 'value': exc.value},
            )
        result = _rms_spl_acl.get_all(
            page=parsed['page'],
            per_page=parsed['per_page'],
            api_id=parsed['api_id'],
            calibration_status=params.get('calibration_status') or None,
        )
        if not result.success:
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')

    @staticmethod
    def get_one(mapping_id: int):
        result = _rms_spl_acl.get_one(mapping_id)
        if not result.success:
            code = result.code or 400
            if code == 404:
                return error_response(result.message or '未找到映射记录', code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')

    @staticmethod
    def get_by_api(api_id: int):
        result = _rms_spl_acl.get_by_api(api_id)
        if not result.success:
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')
