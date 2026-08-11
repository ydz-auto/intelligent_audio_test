# -*- coding: utf-8 -*-
"""算法配置缓存仓储

迁移自 shared/algorithm/algorithm_config_loader.py
通过本地 infrastructure/persistence 仓储直接读取算法配置（同进程内访问），
为 application 层提供统一配置缓存接口。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from threading import Lock, RLock

from shared.utils.log_handler import log_not_emit

from algorithm_service.infrastructure.persistence.algorithm_repository import (
    algorithm_definition_query_repository,
    algorithm_group_query_repository,
    dimension_param_repository,
    param_mapping_query_repository,
)
from algorithm_service.infrastructure.persistence.param_repository import (
    algorithm_param_repository,
    case_param_repository,
    reference_param_repository,
    mapping_repository,
    dimension_relation_repository,
)


class AlgorithmConfigCache:
    """算法配置缓存器 - 单例模式"""

    _instance = None
    _instance_lock = Lock()
    _config_cache: Dict[str, Any] = {}
    _last_reload_time: Optional[datetime] = None
    _reload_lock = RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._load_all_configs()
        return cls._instance

    def _load_all_configs(self):
        """从本地数据库加载所有算法配置（线程安全）"""
        with self._reload_lock:
            log_not_emit('DEBUG', 'algorithm_config_cache', 'Starting to load all algorithm configs', category='algorithm')
            self._config_cache = {
                'algorithms': {},
                'device_params': {},
                'api_params': {},
                'case_params': {},
                'evaluation_dimension_params': {},
                'mappings': {},
                'reference_params': {},
            }

            algorithms = algorithm_definition_query_repository.list_online_definitions()

            log_not_emit('INFO', 'algorithm_config_cache', f'Found {len(algorithms)} online algorithms', category='algorithm')

            for algo in algorithms:
                algo_type = algo.get('algorithm_type') or algo.get('type')
                if not algo_type:
                    continue
                self._config_cache['algorithms'][algo_type] = {
                    'id': algo.get('id'),
                    'type': algo_type,
                    'name': algo.get('name'),
                    'description': algo.get('description'),
                    'status': algo.get('status'),
                    'icon': algo.get('icon'),
                    'display_order': algo.get('display_order'),
                }

                device_params = algorithm_param_repository.list_by_algorithm(algo_type, 'device')
                self._config_cache['device_params'][algo_type] = self._serialize_params(device_params)

                api_params = algorithm_param_repository.list_by_algorithm(algo_type, 'api')
                self._config_cache['api_params'][algo_type] = self._serialize_params(api_params)

                mappings = mapping_repository.list_by_algorithm(algo_type)
                self._config_cache['mappings'][algo_type] = self._serialize_mappings(mappings)

                case_params = case_param_repository.list_by_algorithm(algo_type)
                self._config_cache['case_params'][algo_type] = self._serialize_params(case_params)

                ref_params = reference_param_repository.list_by_algorithm(algo_type)
                self._config_cache['reference_params'][algo_type] = self._serialize_reference_params(ref_params)

                dim_relations = dimension_relation_repository.list_by_algorithm(algo_type)
                for rel in dim_relations:
                    dim_id = rel.get('dimension_id') if isinstance(rel, dict) else None
                    if dim_id and dim_id not in self._config_cache['evaluation_dimension_params']:
                        params = dimension_param_repository.list_by_dimension(dim_id)
                        self._config_cache['evaluation_dimension_params'][dim_id] = [
                            self._serialize_dimension_param(p) for p in params
                        ]

            self._last_reload_time = datetime.now()
            log_not_emit('INFO', 'algorithm_config_cache',
                         f'Config loaded successfully, {len(algorithms)} algorithms cached', category='algorithm')

    @staticmethod
    def _serialize_params(params: List) -> List[Dict[str, Any]]:
        result = []
        for p in params:
            if not isinstance(p, dict):
                continue
            result.append({
                'id': p.get('id'),
                'algorithm_type': p.get('algorithm_type'),
                'code': p.get('param_code') or p.get('code'),
                'name': p.get('param_name') or p.get('name'),
                'label': p.get('label'),
                'type': p.get('param_type') or p.get('type'),
                'direction': p.get('direction', 'output'),
                'required': p.get('required') or p.get('is_required'),
                'default_value': p.get('default_value'),
                'validation_rules': p.get('validation_rules') or p.get('validation'),
                'help_text': p.get('help_text'),
                'ui_order': p.get('ui_order') or p.get('sort_order'),
                'ui_group': p.get('ui_group', 'default'),
                'hidden': p.get('hidden', False),
                'param_type': p.get('param_type'),
            })
        return result

    @staticmethod
    def _serialize_reference_params(params: List) -> List[Dict[str, Any]]:
        result = []
        for p in params:
            if not isinstance(p, dict):
                continue
            result.append({
                'id': p.get('id'),
                'algorithm_type': p.get('algorithm_type'),
                'code': p.get('code'),
                'name': p.get('name'),
                'type': p.get('param_type') or p.get('type'),
                'help_text': p.get('help_text'),
            })
        return result

    @staticmethod
    def _serialize_dimension_param(param: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(param, dict):
            return {}
        return {
            'id': param.get('id'),
            'dimension_id': param.get('dimension_id'),
            'dimension_name': param.get('dimension_name'),
            'code': param.get('param_code') or param.get('code'),
            'name': param.get('param_name') or param.get('name'),
            'label': param.get('label'),
            'field_type': param.get('field_type'),
            'required': param.get('required'),
            'default_value': param.get('default_value'),
            'help_text': param.get('help_text'),
            'ui_order': param.get('ui_order'),
        }

    @staticmethod
    def _serialize_mappings(mappings) -> Dict[str, Any]:
        result = {'device': [], 'api': [], 'case': [], 'reference': []}
        if isinstance(mappings, list):
            for m in mappings:
                if not isinstance(m, dict):
                    continue
                source = m.get('source') or m.get('source_type') or 'api'
                source_key = source if source in result else 'api'
                result[source_key].append({
                    'source': source,
                    'source_param': m.get('source_param') or m.get('source_field'),
                    'source_direction': m.get('source_direction') or m.get('direction'),
                    'dimension_id': m.get('dimension_id'),
                    'dimension_name': m.get('dimension_name'),
                    'target_param': m.get('target_param') or m.get('target_field'),
                    'transform_type': m.get('transform_type') or m.get('transform_rule') or 'none',
                })
        return result

    def reload_if_changed(self) -> bool:
        """重新加载配置"""
        try:
            with self._reload_lock:
                self._load_all_configs()
                return True
        except Exception as e:
            log_not_emit('ERROR', 'algorithm_config_cache', f'Error checking config changes: {e}', category='algorithm')
            return False

    def reload(self) -> bool:
        """强制重新加载"""
        with self._reload_lock:
            self._load_all_configs()
        return True

    def get_last_reload_time(self) -> Optional[str]:
        if self._last_reload_time:
            return self._last_reload_time.isoformat()
        return None

    def get_all_algorithms(self) -> List[Dict[str, Any]]:
        return [
            {'type': k, 'name': v.get('name', k), 'description': v.get('description')}
            for k, v in self._config_cache.get('algorithms', {}).items()
        ]

    def get_algorithm_config(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        if algorithm_type not in self._config_cache.get('algorithms', {}):
            return None
        return {
            'definition': self._config_cache['algorithms'].get(algorithm_type),
            'device_params': self._config_cache['device_params'].get(algorithm_type, []),
            'api_params': self._config_cache['api_params'].get(algorithm_type, []),
            'case_params': self._config_cache['case_params'].get(algorithm_type, []),
            'mappings': self._config_cache['mappings'].get(algorithm_type, {}),
        }

    def get_algorithm_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        device_params = self._config_cache.get('device_params', {}).get(algorithm_type, [])
        api_params = self._config_cache.get('api_params', {}).get(algorithm_type, [])
        return device_params + api_params

    def get_device_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('device_params', {}).get(algorithm_type, [])

    def get_api_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('api_params', {}).get(algorithm_type, [])

    def get_case_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('case_params', {}).get(algorithm_type, [])

    def get_reference_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('reference_params', {}).get(algorithm_type, [])

    def get_param_mapping(self, algorithm_type: str, component_type: str) -> List[Dict[str, Any]]:
        if component_type == 'evaluation':
            self.reload_if_changed()
            return self._get_evaluation_mappings(algorithm_type)
        mappings = self._config_cache.get('mappings', {}).get(algorithm_type, {})
        return mappings.get(component_type, [])

    def _get_evaluation_mappings(self, algorithm_type: str) -> List[Dict[str, Any]]:
        mappings = self._config_cache.get('mappings', {}).get(algorithm_type, {})
        result = []
        for source in ['device', 'api', 'case', 'reference', 'adjusted_reference']:
            for m in mappings.get(source, []):
                result.append({
                    'source': source,
                    'source_param': m['source_param'],
                    'target_param': m['target_param'],
                    'direction': 'output',
                    'dimension_id': m.get('dimension_id'),
                    'dimension_name': m.get('dimension_name'),
                    'transform_type': m.get('transform_type', 'none'),
                })
        if 'adjusted_reference' not in mappings:
            for source in ['device', 'api', 'case', 'reference']:
                for m in mappings.get(source, []):
                    target_param = m.get('target_param', '')
                    if target_param in ['rttm_ref', 'stm_ref', 'asr_ref']:
                        result.append({
                            'source': 'adjusted_reference',
                            'source_param': target_param,
                            'target_param': target_param,
                            'direction': 'output',
                            'dimension_id': m.get('dimension_id'),
                            'dimension_name': m.get('dimension_name'),
                            'transform_type': m.get('transform_type', 'none'),
                        })
        return result

    def get_evaluation_dimension_params(self, dimension_id: int) -> List[Dict[str, Any]]:
        return self._config_cache.get('evaluation_dimension_params', {}).get(dimension_id, [])

    def get_algorithm_definition(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        return self._config_cache.get('algorithms', {}).get(algorithm_type)


def get_config_cache() -> AlgorithmConfigCache:
    """获取配置缓存器单例"""
    return AlgorithmConfigCache()
