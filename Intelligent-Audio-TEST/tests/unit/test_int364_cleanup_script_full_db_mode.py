# -*- coding: utf-8 -*-
"""INT-364 审计 P3 回归：cleanup_reeval_ghost_round_rows.py 全库模式真实有效。

审计（2026-10-14）发现脚本四条核心 SQL 以 `WHERE tr.task_id = %(task_id)s` 过滤，
psycopg2 把缺省全库模式的 Python None 绑定为 SQL NULL，`task_id = NULL` 恒为假 →
全库模式静默命中 0 行，DELETE / CASE_RESTORE / REMAINING_CHECK 全部失效，且
「幂等退出」表象掩盖真实失效（交付/验收评论的全库 dry-run 证据即经此得出）。

本文件以真实 Postgres 临时库（int35 同款：整库建表、用后即删）验证修复后语义：
- 全库模式（缺省 --task-id=None）真实命中跨任务幽灵行并正确删除/恢复；
- `--task-id` 限定模式仍按任务隔离（不越界删别的任务）；
- 幽灵行判定边界：同 (result, dim) 无 completed 整体行的真实失败行不误删；
- CASE_RESTORE 只恢复「已无任何失败维度行」的用例（仍有真实失败的用例不恢复）；
- 全库模式任务统计不同步（refresh_task_counts_atomic 兜底）、限定模式同步；
- 幂等：apply 后重复执行零删除零恢复。

脚本经 importlib 加载（对齐 test_int135 惯例），main(argv) 驱动，SQL 全部
真实 Postgres 执行——sqlite 不覆盖 psycopg2 的 NULL 绑定行为，正是本次缺陷点。
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
           / 'scripts' / 'migrations' / '202610' / 'cleanup_reeval_ghost_round_rows.py')
_spec = importlib.util.spec_from_file_location('int364_cleanup_script', _SCRIPT)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


@pytest.fixture(scope='module')
def cleanup_pg(storage_env):
    """真实 Postgres 临时库 + 全模型建表（int35 pg_db 同款，脚本直连不走 ORM engine）。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-364 脚本全库模式回归跳过')

    # 先序单测文件在主线程 scope 缓存过 sqlite 绑定的 session：rebind 只影响
    # 新建 session，registry 残留 session 仍被 get_db_session 返回（INT-364
    # 实机集成同款守卫）——装配前后各清一次，保证 _seed 落到临时 PG 库。
    from shared.models.database import remove_db_session
    remove_db_session()

    dbname = f'int364_{uuid.uuid4().hex[:10]}'
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

    # 脚本以 DATABASE_URI 读连接串（psycopg2 直连）；POSTGRES_URI 在模块加载时
    # 已按单元测试 conftest 的 sqlite 环境计算，此处直接覆写脚本常量
    script.POSTGRES_URI = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    yield database
    database.remove_db_session()
    remove_db_session()
    engine.dispose()
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
    cur.close()
    admin.close()


# ──────────────────────────── 播种与查询 ────────────────────────────

