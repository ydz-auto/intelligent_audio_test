"""
统计缓存刷新工具

提供自动刷新统计缓存的功能，在数据变化时调用。

缓存存储：Redis（key=home_stats，value=JSON）。正常快照 TTL 1 小时；
含失败域的降级快照走短 TTL（_CACHE_TTL_DEGRADED）。
原 stats_cache 表已废弃，BFF 不再持有自有 DB 表。

降级策略（INT-204）：任一 _fetch_*_via_grpc 失败时严禁以 0 兜底后照常
缓存（否则故障窗口内一次首页访问会把全 0/部分 0 快照缓存 1 小时不自愈）：
- 全部域失败：不写缓存（既有快照原样保留或保持缺失），下一轮请求重试；
- 部分域失败：失败域沿用既有快照旧值（stale-while-error），以降级短 TTL
  写入，上游恢复后最迟一个短 TTL 周期自动回正。
- task 域（tasks/test_cases/groups）失败必须在 ACL proxy 层透传：
  _grpc_call 默认吞异常返回 {}，掉线会被误读为合法 0 值按正常 TTL 落缓存
  （INT-204 审计问题 1），故三个 proxy 调用固定/显式 reraise 上抛。
"""
# Task / TestCase 聚合统计已改用 gRPC（task_service.TaskDataService.GetTaskStats /
# GetTestCaseStats）。audio_service / device_service / api_test_service /
# evaluation_service 的聚合统计通过 list RPC per_page=1 取 total。
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import redis as redis_lib

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)

_CACHE_KEY = 'home_stats'
# 正常快照 TTL（秒）
_CACHE_TTL = int(os.environ.get('HOME_STATS_CACHE_TTL_SECONDS', '3600'))  # 1 小时
# 降级快照 TTL（秒）：含沿用旧值的失败域，短 TTL 保证上游恢复后快速重试回正
_CACHE_TTL_DEGRADED = int(os.environ.get('HOME_STATS_CACHE_DEGRADED_TTL_SECONDS', '30'))

# ---- 首页汇总（GET /home/stats/summary）缓存 ----
# 汇总 = 最近任务 + TOP 分组 + 设备状态，原实现每次请求实时串行回源
# （task 列表读模型 + 2 次用例分组 RPC + 设备全量分页拉取），并发 40 下
# avg 1.8s（INT-1464）。实时性要求远低于详情快照，故独立 key + 短 TTL，
# 与详情快照（home_stats，1h）分开失效。
_SUMMARY_CACHE_KEY = 'home_stats_summary'
# 正常 TTL（秒）：首页汇总允许秒级陈旧，取 30~60s 区间
_SUMMARY_CACHE_TTL = int(os.environ.get('HOME_STATS_SUMMARY_CACHE_TTL_SECONDS', '45'))
# 降级 TTL（秒）：有域回源失败时短缓存，避免故障窗口内每个请求都撞上游
_SUMMARY_CACHE_TTL_DEGRADED = int(
    os.environ.get('HOME_STATS_SUMMARY_CACHE_DEGRADED_TTL_SECONDS', '10'))
# 回源锁：缓存过期瞬间只放一个请求回源，其余等快照写出（防缓存击穿）
_SUMMARY_LOCK_KEY = 'home_stats_summary:lock'
_SUMMARY_LOCK_TTL_SECONDS = int(os.environ.get('HOME_STATS_SUMMARY_LOCK_TTL_SECONDS', '5'))
# 等锁者最长等待（秒）与轮询间隔（秒）；超时自行回源（持锁者异常也不致卡死）
_SUMMARY_LOCK_WAIT_SECONDS = float(os.environ.get('HOME_STATS_SUMMARY_LOCK_WAIT_SECONDS', '1.0'))
_SUMMARY_LOCK_POLL_SECONDS = float(
    os.environ.get('HOME_STATS_SUMMARY_LOCK_POLL_SECONDS', '0.02'))

# 模块级 Redis 客户端单例：复用连接，避免每次刷新新建导致连接/内存膨胀
_redis_client = None


