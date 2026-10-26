# -*- coding: utf-8 -*-
"""task_service.TagConfigService 防腐层仓储 — gRPC ACL 适配层。

封装 audio_service 对 task_service.TagConfigService 的跨域 gRPC 调用，
替代 audio_service/infrastructure/persistence/audio_repository.py 中
直接 import shared.clients.grpc_clients.get_tag_config_service_stub。

- 读操作通过 gRPC 完成，返回 dict / list，不返回 ORM 对象。
- 采用具体类 + 模块级单例。
"""
import logging
import threading
import time
from typing import Dict, List, Optional

from shared.infrastructure.config import BaseConfig
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from audio_service.domain.exceptions import TagResolutionError

logger = logging.getLogger(__name__)


# ========== 进程内标签快照缓存（INT-2000 / INT-2047）==========
# 列表/详情解析 tag_id → name 原先每请求都要向 task_service 拉一次全量标签表
# （docker 主库 99 个标签 ≈25.8KB，INT-1992 分段实测 21.2ms/请求 = ListAudios
# 单请求的 33.7%），而解析的只是本页 ≤20 条音频的 tag_id。标签表变更极少，
# 因此把「全量 tag_id → name 快照」放在进程内：TTL 内零跨服务调用。
#
# INT-2047（TTL 过期在请求线程内联刷新 → 列表周期性秒级毛刺）改造：
# - **请求线程只读快照**：快照过期 / 冷启动时立即返回当前快照（可能为空），
#   刷新一律交给后台 daemon 线程；请求侧不再等待上游（旧实现这一点让第一个
#   到达的请求承担整段跨服务 RPC，其余等待者最长阻塞 5 s）。
# - **上游一律带 deadline**：刷新调用显式传 ``timeout=``（默认 2 s，配置化）；
#   不传时会落到共享 channel 的默认 deadline（GRPC_CLIENT_DEADLINE_SECONDS
#   = 60 s），与线上观测到的 29.5 s 刷新同量级，足以把上游抖动放大成列表毛刺。
# - **refresh-ahead**：快照活到 TTL 的 ratio（默认 0.7）时顺带排期一次后台
#   刷新，使过期瞬间通常已命中新快照；刷新同一时刻最多一个线程。
# - **失败退避**：刷新失败后 backoff 秒内不再排期，避免上游挂掉时每个过期
#   请求都排一次刷新。
# - **起服预热**：进程启动时同步拉一次快照（见 ``warm_tag_acl_snapshot``），
#   避免首轮请求降级成数字 id。
#
# 两条语义红线（卡面「范围与不做」第 2 条）：
# - 「查不到」= 上游成功、快照里确实没有该 id → 可短 TTL 负缓存（默认关），
#   绝不影响已缓存的正向映射，调用方照旧回落数字 id；
# - 「查不了」= 上游抛异常/超时 → 不写缓存、不覆盖现有快照，继续用上一份
#   快照（可能为空）+ 告警日志降级，且不把这次失败固化成 TTL 内的空结果。
#
# 陈旧窗口：本服务不写标签（写路径建标签后主动失效），重命名/删除最长
# TTL 秒后才可见 —— 换取一次 RPC/TTL 而不是一次 RPC/请求。

TAG_CACHE_DEFAULT_TTL_SECONDS = 60
TAG_CACHE_DEFAULT_NEGATIVE_SECONDS = 0
# INT-2047：刷新 deadline / refresh-ahead 比例 / 失败退避 / 起服预热默认值。
# 与 shared/infrastructure/config.py 的 BaseConfig 默认值保持同一口径。
TAG_CACHE_DEFAULT_REFRESH_TIMEOUT_SECONDS = 2.0
TAG_CACHE_DEFAULT_REFRESH_AHEAD_RATIO = 0.7
TAG_CACHE_DEFAULT_REFRESH_BACKOFF_SECONDS = 1.0
TAG_CACHE_DEFAULT_WARMUP_ENABLED = True
# 起服预热的尝试次数：宿主机 → docker task_service 首连实测可到 10 s 以上
# （首调 DEADLINE_EXCEEDED、稳定后 ~1 s），单次尝试经常赶不上建连。
TAG_CACHE_DEFAULT_WARMUP_ATTEMPTS = 5

