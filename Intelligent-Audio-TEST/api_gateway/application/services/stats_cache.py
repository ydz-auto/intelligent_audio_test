"""
统计缓存刷新工具

提供自动刷新统计缓存的功能，在数据变化时调用。

缓存存储：Redis（key=home_stats，value=JSON，TTL=1h）。
原 stats_cache 表已废弃，BFF 不再持有自有 DB 表。
"""
# Task / TestCase 聚合统计已改用 gRPC（task_service.TaskDataService.GetTaskStats /
# GetTestCaseStats）。audio_service / device_service / api_test_service /
# evaluation_service 的聚合统计通过 list RPC per_page=1 取 total。
import json
import logging
from datetime import datetime, timezone, timedelta

import redis as redis_lib

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)

_CACHE_KEY = 'home_stats'
_CACHE_TTL = 3600  # 1 小时


def _get_redis():
    """获取 Redis 客户端"""
    return redis_lib.from_url(BaseConfig.REDIS_URL)


def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))


def _fetch_task_stats_via_grpc():
    """通过 gRPC 拉取 Task 聚合统计（一次 group_by=status 拿到全部状态计数）

    返回 (total, completed, running, failed)。
    gRPC 不可用时回退到 0 并打印告警，避免阻塞缓存刷新。
    """
    import logging
    from shared.clients.grpc_clients import get_task_stats
    _log = logging.getLogger(__name__)
    try:
        grouped = get_task_stats(group_by='status')
        items = grouped.get('items', []) if isinstance(grouped, dict) else []
        by_status = {item.get('key', ''): item.get('count', 0) for item in items}
        total = sum(by_status.values())
        completed = by_status.get('completed', 0)
        running = by_status.get('running', 0)
        failed = by_status.get('failed', 0)
        return total, completed, running, failed
    except Exception as e:
        _log.warning("get_task_stats gRPC 失败，任务统计置 0: %s", e)
        return 0, 0, 0, 0


def _fetch_testcase_stats_via_grpc():
    """通过 gRPC 拉取 TestCase 聚合统计（total 计数）

    返回 total。
    gRPC 不可用时回退到 0 并打印告警。
    """
    import logging
    from shared.clients.grpc_clients import get_testcase_stats
    _log = logging.getLogger(__name__)
    try:
        result = get_testcase_stats()
        return int(result.get('total', 0)) if isinstance(result, dict) else 0
    except Exception as e:
        _log.warning("get_testcase_stats gRPC 失败，用例统计置 0: %s", e)
        return 0


def _fetch_testcase_group_count_via_grpc():
    """通过 gRPC 拉取 TestCaseGroup 总数（list_testcase_groups 返回 items 长度）

    返回 count。
    gRPC 不可用时回退到 0。
    """
    import logging
    from shared.clients.grpc_clients import list_testcase_groups
    _log = logging.getLogger(__name__)
    try:
        result = list_testcase_groups()
        items = result.get('items', []) if isinstance(result, dict) else []
        return len(items)
    except Exception as e:
        _log.warning("list_testcase_groups gRPC 失败，用例分组统计置 0: %s", e)
        return 0


