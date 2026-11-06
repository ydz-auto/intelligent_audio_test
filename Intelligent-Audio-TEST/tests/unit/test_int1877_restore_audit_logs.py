# -*- coding: utf-8 -*-
"""INT-1877 审计日志回灌脚本单测（契约 §Q5.3 / 卡片 1 验收第 6 条）。

覆盖：
- 区间枚举（含两端，按目录日期）
- 落点与写侧模板（`AuditLogPathBuilder.build_rel_path`）一字不差
- 字节数（对源对象元数据）+ sha256（落盘回读）校验
- 重跑幂等：默认不覆盖，字节级不变
- 本地已存在且字节数一致 → 跳过（不算失败）；字节数不同且未 --overwrite → 非零退出
- 逐行 JSON 校验：坏行 / 缺 `cursor|event|time` → 非零退出且不落盘
- OSS 不可达（存储层降级 local://）→ 非零退出，一个对象都不回灌
- 区间内没有对象的日子 → 打印 0 并继续（不报错）
"""
import json
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1877_restore_') + '/r.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import scripts.maintenance.restore_audit_logs_from_oss as restore  # noqa: E402
from shared.logging.path_builder import AuditLogPathBuilder  # noqa: E402

_EXIT_OSS_UNAVAILABLE = 3


class FakeObjectStore:
    """进程内模拟 rustfs：逻辑 key → bytes，size 元数据可单独篡改。"""

    def __init__(self, objects=None, oss_available=True):
        self.objects = dict(objects or {})
        self.sizes = {}
        self.oss_available = oss_available
        self.list_calls = []
        self.downloads = []

    # --- 存储层接口（脚本只经这些方法访问对象存储）---
    def _use_oss(self):
        return self.oss_available

    def build_path(self, category, key, prefer_oss=True):
        scheme = 'oss://' if prefer_oss else 'local://'
        return f'{scheme}{category}/{key}'

    def list_objects_with_meta(self, category, prefix=''):
        self.list_calls.append((category, prefix))
        return [{'key': key,
                 'sizeBytes': self.sizes.get(key, len(data)),
                 'lastModified': None}
                for key, data in sorted(self.objects.items())
                if key.startswith(prefix)]

    def load_bytes(self, path):
        self.downloads.append(path)
        prefix = f'oss://{restore.AUDIT_ARCHIVE_CATEGORY}/'
        assert path.startswith(prefix), f'必须经 category 机制拼 key: {path}'
        key = path[len(prefix):]
        return self.objects[key]

    # --- 造数据 ---
    def put(self, key, data, size=None):
        self.objects[key] = data
        if size is not None:
            self.sizes[key] = size


def _line(cursor, event='AUTH_LOGIN', time_text='2026-09-01 09:00:00.000000'):
    return json.dumps({'cursor': cursor, 'time': time_text, 'event': event,
                       'category': 'auth', 'service': 'api_gateway'},
                      ensure_ascii=False)


def _payload(*cursors):
    return ('\n'.join(_line(c) for c in cursors) + '\n').encode('utf-8')


def _obj_key(day, name):
    return f'{restore.AUDIT_ARCHIVE_PREFIX}/{day}/{name}'


def _make_store(days=('2026-09-01', '2026-09-02', '2026-09-03')):
    store = FakeObjectStore()
    for index, day in enumerate(days):
        store.put(_obj_key(day, 'auth.api_gateway.host-1.jsonl'),
                  _payload(1000 + index, 1001 + index))
    return store


def _restore(tmp_path, store, start='2026-09-01', end='2026-09-03',
             overwrite=False, dry_run=False, categories=()):
    return restore.restore_range(
        restore._parse_date(start), restore._parse_date(end),
        str(tmp_path / 'logs'), categories=categories,
        overwrite=overwrite, dry_run=dry_run, store=store)


# ---------------------------------------------------------------------------
# 区间枚举 + 落点
# ---------------------------------------------------------------------------

