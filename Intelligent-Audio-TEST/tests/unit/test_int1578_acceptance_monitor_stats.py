# -*- coding: utf-8 -*-
"""INT-1578 验收用例（测试工程师独立编写，不复用实施者用例）。

覆盖：
  A. HTTP 契约矩阵（缺参 422 / end<start 400 / 91 天 400 / granularity≠day 400 / 无权限 403）
  B. 聚合口径手算对拍（逐日重放、null 语义、errors/operations 计数）
  C. 真库只读对拍（INT1578_REAL_DB=1 时执行：真实 device_status_events 独立重算）
  D. 性能：10 设备 × 90 天 P95 < 2s + 只发 1 条聚合 SQL
  E. 真机输出回放（HarmonyOS hidumper 实采文本 → 解析函数）
  F. 健康检查接入（采不到不写键、无全 0、is_online 与整体成功不变）
"""
import json
import os
import statistics
import time
from datetime import date, datetime, timedelta

import pytest

# BaseConfig 类属性首次 import 即校验 OSS 配置；本模块不触网，占位即可
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

pytestmark = pytest.mark.timeout(600)

URL = '/api/v1/test-devices/monitor-stats'


# ==================== A. HTTP 契约矩阵 ====================

def _client(permissions=('*',)):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api_gateway.routes.device_bp import router

    app = FastAPI()

    @app.middleware('http')
    async def _inject(request, call_next):
        request.state.permissions = list(permissions)
        request.state.user_id = 1
        return await call_next(request)

    app.include_router(router, prefix='/api/v1/test-devices')
    return TestClient(app)


class TestHttpContract:
    def test_missing_start_date_422(self):
        r = _client().get(URL, params={'end_date': '2026-10-07'})
        assert r.status_code == 422, r.text

    def test_missing_end_date_422(self):
        r = _client().get(URL, params={'start_date': '2026-10-01'})
        assert r.status_code == 422, r.text

    def test_missing_both_422(self):
        r = _client().get(URL)
        assert r.status_code == 422, r.text

    def test_end_before_start_400(self):
        r = _client().get(URL, params={'start_date': '2026-10-07', 'end_date': '2026-10-01'})
        assert r.status_code == 400, r.text
        assert '结束日期不能早于开始日期' in r.text

    def test_span_91_days_400(self):
        # 2026-01-01 ~ 2026-04-01 = 91 天（含首尾）
        r = _client().get(URL, params={'start_date': '2026-01-01', 'end_date': '2026-04-01'})
        assert r.status_code == 400, r.text
        assert '统计区间不得超过 90 天' in r.text

    def test_granularity_hour_400(self):
        r = _client().get(URL, params={
            'start_date': '2026-10-01', 'end_date': '2026-10-07', 'granularity': 'hour'})
        assert r.status_code == 400, r.text
        assert 'day' in r.text

    def test_without_device_read_403(self):
        r = _client(permissions=()).get(URL, params={
            'start_date': '2026-10-01', 'end_date': '2026-10-07'})
        assert r.status_code == 403, r.text

    def test_static_route_not_swallowed_by_device_id(self):
        """静态段先于 /{device_id}：参数缺失应是 422（query）而不是 device_id 解析错误。"""
        r = _client().get(URL)
        assert r.status_code == 422
        locs = {tuple(item.get('loc', [])) for item in r.json().get('detail', [])}
        assert not any('device_id' in loc for loc in locs), locs


# ==================== A2. 服务侧边界 ====================

class _FakeRepo:
    def __init__(self):
        self.calls = []

    def aggregate_daily_stats(self, device_ids=None, lab_id=None, start_date=None, end_date=None):
        self.calls.append((device_ids, lab_id, start_date, end_date))
        return {'device_count': 0, 'points': []}


@pytest.fixture
def service():
    from device_service.application.queries.device_stats_query_service import DeviceStatsQueryService
    return DeviceStatsQueryService(monitor_repo=_FakeRepo())


class TestServiceBoundary:
    def test_span_90_days_accepted(self, service):
        r = service.get_monitor_stats({'start_date': '2026-01-01', 'end_date': '2026-03-31'})
        assert r['success'] is True, r
        assert service.monitor_repo.calls

    def test_span_90_days_plus_one_rejected(self, service):
        r = service.get_monitor_stats({'start_date': '2026-01-01', 'end_date': '2026-04-01'})
        assert r['success'] is False and r['code'] == 400

    def test_granularity_defaults_to_day(self, service):
        service.get_monitor_stats({'start_date': '2026-10-01', 'end_date': '2026-10-02'})
        data = service.get_monitor_stats({'start_date': '2026-10-01', 'end_date': '2026-10-02'})
        assert data['data']['granularity'] == 'day'