def _fetch_reports_count_via_grpc():
    """通过 gRPC 拉取 Report 总数（ListReports page=1 per_page=1 取 total）

    返回 count。
    gRPC 不可用时回退到 0 并打印告警。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_report_config_service_stub()
        resp = stub.ListReports(report_pb.ListReportsRequest(
            page=1, per_page=1))
        if not resp.success:
            _log.warning("ListReports gRPC 返回失败: %s", resp.message)
            return 0
        payload = _loads(resp.data, {}) or {}
        return int(payload.get('total', 0))
    except Exception as e:
        _log.warning("ListReports gRPC 失败，报告统计置 0: %s", e)
        return 0


def _fetch_audio_stats_via_grpc():
    """通过 gRPC 拉取音频统计（ListAudios per_page=1 取 total + 按类型分别查）

    返回 (total, dry_count, noise_count, prompt_count, total_duration,
          dry_duration, noise_duration, prompt_duration)。
    gRPC 不可用时回退到 0。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_audio_config_service_stub()

        # 总数
        resp = stub.ListAudios(e2e_pb.ListAudiosRequest(
            data='{"page": 1, "per_page": 1}',
        ))
        total = 0
        if resp.success and resp.data:
            payload = _loads(resp.data, {}) or {}
            total = int(payload.get('total', 0))

        # 按类型查
        dry = noise = prompt = 0
        dry_dur = noise_dur = prompt_dur = 0.0
        for audio_type, cnt_attr, dur_attr in [
            ('dry', 'dry', 'dry_dur'),
            ('noise', 'noise', 'noise_dur'),
            ('prompt', 'prompt', 'prompt_dur'),
        ]:
            r = stub.ListAudios(e2e_pb.ListAudiosRequest(
                data=f'{{"page": 1, "per_page": 1, "audio_type": "{audio_type}"}}',
            ))
            if r.success and r.data:
                p = _loads(r.data, {}) or {}
                cnt = int(p.get('total', 0))
                # duration 需要从 items 中提取（无专用聚合 RPC，取分页首条估算不可行）
                # 暂用 0 作为 duration，待 audio_service 补充 stats 聚合 RPC 后完善
                if audio_type == 'dry':
                    dry = cnt
                elif audio_type == 'noise':
                    noise = cnt
                elif audio_type == 'prompt':
                    prompt = cnt

        total_dur = 0.0  # 待 audio_service 补充聚合 RPC

        return total, dry, noise, prompt, total_dur, dry_dur, noise_dur, prompt_dur
    except Exception as e:
        _log.warning("ListAudios gRPC 失败，音频统计置 0: %s", e)
        return 0, 0, 0, 0, 0, 0, 0, 0


def _fetch_device_stats_via_grpc():
    """通过 gRPC 拉取设备统计（ListDevices 按 status 分别查）

    返回 (online, offline)。
    gRPC 不可用时回退到 0。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_device_config_service_stub
        from shared.proto import device_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_device_config_service_stub()

        online = offline = 0
        for status in ('online', 'offline'):
            resp = stub.ListDevices(e2e_pb.ListDevicesRequest(
                page=1, per_page=1, status=status,
            ))
            if resp.success and resp.data:
                payload = _loads(resp.data, {}) or {}
                cnt = int(payload.get('total', 0))
                if status == 'online':
                    online = cnt
                else:
                    offline = cnt

        return online, offline
    except Exception as e:
        _log.warning("ListDevices gRPC 失败，设备统计置 0: %s", e)
        return 0, 0


def _fetch_playback_device_stats_via_grpc():
    """通过 gRPC 拉取播放设备总数（ListPlaybackDevices per_page=1 取 total）

    返回 count。
    gRPC 不可用时回退到 0。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import device_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_playback_config_service_stub()
        resp = stub.ListPlaybackDevices(e2e_pb.ListPlaybackDevicesRequest(
            page=1, per_page=1,
        ))
        if resp.success and resp.data:
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0))
        return 0
    except Exception as e:
        _log.warning("ListPlaybackDevices gRPC 失败，播放设备统计置 0: %s", e)
        return 0


