# -*- coding: utf-8 -*-
"""INT-128 TTL 扫描缓存内存上界回归。

1. 单条缓存条目物化上限（LOG_BUSINESS_SCAN_CACHE_ENTRY_MAX_ENTRIES，默认
   1 万，0 = 不限）：结果条数超上限的查询不缓存（每次真实扫描，命中/
   未命中结果一致，仅失去 TTL 内免复扫）；不超限结果照常缓存。
2. 惰性全表过期清扫：过期条目在任意 get/put 时即被释放，不再等待被再次
   访问或缓存满，驻留内存只含 TTL 内活跃查询。
3. 单条缓存条目物化恒不超过 min(扫描上限, 条目上限)；配置快照接线默认值。
"""
import os
import sys
import types
from pathlib import Path

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int128_entry_cap_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, reset_log_settings  # noqa: E402
from shared.logging.enums import LogEnvironment  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9101280  # 隔离用 task_id（仅文件侧用例，不触 DB）


def _make_settings(root, *, scan_ttl_seconds=3, scan_cap=100_000, entry_cap=10_000):
    from shared.logging.config import LogSettings
    return LogSettings(
        root_dir=root,
        environment=LogEnvironment.DEV,
        service_max_bytes=50 * 1024 * 1024,
        service_retention_days=30,
        business_enabled=True,
        business_db_enabled=False,
        business_max_bytes=50 * 1024 * 1024,
        business_retention_days=30,
        business_max_scan_entries=scan_cap,
        business_scan_cache_ttl_seconds=scan_ttl_seconds,
        business_scan_cache_entry_max_entries=entry_cap,
    )


@pytest.fixture()
def log_root(tmp_path, monkeypatch):
    root = str(tmp_path / 'logs')
    monkeypatch.setattr('shared.logging.config._SETTINGS', _make_settings(root))
    yield root
    reset_log_settings()
    import shared.logging.business_reader as br
    br._SCAN_CACHE.clear()


def _write_business_file(root, rel, entries):
    path = Path(root) / 'business' / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for i, entry in enumerate(entries):
            handle.write(
                '{"time": "' + entry['time'] + '", "level": "' + entry['level'] +
                '", "content": "' + entry.get('content', f'file line {i}') +
                '", "task_id": ' + str(_TASK_ID) + '}\n'
            )
    return str(path)


def _entries(count):
    return [{'time': f'2026-10-10T12:00:{i:02d}', 'level': 'INFO'}
            for i in range(count)]


@pytest.fixture()
def counting_reader():
    """BusinessLogReader + _parse_file 扫描计数（每次调用后可断言扫描次数）。"""
    reader = BusinessLogReader()
    calls = {'n': 0}
    original_parse = reader._parse_file

    def counting_parse(file_path):
        calls['n'] += 1
        return original_parse(file_path)

    reader._parse_file = counting_parse
    return reader, calls


class TestScanCacheEntryCap:
    """单条缓存条目物化上限：超限不缓存，结果语义不变。"""

    def test_oversized_result_not_cached(self, log_root, counting_reader, monkeypatch):
        """验收 1：结果条数超过单条条目上限 → 不缓存，每次真实扫描且结果完整。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             _entries(3))
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=2))

        reader, calls = counting_reader
        args = dict(task_id=_TASK_ID)
        first = reader.read_entries(**args)
        assert len(first) == 3          # 结果语义不变：完整返回
        assert calls['n'] == 1
        assert len(br._SCAN_CACHE) == 0  # 超限条目未物化进缓存
        second = reader.read_entries(**args)
        assert calls['n'] == 2          # 无缓存命中 → 真实复扫
        assert [item['id'] for item in second] == [item['id'] for item in first]

    def test_result_within_cap_cached(self, log_root, counting_reader, monkeypatch):
        """结果不超上限 → 照常缓存，TTL 窗口内免复扫。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             _entries(3))
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=3))

        reader, calls = counting_reader
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1          # 命中缓存
        (key, (stored_at, items)), = br._SCAN_CACHE.items()
        assert len(items) == 3

    def test_entry_cap_zero_unlimited(self, log_root, counting_reader, monkeypatch):
        """entry_cap = 0 = 不限：超限行为回退 INT-100 形态（照常缓存）。"""
        _write_business_file(log_root, f'{_TASK_ID}/dev-1/round-1/act.log',
                             _entries(3))
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=0))

        reader, calls = counting_reader
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1
        assert len(br._SCAN_CACHE) == 1

    def test_mixed_keys_only_within_cap_stored(self, log_root, counting_reader, monkeypatch):
        """混合键：超限键不缓存、未超限键缓存，全部驻留条目 ≤ 条目上限。"""
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=2))

        for task_no, row_count in ((1, 1), (2, 3), (3, 5)):
            task_id = _TASK_ID + task_no
            _write_business_file(log_root, f'{task_id}/dev-1/round-1/act.log',
                                 _entries(row_count))
        reader, _ = counting_reader
        for task_no in (1, 2, 3):
            reader.read_entries(task_id=_TASK_ID + task_no)
        assert len(br._SCAN_CACHE) == 1  # 仅 1 行的 task 未超上限
        reader.read_entries(task_id=_TASK_ID + 1)
        for _stored_at, items in br._SCAN_CACHE.values():
            assert len(items) <= 2