# ==================== B. 聚合口径手算对拍 ====================

def _ev(device_id, event_type, when, success=True, to_status=None, detail=None):
    return {
        'device_id': device_id, 'event_type': event_type, 'to_status': to_status,
        'success': success, 'detail': detail, 'created_at': when,
    }


class TestAggregationHandCheck:
    DAY = date(2026, 10, 5)
    NOW = datetime(2026, 10, 6, 0, 0)  # 区间日已完整过去

    def _points(self, events):
        from device_service.infrastructure.persistence.device_monitor_repository import (
            _aggregate_daily_points,
        )
        return _aggregate_daily_points(events, [self.DAY], self.NOW)

    def test_empty_day_all_null_and_zero_counts(self):
        p = self._points([])[0]
        assert p['date'] == '2026-10-05'
        assert p['availability'] is None
        assert p['cpu'] is None and p['memory'] is None and p['battery'] is None
        assert p['errors'] == 0 and p['operations'] == 0
        assert p['health_check_samples'] == 0

    def test_availability_half_day_online(self):
        """日初在线（区间外基线）→ 06:00 离线 → 18:00 上线：在线 6h + 6h = 50%。"""
        events = [
            _ev(1, 'online', datetime(2026, 10, 4, 20, 0)),
            _ev(1, 'offline', datetime(2026, 10, 5, 6, 0), success=False),
            _ev(1, 'online', datetime(2026, 10, 5, 18, 0)),
        ]
        p = self._points(events)[0]
        assert p['availability'] == 50.0, p

    def test_availability_no_baseline_first_event_is_start(self):
        """日初无基线：首条事件 12:00 离线 → 观测 12h 全离线 → 0.0（不是 null）。"""
        events = [_ev(1, 'offline', datetime(2026, 10, 5, 12, 0), success=False)]
        p = self._points(events)[0]
        assert p['availability'] == 0.0, p

    def test_availability_null_when_no_state_events(self):
        events = [_ev(1, 'health_check', datetime(2026, 10, 5, 9, 0),
                      detail={'metrics': {'cpu': 10}})]
        p = self._points(events)[0]
        assert p['availability'] is None, p
        assert p['cpu'] == 10.0

    def test_availability_averaged_across_devices(self):
        """设备1 全天在线(100) + 设备2 全天离线(0) → 平均 50.0。"""
        events = [
            _ev(1, 'online', datetime(2026, 10, 1, 0, 0)),
            _ev(2, 'offline', datetime(2026, 10, 1, 0, 0), success=False),
        ]
        p = self._points(events)[0]
        assert p['availability'] == 50.0, p

    def test_errors_and_operations_counting(self):
        events = [
            _ev(1, 'health_check', datetime(2026, 10, 5, 8, 0), success=False),
            _ev(1, 'operation', datetime(2026, 10, 5, 9, 0), success=True),
            _ev(1, 'health_check', datetime(2026, 10, 5, 10, 0), success=True),
            _ev(1, 'operation', datetime(2026, 10, 5, 11, 0), success=False),
            _ev(1, 'online', datetime(2026, 10, 5, 12, 0), to_status='error', success=False),
        ]
        p = self._points(events)[0]
        # 契约 §1.2 括号口径：errors = health_check/operation 的 success=false 事件数(2)
        # + to_status=error 事件数(1)；那条 online 事件的 success=false 不再单独计入。
        assert p['errors'] == 3, p
        assert p['operations'] == 1, p
        assert p['health_check_samples'] == 2, p

    def test_offline_transition_not_counted_as_error(self):
        """契约 §1.2 括号口径：errors 只算 health_check 失败 + operation 失败。

        离线状态事件在写入时 `success=is_online`（见 device_command_service），
        因此每条 offline 事件都是 success=False。若按「事件表全量 success=False」
        计数，则设备每次正常下线都会在错误图里多一个错误点。
        """
        events = [
            _ev(1, 'offline', datetime(2026, 10, 5, 12, 0), success=False),
            _ev(1, 'health_check', datetime(2026, 10, 5, 8, 0), success=True),
        ]
        p = self._points(events)[0]
        assert p['errors'] == 0, p

    def test_metrics_only_from_health_check_events(self):
        events = [
            _ev(1, 'health_check', datetime(2026, 10, 5, 8, 0),
                detail={'metrics': {'cpu': 20.0, 'memory': 40.0, 'battery': 80.0}}),
            _ev(1, 'health_check', datetime(2026, 10, 5, 9, 0),
                detail={'metrics': {'cpu': 40.0, 'battery': 90.0}}),
            # operation 事件里即使有 metrics 也不计入
            _ev(1, 'operation', datetime(2026, 10, 5, 10, 0), success=True,
                detail={'metrics': {'cpu': 99.0}}),
        ]
        p = self._points(events)[0]
        assert p['cpu'] == 30.0
        assert p['memory'] == 40.0
        assert p['battery'] == 85.0

    def test_metrics_missing_key_not_zero_filled(self):
        events = [
            _ev(1, 'health_check', datetime(2026, 10, 5, 8, 0), detail={'metrics': {'battery': 77.0}}),
        ]
        p = self._points(events)[0]
        assert p['battery'] == 77.0
        assert p['cpu'] is None and p['memory'] is None

    def test_every_day_in_range_returned(self):
        from device_service.infrastructure.persistence.device_monitor_repository import (
            _aggregate_daily_points,
        )
        days = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
        points = _aggregate_daily_points([], days, self.NOW)
        assert [p['date'] for p in points] == [d.isoformat() for d in days]


