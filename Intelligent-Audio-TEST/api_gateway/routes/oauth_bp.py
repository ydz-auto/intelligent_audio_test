"""OAuth 提供方路由 — interfaces 层（INT-51 登录体系改造）

公开端点（白名单）：登录页提供方列表 / 授权跳转 / 授权回调。
管理端点（require_permission）：提供方 CRUD（client_secret 掩去）。
绑定/发现端点（INT-147）：位于 /oauth 公开前缀内，路由内自解析
Authorization Bearer 校验用户态（白名单路径中间件不注入登录态）。
"""
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

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
# intent=bind 绑定票据回传页面（INT-147）
_FRONTEND_BIND_REDIRECT = '{base}/#/AccountSettings?bind_ticket={ticket}'
_FRONTEND_BIND_ERROR = '{base}/#/AccountSettings?bind_error={error}'


def _callback_redirect_uri(slug: str) -> str:
    """提供方回调地址（OAUTH_REDIRECT_BASE + slug 拼接）。"""
    return f'{Config.OAUTH_REDIRECT_BASE.rstrip("/")}/api/v1/auth/oauth/{slug}/callback'


# ---- 公开端点（AuthMiddleware 白名单 /api/v1/auth/oauth 前缀） ----

@router.get('/oauth/providers')
def list_public_providers():
    """已启用提供方列表（登录页动态渲染，无凭证字段）"""
    return to_response({'providers': OAuthProviderService.list_public_providers()})


@router.get('/oauth/{slug}/authorize')
def oauth_authorize(slug: str, intent: str = Query('login')):
    """302 跳转到提供方授权页（state 短时效签名防 CSRF，携带 intent）。

    intent=bind（INT-147）：第三方账号绑定流程入口；非法值按 login。
    """
    if intent not in ('login', 'bind'):
        intent = 'login'
    config = OAuthProviderService.get_provider_config(slug)
    if config is None:
        return RedirectResponse(url=_FRONTEND_OAUTH_ERROR.format(
            base=Config.OAUTH_REDIRECT_BASE.rstrip('/'),
            error=quote(f'OAuth 提供方不存在或未启用: {slug}')))
    authorize_url = OAuthProviderService.build_authorize_url(
        config, _callback_redirect_uri(slug), intent=intent)
    return RedirectResponse(url=authorize_url)


@router.get('/oauth/{slug}/callback')
def oauth_callback(slug: str, code: str = Query(...),
                   state: str = Query('')):
    """授权回调：换 token → userinfo → 字段映射 → 查/建用户 → 签发 JWT。

    state 携带 intent=bind 时（INT-147）不签发登录 token，改为回传
    绑定票据到账号设置页，由前端携登录态完成绑定落库。
    """
    from api_gateway.application.services.auth.auth_service import AuthService
    base = Config.OAUTH_REDIRECT_BASE.rstrip('/')
    try:
        intent = OAuthProviderService.verify_state_intent(state, slug)
        if intent == 'bind':
            return _bind_callback(slug, code, state, base)
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


def _bind_callback(slug: str, code: str, state: str, base: str):
    """intent=bind 回调分支：验真第三方身份 → 签绑定票据回传前端。"""
    config = OAuthProviderService.get_provider_config(slug)
    if config is None or not config.get('id'):
        # 环境变量回退的预置提供方无 DB 行（id=0），绑定无归属
        return RedirectResponse(url=_FRONTEND_BIND_ERROR.format(
            base=base, error=quote('预置提供方（环境配置回退）不支持账号绑定')))
    user_info = OAuthProviderService.handle_callback(
        slug, code, state, _callback_redirect_uri(slug), intent='bind')
    ticket = OAuthProviderService.sign_bind_ticket(
        provider_id=config['id'], slug=slug,
        provider_user_id=user_info.external_id,
        display_name=user_info.display_name or '')
    return RedirectResponse(url=_FRONTEND_BIND_REDIRECT.format(
        base=base, ticket=quote(ticket)))


# ---- 第三方账号绑定（INT-147；公开前缀内路由内自校验用户态） ----

@router.get('/oauth/bindings')
def list_oauth_bindings(request: Request):
    """当前用户第三方账号绑定列表（对齐旧库 GET /oauth/bindings）"""
    user_id, _ = _request_user_context(request)
    if not user_id:
        return JSONResponse(status_code=401, content={'detail': '未登录'})
    from api_gateway.application.services.auth.oauth_binding_service import (
        OAuthBindingGatewayService,
    )
    return to_response(OAuthBindingGatewayService.list_bindings(user_id))


@router.post('/oauth/bindings')
def create_oauth_binding(request: Request):
    """携绑定票据完成绑定（对齐旧库 intent=bind 落库语义，幂等）"""
    user_id, _ = _request_user_context(request)
    if not user_id:
        return JSONResponse(status_code=401, content={'detail': '未登录'})
    from api_gateway.application.services.auth.oauth_binding_service import (
        OAuthBindingGatewayService,
    )
    bind_ticket = (_json_body(request).get('bind_ticket') or '')
    return to_response(OAuthBindingGatewayService.complete_bind(
        user_id, bind_ticket))


@router.delete('/oauth/bindings/{provider_id}')
def delete_oauth_binding(provider_id: int, request: Request):
    """解绑指定提供方（幂等，对齐旧库 DELETE /oauth/bindings/{id}）"""
    user_id, _ = _request_user_context(request)
    if not user_id:
        return JSONResponse(status_code=401, content={'detail': '未登录'})
    from api_gateway.application.services.auth.oauth_binding_service import (
        OAuthBindingGatewayService,
    )
    return to_response(OAuthBindingGatewayService.unbind(user_id, provider_id))


@router.post('/oauth/admin/discovery')
def fetch_oauth_discovery(request: Request):
    """OIDC Discovery 拉取（对齐旧库 POST /oauth/admin/discovery，admin）。

    供自定义提供方管理页按 issuer 自动填充端点配置。
    """
    user_id, permissions = _request_user_context(request)
    if not user_id:
        return JSONResponse(status_code=401, content={'detail': '未登录'})
    if '*' not in (permissions or []) and 'auth:manage_provider' not in (permissions or []):
        return JSONResponse(
            status_code=403,
            content={'detail': '缺少权限: auth:manage_provider'})
    return to_response(OAuthProviderService.fetch_discovery(_json_body(request)))


def _request_user_context(request: Request):
    """绑定/发现端点用户态解析（INT-147）。

    端点位于 /api/v1/auth/oauth 公开前缀内，AuthMiddleware 白名单跳过
    JWT 解析；优先解析 Authorization Bearer（登录用户必然携带），无
    token 时回退中间件注入的 request.state（AUTH_MODE=off 语义）。
    """
    from api_gateway.application.services.auth.token_service import TokenService
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            payload = TokenService.verify(auth_header[7:])
            return (int(payload.get('user_id', 0) or 0),
                    list(payload.get('permissions', []) or []))
        except Exception:
            return 0, []
    return (int(getattr(request.state, 'user_id', 0) or 0),
            list(getattr(request.state, 'permissions', []) or []))


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
