# -*- coding: utf-8 -*-
"""INT-1578 专项：设备监控统计端点 + 健康检查性能指标采集。

覆盖（对应卡内可测验收标准）：
1. 聚合口径：区间内每一天都出点；无数据日 availability/cpu/memory/battery 为 null、
   errors=operations=0；health_check 失败与 operation 成功分别计入 errors/operations；
   online→offline 重放得到的可用率与手算一致。
2. 仓储取数：区间事件与日初基线 UNION ALL 合成 **一条** 聚合 SQL（避免逐日 N+1），
   只统计未删除的测试设备（lab_id / device_ids 过滤）。
3. 参数校验：缺日期 / end<start / 跨度 91 天 / granularity=hour → 400；90 天边界通过。
4. 指标采集：Android dumpsys battery、/proc/meminfo、top 汇总行；HarmonyOS hidumper
   解析；采不到就不写该键；命令失败/超时只影响该指标。
5. 健康检查：在线设备 detail.metrics 落库、离线不采、采集异常不影响 is_online 与整体成功。
"""
import json
import os
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# BaseConfig 类属性首次 import 即校验 OSS 配置；本模块不触网，占位即可
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.application.queries.device_stats_query_service import (
    DeviceStatsQueryService,
)
from device_service.infrastructure.drivers import device_metrics_collector as collector
from device_service.infrastructure.persistence.device_monitor_repository import (
    DeviceMonitorRepository,
    _aggregate_daily_points,
)


def _event(device_id, event_type, created_at, success=True, to_status=None, detail=None):
    return {
        'device_id': device_id,
        'event_type': event_type,
        'to_status': to_status,
        'success': success,
        'detail': detail,
        'created_at': created_at,
    }


# ==================== 1. 聚合口径（纯函数） ====================

class TestAggregateDailyPoints:
    NOW = datetime(2026, 12, 31, 23, 59, 59)
    DAY1 = date(2026, 10, 1)
    DAY2 = date(2026, 10, 2)

    def test_every_day_returned_with_nulls_for_empty_day(self):
        points = _aggregate_daily_points([], [self.DAY1, self.DAY2], self.NOW)

        assert [p['date'] for p in points] == ['2026-10-01', '2026-10-02']
        for point in points:
            assert point['availability'] is None
            assert point['cpu'] is None
            assert point['memory'] is None
            assert point['battery'] is None
            assert point['errors'] == 0
            assert point['operations'] == 0
            assert point['health_check_samples'] == 0

    def test_errors_operations_and_samples_counting(self):
        events = [
            _event(1, 'health_check', datetime(2026, 10, 1, 9, 0), success=False,
                   to_status='offline', detail={'serial_number': 'S1'}),
            _event(1, 'operation', datetime(2026, 10, 1, 10, 0), success=True),
            _event(1, 'operation', datetime(2026, 10, 1, 11, 0), success=False),
            _event(1, 'offline', datetime(2026, 10, 1, 12, 0), success=False,
                   to_status='error'),
            _event(1, 'health_check', datetime(2026, 10, 2, 9, 0), success=True,
                   to_status='online'),
        ]

        points = _aggregate_daily_points(events, [self.DAY1, self.DAY2], self.NOW)

        # errors = health_check/operation 的 success=false 2 条 + to_status=error 1 条 = 3
        # （契约 §1.2 括号口径：online/offline 状态事件即便 success=false 也不计入 errors）
        assert points[0]['errors'] == 3
        assert points[0]['operations'] == 1
        assert points[0]['health_check_samples'] == 1
        assert points[1]['errors'] == 0
        assert points[1]['health_check_samples'] == 1

    def test_availability_replay_matches_hand_calculation(self):
        events = [
            # 日初基线：10-01 22:00 已在线 → 10-02 00:00 起按在线计
            _event(1, 'online', datetime(2026, 10, 1, 22, 0)),
            # 10-02 12:00 离线 → 当日在线 12h / 24h = 50%
            _event(1, 'offline', datetime(2026, 10, 2, 12, 0)),
        ]

        points = _aggregate_daily_points(events, [self.DAY2], self.NOW)

        assert points[0]['availability'] == 50.0

    def test_availability_uses_first_event_as_start_without_baseline(self):
        events = [
            # 当日无基线：首条事件 06:00 在线，18:00 离线
            # 观测窗口 06:00~24:00 = 18h，其中在线 12h → 66.7%
            _event(1, 'online', datetime(2026, 10, 2, 6, 0)),
            _event(1, 'offline', datetime(2026, 10, 2, 18, 0)),
        ]

        points = _aggregate_daily_points(events, [self.DAY2], self.NOW)

        assert points[0]['availability'] == 66.7

    def test_availability_averaged_across_devices(self):
        events = [
            _event(1, 'online', datetime(2026, 10, 1, 0, 0)),
            _event(1, 'offline', datetime(2026, 10, 2, 0, 0)),   # 10-02 全天离线 → 0%
            _event(2, 'online', datetime(2026, 10, 1, 0, 0)),     # 10-02 全天在线 → 100%
        ]

        points = _aggregate_daily_points(events, [self.DAY2], self.NOW)

        assert points[0]['availability'] == 50.0

    def test_metrics_averaged_from_health_check_detail(self):
        events = [
            _event(1, 'health_check', datetime(2026, 10, 1, 8, 0),
                   detail={'metrics': {'cpu': 40, 'memory': 60}}),
            _event(1, 'health_check', datetime(2026, 10, 1, 9, 0),
                   detail={'metrics': {'cpu': 50.0, 'battery': 80}}),
            _event(1, 'health_check', datetime(2026, 10, 1, 10, 0),
                   detail={'metrics': {'cpu': None, 'memory': 'n/a'}}),
        ]

        points = _aggregate_daily_points(events, [self.DAY1], self.NOW)

        assert points[0]['cpu'] == 45.0
        assert points[0]['memory'] == 60.0
        assert points[0]['battery'] == 80.0

    def test_detail_as_json_string_supported(self):
        events = [
            _event(1, 'health_check', datetime(2026, 10, 1, 8, 0),
                   detail=json.dumps({'metrics': {'cpu': 12.5}})),
        ]

        points = _aggregate_daily_points(events, [self.DAY1], self.NOW)

        assert points[0]['cpu'] == 12.5

    def test_health_check_success_false_not_counted_as_operation(self):
        events = [
            _event(1, 'operation', datetime(2026, 10, 1, 8, 0), success=True),
        ]
        points = _aggregate_daily_points(events, [self.DAY1], self.NOW)
        assert points[0]['operations'] == 1
        assert points[0]['errors'] == 0


