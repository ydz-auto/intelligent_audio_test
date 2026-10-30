# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的参数策略写方法 mixin。

RPC（proto：shared/proto/algorithm_service.proto）：
- SaveParamProfile / CloneParamProfile / DeleteParamProfile
- BindApiParamProfile（API 实例 ↔ 策略，profile_id 缺省/0 = 解绑）
- SaveApiScopeOverrides（按 api_id 原子保存实例覆盖行）

写成功后统一 ``_invalidate_cache()``：策略与绑定都在配置缓存的分桶里，
不刷新会让执行侧继续读到旧声明。
"""
from __future__ import annotations

from shared.utils.grpc_json import loads as _loads

from algorithm_service.application.handlers.param_profile_handlers import (
    ParamProfileCommandHandler,
)
from algorithm_service.interfaces.grpc.mixins.param_helpers import (
    _failure,
    _success,
    _ParamBaseMixin,
)


class _ParamProfileWriteMixin(_ParamBaseMixin):
    """参数策略写 RPC mixin。"""

    def SaveParamProfile(self, request, context=None):
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            detail = ParamProfileCommandHandler.save_profile(data)
            self._invalidate_cache()
            return _success(detail)
        except ValueError as exc:
            return _failure(str(exc))
        except Exception as exc:  # 唯一键冲突等基础设施异常统一回传
            return _failure(f'保存参数策略失败: {exc}')

    def CloneParamProfile(self, request, context=None):
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            detail = ParamProfileCommandHandler.clone_profile(
                data.get('source_profile_id') or data.get('sourceProfileId'),
                data.get('name') or '',
                data.get('description'),
            )
            self._invalidate_cache()
            return _success(detail)
        except (TypeError, ValueError) as exc:
            return _failure(str(exc))
        except Exception as exc:
            return _failure(f'克隆参数策略失败: {exc}')

    def DeleteParamProfile(self, request, context=None):
        try:
            deleted = ParamProfileCommandHandler.delete_profile(int(request.profile_id))
            if not deleted:
                return _failure('策略不存在或已删除')
            self._invalidate_cache()
            return _success({'profile_id': int(request.profile_id), 'deleted': True})
        except Exception as exc:
            return _failure(f'删除参数策略失败: {exc}')

    def BindApiParamProfile(self, request, context=None):
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            api_id = data.get('api_id') or data.get('apiId')
            if api_id is None:
                return _failure('api_id 必填')
            profile_id = data.get('profile_id', data.get('profileId'))
            result = ParamProfileCommandHandler.bind_api(int(api_id), profile_id)
            self._invalidate_cache()
            return _success(result)
        except (TypeError, ValueError) as exc:
            return _failure(str(exc))
        except Exception as exc:
            return _failure(f'绑定参数策略失败: {exc}')

    def SaveApiScopeOverrides(self, request, context=None):
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            api_id = data.get('api_id') or data.get('apiId')
            if api_id is None:
                return _failure('api_id 必填')
            counts = ParamProfileCommandHandler.save_api_overrides(
                int(api_id),
                data.get('algorithm_type') or data.get('algorithmType') or '',
                data.get('api_params') or data.get('apiParams') or [],
                data.get('mappings') or [],
            )
            self._invalidate_cache()
            return _success(counts)
        except (TypeError, ValueError) as exc:
            return _failure(str(exc))
        except Exception as exc:
            return _failure(f'保存 API 覆盖配置失败: {exc}')
