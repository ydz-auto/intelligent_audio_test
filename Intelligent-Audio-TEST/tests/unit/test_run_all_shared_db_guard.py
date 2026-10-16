# -*- coding: utf-8 -*-
"""INT-453 验收：run_all.py 启动守卫单元防线。

守卫 `_assert_not_shared_db()` 与 tests/conftest.py 会话守卫同语义：
生效 DATABASE_URL 指向共享业务库且未显式 --test-db 时，run_all 启动即
RuntimeError（零进程零写入）；隔离测试库 / 空 URL / 非 Postgres（sqlite）
均不受影响。

import run_all 的既有先例：tests/unit/test_int102_console_safe_logging.py。
"""
import pytest

import run_all as run_all_mod


@pytest.fixture(autouse=True)
def _restore_db_url():
    """用例间恢复 CHILD_ENV['DATABASE_URL']，避免污染同进程后续读取。"""
    original = run_all_mod.CHILD_ENV.get('DATABASE_URL')
    yield
    if original is None:
        run_all_mod.CHILD_ENV.pop('DATABASE_URL', None)
    else:
        run_all_mod.CHILD_ENV['DATABASE_URL'] = original


def _set_db_url(value):
    """直接改写 run_all.CHILD_ENV 的 DATABASE_URL（守卫唯一读取源）。"""
    run_all_mod.CHILD_ENV['DATABASE_URL'] = value


def test_shared_business_db_rejected_without_test_db():
    _set_db_url('postgresql://u:p@localhost:5432/intelligent_audio_test')
    with pytest.raises(RuntimeError, match='INT-453 启动守卫'):
        run_all_mod._assert_not_shared_db()


def test_driver_modified_shared_scheme_rejected():
    _set_db_url('postgresql+psycopg2://u:p@localhost:5432/intelligent_audio_test')
    with pytest.raises(RuntimeError, match='INT-453 启动守卫'):
        run_all_mod._assert_not_shared_db()


def test_isolated_test_db_allowed():
    _set_db_url('postgresql://u:p@localhost:5432/intelligent_audio_test_test')
    run_all_mod._assert_not_shared_db()  # 不抛即通过


def test_empty_url_allowed():
    _set_db_url('')
    run_all_mod._assert_not_shared_db()


def test_sqlite_allowed():
    _set_db_url('sqlite:///./tmp.db')
    run_all_mod._assert_not_shared_db()
