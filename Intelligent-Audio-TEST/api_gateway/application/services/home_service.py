"""首页统计服务"""
import json
import logging

import redis as redis_lib

from api_gateway.infrastructure.request_adapter import request

logger = logging.getLogger(__name__)
from api_gateway.infrastructure.acl import DeviceAclRepositoryImpl, TaskConfigAclRepositoryImpl
from api_gateway.schemas.home import HomeStatsDetails, HomeStatsRefreshRequest
from api_gateway.utils.response import success_response, error_response
from api_gateway.application.services.stats_cache import refresh_stats_cache, _CACHE_KEY
from shared.infrastructure.config import BaseConfig
from api_gateway.infrastructure.grpc_proxies import task_data_service

_task_acl = TaskConfigAclRepositoryImpl()
_device_acl = DeviceAclRepositoryImpl()


def _get_redis():
    """获取 Redis 客户端"""
    return redis_lib.from_url(BaseConfig.REDIS_URL)


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
            refresh_stats_cache()
            return success_response(message="统计缓存已刷新")
        except Exception as e:
            return error_response(message=f"刷新统计缓存失败: {str(e)}")

    @staticmethod
    def _fetch_top_groups_via_grpc(limit=5):
        """通过 gRPC 拉取 TestCaseGroup+TestCase 聚合统计（top N 分组）

        组合 list_testcase_groups（分组元数据）与 get_testcase_stats(group_by='group_id')
        （每分组的用例数），在客户端做 join + 排序 + 截断，替代直连 PO 的
        outerjoin + group_by + count + limit 聚合查询。

        返回 [{id, name, case_count}, ...]，按 case_count 降序取前 limit 条。
        gRPC 失败时返回空列表。
        """
        try:
            groups_resp = task_data_service.list_testcase_groups() or {}
            group_items = groups_resp.get('items', []) if isinstance(groups_resp, dict) else []
            group_map = {g.get('id'): g for g in group_items if g.get('id') is not None}

            stats_resp = task_data_service.get_testcase_stats(group_by='group_id') or {}
            stat_items = stats_resp.get('items', []) if isinstance(stats_resp, dict) else []
        except Exception:
            return []

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
        try:
            # 通过 gRPC 获取最近任务（替代直连 task_service PO）
            result = _task_acl.list_tasks(page=1, per_page=5)
            recent_tasks_data = []
            if result.get('success'):
                for task in (result.get('data') or {}).get('items', []):
                    recent_tasks_data.append(
                        {
                            'id': task.get('id'),
                            'name': task.get('name'),
                            'type': task.get('type'),
                            'status': task.get('status'),
                            'algorithm_type': task.get('algorithm_type'),
                            'total_cases': task.get('total_cases'),
                            'completed_cases': task.get('completed_cases'),
                            'created_at': task.get('created_at'),
                        }
                    )

            # 通过 gRPC 获取 TestCaseGroup+TestCase 聚合统计（替代直连 PO 的 join 聚合）
            top_groups_data = HomeService._fetch_top_groups_via_grpc(limit=5)

            from api_gateway.schemas.home import RecentTaskItem, TopGroupItem, DeviceStatus, HomeStatsSummary
            recent_task_items = []
            for task in recent_tasks_data:
                recent_task_items.append(
                    RecentTaskItem(
                        id=task['id'],
                        name=task['name'],
                        type=task['type'],
                        status=task['status'],
                        algorithm_type=task['algorithm_type'],
                        total_cases=task['total_cases'],
                        completed_cases=task['completed_cases'],
                        created_at=task['created_at'],
                    )
                )

            top_group_items = [
                TopGroupItem(
                    id=g.get('id'),
                    name=g.get('name', ''),
                    case_count=g.get('case_count', 0)
                )
                for g in top_groups_data
            ]

            # 通过 gRPC 获取设备状态（替代直连 device_service PO）
            online_count = 0
            offline_count = 0
            try:
                dev_result = _device_acl.get_all(page=1, per_page=10000)
                if dev_result.get('success'):
                    for dev in (dev_result.get('data') or {}).get('items', []):
                        if dev.get('status') == 'online':
                            online_count += 1
                        else:
                            offline_count += 1
            except Exception:
                logger.warning("获取设备状态统计失败", exc_info=True)

            device_status = DeviceStatus(
                online=online_count,
                offline=offline_count
            )

            summary = HomeStatsSummary(
                recentTasks=recent_task_items,
                topGroups=top_group_items,
                deviceStatus=device_status
            )

            return success_response(data=summary)

        except Exception as e:
            return error_response(message=f"获取汇总统计失败: {str(e)}")
