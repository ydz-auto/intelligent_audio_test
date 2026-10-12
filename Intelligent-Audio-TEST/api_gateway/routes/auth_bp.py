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
    return to_response({'enabled': True, 'kid': kid, 'public_key': public_key_pem})


@router.get('/login')
def login_page():
    """登录入口：dev 重定向到前端登录页，prod 重定向到华为云"""
    entry = AuthService.get_login_entry()
    return RedirectResponse(url=entry)


@router.post('/login')
def login_submit(username: str = Form(...),
                 password: str = Form(''),
                 password_encrypted: str = Form(''),
                 encryption_key_id: str = Form('')):
    """账号(用户名/邮箱)+密码登录（INT-147：密码 RSA 加密传输 + 邮箱登录）。

    加密开关开启时仅接受 password_encrypted/encryption_key_id（明文
    password 字段被忽略，对齐旧库无明文回退）；解密失败与凭证错误
    统一 401「用户名或密码错误」（防用户名枚举）。
    """
    from api_gateway.application.services.auth.password_encryption import (
        PasswordEncryptionError, PasswordEncryptionService,
    )
    if Config.AUTH_PASSWORD_ENCRYPTION_ENABLED:
        try:
            password = PasswordEncryptionService.decrypt_password(
                password_encrypted, encryption_key_id,
                Config.AUTH_RSA_KEY_PATH)
        except PasswordEncryptionError:
            return JSONResponse(
                status_code=401,
                content={'detail': '用户名或密码错误'},
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
            content={'detail': str(e)},
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
def logout():
    """登出（JWT 无状态，前端清除 token 即可）"""
    return to_response({'message': '已登出'})


@router.get('/me')
def me(request: Request):
    """获取当前用户信息"""
    return to_response(AuthService.get_current_user_info(request.state))