# ==================== C. 真库只读对拍 ====================

REAL_DB = os.environ.get('INT1578_REAL_DB') == '1'


@pytest.mark.skipif(not REAL_DB, reason='需 INT1578_REAL_DB=1 且 INT1578_REAL_DB_URL 指向真实库')
class TestRealDbReadOnly:
    """真实 device_status_events 上的只读对拍：聚合结果 vs 独立 SQL 重算。

    不经过进程级 DATABASE_URL（conftest 的共享库守卫），自建只读 engine 并 patch
    仓储取 session 的入口；全程只发 SELECT。
    """

    START = date(2026, 10, 13)
    END = date(2026, 10, 23)

    @pytest.fixture(scope='class')
    def real_engine(self):
        from sqlalchemy import create_engine

        url = os.environ.get(
            'INT1578_REAL_DB_URL',
            'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:15432/intelligent_audio_test')
        engine = create_engine(url, pool_pre_ping=True)
        yield engine
        engine.dispose()

    @pytest.fixture
    def real_repo(self, real_engine):
        from sqlalchemy.orm import sessionmaker
        from unittest.mock import patch

        session_factory = sessionmaker(bind=real_engine)
        with patch(
            'device_service.infrastructure.persistence.device_monitor_repository.get_db_session',
            side_effect=lambda: session_factory(),
        ):
            from device_service.infrastructure.persistence import device_monitor_repository as mod
            yield mod.device_monitor_repository

    def test_aggregate_matches_independent_sql(self, real_engine, real_repo):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker

        session = sessionmaker(bind=real_engine)()
        try:
            result = real_repo.aggregate_daily_stats(
                start_date=self.START, end_date=self.END)
            points = {p['date']: p for p in result['points']}
            assert len(points) == (self.END - self.START).days + 1

            scope_ids = [row[0] for row in session.execute(text(
                'select id from devices where deleted = false')).all()]
            assert result['device_count'] == len(scope_ids)

            rows = session.execute(text(
                """
                select date(created_at) as d,
                       count(*) filter (where event_type = 'health_check') as samples,
                       count(*) filter (where event_type in ('health_check','operation')
                                        and success = false) as failed,
                       count(*) filter (where coalesce(to_status,'') = 'error') as errored,
                       count(*) filter (where event_type = 'operation' and success) as ops
                from device_status_events
                where device_id = any(:ids) and created_at >= :s and created_at < :e
                group by date(created_at) order by d
                """), {'ids': scope_ids,
                       's': datetime.combine(self.START, datetime.min.time()),
                       'e': datetime.combine(self.END + timedelta(days=1), datetime.min.time())}).all()
            by_day = {str(r[0]): r for r in rows}

            for day, point in points.items():
                row = by_day.get(day)
                if row is None:
                    assert point['errors'] == 0 and point['operations'] == 0
                    assert point['health_check_samples'] == 0
                    continue
                assert point['health_check_samples'] == row[1], (day, point['health_check_samples'], row[1])
                assert point['errors'] == row[2] + row[3], (day, point['errors'], row[2], row[3])
                assert point['operations'] == row[4], (day, point['operations'], row[4])

            metric_rows = session.execute(text(
                """
                select date(created_at) as d,
                       avg((detail::jsonb->'metrics'->>'cpu')::numeric) as cpu,
                       avg((detail::jsonb->'metrics'->>'memory')::numeric) as memory,
                       avg((detail::jsonb->'metrics'->>'battery')::numeric) as battery
                from device_status_events
                where device_id = any(:ids) and event_type = 'health_check'
                  and detail::jsonb->'metrics' is not null
                  and created_at >= :s and created_at < :e
                group by date(created_at)
                """), {'ids': scope_ids,
                       's': datetime.combine(self.START, datetime.min.time()),
                       'e': datetime.combine(self.END + timedelta(days=1), datetime.min.time())}).all()
            metrics_by_day = {str(r[0]): r for r in metric_rows}
            for day, point in points.items():
                row = metrics_by_day.get(day)
                for idx, key in ((1, 'cpu'), (2, 'memory'), (3, 'battery')):
                    expected = None if row is None or row[idx] is None else round(float(row[idx]), 1)
                    assert point[key] == expected, (day, key, point[key], expected)
        finally:
            session.close()

    def test_scope_filters(self, real_repo):
        all_scope = real_repo.get_monitor_device_ids()
        if len(all_scope) < 2:
            pytest.skip('真库未删除设备不足 2 台')
        assert real_repo.get_monitor_device_ids(device_ids=[all_scope[0]]) == [all_scope[0]]

    def test_read_only_no_rows_written(self, real_engine, real_repo):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker

        session = sessionmaker(bind=real_engine)()
        try:
            before = session.execute(text('select count(*), max(id) from device_status_events')).one()
            real_repo.aggregate_daily_stats(start_date=self.START, end_date=self.END)
            after = session.execute(text('select count(*), max(id) from device_status_events')).one()
            assert tuple(before) == tuple(after)
        finally:
            session.close()


