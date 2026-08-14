# -*- coding: utf-8 -*-
"""算法配置缓存仓储 — Redis 持久化 + 进程内 L1 缓存。

迁移自 shared/algorithm/algorithm_config_loader.py
通过本地 infrastructure/persistence 仓储直接读取算法配置（同进程内访问），
为 application 层提供统一配置缓存接口。

缓存架构:
  - L1: 进程内内存字典（每次 reload 从 DB 全量加载）
  - L2: Redis HASH（key=algo_config_cache），写操作后自动刷新
  - 跨进程通知: Redis Pub/Sub（channel=algo_config_invalidate）
    其他进程（如 task_service 通过 gRPC 触发写操作）调用 reload() 后，
    本进程通过 pubsub 收到通知，自动失效 L1 并从 DB 重新加载。
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from threading import Lock, RLock, Thread

logger = logging.getLogger(__name__)

from shared.utils.log_handler import log_not_emit
from shared.infrastructure.config import BaseConfig

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

_REDIS_KEY = 'algo_config_cache'
_RELOAD_CHANNEL = 'algo_config_invalidate'


def _get_redis():
    """获取 Redis 连接（惰性创建，连接失败返回 None）"""
    try:
        import redis as redis_lib
        return redis_lib.from_url(BaseConfig.REDIS_URL, decode_responses=True)
    except Exception:
        return None


class AlgorithmConfigCache:
    """算法配置缓存器 - 单例模式

    L1（内存）+ L2（Redis）双层缓存:
    - 读: L1 → L2 → DB（逐级回源）
    - 写后刷新: 先更新 DB，再 reload() 刷新 L1，最后 PUBLISH 通知其他进程
    - 跨进程同步: 订阅 Redis pubsub，收到通知后自动 reload L1
    """

    _instance = None
    _instance_lock = Lock()
    _reload_lock = RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._config_cache: Dict[str, Any] = {}
                    obj._last_reload_time: Optional[datetime] = None
                    obj._config_cache = {}
                    obj._load_all_configs()
                    cls._instance = obj
                    # 启动后台 pubsub 监听线程
                    obj._start_invalidation_listener()
        return cls._instance

    # ---- L1 内存加载 ----

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

            # 将快照写入 Redis（L2）
            self._save_to_redis()

            log_not_emit('INFO', 'algorithm_config_cache',
                         f'Config loaded successfully, {len(algorithms)} algorithms cached', category='algorithm')

    # ---- L2 Redis 持久化 ----

    def _save_to_redis(self):
        """将当前 L1 快照写入 Redis HASH"""
        r = _get_redis()
        if r is None:
            return
        try:
            r.hset(_REDIS_KEY, mapping={
                'snapshot': json.dumps(self._config_cache, ensure_ascii=False, default=str),
                'reload_time': self._last_reload_time.isoformat() if self._last_reload_time else '',
            })
        except Exception as e:
            log_not_emit('WARN', 'algorithm_config_cache', f'Failed to save snapshot to Redis: {e}', category='algorithm')

    def _load_from_redis(self) -> Optional[Dict[str, Any]]:
        """从 Redis 读取快照（L2 回源）"""
        r = _get_redis()
        if r is None:
            return None
        try:
            raw = r.hget(_REDIS_KEY, 'snapshot')
            if raw:
                return json.loads(raw)
        except Exception:
            logger.debug("从 Redis 读取配置缓存快照失败", exc_info=True)
        return None

    # ---- 跨进程失效通知 ----

    def _publish_invalidation(self):
        """通知其他进程: 配置已变更，请重新加载"""
        r = _get_redis()
        if r is None:
            return
        try:
            r.publish(_RELOAD_CHANNEL, datetime.now().isoformat())
        except Exception:
            logger.warning("发布配置缓存失效通知到 Redis pubsub 失败", exc_info=True)

    def _start_invalidation_listener(self):
        """启动后台线程，监听 Redis pubsub 失效通知"""
        def _listen():
            import time
            while True:
                r = _get_redis()
                if r is None:
                    time.sleep(5)
                    continue
                try:
                    pubsub = r.pubsub()
                    pubsub.subscribe(_RELOAD_CHANNEL)
                    for _msg in pubsub.listen():
                        if _msg.get('type') == 'message':
                            log_not_emit('INFO', 'algorithm_config_cache',
                                         'Received invalidation notice from Redis pubsub, reloading L1', category='algorithm')
                            self._load_all_configs()
                except Exception:
                    time.sleep(3)

        Thread(target=_listen, daemon=True, name='algo-cache-pubsub').start()

    # ---- 序列化 ----

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

    # ---- 公开 API ----

    def reload_if_changed(self) -> bool:
        """重新加载配置（与 reload 等效，保留接口兼容）"""
        try:
            with self._reload_lock:
                self._load_all_configs()
                self._publish_invalidation()
                return True
        except Exception as e:
            log_not_emit('ERROR', 'algorithm_config_cache', f'Error checking config changes: {e}', category='algorithm')
            return False

    def reload(self) -> bool:
        """强制重新加载，并通知其他进程"""
        with self._reload_lock:
            self._load_all_configs()
        self._publish_invalidation()
        return True

    def invalidate(self):
        """写操作后调用: 重新加载 L1 并通知其他进程"""
        with self._reload_lock:
            self._load_all_configs()
        self._publish_invalidation()

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
        mappings = self._config_cache.get('mappings', {}).get(algorithm_type, {})
        if component_type == 'evaluation':
            return self._get_evaluation_mappings(algorithm_type)
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
