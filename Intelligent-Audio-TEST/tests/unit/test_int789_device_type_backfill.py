# -*- coding: utf-8 -*-
"""INT-789 验收测试：task_case_relations.device_type 历史数据回填迁移。

父卡 INT-775 FEAT 评审 17:59 结论：历史 NULL 行按关系表确定性回填
（task_api_relations → http_api / task_device_relations → physical /
websocket 前缀 → websocket_api），合并容器任务按设计 §3.3 不回填；
device_id 一并回填（设计 §3.3 原口径），供 task_dispatch 重执行设备绑定。

本文件以真实 Postgres 临时库（int364 同款：整库建表、用后即删）验证：
- dry-run（事务内回滚预览）不落任何变更，且逐步行数准确；
- --apply 全分支正确：device-only → physical / api-only → http_api /
  兼有 → http_api（API 优先）/ 合并容器 → 保持 NULL / 既有值 → 不覆写 /
  无关系 → 保持 NULL / ws 前缀 → websocket_api / http 前缀 → 不转 ws /
  部分迁移态（type 已 physical、device_id 仍 NULL）→ 只补 device_id；
- 幂等：apply 后重复执行三步全 0 行；NULL 仅剩合并容器与无关系任务。
"""
import importlib.util
import io
import os
import uuid
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'postgresql://placeholder:placeholder@localhost:5432/placeholder')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import psycopg2
import pytest

from tests.integration.test_task_execute_real_chain import (
    PG_HOST, PG_PASSWORD, PG_PORT, PG_USER,
    _pg_reachable, _import_all_models,
    storage_env,  # noqa: F401  pytest fixture
)

_SCRIPT = (Path(__file__).resolve().parents[2]
           / 'scripts' / 'migrations' / '202610' / 'backfill_task_case_device_type_int789.py')
_spec = importlib.util.spec_from_file_location('int789_backfill', _SCRIPT)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


@pytest.fixture(scope='function')
def int789_pg(storage_env):
    """真实 Postgres 临时库 + 全模型建表（脚本 psycopg2 直连，不走 ORM engine）。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-789 迁移回归跳过')

    from shared.models.database import remove_db_session
    remove_db_session()

    dbname = f'int789_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        dbname='postgres', connect_timeout=5)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')
    cur.close()

    _import_all_models()
    from sqlalchemy import create_engine

    import shared.models.database as database

    engine = create_engine(
        f'postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}',
        pool_pre_ping=True)
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)

    os.environ['DATABASE_URL'] = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    yield database
    database.remove_db_session()
    remove_db_session()
    engine.dispose()
    cur = admin.cursor()
    # 清理临时库：FORCE 需终止跨角色后端，`intelligent_audio_test` 角色权限不足时
    # 报 InsufficientPrivilege 留下孤儿库（实测过一次）。改为：先终止本角色残留
    # 连接（同角色终止被允许），再普通 DROP，不依赖 FORCE。
    cur.execute(
        'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
        'WHERE datname = %s AND usename = %s AND pid <> pg_backend_pid()',
        (dbname, PG_USER))
    cur.execute(f'DROP DATABASE IF EXISTS {dbname}')
    cur.close()
    admin.close()


# ──────────────────────────── 播种 ────────────────────────────

def _seed(db):
    """播种 10 个分支场景，返回 {case_id: (device_type, device_id)} 期望映射。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation, TestCase,
    )
    from api_test_service.infrastructure.persistence.models import API

    s = get_db_session()
    now = datetime.now()
    expected = {}

    def make_task(name):
        t = Task(name=name, status='completed', total_cases=1,
                 completed_cases=0, failed_cases=0, algorithm_type='translation',
                 created_at=now)
        s.add(t)
        s.flush()
        return t.id

    def make_case(cid):
        s.add(TestCase(id=cid, name=f'case-{cid}', config={'dimensions': []},
                       algorithm_type='translation'))
        s.flush()
        return cid

    def make_case_row(task_id, case_id, device_type=None, device_id=None):
        s.add(TaskCase(task_id=task_id, test_case_id=case_id, status='pending',
                       execution_status='pending', evaluation_status='pending',
                       device_type=device_type, device_id=device_id, created_at=now))
        s.flush()

    # T1 device-only → physical + device_id=101
    t1 = make_task('T1-device-only')
    make_case_row(t1, 'T1C1')
    s.add(TaskDevice(task_id=t1, device_id=101)); s.flush()
    expected['T1C1'] = ('physical', '101')

    # T2 device-only 双设备 → physical + 任一 device_id
    t2 = make_task('T2-device-2')
    make_case_row(t2, 'T2C1')
    s.add(TaskDevice(task_id=t2, device_id=201)); s.add(TaskDevice(task_id=t2, device_id=202)); s.flush()
    expected['T2C1'] = ('physical', None)  # 201/202 任一，单独断言

    # T3 api-only → http_api + api_id
    t3 = make_task('T3-api-only')
    make_case_row(t3, 'T3C1')
    api3 = API(name='api3', api_url='http://x', api_endpoints=[], status='online',
               meta={}, algorithm_type='translation')
    s.add(api3); s.flush()
    s.add(TaskAPI(task_id=t3, api_id=api3.id)); s.flush()
    expected['T3C1'] = ('http_api', str(api3.id))

    # T4 兼有 device+api → http_api（设计 §3.3 API 优先）+ api_id
    t4 = make_task('T4-both')
    make_case_row(t4, 'T4C1')
    api4 = API(name='api4', api_url='http://y', api_endpoints=[], status='online',
               meta={}, algorithm_type='translation')
    s.add(api4); s.flush()
    s.add(TaskDevice(task_id=t4, device_id=301)); s.flush()
    s.add(TaskAPI(task_id=t4, api_id=api4.id)); s.flush()
    expected['T4C1'] = ('http_api', str(api4.id))

    # T5 合并容器（merged_task_id 存在）+ device rel → 保持 NULL
    t5 = make_task('T5-merged')
    make_case_row(t5, 'T5C1')
    s.add(TaskDevice(task_id=t5, device_id=401)); s.flush()
    s.add(TaskMergeRelation(merged_task_id=t5, source_task_id=t1, created_at=now)); s.flush()
    expected['T5C1'] = (None, None)

    # T6 既有值（physical/777）→ 不覆写
    t6 = make_task('T6-already')
    make_case_row(t6, 'T6C1', device_type='physical', device_id='777')
    s.add(TaskDevice(task_id=t6, device_id=501)); s.flush()
    expected['T6C1'] = ('physical', '777')

    # T7 无任何关系 → 保持 NULL
    t7 = make_task('T7-norel')
    make_case_row(t7, 'T7C1')
    expected['T7C1'] = (None, None)

    # T8 api + ws 前缀 → websocket_api
    t8 = make_task('T8-ws')
    make_case_row(t8, 'T8C1')
    api8 = API(name='api8', api_url='ws://realtime',
               api_endpoints=[{'url': 'ws://realtime/audio'}], status='online',
               meta={}, algorithm_type='translation')
    s.add(api8); s.flush()
    s.add(TaskAPI(task_id=t8, api_id=api8.id)); s.flush()
    expected['T8C1'] = ('websocket_api', str(api8.id))

    # T9 api + http 前缀（非 ws）→ 保持 http_api
    t9 = make_task('T9-api-http')
    make_case_row(t9, 'T9C1')
    api9 = API(name='api9', api_url='http://h', api_endpoints=[{'url': 'http://h/x'}],
               status='online', meta={}, algorithm_type='translation')
    s.add(api9); s.flush()
    s.add(TaskAPI(task_id=t9, api_id=api9.id)); s.flush()
    expected['T9C1'] = ('http_api', str(api9.id))

    # T10 部分迁移态（type 已 physical、device_id 仍 NULL）→ 只补 device_id
    t10 = make_task('T10-partial')
    make_case_row(t10, 'T10C1', device_type='physical', device_id=None)
    s.add(TaskDevice(task_id=t10, device_id=601)); s.flush()
    expected['T10C1'] = ('physical', '601')

    s.commit()
    return expected