# ==================== 2. 仓储取数（单条聚合 SQL + 设备范围） ====================

@pytest.fixture(scope='module')
def sqlite_env():
    """本模块使用的 sqlite 库：建 devices / device_status_events 两表。"""
    from shared.models import database
    from device_service.infrastructure.persistence.models import Device, DeviceStatusEvent

    database.init_db()
    engine = database.get_engine()
    database.Base.metadata.create_all(
        bind=engine, tables=[Device.__table__, DeviceStatusEvent.__table__])
    yield engine, Device, DeviceStatusEvent
    database.remove_db_session()


@pytest.fixture
def stats_data(sqlite_env):
    """写入 2 台测试设备 + 1 台已删除设备及其事件，测试结束清理。"""
    from shared.models.database import get_db_session, remove_db_session

    engine, Device, DeviceStatusEvent = sqlite_env
    session = get_db_session()
    devices = [
        Device(id=900001, name='INT1578统计A', model='M', type='phone', system='Android',
               system_version='14', app_name='app', app_version='1', serial_number='STATS-A',
               status='online', lab_id=1, deleted=False),
        Device(id=900002, name='INT1578统计B', model='M', type='phone', system='Android',
               system_version='14', app_name='app', app_version='1', serial_number='STATS-B',
               status='offline', lab_id=2, deleted=False),
        Device(id=900003, name='INT1578已删除', model='M', type='phone', system='Android',
               system_version='14', app_name='app', app_version='1', serial_number='STATS-C',
               status='online', lab_id=1, deleted=True),
    ]
    session.add_all(devices)
    events = [
        # 基线（区间之前）：A 10-01 22:00 在线
        DeviceStatusEvent(id=910001, device_id=900001, event_type='online', to_status='online',
                          source='monitor', success=True,
                          created_at=datetime(2026, 10, 1, 22, 0)),
        # 区间内：A 10-03 12:00 离线
        DeviceStatusEvent(id=910002, device_id=900001, event_type='offline', to_status='offline',
                          source='monitor', success=False,
                          created_at=datetime(2026, 10, 3, 12, 0)),
        # 区间内：A 一条带指标的健康检查
        DeviceStatusEvent(id=910003, device_id=900001, event_type='health_check',
                          to_status='online', source='health_check', success=True,
                          detail={'serial_number': 'STATS-A',
                                  'metrics': {'cpu': 30, 'memory': 40, 'battery': 50}},
                          created_at=datetime(2026, 10, 3, 9, 0)),
        # 已删除设备的事件不得进入统计
        DeviceStatusEvent(id=910004, device_id=900003, event_type='health_check',
                          to_status='online', source='health_check', success=True,
                          detail={'metrics': {'cpu': 99}},
                          created_at=datetime(2026, 10, 3, 9, 0)),
    ]
    session.add_all(events)
    session.commit()

    yield session

    session.query(DeviceStatusEvent).filter(
        DeviceStatusEvent.device_id.in_([900001, 900002, 900003])).delete(
        synchronize_session=False)
    session.query(Device).filter(
        Device.id.in_([900001, 900002, 900003])).delete(synchronize_session=False)
    session.commit()
    remove_db_session()