class StatsFetchError(RuntimeError):
    """统计域拉取失败（gRPC 传输异常或服务返回 success=False）。

    各 _fetch_*_via_grpc 失败时抛出，由 refresh_stats_cache 统一按域降级；
    域内严禁自行以 0 兜底（INT-204：0 快照按正常 TTL 缓存后不自愈）。
    """


def _get_redis():
    """获取/复用模块级 Redis 客户端（惰性单例）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.from_url(BaseConfig.REDIS_URL)
    return _redis_client


def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))


def _fetch_task_stats_via_grpc():
    """通过 gRPC 拉取 Task 聚合统计（一次 group_by=status 拿到全部状态计数）

    返回 (total, completed, running, failed)。
    失败时抛出异常（proxy 层 get_task_stats 固定 reraise，传输异常与
    success=False 均上抛），由 refresh_stats_cache 统一走 stale-while-error 降级。
    """
    from api_gateway.infrastructure.grpc_proxies import task_data_service
    grouped = task_data_service.get_task_stats(group_by='status')
    if not isinstance(grouped, dict):
        raise StatsFetchError('get_task_stats 返回非 dict 载荷')
    items = grouped.get('items', [])
    by_status = {item.get('key', ''): item.get('count', 0) for item in items}
    total = sum(by_status.values())
    completed = by_status.get('completed', 0)
    running = by_status.get('running', 0)
    failed = by_status.get('failed', 0)
    return total, completed, running, failed


def _fetch_testcase_stats_via_grpc():
    """通过 gRPC 拉取 TestCase 聚合统计（total 计数）

    返回 total。失败时抛出异常（reraise=True 上抛，同 task 域口径）。
    """
    from api_gateway.infrastructure.grpc_proxies import task_data_service
    result = task_data_service.get_testcase_stats(reraise=True)
    if not isinstance(result, dict):
        raise StatsFetchError('get_testcase_stats 返回非 dict 载荷')
    return int(result.get('total', 0))


def _fetch_testcase_group_count_via_grpc():
    """通过 gRPC 拉取 TestCaseGroup 总数（list_testcase_groups 返回 items 长度）

    返回 count。失败时抛出异常（reraise=True 上抛，同 task 域口径）。
    """
    from api_gateway.infrastructure.grpc_proxies import task_data_service
    result = task_data_service.list_testcase_groups(reraise=True)
    if not isinstance(result, dict):
        raise StatsFetchError('list_testcase_groups 返回非 dict 载荷')
    items = result.get('items', [])
    return len(items)


def _fetch_reports_count_via_grpc():
    """通过 gRPC 拉取 Report 总数（ListReports page=1 per_page=1 取 total）

    返回 count。失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import report_config_service
    from shared.proto import report_service_pb2 as report_pb
    from shared.utils.grpc_json import loads as _loads

    stub = report_config_service.stub
    resp = stub.ListReports(report_pb.ListReportsRequest(
        page=1, per_page=1))
    if not resp.success:
        raise StatsFetchError('ListReports 返回失败: %s' % resp.message)
    if not resp.data:
        return 0
    payload = _loads(resp.data, {}) or {}
    return int(payload.get('total', 0))


def _fetch_audio_stats_via_grpc():
    """通过 gRPC 拉取音频统计（ListAudios per_page=1 取 total + 按类型分别查）

    返回 (total, dry_count, noise_count, prompt_count, total_duration,
          dry_duration, noise_duration, prompt_duration)。
    失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import audio_config_service
    from shared.proto import audio_service_pb2 as e2e_pb
    from shared.utils.grpc_json import loads as _loads

    stub = audio_config_service.stub

    # 总数
    resp = stub.ListAudios(e2e_pb.ListAudiosRequest(
        data='{"page": 1, "per_page": 1}',
    ))
    if not resp.success:
        raise StatsFetchError('ListAudios 返回失败: %s' % resp.message)
    total = 0
    if resp.data:
        payload = _loads(resp.data, {}) or {}
        total = int(payload.get('total', 0))

    # 按类型查
    dry = noise = prompt = 0
    dry_dur = noise_dur = prompt_dur = 0.0
    for audio_type in ('dry', 'noise', 'prompt'):
        r = stub.ListAudios(e2e_pb.ListAudiosRequest(
            data=f'{{"page": 1, "per_page": 1, "audio_type": "{audio_type}"}}',
        ))
        if not r.success:
            raise StatsFetchError('ListAudios(%s) 返回失败: %s' % (audio_type, r.message))
        if not r.data:
            continue
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


def _fetch_device_stats_via_grpc():
    """通过 gRPC 拉取设备统计（ListDevices 按 status 分别查）

    返回 (online, offline)。失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import device_config_service
    from shared.proto import device_service_pb2 as e2e_pb
    from shared.utils.grpc_json import loads as _loads

    stub = device_config_service.stub

    online = offline = 0
    for status in ('online', 'offline'):
        resp = stub.ListDevices(e2e_pb.ListDevicesRequest(
            page=1, per_page=1, status=status,
        ))
        if not resp.success:
            raise StatsFetchError('ListDevices(%s) 返回失败: %s' % (status, resp.message))
        if not resp.data:
            continue
        payload = _loads(resp.data, {}) or {}
        cnt = int(payload.get('total', 0))
        if status == 'online':
            online = cnt
        else:
            offline = cnt

    return online, offline