def _rows(db):
    from sqlalchemy import text
    with db.get_engine().connect() as conn:
        rows = conn.execute(
            text('SELECT test_case_id, device_type, device_id FROM task_case_relations')
        ).fetchall()
    return {cid: (dt, did) for cid, dt, did in rows}


def _run(*argv):
    """跑脚本 main(argv)，捕获 stdout 返回。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        script.main(list(argv))
    return buf.getvalue()


# ──────────────────────────── 用例 ────────────────────────────

class TestInt789DeviceTypeBackfill:
    def test_dry_run_does_not_write_and_counts_accurate(self, int789_pg):
        """dry-run 事务内回滚预览：不落库；分步行数反映执行前状态。"""
        expected = _seed(int789_pg)
        out = _run()
        assert '[DRY-RUN]' in out and '将更新' in out, f'输出:\n{out}'
        # ① 4 行（T3/T4/T8/T9 四个 api-rel NULL 行）；② 4 行（T1/T2/T4/T10，
        # 其中 T10 为 physical+NULL device_id）；③ 0 行（执行前无 http_api）
        assert '① task_api_relations → http_api（+api_id）：将更新 4 行' in out, out
        assert '② task_device_relations → physical（+device_id）：将更新 4 行' in out, out
        assert '③ apis.api_endpoints url ws% 前缀 → websocket_api：将更新 0 行' in out, out

        # dry-run 未落任何变更（播种态：除 T6=physical/777、T10=physical/None 外全 NULL）
        rows = _rows(int789_pg)
        for cid, (dt, did) in rows.items():
            assert (dt is None and did is None) or (dt == 'physical' and did in ('777', None)), \
                f'dry-run 不应落库: {cid} -> {dt}/{did}'
        assert rows['T6C1'] == ('physical', '777')
        assert rows['T10C1'] == ('physical', None)

    def test_apply_all_branches_correct(self, int789_pg):
        """--apply 后全分支终态正确；重复 apply 三步全 0 行（幂等）。"""
        expected = _seed(int789_pg)
        out = _run('--apply')
        assert '[EXEC]' in out, f'输出:\n{out}'
        # ① 4 行；② 3 行（T4 已被 ① 置 http_api，只剩 T1/T2/T10）；③ 1 行（T8）
        assert '① task_api_relations → http_api（+api_id）：4 行' in out, out
        assert '② task_device_relations → physical（+device_id）：3 行' in out, out
        assert '③ apis.api_endpoints url ws% 前缀 → websocket_api：1 行' in out, out

        rows = _rows(int789_pg)
        for cid, (dt, did) in expected.items():
            if cid == 'T2C1':
                actual = rows[cid]
                assert actual[0] == 'physical' and actual[1] in ('201', '202'), \
                    f'T2: 期望 physical + 任一设备，实际 {actual}'
            else:
                assert rows[cid] == (dt, did), f'{cid}: 期望 {dt}/{did} 实际 {rows[cid]}'

        # 终态：NULL 仅剩合并容器（T5）与无关系（T7）
        n_null = sum(1 for cid in rows if rows[cid][0] is None)
        assert n_null == 2, f'仅 T5/T7 应保持 NULL，实际 {n_null}'

        # 幂等：重复 apply 三步全 0
        out = _run('--apply')
        assert '：0 行' in out, f'重复 apply 应三步全 0 行:\n{out}'