class TestRestoreRange:

    def test_three_dates_land_on_write_side_template(self, tmp_path):
        store = _make_store()
        stats = _restore(tmp_path, store)

        assert stats.expected == 3
        assert stats.downloaded == 3
        assert stats.written == 3
        assert stats.failed == 0 and stats.conflicts == 0
        builder = AuditLogPathBuilder()
        for day in ('2026-09-01', '2026-09-02', '2026-09-03'):
            expected_rel = builder.build_rel_path(
                category='auth', service_name='api_gateway',
                date_seg=day, process_id='host-1')
            dst = tmp_path / 'logs' / expected_rel
            assert dst.is_file(), f'落点必须与写侧模板一致: {dst}'
            key = _obj_key(day, 'auth.api_gateway.host-1.jsonl')
            assert dst.read_bytes() == store.objects[key], '回灌内容必须原样'

        # 只枚举区间内日期（按目录日期前缀）
        prefixes = [prefix for _category, prefix in store.list_calls]
        assert prefixes == ['audit/2026-09-01/', 'audit/2026-09-02/',
                            'audit/2026-09-03/'], '区间枚举必须逐日（含两端）'

    def test_range_is_inclusive_and_ordered(self):
        days = [d.isoformat() for d in restore.iter_date_range(
            restore._parse_date('2026-09-01'),
            restore._parse_date('2026-09-04'))]
        assert days == ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']

    def test_from_after_to_is_usage_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            restore.parse_args(['--from', '2026-09-05', '--to', '2026-09-01'])
        assert exc.value.code == 2

    def test_empty_day_reports_zero_and_continues(self, tmp_path):
        store = _make_store(days=('2026-09-01',))
        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-03')
        assert stats.expected == 1 and stats.written == 1
        assert stats.failed == 0, '区间内没有对象的日子不得报错'
        assert not (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-02').exists()

    def test_category_filter(self, tmp_path):
        store = FakeObjectStore()
        store.put(_obj_key('2026-09-01', 'auth.api_gateway.h-1.jsonl'), _payload(1))
        store.put(_obj_key('2026-09-01', 'benchmark.report_service.h-1.jsonl'),
                  _payload(2))
        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01',
                         categories=('auth',))
        assert stats.expected == 1 and stats.written == 1
        assert (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                / 'auth.api_gateway.h-1.jsonl').is_file()
        assert not (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                    / 'benchmark.report_service.h-1.jsonl').exists()

    def test_dry_run_does_not_download_or_write(self, tmp_path):
        store = _make_store()
        stats = _restore(tmp_path, store, dry_run=True)
        assert stats.expected == 3 and stats.written == 0
        assert store.downloads == [], 'dry-run 不得下载'
        assert not (tmp_path / 'logs').exists(), 'dry-run 不得落盘'


# ---------------------------------------------------------------------------
# 幂等：默认不覆盖 / 重跑字节级不变
# ---------------------------------------------------------------------------

class TestIdempotence:

    def test_rerun_is_byte_identical(self, tmp_path):
        store = _make_store()
        first = _restore(tmp_path, store)
        assert first.written == 3

        target = (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                  / 'auth.api_gateway.host-1.jsonl')
        before = target.read_bytes()
        before_mtime = os.stat(target).st_mtime_ns

        second = _restore(tmp_path, store)
        assert second.written == 0
        assert second.skipped == 3, '本地已存在且字节数一致 → 计入跳过'
        assert second.failed == 0 and second.conflicts == 0, '跳过不算失败'
        assert second.ok is True
        assert target.read_bytes() == before, '重跑必须字节级不变'
        assert os.stat(target).st_mtime_ns == before_mtime, '重跑不得重写已有文件'
        assert len(store.downloads) == 3, '跳过时不应再下载'

    def test_existing_local_file_differs_without_overwrite_is_failure(self, tmp_path):
        store = _make_store(days=('2026-09-01',))
        target = (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                  / 'auth.api_gateway.host-1.jsonl')
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"cursor": 1}\n')  # 比源短，且内容不同

        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01')
        assert stats.conflicts == 1 and stats.written == 0
        assert stats.ok is False
        assert target.read_bytes() == b'{"cursor": 1}\n', '默认不覆盖本地文件'
        assert restore._report(stats, False, str(tmp_path / 'logs')) != 0

    def test_overwrite_replaces_local_file(self, tmp_path):
        store = _make_store(days=('2026-09-01',))
        target = (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                  / 'auth.api_gateway.host-1.jsonl')
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"cursor": 1}\n')

        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01',
                         overwrite=True)
        assert stats.written == 1 and stats.conflicts == 0
        key = _obj_key('2026-09-01', 'auth.api_gateway.host-1.jsonl')
        assert target.read_bytes() == store.objects[key]


# ---------------------------------------------------------------------------
# 校验失败：字节数 / JSON 逐行 / sha256
# ---------------------------------------------------------------------------

