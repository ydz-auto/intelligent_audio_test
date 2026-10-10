# -*- coding: utf-8 -*-
"""api_adapter_service 密钥提供者（Infrastructure 层，INT-70）。

设计依据：API测试功能设计文档 §3.7/§8.1 —— 密钥解析统一收敛在
Infrastructure 层密钥提供者，Domain 层只见解析结果。

解析顺序（逐级回退）：
  1. vendor_config.api_key_candidates.case_config（用例层候选，
     由 api_test_service 执行侧按其配置的键名提取后随 SendRoundRequest 下发）
  2. vendor_config.api_key_candidates.meta（API meta 层候选）
  3. application.yml vendor 层 api_key（加载期完成 ${ENV:} 替换）
  4. 环境变量（默认 OPENAI_API_KEY）

服务配置层的键名与环境变量名经 application.yml secrets.api_key_chain
配置；用例层/meta 层键名由提取侧（api_test_service，config_manager
secrets 段）配置。禁止硬编码密钥。
"""
from shared.utils.api_key_provider import (
    DEFAULT_ENV_KEY,
    ApiKeyChainResolver,
)

from api_adapter_service.utils.config import config


class ApiKeyProvider:
    """vendor_config 密钥链解析（Infrastructure 层密钥提供者）。"""

    def __init__(self, config=config):
        self._config = config

    def resolve(self, vendor_config) -> str:
        """按密钥链解析 vendor_config 携带的各级候选，返回最终密钥。"""
        vendor_config = vendor_config or {}
        chain = self._config.get('secrets.api_key_chain') or {}
        candidates = vendor_config.get('api_key_candidates') or {}
        resolver = ApiKeyChainResolver(
            env_key=chain.get('env_key', DEFAULT_ENV_KEY),
        )
        return resolver.resolve(
            case_value=candidates.get('case_config'),
            meta_value=candidates.get('meta'),
            service_candidates=[vendor_config.get(
                chain.get('service_config_key', 'api_key'))],
        )


# 单例
api_key_provider = ApiKeyProvider()
