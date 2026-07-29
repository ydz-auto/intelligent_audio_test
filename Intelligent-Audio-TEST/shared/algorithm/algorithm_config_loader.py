# -*- coding: utf-8 -*-
"""
算法配置加载器

职责：
- 从数据库加载算法定义、设备参数、API参数、评估维度映射
- 提供配置缓存和热更新
- 只负责配置查询，不负责参数构建
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from threading import Lock
from shared.models.algorithm_models import (
    AlgorithmDefinition,
    AlgorithmDeviceParam,
    AlgorithmApiParam,
    EvaluationDimensionParam,
    ParamMapping,
    CaseAlgorithmParam,
    AlgorithmReferenceParam
)
from shared.utils.log_handler import log_not_emit


class AlgorithmConfigLoader:
    """
    算法配置加载器 - 单例模式

    从数据库加载算法配置，提供统一的配置查询接口
    """

    _instance = None
    _instance_lock = Lock()
    _config_cache: Dict[str, Any] = {}
    _last_reload_time: Optional[datetime] = None
    _reload_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._load_all_configs()
        return cls._instance

    def _load_all_configs(self):
        """从数据库加载所有算法配置（线程安全）"""
        with self._reload_lock:
            log_not_emit('DEBUG', 'algorithm_config_loader', 'Starting to load all algorithm configs', category='algorithm')
            self._config_cache = {
                'algorithms': {},
                'device_params': {},
                'api_params': {},
                'case_params': {},
                'evaluation_dimension_params': {},
                'mappings': {},
                'reference_params': {}
            }

            algorithms = AlgorithmDefinition.query.filter_by(
                status='online', deleted=False
            ).all()

            log_not_emit('INFO', 'algorithm_config_loader', f'Found {len(algorithms)} online algorithms', category='algorithm')

            for algo in algorithms:
                algo_type = algo.type
                self._config_cache['algorithms'][algo_type] = {
                    'id': algo.id,
                    'type': algo.type,
                    'name': algo.name,
                    'description': algo.description,
                    'status': algo.status,
                    'icon': algo.icon,
                    'display_order': algo.display_order
                }

                self._config_cache['device_params'][algo_type] = self._serialize_params(
                    AlgorithmDeviceParam.query.filter_by(
                        algorithm_type=algo_type, deleted=False
                    ).order_by(AlgorithmDeviceParam.ui_order).all()
                )

                self._config_cache['api_params'][algo_type] = self._serialize_params(
                    AlgorithmApiParam.query.filter_by(
                        algorithm_type=algo_type, deleted=False
                    ).order_by(AlgorithmApiParam.ui_order).all()
                )

                self._config_cache['mappings'][algo_type] = self._serialize_mappings(
                    ParamMapping.query.filter_by(
                        algorithm_type=algo_type, deleted=False
                    ).all()
                )

                self._config_cache['case_params'][algo_type] = self._serialize_params(
                    CaseAlgorithmParam.query.filter_by(
                        algorithm_type=algo_type, deleted=False
                    ).order_by(CaseAlgorithmParam.ui_order).all()
                )

                self._config_cache['reference_params'][algo_type] = self._serialize_reference_params(
                    AlgorithmReferenceParam.query.filter_by(
                        algorithm_type=algo_type, deleted=False
                    ).all()
                )

            all_dimension_params = EvaluationDimensionParam.query.filter_by(
                deleted=False
            ).all()
            self._config_cache['evaluation_dimension_params'] = {
                d.id: self._serialize_dimension_param(d)
                for d in all_dimension_params
            }

            self._last_reload_time = datetime.now()
            log_not_emit('INFO', 'algorithm_config_loader', f'Config loaded successfully, {len(algorithms)} algorithms cached', category='algorithm')

    def _serialize_params(self, params: List) -> List[Dict[str, Any]]:
        """序列化参数列表"""
        return [
            {
                'id': p.id,
                'algorithm_type': p.algorithm_type,
                'code': p.param_code,
                'name': p.param_name,
                'label': p.label,
                'type': p.param_type,
                'direction': getattr(p, 'direction', 'output'),
                'required': p.required,
                'default_value': p.default_value,
                'validation_rules': getattr(p, 'validation_rules', None),
                'help_text': getattr(p, 'help_text', None),
                'ui_order': p.ui_order,
                'ui_group': getattr(p, 'ui_group', 'default'),
                'hidden': getattr(p, 'hidden', False),
                'param_type': getattr(p, 'param_type', None)
            }
            for p in params
        ]

    def _serialize_reference_params(self, params: List) -> List[Dict[str, Any]]:
        """序列化参考参数"""
        return [
            {
                'id': p.id,
                'algorithm_type': p.algorithm_type,
                'code': p.code,
                'name': p.name,
                'type': p.param_type,
                'help_text': p.help_text
            }
            for p in params
        ]

    def _serialize_dimension_param(self, param: EvaluationDimensionParam) -> Dict[str, Any]:
        """序列化评估维度参数"""
        return {
            'id': param.id,
            'dimension_id': param.dimension_id,
            'dimension_name': param.dimension.name if param.dimension else None,
            'code': param.param_code,
            'name': param.param_name,
            'label': param.label,
            'field_type': param.field_type,
            'required': param.required,
            'default_value': param.default_value,
            'help_text': param.help_text,
            'ui_order': param.ui_order
        }

    def _serialize_mappings(self, mappings: List[ParamMapping]) -> Dict[str, Any]:
        """序列化参数映射"""
        result = {'device': [], 'api': [], 'case': [], 'reference': []}
        for m in mappings:
            source = getattr(m, 'source', None) or 'api'
            if source in result:
                result[source].append({
                    'source': source,
                    'source_param': m.source_param,
                    'source_direction': m.source_direction,
                    'dimension_id': m.dimension_id,
                    'dimension_name': m.dimension.name if m.dimension else None,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type
                })
            else:
                result['api'].append({
                    'source': source,
                    'source_param': m.source_param,
                    'source_direction': m.source_direction,
                    'dimension_id': m.dimension_id,
                    'dimension_name': m.dimension.name if m.dimension else None,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type
                })
        return result

    def reload_if_changed(self) -> bool:
        """检查数据库配置是否变化，如果变化则重新加载"""
        from shared.models.database import db
        from shared.models.algorithm_models import ParamMapping
        try:
            with self._reload_lock:
                latest_algo = db.session.query(
                    db.func.max(AlgorithmDefinition.updated_at)
                ).filter_by(deleted=False).scalar()

                latest_mapping = db.session.query(
                    db.func.max(ParamMapping.updated_at)
                ).scalar()

                latest_reload = max(filter(None, [latest_algo, latest_mapping]), default=None)

                if latest_reload and self._last_reload_time:
                    if latest_reload > self._last_reload_time:
                        log_not_emit('INFO', 'algorithm_config_loader', 'Config changed, reloading...', category='algorithm')
                        self._load_all_configs()
                        return True
        except Exception as e:
            log_not_emit('ERROR', 'algorithm_config_loader', f'Error checking config changes: {e}', category='algorithm')
        return False

    def reload(self) -> bool:
        """强制重新加载配置"""
        with self._reload_lock:
            log_not_emit('INFO', 'algorithm_config_loader', 'Force reloading config...', category='algorithm')
            self._load_all_configs()
        return True

    def get_last_reload_time(self) -> Optional[str]:
        """获取最后一次reload时间"""
        if self._last_reload_time:
            return self._last_reload_time.isoformat()
        return None

    def get_all_algorithms(self) -> List[Dict[str, Any]]:
        """获取所有在线算法"""
        return [
            {'type': k, 'name': v.get('name', k), 'description': v.get('description')}
            for k, v in self._config_cache.get('algorithms', {}).items()
        ]

    def get_algorithm_config(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        """获取算法完整配置"""
        if algorithm_type not in self._config_cache.get('algorithms', {}):
            return None
        return {
            'definition': self._config_cache['algorithms'].get(algorithm_type),
            'device_params': self._config_cache['device_params'].get(algorithm_type, []),
            'api_params': self._config_cache['api_params'].get(algorithm_type, []),
            'case_params': self._config_cache['case_params'].get(algorithm_type, []),
            'mappings': self._config_cache['mappings'].get(algorithm_type, {})
        }

    def get_algorithm_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取算法参数（合并设备参数和API参数）"""
        device_params = self._config_cache.get('device_params', {}).get(algorithm_type, [])
        api_params = self._config_cache.get('api_params', {}).get(algorithm_type, [])
        return device_params + api_params

    def get_device_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取设备参数"""
        return self._config_cache.get('device_params', {}).get(algorithm_type, [])

    def get_api_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取API参数"""
        return self._config_cache.get('api_params', {}).get(algorithm_type, [])

    def get_case_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取用例专属参数"""
        return self._config_cache.get('case_params', {}).get(algorithm_type, [])

    def get_reference_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取参考参数"""
        return self._config_cache.get('reference_params', {}).get(algorithm_type, [])

    def get_param_mapping(self, algorithm_type: str, component_type: str) -> List[Dict[str, Any]]:
        """获取参数映射"""
        if component_type == 'evaluation':
            self.reload_if_changed()
            return self._get_evaluation_mappings(algorithm_type)
        mappings = self._config_cache.get('mappings', {}).get(algorithm_type, {})
        return mappings.get(component_type, [])

    def _get_evaluation_mappings(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取评估参数映射"""
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
                    'transform_type': m.get('transform_type', 'none')
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
                            'transform_type': m.get('transform_type', 'none')
                        })
        return result

    def get_evaluation_dimension_params(self, dimension_id: int) -> List[Dict[str, Any]]:
        """获取评估维度参数"""
        return self._config_cache.get('evaluation_dimension_params', {}).get(dimension_id, [])

    def get_algorithm_definition(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        """获取算法定义"""
        return self._config_cache.get('algorithms', {}).get(algorithm_type)


def get_config_loader() -> AlgorithmConfigLoader:
    """获取配置加载器单例"""
    return AlgorithmConfigLoader()