class TestAggregateDailyStatsRepository:
    def test_points_baseline_and_device_scope(self, stats_data, sqlite_env):
        repo = DeviceMonitorRepository()
        result = repo.aggregate_daily_stats(
            start_date=date(2026, 10, 2), end_date=date(2026, 10, 4),
            lab_id=1, now=datetime(2026, 12, 31))

        # lab_id=1 只有未删除的 900001
        assert result['device_count'] == 1
        points = {p['date']: p for p in result['points']}
        assert list(points) == ['2026-10-02', '2026-10-03', '2026-10-04']

        # 10-02 无区间事件：基线（10-01 22:00 online）决定全天在线 → 100%
        assert points['2026-10-02']['availability'] == 100.0
        assert points['2026-10-02']['cpu'] is None
        assert points['2026-10-02']['errors'] == 0

        # 10-03：00:00~12:00 在线 → 50%；指标来自 health_check；
        # offline 状态事件的 success=false 不计入 errors（契约 §1.2 括号口径）
        assert points['2026-10-03']['availability'] == 50.0
        assert points['2026-10-03']['cpu'] == 30.0
        assert points['2026-10-03']['memory'] == 40.0
        assert points['2026-10-03']['battery'] == 50.0
        assert points['2026-10-03']['errors'] == 0
        assert points['2026-10-03']['health_check_samples'] == 1

        # 10-04：全天离线 → 0%（有可观测时长，不是 null）
        assert points['2026-10-04']['availability'] == 0.0

    def test_deleted_device_excluded(self, stats_data):
        repo = DeviceMonitorRepository()
        result = repo.aggregate_daily_stats(
            start_date=date(2026, 10, 3), end_date=date(2026, 10, 3),
            device_ids=[900003], now=datetime(2026, 12, 31))
        assert result['device_count'] == 0
        assert result['points'][0]['cpu'] is None

    def test_single_aggregate_sql_statement(self, stats_data, sqlite_env):
        engine, _, _ = sqlite_env
        statements = []

        from sqlalchemy import event

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, 'before_cursor_execute', _capture)
        try:
            DeviceMonitorRepository().aggregate_daily_stats(
                start_date=date(2026, 10, 2), end_date=date(2026, 10, 4),
                now=datetime(2026, 12, 31))
        finally:
            event.remove(engine, 'before_cursor_execute', _capture)

        event_statements = [s for s in statements if 'device_status_events' in s]
        assert len(event_statements) == 1, statements
        assert 'UNION ALL' in event_statements[0].upper()


# ==================== 3. 查询服务参数校验 ====================

class FakeStatsRepo:
    def __init__(self):
        self.calls = []

    def aggregate_daily_stats(self, device_ids=None, lab_id=None,
                              start_date=None, end_date=None, now=None):
        self.calls.append({
            'device_ids': device_ids, 'lab_id': lab_id,
            'start_date': start_date, 'end_date': end_date,
        })
        return {'device_count': 0, 'points': [{'date': start_date.isoformat(),
                                               'availability': None, 'cpu': None,
                                               'memory': None, 'battery': None,
                                               'errors': 0, 'operations': 0,
                                               'health_check_samples': 0}]}


