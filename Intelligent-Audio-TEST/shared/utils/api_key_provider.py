# -*- coding: utf-8 -*-
"""OpenAI 密钥链解析（INT-70，Infrastructure 层密钥提供者）。

设计依据：API测试功能设计文档 §3.7/§8.1、04_类设计 §3.2.2、
01_UseCase总览 UC-0901 扩展流程 3a ——
`case_config.api_key → api_config.meta.api_key → env OPENAI_API_KEY`
逐级回退；密钥解析统一收敛在密钥提供者，Domain 层只见解析结果。
各级键名与环境变量名均可配置（默认值对齐设计约定），禁止硬编码密钥。
"""
import os

DEFAULT_CASE_KEY = 'api_key'
DEFAULT_META_KEY = 'api_key'
DEFAULT_ENV_KEY = 'OPENAI_API_KEY'


class ApiKeyChainResolver:
    """密钥链逐级回退解析器（case_config → meta → 服务配置层 → env）。

    resolve() 按序取第一个非空候选；全部为空时回退环境变量
    （默认 OPENAI_API_KEY）。各级键名经构造参数注入，由调用方
    服务自己的配置源（yml / config_manager）提供。
    """

    def __init__(self, case_key=DEFAULT_CASE_KEY, meta_key=DEFAULT_META_KEY,
                 env_key=DEFAULT_ENV_KEY):
        self.case_key = case_key
        self.meta_key = meta_key
        self.env_key = env_key

    def resolve(self, case_config=None, meta=None, service_candidates=None,
                case_value=None, meta_value=None) -> str:
        """按密钥链顺序解析，返回首个非空候选（去首尾空白）。

        :param case_config: 用例配置 dict（取 case_key 字段）
        :param meta: API meta dict（取 meta_key 字段）
        :param service_candidates: 服务配置层候选序列（依序，
            如 application.yml vendor 层 api_key，env 替换后的值）
        :param case_value: 跨服务下发场景的 case 层直接候选值
            （执行侧按配置键名提取后随 vendor_config 传递）
        :param meta_value: 跨服务下发场景的 meta 层直接候选值
        """
        candidates = (
            case_value if case_value else (case_config or {}).get(self.case_key),
            meta_value if meta_value else (meta or {}).get(self.meta_key),
            *(service_candidates or ()),
        )
        for candidate in candidates:
            if candidate:
                return str(candidate).strip()
        return os.environ.get(self.env_key, '').strip()


def resolver_from_config(get_value, section='secrets') -> ApiKeyChainResolver:
    """从配置源构建解析器（各级键名与环境变量名均可配置）。

    :param get_value: 配置读取函数，签名 (section, key, default)
        （如 config_manager.get_value）
    """
    return ApiKeyChainResolver(
        case_key=get_value(section, 'case_config_key', DEFAULT_CASE_KEY),
        meta_key=get_value(section, 'meta_key', DEFAULT_META_KEY),
        env_key=get_value(section, 'env_key', DEFAULT_ENV_KEY),
    )
