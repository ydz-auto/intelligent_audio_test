# -*- coding: utf-8 -*-
"""INT-1677 专项：播放设备控制事件与测试设备共用 device_status_events.device_id 的隔离。

修法 A（写入侧打标 + 读侧排除）：

1. 写入侧（A）：restart / reset-config / repair(re-enumerate) 落的 operation 事件
   ``source='playback_operation'``，``event_type`` 仍为 operation，``detail.operation`` 不变。
2. 读侧（B）：测试设备口径的四个读路径统一排除该 source ——
   监控统计按日聚合、可用率重放（区间状态支 + 基线支）、状态历史（全局 / 单设备共用）、
   告警侧 ``count_health_check_failures_batch`` / ``get_last_online_events``。
3. 排除谓词对 ``source IS NULL`` 宽容：历史 NULL 行仍计入测试设备统计。
4. 排除集合只写一处、引用枚举，device_service 业务代码不留新字面量。

读侧用例走隔离库（pytest 会话级临时 sqlite，见 tests/conftest.py），不触主库。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import types  # noqa: E402
from datetime import date, datetime  # noqa: E402

import pytest  # noqa: E402

from shared.models.common_enums import (  # noqa: E402
    DeviceStatusEventSource,
    DeviceStatusEventType,
    PlaybackControlAction,
    PlaybackRepairAction,
)
from device_service.application.commands.playback_command_service import (  # noqa: E402
    PlaybackCommandService,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PLAYBACK_SOURCE = DeviceStatusEventSource.PLAYBACK_OPERATION.value

# ==================== A. 写入侧：控制动作打标 ====================

PLAYBACK_DEVICE_ID = 930001
UNIQUE_ID = 'Speakers (RME Fireface 802) [Ch 1]'
PHYSICAL_DEVICES = [
    {'unique_id': UNIQUE_ID, 'device_index': 0, 'channel_index': 0,
     'sample_rate': 44100, 'host_api': 'Windows WASAPI'},
]


class _FakePlaybackRepo:
    def __init__(self, device):
        self.device = device
        self.updates = []

    def get_playback_device(self, device_id):
        return self.device if self.device and self.device.id == device_id else None

    def update_playback_device(self, device_id, update_fields):
        self.updates.append(dict(update_fields))
        for key, value in update_fields.items():
            setattr(self.device, key, value)
        return self.device


class _EventSink:
    def __init__(self):
        self.events = []

    def record_status_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


def _make_playback_device(**overrides):
    data = dict(
        id=PLAYBACK_DEVICE_ID, name='接线测试_播放设备', device_type='dry',
        device_unique_id=UNIQUE_ID, channel_index=0, sample_rate=48000,
        status='online', current_spl_mapping_id=5,
    )
    data.update(overrides)
    return types.SimpleNamespace(**data)


def _patch_world(monkeypatch):
    monkeypatch.setattr(PlaybackCommandService, '_get_device_index_via_grpc',
                        staticmethod(lambda unique_id: 0))
    monkeypatch.setattr(PlaybackCommandService, '_stop_audio_via_grpc',
                        staticmethod(lambda task_id: True))

    import device_service.infrastructure.acl.audio_service_acl_repository as acl_module
    monkeypatch.setattr(acl_module.audio_service_acl_repository, 'enumerate_physical_devices',
                        lambda: (list(PHYSICAL_DEVICES), True))

    import device_service.infrastructure.acl.task_acl_repository as task_acl_module
    monkeypatch.setattr(task_acl_module.task_acl_repository, 'has_running_e2e_tasks',
                        lambda: False)

    sink = _EventSink()
    import device_service.application.services.device_monitor_service as monitor_module
    monkeypatch.setattr(monitor_module.device_monitor_service, 'record_status_event',
                        sink.record_status_event)
    return sink


def _run_control(monkeypatch, action):
    sink = _patch_world(monkeypatch)
    service = PlaybackCommandService(repo=_FakePlaybackRepo(_make_playback_device()),
                                     spl_repo=None)
    if action == PlaybackControlAction.RESTART.value:
        result = service.restart(PLAYBACK_DEVICE_ID)
    elif action == PlaybackControlAction.RESET_CONFIG.value:
        result = service.reset_config(PLAYBACK_DEVICE_ID)
    else:
        result = service.repair(
            PLAYBACK_DEVICE_ID, {'actions': [PlaybackRepairAction.RE_ENUMERATE.value]})
    return result, sink


@pytest.mark.parametrize('action', [
    PlaybackControlAction.RESTART.value,
    PlaybackControlAction.RESET_CONFIG.value,
    PlaybackRepairAction.RE_ENUMERATE.value,
])
def test_control_action_writes_playback_operation_source(monkeypatch, action):
    """三个控制动作各落一条事件：source=playback_operation，类型与 detail 口径不变。"""
    result, sink = _run_control(monkeypatch, action)

    assert result['code'] == 200, result
    assert len(sink.events) == 1, sink.events
    event = sink.events[0]
    assert event['device_id'] == PLAYBACK_DEVICE_ID
    assert event['source'] == PLAYBACK_SOURCE
    assert event['event_type'] == DeviceStatusEventType.OPERATION.value
    assert event['detail']['operation'] == action


def test_repository_default_source_stays_monitor():
    """回归：仓储默认 source 仍是 monitor（本卡只改播放写入点，不顺手重构）。"""
    from device_service.infrastructure.persistence.device_monitor_repository import (
        DeviceMonitorRepository,
    )

    class _Session:
        def __init__(self):
            self.added = []

        def add(self, po):
            self.added.append(po)

        def commit(self):
            pass

    session = _Session()
    from unittest.mock import patch
    with patch(
        'device_service.infrastructure.persistence.device_monitor_repository.get_db_session',
        return_value=session,
    ):
        DeviceMonitorRepository().record_status_event({
            'device_id': 1, 'event_type': 'online', 'to_status': 'online'})

    assert session.added[0].source == DeviceStatusEventSource.MONITOR.value


# ==================== B. 读侧：隔离库构造撞号事件 ====================

DUP_DEVICE_ID = 930011       # 测试设备与播放设备撞号
AVAIL_DEVICE_ID = 930012
ALERT_DEVICE_ID = 930013

DUP_DAY = date(2026, 10, 10)
OTHER_DAY = date(2026, 10, 11)


@pytest.fixture(scope='module')
def scope_db():
    """会话级临时 sqlite：只建 devices / device_status_events 两表。"""
    from shared.models import database
    from device_service.infrastructure.persistence.models import Device, DeviceStatusEvent

    database.init_db()
    engine = database.get_engine()
    database.Base.metadata.create_all(
        bind=engine, tables=[Device.__table__, DeviceStatusEvent.__table__])
    yield {'engine': engine, 'Device': Device, 'DeviceStatusEvent': DeviceStatusEvent}
    engine.dispose()
    database.remove_db_session()


@pytest.fixture
def scene(scope_db):
    """播种三台测试设备，用例结束按 id 清理（含事件）。"""
    from shared.models.database import get_db_session

    Device = scope_db['Device']
    DeviceStatusEvent = scope_db['DeviceStatusEvent']
    ids = [DUP_DEVICE_ID, AVAIL_DEVICE_ID, ALERT_DEVICE_ID]
    session = get_db_session()

    def _clear():
        session.query(DeviceStatusEvent).filter(
            DeviceStatusEvent.device_id.in_(ids)).delete(synchronize_session=False)
        session.query(Device).filter(Device.id.in_(ids)).delete(synchronize_session=False)
        session.commit()

    _clear()
    session.add_all([
        Device(id=dup_id, name=f'INT1677撞号{dup_id}', model='M', type='phone',
               system='Android', system_version='14', app_name='app', app_version='1',
               serial_number=f'INT1677-{dup_id}', status='online', deleted=False)
        for dup_id in ids
    ])
    session.commit()

    # sqlite 的 BIGINT 主键不自动递增（INTEGER PRIMARY KEY 才递增），显式给 id
    next_event_id = [940100]

    def _add(device_id, event_type, when, source, success=True,
             to_status=None, detail=None):
        next_event_id[0] += 1
        event = DeviceStatusEvent(
            id=next_event_id[0], device_id=device_id, event_type=event_type, source=source,
            success=success, to_status=to_status, detail=detail,
            created_at=when,
        )
        session.add(event)
        session.commit()
        return event.id

    def _set_source_null(event_id):
        """显式置 NULL（ORM 写入时 None 可能被列默认值兜底，这里走 UPDATE 确保是 SQL NULL）。"""
        session.query(DeviceStatusEvent).filter(
            DeviceStatusEvent.id == event_id).update(
            {DeviceStatusEvent.source: None}, synchronize_session=False)
        session.commit()

    try:
        yield {'session': session, 'add': _add, 'null_source': _set_source_null}
    finally:
        _clear()
        from shared.models.database import remove_db_session
        remove_db_session()


def _repo():
    from device_service.infrastructure.persistence.device_monitor_repository import (
        DeviceMonitorRepository,
    )
    return DeviceMonitorRepository()


def _points(device_id, day, now=datetime(2026, 12, 31, 23, 59, 59)):
    result = _repo().aggregate_daily_stats(
        device_ids=[device_id], start_date=day, end_date=day, now=now)
    assert result['device_count'] == 1, result
    return result['points'][0]


class TestMonitorStatsScope:
    def test_playback_operation_not_counted(self, scene):
        """operations 只数测试设备的 operation 事件；播放控制失败不计入 errors。"""
        scene['add'](DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 12, 0),
                     source=PLAYBACK_SOURCE, success=False,
                     to_status='online', detail={'operation': 'restart'})
        scene['add'](DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 13, 0),
                     source=DeviceStatusEventSource.OPERATION.value, success=True,
                     to_status='online', detail={'operation': 'reboot'})

        point = _points(DUP_DEVICE_ID, DUP_DAY)

        assert point['operations'] == 1, point
        assert point['errors'] == 0, point

    def test_test_device_operation_and_error_regression(self, scene):
        """不含播放事件时口径不变：operation 成功计 operations，失败计 errors。"""
        scene['add'](DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 12, 0),
                     source=DeviceStatusEventSource.OPERATION.value, success=True,
                     to_status='online', detail={'operation': 'connect'})
        scene['add'](DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 13, 0),
                     source=DeviceStatusEventSource.OPERATION.value, success=False,
                     to_status='online', detail={'operation': 'install_app'})

        point = _points(DUP_DEVICE_ID, DUP_DAY)

        assert point['operations'] == 1, point
        assert point['errors'] == 1, point

    def test_null_source_operation_still_counted(self, scene):
        """排除谓词对 source IS NULL 宽容：历史 NULL 行不得被静默漏统计。"""
        event_id = scene['add'](DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 12, 0),
                                source=DeviceStatusEventSource.MONITOR.value, success=True,
                                to_status='online', detail={'operation': 'reboot'})
        scene['null_source'](event_id)

        point = _points(DUP_DEVICE_ID, DUP_DAY)

        assert point['operations'] == 1, point

    def test_availability_ignores_playback_state_events(self, scene):
        """可用率重放的区间状态支与基线支都排除播放侧 online/offline。"""
        scene['add'](AVAIL_DEVICE_ID, 'online', datetime(2026, 10, 10, 22, 0),
                     source=DeviceStatusEventSource.MONITOR.value, to_status='online')
        scene['add'](AVAIL_DEVICE_ID, 'offline', datetime(2026, 10, 11, 12, 0),
                     source=DeviceStatusEventSource.MONITOR.value, success=False,
                     to_status='offline')

        before = _points(AVAIL_DEVICE_ID, OTHER_DAY)
        assert before['availability'] == 50.0, before

        # 区间前基线支：若未排除会成为新的日初状态（offline → 当日 0% 起算）
        scene['add'](AVAIL_DEVICE_ID, 'offline', datetime(2026, 10, 10, 23, 59),
                     source=PLAYBACK_SOURCE, success=False, to_status='offline')
        # 区间状态支：若未排除会把 06:00 起翻成 online（当日 25%）
        scene['add'](AVAIL_DEVICE_ID, 'online', datetime(2026, 10, 11, 6, 0),
                     source=PLAYBACK_SOURCE, to_status='online')

        after = _points(AVAIL_DEVICE_ID, OTHER_DAY)

        assert after['availability'] == before['availability'] == 50.0, after


class TestStatusHistoryScope:
    def test_list_status_events_excludes_playback_operation(self, scene):
        """单设备与全局两个端点共用 list_status_events，均不返回播放控制事件。"""
        test_event_id = scene['add'](
            DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 13, 0),
            source=DeviceStatusEventSource.OPERATION.value, success=True,
            to_status='online', detail={'operation': 'reboot'})
        global_before = _repo().list_status_events(page=1, per_page=500)['total']

        playback_event_id = scene['add'](
            DUP_DEVICE_ID, 'operation', datetime(2026, 10, 10, 14, 0),
            source=PLAYBACK_SOURCE, success=True,
            to_status='online', detail={'operation': 'restart'})

        global_after = _repo().list_status_events(page=1, per_page=500)
        assert global_after['total'] == global_before, '播放控制事件不得进入状态历史'
        assert playback_event_id not in [e['id'] for e in global_after['items']]
        assert all(e['source'] != PLAYBACK_SOURCE for e in global_after['items'])

        scoped = _repo().list_status_events(device_ids=[DUP_DEVICE_ID])
        assert scoped['total'] == 1, scoped
        assert [e['id'] for e in scoped['items']] == [test_event_id]


class TestAlertSideScope:
    def test_health_check_failures_ignore_playback_operation(self, scene):
        """防御性一致：播放侧不写 health_check，但同一谓词套上后不得串号。"""
        scene['add'](ALERT_DEVICE_ID, 'health_check', datetime(2026, 10, 10, 8, 0),
                     source=DeviceStatusEventSource.HEALTH_CHECK.value, success=True,
                     to_status='online', detail={'serial_number': 'INT1677-ALERT'})
        scene['add'](ALERT_DEVICE_ID, 'health_check', datetime(2026, 10, 10, 9, 0),
                     source=PLAYBACK_SOURCE, success=False, to_status='offline')

        counts = _repo().count_health_check_failures_batch([ALERT_DEVICE_ID])

        assert counts == {ALERT_DEVICE_ID: 0}, counts

    def test_last_online_events_ignore_playback_operation(self, scene):
        """防御性一致：播放侧不写 online/offline，仍按同一谓词取最后一次状态事件。"""
        scene['add'](ALERT_DEVICE_ID, 'online', datetime(2026, 10, 10, 8, 0),
                     source=DeviceStatusEventSource.MONITOR.value, to_status='online')
        scene['add'](ALERT_DEVICE_ID, 'offline', datetime(2026, 10, 10, 9, 0),
                     source=PLAYBACK_SOURCE, success=False, to_status='offline')

        latest = _repo().get_last_online_events([ALERT_DEVICE_ID])

        assert latest[ALERT_DEVICE_ID]['event_type'] == 'online', latest
        assert latest[ALERT_DEVICE_ID]['source'] == DeviceStatusEventSource.MONITOR.value


# ==================== C. 单一来源：枚举 + 无新字面量 ====================

def test_enum_and_exclusion_set_are_single_source():
    from device_service.infrastructure.persistence.device_monitor_repository import (
        _NON_TEST_DEVICE_EVENT_SOURCES,
    )

    assert {source.value for source in DeviceStatusEventSource} == {
        'monitor', 'manual', 'health_check', 'operation', 'playback_operation',
    }
    assert _NON_TEST_DEVICE_EVENT_SOURCES == frozenset({PLAYBACK_SOURCE})


def test_no_playback_operation_literal_in_device_service():
    """写入点与排除集合都引用枚举：业务代码不出现新的 'playback_operation' 字面量。"""
    hits = []
    for dirpath, _, filenames in os.walk(os.path.join(PROJECT_ROOT, 'device_service')):
        for name in filenames:
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as handle:
                for lineno, line in enumerate(handle, 1):
                    if "'playback_operation'" in line or '"playback_operation"' in line:
                        hits.append(f'{os.path.relpath(path, PROJECT_ROOT)}:{lineno}')
    assert hits == [], hits