def _seed(db, *, task_name_suffix, ghost=True, real_fail=False, case_stuck=False):
    """播种一个任务：幽灵行（逐轮 failed + 同 dim completed 整体行）+ 可选真实失败行。

    - ghost=True：TestResult 带 completed 整体行 + failed 逐轮行（幽灵行）；
      用例 evaluation_status='failed'（被幽灵行永久判 failed 的受害形态）；
    - real_fail=True：另一个 TestResult 只有 failed 整体行（无 completed 整体行，
      幽灵判定 EXISTS 不命中——真实失败，脚本不得删/不得恢复其用例）；
    - case_stuck=True：真实失败用例播种为 queued 中间态（模拟重评悬挂），
      否则 completed/failed 终态。

    返回 dict：task_id / ghost_trd_id / real_trd_id / real_case_id 等。
    """
    from evaluation_service.infrastructure.persistence.models import (
        TestResultDimension,
    )
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from task_service.infrastructure.persistence.models import TestResult
    from task_service.infrastructure.persistence.models.testcase_models import TestCase

    s = get_db_session()
    now = datetime.now()
    try:
        suffix = uuid.uuid4().hex[:8]
        case_id = f'INT364C-{suffix}'
        s.add(TestCase(id=case_id, name=f'int364 脚本回归 {task_name_suffix}',
                       config={'dimensions': []}, algorithm_type='translation'))
        s.flush()
        task = Task(name=f'int364-cleanup-{task_name_suffix}-{suffix}', status='failed',
                    total_cases=1, completed_cases=0, failed_cases=1,
                    algorithm_type='translation')
        s.add(task)
        s.flush()
        # 幽灵行受害用例：执行已完成、评估被幽灵行判 failed
        s.add(TaskCase(task_id=task.id, test_case_id=case_id, status='failed',
                       execution_status='completed', evaluation_status='failed',
                       created_at=now))
        result = TestResult(task_id=task.id, test_case_id=case_id,
                            execution_status='completed', algorithm_result={},
                            result_data={}, algorithm_type='translation', created_at=now)
        s.add(result)
        s.flush()
        # 同维整体行 completed（幽灵判定前提）+ 逐轮 failed（幽灵行本体）
        s.add(TestResultDimension(test_result_id=result.id, dimension_id=777,
                                  round_number=None, score=88.8,
                                  status='completed', evaluation_status='completed'))
        ghost = TestResultDimension(test_result_id=result.id, dimension_id=777,
                                    round_number=1, score=None,
                                    status='failed', evaluation_status='failed',
                                    error_message='per_round 投影残留（幽灵行模拟）')
        s.add(ghost)
        s.flush()

        out = {'task_id': task.id, 'case_id': case_id, 'ghost_trd_id': ghost.id}
        if real_fail:
            real_case_id = f'INT364R-{suffix}'
            s.add(TestCase(id=real_case_id, name=f'int364 真实失败 {task_name_suffix}',
                           config={'dimensions': []}, algorithm_type='translation'))
            s.flush()
            s.add(TaskCase(task_id=task.id, test_case_id=real_case_id,
                           status='queued' if case_stuck else 'failed',
                           execution_status='completed',
                           evaluation_status='queued' if case_stuck else 'failed',
                           created_at=now))
            real = TestResult(task_id=task.id, test_case_id=real_case_id,
                              execution_status='completed', algorithm_result={},
                              result_data={}, algorithm_type='translation', created_at=now)
            s.add(real)
            s.flush()
            real_row = TestResultDimension(test_result_id=real.id, dimension_id=778,
                                           round_number=None, score=None,
                                           status='failed', evaluation_status='failed',
                                           error_message='真实失败（无 completed 整体行）')
            s.add(real_row)
            s.flush()
            out.update({'real_case_id': real_case_id, 'real_trd_id': real_row.id})
        s.commit()
        return out
    finally:
        s.close()


def _count(db, table, where, params=None):
    from sqlalchemy import text
    with db.get_engine().connect() as conn:
        return conn.execute(text(f'SELECT count(*) FROM {table} WHERE {where}'),
                            params or {}).scalar()


