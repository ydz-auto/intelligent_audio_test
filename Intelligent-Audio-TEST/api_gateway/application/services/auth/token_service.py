"""
JWT 签发与校验服务

使用 PyJWT (jwt) 库，HS256 对称加密。
payload 包含 user_id / username / role_id / permissions。
"""
from datetime import datetime, timedelta, timezone

import jwt

from api_gateway.config.config import Config


class TokenService:
    """JWT 签发与校验"""

    SECRET = Config.JWT_SECRET
    ALGORITHM = Config.JWT_ALGORITHM
    EXPIRE_HOURS = Config.JWT_EXPIRE_HOURS

    @staticmethod
    def create_token(user_id: int, username: str, role_id: int,
                     permissions: list[str]) -> str:
        """签发 JWT"""
        now = datetime.now(timezone.utc)
        payload = {
            'user_id': user_id,
            'username': username,
            'role_id': role_id,
            'permissions': permissions,
            'iat': now,
            'exp': now + timedelta(hours=TokenService.EXPIRE_HOURS),
        }
        return jwt.encode(payload, TokenService.SECRET,
                          algorithm=TokenService.ALGORITHM)

    @staticmethod
    def verify(token: str) -> dict:
        """校验 JWT，返回 payload；失败抛 jwt.PyJWTError 子类"""
        return jwt.decode(token, TokenService.SECRET,
                          algorithms=[TokenService.ALGORITHM])

    @staticmethod
    def refresh(token: str) -> str:
        """刷新 token（重新签发；权限按当前生效值重算，不再复制旧快照）。

        JWT 里的 permissions 是登录时的快照——原实现整份复制会让续期后的
        token 继续携带旧权限。这里经权限实时化缓存（短 TTL）取当前权限，
        取不到时回落旧快照，保证续期不放大也不丢失既有权限。
        """
        payload = TokenService.verify(token)
        permissions = list(payload.get('permissions') or [])
        try:
            from api_gateway.infrastructure.permission_cache import resolve_permissions
            permissions = resolve_permissions(
                int(payload['user_id']), permissions)
        except Exception:  # 权限服务不可用不阻断续期
            pass
        return TokenService.create_token(
            user_id=payload['user_id'],
            username=payload['username'],
            role_id=payload['role_id'],
            permissions=permissions,
        )
