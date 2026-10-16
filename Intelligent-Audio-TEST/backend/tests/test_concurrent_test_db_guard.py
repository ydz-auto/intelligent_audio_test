# -*- coding: utf-8 -*-
"""VEGA-49 防回归：并发 pytest 会话不得互相踩对方的测试库。

背景（VEGA-31 验收时实测）：所有会话共用一个固定测试库名
``intelligent_audio_test_test``，而库内操作并不隔离——
`db.drop_all()` 删的是**整库所有表**，`create_all` 又会把别人正在用的表建回来。
于是 A 会话跑到一半被 B 会话清表，报"库/表不存在"，失败集合每次都不一样。

本文件是纯本地检查（不连数据库、不起 pytest 会话），把当时的判据固化下来：

1. 测试库名必须按**进程**唯一，不再是一个所有会话共用的固定名；
2. TestingConfig 必须指向这个进程专属库，且不等于生产库名；
3. ``backend/tests/`` 下不得出现会清空整库对象的调用（drop_all / DROP DATABASE）——
   需要收尾就用 conftest 的 ``committed_rows`` fixture 按 id 删自己提交的行；
4. conftest 必须在会话收尾时删掉本会话专属测试库（否则每跑一次多一个库）；
5. 日志落库线程必须走自己的连接（见下），否则后台线程的 commit 会穿透测试事务。

第 5 条修的是**进程内**的第二个干扰源（与"会话互踩库"是两回事，但同样让结果
不可复现）：TestingConfig 的 app 引擎是 StaticPool，全进程只有一条连接，而后台
log_worker 线程用 sessionmaker(bind=db.engine) 写 logs 表——它一次 commit 就会把
测试外层事务里尚未回滚的数据永久落库，后面的用例于是读到前面用例的残留行。
实测：4 个用例文件连跑 4 次，失败数 0/1/3/1，且失败集合每次不同；测试配置打开
DB_LOG_SEPARATE_ENGINE（日志线程改用独立引擎）后 4 次全绿，日志照常落库。
"""
import ast
import os
import re

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TESTS_DIR))
_CONFTEST = os.path.join(_TESTS_DIR, 'conftest.py')
# 迁移脚本里的 DROP DATABASE 属于人工操作，不在本检查范围内（只扫测试目录）
_FORBIDDEN_CALLS = ('drop_all', 'drop_database')


def _iter_test_modules():
    """backend/tests/ 下所有测试模块（含 conftest.py）。"""
    for name in sorted(os.listdir(_TESTS_DIR)):
        if name.endswith('.py'):
            yield os.path.join(_TESTS_DIR, name)


def _read(path):
    # utf-8-sig：部分测试文件带 BOM，直接 utf-8 解析会 SyntaxError
    with open(path, 'r', encoding='utf-8-sig') as f:
        return f.read()


def test_test_database_name_is_scoped_to_the_process(monkeypatch):
    """测试库名必须带进程标识：两个并发会话拿到的库名必须不同。"""
    from backend.config.config import (
        TEST_DB_NAME_PREFIX,
        _get_test_database_name,
    )

    monkeypatch.setattr('os.getpid', lambda: 11111)
    first = _get_test_database_name()
    monkeypatch.setattr('os.getpid', lambda: 22222)
    second = _get_test_database_name()

    assert first != second, (
        f'测试库名没有随进程变化（都是 {first!r}）：并发会话会共用同一个库，'
        '回到 VEGA-49 之前"互相踩"的状态'
    )
    assert first.startswith(f'{TEST_DB_NAME_PREFIX}_'), (
        f'测试库名 {first!r} 不符合 {TEST_DB_NAME_PREFIX}_<进程标识> 约定，'
        'conftest 的遗留库回收按该约定匹配'
    )
    assert first != TEST_DB_NAME_PREFIX, (
        f'测试库名退化成了所有会话共用的固定名 {TEST_DB_NAME_PREFIX!r}（VEGA-49）'
    )


def test_testing_config_points_at_the_process_scoped_database():
    """TestingConfig 连的必须是本进程专属测试库，且与生产库不同名。"""
    from sqlalchemy.engine import make_url

    from backend.config.config import (
        TestingConfig,
        _get_database_uri,
        _get_test_database_name,
    )

    test_db = make_url(TestingConfig.SQLALCHEMY_DATABASE_URI).database
    prod_db = make_url(_get_database_uri()).database
    assert test_db == _get_test_database_name(), (
        f'TestingConfig 连的是 {test_db!r}，与 _get_test_database_name() 不一致'
    )
    assert test_db != prod_db, (
        f'测试配置连上了生产库 {prod_db!r}，测试的清理逻辑会写坏真实数据'
    )


def test_tests_never_drop_whole_database_objects():
    """backend/tests/ 下不得出现 drop_all / drop_database。

    这类调用删的是**整个库**的表，并发会话共用库时等于把别人正在跑的表清掉。
    需要收尾请用 conftest 的 committed_rows fixture 按 id 删自己提交的行。
    """
    offenders = []
    for path in _iter_test_modules():
        tree = ast.parse(_read(path), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
            if name in _FORBIDDEN_CALLS:
                offenders.append(f'{os.path.relpath(path, _PROJECT_ROOT)}:{node.lineno} {name}()')
    assert not offenders, (
        'backend/tests/ 里出现会清空整个库的调用，并发会话下会互相踩（VEGA-49）：\n  '
        + '\n  '.join(offenders)
    )


def test_conftest_reclaims_its_own_test_database_on_session_finish():
    """conftest 必须自己删掉本会话专属测试库，且只删自己的。"""
    source = _read(_CONFTEST)
    assert 'def pytest_sessionfinish' in source, (
        'conftest 没有 pytest_sessionfinish：会话结束不删库，每跑一次测试就多一个库'
    )
    assert re.search(r'DROP DATABASE IF EXISTS', source), (
        'conftest 没有 DROP DATABASE 语句，会话专属测试库不会被回收'
    )
    assert 'WITH (FORCE)' not in source, (
        'conftest 用了 DROP DATABASE ... WITH (FORCE)：强删会踢掉其它会话的连接，'
        '回收遗留库只允许删"没有任何连接"的库'
    )


def test_testing_config_gives_the_log_writer_its_own_connection():
    """测试配置必须让日志落库线程走独立连接（VEGA-49 进程内竞态）。

    否则后台线程与测试线程共用 StaticPool 那唯一一条连接，它一次 commit 就把
    测试外层事务里未回滚的数据落库，用例之间互相看见残留行，结果不可复现。
    """
    from backend.config.config import TestingConfig

    assert TestingConfig.DB_LOG_SEPARATE_ENGINE is True, (
        'TestingConfig 没打开 DB_LOG_SEPARATE_ENGINE：日志线程会与测试线程共用'
        '同一条连接，后台 commit 穿透测试事务，用例时红时绿'
    )

    handler_path = os.path.join(_PROJECT_ROOT, 'backend', 'utils', 'web', 'log_handler.py')
    handler_source = _read(handler_path)
    assert '_log_bind' in handler_source, (
        'log_handler 没有 _log_bind：日志线程仍然直接 bind 到 db.engine（测试里即'
        'StaticPool 那唯一一条连接）'
    )
