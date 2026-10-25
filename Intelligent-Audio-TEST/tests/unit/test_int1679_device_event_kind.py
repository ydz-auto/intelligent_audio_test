# -*- coding: utf-8 -*-
"""INT-1679 专项：device_status_events 设备类型列（device_kind=test/playback）。

背景：`devices` 与 `playback_devices` 的 id 各自自增、真实库已重叠；播放设备的
restart / reset-config / repair 控制事件与测试设备事件同表同 device_id，无类型列
时查询侧无法区分 → 串进同 id 测试设备的状态历史与监控统计（契约 §1.2 只统计
测试设备）。本模块锁住：

1. 写入侧：默认 `test`，播放设备控制事件显式 `playback`；
2. 查询侧：`list_status_events` / `aggregate_daily_stats` / 告警三项
   （连续健康检查失败 / 离线时长 / 指标详情）在 id 重叠时只读 `test` 事件；
3. `_event_to_dict` 输出 `device_kind`；
4. 迁移回填判定（纯函数）与脚本/引导链的幂等要素。
"""
import importlib.util
import os
import re
from datetime import date, datetime

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.application.services.device_monitor_service import (  # noqa: E402
    DeviceMonitorService,
)
from device_service.infrastructure.persistence.device_monitor_repository import (  # noqa: E402
    DeviceMonitorRepository,
    _event_to_dict,
)
from shared.models.common_enums import DeviceKind  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MIGRATION_REL = 'scripts/migrations/202610/add_device_kind_int1679.py'
MIGRATION_PATH = os.path.join(PROJECT_ROOT, MIGRATION_REL)
BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')

# id 重叠场景：同一 device_id 同时存在 test 与 playback 事件
OVERLAP_A = 930001   # 有播放设备控制事件、也有测试设备事件
OVERLAP_B = 930002   # 只有测试设备事件（反向回归）
DAY = date(2026, 10, 24)


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def sqlite_env():
    """建 devices / device_status_events 两表（与 INT-1578 同口径的进程内 sqlite）。"""
    from shared.models import database
    from device_service.infrastructure.persistence.models import Device, DeviceStatusEvent

    database.init_db()
    engine = database.get_engine()
    database.Base.metadata.create_all(
        bind=engine, tables=[Device.__table__, DeviceStatusEvent.__table__])
    yield engine, Device, DeviceStatusEvent
    database.remove_db_session()


@pytest.fixture
def overlap_data(sqlite_env):
    """同一批 id 上构造 test / playback 两类事件，覆盖 6 处读取过滤。"""
    from shared.models.database import get_db_session

    _engine, Device, DeviceStatusEvent = sqlite_env
    session = get_db_session()
    session.add_all([
        Device(id=OVERLAP_A, name='INT1679重叠A', model='M', type='phone',
               system='Android', system_version='14', app_name='app',
               app_version='1', serial_number='INT1679-A', status='online',
               deleted=False),
        Device(id=OVERLAP_B, name='INT1679重叠B', model='M', type='phone',
               system='Android', system_version='14', app_name='app',
               app_version='1', serial_number='INT1679-B', status='online',
               deleted=False),
    ])
    session.add_all([
        # ── 播放设备控制事件（device_kind=playback，设备 id 与测试设备重叠）──
        DeviceStatusEvent(id=940001, device_id=OVERLAP_A, device_kind=DeviceKind.PLAYBACK.value,
                          event_type='operation', source='operation', success=True,
                          detail={'operation': 'restart'},
                          created_at=datetime(2026, 10, 24, 10, 0)),
        DeviceStatusEvent(id=940002, device_id=OVERLAP_A, device_kind=DeviceKind.PLAYBACK.value,
                          event_type='operation', source='operation', success=False,
                          detail={'operation': 'reset-config'},
                          created_at=datetime(2026, 10, 24, 11, 0)),
        DeviceStatusEvent(id=940006, device_id=OVERLAP_A, device_kind=DeviceKind.PLAYBACK.value,
                          event_type='online', to_status='online', source='monitor',
                          success=True, created_at=datetime(2026, 10, 24, 9, 0)),
        # 播放设备侧更新的一条 health_check（latest 判定必须忽略它）
        DeviceStatusEvent(id=940003, device_id=OVERLAP_A, device_kind=DeviceKind.PLAYBACK.value,
                          event_type='health_check', source='health_check', success=False,
                          detail={'metrics': {'cpu': 99, 'memory': 99, 'battery': 1}},
                          created_at=datetime(2026, 10, 24, 14, 30)),
        # ── 测试设备事件（device_kind=test）──
        DeviceStatusEvent(id=940004, device_id=OVERLAP_A, device_kind=DeviceKind.TEST.value,
                          event_type='health_check', source='health_check', success=True,
                          detail={'metrics': {'cpu': 10, 'memory': 20, 'battery': 80}},
                          created_at=datetime(2026, 10, 24, 13, 0)),
        DeviceStatusEvent(id=940008, device_id=OVERLAP_A, device_kind=DeviceKind.TEST.value,
                          event_type='operation', source='operation', success=True,
                          detail={'operation': 'reboot'},
                          created_at=datetime(2026, 10, 24, 14, 0)),
        DeviceStatusEvent(id=940005, device_id=OVERLAP_B, device_kind=DeviceKind.TEST.value,
                          event_type='operation', source='operation', success=True,
                          detail={'operation': 'connect'},
                          created_at=datetime(2026, 10, 24, 10, 30)),
        DeviceStatusEvent(id=940007, device_id=OVERLAP_B, device_kind=DeviceKind.TEST.value,
                          event_type='online', to_status='online', source='monitor',
                          success=True, created_at=datetime(2026, 10, 24, 9, 30)),
    ])
    session.commit()
    yield session
    session.rollback()
    session.query(DeviceStatusEvent).filter(
        DeviceStatusEvent.id.in_([940001, 940002, 940003, 940004,
                                  940005, 940006, 940007, 940008])).delete(
        synchronize_session=False)
    session.query(Device).filter(Device.id.in_([OVERLAP_A, OVERLAP_B])).delete(
        synchronize_session=False)
    session.commit()