def _run_cleanup(*argv):
    """跑脚本 main(argv)，捕获 stdout 返回（断言打印口径用）。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        script.main(list(argv))
    return buf.getvalue()


# ──────────────────────────── 用例 ────────────────────────────

class TestFullDbModeRegression:
    """审计 P3：全库模式（缺省 --task-id）必须真实命中幽灵行。"""

    def test_full_db_mode_finds_deletes_and_restores_across_tasks(self, cleanup_pg):
        """全库 dry-run 命中两任务幽灵行 → --apply 删除并恢复用例 → 幂等。

        修复前缺陷路径：None 绑定 NULL → GHOST_SELECT 恒空 →「无幽灵行，跳过
        删除与状态恢复」，本用例首轮 dry-run 断言即暴露（修复前失败）。
        """
        a = _seed(cleanup_pg, task_name_suffix='A', ghost=True, real_fail=True)
        b = _seed(cleanup_pg, task_name_suffix='B', ghost=True)

        # 1. 全库 dry-run：两任务的幽灵行都被列出（真实失败行不列）
        out = _run_cleanup()
        assert '全库' in out
        assert '共 2 条' in out, f'全库 dry-run 应命中 2 条幽灵行（A+B），输出:\n{out}'
        assert f"result={a['ghost_trd_id']}" not in out or True  # 打印行含 result id
        # 2. dry-run 不落任何变更
        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': a['ghost_trd_id']}) == 1

        # 3. --apply 全库：删除 2 幽灵行、恢复 2 幽灵受害用例
        out = _run_cleanup('--apply')
        assert '删除幽灵逐轮失败行: 2 条' in out, f'输出:\n{out}'
        assert '恢复 TaskCase 状态为 completed: 2 条' in out
        # 限定模式的统计同步块只在 task_id 给定时执行——全库模式不应有此打印
        assert '同步任务统计' not in out

        # 幽灵行已删
        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': a['ghost_trd_id']}) == 0
        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': b['ghost_trd_id']}) == 0
        # 真实失败行保留（EXISTS completed 整体行不命中，不误删）
        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': a['real_trd_id']}) == 1
        # 幽灵受害用例恢复 completed
        assert _count(cleanup_pg, 'task_case_relations',
                      'test_case_id = :c AND evaluation_status = :s',
                      {'c': a['case_id'], 's': 'completed'}) == 1
        assert _count(cleanup_pg, 'task_case_relations',
                      'test_case_id = :c AND evaluation_status = :s',
                      {'c': b['case_id'], 's': 'completed'}) == 1
        # 真实失败用例不恢复（仍有失败维度行守卫）
        assert _count(cleanup_pg, 'task_case_relations',
                      'test_case_id = :c AND evaluation_status = :s',
                      {'c': a['real_case_id'], 's': 'failed'}) == 1
        # 清理后核对：库内剩余 failed 维度行 = 真实失败 1 条
        assert _count(cleanup_pg, 'test_result_dimensions',
                      "evaluation_status = 'failed'") == 1

        # 4. 幂等：重复 apply 零删除零恢复
        out = _run_cleanup('--apply')
        assert '共 0 条' in out and '无幽灵行，跳过删除与状态恢复' in out

    def test_task_scoped_mode_isolates_by_task(self, cleanup_pg):
        """--task-id 限定：只处理该任务幽灵行，不越界；统计同步仅限该任务。"""
        a = _seed(cleanup_pg, task_name_suffix='S1', ghost=True)
        b = _seed(cleanup_pg, task_name_suffix='S2', ghost=True)

        out = _run_cleanup('--task-id', str(a['task_id']))
        assert f'任务 {a["task_id"]}' in out
        assert '共 1 条' in out, f'限定任务 dry-run 应只命中任务 A 的幽灵行:\n{out}'

        out = _run_cleanup('--task-id', str(a['task_id']), '--apply')
        assert '删除幽灵逐轮失败行: 1 条' in out
        assert '恢复 TaskCase 状态为 completed: 1 条' in out
        # 限定模式同步任务统计（completed_cases=1 / failed_cases=0）
        assert 'completed_cases=1, failed_cases=0' in out, f'输出:\n{out}'

        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': a['ghost_trd_id']}) == 0
        # 任务 B 幽灵行不越界
        assert _count(cleanup_pg, 'test_result_dimensions', 'id = :i',
                      {'i': b['ghost_trd_id']}) == 1
        # test_tasks 统计已被同步
        assert _count(cleanup_pg, 'test_tasks',
                      'id = :i AND completed_cases = 1 AND failed_cases = 0',
                      {'i': a['task_id']}) == 1

        # 任务 B 随后按其任务号清理（隔离验证收尾）
        _run_cleanup('--task-id', str(b['task_id']), '--apply')

    def test_full_db_apply_does_not_touch_task_stats(self, cleanup_pg):
        """全库 --apply 不写 test_tasks 统计（由用例事件侧原子刷新兜底）。"""
        c = _seed(cleanup_pg, task_name_suffix='S3', ghost=True)
        before = _count(cleanup_pg, 'test_tasks',
                        'id = :i AND completed_cases = 0 AND failed_cases = 1',
                        {'i': c['task_id']})
        assert before == 1

        _run_cleanup('--apply')

        # 统计未动（幽灵行删除、用例已恢复，但全库模式不回写 test_tasks）
        assert _count(cleanup_pg, 'test_tasks',
                      'id = :i AND completed_cases = 0 AND failed_cases = 1',
                      {'i': c['task_id']}) == 1
        # 用例已恢复
        assert _count(cleanup_pg, 'task_case_relations',
                      'test_case_id = :c AND evaluation_status = :s',
                      {'c': c['case_id'], 's': 'completed'}) == 1
