"""首页统计服务"""
import json
import logging

import redis as redis_lib

from api_gateway.infrastructure.request_adapter import request

logger = logging.getLogger(__name__)
from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
from api_gateway.schemas.home import (
    DeviceStatus,
    HomeStatsDetails,
    HomeStatsRefreshRequest,
    HomeStatsSummary,
    RecentTaskItem,
    TopGroupItem,
)
from api_gateway.utils.response import success_response, error_response
from api_gateway.application.services.stats_cache import (
    _CACHE_KEY,
    acquire_summary_refresh_lock,
    fetch_device_status_counts,
    load_summary_cache,
    refresh_stats_cache,
    release_summary_refresh_lock,
    store_summary_cache,
    wait_summary_cache,
)
from shared.infrastructure.config import BaseConfig
from api_gateway.application.services.system_option_service import SystemOptionService
from api_gateway.domain.entities.system_option import SYSTEM_OPTION_DEFAULTS
from api_gateway.infrastructure.grpc_proxies import task_data_service

_task_acl = TaskConfigAclRepositoryImpl()

# 首页汇总最近任务条数（与前端统计卡一屏展示口径一致）
SUMMARY_RECENT_TASK_LIMIT = 5
# 首页汇总 TOP 分组条数
SUMMARY_TOP_GROUP_LIMIT = 5

# 模块级 Redis 客户端单例：复用连接，避免每次请求新建导致连接/内存膨胀
_redis_client = None


