# -*- coding: utf-8 -*-
"""INT-1812 审计日志读侧单测（INT-1793 契约 §Q2/§Q3/§Q4，卡片 2）。

覆盖：
- `AuditLogReader`：日期目录枚举与剪枝、默认 30 天窗口、逐行解析、条目 id = cursor、
  (time desc, cursor desc) 排序、扫描上界（触顶保最新 / total 下界）、3s TTL 缓存
  （同参共享一次扫描、TTL=0 关闭）、游标反查（日期目录 + 相邻日期兜底）
- 过滤语义对等：level 多值 / category / module('all') / keyword / content_include|
  exclude / algorithm_type / test_case_id / thread_id / device_id / api_id / task_id /
  user_id（「仅自己」）/ mark（文件侧恒空命中）/ 时间区间
- `GET /logs` 全局分支：审计文件 + logs 表历史行合并、内存分页、默认 30 天窗口
- `GET /logs/stats`：与列表同源同筛选（total 与列表一致）
- `POST /logs/refresh`：建基准 / 增量 ≤100 升序 / 两类越界 reset_required / 幂等
- `PUT /logs/mark`：文件游标 → 200 + 专用文案；legacy id 行为不变
- `POST /logs/export`：与列表同源（文件游标按日期目录反查，legacy id 走 DB）
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1812_reader_') + '/reader.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.logging.audit_reader import (  # noqa: E402
    CURSOR_FLOOR,
    AuditLogReader,
    cursor_to_date_seg,
)
from shared.logging.config import LogSettings  # noqa: E402
from shared.logging.enums import AUDIT_DIR, LogEnvironment  # noqa: E402

import shared.logging.audit_reader as audit_reader_module  # noqa: E402

_CST = timezone(timedelta(hours=8))


# =====================================================================
# 夹具
# =====================================================================

def _make_settings(root, **overrides):
    values = dict(
        root_dir=str(root),
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
        business_max_scan_entries=100_000,
        audit_enabled=True,
        audit_db_enabled=False,
        audit_max_bytes=50 * 1024 * 1024,
        audit_retention_days=30,
        audit_archive_enabled=True,
        audit_max_scan_entries=100_000,
        audit_query_default_days=30,
        audit_scan_cache_ttl_seconds=3,
        sweep_service='api_gateway',
        file_retention_days=30,
    )
    values.update(overrides)
    return LogSettings(**values)


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    """临时日志根 + 审计读侧配置快照（默认 TTL 3s）。"""
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    audit_reader_module._SCAN_CACHE.clear()
    yield root
    audit_reader_module._SCAN_CACHE.clear()
    from shared.logging.config import reset_log_settings
    reset_log_settings()


def _today() -> str:
    return datetime.now(_CST).strftime('%Y-%m-%d')


def _days_ago(days: int) -> str:
    return (datetime.now(_CST) - timedelta(days=days)).strftime('%Y-%m-%d')


def _record(cursor, time, **overrides):
    base = {
        'cursor': cursor,
        'time': time,
        'level': 'INFO',
        'category': 'auth',
        'module': 'auth_login',
        'source': 'api_gateway',
        'service': 'api_gateway',
        'event': 'AUTH_LOGIN',
        'operator_id': 1,
        'user_id': 1,
        'content': '{"event": "AUTH_LOGIN", "operator_id": 1}',
    }
    base.update(overrides)
    return base


def _write_audit(root, date_seg, records, *, category='auth',
                 service='api_gateway', identity='test-1', split=None):
    """写一个审计 JSONL 文件（split 给定时写切分文件 -NNN）。"""
    dir_path = os.path.join(root, AUDIT_DIR, date_seg)
    os.makedirs(dir_path, exist_ok=True)
    name = f'{category}.{service}.{identity}'
    if split:
        name = f'{name}-{split:03d}'
    path = os.path.join(dir_path, f'{name}.jsonl')
    with open(path, 'w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    return path


def _base_cursor(day: str, hour: int = 12) -> int:
    """某日 12:00 的 epoch 微秒游标（同日内按需 +N 递增）。"""
    moment = datetime.strptime(day, '%Y-%m-%d').replace(hour=hour, tzinfo=_CST)
    return int(moment.timestamp() * 1_000_000)


# =====================================================================
# 1. 日期目录枚举与剪枝
# =====================================================================

class TestDateDirEnumeration:
    def test_lists_only_existing_date_dirs(self, log_root):
        _write_audit(log_root, _days_ago(2), [_record(_base_cursor(_days_ago(2)),
                                                      f'{_days_ago(2)} 12:00:00.000000')])
        _write_audit(log_root, _days_ago(1), [_record(_base_cursor(_days_ago(1)),
                                                      f'{_days_ago(1)} 12:00:00.000000')])
        os.makedirs(os.path.join(log_root, AUDIT_DIR, 'not-a-date'), exist_ok=True)

        segs = AuditLogReader().list_date_segs(
            start_time=f'{_days_ago(5)} 00:00:00')
        assert segs == [_days_ago(2), _days_ago(1)]

    def test_default_window_drops_dirs_older_than_30_days(self, log_root):
        old = _days_ago(40)
        recent = _days_ago(1)
        _write_audit(log_root, old, [_record(_base_cursor(old), f'{old} 12:00:00.000000')])
        _write_audit(log_root, recent,
                     [_record(_base_cursor(recent), f'{recent} 12:00:00.000000')])

        reader = AuditLogReader()
        # 无时间筛选 → 默认近 30 天，40 天前的目录被日期剪枝掉
        assert reader.list_date_segs() == [recent]
        # 显式给时间窗时按窗口枚举（不做 30 天截断）
        assert reader.list_date_segs(start_time=f'{old} 00:00:00') == [old, recent]

    def test_explicit_window_bounds_both_ends(self, log_root):
        for offset in (1, 2, 3):
            day = _days_ago(offset)
            _write_audit(log_root, day,
                         [_record(_base_cursor(day), f'{day} 12:00:00.000000')])
        reader = AuditLogReader()
        segs = reader.list_date_segs(
            start_time=f'{_days_ago(3)} 00:00:00', end_time=f'{_days_ago(2)} 23:59:59')
        assert segs == [_days_ago(3), _days_ago(2)]


# =====================================================================
# 2. 条目映射与排序（id = cursor）
# =====================================================================

class TestEntryMapping:
    def test_item_id_is_cursor_and_mark_is_none(self, log_root):
        day = _days_ago(1)
        cursor = _base_cursor(day)
        _write_audit(log_root, day, [_record(cursor, f'{day} 12:00:00.000000')])

        items = AuditLogReader().read_entries(start_time=f'{day} 00:00:00')
        assert [item['id'] for item in items] == [cursor]
        assert items[0]['mark'] is None
        assert items[0]['level'] == 'INFO'
        assert items[0]['user_id'] == 1
        assert items[0]['service'] == 'api_gateway'

    def test_rows_without_cursor_are_skipped(self, log_root):
        day = _days_ago(1)
        records = [
            _record(_base_cursor(day), f'{day} 12:00:00.000000'),
            {'time': f'{day} 12:00:01.000000', 'level': 'INFO', 'content': 'no cursor'},
        ]
        _write_audit(log_root, day, records)
        items = AuditLogReader().read_entries(start_time=f'{day} 00:00:00')
        assert len(items) == 1

    def test_sort_is_time_desc_then_cursor_desc(self, log_root):
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base, f'{day} 12:00:00.000000', content='old'),
            _record(base + 2, f'{day} 12:00:02.000000', content='newest'),
            _record(base + 1, f'{day} 12:00:01.000000', content='middle'),
        ])
        items = AuditLogReader().read_entries(start_time=f'{day} 00:00:00')
        assert [item['content'] for item in items] == ['newest', 'middle', 'old']

    def test_split_files_scanned_newest_first(self, log_root):
        """活跃文件与切分文件都要读到（切分不是丢数据）。"""
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day,
                     [_record(base, f'{day} 12:00:00.000000', content='split')],
                     split=1)
        _write_audit(log_root, day,
                     [_record(base + 1, f'{day} 12:00:01.000000', content='active')])
        items = AuditLogReader().read_entries(start_time=f'{day} 00:00:00')
        assert [item['content'] for item in items] == ['active', 'split']


# =====================================================================
# 3. 过滤语义对等（与 DB 查询同口径）
# =====================================================================

class TestFilterParity:
    @pytest.fixture()
    def seeded(self, log_root):
        day = _days_ago(1)
        base = _base_cursor(day)
        records = [
            _record(base, f'{day} 12:00:00.000000', level='ERROR', module='publish',
                    category='system', content='publish failed', user_id=7,
                    device_id=3, api_id=11, task_id=42, test_case_id='TC-1',
                    thread_id='th-abc', algorithm_type='asr'),
            _record(base + 1, f'{day} 12:00:01.000000', level='INFO', module='auth_login',
                    category='auth', content='login ok', user_id=8),
            _record(base + 2, f'{day} 12:00:02.000000', level='WARNING',
                    module='visibility', category='visibility',
                    content='private access denied', user_id=7),
        ]
        _write_audit(log_root, day, records[1:], category='auth')
        _write_audit(log_root, day, records[:1], category='system')
        return {'root': log_root, 'day': day,
                'start': f'{day} 00:00:00', 'end': f'{day} 23:59:59'}

    def _read(self, seeded, **filters):
        reader = AuditLogReader()
        return reader.read_entries(start_time=seeded['start'], **filters)

    def test_level_multi_value(self, seeded):
        items = self._read(seeded, level='error,warning')
        assert {item['level'] for item in items} == {'ERROR', 'WARNING'}

    def test_category_and_module_all_normalization(self, seeded):
        assert len(self._read(seeded, category='auth')) == 1
        assert len(self._read(seeded, category='all')) == 3
        assert len(self._read(seeded, module='publish')) == 1
        assert len(self._read(seeded, module='all')) == 3

    def test_keyword_and_content_include_exclude(self, seeded):
        assert len(self._read(seeded, keyword='login')) == 1
        assert len(self._read(seeded, content_include='private')) == 1
        assert len(self._read(seeded, content_exclude='login')) == 2

    def test_user_id_only_self(self, seeded):
        items = self._read(seeded, user_id=7)
        assert len(items) == 2
        assert {item['user_id'] for item in items} == {7}

    def test_id_filters(self, seeded):
        assert len(self._read(seeded, device_id=3)) == 1
        assert len(self._read(seeded, api_id=11)) == 1
        assert len(self._read(seeded, task_id=42)) == 1
        assert len(self._read(seeded, test_case_id='TC-1')) == 1
        assert len(self._read(seeded, thread_id='abc')) == 1
        assert len(self._read(seeded, algorithm_type='asr')) == 1

    def test_mark_filter_never_matches_files(self, seeded):
        """契约 §Q3：文件日志不可标记，mark 筛选在文件侧恒空命中。"""
        assert self._read(seeded, mark='flagged') == []

    def test_time_window_excludes_out_of_range(self, seeded):
        items = AuditLogReader().read_entries(
            start_time=f'{seeded["day"]} 12:00:01',
            end_time=f'{seeded["day"]} 12:00:01.999999')
        assert [item['content'] for item in items] == ['login ok']


# =====================================================================
# 4. 扫描上界（total 下界，保留最新）
# =====================================================================

class TestScanCap:
    def test_cap_keeps_newest_and_flags_truncated(self, tmp_path, monkeypatch):
        root = str(tmp_path / 'logs')
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(root, audit_max_scan_entries=3))
        audit_reader_module._SCAN_CACHE.clear()
        try:
            day = _days_ago(1)
            base = _base_cursor(day)
            _write_audit(root, day, [
                _record(base + i, f'{day} 12:00:{i:02d}.000000', content=f'c{i}')
                for i in range(10)
            ])
            result = AuditLogReader().read_page(
                page=1, per_page=0, start_time=f'{day} 00:00:00')
            assert result['truncated'] is True
            assert result['total'] == 3
            # 触顶保留最新：c9 / c8 / c7
            assert [item['content'] for item in result['items']] == ['c9', 'c8', 'c7']
        finally:
            audit_reader_module._SCAN_CACHE.clear()
            from shared.logging.config import reset_log_settings
            reset_log_settings()


# =====================================================================
# 5. 同参 TTL 缓存（列表 / 统计共享一次扫描）
# =====================================================================

class TestScanCache:
    def _counting_reader(self, monkeypatch):
        counter = {'n': 0}
        original = AuditLogReader._parse_file

        def _counted(path):
            counter['n'] += 1
            return original(path)

        monkeypatch.setattr(AuditLogReader, '_parse_file', staticmethod(_counted))
        return counter

    def test_second_query_with_same_filters_reuses_scan(self, log_root, monkeypatch):
        day = _days_ago(1)
        _write_audit(log_root, day, [
            _record(_base_cursor(day), f'{day} 12:00:00.000000'),
            _record(_base_cursor(day) + 1, f'{day} 12:00:01.000000'),
        ])
        counter = self._counting_reader(monkeypatch)
        reader = AuditLogReader()
        filters = {'start_time': f'{day} 00:00:00'}

        first = reader.read_page(page=1, per_page=0, **filters)
        scans_after_first = counter['n']
        second = reader.read_page(page=1, per_page=0, **filters)

        assert counter['n'] == scans_after_first, 'TTL 内同参查询不应二次扫描'
        assert [item['id'] for item in second['items']] == \
            [item['id'] for item in first['items']]

    def test_ttl_zero_disables_cache(self, tmp_path, monkeypatch):
        root = str(tmp_path / 'logs')
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(root, audit_scan_cache_ttl_seconds=0))
        audit_reader_module._SCAN_CACHE.clear()
        try:
            day = _days_ago(1)
            _write_audit(root, day, [
                _record(_base_cursor(day), f'{day} 12:00:00.000000')])
            counter = self._counting_reader(monkeypatch)
            reader = AuditLogReader()
            reader.read_entries(start_time=f'{day} 00:00:00')
            first = counter['n']
            reader.read_entries(start_time=f'{day} 00:00:00')
            assert counter['n'] == first * 2
        finally:
            audit_reader_module._SCAN_CACHE.clear()
            from shared.logging.config import reset_log_settings
            reset_log_settings()


# =====================================================================
# 6. 增量游标（契约 §Q4）
# =====================================================================

class TestCursorDomain:
    def test_cursor_floor_separates_id_spaces(self):
        assert CURSOR_FLOOR == 10 ** 12
        # legacy logs 表实测 max id 远小于下限；epoch 微秒在 2026 年远大于下限
        assert CURSOR_FLOOR > 6_949_425
        assert _base_cursor('2026-10-24') > CURSOR_FLOOR
        assert _base_cursor('2026-10-24') < 2 ** 53

    def test_max_cursor_returns_latest_event(self, log_root):
        old_day, new_day = _days_ago(2), _days_ago(1)
        _write_audit(log_root, old_day,
                     [_record(_base_cursor(old_day), f'{old_day} 12:00:00.000000')])
        latest = _base_cursor(new_day) + 5
        _write_audit(log_root, new_day,
                     [_record(latest, f'{new_day} 12:00:05.000000')])
        assert AuditLogReader().max_cursor() == latest

    def test_max_cursor_is_zero_without_files(self, log_root):
        assert AuditLogReader().max_cursor() == 0

    def test_read_after_cursor_is_ascending_and_limited(self, log_root):
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base + i, f'{day} 12:00:{i:02d}.000000', content=f'c{i}')
            for i in range(150)
        ])
        reader = AuditLogReader()
        first = reader.read_after_cursor(base, limit=100)
        assert len(first) == 100
        assert [item['id'] for item in first] == sorted(item['id'] for item in first)
        assert first[0]['id'] == base + 1

        second = reader.read_after_cursor(first[-1]['id'], limit=100)
        assert len(second) == 49          # base+1..base+149 共 149 条，后 49 条
        assert second[0]['id'] == first[-1]['id'] + 1

    def test_read_after_cursor_is_idempotent(self, log_root):
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [_record(base + 1, f'{day} 12:00:01.000000')])
        reader = AuditLogReader()
        first = reader.read_after_cursor(base, limit=100)
        again = reader.read_after_cursor(base, limit=100)
        assert [i['id'] for i in first] == [i['id'] for i in again] == [base + 1]
        # 拉到末条后再拉同一个 last_id → 空
        assert reader.read_after_cursor(base + 1, limit=100) == []

    def test_read_by_cursors_reverse_lookup(self, log_root):
        older, newer = _days_ago(2), _days_ago(1)
        c1 = _base_cursor(older) + 9
        c2 = _base_cursor(newer) + 9
        _write_audit(log_root, older,
                     [_record(c1, f'{older} 12:00:09.000000', content='old')])
        _write_audit(log_root, newer,
                     [_record(c2, f'{newer} 12:00:09.000000', content='new')])
        items = AuditLogReader().read_by_cursors([c1, c2, 12345])
        assert [item['content'] for item in items] == ['new', 'old']

    def test_read_by_cursors_falls_back_to_neighbour_date(self, log_root):
        """同微秒 +1 可能把游标推过日期边界：相邻日期兜底仍能命中。"""
        day = _days_ago(1)
        next_day = (datetime.strptime(day, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        cursor = _base_cursor(next_day) + 1          # 游标落在下一天
        _write_audit(log_root, day,
                     [_record(cursor, f'{day} 23:59:59.999999', content='edge')])
        items = AuditLogReader().read_by_cursors([cursor])
        assert [item['content'] for item in items] == ['edge']

    def test_cursor_to_date_seg_matches_writer_layout(self):
        day = '2026-10-24'
        assert cursor_to_date_seg(_base_cursor(day)) == day


# =====================================================================
# 7. 网关服务层：GET /logs 全局合并视图
# =====================================================================

class _FakeProxy:
    """task_data_service 假实现（记录参数，返回预设数据）。"""

    def __init__(self):
        self.list_logs_kwargs = []
        self.items = []
        self.total = 0
        self.stats = {'total': 0, 'debug': 0, 'info': 0, 'warning': 0,
                      'error': 0, 'critical': 0}
        self.stats_kwargs = None
        self.export_args = None
        self.export_items = []
        self.mark_args = None
        self.updated = 0

    def list_logs(self, **kwargs):
        self.list_logs_kwargs.append(kwargs)
        return {'items': list(self.items), 'total': self.total}

    def get_log_stats(self, **kwargs):
        self.stats_kwargs = kwargs
        return dict(self.stats)

    def get_logs_for_export(self, log_ids=None, level=None, module=None):
        self.export_args = (log_ids, level, module)
        return {'items': list(self.export_items)}

    def update_logs_mark(self, log_ids, mark):
        self.mark_args = (list(log_ids), mark)
        return {'updated': self.updated}


@pytest.fixture()
def fake_proxy(monkeypatch):
    proxy = _FakeProxy()
    monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                        proxy)
    yield proxy


def _set_request(body=None, query=None, user_id=0):
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(SimpleNamespace(
        state=SimpleNamespace(_json_body=body, user_id=user_id),
        query_params=query or {},
        method='POST',
    ))


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(None)


class TestGlobalListMerge:
    def test_merges_audit_files_and_db_history(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base, f'{day} 12:00:00.000000', content='file row'),
        ])
        fake_proxy.items = [{
            'id': 88, 'time': f'{day}T12:00:05', 'level': 'ERROR', 'category': 'auth',
            'module': 'auth_login', 'source': 'db', 'content': 'db row',
            'created_by_user_id': 7,
        }]
        fake_proxy.total = 1
        _set_request({}, {'page': '1', 'per_page': '50'})

        body, _code = LogQueryService.get_logs()
        data = body['data']
        assert [item['content'] for item in data['items']] == ['db row', 'file row']
        assert data['total'] == 2
        # 文件条目 id = cursor，DB 行仍是自增 id（两个 id 空间并存）
        assert data['items'][1]['id'] == base
        assert data['items'][0]['id'] == 88
        assert data['items'][1]['user_id'] == 1

    def test_merged_order_ignores_time_string_format(self, log_root, fake_proxy):
        """文件 'YYYY-MM-DD HH:MM:SS.ffffff' 与 DB ISO 'T' 混排按真实时间排序。

        按字符串比较会让同日 'T' 分隔的 DB 行整体排到文件行之前（'T' > ' '），
        故合并键必须解析成 epoch（INT-1812 实测发现）。
        """
        from api_gateway.application.services.log.log_query_service import LogQueryService

        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base, f'{day} 12:00:30.000000', content='file newer')])
        fake_proxy.items = [{
            'id': 5, 'time': f'{day}T12:00:10', 'level': 'INFO', 'category': 'auth',
            'module': 'm', 'source': 'db', 'content': 'db older',
        }]
        fake_proxy.total = 1
        _set_request({}, {'page': '1', 'per_page': '10'})

        body, _code = LogQueryService.get_logs()
        assert [item['content'] for item in body['data']['items']] == \
            ['file newer', 'db older']

    def test_defaults_to_recent_30_days_window(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        _set_request({}, {'page': '1', 'per_page': '20'})
        LogQueryService.get_logs()
        kwargs = fake_proxy.list_logs_kwargs[0]
        assert kwargs['start_date'], '无时间筛选时必须下发默认窗口起点'
        parsed = datetime.fromisoformat(kwargs['start_date'])
        delta = datetime.now() - parsed
        assert 29 <= delta.days <= 31

    def test_explicit_window_is_not_overridden(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        _set_request({}, {'start_time': '2026-10-01 00:00:00',
                          'end_time': '2026-10-02 00:00:00'})
        LogQueryService.get_logs()
        kwargs = fake_proxy.list_logs_kwargs[0]
        assert kwargs['start_date'] == '2026-10-01 00:00:00'
        assert kwargs['end_date'] == '2026-10-02 00:00:00'

    def test_paging_uses_merged_total(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base + i, f'{day} 12:00:{i:02d}.000000', content=f'f{i}')
            for i in range(3)
        ])
        fake_proxy.items = [{
            'id': i + 1, 'time': f'{day}T11:00:0{i}', 'level': 'INFO',
            'category': 'auth', 'module': 'm', 'source': 'db',
            'content': f'd{i}',
        } for i in range(2)]
        fake_proxy.total = 2
        _set_request({}, {'page': '2', 'per_page': '3'})

        body, _code = LogQueryService.get_logs()
        data = body['data']
        assert data['total'] == 5 and data['page'] == 2 and data['per_page'] == 3
        assert data['pages'] == 2
        assert len(data['items']) == 2

    def test_mark_filter_returns_only_db_rows(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        day = _days_ago(1)
        _write_audit(log_root, day, [
            _record(_base_cursor(day), f'{day} 12:00:00.000000', content='file row')])
        fake_proxy.items = [{
            'id': 5, 'time': f'{day}T12:00:05', 'level': 'INFO', 'category': 'auth',
            'module': 'm', 'source': 'db', 'content': 'flagged db row', 'mark': 'flagged',
        }]
        fake_proxy.total = 1
        _set_request({}, {'mark': 'flagged'})

        body, _code = LogQueryService.get_logs()
        assert [item['content'] for item in body['data']['items']] == ['flagged db row']
        assert fake_proxy.list_logs_kwargs[0]['mark'] == 'flagged'


class TestGlobalStatsMerge:
    def test_stats_total_matches_list_total(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base, f'{day} 12:00:00.000000', level='ERROR'),
            _record(base + 1, f'{day} 12:00:01.000000', level='WARNING'),
        ])
        fake_proxy.stats = {'total': 2, 'debug': 0, 'info': 2, 'warning': 0,
                            'error': 0, 'critical': 0}
        fake_proxy.items = [{
            'id': 1, 'time': f'{day}T11:00:00', 'level': 'INFO', 'category': 'auth',
            'module': 'm', 'source': 'db', 'content': 'db row',
        }]
        fake_proxy.total = 2
        _set_request({}, {'page': '1', 'per_page': '50'})

        list_body, _c1 = LogQueryService.get_logs()
        stats_body, _c2 = LogQueryService.get_stats()
        assert list_body['data']['total'] == 2 + 2
        assert stats_body['data']['total'] == list_body['data']['total']
        assert stats_body['data']['info'] == 2 + 0
        assert stats_body['data']['error'] == 1
        assert stats_body['data']['warning'] == 1
        # 统计同样下发默认 30 天窗口，且与列表同参（共享一次扫描）
        assert fake_proxy.stats_kwargs['start_time']

    def test_task_stats_keeps_business_file_branch(self, log_root, fake_proxy):
        """有 task_id 时仍走业务文件分支，不叠加审计文件（契约 §Q2 不变项）。"""
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        fake_proxy.stats = {'total': 1, 'debug': 0, 'info': 1, 'warning': 0,
                            'error': 0, 'critical': 0}
        _set_request({}, {'task_id': '777'})
        stats_body, _code = LogQueryService.get_stats()
        assert stats_body['data']['total'] == 1
        # 任务维度不做默认窗口（遗留行为不变）
        assert not fake_proxy.stats_kwargs['start_time']


# =====================================================================
# 8. POST /logs/refresh（契约 §Q4 四类情形）
# =====================================================================

class TestRefreshCursor:
    def _seed(self, log_root, count=3):
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base + i, f'{day} 12:00:{i:02d}.000000', content=f'c{i}')
            for i in range(count)
        ])
        return base, base + count - 1

    def test_first_round_builds_baseline(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        _base, latest = self._seed(log_root)
        _set_request({'last_id': 0})
        body, _code = LogQueryService.refresh_logs()
        data = body['data']
        assert data['items'] == []
        assert data['last_id'] == latest
        assert data['db_max_id'] == latest
        assert 'reset_required' not in data

    def test_incremental_returns_ascending_at_most_100(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        base, latest = self._seed(log_root, count=150)
        _set_request({'last_id': base - 1})
        body, _code = LogQueryService.refresh_logs()
        data = body['data']
        assert data['count'] == 100
        ids = [item['id'] for item in data['items']]
        assert ids == sorted(ids)
        assert data['last_id'] == ids[-1]

        _set_request({'last_id': ids[-1]})
        body2, _code = LogQueryService.refresh_logs()
        assert body2['data']['count'] == 50
        assert body2['data']['last_id'] == latest

    def test_legacy_id_space_triggers_reset(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        _base, latest = self._seed(log_root)
        _set_request({'last_id': 6_949_425})           # logs 表旧自增 id
        body, _code = LogQueryService.refresh_logs()
        assert body['data']['items'] == []
        assert body['data']['reset_required'] is True
        assert body['data']['last_id'] == latest

    def test_cursor_beyond_server_max_triggers_reset(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        _base, latest = self._seed(log_root)
        _set_request({'last_id': latest + 1_000_000})
        body, _code = LogQueryService.refresh_logs()
        assert body['data']['items'] == []
        assert body['data']['reset_required'] is True
        assert body['data']['last_id'] == latest

    def test_repeated_pull_is_idempotent(self, log_root, fake_proxy):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        base, _latest = self._seed(log_root)
        _set_request({'last_id': base})
        first, _c = LogQueryService.refresh_logs()
        second, _c = LogQueryService.refresh_logs()
        assert first['data']['items'] == second['data']['items']
        assert first['data']['last_id'] == second['data']['last_id']


# =====================================================================
# 9. PUT /logs/mark（契约 §Q3）
# =====================================================================

class TestMarkFileCursor:
    def test_file_cursor_returns_200_with_dedicated_message(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        _set_request({'log_ids': [1_790_000_000_000_000], 'mark': 'flagged'})
        body, code = LogCommandService.mark_logs()
        assert code == 200
        assert '不支持标记' in body['message']
        assert fake_proxy.mark_args is None, '文件游标不应送 DB 更新'

    def test_legacy_id_behaviour_unchanged(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        fake_proxy.updated = 2
        _set_request({'log_ids': [11, 12], 'mark': 'flagged'})
        body, code = LogCommandService.mark_logs()
        assert code == 200
        assert fake_proxy.mark_args == ([11, 12], 'flagged')
        assert '已为 2 条日志' in body['message']

    def test_mixed_ids_only_update_legacy(self, fake_proxy):
        from api_gateway.application.services.log.log_command_service import (
            LogCommandService,
        )

        fake_proxy.updated = 1
        _set_request({'log_ids': [1_790_000_000_000_000, 11]})
        body, code = LogCommandService.mark_logs()
        assert code == 200
        assert fake_proxy.mark_args[0] == [11]
        assert '已为 1 条日志' in body['message']


# =====================================================================
# 10. POST /logs/export（与列表同源）
# =====================================================================

class TestExportSameSource:
    def test_export_without_ids_reads_audit_files_and_db(self, log_root, fake_proxy,
                                                         tmp_path, monkeypatch):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        day = _days_ago(1)
        base = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(base, f'{day} 12:00:00.000000', module='auth_login',
                    content='file row'),
        ])
        fake_proxy.items = [{
            'id': 3, 'time': f'{day}T12:00:01', 'level': 'ERROR',
            'module': 'auth_login', 'content': 'db row',
        }]
        fake_proxy.total = 1
        _set_request({'format': 'json'})

        LogQueryService.export_logs()
        files = list((tmp_path / 'exports').glob('*.json'))
        assert len(files) == 1
        rows = json.loads(files[0].read_text(encoding='utf-8'))
        assert [row['Content'] for row in rows] == ['db row', 'file row']
        # 筛选式导出与列表同源：走 list_logs，且同下默认 30 天窗口
        assert fake_proxy.export_args is None
        kwargs = fake_proxy.list_logs_kwargs[0]
        assert kwargs['level'] is None and kwargs['module'] is None
        assert kwargs['start_date'], '默认 30 天窗口必须下发给 DB 侧'

    def test_export_with_file_cursors_looks_up_by_date_dir(self, log_root, fake_proxy,
                                                           tmp_path, monkeypatch):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        day = _days_ago(1)
        cursor = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(cursor, f'{day} 12:00:00.000000', content='picked row'),
        ])
        _set_request({'log_ids': [cursor], 'format': 'txt'})

        LogQueryService.export_logs()
        files = list((tmp_path / 'exports').glob('*.txt'))
        assert len(files) == 1
        assert 'picked row' in files[0].read_text(encoding='utf-8')
        # 全部是文件游标 → 不发起 DB 导出（否则会把全表都导出来）
        assert fake_proxy.export_args is None
        assert fake_proxy.list_logs_kwargs == []

    def test_export_merges_legacy_ids_with_file_cursors(self, log_root, fake_proxy,
                                                        tmp_path, monkeypatch):
        from api_gateway.application.services.log.log_query_service import (
            LogQueryService,
        )

        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        day = _days_ago(1)
        cursor = _base_cursor(day)
        _write_audit(log_root, day, [
            _record(cursor, f'{day} 12:00:02.000000', content='file picked'),
        ])
        fake_proxy.export_items = [{
            'id': 7, 'time': f'{day}T12:00:01', 'level': 'INFO',
            'module': 'm', 'content': 'db picked',
        }]
        _set_request({'log_ids': [cursor, 7], 'format': 'json'})

        LogQueryService.export_logs()
        # legacy id 仍走 get_logs_for_export，文件游标按日期目录反查
        assert fake_proxy.export_args[0] == [7]
        rows = json.loads(list((tmp_path / 'exports').glob('*.json'))[0]
                          .read_text(encoding='utf-8'))
        assert [row['Content'] for row in rows] == ['file picked', 'db picked']


# =====================================================================
# 11. DB 侧分块拉取（返工：导出静默丢 DB 行 / 深分页 total 塌成文件侧）
# =====================================================================

class _PagingProxy:
    """按 page/per_page 正确分页的假代理（模拟 ListLogs：id 倒序 + 精确 total）。

    旧实现的瓶颈是「一次要 page*per_page 或 10 万行」，单条 gRPC 消息越界后
    被代理吞成空结果；本假代理按页返回，用来校验单块请求量与跨块拼接。
    """

    def __init__(self, rows, fail_on_page=None):
        self.rows = list(rows)
        self.fail_on_page = fail_on_page
        self.calls = []

    def list_logs(self, page=1, per_page=20, **kwargs):
        self.calls.append(dict(kwargs, page=page, per_page=per_page))
        if self.fail_on_page and page == self.fail_on_page:
            raise RuntimeError(
                'ListLogs gRPC 失败: RESOURCE_EXHAUSTED Sent message larger than max')
        start = (page - 1) * per_page
        return {'items': list(self.rows[start:start + per_page]),
                'total': len(self.rows)}


def _db_rows(count, day):
    """id 倒序、时间递减的假 DB 行（第 index 条内容为 row {index}）。"""
    base = datetime.strptime(day, '%Y-%m-%d').replace(hour=12)
    rows = []
    for index in range(count):
        rows.append({'id': count - index,
                     'time': (base - timedelta(seconds=index)).isoformat(),
                     'level': 'INFO', 'category': 'auth', 'module': 'm',
                     'content': f'row {index}', 'mark': ''})
    return rows


@pytest.fixture()
def chunk_100(monkeypatch):
    """把单块行数压到 100，用少量假数据就能覆盖跨块拼接（默认 5000）。"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'LOG_DB_FETCH_CHUNK_ROWS', 100)
    return 100