# ==================== 1. 写入侧 ====================

class _RecordingRepo:
    """替身仓储：记录应用层透传的 data dict（写入侧契约只看透传值）。"""

    def __init__(self):
        self.calls = []

    def record_status_event(self, data):
        self.calls.append(dict(data))
        return {'id': len(self.calls), **data, 'created_at': None}


class _RecordingSession:
    """替身会话：捕获 add 的 PO（sqlite 的 BIGSERIAL PK 不自增，不落真库）。"""

    def __init__(self):
        self.added = []

    def add(self, po):
        self.added.append(po)

    def commit(self):
        pass


class TestWriteSide:
    DEVICE_ID = 931001

    def _service(self, repo):
        service = DeviceMonitorService(monitor_repo=repo)
        return service

    def test_default_kind_is_test(self):
        repo = _RecordingRepo()
        self._service(repo).record_status_event(
            device_id=self.DEVICE_ID, event_type='online',
            to_status='online', source='health_check', success=True)
        assert repo.calls[0]['device_kind'] == DeviceKind.TEST.value

    def test_playback_kind_written_explicitly(self):
        repo = _RecordingRepo()
        self._service(repo).record_status_event(
            device_id=self.DEVICE_ID, event_type='operation',
            source='operation', success=True,
            detail={'operation': 'restart'},
            device_kind=DeviceKind.PLAYBACK.value)
        assert repo.calls[0]['device_kind'] == DeviceKind.PLAYBACK.value

    def test_repository_defaults_absent_kind_to_test(self, monkeypatch):
        """仓储层兜底：data 没带 device_kind 也落 test（其余写入腿不传即默认）。"""
        import device_service.infrastructure.persistence.device_monitor_repository as repo_module

        session = _RecordingSession()
        monkeypatch.setattr(repo_module, 'get_db_session', lambda: session)
        event = repo_module.DeviceMonitorRepository().record_status_event({
            'device_id': self.DEVICE_ID, 'event_type': 'online',
            'source': 'monitor', 'success': True,
        })
        assert session.added[0].device_kind == DeviceKind.TEST.value
        assert event['device_kind'] == DeviceKind.TEST.value

    def test_repository_persists_explicit_playback(self, monkeypatch):
        import device_service.infrastructure.persistence.device_monitor_repository as repo_module

        session = _RecordingSession()
        monkeypatch.setattr(repo_module, 'get_db_session', lambda: session)
        event = repo_module.DeviceMonitorRepository().record_status_event({
            'device_id': self.DEVICE_ID, 'event_type': 'operation',
            'source': 'operation', 'success': True,
            'device_kind': DeviceKind.PLAYBACK.value,
        })
        assert session.added[0].device_kind == DeviceKind.PLAYBACK.value
        assert event['device_kind'] == DeviceKind.PLAYBACK.value

    def test_event_to_dict_carries_device_kind(self):
        """_event_to_dict 输出 device_kind（排查 / 后续播放设备历史复用）。"""
        from types import SimpleNamespace
        po = SimpleNamespace(
            id=1, device_id=OVERLAP_A, device_kind=DeviceKind.PLAYBACK.value,
            event_type='operation', from_status='online', to_status='online',
            source='operation', success=True, detail={'operation': 'restart'},
            created_at=None)
        assert _event_to_dict(po)['device_kind'] == DeviceKind.PLAYBACK.value


# ==================== 2. 查询侧 ====================