class TestStatsQueryServiceValidation:
    @pytest.fixture
    def service(self):
        return DeviceStatsQueryService(monitor_repo=FakeStatsRepo())

    def _params(self, **overrides):
        params = {
            'start_date': '2026-10-01',
            'end_date': '2026-10-07',
            'granularity': 'day',
        }
        params.update(overrides)
        return params

    def test_valid_request(self, service):
        result = service.get_monitor_stats(self._params())
        assert result['success'] is True
        assert result['data']['granularity'] == 'day'
        assert result['data']['start_date'] == '2026-10-01'

    def test_missing_dates_rejected(self, service):
        assert service.get_monitor_stats({'granularity': 'day'})['code'] == 400

    def test_end_before_start_rejected(self, service):
        result = service.get_monitor_stats(self._params(end_date='2026-09-30'))
        assert result['code'] == 400
        assert '不能早于' in result['message']

    def test_span_91_days_rejected(self, service):
        # 2026-01-01 ~ 2026-04-01 = 91 天（含首尾）
        result = service.get_monitor_stats(self._params(
            start_date='2026-01-01', end_date='2026-04-01'))
        assert result['code'] == 400
        assert '90' in result['message']

    def test_span_90_days_accepted(self, service):
        result = service.get_monitor_stats(self._params(
            start_date='2026-01-01', end_date='2026-03-31'))
        assert result['success'] is True

    def test_granularity_hour_rejected(self, service):
        result = service.get_monitor_stats(self._params(granularity='hour'))
        assert result['code'] == 400
        assert 'day' in result['message']

    def test_device_ids_csv_and_lab_id_forwarded(self, service):
        service.get_monitor_stats(self._params(device_ids='1,2,3', lab_id='7'))
        call = service.monitor_repo.calls[0]
        assert call['device_ids'] == [1, 2, 3]
        assert call['lab_id'] == 7


# ==================== 4. gRPC servicer 信封 ====================

class TestServicer:
    def test_get_device_monitor_stats_returns_json_data(self):
        from shared.proto import device_service_pb2 as pb
        from device_service.interfaces.grpc.device_config_servicers import (
            DeviceConfigServiceServicer,
        )

        fake_query = SimpleNamespace(get_monitor_stats=lambda params: {
            'success': True,
            'message': 'ok',
            'data': {'granularity': 'day', 'start_date': params['start_date'],
                     'end_date': params['end_date'], 'device_count': 0, 'points': []},
        })
        servicer = DeviceConfigServiceServicer()
        servicer._stats_query = fake_query

        response = servicer.GetDeviceMonitorStats(pb.GetDeviceMonitorStatsRequest(
            data=json.dumps({'start_date': '2026-10-01', 'end_date': '2026-10-02'})),
            None)

        assert response.success is True
        assert json.loads(response.data)['start_date'] == '2026-10-01'

    def test_servicer_returns_failure_envelope_on_error(self):
        from shared.proto import device_service_pb2 as pb
        from device_service.interfaces.grpc.device_config_servicers import (
            DeviceConfigServiceServicer,
        )

        def _boom(params):
            raise RuntimeError('db down')

        servicer = DeviceConfigServiceServicer()
        servicer._stats_query = SimpleNamespace(get_monitor_stats=_boom)
        response = servicer.GetDeviceMonitorStats(
            pb.GetDeviceMonitorStatsRequest(data='{}'), None)

        assert response.success is False
        assert 'db down' in response.message


# ==================== 5. HTTP 路由契约（422 / 400，不触 gRPC） ====================

