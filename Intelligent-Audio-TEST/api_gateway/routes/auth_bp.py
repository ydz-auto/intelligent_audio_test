"""
认证路由 — interfaces 层

对齐 DDD 重构方案第八章「auth_bp 路由」。
登录/回调/登出/刷新/获取当前用户信息/登录密码加密公钥（INT-147）。
"""
import logging

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse

from api_gateway.application.services.auth.auth_service import AuthService
from api_gateway.config.config import Config
from api_gateway.routes._response import to_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/login/encryption-key')
def encryption_key():
    """登录密码加密公钥下发（INT-147 对齐旧库 GET /auth/encryption-key）。

    挂 /login 前缀下以复用 AuthMiddleware 登录白名单（登录/注册前无
    token，须免认证可达）。加密开关关闭时返回 {enabled: false}，前端
    回退明文提交。
    """
    return _encryption_key_payload()


@router.get('/encryption-key')
def encryption_key_alias():
    """旧库路径别名 GET /auth/encryption-key（INT-179）。

    对齐旧库公开端点路径：白名单含 /api/v1/auth/encryption-key，与
    /login/encryption-key 同源同响应，旧脚本/人工联调不因路径断代 401。
    """
    return _encryption_key_payload()


def _encryption_key_payload():
    from api_gateway.application.services.auth.password_encryption import (
        PasswordEncryptionService,
    )
    if not Config.AUTH_PASSWORD_ENCRYPTION_ENABLED:
        return to_response({'enabled': False})
    try:
        public_key_pem, kid = PasswordEncryptionService.get_public_key_info(
            Config.AUTH_RSA_KEY_PATH)
    except Exception:  # noqa: BLE001 — 密钥不可用收敛为 500，固定文案不暴露细节
        logger.warning('登录加密公钥加载失败', exc_info=True)
        return JSONResponse(status_code=500,
                            content={'detail': '登录加密公钥不可用'})
    payload = {'enabled': True, 'kid': kid, 'public_key': public_key_pem}
    # INT-245：降级公钥一并下发——前端非安全上下文（http+IP）WebCrypto
    # 不可用时走 jsencrypt PKCS1v15 + 降级 kid。加载失败仅缺降级能力
    # （主路径不受影响），不阻塞安全上下文登录。
    try:
        fb_pem, fb_kid = (
            PasswordEncryptionService.get_fallback_public_key_info(
                Config.AUTH_RSA_FALLBACK_KEY_PATH))
        payload['fallback'] = {'kid': fb_kid, 'public_key': fb_pem}
    except Exception:  # noqa: BLE001
        logger.warning('登录加密降级公钥加载失败', exc_info=True)
    return to_response(payload)


@router.get('/mode')
def auth_mode():
    """当前生效认证模式（INT-180 前端启动自检数据源，未认证可读）。

    仅回枚举 mode 值（off|dev|prod），无其他配置项；前端启动时与
    本地 VITE_AUTH_MODE 比对，错位即页面告警——杜绝"后端改 AUTH_MODE、
    前端构建期变量无感知"的静默失配。值取网关自身 AUTH_MODE（认证
    强制点，见 AuthService.get_auth_mode）。
    """
    return to_response({'auth_mode': AuthService.get_auth_mode()})


@router.get('/login')
def login_page():
    """登录入口：dev 重定向到前端登录页，prod 重定向到华为云"""
    entry = AuthService.get_login_entry()
    return RedirectResponse(url=entry)


@router.post('/login')
def login_submit(request: Request,
                 username: str = Form(''),
                 password: str = Form(''),
                 password_encrypted: str = Form(''),
                 encryption_key_id: str = Form('')):
    """账号(用户名/邮箱)+密码登录（INT-147：密码 RSA 加密传输 + 邮箱登录）。

    INT-179：请求体双格式兼容——表单编码（application/x-www-form-urlencoded，
    前端契约）与 JSON body 均可（JSON 经 RequestAdapterMiddleware 预解析进
    request.state._json_body 兜底），消除 Content-Type 契约不匹配的 422。

    加密开关开启时仅接受 password_encrypted/encryption_key_id（明文
    password 字段被忽略，对齐旧库无明文回退）。401 保持统一状态码防
    用户名枚举，但以 error code 区分语义（INT-188）：加密载荷无效
    （旧缓存包/明文回退/公钥轮换）回 AUTH_ENCRYPTION_INVALID 并引导
    刷新页面，凭证错误回 AUTH_CREDENTIALS_INVALID。
    """
    if not any((username, password, password_encrypted, encryption_key_id)):
        body = getattr(request.state, '_json_body', None)
        if isinstance(body, dict):
            username = str(body.get('username') or '')
            password = str(body.get('password') or '')
            password_encrypted = str(body.get('password_encrypted') or '')
            encryption_key_id = str(body.get('encryption_key_id') or '')
    from api_gateway.utils.error_codes import ErrorCode
    from api_gateway.application.services.auth.password_encryption import (
        PasswordEncryptionError, PasswordEncryptionService,
    )
    if Config.AUTH_PASSWORD_ENCRYPTION_ENABLED:
        try:
            password = PasswordEncryptionService.decrypt_password(
                password_encrypted, encryption_key_id,
                Config.AUTH_RSA_KEY_PATH, Config.AUTH_RSA_FALLBACK_KEY_PATH)
        except PasswordEncryptionError:
            return JSONResponse(
                status_code=401,
                content={'detail': '登录加密校验失败，请刷新页面重试',
                         'code': ErrorCode.AUTH_ENCRYPTION_INVALID},
            )
    try:
        result = AuthService.login_with_password(username, password)
        return to_response(result)
    except PermissionError as e:
        return JSONResponse(
            status_code=403,
            content={'detail': str(e)},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=401,
            content={'detail': str(e),
                     'code': ErrorCode.AUTH_CREDENTIALS_INVALID},
        )


@router.get('/callback')
def callback(code: str = Query(...), state: str = Query('')):
    """OAuth 回调（生产模式：华为云授权码）"""
    try:
        result = AuthService.handle_callback(code, state)
        return to_response(result)
    except PermissionError as e:
        return JSONResponse(
            status_code=403,
            content={'detail': str(e)},
        )
    except Exception as e:
        return JSONResponse(
            status_code=401,
            content={'detail': f'OAuth 回调失败: {e}'},
        )


@router.post('/refresh')
def refresh_token(request: Request):
    """刷新 token"""
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
    try:
        result = AuthService.refresh_token(token)
        return to_response(result)
    except Exception as e:
        return JSONResponse(
            status_code=401,
            content={'detail': f'令牌刷新失败: {e}'},
        )


@router.post('/logout')
def logout(request: Request):
    """登出（JWT 无状态，前端清除 token 即可）。

    INT-406：登出落 AUTH_LOGOUT 审计（旁路，失败不阻断）。操作人取
    AuthMiddleware 注入的 request.state（AUTH_MODE=off 时为 dev_user）。
    """
    from api_gateway.application.services.auth.auth_audit import write_auth_audit
    from shared.models.common_enums import AuditEvent
    write_auth_audit(AuditEvent.AUTH_LOGOUT, 'auth_logout', {
        'operator_id': getattr(request.state, 'user_id', None),
        'operator': getattr(request.state, 'username', '') or '',
    })
    return to_response({'message': '已登出'})


@router.get('/me')
def me(request: Request):
    """获取当前用户信息"""
    return to_response(AuthService.get_current_user_info(request.state))