_SNAPSHOT: Dict[int, str] = {}          # 只整体替换，不原地改（读侧拿引用即用）
_SNAPSHOT_AT: Optional[float] = None    # 最近一次成功加载的 monotonic 时刻
_NEGATIVE: Dict[int, float] = {}        # 查不到 的 tag_id → 负缓存过期时刻
_MISS_LOGGED = set()                    # 本快照代已 INFO 记过的查不到 id（防刷屏）
_REFRESHING = False                     # 后台刷新线程是否在跑（同一时刻最多一个）
_REFRESH_THREAD: Optional[threading.Thread] = None
_LAST_ATTEMPT_AT: Optional[float] = None   # 最近一次排期刷新的 monotonic 时刻
_LAST_ATTEMPT_FAILED = False            # 最近一次刷新是否失败（退避判据）
_EPOCH = 0                              # reset 代际：旧代后台线程的结果一律丢弃
_COND = threading.Condition(threading.Lock())
_STATS = {
    'hit': 0,                # 命中快照的 id 数
    'miss': 0,               # 快照里没有的 id 数
    'negative_hit': 0,       # 命中负缓存（已知查不到）的 id 数
    'refresh_ok': 0,         # 上游刷新成功次数
    'refresh_fail': 0,       # 上游刷新失败次数
    'degraded': 0,           # 因上游失败而降级的刷新次数
    'refresh_scheduled': 0,  # 排期到后台线程的刷新次数
    'request_stale': 0,      # 请求侧读到过期/空快照（立即降级、未阻塞）的次数
}


def _config_int(name: str, default: int) -> int:
    """读取配置项（负数/非法按默认值），与 shared 既有缓存配置同口径。"""
    try:
        value = getattr(BaseConfig, name, None)
        if value is None:
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def tag_cache_ttl_seconds() -> int:
    """快照 TTL 秒数（0 = 关闭缓存，退回每请求打上游）。"""
    return _config_int('AUDIO_TAG_ACL_CACHE_TTL_SECONDS', TAG_CACHE_DEFAULT_TTL_SECONDS)


def tag_cache_negative_seconds() -> int:
    """「查不到」负缓存秒数（0 = 关闭）。"""
    return _config_int('AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS',
                       TAG_CACHE_DEFAULT_NEGATIVE_SECONDS)