# ==================== D. 性能（10 设备 × 90 天） ====================

class TestPerformance:
    def test_10_devices_90_days_p95_under_2s_and_single_sql(self):
        from sqlalchemy import event
        from shared.models import database
        from device_service.infrastructure.persistence.models import Device, DeviceStatusEvent
        from device_service.infrastructure.persistence.device_monitor_repository import (
            device_monitor_repository as repo,
        )

        database.init_db()
        engine = database.get_engine()
        database.Base.metadata.create_all(
            bind=engine, tables=[Device.__table__, DeviceStatusEvent.__table__])

        start = date(2026, 7, 1)
        end = start + timedelta(days=89)
        device_ids = list(range(500001, 500011))
        base_time = datetime(2026, 6, 30, 12, 0)

        session = database.get_db_session()
        try:
            session.query(DeviceStatusEvent).filter(
                DeviceStatusEvent.device_id.in_(device_ids)).delete(synchronize_session=False)
            session.query(Device).filter(Device.id.in_(device_ids)).delete(synchronize_session=False)
            session.add_all([
                Device(id=i, name=f'INT1578PERF{i}', model='M', type='phone', system='Android',
                       system_version='14', app_name='a', app_version='1',
                       serial_number=f'PERF{i}', status='online', deleted=False)
                for i in device_ids
            ])
            payload = []
            next_id = [880000]
            # 每设备区间外一条基线 + 90 天 × 每 15 分钟一条 health_check（96/天）
            for i in device_ids:
                next_id[0] += 1
                payload.append(DeviceStatusEvent(
                    id=next_id[0], device_id=i, event_type='online', to_status='online',
                    source='monitor', success=True, detail={}, created_at=base_time))
            for day_offset in range(90):
                day = start + timedelta(days=day_offset)
                for i in device_ids:
                    for slot in range(96):
                        next_id[0] += 1
                        when = datetime.combine(day, datetime.min.time()) + timedelta(minutes=15 * slot)
                        payload.append(DeviceStatusEvent(
                            id=next_id[0], device_id=i, event_type='health_check', to_status='online',
                            source='health_check', success=(slot != 0),
                            detail={'serial_number': f'PERF{i}',
                                    'metrics': {'cpu': 30.0, 'memory': 50.0, 'battery': 70.0}},
                            created_at=when))
            session.bulk_save_objects(payload)
            session.commit()

            statements = []
            counter = {'n': 0}

            def _before(conn, cursor, statement, params, context, executemany):
                if 'device_status_events' in statement:
                    counter['n'] += 1

            event.listen(engine, 'before_cursor_execute', _before)
            try:
                timings = []
                for _ in range(5):
                    counter['n'] = 0
                    t0 = time.perf_counter()
                    out = repo.aggregate_daily_stats(start_date=start, end_date=end)
                    timings.append(time.perf_counter() - t0)
                    statements.append(counter['n'])
            finally:
                event.remove(engine, 'before_cursor_execute', _before)

            assert out['device_count'] == 10
            assert len(out['points']) == 90
            p95 = statistics.quantiles(timings, n=20)[-1] if len(timings) > 1 else max(timings)
            assert p95 < 2.0, f'P95={p95:.3f}s timings={timings}'
            assert max(statements) == 1, f'聚合应为 1 条 SQL，实测 {statements}'
        finally:
            session.query(DeviceStatusEvent).filter(
                DeviceStatusEvent.device_id.in_(device_ids)).delete(synchronize_session=False)
            session.query(Device).filter(Device.id.in_(device_ids)).delete(synchronize_session=False)
            session.commit()
            database.remove_db_session()