class TestLazyExpiredSweep:
    """过期条目在任意 get/put 时惰性全表清扫，不再等待缓存满。"""

    def test_expired_entries_swept_on_get(self, monkeypatch):
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 1000.0))
        key_a, key_b = ('a',), ('b',)
        BusinessLogReader._scan_cache_put(key_a, [{'id': 1}])
        BusinessLogReader._scan_cache_put(key_b, [{'id': 2}])
        assert len(br._SCAN_CACHE) == 2

        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 2000.0))
        assert BusinessLogReader._scan_cache_get(key_a) is None  # 已过期
        # 全表清扫：b 从未被访问也一并释放
        assert len(br._SCAN_CACHE) == 0
        assert key_b not in br._SCAN_CACHE

    def test_expired_entries_swept_on_put(self, monkeypatch):
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 1000.0))
        key_a, key_b = ('a',), ('b',)
        BusinessLogReader._scan_cache_put(key_a, [{'id': 1}])
        BusinessLogReader._scan_cache_put(key_b, [{'id': 2}])

        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 2000.0))
        BusinessLogReader._scan_cache_put(('c',), [{'id': 3}])
        # put 时惰性清扫：a/b 过期即释放，缓存只含 TTL 内活跃条目
        assert list(br._SCAN_CACHE.keys()) == [('c',)]

    def test_sweep_never_evicts_live_entries(self, monkeypatch):
        import shared.logging.business_reader as br
        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 1000.0))
        BusinessLogReader._scan_cache_put(('live',), [{'id': 1}])
        monkeypatch.setattr('shared.logging.business_reader.time',
                            types.SimpleNamespace(monotonic=lambda: 1001.0))
        BusinessLogReader._scan_cache_put(('other',), [{'id': 2}])
        assert BusinessLogReader._scan_cache_get(('live',)) == [{'id': 1}]


class TestConfigWiring:
    """配置链：LogSettings 默认值与 _build_settings 接线（BaseConfig 默认 1 万）。"""

    def test_log_settings_default_entry_cap(self):
        from shared.logging.config import LogSettings
        assert LogSettings.business_scan_cache_entry_max_entries == 10_000

    def test_build_settings_reads_base_config(self):
        from shared.infrastructure.config import BaseConfig
        from shared.logging.config import _build_settings
        settings = _build_settings()
        expected = max(0, BaseConfig.LOG_BUSINESS_SCAN_CACHE_ENTRY_MAX_ENTRIES)
        assert settings.business_scan_cache_entry_max_entries == expected
        assert settings.business_scan_cache_entry_max_entries == 10_000

    def test_reader_helper_fallback_on_bad_config(self, monkeypatch):
        """配置非法时按不限（0）降级，不影响缓存可用性。"""
        import shared.logging.config as log_config
        monkeypatch.setattr(
            'shared.logging.config._SETTINGS',
            type('Broken', (), {'business_scan_cache_entry_max_entries': 'abc'})())
        assert BusinessLogReader._scan_cache_entry_cap() == 0