def _config_float(name: str, default: float) -> float:
    """读取浮点配置项（非法/负数按默认值）。"""
    try:
        value = getattr(BaseConfig, name, None)
        if value is None:
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _config_bool(name: str, default: bool) -> bool:
    """读取布尔配置项（``True/1/yes/on`` 为真，非法按默认值）。"""
    value = getattr(BaseConfig, name, None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in ('true', '1', 'yes', 'on'):
            return True
        if raw in ('false', '0', 'no', 'off', ''):
            return False
    return default


def tag_cache_refresh_timeout_seconds() -> float:
    """刷新（跨服务 ListTags）的 deadline（秒；<=0 = 不显式传，落默认 60 s）。"""
    return _config_float('AUDIO_TAG_ACL_REFRESH_TIMEOUT_SECONDS',
                         TAG_CACHE_DEFAULT_REFRESH_TIMEOUT_SECONDS)


def tag_cache_refresh_ahead_ratio() -> float:
    """refresh-ahead 比例（0.7 = TTL 的 70% 处预热；<=0 或 >=1 = 关闭预热）。"""
    return _config_float('AUDIO_TAG_ACL_REFRESH_AHEAD_RATIO',
                         TAG_CACHE_DEFAULT_REFRESH_AHEAD_RATIO)


def tag_cache_refresh_backoff_seconds() -> float:
    """刷新失败后的重试退避（秒，0 = 不退避）。"""
    return _config_float('AUDIO_TAG_ACL_REFRESH_BACKOFF_SECONDS',
                         TAG_CACHE_DEFAULT_REFRESH_BACKOFF_SECONDS)


def tag_cache_warmup_enabled() -> bool:
    """起服预热开关（默认开）。"""
    return _config_bool('AUDIO_TAG_ACL_WARMUP_ENABLED',
                        TAG_CACHE_DEFAULT_WARMUP_ENABLED)


def _normalize_tag_id(value) -> Optional[int]:
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_fresh(now: float, ttl: int) -> bool:
    """快照是否仍在 TTL 内（ttl=0 视为永不新鲜 = 缓存关闭）。"""
    return _SNAPSHOT_AT is not None and ttl > 0 and (now - _SNAPSHOT_AT) < ttl


def _prefetch_due(now: float, ttl: int) -> bool:
    """是否已到 refresh-ahead 时刻（快照活到 TTL 的 ratio 比例）。

    提前排期一次后台刷新，使 TTL 真正到期时快照通常已经是新的 —— 请求侧
    永远命中新鲜快照，而不是「过期后先降级、再等刷新回填」。
    """
    ratio = tag_cache_refresh_ahead_ratio()
    if not (0.0 < ratio < 1.0) or _SNAPSHOT_AT is None:
        return False
    return (now - _SNAPSHOT_AT) >= ttl * ratio


def get_tag_acl_cache_stats() -> Dict[str, int]:
    """缓存计数快照（供 INT-1471 复测轮归因与单测断言）。

    ``refresh_scheduled`` / ``request_stale`` 是 INT-2047 新增的归因判据：
    前者说明刷新确实排到了后台线程，后者是请求侧读到过期快照并立即降级的
    次数 —— 两者都增长时，请求侧没有任何一次等待上游。
    """
    with _COND:
        return dict(_STATS)


def wait_tag_acl_refresh_idle(timeout: float = 5.0) -> bool:
    """等待后台刷新线程结束（起服编排与单测用）；返回是否已空闲。"""
    deadline = time.monotonic() + max(0.0, timeout)
    with _COND:
        while _REFRESHING:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _COND.wait(timeout=min(remaining, 0.05))
        return True


def reset_tag_acl_cache() -> None:
    """清空快照/负缓存/计数（测试与本地排障用）。"""
    global _SNAPSHOT, _SNAPSHOT_AT, _REFRESHING, _REFRESH_THREAD
    global _LAST_ATTEMPT_AT, _LAST_ATTEMPT_FAILED, _EPOCH
    with _COND:
        # 代际 +1：清理前已在跑的后台刷新线程回来时按旧代丢弃，不会把它的
        # 结果写进新一轮的缓存。
        _EPOCH += 1
        _SNAPSHOT = {}
        _SNAPSHOT_AT = None
        _NEGATIVE.clear()
        _MISS_LOGGED.clear()
        _REFRESHING = False
        _REFRESH_THREAD = None
        _LAST_ATTEMPT_AT = None
        _LAST_ATTEMPT_FAILED = False
        for key in _STATS:
            _STATS[key] = 0
        _COND.notify_all()


def invalidate_tag_snapshot(reason: str = '') -> None:
    """丢弃当前快照（写路径新建标签后调用，避免新标签在 TTL 内显示数字 id）。

    INT-2047：失效后不再让下一个请求线程同步刷新，而是立刻排期一次后台
    刷新 —— 新标签的名字最多晚一个刷新耗时（毫秒级）出现在列表里。
    """
    global _SNAPSHOT_AT
    with _COND:
        _SNAPSHOT_AT = None
        _NEGATIVE.clear()
        _MISS_LOGGED.clear()
        # 没有 loader 可用时（单测/早于首次解析）留空，等首个请求排期。
        _schedule_refresh_locked(_default_loader(), reason='invalidated')
    if reason:
        logger.info("audio_tag_acl_cache invalidated reason=%s", reason)


def _default_loader():
    """默认快照 loader（模块级单例的方法，懒解析避免前向引用）。"""
    return tag_acl_repository._load_tag_id_to_name_snapshot_strict


def _schedule_refresh_locked(loader, reason: str) -> bool:
    """在持锁状态下排期一次后台刷新；返回是否真的排期了。

    单飞：同一时刻最多一个刷新线程；失败后在 backoff 窗口内不再排期，
    避免上游不可用时每个过期请求都打一次上游。
    """
    global _REFRESHING, _REFRESH_THREAD, _LAST_ATTEMPT_AT

    if _REFRESHING or loader is None:
        return False
    now = time.monotonic()
    backoff = tag_cache_refresh_backoff_seconds()
    if (_LAST_ATTEMPT_FAILED and backoff > 0 and _LAST_ATTEMPT_AT is not None
            and (now - _LAST_ATTEMPT_AT) < backoff):
        return False

    _REFRESHING = True
    _LAST_ATTEMPT_AT = now
    _STATS['refresh_scheduled'] += 1
    thread = threading.Thread(
        target=_refresh_worker,
        args=(loader, _EPOCH, reason),
        name='audio-tag-acl-refresh',
        daemon=True,       # 进程退出时不拖住关机（长驻服务由解释器回收）
    )
    _REFRESH_THREAD = thread
    thread.start()
    logger.info(
        "audio_tag_acl_cache refresh_scheduled reason=%s ttl_s=%d "
        "deadline_s=%.2f in_request_thread=false",
        reason, tag_cache_ttl_seconds(), tag_cache_refresh_timeout_seconds(),
    )
    return True


def _refresh_worker(loader, epoch: int, reason: str) -> None:
    """后台刷新线程：拉上游并回填快照；失败只降级，绝不清空快照。"""
    global _SNAPSHOT, _SNAPSHOT_AT, _REFRESHING, _LAST_ATTEMPT_FAILED

    started = time.monotonic()
    try:
        fresh_snapshot = loader()
    except Exception as exc:  # 上游异常/超时 = 「查不了」，绝不写缓存
        cost_ms = (time.monotonic() - started) * 1000.0
        with _COND:
            if epoch == _EPOCH:
                _REFRESHING = False
                _LAST_ATTEMPT_FAILED = True
                _STATS['refresh_fail'] += 1
                _STATS['degraded'] += 1
            stale_items = len(_SNAPSHOT)
            _COND.notify_all()
        logger.warning(
            "audio_tag_acl_cache refresh_fail cost_ms=%.1f err=%s:%s "
            "serve_stale_items=%d ttl_s=%d reason=%s in_request_thread=false",
            cost_ms, type(exc).__name__, exc, stale_items,
            tag_cache_ttl_seconds(), reason,
        )
        return

    cost_ms = (time.monotonic() - started) * 1000.0
    with _COND:
        if epoch == _EPOCH:
            _SNAPSHOT = fresh_snapshot
            _SNAPSHOT_AT = time.monotonic()
            _REFRESHING = False
            _LAST_ATTEMPT_FAILED = False
            _STATS['refresh_ok'] += 1
            _MISS_LOGGED.clear()   # 新快照代：查不到的 id 重新记一次 INFO
        snapshot = _SNAPSHOT
        _COND.notify_all()
    logger.info(
        "audio_tag_acl_cache refresh_ok items=%d cost_ms=%.1f ttl_s=%d "
        "reason=%s in_request_thread=false",
        len(snapshot), cost_ms, tag_cache_ttl_seconds(), reason,
    )


def _warmup_allowed() -> bool:
    if tag_cache_ttl_seconds() <= 0:
        logger.info("audio_tag_acl_cache warmup_skipped reason=cache_disabled")
        return False
    if not tag_cache_warmup_enabled():
        logger.info("audio_tag_acl_cache warmup_skipped reason=disabled")
        return False
    return True


def _warmup_attempt(loader, epoch: int, attempt: int, attempts: int) -> bool:
    """预热的一次尝试：成功回填快照并返回 True，失败只告警、不动现有快照。"""
    global _SNAPSHOT, _SNAPSHOT_AT, _LAST_ATTEMPT_AT, _LAST_ATTEMPT_FAILED

    started = time.monotonic()
    try:
        snapshot = loader()
    except Exception as exc:
        cost_ms = (time.monotonic() - started) * 1000.0
        with _COND:
            _LAST_ATTEMPT_AT = time.monotonic()
            _LAST_ATTEMPT_FAILED = True
            stale_items = len(_SNAPSHOT)
        logger.warning(
            "audio_tag_acl_cache warmup_fail attempt=%d/%d cost_ms=%.1f "
            "err=%s:%s deadline_s=%.2f serve_stale_items=%d "
            "in_request_thread=false",
            attempt, attempts, cost_ms, type(exc).__name__, exc,
            tag_cache_refresh_timeout_seconds(), stale_items,
        )
        return False

    cost_ms = (time.monotonic() - started) * 1000.0
    with _COND:
        if epoch == _EPOCH:
            _SNAPSHOT = snapshot
            _SNAPSHOT_AT = time.monotonic()
            _LAST_ATTEMPT_FAILED = False
            _STATS['refresh_ok'] += 1
            _MISS_LOGGED.clear()
        items = len(_SNAPSHOT)
    logger.info(
        "audio_tag_acl_cache warmup_ok items=%d cost_ms=%.1f ttl_s=%d "
        "deadline_s=%.2f attempt=%d/%d in_request_thread=false",
        items, cost_ms, tag_cache_ttl_seconds(),
        tag_cache_refresh_timeout_seconds(), attempt, attempts,
    )
    return True


def warm_tag_acl_snapshot(loader=None, attempts: Optional[int] = None,
                          epoch: Optional[int] = None) -> bool:
    """起服预热：拉一次快照（带 deadline），失败按 attempts/退避重试。

    请求线程不再刷新快照（INT-2047），没有预热时冷启动的头几个列表请求会
    降级成数字 id。宿主机 → docker task_service 的首连本身可能要几秒
    （实测首个 ListTags 10 s 超时、稳定后 ~1 s），所以服务启动用
    ``start_tag_acl_warmup``（后台线程 + 重试），不拿启动时间赌建连。
    """
    global _LAST_ATTEMPT_AT, _LAST_ATTEMPT_FAILED

    if not _warmup_allowed():
        return False
    if loader is None:
        loader = _default_loader()
    total = attempts if attempts and attempts > 0 else TAG_CACHE_DEFAULT_WARMUP_ATTEMPTS
    backoff = tag_cache_refresh_backoff_seconds()
    target_epoch = _EPOCH if epoch is None else epoch
    for attempt in range(1, total + 1):
        if _warmup_attempt(loader, target_epoch, attempt, total):
            return True
        if attempt < total and backoff > 0:
            time.sleep(backoff)
    with _COND:
        _LAST_ATTEMPT_AT = time.monotonic()
        _LAST_ATTEMPT_FAILED = True
        _STATS['refresh_fail'] += 1
        _STATS['degraded'] += 1
    return False


def _warmup_worker(loader, epoch: int) -> None:
    """后台预热线程：重试到拿到快照或次数用完，然后交还刷新权。"""
    global _REFRESHING
    try:
        warm_tag_acl_snapshot(loader, epoch=epoch)
    finally:
        with _COND:
            if epoch == _EPOCH:
                _REFRESHING = False
            _COND.notify_all()


def start_tag_acl_warmup(loader=None) -> bool:
    """起服预热（后台 daemon）：不占用启动时间，失败按退避重试。"""
    global _REFRESHING, _REFRESH_THREAD, _LAST_ATTEMPT_AT

    if not _warmup_allowed():
        return False
    if loader is None:
        loader = _default_loader()
    with _COND:
        if _REFRESHING:
            return False
        _REFRESHING = True
        _LAST_ATTEMPT_AT = time.monotonic()
        _STATS['refresh_scheduled'] += 1
        thread = threading.Thread(
            target=_warmup_worker,
            args=(loader, _EPOCH),
            name='audio-tag-acl-warmup',
            daemon=True,
        )
        _REFRESH_THREAD = thread
        thread.start()
    logger.info(
        "audio_tag_acl_cache warmup_scheduled attempts=%d deadline_s=%.2f "
        "backoff_s=%.2f",
        TAG_CACHE_DEFAULT_WARMUP_ATTEMPTS,
        tag_cache_refresh_timeout_seconds(),
        tag_cache_refresh_backoff_seconds(),
    )
    return True


def _load_in_request_thread(loader) -> tuple:
    """缓存关闭（TTL=0，线上紧急开关）时的旧行为：本线程同步拉一次。"""
    global _SNAPSHOT, _SNAPSHOT_AT

    started = time.monotonic()
    try:
        snapshot = loader()
    except Exception as exc:
        cost_ms = (time.monotonic() - started) * 1000.0
        with _COND:
            _STATS['refresh_fail'] += 1
            _STATS['degraded'] += 1
            stale = _SNAPSHOT
            stale_items = len(stale)
        logger.warning(
            "audio_tag_acl_cache refresh_fail cost_ms=%.1f err=%s:%s "
            "serve_stale_items=%d ttl_s=0 in_request_thread=true",
            cost_ms, type(exc).__name__, exc, stale_items,
        )
        return stale, False

    cost_ms = (time.monotonic() - started) * 1000.0
    with _COND:
        _SNAPSHOT = snapshot
        _SNAPSHOT_AT = time.monotonic()
        _STATS['refresh_ok'] += 1
        _MISS_LOGGED.clear()
        snap = _SNAPSHOT
    logger.info(
        "audio_tag_acl_cache refresh_ok items=%d cost_ms=%.1f ttl_s=0 "
        "in_request_thread=true",
        len(snap), cost_ms,
    )
    return snap, True


def _get_snapshot(loader) -> tuple:
    """取当前快照；请求线程只读，过期只排期后台刷新，不等待、不刷新。

    返回 ``(snapshot, authoritative)``：authoritative=False 表示快照已过期
    （或冷启动还没拉到）、刷新已排期，此时「查不到」不可信，不做负缓存。
    """
    ttl = tag_cache_ttl_seconds()
    if ttl <= 0:
        # TTL=0 = 关闭缓存（线上紧急开关）：保持 INT-2000 之前的每请求拉一次。
        return _load_in_request_thread(loader)

    now = time.monotonic()
    with _COND:
        snapshot = _SNAPSHOT
        if _is_fresh(now, ttl):
            if _prefetch_due(now, ttl):
                _schedule_refresh_locked(loader, reason='prefetch')
            return snapshot, True
        # 过期 / 冷启动：立即返回当前快照（可能为空），刷新交给后台线程。
        # 请求线程绝不在这里调用 loader —— 否则又把跨服务时延转嫁给了用户请求。
        _STATS['request_stale'] += 1
        _schedule_refresh_locked(loader, reason='expired')
        return snapshot, False


def _record_miss(missing: List[int], authoritative: bool) -> None:
    """记录「查不到」；仅在权威快照（上游本次成功）下写负缓存。"""
    now = time.monotonic()
    negative_ttl = tag_cache_negative_seconds()
    known = 0
    new_ids: List[int] = []
    with _COND:
        for tid in [k for k, exp in _NEGATIVE.items() if exp <= now]:
            _NEGATIVE.pop(tid, None)
        for tid in missing:
            if tid in _NEGATIVE:
                known += 1
            elif negative_ttl and authoritative:
                _NEGATIVE[tid] = now + negative_ttl
            if tid not in _MISS_LOGGED:
                _MISS_LOGGED.add(tid)
                new_ids.append(tid)
        _STATS['miss'] += len(missing)
        _STATS['negative_hit'] += known
    # 同一快照代内重复出现的「查不到」只留 debug，避免一个已删标签把列表日志刷满
    if new_ids:
        logger.info(
            "audio_tag_acl_cache miss_new ids=%s total=%d known_missing=%d "
            "authoritative=%s",
            new_ids[:5], len(missing), known, authoritative,
        )
    else:
        logger.debug(
            "audio_tag_acl_cache miss count=%d known_missing=%d authoritative=%s",
            len(missing), known, authoritative,
        )


def resolve_tag_id_to_name_map(tag_ids: List[int], loader) -> Dict[int, str]:
    """按 tag_id 解析标签名：进程内快照 + TTL + 单飞刷新。"""
    wanted: List[int] = [
        tid for tid in dict.fromkeys(
            _normalize_tag_id(raw) for raw in (tag_ids or []))
        if tid is not None
    ]
    if not wanted:
        return {}

    snapshot, authoritative = _get_snapshot(loader)

    resolved: Dict[int, str] = {}
    missing: List[int] = []
    for tid in wanted:
        name = snapshot.get(tid)
        if name is None:
            missing.append(tid)
        else:
            resolved[tid] = name

    if missing:
        _record_miss(missing, authoritative)
    if resolved:
        with _COND:
            _STATS['hit'] += len(resolved)
    return resolved


class _TagProxy:
    """标签轻量代理对象（供 add_audio_tag 使用 tag.id / tag.name）"""

    def __init__(self, id, name):
        self.id = id
        self.name = name


class TagAclRepository:
    """task_service.TagConfigService 防腐层仓储

    封装 gRPC 调用，提供 audio_service persistence 层可用的返回值。
    所有方法返回纯 dict / list，不返回 ORM 对象。
    """

    def _list_tags_page(self, page: int = 1, per_page: int = 500, keyword: str = ''):
        """查询单页标签列表，返回 (items, total_pages) 或 ([], 0)。"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_tag_config_service_stub()
            resp = stub.ListTags(task_pb.ListTagsRequest(
                page=page, per_page=per_page, keyword=keyword,
            ))
            if not resp.success:
                return [], 0
            data = _loads(resp.data, {})
            if not isinstance(data, dict):
                return [], 0
            items = data.get('items', []) or []
            return items, data.get('pages', 1)
        except Exception:
            return [], 0

    def _list_tags_page_strict(self, page: int = 1, per_page: int = 500,
                               keyword: str = '', timeout: Optional[float] = None):
        """查询单页标签列表；失败向上抛，供写路径区分「查无」与「查不了」.

        INT-2047：``timeout`` 显式传 gRPC deadline（秒）。不传时沿用共享
        channel 的默认 deadline，写路径（``_find_tag_by_name``）保持原语义。
        """
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb

        stub = get_tag_config_service_stub()
        call_kwargs = {'timeout': timeout} if timeout and timeout > 0 else {}
        resp = stub.ListTags(task_pb.ListTagsRequest(
            page=page, per_page=per_page, keyword=keyword,
        ), **call_kwargs)
        if not resp.success:
            raise RuntimeError(f'ListTags 失败: {resp.message or "未知原因"}')
        data = _loads(resp.data, {})
        if not isinstance(data, dict):
            raise RuntimeError(f'ListTags 响应不是对象: {str(resp.data)[:200]}')
        return data.get('items', []) or [], data.get('pages', 1)

    def get_tag_name_to_id_map(self, tag_names: List[str]) -> Dict[str, int]:
        """通过 gRPC 查询标签名 → ID 映射（Tag 属于 task_service 域）"""
        if not tag_names:
            return {}
        result = {}
        try:
            target_names = set(tag_names)
            page = 1
            per_page = 500
            while target_names:
                items, total_pages = self._list_tags_page(page, per_page)
                if not items:
                    break
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid and name in target_names:
                        result[name] = tid
                        target_names.discard(name)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            logger.debug("通过 gRPC 查询标签名→ID映射失败: tag_names=%s", tag_names, exc_info=True)
        return result

    def get_all_tag_name_to_id_map(self) -> Dict[str, int]:
        """通过 gRPC 查询所有标签名 → ID 映射"""
        result = {}
        try:
            page = 1
            per_page = 500
            while True:
                items, total_pages = self._list_tags_page(page, per_page)
                if not items:
                    break
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid:
                        result[name] = tid
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            logger.debug("通过 gRPC 查询所有标签名→ID映射失败", exc_info=True)
        return result

    def get_all_tag_names(self) -> List[str]:
        """查询所有不重复的标签名"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_tag_config_service_stub()
            resp = stub.ListTagNames(task_pb.ListTagNamesRequest(
                page=1, per_page=500,
            ))
            if not resp.success:
                return []
            data = _loads(resp.data, {})
            if isinstance(data, dict):
                return data.get('items', []) or []
            return []
        except Exception:
            return []

    def _find_tag_by_name(self, tag_name: str) -> Optional[_TagProxy]:
        """按名称精确查标签；传输/协议异常向上抛（与「查无此标签」区分）。

        INT-1533：写路径必须能分辨「标签不存在，该创建」和「标签服务连不上」，
        后者绝不能被当成「没有该标签」继续走创建，更不能最终降级成 NULL。
        """
        page = 1
        per_page = 500
        while True:
            items, total_pages = self._list_tags_page_strict(page, per_page, keyword=tag_name)
            for item in items:
                if item.get('name') == tag_name:
                    return _TagProxy(id=item.get('id'), name=item.get('name'))
            if not items or page >= total_pages:
                return None
            page += 1

    def get_or_create_tag(self, tag_name: str):
        """查找或创建标签，返回含 id 和 name 的对象（供 add_audio_tag 使用 tag.id）。

        INT-1533：解析失败一律抛 TagResolutionError，不再返回 id=None 的代理
        ——否则调用方会写出 audio_tags.tag_id 为 NULL 的关联行却回「成功」。
        """
        try:
            found = self._find_tag_by_name(tag_name)
        except Exception as e:
            logger.warning("查询标签失败（继续尝试创建）: tag_name=%s err=%s", tag_name, e)
            found = None
        if found is not None:
            return found

        create_error = ''
        try:
            from shared.clients.grpc_clients import get_tag_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            stub = get_tag_config_service_stub()
            create_resp = stub.CreateTag(task_pb.CreateTagRequest(
                data=_dumps({'name': tag_name}),
            ))
            if create_resp.success:
                data = _loads(create_resp.data, {})
                if isinstance(data, dict) and data.get('id'):
                    # 新标签必须让 id→name 快照立刻失效（INT-2000）：否则该
                    # 标签在一个 TTL 内没有名字，列表里会显示数字 id。
                    invalidate_tag_snapshot(reason='create_tag')
                    return _TagProxy(id=data.get('id'), name=data.get('name', tag_name))
                create_error = f'创建成功但响应缺少 id: {str(create_resp.data)[:200]}'
            else:
                create_error = create_resp.message or '创建标签失败'
        except Exception as e:
            create_error = f'{type(e).__name__}: {e}'

        # 并发下同名标签可能已被其它请求创建（CreateTag 撞唯一约束），复查一次
        try:
            found = self._find_tag_by_name(tag_name)
            if found is not None:
                return found
        except Exception as e:
            create_error = f'{create_error}；复查失败: {type(e).__name__}: {e}'

        logger.warning("标签解析失败: tag_name=%s err=%s", tag_name, create_error)
        raise TagResolutionError(tag_name, create_error)

    def _load_tag_id_to_name_snapshot_strict(self) -> Dict[int, str]:
        """拉取全量标签表并构造成 tag_id → name 快照。

        与 ``_list_tags_page`` 不同，这里失败一律向上抛：「查不了」必须能被
        缓存层识别，绝不能被当成「一个标签都没有」写进快照。

        INT-2047：每页显式带 deadline（默认 2 s，配置
        ``AUDIO_TAG_ACL_REFRESH_TIMEOUT_SECONDS``）；不传会落到共享 channel
        的默认 deadline（60 s），上游假死时刷新线程能挂几十秒。
        """
        snapshot: Dict[int, str] = {}
        page = 1
        per_page = 500
        timeout = tag_cache_refresh_timeout_seconds()
        while True:
            items, total_pages = self._list_tags_page_strict(
                page, per_page, timeout=timeout)
            for item in items or []:
                tid = _normalize_tag_id(item.get('id'))
                name = item.get('name')
                if tid is not None and name:
                    snapshot[tid] = name
            try:
                pages = int(total_pages or 1)
            except (TypeError, ValueError):
                pages = 1
            if not items or page >= pages:
                break
            page += 1
        return snapshot

    def get_tag_id_to_name_map(self, tag_ids: List[int]) -> Dict[int, str]:
        """通过进程内快照解析标签 ID → 名（Tag 属于 task_service 域，INT-2000）。

        返回的是「解析到的」映射：查不到 / 查不了的 id 不在结果里，调用方
        照旧回落 ``str(tag_id)`` —— 对外响应语义与旧实现完全一致。
        """
        if not tag_ids:
            return {}
        return resolve_tag_id_to_name_map(
            tag_ids, self._load_tag_id_to_name_snapshot_strict)

    def get_tag_config_stub(self):
        """获取 TagConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_tag_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_tag_config_service_stub
        return get_tag_config_service_stub()


# 模块级单例
tag_acl_repository = TagAclRepository()
