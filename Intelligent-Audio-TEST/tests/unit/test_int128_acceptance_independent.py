# -*- coding: utf-8 -*-
"""INT-128 测试工程师独立验收（P2.1 TTL 扫描缓存内存上界）。

与开发自测 test_int128_scan_cache_entry_cap.py 互补，全部走公开 read_entries
路径（不经私有 get/put 助手），覆盖开发自测未触及的验收角度：

1. 物化上限 = min(扫描上限, 条目上限) 双向不变量：扫描上限 < 条目上限时
   结果照常缓存（条目 ≤ 扫描上限）；扫描上限结果超条目上限时不缓存。
2. 大任务（缩放）结果语义：超限结果每次完整返回且多次调用逐条一致
   （id + 顺序），仅失去 TTL 内免复扫——命中/未命中结果一致。
3. 驻留有界量化：默认 _SCAN_CACHE_MAX=32 条 × 条目上限条目的真实填充后，
   缓存对象深尺寸有界且全部条目 ≤ min(扫描上限, 条目上限)。
4. 与 INT-132 归一的交互：module='all'（文件侧不过滤）超限结果同样完整
   返回不缓存；未超限照常缓存——两条整改叠加行为正确。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int128_accept_unused.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import shared.logging  # noqa: E402  定位仓库根
from shared.logging import BusinessLogReader, LogEnvironment, reset_log_settings  # noqa: E402

_REPO_ROOT = str(Path(shared.logging.__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TASK_ID = 9101281  # 独立 task_id 段，与开发自测（9101280）及其他用例隔离


def _make_settings(root, *, scan_ttl_seconds=3600, scan_cap=100_000,
                   entry_cap=10_000):
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


def _write_business_file(root, task_id, entries, module=None):
    path = Path(root) / 'business' / str(task_id) / 'dev-1' / 'act.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for i, entry in enumerate(entries):
            record = ('{"time": "%s", "level": "%s", "content": "%s", '
                      '"task_id": %d'
                      % (entry['time'], entry['level'],
                         entry.get('content', f'file line {i}'), task_id))
            if module is not None:
                record += ', "module": "%s"' % module
            handle.write(record + '}\n')
    return str(path)


def _entries(count, *, start_second=0):
    return [{'time': f'2026-10-10T12:00:{start_second + i:02d}',
             'level': 'INFO'} for i in range(count)]


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


# ========== 验收 1：单条条目物化上限 = min(扫描上限, 条目上限) ==========

class TestEntryCapMinInvariant:
    def test_scan_cap_below_entry_cap_result_cached(self, log_root,
                                                    counting_reader, monkeypatch):
        """扫描上限(5) < 条目上限(10)：结果不超条目上限，照常缓存（TTL 内
        免复扫不回退）——单条条目物化 ≤ min = 扫描上限。"""
        _write_business_file(log_root, _TASK_ID, _entries(5))
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_cap=5, entry_cap=10))

        reader, calls = counting_reader
        first = reader.read_entries(task_id=_TASK_ID)
        assert len(first) == 5
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1  # 命中缓存
        import shared.logging.business_reader as br
        (_key, (_stored_at, items)), = br._SCAN_CACHE.items()
        assert len(items) == 5
        assert len(items) <= min(5, 10)

    def test_scan_cap_result_above_entry_cap_not_cached(self, log_root,
                                                        counting_reader,
                                                        monkeypatch):
        """扫描上限(5) > 条目上限(2)：达扫描上限的结果(5 条) 超条目上限 →
        不缓存；每次完整返回且逐条一致。"""
        _write_business_file(log_root, _TASK_ID, _entries(5))
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, scan_cap=5, entry_cap=2))

        reader, calls = counting_reader
        first = reader.read_entries(task_id=_TASK_ID)
        assert len(first) == 5
        second = reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 2  # 超限不缓存 → 真实复扫
        assert [i['id'] for i in second] == [i['id'] for i in first]
        import shared.logging.business_reader as br
        assert len(br._SCAN_CACHE) == 0


# ========== 验收 1（续）：大任务缩放——命中/未命中结果一致 ==========

class TestLargeResultSemantics:
    def test_oversize_result_complete_and_identical(self, log_root,
                                                    counting_reader, monkeypatch):
        """大任务（缩放：25 条 vs 上限 10）：结果完整返回、多次调用逐条一致
        （含顺序），缓存保持空——超限只失去免复扫，结果语义不变。"""
        _write_business_file(log_root, _TASK_ID, _entries(25))
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=10))

        reader, calls = counting_reader
        results = [reader.read_entries(task_id=_TASK_ID) for _ in range(3)]
        assert all(len(r) == 25 for r in results)
        ids = [[i['id'] for i in r] for r in results]
        assert ids[0] == ids[1] == ids[2]
        assert calls['n'] == 3  # 每次真实扫描
        import shared.logging.business_reader as br
        assert len(br._SCAN_CACHE) == 0

    def test_entry_cap_zero_unlimited_caches_large_result(self, log_root,
                                                          counting_reader,
                                                          monkeypatch):
        """entry_cap=0（不限）回退 INT-100 形态：大结果照常缓存，免复扫。"""
        _write_business_file(log_root, _TASK_ID, _entries(25))
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=0))

        reader, calls = counting_reader
        reader.read_entries(task_id=_TASK_ID)
        reader.read_entries(task_id=_TASK_ID)
        assert calls['n'] == 1
        import shared.logging.business_reader as br
        (_key, (_stored_at, items)), = br._SCAN_CACHE.items()
        assert len(items) == 25


# ========== 验收 1（续）：驻留有界量化（默认 32 条 × 条目上限） ==========

class TestBoundedResidency:
    def test_full_cache_residency_bounded(self, log_root, monkeypatch):
        """按默认 _SCAN_CACHE_MAX=32 条真实填充至满：全部条目 ≤ min(扫描上限,
        条目上限)，缓存对象深尺寸有界（GB 级驻留不再可达）。"""
        import shared.logging.business_reader as br

        entry_cap = 2000
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=entry_cap))
        for offset in range(32):
            task_id = _TASK_ID + 100 + offset
            _write_business_file(log_root, task_id, _entries(entry_cap,
                                                             start_second=0))

        reader = BusinessLogReader()
        for offset in range(32):
            reader.read_entries(task_id=_TASK_ID + 100 + offset)

        assert len(br._SCAN_CACHE) == 32

        def _deep_size(obj, _seen=None):
            _seen = _seen if _seen is not None else set()
            if id(obj) in _seen:
                return 0
            _seen.add(id(obj))
            total = sys.getsizeof(obj)
            if isinstance(obj, dict):
                for k, v in obj.items():
                    total += _deep_size(k, _seen) + _deep_size(v, _seen)
            elif isinstance(obj, (list, tuple, set)):
                for v in obj:
                    total += _deep_size(v, _seen)
            elif isinstance(obj, str) and id(obj) not in _seen:
                pass
            return total

        residency = sum(_deep_size(entry) for entry in br._SCAN_CACHE.values())
        assert residency < 200 * 1024 * 1024  # 数据实量约 25MB，上界宽松防抖
        for _key, (_stored_at, items) in br._SCAN_CACHE.items():
            assert len(items) <= min(100_000, entry_cap)


# ========== 验收 2 交叉：与 INT-132 module='all' 归一的叠加行为 ==========

class TestModuleAllInteraction:
    def test_module_all_oversize_result_complete_not_cached(self, log_root,
                                                            counting_reader,
                                                            monkeypatch):
        """module='all'（INT-132 后文件侧不过滤）× 超限结果：完整返回且多次
        一致、不缓存——两条整改叠加无相互破坏。"""
        _write_business_file(log_root, _TASK_ID, _entries(5), module='exec')
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=2))

        reader, calls = counting_reader
        first = reader.read_entries(task_id=_TASK_ID, module='all')
        assert len(first) == 5  # 'all' 不过滤（非字面清零）
        second = reader.read_entries(task_id=_TASK_ID, module='all')
        assert [i['id'] for i in second] == [i['id'] for i in first]
        assert calls['n'] == 2
        import shared.logging.business_reader as br
        assert len(br._SCAN_CACHE) == 0

    def test_module_all_within_cap_cached_single_scan(self, log_root,
                                                      counting_reader,
                                                      monkeypatch):
        """module='all' 未超限：照常缓存，TTL 内同参免复扫。"""
        _write_business_file(log_root, _TASK_ID, _entries(2), module='exec')
        monkeypatch.setattr('shared.logging.config._SETTINGS',
                            _make_settings(log_root, entry_cap=10))

        reader, calls = counting_reader
        reader.read_entries(task_id=_TASK_ID, module='all')
        reader.read_entries(task_id=_TASK_ID, module='all')
        assert calls['n'] == 1
        import shared.logging.business_reader as br
        assert len(br._SCAN_CACHE) == 1


# ========== 验收 1：配置旋钮独立存在与默认值 ==========

class TestConfigKnob:
    def test_base_config_default_10000(self):
        """独立配置旋钮存在且默认 1 万（验收标准：给出独立配置旋钮与默认值）。"""
        from shared.infrastructure.config import BaseConfig
        assert BaseConfig.LOG_BUSINESS_SCAN_CACHE_ENTRY_MAX_ENTRIES == 10_000