class TestQuerySide:
    def test_list_status_events_only_returns_test_kind(self, overlap_data):
        repo = DeviceMonitorRepository()
        result = repo.list_status_events(device_ids=[OVERLAP_A], per_page=50)

        ids = sorted(item['id'] for item in result['items'])
        assert ids == [940004, 940008], '播放设备事件不得进入测试设备状态历史'
        assert result['total'] == 2
        assert {item['device_kind'] for item in result['items']} == {DeviceKind.TEST.value}

    def test_aggregate_daily_stats_excludes_playback_events(self, overlap_data):
        repo = DeviceMonitorRepository()
        result = repo.aggregate_daily_stats(
            device_ids=[OVERLAP_A, OVERLAP_B], start_date=DAY, end_date=DAY,
            now=datetime(2026, 10, 24, 23, 59))

        point = result['points'][0]
        assert result['device_count'] == 2
        # operations 只计两条 test operation（940008 + 940005），播放设备 restart 不计
        assert point['operations'] == 2
        # errors：播放设备的 operation 失败与 health_check 失败都不计
        assert point['errors'] == 0
        # health_check_samples：只计 test 的 940004（播放设备 940003 不计）
        assert point['health_check_samples'] == 1
        # cpu 均值只来自 test 事件：播放设备那条 cpu=99 不得拉高均值
        assert point['cpu'] == 10.0

    def test_alert_reads_ignore_playback_events(self, overlap_data):
        repo = DeviceMonitorRepository()

        # 连续健康检查失败：播放设备 940003(success=False) 是 (device, 时间) 上最新的一条，
        # 过滤后该设备只有 test 的一条成功采样 → 0 次连续失败
        assert repo.count_health_check_failures_batch([OVERLAP_A]) == {OVERLAP_A: 0}
        assert repo.count_health_check_failures_batch([OVERLAP_B]) == {OVERLAP_B: 0}

        # 离线时长基线：OVERLAP_A 只有播放设备的 online 事件 → 无基线
        assert repo.get_last_online_events([OVERLAP_A]) == {}
        assert repo.get_last_online_events([OVERLAP_B])[OVERLAP_B]['id'] == 940007

        # 指标详情：OVERLAP_A 最新的 health_check 是播放设备的 cpu=99，必须忽略
        details = repo.get_latest_health_details([OVERLAP_A])
        assert details[OVERLAP_A]['metrics'] == {'cpu': 10, 'memory': 20, 'battery': 80}


# ==================== 3. 迁移回填判定与部署链 ====================

@pytest.fixture(scope='module')
def migration():
    """迁移脚本模块（回填判定纯函数 / DDL 常量）。"""
    return _load_module(MIGRATION_PATH, 'int1679_migration')


class TestMigration:
    @pytest.mark.parametrize('operation', ['restart', 'reset-config', 're-enumerate'])
    def test_backfill_recognizes_playback_control_operations(self, migration, operation):
        assert migration.is_playback_control_event({
            'source': 'operation', 'detail': {'operation': operation}}) is True

    @pytest.mark.parametrize('operation', ['connect', 'disconnect', 'reboot',
                                           'shutdown', 'install_app', 'uninstall_app'])
    def test_backfill_does_not_touch_test_device_operations(self, migration, operation):
        """测试设备 DeviceOperation 取值与三个播放动作无交集，不得被回填成 playback。"""
        assert migration.is_playback_control_event({
            'source': 'operation', 'detail': {'operation': operation}}) is False

    def test_backfill_ignores_non_operation_sources(self, migration):
        for source in ('monitor', 'health_check', 'manual', None):
            assert migration.is_playback_control_event({
                'source': source, 'detail': {'operation': 'restart'}}) is False
        assert migration.is_playback_control_event({
            'source': 'operation', 'detail': None}) is False

    def test_ddl_is_idempotent_not_null_default_test(self, migration):
        text = open(MIGRATION_PATH, encoding='utf-8').read()
        assert 'ADD COLUMN IF NOT EXISTS' in text
        assert re.search(r'VARCHAR\(20\)\s+NOT NULL\s+DEFAULT\s+\'test\'',
                         migration.COLUMN_DDL)
        # 不加索引：现有 (device_id, created_at) 已覆盖，kind 只是命中行上的布尔过滤
        assert 'CREATE INDEX' not in text
        # 默认 dry-run，--apply 才落 DDL
        assert "add_argument('--apply'" in text

    def test_backfill_sql_scoped_to_playback_actions(self, migration):
        """回填只把仍为 test 的播放控制动作改成 playback，不碰其他行。"""
        assert migration.BACKFILL_SQL.startswith('UPDATE device_status_events SET')
        assert "SET device_kind = 'playback'" in migration.BACKFILL_SQL
        assert "WHERE device_kind = 'test'" in migration.BACKFILL_SQL
        assert "source = 'operation'" in migration.BACKFILL_SQL
        for operation in ('restart', 'reset-config', 're-enumerate'):
            assert f"'{operation}'" in migration.BACKFILL_SQL

    def test_bootstrap_chain_applies_migration(self):
        """存量库靠 db_bootstrap 引导链自愈，且必须带 --apply（脚本默认 dry-run）。"""
        steps = [list(step) for step in
                 _load_module(BOOTSTRAP_PATH,
                              'int1679_db_bootstrap').BOOTSTRAP_STEPS]
        matches = [step for step in steps if MIGRATION_REL in step]
        assert matches, f'BOOTSTRAP_STEPS 未包含 {MIGRATION_REL}'
        assert any('--apply' in step for step in matches)
