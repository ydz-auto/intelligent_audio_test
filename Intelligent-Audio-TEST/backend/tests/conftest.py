# -*- coding: utf-8 -*-
"""算法模块测试共享夹具

使用 PostgreSQL 真实数据库 + 嵌套事务（SAVEPOINT）实现测试隔离。
每个测试在事务中运行，测试结束后回滚，不影响数据库状态。

VEGA-49：测试库按 pytest 会话（进程）唯一化——``intelligent_audio_test_test_p<pid>``。
此前所有会话共用一个固定库名，任一测试文件的 ``db.drop_all()`` / ``create_all``
都会打到别人正在跑的库上（库内还残留着历史 run 提交的行，制造稳定的
UniqueViolation 假失败）。现在一个进程一套库：建库前回收遗留库、会话结束删库。
"""
import os
import re
import sys
import pytest

# 确保 backend 目录在 sys.path 中
_backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.app import create_app
from backend.config.config import (
    TEST_DB_NAME_PREFIX,
    _get_database_uri,
    _get_test_database_name,
    _get_test_database_uri,
)
from backend.models.database import db
from backend.models.algorithm_models import (
    AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
    AlgorithmReferenceParam, EvaluationDimensionParam,
)
from backend.models.models import Dimension
from sqlalchemy.orm import sessionmaker

# 本会话专属测试库名（含 PID）
TEST_DB_NAME = _get_test_database_name()

# 只有本仓库自动生成的测试库会被回收：<前缀>_p<pid>
_TEST_DB_NAME_PATTERN = re.compile(rf'^{re.escape(TEST_DB_NAME_PREFIX)}_p\d+$')

# 建库 + 回收遗留库的跨进程互斥锁（PostgreSQL advisory lock 键，仅本仓库使用）。
# 没有它，两个会话同时启动时，A 可能把 B"刚建好、还没连上"的库当成遗留库回收掉。
_TEST_DB_SETUP_LOCK_KEY = 0x564547413439  # 'VEGA49'

# 会话期间常驻的一条到本库的连接：其它会话据此区分"在用"与"遗留"（见 _setup_test_database）
_keepalive_engine = None
_keepalive_conn = None


def _admin_engine():
    """管理连接：连生产库（必然存在），仅用于 CREATE/DROP 测试库。"""
    from sqlalchemy import create_engine
    return create_engine(_get_database_uri(), isolation_level='AUTOCOMMIT')


def _database_exists(conn, name):
    from sqlalchemy import text
    return conn.execute(
        text('SELECT 1 FROM pg_database WHERE datname = :name'), {'name': name}
    ).fetchone() is not None


def _drop_database(conn, name, terminate=False):
    """删库。

    terminate=True 会先踢掉该库上的连接——**只对 TEST_DB_NAME（本进程自己的库）
    使用**：并发会话绝不允许去动别人的库。
    """
    from sqlalchemy import text
    if terminate:
        conn.execute(
            text(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = :name AND pid <> pg_backend_pid()'
            ),
            {'name': name},
        )
    conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def _recycle_stale_test_databases(conn):
    """回收本仓库遗留的测试库（只回收当前没有任何连接的）。

    会话被强杀/崩溃时跑不到 sessionfinish，库会留下；这里顺带清掉，
    避免每跑一次测试就多一个库。判据是 pg_stat_activity：**在用**的会话
    拿到库后会立刻占一条常驻连接（见 _setup_test_database），所以
    "没有连接"等价于"没人用"。回收是尽力而为，失败不影响本次会话。
    """
    from sqlalchemy import bindparam, text
    rows = conn.execute(
        text('SELECT datname FROM pg_database WHERE datname LIKE :pat'),
        {'pat': f'{TEST_DB_NAME_PREFIX}_p%'},
    ).fetchall()
    names = [r[0] for r in rows
             if _TEST_DB_NAME_PATTERN.match(r[0]) and r[0] != TEST_DB_NAME]
    if not names:
        return
    busy_stmt = text(
        'SELECT DISTINCT datname FROM pg_stat_activity WHERE datname IN :names'
    ).bindparams(bindparam('names', expanding=True))
    busy = {r[0] for r in conn.execute(busy_stmt, {'names': names}).fetchall()}
    for name in names:
        if name in busy:
            continue
        try:
            _drop_database(conn, name)
            print(f'[conftest] 已回收遗留测试库 {name}')
        except Exception as exc:  # 尽力而为：回收失败不能拖垮本次会话
            print(f'[conftest] 回收遗留测试库 {name} 失败（忽略）：{exc}')