# 首页汇总（/home/stats/summary）设备状态复用同一计数口径：ListDevices
# per_page=1 按 status 取 total，两次 RPC 拿齐在线/离线数，禁止按
# EXPORT_PAGE_SIZE 全量分页拉取设备（INT-1464）。
fetch_device_status_counts = _fetch_device_stats_via_grpc


def _fetch_playback_device_stats_via_grpc():
    """通过 gRPC 拉取播放设备总数（ListPlaybackDevices per_page=1 取 total）

    返回 count。失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import playback_config_service
    from shared.proto import device_service_pb2 as e2e_pb
    from shared.utils.grpc_json import loads as _loads

    stub = playback_config_service.stub
    resp = stub.ListPlaybackDevices(e2e_pb.ListPlaybackDevicesRequest(
        page=1, per_page=1,
    ))
    if not resp.success:
        raise StatsFetchError('ListPlaybackDevices 返回失败: %s' % resp.message)
    if not resp.data:
        return 0
    payload = _loads(resp.data, {}) or {}
    return int(payload.get('total', 0))


def _fetch_api_stats_via_grpc():
    """通过 gRPC 拉取 API 统计（api_test_service.APITestService.ListAPIs per_page=1 取 total）

    返回 (online, offline)。失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import api_config_service
    from shared.proto import api_test_service_pb2 as api_test_pb
    from shared.utils.grpc_json import loads as _loads

    stub = api_config_service.stub
    online = offline = 0
    for status in ('online', 'offline'):
        resp = stub.ListAPIConfigs(api_test_pb.ListAPIConfigsRequest(
            page=1, per_page=1, status=status,
        ))
        if not resp.success:
            raise StatsFetchError('ListAPIConfigs(%s) 返回失败: %s' % (status, resp.message))
        if not resp.data:
            continue
        payload = _loads(resp.data, {}) or {}
        cnt = int(payload.get('total', 0))
        if status == 'online':
            online = cnt
        else:
            offline = cnt
    return online, offline


def _fetch_dimension_stats_via_grpc():
    """通过 gRPC 拉取评估维度统计（evaluation_service.EvaluationConfigService.ListDimensions per_page=1 取 total）

    返回 (total, with_endpoints, endpoints_total)。失败时抛出异常。
    """
    from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
    from shared.proto import evaluation_service_pb2 as eval_pb
    from shared.utils.grpc_json import loads as _loads

    stub = evaluation_config_service.stub
    resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
        page=1, per_page=1,
    ))
    if not resp.success:
        raise StatsFetchError('ListDimensions 返回失败: %s' % resp.message)
    total = 0
    if resp.data:
        payload = _loads(resp.data, {}) or {}
        total = int(payload.get('total', 0))
    # with_endpoints 和 endpoints_total 需要遍历所有维度检查 api_endpoints 字段
    # 暂用 0，待 evaluation_service 补充专用 stats 聚合 RPC 后完善
    return total, 0, 0


def _load_cached_stats():
    """读取既有统计快照（供失败域沿用旧值）；无缓存/损坏时返回 None"""
    try:
        raw = _get_redis().get(_CACHE_KEY)
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        logger.warning("读取既有统计缓存失败，降级时无旧值可沿用", exc_info=True)
        return None


