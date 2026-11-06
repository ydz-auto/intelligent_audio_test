# -*- coding: utf-8 -*-
"""INT-1652：DDL 锁预算与只读事务收口的守卫。

事故（2026-10-23）：db_bootstrap 的 ALTER TABLE 需要 ACCESS EXCLUSIVE，被
algorithm_service 的 idle in transaction 一挡就无限等待；发起它的 run 容器被删后
Postgres 后端不退出，永久占住 case_algorithm_params 的锁队列头部，/algorithm/*
全站 60s 超时。这里守两层：

1. 迁移侧（docker/db_bootstrap_entrypoint.py）
   - 锁预算经 PGOPTIONS 下发到每个迁移子进程的连接（lock_timeout /
     statement_timeout / idle_in_transaction_session_timeout），失败即非零退出；
   - 单步进程级超时兜底（SQL 超时照不到的 Python 层等待）；
   - 失败清理只 terminate application_name=db_bootstrap 的空转会话。
2. 服务侧（shared/models/database.py::end_read_transaction）
   - 只读查询后回滚，连接不挂在 idle in transaction；
   - 有待提交写时不回滚（不得吞掉调用链上的写）。

真实 Postgres 的等锁红-绿验收见 tests/integration/test_int1652_ddl_lock_timeout_pg.py。
"""
import importlib.util
import os
import sys
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1652_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import Column, Integer, String

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_ENTRYPOINT = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')


def _load_entrypoint():
    """按路径加载引导入口模块（docker/ 不是包，不能被 import 语句直接引入）。"""
    spec = importlib.util.spec_from_file_location('int1652_db_bootstrap_entrypoint',
                                                  _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def entrypoint():
    return _load_entrypoint()


# ==================== 迁移侧：锁预算 ====================

def test_default_budget_is_bounded(entrypoint, monkeypatch):
    """默认预算：lock_timeout 5s、statement_timeout 300s、空转 60s、单步 900s。"""
    for key in ('DB_BOOTSTRAP_LOCK_TIMEOUT_MS', 'DB_BOOTSTRAP_STATEMENT_TIMEOUT_MS',
                'DB_BOOTSTRAP_IDLE_IN_TX_TIMEOUT_MS',
                'DB_BOOTSTRAP_STEP_TIMEOUT_SECONDS'):
        monkeypatch.delenv(key, raising=False)
    budget = entrypoint.lock_budget()
    assert budget['lock_timeout_ms'] == 5000
    assert budget['statement_timeout_ms'] == 300000
    assert budget['idle_in_tx_timeout_ms'] == 60000
    assert budget['step_timeout_s'] == 900

    options = entrypoint.build_pgoptions(budget)
    # 三个上限都要真的下发（少任何一个，事故形态就能复现一半）
    assert '-c lock_timeout=5000' in options
    assert '-c statement_timeout=300000' in options
    assert '-c idle_in_transaction_session_timeout=60000' in options


def test_budget_env_override_and_invalid_fallback(entrypoint, monkeypatch):
    monkeypatch.setenv('DB_BOOTSTRAP_LOCK_TIMEOUT_MS', '2000')
    monkeypatch.setenv('DB_BOOTSTRAP_STATEMENT_TIMEOUT_MS', 'abc')
    monkeypatch.setenv('DB_BOOTSTRAP_IDLE_IN_TX_TIMEOUT_MS', '0')
    budget = entrypoint.lock_budget()
    assert budget['lock_timeout_ms'] == 2000           # 合法值生效
    assert budget['statement_timeout_ms'] == 300000     # 非数字回落默认
    assert budget['idle_in_tx_timeout_ms'] == 60000     # 非正数回落默认


def test_prepare_env_injects_pgoptions_and_keeps_inherited(entrypoint, monkeypatch):
    """PGOPTIONS 追加而非覆盖；连接打上 application_name=db_bootstrap 供定向清理。"""
    monkeypatch.setenv('DATABASE_URI', 'postgresql://u:p@h:5432/db')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('PGOPTIONS', '-c search_path=public')
    monkeypatch.delenv('PGAPPNAME', raising=False)
    env = entrypoint._prepare_env(entrypoint.lock_budget())
    assert env['DATABASE_URL'] == 'postgresql://u:p@h:5432/db'
    assert env['PGOPTIONS'].startswith('-c search_path=public')
    assert '-c lock_timeout=5000' in env['PGOPTIONS']
    assert env['PGAPPNAME'] == entrypoint.BOOTSTRAP_APP_NAME
    # 子进程环境不能污染调用方进程
    assert 'PGAPPNAME' not in os.environ


def test_run_step_timeout_is_failure(entrypoint, tmp_path):
    """单步超时返回 (非零, timed_out=True)：SQL 超时照不到的等待也不能挂死。"""
    script = tmp_path / 'hang.py'
    script.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
    rc, timed_out = entrypoint._run_step(
        (sys.executable, str(script)), str(tmp_path),
        dict(os.environ), 'y', step_timeout_s=1)
    assert timed_out is True
    assert rc != 0


# ==================== 服务侧：只读事务收口 ====================

def _open_engine():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    return Base, get_engine()


def test_end_read_transaction_closes_idle_read_transaction():
    """SELECT 之后必须能结束事务：in_transaction True → False。"""
    from shared.models.database import Base, end_read_transaction, get_db_session
    from sqlalchemy import Column, Integer

    class _Int1652Read(Base):
        __tablename__ = 'int1652_read_guard'
        id = Column(Integer, primary_key=True)

    Base.metadata.create_all(_open_engine()[1], tables=[_Int1652Read.__table__])

    session = get_db_session()()
    session.query(_Int1652Read).all()
    assert session.in_transaction() is True         # 读后事务已开
    assert end_read_transaction() is True
    assert session.in_transaction() is False        # 已回滚，连接可归还
    # 幂等：没有事务时再调用不报错
    assert end_read_transaction() is False


def test_end_read_transaction_without_session_returns_false():
    """当前 scope 还没有 session 时直接返回 False：不新建、不递归。"""
    from shared.models.database import end_read_transaction, remove_db_session

    remove_db_session()
    assert end_read_transaction() is False


def test_end_read_transaction_keeps_pending_writes():
    """有待提交写时不回滚——只读收口绝不能吞掉调用链上的写。"""
    from shared.models.database import Base, end_read_transaction, get_db_session
    from sqlalchemy import Column, Integer

    class _Int1652Write(Base):
        __tablename__ = 'int1652_write_guard'
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String(20))

    Base.metadata.create_all(_open_engine()[1], tables=[_Int1652Write.__table__])

    session = get_db_session()()
    session.add(_Int1652Write(name='pending'))
    assert end_read_transaction() is False          # 有 pending 写：不动
    assert session.new and session.in_transaction() is True
    session.rollback()                              # 用例自清，不落库


def test_algorithm_service_registers_request_scope_middleware():
    """HTTP 边界必须挂请求级 session scope（int 事故里这个服务缺的就是它）。"""
    from shared.infrastructure.db_session_middleware import DbSessionScopeMiddleware
    from algorithm_service.app import create_app

    app = create_app()
    assert any(m.cls is DbSessionScopeMiddleware for m in app.user_middleware), \
        'algorithm_service 未注册 DbSessionScopeMiddleware：只读路由会遗留 idle in transaction'