def _database_has_connections(conn, name):
    from sqlalchemy import text
    return conn.execute(
        text('SELECT 1 FROM pg_stat_activity WHERE datname = :name LIMIT 1'),
        {'name': name},
    ).fetchone() is not None


def _setup_test_database():
    """建立本会话专属测试库（VEGA-49），返回其 URI。

    - 库名带 PID ⇒ 并发会话天然互不可见；
    - 先回收遗留库，再处理同名库，最后建库；
    - 以上都在 advisory lock 内完成，且**拿到库后立刻占一条常驻连接再放锁**，
      所以另一个会话不可能把"刚建好、还没连上"的库当成遗留库回收。
    """
    global _keepalive_engine, _keepalive_conn
    from sqlalchemy import create_engine, text
    engine = _admin_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT pg_advisory_lock(:key)'),
                         {'key': _TEST_DB_SETUP_LOCK_KEY})
            try:
                _recycle_stale_test_databases(conn)
                if _database_exists(conn, TEST_DB_NAME) and _database_has_connections(conn, TEST_DB_NAME):
                    # 本进程已经建过了（模块被重复导入）：直接复用，别把库删了重建
                    print(f'[conftest] 本会话专属测试库 {TEST_DB_NAME} 已就绪，复用')
                    return _get_test_database_uri()
                if _database_exists(conn, TEST_DB_NAME):
                    # PID 复用：同名库没有连接 ⇒ 只可能是上一次进程留下的，重建保证干净
                    _drop_database(conn, TEST_DB_NAME, terminate=True)
                    print(f'[conftest] 已清理 PID 复用的残留测试库 {TEST_DB_NAME}')
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
                print(f'[conftest] 已创建本会话专属测试库 {TEST_DB_NAME}')
                # 常驻连接必须在放锁前建立（见 docstring）
                _keepalive_engine = create_engine(_get_test_database_uri())
                _keepalive_conn = _keepalive_engine.connect()
            finally:
                conn.execute(text('SELECT pg_advisory_unlock(:key)'),
                             {'key': _TEST_DB_SETUP_LOCK_KEY})
    finally:
        engine.dispose()
    return _get_test_database_uri()


def _teardown_test_database():
    """断开常驻连接并删掉本会话专属测试库。

    删库是尽力而为：即使失败（例如还有没断开的连接）也只是留下一个库，
    下次会话启动时的回收逻辑会收拾它，不该让一次成功的测试跑变成 error。
    """
    global _keepalive_engine, _keepalive_conn
    if _keepalive_conn is not None:
        try:
            _keepalive_conn.close()
        except Exception:
            pass
        _keepalive_conn = None
    if _keepalive_engine is not None:
        try:
            _keepalive_engine.dispose()
        except Exception:
            pass
        _keepalive_engine = None
    try:
        engine = _admin_engine()
        try:
            with engine.connect() as conn:
                _drop_database(conn, TEST_DB_NAME, terminate=True)
            print(f'[conftest] 已删除本会话专属测试库 {TEST_DB_NAME}')
        finally:
            engine.dispose()
    except Exception as exc:
        print(f'[conftest] 删除测试库 {TEST_DB_NAME} 失败（下次会话会回收）：{exc}')


def pytest_sessionfinish(session, exitstatus):
    """pytest 会话收尾：删掉本会话专属测试库（VEGA-49）。"""
    _teardown_test_database()


_setup_test_database()


def _cleanup_algorithm_tables():
    """清理算法相关表数据（在事务中执行，测试后回滚不影响真实数据）

    仅作用于独立测试库（TestingConfig.SQLALCHEMY_DATABASE_URI），生产库不受影响。
    """
    db.session.query(AlgorithmDimensionRelation).delete()
    db.session.query(ParamMapping).delete()
    db.session.query(AlgorithmReferenceParam).delete()
    db.session.query(CaseAlgorithmParam).delete()
    db.session.query(AlgorithmApiParam).delete()
    db.session.query(AlgorithmDeviceParam).delete()
    db.session.query(AlgorithmDefinition).delete()
    db.session.query(AlgorithmGroup).delete()
    db.session.flush()  # 用 flush 代替 commit，避免在嵌套事务中真正提交