def _stale_value(old_stats, *path):
    """按路径从既有快照提取旧值（stale-while-error），缺失/损坏时返回 0"""
    node = old_stats
    for key in path:
        if not isinstance(node, dict):
            return 0
        node = node.get(key)
    return node if isinstance(node, (int, float)) else 0


def _stale_audio_stats(old_stats):
    """从既有快照提取音频域旧值 8 元组（stale-while-error）"""
    return (
        _stale_value(old_stats, 'audio_files', 'total'),
        _stale_value(old_stats, 'audio_files', 'dry'),
        _stale_value(old_stats, 'audio_files', 'noise'),
        _stale_value(old_stats, 'audio_files', 'prompt'),
        _stale_value(old_stats, 'audio_files', 'duration', 'total'),
        _stale_value(old_stats, 'audio_files', 'duration', 'dry'),
        _stale_value(old_stats, 'audio_files', 'duration', 'noise'),
        _stale_value(old_stats, 'audio_files', 'duration', 'prompt'),
    )


def load_summary_cache():
    """读取首页汇总快照；无缓存 / 载荷损坏 / Redis 不可用时返回 None（按未命中处理）"""
    try:
        raw = _get_redis().get(_SUMMARY_CACHE_KEY)
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        logger.warning("读取首页汇总缓存失败，按未命中处理", exc_info=True)
        return None


def store_summary_cache(value, degraded=False):
    """写入首页汇总快照；degraded=True 时按降级短 TTL 写入

    返回 True 表示已写入。Redis 不可用时返回 False（不影响本次响应）。
    """
    ttl = _SUMMARY_CACHE_TTL_DEGRADED if degraded else _SUMMARY_CACHE_TTL
    try:
        _get_redis().setex(
            _SUMMARY_CACHE_KEY, ttl,
            json.dumps(value, ensure_ascii=False, default=str))
        return True
    except Exception:
        logger.warning("写入首页汇总缓存失败", exc_info=True)
        return False


def invalidate_summary_cache():
    """数据变化后失效首页汇总快照，下一次请求重算（调用方不感知失败）"""
    try:
        _get_redis().delete(_SUMMARY_CACHE_KEY)
    except Exception:
        logger.warning("失效首页汇总缓存失败", exc_info=True)


def acquire_summary_refresh_lock():
    """抢占汇总回源锁（防缓存过期瞬间并发请求同时回源）

    返回 True=本请求取得回源权；False=他人持有，应等待其写出快照；
    None=Redis 不可用（无锁可依，调用方直接回源）。
    """
    try:
        return bool(_get_redis().set(
            _SUMMARY_LOCK_KEY, '1', nx=True, ex=_SUMMARY_LOCK_TTL_SECONDS))
    except Exception:
        logger.warning("首页汇总回源锁不可用，直接回源", exc_info=True)
        return None


def release_summary_refresh_lock():
    """释放汇总回源锁（未持锁 / Redis 不可用时静默）"""
    try:
        _get_redis().delete(_SUMMARY_LOCK_KEY)
    except Exception:
        logger.warning("释放首页汇总回源锁失败", exc_info=True)


def wait_summary_cache(timeout=None):
    """等锁者轮询等待持锁者写出快照；超时返回 None（调用方自行回源）"""
    deadline = time.monotonic() + (
        _SUMMARY_LOCK_WAIT_SECONDS if timeout is None else timeout)
    while time.monotonic() < deadline:
        time.sleep(_SUMMARY_LOCK_POLL_SECONDS)
        value = load_summary_cache()
        if value is not None:
            return value
    return None