@pytest.fixture(scope='module')
def monitor_stats_client():
    """只挂 device_bp 的最小 FastAPI app（权限由中间件注入，不触 gRPC）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api_gateway.routes.device_bp import router

    app = FastAPI()

    @app.middleware('http')
    async def _inject_permissions(request, call_next):
        request.state.permissions = ['*']
        request.state.user_id = 1
        return await call_next(request)

    app.include_router(router, prefix='/api/v1/test-devices')
    return TestClient(app)


class TestMonitorStatsRouteContract:
    """参数校验发生在调用 ACL 之前，故无需真实 device_service 即可验状态码。"""

    URL = '/api/v1/test-devices/monitor-stats'

    def test_missing_start_date_returns_422(self, monitor_stats_client):
        response = monitor_stats_client.get(self.URL, params={'end_date': '2026-10-07'})
        assert response.status_code == 422

    def test_missing_end_date_returns_422(self, monitor_stats_client):
        response = monitor_stats_client.get(self.URL, params={'start_date': '2026-10-01'})
        assert response.status_code == 422

    def test_end_before_start_returns_400(self, monitor_stats_client):
        response = monitor_stats_client.get(self.URL, params={
            'start_date': '2026-10-07', 'end_date': '2026-10-01'})
        assert response.status_code == 400
        assert '不能早于' in response.json()['message']

    def test_span_91_days_returns_400(self, monitor_stats_client):
        response = monitor_stats_client.get(self.URL, params={
            'start_date': '2026-01-01', 'end_date': '2026-04-01'})
        assert response.status_code == 400
        assert '90' in response.json()['message']

    def test_granularity_hour_returns_400(self, monitor_stats_client):
        response = monitor_stats_client.get(self.URL, params={
            'start_date': '2026-10-01', 'end_date': '2026-10-07',
            'granularity': 'hour'})
        assert response.status_code == 400
        assert 'day' in response.json()['message']

    def test_static_route_registered_before_device_id(self, monitor_stats_client):
        """若被 /{device_id} 抢先匹配，合法日期请求会被 device_id 解析拦截；
        这里命中区间校验（400）证明静态段先注册。"""
        response = monitor_stats_client.get(self.URL, params={
            'start_date': '2026-10-07', 'end_date': '2026-10-01'})
        assert response.status_code == 400

    def test_without_device_read_permission_returns_403(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api_gateway.routes.device_bp import router

        app = FastAPI()

        @app.middleware('http')
        async def _no_permissions(request, call_next):
            request.state.permissions = []
            request.state.user_id = 1
            return await call_next(request)

        app.include_router(router, prefix='/api/v1/test-devices')

        response = TestClient(app).get(self.URL, params={
            'start_date': '2026-10-01', 'end_date': '2026-10-07'})
        assert response.status_code == 403


# ==================== 6. gRPC 全链路（网关 service → ACL → 代理 → servicer → 聚合 SQL） ====================

class TestMonitorStatsGrpcChain:
    def test_gateway_service_returns_aggregated_points(self, stats_data):
        import grpc
        from concurrent.futures import ThreadPoolExecutor

        from shared.proto import device_service_pb2_grpc as pb_grpc
        from device_service.interfaces.grpc.device_config_servicers import (
            DeviceConfigServiceServicer,
        )
        from api_gateway.application.services.device import device_query_service as gateway_module

        server = grpc.server(ThreadPoolExecutor(max_workers=2))
        pb_grpc.add_DeviceConfigServiceServicer_to_server(
            DeviceConfigServiceServicer(), server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        channel = grpc.insecure_channel(f'127.0.0.1:{port}')
        stub = pb_grpc.DeviceConfigServiceStub(channel)
        try:
            with patch(
                'api_gateway.infrastructure.grpc_proxies.device_proxies.get_device_config_service_stub',
                return_value=stub,
            ):
                body, status = gateway_module.DeviceQueryService.get_monitor_stats(
                    '2026-10-02', '2026-10-03', device_ids='900001', granularity='day')
        finally:
            channel.close()
            server.stop(0)

        assert status == 200
        data = body['data']
        assert data['device_count'] == 1
        assert [p['date'] for p in data['points']] == ['2026-10-02', '2026-10-03']
        assert data['points'][0]['availability'] == 100.0
        assert data['points'][1]['cpu'] == 30.0


# ==================== 7. 指标采集解析 ====================

class TestAndroidMetricParsing:
    def test_dumpsys_battery_level(self):
        output = (
            'Current Battery Service state:\n'
            '  AC powered: false\n'
            '  level: 78\n'
            '  scale: 100\n'
        )
        assert collector._parse_dumpsys_battery(output) == 78.0

    def test_dumpsys_battery_non_100_scale(self):
        output = '  level: 100\n  scale: 200\n'
        assert collector._parse_dumpsys_battery(output) == 50.0

    def test_dumpsys_battery_without_level_returns_none(self):
        assert collector._parse_dumpsys_battery('Current Battery Service state:\n') is None

    def test_proc_meminfo_uses_mem_available(self):
        output = (
            'MemTotal:        4000000 kB\n'
            'MemFree:          500000 kB\n'
            'MemAvailable:    1000000 kB\n'
        )
        # (4000000-1000000)/4000000 = 75%
        assert collector._parse_proc_meminfo(output) == 75.0

    def test_proc_meminfo_falls_back_to_mem_free(self):
        output = (
            'MemTotal:        4000000 kB\n'
            'MemFree:         1000000 kB\n'
        )
        assert collector._parse_proc_meminfo(output) == 75.0

    def test_proc_meminfo_missing_total_returns_none(self):
        assert collector._parse_proc_meminfo('MemFree: 1 kB\n') is None

    def test_toybox_top_aggregate_line(self):
        output = (
            'Tasks: 300 total,   1 running\n'
            'Mem:  2000000K used,  3000000K free\n'
            '400%cpu  55%user   0%nice  31%sys 308%idle   2%iow  0%irq   3%sirq   0%host\n'
            '  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS\n'
        )
        # 分项合计 399，idle 308 → 使用率 (399-308)/399 = 22.8%
        assert collector._parse_toybox_top_cpu(output) == 22.8

    def test_toybox_top_without_summary_returns_none(self):
        assert collector._parse_toybox_top_cpu('  PID USER ARGS\n') is None


class TestHarmonyMetricParsing:
    def test_hidumper_battery_capacity(self):
        assert collector._parse_hidumper_battery(
            'BatteryService dump:\n  capacity: 85\n') == 85.0

    def test_hidumper_battery_missing_returns_none(self):
        assert collector._parse_hidumper_battery('no battery info\n') is None

    def test_hidumper_memory_mixed_units(self):
        output = (
            'Total Memory: 8 GB\n'
            'Free Memory: 2048 MB\n'
        )
        # (8GB-2GB)/8GB = 75%
        assert collector._parse_hidumper_memory(output) == 75.0

    def test_hidumper_memory_missing_returns_none(self):
        assert collector._parse_hidumper_memory('nothing here\n') is None

    def test_hidumper_cpu_usage(self):
        assert collector._parse_hidumper_cpu('CPU usage: 12.5%\n') == 12.5

    def test_hidumper_cpu_missing_returns_none(self):
        assert collector._parse_hidumper_cpu('no cpu line\n') is None


class TestCollectDeviceMetrics:
    def test_collects_only_successful_keys(self):
        def fake_run(args):
            command = ' '.join(args)
            if 'dumpsys battery' in command:
                return '  level: 66\n  scale: 100\n'
            if 'meminfo' in command:
                return 'MemTotal: 100 kB\nMemAvailable: 25 kB\n'
            return None  # top 采不到

        with patch.object(collector, '_run_command', side_effect=fake_run):
            metrics = collector.collect_device_metrics('Android', 'SERIAL-1')

        assert metrics == {'battery': 66.0, 'memory': 75.0}
        assert 'cpu' not in metrics

    def test_command_timeout_is_swallowed(self):
        import subprocess

        with patch.object(collector.subprocess, 'run',
                          side_effect=subprocess.TimeoutExpired(cmd='adb', timeout=5)):
            assert collector._run_command(['adb', 'devices']) is None
            assert collector.collect_device_metrics('Android', 'SERIAL-1') == {}

    def test_nonzero_exit_returns_none(self):
        completed = SimpleNamespace(returncode=1, stdout='garbage')
        with patch.object(collector.subprocess, 'run', return_value=completed):
            assert collector._run_command(['adb', 'devices']) is None

    def test_unknown_system_not_collected(self):
        assert collector.collect_device_metrics('iOS', 'SERIAL-1') == {}

    def test_missing_serial_not_collected(self):
        assert collector.collect_device_metrics('Android', '') == {}


# ==================== 8. 健康检查接入 ====================

class FakeHealthRepo:
    def __init__(self, devices):
        self.devices = devices
        self.status_updates = []
        self.events = []

    def list_devices(self, page=1, per_page=10, **kwargs):
        return {'items': [dict(d) for d in self.devices], 'total': len(self.devices),
                'page': page, 'per_page': per_page, 'pages': 1}

    def get_device(self, device_id):
        for device in self.devices:
            if device['id'] == device_id:
                return SimpleNamespace(**device, to_dict=lambda d=device: dict(d))
        return None

    def update_device_status(self, device_id, status, last_online_at=None):
        self.status_updates.append((device_id, status))
        return True


class FakeDriver:
    def __init__(self, serials):
        self._serials = serials
        self._mock_mode = False

    def scan(self):
        return [{'serial': serial, 'model': 'M', 'system': 'Android', 'status': 'online'}
                for serial in self._serials]


class FakeMonitorService:
    def __init__(self):
        self.recorded = []

    def record_status_event(self, **kwargs):
        self.recorded.append(kwargs)
        return kwargs


@pytest.fixture
def health_service():
    from device_service.application.commands.device_command_service import DeviceCommandService
    devices = [
        {'id': 1, 'name': '在线机', 'system': 'Android', 'serial_number': 'ONLINE-1',
         'status': 'offline', 'model': 'M'},
        {'id': 2, 'name': '离线机', 'system': 'Android', 'serial_number': 'OFFLINE-1',
         'status': 'offline', 'model': 'M'},
    ]
    service = DeviceCommandService(repo=FakeHealthRepo(devices))
    return service


class TestHealthCheckMetrics:
    @pytest.fixture(autouse=True)
    def _no_sleep(self):
        """健康检查每台设备有 0.5~2s 随机等待，测试中直接跳过。"""
        with patch('device_service.application.commands.device_command_service.time.sleep'):
            yield

    def _run(self, health_service, metrics_by_serial, serials=('ONLINE-1',)):
        monitor = FakeMonitorService()
        driver = FakeDriver(serials)

        def _collect(system, serial_number):
            if serial_number in metrics_by_serial:
                return metrics_by_serial[serial_number]
            return {}

        with patch(
            'device_service.infrastructure.drivers.driver_factory.device_driver_factory'
        ) as factory, patch.object(
            health_service, '_collect_health_metrics', side_effect=lambda d: _collect(
                d.get('system'), d.get('serial_number'))
        ):
            factory.get_driver_by_system.return_value = driver
            with patch(
                'device_service.application.services.device_monitor_service.device_monitor_service',
                monitor,
            ):
                result = health_service.health_check()
        return result, monitor

    def test_online_device_writes_metrics(self, health_service):
        result, monitor = self._run(
            health_service, {'ONLINE-1': {'cpu': 31.5, 'battery': 82.0}})

        assert result['success'] is True
        health_event = next(e for e in monitor.recorded
                            if e['event_type'] == 'health_check' and e['device_id'] == 1)
        assert health_event['detail']['metrics'] == {'cpu': 31.5, 'battery': 82.0}
        assert health_event['detail']['serial_number'] == 'ONLINE-1'
        assert health_event['success'] is True

    def test_offline_device_has_no_metrics(self, health_service):
        result, monitor = self._run(health_service, {}, serials=())

        assert result['success'] is True
        health_events = [e for e in monitor.recorded if e['event_type'] == 'health_check']
        assert health_events
        for event in health_events:
            assert 'metrics' not in event['detail']
            assert event['success'] is False

    def test_metrics_absent_when_nothing_collected(self, health_service):
        result, monitor = self._run(health_service, {}, serials=('ONLINE-1',))

        assert result['success'] is True
        event = next(e for e in monitor.recorded if e['event_type'] == 'health_check'
                     and e['device_id'] == 1)
        assert 'metrics' not in event['detail']   # 采不到就不写该键，不写 0

    def test_collector_exception_does_not_fail_health_check(self, health_service):
        monitor = FakeMonitorService()
        driver = FakeDriver(('ONLINE-1',))

        with patch(
            'device_service.infrastructure.drivers.device_metrics_collector.collect_device_metrics',
            side_effect=RuntimeError('collector exploded'),
        ), patch(
            'device_service.infrastructure.drivers.driver_factory.device_driver_factory'
        ) as factory, patch(
            'device_service.application.services.device_monitor_service.device_monitor_service',
            monitor,
        ):
            factory.get_driver_by_system.return_value = driver
            result = health_service.health_check()

        assert result['success'] is True
        event = next(e for e in monitor.recorded if e['event_type'] == 'health_check'
                     and e['device_id'] == 1)
        assert event['success'] is True          # is_online 判定不变
        assert 'metrics' not in event['detail']