class TestValidation:

    def test_size_mismatch_against_metadata_fails(self, tmp_path):
        store = _make_store(days=('2026-09-01',))
        key = _obj_key('2026-09-01', 'auth.api_gateway.host-1.jsonl')
        store.sizes[key] = len(store.objects[key]) + 7  # 元数据 size 与内容不符

        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01')
        assert stats.failed == 1 and stats.written == 0
        assert '字节数校验失败' in stats.failures[0]
        assert not (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01').exists(), \
            '校验失败不得落盘'

    def test_bad_json_line_fails_and_writes_nothing(self, tmp_path):
        store = FakeObjectStore()
        store.put(_obj_key('2026-09-01', 'auth.api_gateway.h-1.jsonl'),
                  b'{"cursor": 1, "event": "X", "time": "t"}\nNOT-JSON\n')
        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01')
        assert stats.failed == 1 and stats.written == 0
        assert 'JSON 解析失败' in stats.failures[0]
        assert not (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01').exists()

    def test_missing_required_field_fails(self, tmp_path):
        store = FakeObjectStore()
        store.put(_obj_key('2026-09-01', 'auth.api_gateway.h-1.jsonl'),
                  json.dumps({'cursor': 1, 'event': '', 'time': 'x'}).encode()
                  + b'\n')
        problems = restore.validate_jsonl(store.objects[
            _obj_key('2026-09-01', 'auth.api_gateway.h-1.jsonl')])
        assert any('event' in item for item in problems)

    def test_trailing_newline_is_not_an_empty_line(self):
        assert restore.validate_jsonl(_payload(1, 2)) == []
        assert any('空行' in item for item in
                   restore.validate_jsonl(_payload(1) + b'\n\n'))

    def test_sha256_check_detects_corrupted_write(self, tmp_path, monkeypatch):
        """落盘回读 sha256 与下载内容不一致 → 计失败并清掉坏文件。"""
        store = _make_store(days=('2026-09-01',))
        real_write = restore._write_atomic

        def _corrupting_write(path, data):
            real_write(path, b'corrupted')

        monkeypatch.setattr(restore, '_write_atomic', _corrupting_write)
        stats = _restore(tmp_path, store, start='2026-09-01', end='2026-09-01')
        assert stats.failed == 1 and stats.written == 0
        assert 'sha256 校验失败' in stats.failures[0]
        assert not (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-01'
                    / 'auth.api_gateway.host-1.jsonl').exists()

    def test_unknown_object_prefix_is_skipped(self, tmp_path):
        """目录占位 / 非 .jsonl 对象不参与回灌、也不算失败。"""
        store = FakeObjectStore()
        store.put('audit/2026-09-01/', b'')
        store.put('audit/2026-09-01/notes.txt', b'hello')
        assert restore.list_day_objects(store, '2026-09-01', ()) == []


# ---------------------------------------------------------------------------
# OSS 可达性探活（非零退出，不允许「成功回灌 0 个文件」）
# ---------------------------------------------------------------------------

def _run_main(monkeypatch, tmp_path, store, argv=None):
    monkeypatch.setattr(restore, 'storage', store)
    args = argv or ['--from', '2026-09-01', '--to', '2026-09-03',
                    '--target-root', str(tmp_path / 'logs')]
    return restore.main(args)


class TestObjectStorageProbe:

    def test_probe_reports_oss_when_backend_available(self):
        assert restore.probe_object_storage(
            FakeObjectStore(oss_available=True)).startswith('oss://')

    def test_probe_reports_local_fallback(self):
        path = restore.probe_object_storage(
            FakeObjectStore(oss_available=False))
        assert path.startswith('local://')

    def test_local_fallback_exits_non_zero_without_restoring(
            self, tmp_path, monkeypatch):
        store = _make_store()
        store.oss_available = False
        code = _run_main(monkeypatch, tmp_path, store)
        assert code == _EXIT_OSS_UNAVAILABLE, 'OSS 不可达必须非零退出'
        assert store.list_calls == [], '探活失败时不得开始枚举/回灌'
        assert not (tmp_path / 'logs').exists()

    def test_successful_run_exits_zero(self, tmp_path, monkeypatch):
        store = _make_store()
        code = _run_main(monkeypatch, tmp_path, store)
        assert code == restore.EXIT_OK
        assert (tmp_path / 'logs' / restore.AUDIT_DIR / '2026-09-02'
                / 'auth.api_gateway.host-1.jsonl').is_file()

    def test_failures_make_exit_non_zero(self, tmp_path, monkeypatch):
        store = FakeObjectStore()
        store.put(_obj_key('2026-09-01', 'auth.api_gateway.h-1.jsonl'),
                  b'broken\n')
        code = _run_main(monkeypatch, tmp_path, store,
                         argv=['--from', '2026-09-01', '--to', '2026-09-01',
                               '--target-root', str(tmp_path / 'logs')])
        assert code == restore.EXIT_VALIDATION_FAILED
