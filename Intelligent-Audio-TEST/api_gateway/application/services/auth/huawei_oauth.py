"""
华为云 OAuth Provider — application 层

对齐 DDD 重构方案第八章「生产模式 HuaweiOAuthProvider」。
授权码模式：get_login_url → callback 换 token → 获取用户信息。
"""
import logging
from typing import Optional
from urllib.parse import urlencode

from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from api_gateway.config.config import Config

logger = logging.getLogger(__name__)


class HuaweiOAuthProvider:
    """华为云 OAuth 2.0 授权码模式"""

    @staticmethod
    def get_login_url(state: str = '') -> str:
        """生成华为云授权页 URL"""
        params = {
            'client_id': Config.HW_OAUTH_CLIENT_ID,
            'redirect_uri': Config.HW_OAUTH_REDIRECT_URI,
            'response_type': 'code',
            'state': state or 'auth',
        }
        return f'{Config.HW_OAUTH_AUTHORIZE_URL}?{urlencode(params)}'

    @staticmethod
    def exchange_token(code: str) -> dict:
        """用授权码换取 access_token"""
        import httpx

        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': Config.HW_OAUTH_CLIENT_ID,
            'client_secret': Config.HW_OAUTH_CLIENT_SECRET,
            'redirect_uri': Config.HW_OAUTH_REDIRECT_URI,
        }
        resp = httpx.post(Config.HW_OAUTH_TOKEN_URL, data=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def get_user_info(access_token: str) -> UserInfo:
        """用 access_token 获取用户信息"""
        import httpx

        headers = {'Authorization': f'Bearer {access_token}'}
        resp = httpx.get(Config.HW_OAUTH_USERINFO_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        return UserInfo(
            username=data.get('preferred_username') or data.get('username', ''),
            email=data.get('email'),
            external_id=data.get('sub') or data.get('user_id'),
            display_name=data.get('name'),
        )

    @staticmethod
    def handle_callback(code: str, state: str = '') -> UserInfo:
        """回调处理：code → token → userinfo"""
        token_resp = HuaweiOAuthProvider.exchange_token(code)
        access_token = token_resp.get('access_token')
        if not access_token:
            raise ValueError('华为云未返回 access_token')
        return HuaweiOAuthProvider.get_user_info(access_token)