# ==================== E. 真机输出回放（真机实采文本） ====================

# 2026-10-23 于真机 6YF0126211000225（HarmonyOS）实采，节选
_REAL_HARMONY_CPU = """-------------------------------[cpuusage]----------------------------------
Load average: 12.0 / 12.3 / 12.5; the cpu load average in 1 min, 5 min and 15 min
CPU usage from 2026-10-23 23:27:43 to 2026-10-23 23:27:51
Total: 11.00%; User Space: 1.37%; Kernel Space: 9.63%; iowait: 0.00%; irq: 0.09%; idle: 88.91%
Details of Processes:
    PID   Total Usage\t   User Space    Kernel Space    Page Fault Minor    Page Fault Major    Name
    9339      27.25%          10.03%         17.21%           59942                4262    hidumper_service
"""

_REAL_HARMONY_MEM = """-------------------------------[memory]-------------------------------
Total Memory Usage by PID:
PID        Total Pss(xxx in SwapPss)    Total Vss    Total Rss    Total Uss           GL        Graph          Dma      PurgSum      PurgPin     Name
1           4742(1068 in SwapPss) kB   2164444 kB      6736 kB      3380 kB         0 kB          0 kB         0 kB         0 kB         0 kB     init
852        19579(9964 in SwapPss) kB   2612152 kB     17652 kB      9240 kB         0 kB          0 kB         0 kB         0 kB         0 kB     audio_server
"""

_REAL_HARMONY_BATTERY = """----------------------------------BatteryService----------------------------------
Current time: 2026-10-23 23:26:55.586
capacity: 98
batteryLevel: 2
chargingStatus: 1
"""