def _use_proxy(monkeypatch, proxy):
    monkeypatch.setattr(
        'api_gateway.infrastructure.grpc_proxies.task_data_service', proxy)
    return proxy


class TestDbChunkedFetch:
    def test_small_page_requests_only_needed_rows(self, log_root, monkeypatch, chunk_100):
        """首页只要 page*per_page 行：不因分块把单次请求放大到整块。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        proxy = _use_proxy(monkeypatch, _PagingProxy(_db_rows(500, _days_ago(1))))
        _set_request({}, {'page': '1', 'per_page': '20'})

        body, _code = LogQueryService.get_logs()
        assert body['data']['total'] == 500
        assert len(body['data']['items']) == 20
        assert [call['per_page'] for call in proxy.calls] == [20]

    def test_deep_page_total_keeps_db_count(self, log_root, monkeypatch, chunk_100):
        """深分页（need_rows=1000）分块拉取后 total 仍是 DB 精确计数，列表不重不漏。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        proxy = _use_proxy(monkeypatch, _PagingProxy(_db_rows(2000, _days_ago(1))))
        _set_request({}, {'page': '10', 'per_page': '100'})

        body, code = LogQueryService.get_logs()
        assert code == 200
        assert body['data']['total'] == 2000
        assert body['data']['pages'] == 20
        items = body['data']['items']
        assert len(items) == 100
        assert [item['content'] for item in items[:2]] == ['row 900', 'row 901']
        # 每块请求量都受单块上限约束（修复前这里一次要 1000 行、真实库上撞 64MB）
        assert all(call['per_page'] <= chunk_100 for call in proxy.calls)
        assert len(proxy.calls) == 10

    def test_chunk_failure_returns_error_not_partial_list(self, log_root, monkeypatch,
                                                         chunk_100):
        """任一后续块失败 → 整单报错，不把「拿不到」伪装成部分列表。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        _use_proxy(monkeypatch, _PagingProxy(_db_rows(2000, _days_ago(1)), fail_on_page=3))
        _set_request({}, {'page': '10', 'per_page': '100'})

        body, _http = LogQueryService.get_logs()
        assert body['code'] == 500
        assert '获取日志失败' in body['message']
        assert 'data' not in body

    def test_task_dimension_uses_chunked_fetch(self, log_root, monkeypatch, chunk_100):
        """任务维度合并视图同一取数路径：过滤下推 + 分块，total 为 DB 精确计数。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        proxy = _use_proxy(monkeypatch, _PagingProxy(_db_rows(250, _days_ago(1))))
        _set_request({}, {'task_id': '7', 'page': '1', 'per_page': '50'})

        body, code = LogQueryService.get_logs()
        assert code == 200
        assert body['data']['total'] == 250
        assert len(body['data']['items']) == 50
        assert all(call['task_id'] == 7 for call in proxy.calls)
        assert all(call['per_page'] <= chunk_100 for call in proxy.calls)

    def test_export_counts_all_matched_rows(self, log_root, monkeypatch, tmp_path,
                                            chunk_100):
        """导出无 log_ids：分块拉全部命中行，条数与列表 total 一致（修复前只剩文件行）。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        proxy = _use_proxy(monkeypatch, _PagingProxy(_db_rows(305, _days_ago(1))))
        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        _set_request({'format': 'json'})

        LogQueryService.export_logs()
        rows = json.loads(next((tmp_path / 'exports').glob('*.json'))
                          .read_text(encoding='utf-8'))
        assert len(rows) == 305
        assert [row['Content'] for row in rows[:2]] == ['row 0', 'row 1']
        assert all(call['per_page'] <= chunk_100 for call in proxy.calls)
        assert len(proxy.calls) == 4          # 100 + 100 + 100 + 5

    def test_export_failure_returns_error_and_no_file(self, log_root, monkeypatch,
                                                      tmp_path, chunk_100):
        from api_gateway.application.services.log.log_query_service import LogQueryService

        _use_proxy(monkeypatch, _PagingProxy(_db_rows(300, _days_ago(1)), fail_on_page=2))
        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        _set_request({'format': 'csv'})

        body, http = LogQueryService.export_logs()
        assert http == 500
        assert '导出日志失败' in body['message']
        assert not list((tmp_path / 'exports').glob('*.csv'))

    def test_export_max_rows_guard_is_explicit(self, log_root, monkeypatch,
                                               tmp_path, chunk_100):
        """配置了导出上限时超限显式报 400，不静默截断成部分数据。"""
        from shared.infrastructure.config import BaseConfig
        from api_gateway.application.services.log.log_query_service import LogQueryService

        monkeypatch.setattr(BaseConfig, 'LOG_DB_EXPORT_MAX_ROWS', 100)
        _use_proxy(monkeypatch, _PagingProxy(_db_rows(300, _days_ago(1))))
        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        _set_request({'format': 'csv'})

        body, http = LogQueryService.export_logs()
        assert http == 400
        assert '超过上限 100 行' in body['message']
        assert not list((tmp_path / 'exports').glob('*.csv'))


    def test_export_pins_db_end_time_to_snapshot(self, log_root, monkeypatch,
                                                 tmp_path, chunk_100):
        """分块 offset 分页 + 实时库：导出把 DB 结果集钉在起点（不重复、不丢行）。"""
        from api_gateway.application.services.log.log_query_service import LogQueryService

        proxy = _use_proxy(monkeypatch, _PagingProxy(_db_rows(150, _days_ago(1))))
        monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))
        _set_request({'format': 'json'})

        LogQueryService.export_logs()
        assert proxy.calls[0]['start_date']
        assert proxy.calls[0]['end_date']
