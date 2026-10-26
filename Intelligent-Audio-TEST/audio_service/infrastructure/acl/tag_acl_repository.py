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


# ========== 进程内标签快照缓存（INT-2000）==========
# 列表/详情解析 tag_id → name 原先每请求都要向 task_service 拉一次全量标签表
# （docker 主库 99 个标签 ≈25.8KB，INT-1992 分段实测 21.2ms/请求 = ListAudios
# 单请求的 33.7%），而解析的只是本页 ≤20 条音频的 tag_id。标签表变更极少，
# 因此把「全量 tag_id → name 快照」放在进程内：TTL 内零跨服务调用，到期才
# 刷新一次；过期瞬间的并发请求单飞（只一个线程打上游，其余等它回填后命中）。
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

_SNAPSHOT: Dict[int, str] = {}          # 只整体替换，不原地改（读侧拿引用即用）
_SNAPSHOT_AT: Optional[float] = None    # 最近一次成功加载的 monotonic 时刻
_NEGATIVE: Dict[int, float] = {}        # 查不到 的 tag_id → 负缓存过期时刻
_MISS_LOGGED = set()                    # 本快照代已 INFO 记过的查不到 id（防刷屏）
_ATTEMPT_SEQ = 0                        # 每次刷新尝试（成功或失败）+1
_REFRESHING = False                     # 是否有线程正在打上游
_COND = threading.Condition(threading.Lock())
_STATS = {
    'hit': 0,             # 命中快照的 id 数
    'miss': 0,            # 快照里没有的 id 数
    'negative_hit': 0,    # 命中负缓存（已知查不到）的 id 数
    'refresh_ok': 0,      # 上游刷新成功次数
    'refresh_fail': 0,    # 上游刷新失败次数
    'degraded': 0,        # 因上游失败而降级服务旧快照的次数
}
# 等上游刷新的上限（秒）。只防上游假死把请求无限挂住；正常刷新是毫秒级。
_REFRESH_WAIT_SECONDS = 5.0


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


def get_tag_acl_cache_stats() -> Dict[str, int]:
    """缓存计数快照（供 INT-1471 复测轮归因与单测断言）。"""
    with _COND:
        return dict(_STATS)


def reset_tag_acl_cache() -> None:
    """清空快照/负缓存/计数（测试与本地排障用）。"""
    global _SNAPSHOT, _SNAPSHOT_AT, _ATTEMPT_SEQ, _REFRESHING
    with _COND:
        _SNAPSHOT = {}
        _SNAPSHOT_AT = None
        _NEGATIVE.clear()
        _MISS_LOGGED.clear()
        _ATTEMPT_SEQ = 0
        _REFRESHING = False
        for key in _STATS:
            _STATS[key] = 0
        _COND.notify_all()


def invalidate_tag_snapshot(reason: str = '') -> None:
    """丢弃当前快照（写路径新建标签后调用，避免新标签在 TTL 内显示数字 id）。"""
    global _SNAPSHOT_AT
    with _COND:
        _SNAPSHOT_AT = None
        _NEGATIVE.clear()
        _MISS_LOGGED.clear()
    if reason:
        logger.info("audio_tag_acl_cache invalidated reason=%s", reason)


def _get_snapshot(loader) -> tuple:
    """取当前快照；TTL 过期时单飞刷新。

    返回 ``(snapshot, authoritative)``：authoritative=False 表示上游本次
    刷新失败、返回的是上一份（可能为空的）陈旧快照 —— 此时「查不到」不可
    信，不做负缓存。
    """
    global _SNAPSHOT, _SNAPSHOT_AT, _ATTEMPT_SEQ, _REFRESHING

    ttl = tag_cache_ttl_seconds()
    with _COND:
        now = time.monotonic()
        if _is_fresh(now, ttl):
            return _SNAPSHOT, True

        # 单飞：进入等待前记下尝试序号；被唤醒后若序号已变，说明本轮已有
        # 线程打过上游（成功→快照新鲜直接命中；失败→服务陈旧快照，不再重试）。
        attempt = _ATTEMPT_SEQ
        wait_deadline = time.monotonic() + _REFRESH_WAIT_SECONDS
        while True:
            now = time.monotonic()
            if _is_fresh(now, ttl):
                return _SNAPSHOT, True
            if _ATTEMPT_SEQ != attempt:
                return _SNAPSHOT, False
            if not _REFRESHING:
                _REFRESHING = True
                break
            remaining = wait_deadline - now
            if remaining <= 0:
                # 上游迟迟不回：等待者不再跟着挂住，先用陈旧快照降级服务
                # （刷新线程回填后自然生效）。只记一条结构化告警。
                stale = _SNAPSHOT
                _STATS['degraded'] += 1
                logger.warning(
                    "audio_tag_acl_cache wait_timeout serve_stale_items=%d",
                    len(stale))
                return stale, False
            _COND.wait(timeout=min(_REFRESH_WAIT_SECONDS, remaining))

    started = time.monotonic()
    try:
        fresh_snapshot = loader()
    except Exception as exc:  # 上游异常/超时 = 「查不了」，绝不写缓存
        cost_ms = (time.monotonic() - started) * 1000.0
        with _COND:
            _ATTEMPT_SEQ += 1
            _REFRESHING = False
            _STATS['refresh_fail'] += 1
            _STATS['degraded'] += 1
            stale = _SNAPSHOT
            stale_items = len(stale)
            _COND.notify_all()
        logger.warning(
            "audio_tag_acl_cache refresh_fail cost_ms=%.1f err=%s:%s "
            "serve_stale_items=%d ttl_s=%d",
            cost_ms, type(exc).__name__, exc, stale_items, ttl,
        )
        return stale, False

    cost_ms = (time.monotonic() - started) * 1000.0
    with _COND:
        _SNAPSHOT = fresh_snapshot
        _SNAPSHOT_AT = time.monotonic()
        _ATTEMPT_SEQ += 1
        _REFRESHING = False
        _STATS['refresh_ok'] += 1
        _MISS_LOGGED.clear()   # 新快照代：查不到的 id 重新记一次 INFO
        snapshot = _SNAPSHOT
        _COND.notify_all()
    logger.info(
        "audio_tag_acl_cache refresh_ok items=%d cost_ms=%.1f ttl_s=%d",
        len(snapshot), cost_ms, ttl,
    )
    return snapshot, True


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

    def _list_tags_page_strict(self, page: int = 1, per_page: int = 500, keyword: str = ''):
        """查询单页标签列表；失败向上抛，供写路径区分「查无」与「查不了」."""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb

        stub = get_tag_config_service_stub()
        resp = stub.ListTags(task_pb.ListTagsRequest(
            page=page, per_page=per_page, keyword=keyword,
        ))
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
        """
        snapshot: Dict[int, str] = {}
        page = 1
        per_page = 500
        while True:
            items, total_pages = self._list_tags_page_strict(page, per_page)
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
