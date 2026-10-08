# -*- coding: utf-8 -*-
"""transfer_agent 领域配置。

T-A / T-B 双实例形态：同一份代码按 TRANSFER_ZONE 部署到 A / B（备选方案 C）区，
预共享 Token 与路由白名单决定跨区可达性，全部配置化、无硬编码密钥。
"""
import os

from shared.config.service_ports import (
    TRANSFER_AGENT_GRPC_PORT,
    TRANSFER_AGENT_HTTP_PORT,
)
from shared.infrastructure.config import BaseConfig

_MB = 1024 * 1024
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', TRANSFER_AGENT_HTTP_PORT))
    GRPC_PORT = int(os.environ.get(
        'TRANSFER_AGENT_GRPC_PORT', os.environ.get('GRPC_PORT', TRANSFER_AGENT_GRPC_PORT),
    ))

    SERVICE_NAME = 'transfer_agent'

    # --- 本实例所在区（A / B，备选方案 C）---
    TRANSFER_ZONE: str = os.environ.get('TRANSFER_ZONE', 'A').upper()

    # --- 分片传输 ---
    TRANSFER_CHUNK_SIZE_MB: int = int(os.environ.get('TRANSFER_CHUNK_SIZE_MB', 4))
    TRANSFER_CHUNK_SIZE: int = TRANSFER_CHUNK_SIZE_MB * _MB

    # --- TTL 边界（秒）---
    TRANSFER_MIN_TTL_SECONDS: int = int(os.environ.get('TRANSFER_MIN_TTL_SECONDS', 60))
    TRANSFER_MAX_TTL_SECONDS: int = int(os.environ.get('TRANSFER_MAX_TTL_SECONDS', 7 * 86400))
    TRANSFER_DEFAULT_TTL_SECONDS: int = int(os.environ.get('TRANSFER_DEFAULT_TTL_SECONDS', 3600))

    # --- 过期清理扫描间隔（秒）---
    TRANSFER_SWEEP_INTERVAL_SECONDS: int = int(os.environ.get('TRANSFER_SWEEP_INTERVAL_SECONDS', 300))

    # --- 预共享 Token（访问控制层 + 签名层密钥）---
    # 优先环境变量；其次 shared/config/secrets_config.json（{"TOKEN_A_B": "...", ...}）。
    # 未配置的路由一律拒绝（fail-closed）。
    TRANSFER_SECRETS_FILE: str = os.environ.get(
        'TRANSFER_SECRETS_FILE',
        os.path.join(_REPO_ROOT, 'shared', 'config', 'secrets_config.json'),
    )

    # --- 路由白名单（网络隔离点/内容层）---
    # 缺省用 ZoneRoutePolicy.DEFAULT_ROUTES；提供 JSON 文件可整体覆盖
    #（格式：{"routes": [{"src": "A", "dst": "B", "pkg_types": [...]}, ...]}）
    TRANSFER_ROUTE_POLICY_FILE: str = os.environ.get('TRANSFER_ROUTE_POLICY_FILE', '')

    @classmethod
    def transfer_tokens(cls) -> dict:
        """汇总预共享 token：环境变量优先，secrets_config.json 兜底。"""
        tokens = {}
        try:
            from transfer_agent.domain.services.signature_service import (
                load_tokens_from_secrets_file,
            )
            tokens.update(load_tokens_from_secrets_file(cls.TRANSFER_SECRETS_FILE))
        except Exception:
            pass
        for key in ('TRANSFER_TOKEN_A_B', 'TRANSFER_TOKEN_B_C'):
            val = os.environ.get(key, '')
            if val:
                tokens[key.replace('TRANSFER_', '', 1).upper()] = val
        return tokens

    @classmethod
    def route_policy(cls):
        from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy
        return ZoneRoutePolicy(policy_file=cls.TRANSFER_ROUTE_POLICY_FILE or None)
