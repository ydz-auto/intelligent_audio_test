# -*- coding: utf-8 -*-
"""算法配置查询处理器

CQRS 读侧 - 迁移自 algorithm_config_loader 的查询逻辑。
通过 infrastructure 层 config_cache 提供配置查询。
"""

from typing import Dict, List, Any, Optional

from algorithm_service.infrastructure.persistence.config_cache import get_config_cache


class AlgorithmConfigQueryHandler:
    """算法配置查询处理器"""

    @staticmethod
    def get_algorithm_config(algorithm_type: str) -> Optional[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_algorithm_config(algorithm_type)

    @staticmethod
    def get_all_algorithms() -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_all_algorithms()

    @staticmethod
    def get_algorithm_params(algorithm_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_algorithm_params(algorithm_type)

    @staticmethod
    def get_device_params(algorithm_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_device_params(algorithm_type)

    @staticmethod
    def get_api_params(algorithm_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_api_params(algorithm_type)

    @staticmethod
    def get_case_params(algorithm_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_case_params(algorithm_type)

    @staticmethod
    def get_reference_params(algorithm_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_reference_params(algorithm_type)

    @staticmethod
    def get_param_mapping(algorithm_type: str, component_type: str) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_param_mapping(algorithm_type, component_type)

    @staticmethod
    def get_evaluation_dimension_params(dimension_id: int) -> List[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_evaluation_dimension_params(dimension_id)

    @staticmethod
    def get_algorithm_definition(algorithm_type: str) -> Optional[Dict[str, Any]]:
        cache = get_config_cache()
        return cache.get_algorithm_definition(algorithm_type)

    @staticmethod
    def reload_config() -> bool:
        cache = get_config_cache()
        return cache.reload()

    @staticmethod
    def get_last_reload_time() -> Optional[str]:
        cache = get_config_cache()
        return cache.get_last_reload_time()