def _delete_committed_rows(registry):
    """按显式 id 删掉本测试 commit 的行，顺序由内到外（先删关联表）。

    走独立连接执行（不经过 db.session），因此不会 expire 测试里的 ORM 实例——
    测试函数末尾还要用 `task.id` 这类属性做断言。
    """
    from sqlalchemy import create_engine, delete, or_
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup

    task_ids = list(registry['task_ids'])
    case_ids = list(registry['case_ids'])
    group_ids = list(registry['group_ids'])
    statements = []
    if task_ids or case_ids:
        conditions = []
        if task_ids:
            conditions.append(TaskCase.task_id.in_(task_ids))
        if case_ids:
            conditions.append(TaskCase.test_case_id.in_(case_ids))
        statements.append(delete(TaskCase).where(or_(*conditions)))
    if case_ids:
        statements.append(delete(TestCase).where(TestCase.id.in_(case_ids)))
    if group_ids:
        statements.append(delete(TestCaseGroup).where(TestCaseGroup.id.in_(group_ids)))
    if task_ids:
        statements.append(delete(Task).where(Task.id.in_(task_ids)))

    engine = create_engine(_get_test_database_uri())
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(statement)
    finally:
        engine.dispose()


@pytest.fixture
def committed_rows():
    """登记本测试真正 commit 的行，测试结束后按表删掉（VEGA-49，取代 db.drop_all()）。

    有些测试必须真的 commit（例如"原子抢占"要用两个独立会话验证），用不了 app
    fixture 的外层事务回滚，因此原实现靠 `db.drop_all()` 收尾。但 drop_all 有两宗罪：

    1. 删的是**整个库**的表——并发会话共用一个库名时，等于把别人正在跑的表清掉；
    2. 本仓库模型存在循环外键（playback_devices ↔ spl_mappings），drop_all 必然抛
       CircularDependencyError，把真正的断言失败盖成"表排序失败"。

    本 fixture 只按登记到的 id 删本测试自己的行，不碰库里任何其它对象。
    收尾在测试函数**返回之后**执行，所以函数末尾的断言照旧能看到实例属性。

    用法::

        def test_x(committed_rows):
            ...
            db.session.commit()
            committed_rows(task_id=task.id, case_ids=["tc-1"], group_ids=["g-1"])
    """
    registry = {'task_ids': [], 'case_ids': [], 'group_ids': []}

    def _register(*, task_id=None, case_ids=(), group_ids=()):
        if task_id is not None:
            registry['task_ids'].append(task_id)
        registry['case_ids'].extend(case_ids)
        registry['group_ids'].extend(group_ids)

    yield _register
    if any(registry.values()):
        _delete_committed_rows(registry)


@pytest.fixture(autouse=True)
def _release_db_connections():
    """每个测试结束后释放该测试创建的数据库引擎连接（VEGA-35 连接泄漏治理）。

    测试文件普遍在**每个测试**里 create_app("testing")，而 TestingConfig 用
    StaticPool（单连接常驻）。引擎不 dispose，那条连接就一直挂在测试库上：
    全量跑一遍会累积上百条 idle 连接，把 max_connections 额度吃光，
    导致无关脚本/服务连不上库（实测出现过
    "remaining connection slots are reserved for roles with the SUPERUSER attribute"）。

    autouse + 目录级 conftest ⇒ 本文件下所有测试（含直接调用 create_app 的）
    都会在收尾时被清理。teardown 顺序：autouse fixture 最后收尾，
    因此这里跑在 app fixture 的 session.remove()/rollback 之后。
    """
    yield
    try:
        db.session.remove()
    except Exception:
        pass
    # db._app_engines: Flask-SQLAlchemy 按 app 登记的引擎表（每个 create_app 一份）
    app_engines = getattr(db, '_app_engines', None) or {}
    for engines in list(app_engines.values()):
        for engine in list(engines.values()):
            try:
                engine.dispose()
            except Exception:
                pass


