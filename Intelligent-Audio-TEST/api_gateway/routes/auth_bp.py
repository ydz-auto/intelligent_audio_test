"""
认证路由 — interfaces 层

对齐 DDD 重构方案第八章「auth_bp 路由」。
登录/回调/登出/刷新/获取当前用户信息。
"""
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse

from api_gateway.application.services.auth.auth_service import AuthService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/login')
def login_page():
    """登录入口：dev 重定向到前端登录页，prod 重定向到华为云"""
    entry = AuthService.get_login_entry()
    return RedirectResponse(url=entry)


@router.post('/login')
def login_submit(username: str = Form(...), password: str = Form(...)):
    """开发模式：用户名/密码登录"""
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