class TestRealDeviceParsing:
    def test_battery_from_real_output(self):
        from device_service.infrastructure.drivers import device_metrics_collector as c
        assert c._parse_hidumper_battery(_REAL_HARMONY_BATTERY) == 98.0

    def test_cpu_from_real_output(self):
        """真机 hidumper --cpuusage 的汇总行是 `Total: 11.00%`，必须解析出 11.0。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        assert c._parse_hidumper_cpu(_REAL_HARMONY_CPU) == 11.0

    def test_memory_from_real_output(self):
        """真机 hidumper --mem 为逐 PID 明细，无总量/可用汇总行；不得据此写值。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        # 该输出确实取不到内存使用率 → None 是「采不到」的正确结果（现已改走 /proc/meminfo）
        assert c._parse_hidumper_memory(_REAL_HARMONY_MEM) is None

    def test_memory_prefers_proc_meminfo(self):
        """P1-2：HarmonyOS 内存改走 `cat /proc/meminfo`，一条命令即得出使用率。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        from unittest.mock import patch

        output = 'MemTotal:       11720024 kB\nMemFree:         1000000 kB\nMemAvailable:    4345856 kB\n'
        calls = []

        def fake_run(args):
            calls.append(args)
            return output

        with patch.object(c, '_run_command', fake_run):
            value = c._harmony_memory('SN1')
        assert value == 62.9, value
        assert calls == [['hdc', '-t', 'SN1', 'shell', 'cat', '/proc/meminfo']], calls

    def test_memory_command_failure_does_not_run_second_command(self):
        """P1-2：/proc/meminfo 失败/超时不再追加 hidumper --mem（避免白烧第二个 5s）。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        from unittest.mock import patch

        calls = []
        with patch.object(c, '_run_command', lambda args: calls.append(args) or None):
            assert c._harmony_memory('SN1') is None
        assert len(calls) == 1, calls

    def test_cpu_from_idle_when_no_total_line(self):
        """P1-1 兜底：无 Total 汇总行时按 idle 反算。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        assert c._parse_hidumper_cpu('User Space: 1.37%; idle: 88.91%\n') == 11.1

    def test_system_value_is_normalized(self):
        """主库非删除测试设备 system 存在 'harmony' 小写值，采集器须同样归一。"""
        from device_service.infrastructure.drivers import device_metrics_collector as c
        from unittest.mock import patch
        with patch.object(c, '_harmony_battery', lambda serial: 66.0), \
             patch.object(c, '_harmony_memory', lambda serial: None), \
             patch.object(c, '_harmony_cpu', lambda serial: None):
            assert c.collect_device_metrics('harmony', 'SN1') == {'battery': 66.0}


# ==================== F. 健康检查接入 ====================

class _FakeHealthDriver:
    def __init__(self, online_serials):
        self.online_serials = online_serials
        self._mock_mode = False

    def scan(self):
        return [{'serial': s} for s in self.online_serials]


class _FakeHealthRepo:
    def __init__(self, devices):
        self._devices = devices
        self.status_updates = []

    def list_devices(self, page=1, per_page=100000):
        return {'items': list(self._devices)}

    def get_device(self, device_id):
        class _D:
            def __init__(self, data):
                self._data = data

            def to_dict(self):
                return dict(self._data)
        for d in self._devices:
            if d['id'] == device_id:
                return _D(d)
        return None

    def update_device_status(self, device_id, status, online_time=None):
        self.status_updates.append((device_id, status))

    def update_device_statuses(self, updates):
        for update in updates:
            self.status_updates.append((update['id'], update['status']))
        return len(updates)


class _FakeMonitor:
    def __init__(self):
        self.events = []

    def record_status_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs

    def record_status_events(self, events):
        for event in events:
            self.events.append(dict(event))
        return list(events)


def _health_service(devices, online_serials):
    from unittest.mock import patch
    from device_service.application.commands.device_command_service import DeviceCommandService

    repo = _FakeHealthRepo(devices)
    monitor = _FakeMonitor()
    service = DeviceCommandService(repo=repo)
    patches = [
        patch('device_service.infrastructure.drivers.driver_factory.device_driver_factory'),
        patch('device_service.application.services.device_monitor_service.device_monitor_service',
              monitor),
    ]
    for p in patches:
        p.start()
    from device_service.infrastructure.drivers import driver_factory as df
    df.device_driver_factory.get_driver_by_system.return_value = _FakeHealthDriver(online_serials)
    return service, monitor, patches


class TestHealthCheckIntegration:
    def _run(self, devices, online_serials, collector):
        from unittest.mock import patch
        service, monitor, patches = _health_service(devices, online_serials)
        try:
            with patch(
                'device_service.infrastructure.drivers.device_metrics_collector.collect_device_metrics',
                side_effect=collector,
            ) as m:
                result = service.health_check([d['id'] for d in devices])
        finally:
            for p in patches:
                p.stop()
        return result, monitor, m

    def _device(self, **kw):
        base = {'id': 700001, 'name': 'INT1578健康检查', 'model': 'M', 'system': 'HarmonyOS',
                'serial_number': 'SN-1', 'status': 'online'}
        base.update(kw)
        return base

    def test_online_device_metrics_written_to_same_event(self):
        result, monitor, m = self._run(
            [self._device()], ['SN-1'], lambda system, serial: {'battery': 77.0, 'cpu': 12.5})
        assert result['success'] is True
        health = [e for e in monitor.events if e['event_type'] == 'health_check']
        assert len(health) == 1
        assert health[0]['detail']['metrics'] == {'battery': 77.0, 'cpu': 12.5}
        assert health[0]['success'] is True
        m.assert_called_once()

    def test_nothing_collected_no_metrics_key(self):
        result, monitor, m = self._run([self._device()], ['SN-1'], lambda system, serial: {})
        health = [e for e in monitor.events if e['event_type'] == 'health_check'][0]
        assert 'metrics' not in health['detail'], health['detail']
        assert health['success'] is True

    def test_offline_device_not_collected(self):
        result, monitor, m = self._run([self._device()], [], lambda system, serial: {'cpu': 1.0})
        health = [e for e in monitor.events if e['event_type'] == 'health_check'][0]
        assert 'metrics' not in health['detail']
        assert health['success'] is False
        m.assert_not_called()

    def test_collector_exception_keeps_health_check_success(self):
        def _boom(system, serial):
            raise RuntimeError('adb missing')

        result, monitor, m = self._run([self._device()], ['SN-1'], _boom)
        health = [e for e in monitor.events if e['event_type'] == 'health_check'][0]
        assert health['success'] is True
        assert 'metrics' not in health['detail']
        assert result['success'] is True


# ==================== G. 网关 → gRPC → 仓储 全链路 ====================

@pytest.fixture(scope='module')
def chain_env():
    """sqlite 造数 + 真 grpc.server 上的 DeviceConfigServiceServicer。"""
    from concurrent.futures import ThreadPoolExecutor

    import grpc
    from shared.models import database
    from shared.proto import device_service_pb2_grpc as pb_grpc
    from device_service.infrastructure.persistence.models import Device, DeviceStatusEvent
    from device_service.interfaces.grpc.device_config_servicers import (
        DeviceConfigServiceServicer,
    )

    database.init_db()
    engine = database.get_engine()
    database.Base.metadata.create_all(
        bind=engine, tables=[Device.__table__, DeviceStatusEvent.__table__])

    ids = [810001, 810002]
    session = database.get_db_session()
    session.query(DeviceStatusEvent).filter(DeviceStatusEvent.device_id.in_(ids)).delete(
        synchronize_session=False)
    session.query(Device).filter(Device.id.in_(ids)).delete(synchronize_session=False)
    session.add_all([
        Device(id=810001, name='INT1578链路A', model='M', type='phone', system='Android',
               system_version='14', app_name='a', app_version='1', serial_number='CHAIN-A',
               status='online', deleted=False),
        Device(id=810002, name='INT1578链路B', model='M', type='phone', system='HarmonyOS',
               system_version='4', app_name='a', app_version='1', serial_number='CHAIN-B',
               status='online', deleted=False),
    ])
    session.add_all([
        # A：区间前在线，当日 12:00 离线 → 当天 50%
        DeviceStatusEvent(id=820001, device_id=810001, event_type='online', to_status='online',
                          source='monitor', success=True, detail={},
                          created_at=datetime(2026, 10, 4, 9, 0)),
        DeviceStatusEvent(id=820002, device_id=810001, event_type='offline', to_status='offline',
                          source='monitor', success=False, detail={},
                          created_at=datetime(2026, 10, 5, 12, 0)),
        # B：全天在线（基线在区间前）→ 100%，与 A 平均 75.0
        DeviceStatusEvent(id=820003, device_id=810002, event_type='online', to_status='online',
                          source='monitor', success=True, detail={},
                          created_at=datetime(2026, 10, 4, 9, 0)),
        DeviceStatusEvent(id=820004, device_id=810001, event_type='operation', to_status='online',
                          source='auto_test', success=True,
                          detail={'operation': 'test'}, created_at=datetime(2026, 10, 5, 10, 0)),
        DeviceStatusEvent(id=820005, device_id=810002, event_type='health_check',
                          to_status='online', source='health_check', success=False,
                          detail={'serial_number': 'CHAIN-B'}, created_at=datetime(2026, 10, 5, 11, 0)),
        DeviceStatusEvent(id=820006, device_id=810001, event_type='health_check',
                          to_status='online', source='health_check', success=True,
                          detail={'serial_number': 'CHAIN-A',
                                  'metrics': {'cpu': 20.0, 'memory': 40.0, 'battery': 60.0}},
                          created_at=datetime(2026, 10, 5, 8, 0)),
        DeviceStatusEvent(id=820007, device_id=810001, event_type='health_check',
                          to_status='online', source='health_check', success=True,
                          detail={'serial_number': 'CHAIN-A',
                                  'metrics': {'cpu': 40.0, 'battery': 80.0}},
                          created_at=datetime(2026, 10, 5, 9, 0)),
    ])
    session.commit()

    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_DeviceConfigServiceServicer_to_server(DeviceConfigServiceServicer(), server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')

    yield {'stub': pb_grpc.DeviceConfigServiceStub(channel), 'ids': ids,
           'session': session}

    server.stop(grace=None)
    session.query(DeviceStatusEvent).filter(DeviceStatusEvent.device_id.in_(ids)).delete(
        synchronize_session=False)
    session.query(Device).filter(Device.id.in_(ids)).delete(synchronize_session=False)
    session.commit()
    database.remove_db_session()


@pytest.fixture
def chain_client(chain_env):
    from unittest.mock import patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_gateway.routes.device_bp import router

    app = FastAPI()

    @app.middleware('http')
    async def _inject(request, call_next):
        request.state.permissions = ['*']
        request.state.user_id = 1
        return await call_next(request)

    app.include_router(router, prefix='/api/v1/test-devices')
    with patch(
        'api_gateway.infrastructure.grpc_proxies.device_proxies.get_device_config_service_stub',
        return_value=chain_env['stub'],
    ):
        yield TestClient(app)


class TestGatewayGrpcChain:
    def test_monitor_stats_through_real_grpc(self, chain_client, chain_env):
        r = chain_client.get(URL, params={
            'start_date': '2026-10-05', 'end_date': '2026-10-06',
            'device_ids': ','.join(str(i) for i in chain_env['ids'])})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['success'] is True
        data = body['data']
        assert data['granularity'] == 'day'
        assert data['start_date'] == '2026-10-05' and data['end_date'] == '2026-10-06'
        assert data['device_count'] == 2
        assert len(data['points']) == 2

        day1, day2 = data['points']
        assert day1['date'] == '2026-10-05'
        assert day1['availability'] == 75.0, day1
        assert day1['cpu'] == 30.0 and day1['memory'] == 40.0 and day1['battery'] == 70.0
        # errors = health_check 失败(1)；offline 状态事件虽 success=False 但按契约 §1.2
        # 括号口径（health_check 失败 + operation 失败）不计入
        assert day1['errors'] == 1, day1
        assert day1['operations'] == 1
        assert day1['health_check_samples'] == 3
        # 第二天区间内无事件：指标/计数为 0 与 null；availability 仍按契约 §1.2 重放
        # （A 自 10-05 12:00 起离线=0%，B 全天在线=100% → 平均 50.0）
        assert day2['date'] == '2026-10-06'
        assert day2['availability'] == 50.0, day2
        assert day2['cpu'] is None and day2['memory'] is None and day2['battery'] is None
        assert day2['errors'] == 0 and day2['operations'] == 0

    def test_lab_and_granularity_filters_passed_through(self, chain_client):
        r = chain_client.get(URL, params={
            'start_date': '2026-10-05', 'end_date': '2026-10-05', 'lab_id': 999999})
        assert r.status_code == 200, r.text
        assert r.json()['data']['device_count'] == 0

    def test_status_history_regression(self, chain_client):
        """回归：状态历史端点行为不变（仍返回分页事件列表）。"""
        r = chain_client.get('/api/v1/test-devices/status-history')
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['success'] is True
        assert 'items' in body['data'] and 'total' in body['data']


# ==================== H. 告警评估回归 ====================

class TestAlarmEvaluationRegression:
    def _rule(self, metric):
        return {'id': 1, 'metric_type': metric, 'threshold_value': 90.0, 'severity': 'warning'}

    def test_cpu_metric_read_from_detail_metrics(self):
        from device_service.application.services.device_monitor_service import DeviceMonitorService
        snapshots = {'latest_health': {1: {'metrics': {'cpu': 42.0}}}}
        value, ctx = DeviceMonitorService()._collect_metric(
            self._rule('cpu'), {'id': 1}, snapshots)
        assert value == 42.0 and ctx is None

    def test_no_metrics_means_no_evaluation(self):
        from device_service.application.services.device_monitor_service import DeviceMonitorService
        snapshots = {'latest_health': {1: {'serial_number': 'X'}}}
        value, _ = DeviceMonitorService()._collect_metric(
            self._rule('cpu'), {'id': 1}, snapshots)
        assert value is None

    def test_monitor_thread_uses_health_check(self):
        """监控线程与手动检查共用 health_check（采集单点实现）。"""
        import inspect
        from device_service.application.services.device_monitor_service import DeviceMonitorThread
        source = inspect.getsource(DeviceMonitorThread._loop)
        assert 'health_check' in source