@pytest.fixture
def app():
    """创建测试用 Flask 应用

    使用外层事务实现测试隔离：
    1. 开启外层事务
    2. 清理算法相关表数据（让每个测试从空表开始）
    3. 测试运行（fixture 中使用 flush 而非 commit）
    4. 回滚外层事务，所有变更（包括清理）都不影响真实数据库

    注意: controller 源码中的 db.session.commit() 会真正提交数据，
    导致后续测试可能出现 UniqueViolation。这是已知限制，
    按测试文件单独运行时可避免此问题。
    """
    app = create_app("testing")
    with app.app_context():
        # 独立测试库首次使用前确保表结构完整。
        # 用独立 engine（非 StaticPool）执行 create_all，避免 Flask db 共享连接
        # 因应用启动时表缺失导致的事务终止状态干扰建表。
        from sqlalchemy import create_engine
        meta_engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
        try:
            db.metadata.create_all(meta_engine)
        finally:
            meta_engine.dispose()
        connection = db.engine.connect()
        trans = connection.begin()
        # 配置 session 使用此连接
        options = dict(bind=connection, binds={})
        session = db._make_scoped_session(options=options)
        db.session = session
        # 清理算法相关表，让测试从空表开始（仅作用于独立测试库）
        _cleanup_algorithm_tables()
        yield app
        session.remove()
        trans.rollback()
        connection.close()
        # VEGA-35：TestingConfig 用 StaticPool，引擎不 dispose 就会一直占着一条到测试库的
        # 连接（每个测试建一个 app ⇒ 一条连接），全量跑一遍足以耗尽 max_connections。
        try:
            db.engine.dispose()
        except Exception:
            pass


@pytest.fixture
def client(app):
    """测试用 HTTP 客户端"""
    return app.test_client()


@pytest.fixture
def group(app):
    """创建一个算法分组"""
    g = AlgorithmGroup(name="测试分组", display_order=0)
    db.session.add(g)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(g)
    return g


@pytest.fixture
def dimension(app):
    """创建一个评估维度"""
    d = Dimension(name="WER_test", type="auto", result_type=1, weight=1)
    db.session.add(d)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(d)
    return d


@pytest.fixture
def algorithm(app, group):
    """创建一个算法定义"""
    algo = AlgorithmDefinition(
        type="test_algo",
        name="测试算法",
        group_id=group.id,
        status="online",
        display_order=0,
    )
    db.session.add(algo)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(algo)
    return algo


@pytest.fixture
def device_param(app, algorithm):
    """创建一个设备参数"""
    p = AlgorithmDeviceParam(
        algorithm_type="test_algo",
        param_code="input_text",
        param_name="输入文本",
        param_type="text",
        direction="input",
        required=True,
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def api_param(app, algorithm):
    """创建一个 API 参数"""
    p = AlgorithmApiParam(
        algorithm_type="test_algo",
        param_code="api_result",
        param_name="API结果",
        param_type="text",
        direction="output",
        required=False,
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def case_param(app, algorithm):
    """创建一个用例参数"""
    p = CaseAlgorithmParam(
        algorithm_type="test_algo",
        param_code="translation_direction",
        param_name="翻译方向",
        param_type="text",
        scope="common",
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def reference_param(app, algorithm):
    """创建一个参考参数"""
    p = AlgorithmReferenceParam(
        algorithm_type="test_algo",
        code="asr_ref",
        name="ASR参考文本",
        param_type="text",
        annotation_code="asr_ref",
        merge_mode="join",
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def mapping(app, algorithm, dimension):
    """创建一个参数映射"""
    m = ParamMapping(
        algorithm_type="test_algo",
        source="device",
        source_param="input_text",
        source_direction="output",
        dimension_id=dimension.id,
        target_param="ref_text",
        transform_type="none",
    )
    db.session.add(m)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(m)
    return m


@pytest.fixture
def dimension_relation(app, algorithm, dimension):
    """创建一个维度关联"""
    r = AlgorithmDimensionRelation(
        algorithm_type="test_algo",
        dimension_id=dimension.id,
        is_default=True,
        weight=1.0,
    )
    db.session.add(r)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(r)
    return r
