# -*- coding: utf-8 -*-
"""算法配置缓存仓储 — Redis 持久化 + 进程内 L1 缓存。

迁移自 shared/algorithm/algorithm_config_loader.py
通过本地 infrastructure/persistence 仓储直接读取算法配置（同进程内访问），
为 application 层提供统一配置缓存接口。

缓存架构:
  - L1: 进程内内存快照（不可变约定：整份替换，不原地改）
  - L2: Redis HASH（key=algo_config_cache），重载后整份覆盖
  - 跨进程通知: Redis Pub/Sub（channel=algo_config_invalidate）
    其他进程（如 task_service 通过 gRPC 触发写操作）调用 reload() 后，
    本进程通过 pubsub 收到通知，自动失效 L1 并从 DB 重新加载。

刷新策略（INT-1666，替代原「每次写全量重建」）:
  1. 按受影响范围失效: ``invalidate(algorithm_types=[...], dimension_ids=[...])``
     只重载这些切片；不知道范围时才整份重载。写路径不再无条件全量重建。
  2. 常数量级 SQL: 全量/切片构建对每张表只发一次批量 ``IN`` 查询
     （原实现对每个算法 6 次查询 + 逐条维度关系查参数，典型 N+1，
     一次重载 ~N*6+M 条 SQL）。
  3. 构建不持快照锁: DB I/O 在 ``_build_lock`` 下进行，L1 只做原子替换
     （双缓冲），读侧全程无锁，写操作不会因他人重载而排队到分钟级。
  4. 失效合并: 同一时刻的多个失效请求合并成一轮重载；pubsub 通知在
     ``_PUBSUB_COALESCE_WINDOW_SECONDS`` 窗口内只触发一次全量重载。
  5. 失败保留旧快照: 构建中途抛错时 L1 原封不动（INT-94 回归点——旧
     快照被清空会让执行链路提取不到 algorithm_result）。
"""

import json
import logging
import os
import uuid
from datetime import datetime
from threading import Lock, RLock, Thread
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

from shared.utils.log_handler import log_not_emit
from shared.infrastructure.config import BaseConfig
from shared.models.database import end_read_transaction

from algorithm_service.infrastructure.persistence.algorithm_repository import (
    algorithm_definition_query_repository,
    dimension_param_repository,
)
from algorithm_service.infrastructure.persistence.param_repository import (
    algorithm_param_repository,
    case_param_repository,
    reference_param_repository,
    mapping_repository,
    dimension_relation_repository,
)
from algorithm_service.infrastructure.persistence._param_profile_repositories import (
    param_profile_repository,
)

_REDIS_KEY = 'algo_config_cache'
_RELOAD_CHANNEL = 'algo_config_invalidate'

# pubsub 失效通知合并窗口（秒）：窗口内到达的多条通知只触发一次全量重载。
# 写操作每次都会 publish 一条，突发写（前端保存 + 参数同步）会连发多条，
# 原实现逐条全量重载造成重复构建。
_PUBSUB_COALESCE_WINDOW_SECONDS = float(
    os.environ.get('ALGO_CONFIG_PUBSUB_COALESCE_SECONDS', '0.2'))

# 参数来源合法值（_serialize_mappings / 来源反推的判定顺序：case→reference→device→api）
_VALID_MAPPING_SOURCES = ('case', 'reference', 'device', 'api')

# 本进程标识：pubsub 通知带上发布方，收到的若是自己发的说明本地已同步刷新过，
# 不再重复重载（Redis pub/sub 会把消息回投给发布者本身，原实现因此每写一次
# 都要多跑一轮全量重载）。
_INSTANCE_ID = f'{os.getpid()}-{uuid.uuid4().hex[:8]}'

# 快照里「按算法分桶」的键（切片刷新与移除按此清单整组处理）
_PER_ALGORITHM_KEYS = (
    'algorithms',
    'device_params',
    'api_params',
    'case_params',
    'reference_params',
    'mappings',
)

# 模块级 Redis 客户端单例：复用连接，避免每次 publish/save 都新建连接
_redis_client = None
_redis_client_lock = Lock()


def _resolve_actual_source(algo_type: str, source: str, source_param: str) -> str:
    """当 source 为 'evaluation' 或其他非法值时，根据 source_param 查对应参数表反推真实来源。

    仅供没有批量上下文（如外部单独调用 _serialize_mappings）时兜底使用；
    配置缓存重载走 ``_make_source_resolver`` 的内存版，不再逐条查库。
    """
    valid_sources = ('case', 'reference', 'device', 'api')
    if source in valid_sources:
        return source
    if not source_param:
        return 'case'
    # 依次在 case/reference/device/api 参数表里查找 source_param
    from algorithm_service.infrastructure.persistence.models import (
        CaseAlgorithmParam as CaseAlgorithmParamPO,
        AlgorithmReferenceParam as AlgorithmReferenceParamPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        AlgorithmApiParam as AlgorithmApiParamPO,
    )
    from shared.models.database import get_db_session
    session = get_db_session()
    if session.query(CaseAlgorithmParamPO).filter_by(
        algorithm_type=algo_type, param_code=source_param, deleted=False
    ).first():
        return 'case'
    if session.query(AlgorithmReferenceParamPO).filter_by(
        algorithm_type=algo_type, code=source_param, deleted=False
    ).first():
        return 'reference'
    if session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type=algo_type, param_code=source_param, deleted=False
    ).first():
        return 'device'
    if session.query(AlgorithmApiParamPO).filter_by(
        algorithm_type=algo_type, param_code=source_param, deleted=False
    ).first():
        return 'api'
    return 'case'