def refresh_stats_cache():
    """刷新统计缓存

    在数据增删改后调用此函数更新缓存。

    降级规则（INT-204）：
    - 任一域拉取失败：该域沿用既有快照旧值（stale-while-error），不以 0 兜底；
    - 全部域失败：不写缓存（既有快照原样保留或保持缺失），返回 False，
      下一轮请求重试；
    - 部分域失败：以降级短 TTL 写入混合快照，上游恢复后下一轮请求自动回正。

    返回 True 表示本轮已写入快照（全新或降级），False 表示未写缓存。
    """
    try:
        old_stats = _load_cached_stats()
        attempted = []
        failures = []

        def _fetch_or_stale(domain, fetch_fn, stale_fn):
            attempted.append(domain)
            try:
                return fetch_fn()
            except Exception as e:
                failures.append(domain)
                logger.warning("首页统计域 %s 拉取失败，沿用旧快照值: %s", domain, e)
                return stale_fn(old_stats)

        # ---- task_service（已改 gRPC 聚合统计）----
        test_cases_count = _fetch_or_stale(
            'test_cases', _fetch_testcase_stats_via_grpc,
            lambda old: _stale_value(old, 'test_cases', 'total'))
        test_case_groups_count = _fetch_or_stale(
            'test_case_groups', _fetch_testcase_group_count_via_grpc,
            lambda old: _stale_value(old, 'test_cases', 'groups'))
        tasks_count, tasks_completed, tasks_running, tasks_failed = _fetch_or_stale(
            'tasks', _fetch_task_stats_via_grpc,
            lambda old: tuple(
                _stale_value(old, 'tasks', key)
                for key in ('total', 'completed', 'running', 'failed')))

        # ---- audio_service（gRPC：ListAudios per_page=1 取 total）----
        audio_files_count, audio_dry_count, audio_noise_count, audio_prompt_count, \
            audio_total_duration, audio_dry_duration, audio_noise_duration, audio_prompt_duration \
            = _fetch_or_stale('audio_files', _fetch_audio_stats_via_grpc, _stale_audio_stats)

        # ---- device_service（gRPC：ListDevices per_page=1 按 status 取 total）----
        devices_online, devices_offline = _fetch_or_stale(
            'devices', _fetch_device_stats_via_grpc,
            lambda old: (_stale_value(old, 'devices', 'online'),
                         _stale_value(old, 'devices', 'offline')))

        # ---- device_service（gRPC：ListPlaybackDevices per_page=1 取 total）----
        playback_devices_count = _fetch_or_stale(
            'playback_devices', _fetch_playback_device_stats_via_grpc,
            lambda old: _stale_value(old, 'playback_devices'))

        # ---- api_test_service（gRPC：ListAPIs per_page=1 按 status 取 total）----
        apis_online, apis_offline = _fetch_or_stale(
            'apis', _fetch_api_stats_via_grpc,
            lambda old: (_stale_value(old, 'apis', 'online'),
                         _stale_value(old, 'apis', 'offline')))

        # ---- evaluation_service（gRPC：ListDimensions per_page=1 取 total）----
        dimensions_count, dimensions_with_endpoints, dimensions_endpoints_total = _fetch_or_stale(
            'dimensions', _fetch_dimension_stats_via_grpc,
            lambda old: (_stale_value(old, 'dimensions', 'total'),
                         _stale_value(old, 'dimensions', 'with_endpoints'),
                         _stale_value(old, 'dimensions', 'endpoints')))

        # ---- report_service（已改 gRPC：ListReports page=1 per_page=1 取 total）----
        reports_count = _fetch_or_stale(
            'reports', _fetch_reports_count_via_grpc,
            lambda old: _stale_value(old, 'reports'))

        if len(failures) == len(attempted):
            # 全部域失败：不写缓存，既有快照按自身剩余 TTL 自然服务/过期
            logger.error("首页统计全部域 gRPC 拉取失败（%s），本轮不写缓存", ', '.join(failures))
            return False

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

        ttl = _CACHE_TTL_DEGRADED if failures else _CACHE_TTL
        if failures:
            logger.warning(
                "首页统计部分域拉取失败（%s），按降级 TTL=%ss 写入混合快照",
                ', '.join(failures), ttl)

        r = _get_redis()
        r.setex(_CACHE_KEY, ttl, json.dumps(cache_value, ensure_ascii=False, default=str))
        # 数据变化触发的刷新同时失效首页汇总快照，避免汇总比详情晚一个
        # 短 TTL（INT-1464）；下次 summary 请求重算即可。
        invalidate_summary_cache()
        return True

    except Exception as e:
        logger.error("刷新统计缓存失败: %s", e, exc_info=True)
        return False