def _get_redis():
    """获取/复用模块级 Redis 客户端（惰性单例）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.from_url(BaseConfig.REDIS_URL)
    return _redis_client


class HomeService:
    """首页统计服务"""

    @staticmethod
    def get_stats_details():
        try:
            r = _get_redis()
            raw = r.get(_CACHE_KEY)

            if raw:
                stats_data = HomeStatsDetails(**json.loads(raw))
                return success_response(data=stats_data)

            refresh_stats_cache()

            raw = r.get(_CACHE_KEY)
            if raw:
                stats_data = HomeStatsDetails(**json.loads(raw))
                return success_response(data=stats_data)

            return success_response(data=HomeStatsDetails())

        except Exception as e:
            return error_response(message=f"获取统计详情失败: {str(e)}")

    @staticmethod
    def refresh_stats():
        try:
            req = HomeStatsRefreshRequest.model_validate(request.get_json() or {})
            if not refresh_stats_cache():
                # 全部统计域不可用，本轮未写缓存（INT-204：不得谎报刷新成功）
                return error_response(message="统计缓存刷新失败：上游统计服务暂不可用，请稍后重试")
            return success_response(message="统计缓存已刷新")
        except Exception as e:
            return error_response(message=f"刷新统计缓存失败: {str(e)}")

    @staticmethod
    def _fetch_top_groups_via_grpc(limit=SUMMARY_TOP_GROUP_LIMIT):
        """通过 gRPC 拉取 TestCaseGroup+TestCase 聚合统计（top N 分组）

        组合 list_testcase_groups（分组元数据）与 get_testcase_stats(group_by='group_id')
        （每分组的用例数），在客户端做 join + 排序 + 截断，替代直连 PO 的
        outerjoin + group_by + count + limit 聚合查询。

        返回 [{id, name, case_count}, ...]，按 case_count 降序取前 limit 条；
        gRPC 失败时返回 None（由调用方按降级口径处理，不得当作「确实没有分组」）。
        """
        try:
            # 首页汇总要区分「上游失败」与「确实无分组」，故 reraise=True 上抛
            groups_resp = task_data_service.list_testcase_groups(reraise=True) or {}
            group_items = groups_resp.get('items', []) if isinstance(groups_resp, dict) else []
            group_map = {g.get('id'): g for g in group_items if g.get('id') is not None}

            stats_resp = task_data_service.get_testcase_stats(
                group_by='group_id', reraise=True) or {}
            stat_items = stats_resp.get('items', []) if isinstance(stats_resp, dict) else []
        except Exception:
            logger.warning("获取 TOP 分组统计失败", exc_info=True)
            return None

        merged = []
        for item in stat_items:
            key = item.get('key')
            count = int(item.get('count', 0) or 0)
            # 匹配分组元数据（key 为 group_id 字符串）
            group = group_map.get(key) or group_map.get(str(key))
            if group is None:
                continue
            try:
                gid = int(group.get('id'))
            except (TypeError, ValueError):
                gid = group.get('id')
            merged.append({
                'id': gid,
                'name': group.get('name') or '',
                'case_count': count,
            })

        merged.sort(key=lambda x: x.get('case_count', 0), reverse=True)
        return merged[:limit]

    @staticmethod
    def get_stats_summary():
        """首页统计汇总（INT-1464：Redis 短 TTL 缓存 + 设备状态走计数接口）

        未命中缓存时回源：最近任务（task_service 读模型）、TOP 分组（2 次
        gRPC 聚合）、设备在线/离线（2 次 per_page=1 计数 RPC）。回源结果按
        _SUMMARY_CACHE_TTL 写入 Redis，过期后单请求回源（锁防击穿），并发请求
        读缓存即可，不再每次串行回源 4 次 gRPC。
        """
        try:
            cached = HomeService._load_cached_summary()
            if cached is not None:
                return success_response(data=cached)
            return success_response(data=HomeService._refresh_stats_summary())
        except Exception as e:
            return error_response(message=f"获取汇总统计失败: {str(e)}")

    @staticmethod
    def _load_cached_summary():
        """读汇总缓存并还原为 Schema；无缓存或载荷不合法时返回 None"""
        payload = load_summary_cache()
        if payload is None:
            return None
        try:
            return HomeStatsSummary(**payload)
        except Exception:
            logger.warning("首页汇总缓存载荷不合法，按未命中处理", exc_info=True)
            return None

    @staticmethod
    def _refresh_stats_summary():
        """回源构建汇总并写缓存（持锁回源，等锁者复用快照）"""
        lock = acquire_summary_refresh_lock()
        if lock:
            try:
                # 双检：抢到锁期间快照可能已被上一持锁者写出
                cached = HomeService._load_cached_summary()
                if cached is not None:
                    return cached
                summary, degraded = HomeService._build_stats_summary()
                store_summary_cache(summary.model_dump(), degraded=degraded)
                return summary
            finally:
                release_summary_refresh_lock()

        if lock is False:
            # 他人回源中：等其写出快照，避免重复回源
            payload = wait_summary_cache()
            if payload is not None:
                try:
                    return HomeStatsSummary(**payload)
                except Exception:
                    logger.warning("首页汇总缓存载荷不合法，自行回源", exc_info=True)

        # 锁不可用（Redis 异常）或等待超时：自行回源，保证接口可用
        summary, degraded = HomeService._build_stats_summary()
        store_summary_cache(summary.model_dump(), degraded=degraded)
        return summary

    @staticmethod
    def _build_stats_summary():
        """实时聚合首页汇总；返回 (HomeStatsSummary, degraded)

        degraded=True 表示至少一个数据域回源失败（此时快照按降级短 TTL
        写入，不在故障窗口内长时间固化 0 值）。
        """
        degraded = False

        # 最近任务：task_service 列表读模型（已由外层缓存收敛为按 TTL 一次）
        result = _task_acl.list_tasks(page=1, per_page=SUMMARY_RECENT_TASK_LIMIT)
        recent_task_items = []
        if result.get('success'):
            for task in (result.get('data') or {}).get('items', []):
                recent_task_items.append(
                    RecentTaskItem(
                        id=task.get('id'),
                        name=task.get('name'),
                        device_types=task.get('device_types') or [],
                        status=task.get('status'),
                        algorithm_type=task.get('algorithm_type'),
                        total_cases=task.get('total_cases'),
                        completed_cases=task.get('completed_cases'),
                        created_at=task.get('created_at'),
                    )
                )
        else:
            degraded = True

        # TOP 分组：TestCaseGroup + TestCase 聚合（2 次 RPC）
        top_groups_data = HomeService._fetch_top_groups_via_grpc(
            limit=SUMMARY_TOP_GROUP_LIMIT)
        if top_groups_data is None:
            degraded = True
            top_groups_data = []

        top_group_items = [
            TopGroupItem(
                id=g.get('id'),
                name=g.get('name', ''),
                case_count=g.get('case_count', 0)
            )
            for g in top_groups_data
        ]

        # 设备状态：按 status 计数（2 次 per_page=1 RPC），不再全量分页拉取
        try:
            online_count, offline_count = fetch_device_status_counts()
        except Exception:
            logger.warning("获取设备状态统计失败", exc_info=True)
            degraded = True
            online_count = offline_count = 0

        summary = HomeStatsSummary(
            recent_tasks=recent_task_items,
            top_groups=top_group_items,
            device_status=DeviceStatus(
                online=online_count,
                offline=offline_count
            )
        )
        return summary, degraded

    @staticmethod
    def get_site_config():
        """站点配置读侧（公开端点 GET /api/v1/home/site 数据源，INT-674）。

        字段为公开展示数据：system_name / logo / support_email 取系统选项 KV
        （SystemOptionService.get_all() 全量 KV = 领域默认基线 ∪ 库内覆盖，
        显式空值覆盖默认），version 取平台版本常量（只读展示，不可配）。
        读侧，无副作用；数据源与 /api/option/ 同源（system_options KV），
        设置页改 KV → 壳品牌同源生效。
        """
        try:
            result, http = SystemOptionService.get_all()
            if http != 200:
                return error_response(message="读取站点配置失败")
            kv = result.get('data') or {}
            return success_response(data={
                'system_name': kv.get('site.name', SYSTEM_OPTION_DEFAULTS.get('site.name', '')),
                'version': BaseConfig.PLATFORM_VERSION,
                'logo': kv.get('site.logo', ''),
                'support_email': kv.get('site.support_email', ''),
            })
        except Exception as e:
            return error_response(message=f"读取站点配置失败: {str(e)}")