# ========== api_id 作用域合并（INT-1756 C6a） ==========
#
# 规则（父卡 INT-1751 第四节）：缓存分桶键不动，行携带 api_id，读时按唯一键合并——
# API 级行覆盖同键的算法级行（api_id IS NULL），未覆盖的算法级行继续生效。
# 合并键必须等于唯一键，不能拿 target_param 之类非唯一键字段当合并键。

def _api_param_merge_key(param: Dict[str, Any]):
    """algorithm_api_params 的合并键 = 唯一键 (direction, param_code)。"""
    return (param.get('direction'), param.get('code'))


def _mapping_merge_key(mapping: Dict[str, Any]):
    """param_mappings 的合并键 = 唯一键 (source, source_param, dimension_id)。

    ``target_param`` 不在唯一键里，API 级换 target 时按同键覆盖，而不是两行并存。
    """
    return (mapping.get('source'), mapping.get('source_param'),
            mapping.get('dimension_id'))


def _merge_level_rows(rows, api_id: Optional[int], key_fn):
    """算法级 + API 级行按唯一键合并（api_id 为 None 时只返回算法级行）。

    - 不传 api_id：只保留算法级行（存量行全部 ``api_id IS NULL``，与改动前一致），
      其它 API 的行不会串进来；
    - 传 api_id：命中该 API 的行覆盖同键算法级行（覆盖行占据算法级行的位置，
      保持输出顺序稳定），未被覆盖的算法级行原样保留；API 独有的行按缓存顺序追加。
    """
    rows = rows or []
    level_rows = [r for r in rows if r.get('api_id') is None]
    if api_id is None:
        return level_rows
    scoped_rows = [r for r in rows if r.get('api_id') == api_id]
    if not scoped_rows:
        return level_rows
    overrides = {}
    for row in scoped_rows:
        overrides.setdefault(key_fn(row), row)
    merged = []
    used_keys = set()
    for row in level_rows:
        key = key_fn(row)
        override = overrides.get(key)
        if override is not None:
            merged.append(override)
            used_keys.add(key)
        else:
            merged.append(row)
    for row in scoped_rows:
        key = key_fn(row)
        if key in used_keys:
            continue
        used_keys.add(key)
        merged.append(row)
    return merged


def _resolve_scope_rows(profile_rows, override_rows, key_fn):
    """策略行 + 实例覆盖行按唯一键合并（覆盖行替换同键策略行）。

    与 ``_merge_level_rows`` 的区别：来源是「策略声明」而不是「算法级默认行」，
    算法类型级默认层已废弃，因此策略行为空时只返回覆盖行。
    """
    overrides = {}
    for row in override_rows or []:
        overrides.setdefault(key_fn(row), row)
    merged = []
    used_keys = set()
    for row in profile_rows or []:
        key = key_fn(row)
        override = overrides.get(key)
        if override is not None:
            merged.append(override)
            used_keys.add(key)
        else:
            merged.append(row)
    for row in override_rows or []:
        key = key_fn(row)
        if key in used_keys:
            continue
        used_keys.add(key)
        merged.append(row)
    return merged


def _merge_mapping_buckets(mappings, api_id: Optional[int]):
    """对 mappings 的每个来源桶分别做 api_id 作用域合并。"""
    merged = {}
    for bucket, rows in (mappings or {}).items():
        if not isinstance(rows, list):
            merged[bucket] = rows
            continue
        merged[bucket] = _merge_level_rows(rows, api_id, _mapping_merge_key)
    return merged


