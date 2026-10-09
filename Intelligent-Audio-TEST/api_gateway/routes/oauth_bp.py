"""OAuth 提供方路由 — interfaces 层（INT-51 登录体系改造）

公开端点（白名单）：登录页提供方列表 / 授权跳转 / 授权回调。
管理端点（require_permission）：提供方 CRUD（client_secret 掩去）。
"""
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.auth.management_common import (
    current_operator_id,
)
from api_gateway.application.services.auth.oauth_provider_service import (
    OAuthProviderService,
    OAuthProviderError,
)
from api_gateway.config.config import Config
from api_gateway.routes._response import to_response

router = APIRouter()

# OAuth 回调成功/失败后跳转的前端页面（hash 路由，token 只在 # 后不出网）
_FRONTEND_OAUTH_REDIRECT = '{base}/#/login?oauth_token={token}'
_FRONTEND_OAUTH_ERROR = '{base}/#/login?oauth_error={error}'


def _callback_redirect_uri(slug: str) -> str:
    """提供方回调地址（OAUTH_REDIRECT_BASE + slug 拼接）。"""
    return f'{Config.OAUTH_REDIRECT_BASE.rstrip("/")}/api/v1/auth/oauth/{slug}/callback'


# ---- 公开端点（AuthMiddleware 白名单 /api/v1/auth/oauth 前缀） ----

@router.get('/oauth/providers')
def list_public_providers():
    """已启用提供方列表（登录页动态渲染，无凭证字段）"""
    return to_response({'providers': OAuthProviderService.list_public_providers()})


@router.get('/oauth/{slug}/authorize')
def oauth_authorize(slug: str):
    """302 跳转到提供方授权页（state 短时效签名防 CSRF）"""
    config = OAuthProviderService.get_provider_config(slug)
    if config is None:
        return RedirectResponse(url=_FRONTEND_OAUTH_ERROR.format(
            base=Config.OAUTH_REDIRECT_BASE.rstrip('/'),
            error=quote(f'OAuth 提供方不存在或未启用: {slug}')))
    authorize_url = OAuthProviderService.build_authorize_url(
        config, _callback_redirect_uri(slug))
    return RedirectResponse(url=authorize_url)


@router.get('/oauth/{slug}/callback')
def oauth_callback(slug: str, code: str = Query(...),
                   state: str = Query('')):
    """授权回调：换 token → userinfo → 字段映射 → 查/建用户 → 签发 JWT"""
    from api_gateway.application.services.auth.auth_service import AuthService
    base = Config.OAUTH_REDIRECT_BASE.rstrip('/')
    try:
        user_info = OAuthProviderService.handle_callback(
            slug, code, state, _callback_redirect_uri(slug))
        result = AuthService._issue_token(user_info, provider=slug)
    except OAuthProviderError as e:
        return RedirectResponse(url=_FRONTEND_OAUTH_ERROR.format(
            base=base, error=quote(str(e))))
    except PermissionError as e:
        return RedirectResponse(url=_FRONTEND_OAUTH_ERROR.format(
            base=base, error=quote(str(e))))
    except Exception as e:  # noqa: BLE001 — 外部 IdP 异常统一收敛为登录失败
        return RedirectResponse(url=_FRONTEND_OAUTH_ERROR.format(
            base=base, error=quote(f'OAuth 登录失败: {e}')))
    return RedirectResponse(url=_FRONTEND_OAUTH_REDIRECT.format(
        base=base, token=quote(result['access_token'])))


# ---- 管理端点（admin） ----

@router.get('/oauth-providers')
def list_providers(_: None = require_permission('auth:manage_provider')):
    """全部提供方（含禁用；client_secret 掩去）"""
    return to_response(OAuthProviderService.list_providers())


@router.get('/oauth-providers/{provider_id}')
def get_provider(provider_id: int,
                 _: None = require_permission('auth:manage_provider')):
    """提供方详情（client_secret 掩去）"""
    return to_response(OAuthProviderService.get_provider(provider_id))


@router.post('/oauth-providers')
def create_provider(request: Request,
                    _: None = require_permission('auth:manage_provider')):
    """创建提供方（name/slug/client_id/client_secret/三端点必填）"""
    return to_response(OAuthProviderService.create_provider(
        _json_body(request), current_operator_id()))


@router.put('/oauth-providers/{provider_id}')
def update_provider(provider_id: int, request: Request,
                    _: None = require_permission('auth:manage_provider')):
    """更新提供方（body 键缺省=不修改；client_secret 空串=保留原值）"""
    return to_response(OAuthProviderService.update_provider(
        provider_id, _json_body(request), current_operator_id()))


@router.delete('/oauth-providers/{provider_id}')
def delete_provider(provider_id: int,
                    _: None = require_permission('auth:manage_provider')):
    """删除提供方"""
    return to_response(OAuthProviderService.delete_provider(
        provider_id, current_operator_id()))


def _json_body(request: Request) -> dict:
    """预解析 JSON body（RequestAdapterMiddleware 注入）。"""
    body = getattr(request.state, '_json_body', None)
    return body if isinstance(body, dict) else {}