def _fetch_api_stats_via_grpc():
    """通过 gRPC 拉取 API 统计（api_test_service.APITestService.ListAPIs per_page=1 取 total）

    返回 (online, offline)。
    gRPC 不可用时回退到 0。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_api_test_config_service_stub
        from shared.proto import api_test_service_pb2 as api_test_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_api_test_config_service_stub()
        online = offline = 0
        for status in ('online', 'offline'):
            resp = stub.ListAPIs(api_test_pb.ListAPIsRequest(
                page=1, per_page=1, status=status,
            ))
            if resp.success and resp.data:
                payload = _loads(resp.data, {}) or {}
                cnt = int(payload.get('total', 0))
                if status == 'online':
                    online = cnt
                else:
                    offline = cnt
        return online, offline
    except Exception as e:
        _log.warning("ListAPIs gRPC 失败，API 统计置 0: %s", e)
        return 0, 0


def _fetch_dimension_stats_via_grpc():
    """通过 gRPC 拉取评估维度统计（evaluation_service.EvaluationConfigService.ListDimensions per_page=1 取 total）

    返回 (total, with_endpoints, endpoints_total)。
    gRPC 不可用时回退到 0。
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_evaluation_config_service_stub()
        resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
            page=1, per_page=1,
        ))
        total = 0
        if resp.success and resp.data:
            payload = _loads(resp.data, {}) or {}
            total = int(payload.get('total', 0))
        # with_endpoints 和 endpoints_total 需要遍历所有维度检查 api_endpoints 字段
        # 暂用 0，待 evaluation_service 补充专用 stats 聚合 RPC 后完善
        return total, 0, 0
    except Exception as e:
        _log.warning("ListDimensions gRPC 失败，维度统计置 0: %s", e)
        return 0, 0, 0


def refresh_stats_cache():
    """
    刷新统计缓存

    在数据增删改后调用此函数更新缓存
    """
    try:
        # ---- task_service（已改 gRPC 聚合统计）----
        test_cases_count = _fetch_testcase_stats_via_grpc()
        test_case_groups_count = _fetch_testcase_group_count_via_grpc()
        tasks_count, tasks_completed, tasks_running, tasks_failed = _fetch_task_stats_via_grpc()

        # ---- audio_service（gRPC：ListAudios per_page=1 取 total）----
        audio_files_count, audio_dry_count, audio_noise_count, audio_prompt_count, \
            audio_total_duration, audio_dry_duration, audio_noise_duration, audio_prompt_duration \
            = _fetch_audio_stats_via_grpc()

        # ---- device_service（gRPC：ListDevices per_page=1 按 status 取 total）----
        devices_online, devices_offline = _fetch_device_stats_via_grpc()

        # ---- device_service（gRPC：ListPlaybackDevices per_page=1 取 total）----
        playback_devices_count = _fetch_playback_device_stats_via_grpc()

        # ---- api_test_service（gRPC：ListAPIs per_page=1 按 status 取 total）----
        apis_online, apis_offline = _fetch_api_stats_via_grpc()

        # ---- evaluation_service（gRPC：ListDimensions per_page=1 取 total）----
        dimensions_count, dimensions_with_endpoints, dimensions_endpoints_total = _fetch_dimension_stats_via_grpc()

        # ---- report_service（已改 gRPC：ListReports page=1 per_page=1 取 total）----
        reports_count = _fetch_reports_count_via_grpc()

        cache_value = {
            'test_cases': {
                'total': test_cases_count,
                'groups': test_case_groups_count
            },
            'tasks': {
                'total': tasks_count,
                'completed': tasks_completed,
                'running': tasks_running,
                'failed': tasks_failed
            },
            'devices': {
                'online': devices_online,
                'offline': devices_offline,
                'total': devices_online + devices_offline
            },
            'audio_files': {
                'total': audio_files_count,
                'dry': audio_dry_count,
                'noise': audio_noise_count,
                'prompt': audio_prompt_count,
                'duration': {
                    'total': audio_total_duration,
                    'dry': audio_dry_duration,
                    'noise': audio_noise_duration,
                    'prompt': audio_prompt_duration
                }
            },
            'playback_devices': playback_devices_count,
            'apis': {
                'online': apis_online,
                'offline': apis_offline,
                'total': apis_online + apis_offline
            },
            'reports': reports_count,
            'dimensions': {
                'total': dimensions_count,
                'with_endpoints': dimensions_with_endpoints,
                'endpoints': dimensions_endpoints_total
            },
            'updated_at': utc8now().isoformat()
        }

        r = _get_redis()
        r.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(cache_value, ensure_ascii=False, default=str))
        return True

    except Exception as e:
        logger.error("刷新统计缓存失败: %s", e, exc_info=True)
        return False