def _get_redis():
    """获取 Redis 连接（惰性创建 + 复用；连接失败返回 None）"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    with _redis_client_lock:
        if _redis_client is None:
            try:
                import redis as redis_lib
                _redis_client = redis_lib.from_url(
                    BaseConfig.REDIS_URL, decode_responses=True)
            except Exception:
                return None
    return _redis_client


class AlgorithmConfigCache:
    """算法配置缓存器 - 单例模式

    L1（内存）+ L2（Redis）双层缓存:
    - 读: L1 → L2 → DB（逐级回源）
    - 写后刷新: 先更新 DB，再按受影响切片 reload L1，最后 PUBLISH 通知其他进程
    - 跨进程同步: 订阅 Redis pubsub，收到通知后自动 reload L1
    """

    _instance = None
    _instance_lock = Lock()
    # 保护「待重载范围 + L1 快照引用」，只做内存操作，绝不跨 DB/Redis I/O
    _reload_lock = RLock()
    # 串行化快照构建（DB 查询）：一次只构建一轮，并发的失效请求合并到下一轮
    _build_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._config_cache: Dict[str, Any] = {}
                    obj._last_reload_time: Optional[datetime] = None
                    obj._pending_full = False
                    obj._pending_algorithms: Set[str] = set()
                    obj._pending_dimensions: Set[int] = set()
                    # 先完成首次加载再登记单例，避免并发拿到空缓存实例
                    obj._load_all_configs()
                    cls._instance = obj
                    # 启动后台 pubsub 监听线程
                    obj._start_invalidation_listener()
        return cls._instance

    # ---- 快照结构 ----

    @staticmethod
    def _empty_snapshot() -> Dict[str, Any]:
        return {
            'algorithms': {},
            'device_params': {},
            'api_params': {},
            'case_params': {},
            'evaluation_dimension_params': {},
            'mappings': {},
            'reference_params': {},
            # 参数策略：profile_id → 字段声明 / 映射；api_id → profile_id
            'profile_params': {},
            'profile_mappings': {},
            'api_bindings': {},
        }

    @staticmethod
    def _copy_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """复制快照的外层与按算法分桶的内层 dict（值为列表，整组替换）。

        切片刷新时在副本上改，最后整份替换引用——读侧永远看到完整快照。
        """
        copied: Dict[str, Any] = {}
        for key, value in snapshot.items():
            copied[key] = dict(value) if isinstance(value, dict) else value
        return copied

    # ---- 构建（只查库，不触碰 L1） ----

    def _build_full_snapshot(self) -> Dict[str, Any]:
        """从 DB 构建整份新快照；中途失败直接抛出，旧快照不动（INT-94）。

        SQL 条数与算法/维度数量无关：每类配置一次批量 IN 查询。
        """
        log_not_emit('DEBUG', 'algorithm_config_cache',
                     'Starting to load all algorithm configs', category='algorithm')

        snapshot = self._empty_snapshot()

        algorithms = algorithm_definition_query_repository.list_online_definitions()
        algo_types: List[str] = []
        for algo in algorithms:
            algo_type = algo.get('algorithm_type') or algo.get('type')
            if not algo_type:
                continue
            algo_types.append(algo_type)
            snapshot['algorithms'][algo_type] = self._definition_slice(algo)

        log_not_emit('INFO', 'algorithm_config_cache',
                     f'Found {len(algo_types)} online algorithms', category='algorithm')

        device_params = self._group_rows(
            algorithm_param_repository.list_by_algorithms(algo_types, 'device'))
        api_params = self._group_rows(
            algorithm_param_repository.list_by_algorithms(algo_types, 'api'))
        case_params = self._group_rows(
            case_param_repository.list_by_algorithms(algo_types))
        reference_params = self._group_rows(
            reference_param_repository.list_by_algorithms(algo_types))
        mappings = self._group_rows(
            mapping_repository.list_by_algorithms(algo_types))
        relations = dimension_relation_repository.list_by_algorithms(algo_types)

        resolve_source = self._make_source_resolver(
            device_params, api_params, case_params, reference_params)

        for algo_type in algo_types:
            snapshot['device_params'][algo_type] = self._serialize_params(
                device_params.get(algo_type, []))
            snapshot['api_params'][algo_type] = self._serialize_params(
                api_params.get(algo_type, []))
            snapshot['case_params'][algo_type] = self._serialize_params(
                case_params.get(algo_type, []))
            snapshot['reference_params'][algo_type] = (
                self._serialize_reference_params(
                    reference_params.get(algo_type, [])))
            snapshot['mappings'][algo_type] = self._serialize_mappings(
                mappings.get(algo_type, []), resolve_source, algo_type)

        # 参数策略（API 参数与 API 映射的唯一来源）：按 profile 分组序列化，
        # 同时载入 api_id → profile_id 绑定，供运行时按 API 实例解析。
        profiles, profile_params, profile_mappings = param_profile_repository.load_active()
        snapshot['api_bindings'] = param_profile_repository.load_bindings()
        for profile in profiles:
            profile_id = profile.get('id')
            if profile_id is None:
                continue
            profile_algo = profile.get('algorithm_type') or ''
            snapshot['profile_params'][profile_id] = self._serialize_params(
                profile_params.get(profile_id, []))
            snapshot['profile_mappings'][profile_id] = self._serialize_mappings(
                profile_mappings.get(profile_id, []), resolve_source, profile_algo)

        # 维度参数：一次 IN 取回全部受影响维度（原实现逐条维度关系查一次）
        dim_ids = sorted({
            rel.get('dimension_id') for rel in relations
            if rel.get('dimension_id') is not None
        })
        snapshot['evaluation_dimension_params'].update(
            self._load_dimension_params(dim_ids))

        log_not_emit('INFO', 'algorithm_config_cache',
                     f'Config loaded successfully, {len(algo_types)} algorithms cached',
                     category='algorithm')
        return snapshot

    def _build_algorithm_slices(
        self, algorithm_types: Iterable[str]
    ) -> Dict[str, Any]:
        """构建指定算法类型的切片（定义 + 五类子配置 + 映射）。

        返回 ``types``（本次覆盖的算法，含已下线/已删除）与各切片数据；
        应用时 ``types`` 里没有在线定义的类型会被整组移除。
        只查库，不改 L1。
        """
        types = sorted({str(t) for t in algorithm_types or [] if t})
        if not types:
            return {'types': [], 'definitions': {}}

        definitions = {}
        for definition in algorithm_definition_query_repository.list_by_types(types):
            algo_type = (definition.get('algorithm_type')
                         or definition.get('type'))
            if algo_type:
                definitions[algo_type] = definition
        online = [
            t for t in types
            if t in definitions and definitions[t].get('status') == 'online'
        ]

        device_params = self._group_rows(
            algorithm_param_repository.list_by_algorithms(online, 'device'))
        api_params = self._group_rows(
            algorithm_param_repository.list_by_algorithms(online, 'api'))
        case_params = self._group_rows(
            case_param_repository.list_by_algorithms(online))
        reference_params = self._group_rows(
            reference_param_repository.list_by_algorithms(online))
        mappings = self._group_rows(
            mapping_repository.list_by_algorithms(online))

        resolve_source = self._make_source_resolver(
            device_params, api_params, case_params, reference_params)

        return {
            'types': types,
            'definitions': {
                t: self._definition_slice(definitions[t]) for t in online
            },
            'device_params': {
                t: self._serialize_params(device_params.get(t, []))
                for t in online
            },
            'api_params': {
                t: self._serialize_params(api_params.get(t, []))
                for t in online
            },
            'case_params': {
                t: self._serialize_params(case_params.get(t, []))
                for t in online
            },
            'reference_params': {
                t: self._serialize_reference_params(reference_params.get(t, []))
                for t in online
            },
            'mappings': {
                t: self._serialize_mappings(
                    mappings.get(t, []), resolve_source, t)
                for t in online
            },
        }

    def _load_dimension_params(
        self, dimension_ids: Iterable[int]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """构建评估维度参数切片（一次批量查询后按维度分组）。"""
        ids = sorted({
            int(dim_id) for dim_id in dimension_ids or [] if dim_id is not None
        })
        if not ids:
            return {}
        grouped: Dict[int, List[Dict[str, Any]]] = {dim_id: [] for dim_id in ids}
        for row in dimension_param_repository.list_by_dimensions(ids):
            dim_id = row.get('dimension_id')
            if dim_id is None:
                continue
            grouped.setdefault(int(dim_id), []).append(
                self._serialize_dimension_param(row))
        return grouped

    @staticmethod
    def _group_rows(rows: Iterable[dict]) -> Dict[str, List[dict]]:
        """按 algorithm_type 把批量查询结果分组。"""
        grouped: Dict[str, List[dict]] = {}
        for row in rows or []:
            algo_type = row.get('algorithm_type')
            if not algo_type:
                continue
            grouped.setdefault(algo_type, []).append(row)
        return grouped

    @staticmethod
    def _definition_slice(algo: dict) -> Dict[str, Any]:
        algo_type = algo.get('algorithm_type') or algo.get('type')
        return {
            'id': algo.get('id'),
            'type': algo_type,
            'name': algo.get('name'),
            'description': algo.get('description'),
            'status': algo.get('status'),
            'icon': algo.get('icon'),
            'display_order': algo.get('display_order'),
        }

    @staticmethod
    def _apply_algorithm_slices(snapshot: Dict[str, Any], slices: Dict[str, Any]):
        """把算法切片写进快照副本：在线类型逐桶刷新，其余整组移除。"""
        definitions = slices.get('definitions') or {}
        for algo_type in slices.get('types') or []:
            if algo_type in definitions:
                snapshot['algorithms'][algo_type] = definitions[algo_type]
                # algorithms 桶由 definitions 提供，其余按算法分桶逐个刷新
                for key in _PER_ALGORITHM_KEYS[1:]:
                    snapshot[key][algo_type] = (
                        slices.get(key, {}).get(algo_type, []))
            else:
                for key in _PER_ALGORITHM_KEYS:
                    snapshot[key].pop(algo_type, None)

    @staticmethod
    def _make_source_resolver(
        device_params: Dict[str, List[dict]],
        api_params: Dict[str, List[dict]],
        case_params: Dict[str, List[dict]],
        reference_params: Dict[str, List[dict]],
    ) -> Callable[[str, str], str]:
        """用已批量取回的参数做内存版来源反推（判定顺序同 _resolve_actual_source）。"""
        code_sets = {
            'device': {t: {p.get('code') for p in rows if p.get('code')}
                       for t, rows in device_params.items()},
            'api': {t: {p.get('code') for p in rows if p.get('code')}
                    for t, rows in api_params.items()},
            'case': {t: {p.get('code') for p in rows if p.get('code')}
                     for t, rows in case_params.items()},
            'reference': {t: {p.get('code') for p in rows if p.get('code')}
                          for t, rows in reference_params.items()},
        }

        def resolve(algo_type: str, source_param: str) -> str:
            if not source_param:
                return 'case'
            for source in _VALID_MAPPING_SOURCES:
                if source_param in code_sets[source].get(algo_type, ()):
                    return source
            return 'case'

        return resolve

    # ---- L1 安装 ----

    def _install_snapshot(self, snapshot: Dict[str, Any]):
        """原子替换 L1 快照（仅内存操作；L2 写在锁外）。"""
        with self._reload_lock:
            self._config_cache = snapshot
            self._last_reload_time = datetime.now()
            reload_time = self._last_reload_time
        self._save_to_redis(snapshot, reload_time)

    def _load_all_configs(self):
        """全量重载 L1（构建不持快照锁，失败保留旧快照）。

        从本地数据库加载所有算法配置（纯读路径，事务边界在此收口）。

        INT-1652：本函数只做 SELECT，原先既不 commit 也不 rollback —— 在 pubsub
        监听线程 / 单例首次构造时会话一直挂在 idle in transaction，持着表的
        ACCESS SHARE，把随后的迁移 DDL 顶在锁队列里（2026-10-23 事故中
        algorithm_service 就是这样堵住 case_algorithm_params 的）。加载结束
        （成功或异常）一律结束只读事务，连接立即归还，不再跨线程存活。
        """
        try:
            self._load_all_configs_locked()
        finally:
            end_read_transaction()

    def _load_all_configs_locked(self):
        """全量重载 L1（构建不持快照锁，失败保留旧快照）。

        不发 pubsub 通知：pubsub 监听线程与写后失效分别负责发布。
        """
        with self._build_lock:
            snapshot = self._build_full_snapshot()
            self._install_snapshot(snapshot)

    # ---- L2 Redis 持久化 ----

    def _save_to_redis(
        self,
        snapshot: Optional[Dict[str, Any]] = None,
        reload_time: Optional[datetime] = None,
    ):
        """将快照写入 Redis HASH（序列化与网络 I/O 均在快照锁外）。"""
        r = _get_redis()
        if r is None:
            return
        if snapshot is None:
            snapshot = self._config_cache
        if reload_time is None:
            reload_time = self._last_reload_time
        try:
            r.hset(_REDIS_KEY, mapping={
                'snapshot': json.dumps(snapshot, ensure_ascii=False, default=str),
                'reload_time': reload_time.isoformat() if reload_time else '',
            })
        except Exception as e:
            log_not_emit('WARN', 'algorithm_config_cache',
                         f'Failed to save snapshot to Redis: {e}', category='algorithm')

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
            r.publish(_RELOAD_CHANNEL, json.dumps({
                'instance': _INSTANCE_ID,
                'at': datetime.now().isoformat(),
            }))
        except Exception:
            logger.warning("发布配置缓存失效通知到 Redis pubsub 失败", exc_info=True)

    def _start_invalidation_listener(self):
        """启动后台线程，监听 Redis pubsub 失效通知（窗口内合并为一次重载）"""
        def _listen():
            import time

            from shared.models.database import remove_db_session
            while True:
                r = _get_redis()
                if r is None:
                    time.sleep(5)
                    continue
                try:
                    pubsub = r.pubsub()
                    pubsub.subscribe(_RELOAD_CHANNEL)
                    while True:
                        msg = pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=5)
                        if not msg:
                            continue
                        if msg.get('type') != 'message':
                            continue
                        notices = self._drain_invalidation_notices(
                            [msg.get('data')], pubsub)
                        foreign = [n for n in notices if n != _INSTANCE_ID]
                        if not foreign:
                            # 只有本进程自己发的通知：本地写路径已同步刷新过 L1
                            continue
                        log_not_emit(
                            'INFO', 'algorithm_config_cache',
                            f'Received {len(foreign)} foreign invalidation notice(s) '
                            'from Redis pubsub, reloading L1', category='algorithm')
                        # 本线程的线程级 session 跨进程/套件生命周期存活，引擎
                        # 换绑（pytest 模块级临时库、服务重启换库）后旧 session
                        # 首查即抛，reload 静默失败——每条通知强制丢弃旧
                        # session，绑定当前 engine（INT-94）。
                        remove_db_session()
                        self._load_all_configs()
                except Exception as e:
                    log_not_emit('WARN', 'algorithm_config_cache',
                                 f'Reload on invalidation notice failed, kept last snapshot: {e}',
                                 category='algorithm')
                    time.sleep(3)

        Thread(target=_listen, daemon=True, name='algo-cache-pubsub').start()

    @staticmethod
    def _notice_instance(raw) -> str:
        """解析通知载荷里的发布方标识；旧版纯时间戳载荷按「其他进程」处理。"""
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return ''
        if isinstance(payload, dict):
            return str(payload.get('instance') or '')
        return ''

    @classmethod
    def _drain_invalidation_notices(cls, first_payloads, pubsub) -> List[str]:
        """在合并窗口内吞掉后续通知，返回本轮合并的全部发布方标识。

        避免一次突发写连发多条通知时重复全量重载。
        """
        import time

        publishers = [cls._notice_instance(p) for p in first_payloads]
        deadline = time.monotonic() + max(_PUBSUB_COALESCE_WINDOW_SECONDS, 0.0)
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return publishers
            notice = pubsub.get_message(
                ignore_subscribe_messages=True, timeout=remain)
            if notice and notice.get('type') == 'message':
                publishers.append(cls._notice_instance(notice.get('data')))

    # ---- 序列化 ----

    @staticmethod
    def _serialize_params(params: List) -> List[Dict[str, Any]]:
        result = []
        for p in params:
            if not isinstance(p, dict):
                continue
            entry = {
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
            }
            # 输出字段取值路径（INT-1747）：只有 API 参数有该列，设备参数不带此键，
            # 避免把 None 混进 device 字段定义。
            if p.get('field_path') is not None:
                entry['field_path'] = p.get('field_path')
            # INT-1756：只有 algorithm_api_params 有 api_id 列；设备/用例参数
            # 的 PO 没有该字段，不补键，保持既有序列化结果不变。
            if 'api_id' in p:
                entry['api_id'] = p.get('api_id')
            result.append(entry)
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
            'pass_threshold': param.get('pass_threshold'),
        }

    @staticmethod
    def _serialize_mappings(
        mappings,
        resolve_source: Optional[Callable[[str, str], str]] = None,
        algorithm_type: str = '',
    ) -> Dict[str, Any]:
        # 合法来源值
        VALID_SOURCES = {'case', 'reference', 'device', 'api', 'case_config'}
        result = {'device': [], 'api': [], 'case': [], 'reference': [], 'case_config': []}
        if isinstance(mappings, list):
            for m in mappings:
                if not isinstance(m, dict):
                    continue
                source = m.get('source') or m.get('source_type') or 'api'
                # 修复历史脏数据：source='evaluation' 或其他非法值时反推真实来源
                if source not in VALID_SOURCES:
                    source_param = (
                        m.get('source_param') or m.get('source_field') or '')
                    if resolve_source is not None:
                        source = resolve_source(
                            m.get('algorithm_type') or algorithm_type,
                            source_param)
                    else:
                        source = _resolve_actual_source(
                            m.get('algorithm_type') or algorithm_type,
                            source,
                            source_param,
                        )
                # 行携带 api_id（INT-1756 C6a）：缓存分桶键不动，读侧按唯一键
                # 合并时用它区分算法级（NULL）与 API 实例级。
                entry = {
                    'source': source,
                    'source_param': m.get('source_param') or m.get('source_field'),
                    'source_direction': m.get('source_direction') or m.get('direction'),
                    'dimension_id': m.get('dimension_id'),
                    'dimension_name': m.get('dimension_name'),
                    'target_param': m.get('target_param') or m.get('target_field'),
                    'transform_type': m.get('transform_type') or m.get('transform_rule') or 'none',
                    'api_id': m.get('api_id'),
                }
                # 评估维度映射（dimension_id 非空）归入 evaluation 分组
                if m.get('dimension_id') is not None:
                    result.setdefault('evaluation', []).append(entry)
                elif source in result:
                    result[source].append(entry)
                else:
                    result.setdefault('evaluation', []).append(entry)
        return result

    # ---- 失效调度 ----

    def _register_invalidation(
        self,
        algorithm_types: Optional[Iterable[str]] = None,
        dimension_ids: Optional[Iterable[int]] = None,
        force_full: bool = False,
    ):
        """登记待重载范围（不查库）。

        范围为空（未给或给了全空值）视为「不知道受影响范围」，按全量处理，
        避免漏刷新导致写后读不一致。``force_full`` 供构建失败回填时使用。
        """
        algo_scope = {str(t) for t in algorithm_types or [] if t}
        dim_scope = {int(d) for d in dimension_ids or [] if d is not None}
        with self._reload_lock:
            if force_full or (algorithm_types is None and dimension_ids is None):
                self._pending_full = True
            elif not algo_scope and not dim_scope:
                # 给了范围但归一化后为空：宁全量不漏刷新
                self._pending_full = True
            else:
                self._pending_algorithms.update(algo_scope)
                self._pending_dimensions.update(dim_scope)

    def _flush_pending_invalidations(self):
        """执行一轮合并后的重载。

        构建在 ``_build_lock`` 下串行化：并发的失效请求中，先到者构建，
        后到者的范围留在待办里，由下一轮合并处理（同一突发最多重载两轮）。
        构建读库发生在「取走待办」之后，因此被取走的范围一定包含最新提交。
        """
        with self._build_lock:
            with self._reload_lock:
                full = self._pending_full
                algorithm_types = set(self._pending_algorithms)
                dimension_ids = set(self._pending_dimensions)
                self._pending_full = False
                self._pending_algorithms.clear()
                self._pending_dimensions.clear()

            if not (full or algorithm_types or dimension_ids):
                return  # 已被上一轮合并掉

            try:
                if full:
                    self._install_snapshot(self._build_full_snapshot())
                    return

                slices = (self._build_algorithm_slices(algorithm_types)
                          if algorithm_types else None)
                dim_params = (self._load_dimension_params(dimension_ids)
                              if dimension_ids else None)
                snapshot = self._copy_snapshot(self._config_cache)
                if slices is not None:
                    self._apply_algorithm_slices(snapshot, slices)
                if dim_params is not None:
                    snapshot['evaluation_dimension_params'].update(dim_params)
                self._install_snapshot(snapshot)
            except Exception:
                # 构建失败：旧快照原样保留（INT-94），范围放回待办，
                # 下一次失效/重载时重试，避免这一轮的刷新被吞掉
                self._register_invalidation(
                    algorithm_types, dimension_ids, force_full=full)
                raise

    # ---- 公开 API ----

    def invalidate(
        self,
        algorithm_types: Optional[Iterable[str]] = None,
        dimension_ids: Optional[Iterable[int]] = None,
    ):
        """写操作后调用: 按受影响范围刷新 L1 并通知其他进程。

        - 两个范围都不给 → 全量重载
        - 给范围 → 只重载对应切片（未受影响部分保持原快照）
        """
        self._register_invalidation(algorithm_types, dimension_ids)
        self._flush_pending_invalidations()
        self._publish_invalidation()

    def reload_if_changed(self) -> bool:
        """重新加载配置（与 reload 等效，保留接口兼容）"""
        try:
            self.reload()
            return True
        except Exception as e:
            log_not_emit('ERROR', 'algorithm_config_cache',
                         f'Error checking config changes: {e}', category='algorithm')
            return False

    def reload(self) -> bool:
        """强制重新加载，并通知其他进程"""
        self._register_invalidation()
        self._flush_pending_invalidations()
        self._publish_invalidation()
        return True

    def get_last_reload_time(self) -> Optional[str]:
        if self._last_reload_time:
            return self._last_reload_time.isoformat()
        return None

    def get_all_algorithms(self) -> List[Dict[str, Any]]:
        cache = self._config_cache
        return [
            {'type': k, 'name': v.get('name', k), 'description': v.get('description')}
            for k, v in cache.get('algorithms', {}).items()
        ]

    def get_algorithm_config(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        cache = self._config_cache
        if algorithm_type not in cache.get('algorithms', {}):
            return None
        # INT-1756：本入口没有 api_id（proto 亦不带），按算法级默认口径返回，
        # 不能把某个 API 实例级行当作算法级配置透出。
        return {
            'definition': cache['algorithms'].get(algorithm_type),
            'device_params': cache['device_params'].get(algorithm_type, []),
            'api_params': _merge_level_rows(
                cache['api_params'].get(algorithm_type, []), None,
                _api_param_merge_key),
            'case_params': cache['case_params'].get(algorithm_type, []),
            'mappings': _merge_mapping_buckets(
                cache['mappings'].get(algorithm_type, {}), None),
        }

    def get_algorithm_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """算法级合并参数（设备参数 + 算法级 API 默认行）。

        本入口没有 ``api_id``：API 参数按算法级默认口径直接读快照（迁移后为空），
        不走 ``get_api_params``，避免把「调用方本就不该带 api_id」当成异常告警。
        实例作用域的 API 声明请用 :meth:`get_api_params`。
        """
        cache = self._config_cache
        device_params = cache.get('device_params', {}).get(algorithm_type, [])
        api_level_rows = _merge_level_rows(
            cache.get('api_params', {}).get(algorithm_type, []), None,
            _api_param_merge_key)
        return device_params + api_level_rows

    def get_device_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('device_params', {}).get(algorithm_type, [])

    def get_api_params(
        self, algorithm_type: str, api_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取 API 参数 = 策略声明 + 本 API 覆盖行。

        算法类型级默认层（api_id IS NULL）已废弃：不传 api_id 没有任何声明可返回，
        直接返回空列表——调用方必须带 api_id（执行 / 评估 / 报告链路均已接线）。
        """
        if api_id is None:
            log_not_emit(
                'WARN', 'algorithm_config_cache',
                f'get_api_params 未带 api_id（algorithm_type={algorithm_type}）：'
                f'算法类型级默认层已废弃，按空声明返回',
                category='algorithm', algorithm_type=algorithm_type,
            )
            return []
        cache = self._config_cache
        overrides = [
            row for row in cache.get('api_params', {}).get(algorithm_type, [])
            if row.get('api_id') == api_id
        ]
        profile_id = cache.get('api_bindings', {}).get(api_id)
        profile_rows = (
            cache.get('profile_params', {}).get(profile_id, []) if profile_id else []
        )
        resolved = _resolve_scope_rows(profile_rows, overrides, _api_param_merge_key)
        if not resolved:
            log_not_emit(
                'WARN', 'algorithm_config_cache',
                f'get_api_params 空声明：algorithm_type={algorithm_type} api_id={api_id} '
                f'（profile_id={profile_id}，策略与实例覆盖均为空）',
                category='algorithm', algorithm_type=algorithm_type,
            )
        return resolved

    def get_source_mappings(
        self, algorithm_type: str, source: str,
        api_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """跨桶取某来源的映射（输出字段映射不区分维度桶）。

        维度级映射在 ``_serialize_mappings`` 中归入 ``evaluation`` 桶，
        但输出字段映射需要的是「该来源的全部行」，因此按来源跨桶汇总。
        """
        rows: List[Dict[str, Any]] = []
        for bucket_rows in self._scoped_mapping_buckets(algorithm_type, api_id).values():
            if not isinstance(bucket_rows, list):
                continue
            rows.extend(
                row for row in bucket_rows
                if isinstance(row, dict) and row.get('source') == source
            )
        return rows

    def _scoped_mapping_buckets(
        self, algorithm_type: str, api_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """映射分桶按 API 作用域解析。

        - ``source='api'`` 的来源行：策略映射 + 本 API 覆盖行（覆盖优先）；
        - 其余来源（case / reference / device / case_config）：仍为算法类型级，
          只保留 ``api_id IS NULL`` 的行；
        - 不传 api_id：只返回算法级行（API 来源为空）。
        """
        cache = self._config_cache
        buckets = cache.get('mappings', {}).get(algorithm_type, {}) or {}
        base: Dict[str, Any] = {}
        for bucket, rows in buckets.items():
            if not isinstance(rows, list):
                base[bucket] = rows
                continue
            base[bucket] = [row for row in rows if row.get('api_id') is None]
        if api_id is None:
            return base

        profile_id = cache.get('api_bindings', {}).get(api_id)
        profile_buckets = (
            cache.get('profile_mappings', {}).get(profile_id, {}) if profile_id else {}
        )
        override_buckets: Dict[str, List[Dict[str, Any]]] = {}
        for bucket, rows in buckets.items():
            if not isinstance(rows, list):
                continue
            scoped = [row for row in rows if row.get('api_id') == api_id]
            if scoped:
                override_buckets[bucket] = scoped

        merged: Dict[str, Any] = {}
        for bucket in set(base) | set(profile_buckets) | set(override_buckets):
            merged[bucket] = _resolve_scope_rows(
                profile_buckets.get(bucket, []),
                override_buckets.get(bucket, []),
                _mapping_merge_key,
            )
        return merged

    def get_case_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('case_params', {}).get(algorithm_type, [])

    def get_reference_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        return self._config_cache.get('reference_params', {}).get(algorithm_type, [])

    def get_param_mapping(
        self, algorithm_type: str, component_type: str,
        api_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取组件参数映射（API 来源按「策略 + 实例覆盖」解析）。

        修改点（本轮）：算法类型级默认层废弃，``source='api'`` 的映射只来自
        策略 ``param_profile_mappings`` 与实例覆盖行；其余来源仍是算法级。
        """
        if component_type == 'evaluation':
            return self._get_evaluation_mappings(algorithm_type, api_id=api_id)
        buckets = self._scoped_mapping_buckets(algorithm_type, api_id)
        return buckets.get(component_type, [])

    def _get_evaluation_mappings(
        self, algorithm_type: str, cache: Optional[Dict[str, Any]] = None,
        api_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        # 先做 API 作用域解析（策略 + 覆盖），再走原有的四元组去重（INT-1751 硬约束 2）
        mappings = self._scoped_mapping_buckets(algorithm_type, api_id)
        result = []
        seen = set()
        # 维度级映射（dimension_id 非空）在 _serialize_mappings 中统一归入 evaluation 桶，
        # source 保留原值（case/reference/device/api/case_config）
        for m in mappings.get('evaluation', []):
            key = (m.get('source'), m.get('source_param'), m.get('target_param'), m.get('dimension_id'))
            if key in seen:
                continue
            seen.add(key)
            result.append({
                'source': m.get('source', 'api'),
                'source_param': m.get('source_param'),
                'target_param': m.get('target_param'),
                'direction': 'output',
                'dimension_id': m.get('dimension_id'),
                'dimension_name': m.get('dimension_name'),
                'transform_type': m.get('transform_type', 'none'),
                'api_id': m.get('api_id'),
            })
        # 非维度级映射仍分布在各来源桶
        for source in ['device', 'api', 'case', 'case_config', 'reference', 'adjusted_reference']:
            for m in mappings.get(source, []):
                key = (source, m.get('source_param'), m.get('target_param'), m.get('dimension_id'))
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    'source': source,
                    'source_param': m['source_param'],
                    'target_param': m['target_param'],
                    'direction': 'output',
                    'dimension_id': m.get('dimension_id'),
                    'dimension_name': m.get('dimension_name'),
                    'transform_type': m.get('transform_type', 'none'),
                    'api_id': m.get('api_id'),
                })
        if 'adjusted_reference' not in mappings:
            for source in ['device', 'api', 'case', 'case_config', 'reference']:
                for m in mappings.get(source, []):
                    target_param = m.get('target_param', '')
                    if target_param in ['rttm_ref', 'stm_ref', 'asr_ref']:
                        key = ('adjusted_reference', target_param, target_param, m.get('dimension_id'))
                        if key in seen:
                            continue
                        seen.add(key)
                        result.append({
                            'source': 'adjusted_reference',
                            'source_param': target_param,
                            'target_param': target_param,
                            'direction': 'output',
                            'dimension_id': m.get('dimension_id'),
                            'dimension_name': m.get('dimension_name'),
                            'transform_type': m.get('transform_type', 'none'),
                            'api_id': m.get('api_id'),
                        })
        return result

    def get_evaluation_dimension_params(self, dimension_id: int) -> List[Dict[str, Any]]:
        return self._config_cache.get('evaluation_dimension_params', {}).get(dimension_id, [])

    def get_algorithm_definition(self, algorithm_type: str) -> Optional[Dict[str, Any]]:
        return self._config_cache.get('algorithms', {}).get(algorithm_type)


def get_config_cache() -> AlgorithmConfigCache:
    """获取配置缓存器单例"""
    return AlgorithmConfigCache()
