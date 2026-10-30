# -*- coding: utf-8 -*-
"""参数策略网关服务（读 / 写）。

- 策略是「字段声明 + 映射」的可复用模板，API 实例经 api_id 绑定引用；
- 实例差异走 ``/api-scope/{api_id}/overrides``（原子保存，不碰策略行）。

网关只做 HTTP 入参校验与权限边界，落库在 algorithm_service（gRPC）。
"""
from __future__ import annotations

from api_gateway.application.services.algorithm.algorithm_command_service import (
    _validate_api_scope,
)
from api_gateway.infrastructure.grpc_proxies.algorithm_proxies import (
    algorithm_query_service as _algo_proxy,
)
from api_gateway.infrastructure.request_adapter import request
from api_gateway.schemas._algorithm_api_param_schemas import (
    ApiScopedConfigSaveRequest,
    ParamProfileBindRequest,
    ParamProfileCloneRequest,
    ParamProfileListQuery,
    ParamProfileSaveRequest,
)
from api_gateway.utils.response import error_response, success_response


def _parse_query(model_cls):
    params = {k: v[0] if isinstance(v, list) else v
              for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


def _respond(result, default_message: str):
    if result.get('success'):
        return success_response(result.get('data'), result.get('message') or default_message)
    return error_response(result.get('message') or '操作失败', result.get('code') or 400)


class AlgorithmProfileService:
    """策略 CRUD + 绑定 + 实例覆盖。"""

    # ---- 读 ----

    @staticmethod
    def list_profiles():
        query = _parse_query(ParamProfileListQuery)
        result = _algo_proxy.list_param_profiles(
            algorithm_type=query.algorithm_type, scope=query.scope)
        return _respond(result, '查询成功')

    @staticmethod
    def get_profile(profile_id: int):
        result = _algo_proxy.get_param_profile(profile_id)
        return _respond(result, '查询成功')

    # ---- 策略写 ----

    @staticmethod
    def create_profile():
        try:
            req = ParamProfileSaveRequest.model_validate(request.get_json() or {})
        except Exception as exc:
            return error_response(f'请求数据验证失败: {exc}', 400)
        result = _algo_proxy.save_param_profile(req.model_dump())
        return _respond(result, '策略已保存')

    @staticmethod
    def update_profile(profile_id: int):
        try:
            req = ParamProfileSaveRequest.model_validate(request.get_json() or {})
        except Exception as exc:
            return error_response(f'请求数据验证失败: {exc}', 400)
        payload = req.model_dump()
        payload['id'] = int(profile_id)
        result = _algo_proxy.save_param_profile(payload)
        return _respond(result, '策略已保存')

    @staticmethod
    def clone_profile(profile_id: int):
        try:
            req = ParamProfileCloneRequest.model_validate(request.get_json() or {})
        except Exception as exc:
            return error_response(f'请求数据验证失败: {exc}', 400)
        result = _algo_proxy.clone_param_profile(
            profile_id, req.name, req.description)
        return _respond(result, '策略已克隆')

    @staticmethod
    def delete_profile(profile_id: int):
        result = _algo_proxy.delete_param_profile(profile_id)
        return _respond(result, '策略已删除')

    # ---- 绑定 / 实例覆盖 ----

    @staticmethod
    def bind_api(api_id: int):
        try:
            req = ParamProfileBindRequest.model_validate(request.get_json() or {})
        except Exception as exc:
            return error_response(f'请求数据验证失败: {exc}', 400)
        scope_error = _validate_api_scope(api_id, None)
        if scope_error is not None:
            return scope_error
        result = _algo_proxy.bind_api_param_profile(api_id, req.profile_id)
        return _respond(result, '绑定已保存')

    @staticmethod
    def save_api_overrides(api_id: int):
        try:
            req = ApiScopedConfigSaveRequest.model_validate(request.get_json() or {})
        except Exception as exc:
            return error_response(f'请求数据验证失败: {exc}', 400)
        scope_error = _validate_api_scope(api_id, req.algorithm_type)
        if scope_error is not None:
            return scope_error
        result = _algo_proxy.save_api_scope_overrides(
            api_id, req.algorithm_type, req.api_params, req.mappings)
        return _respond(result, 'API 参数配置已保存')
