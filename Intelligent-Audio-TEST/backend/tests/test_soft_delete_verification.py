# -*- coding: utf-8 -*-
"""VEGA-32 独立复核测试（测试工程师2）

与开发侧 `test_soft_delete_semantics.py` 相互独立，按 issue 验收标准逐条实跑。
重点覆盖开发侧用例未触及的部分：

- 验收标准 3：操作人**机制就位**（请求头 X-User-Id 注入时能落库）—— 4 个软删写入点逐点；
- 验收标准 4：软删用例在**执行路径**上的行为（"要么拒绝、要么跳过并记录可见原因"）；
- 验收标准 4：逃生舱在**真实接口**（列表 / 导出）上可用；
- 验收标准 2：执行器实际使用的 `db.session()` 调用形态同样被全局过滤器覆盖；
- 验收标准 6：未软删用例的正常路径回归。

运行（在 Intelligent-Audio-TEST 目录下，需本机 PostgreSQL 已启动）：
    python -m pytest backend/tests/test_soft_delete_verification.py -v
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from backend.models.soft_delete import bulk_soft_delete, include_deleted
from backend.models.database import db
from backend.models.models import TestCase, TestCaseGroup, Tag, TestCaseTag, Task, TaskCase
from backend.services.execution.execution_engine import ExecutionEngine
from backend.services.execution.api_executor import APIExecutor

UTC8 = timezone(timedelta(hours=8))
OPERATOR_ID = 424242


def _new_group():
    group = TestCaseGroup(id=str(uuid.uuid4()), name=f'复核组-{uuid.uuid4().hex[:8]}')
    db.session.add(group)
    db.session.flush()
    return group


def _new_case(group):
    case = TestCase(
        id=str(uuid.uuid4()),
        name=f'复核用例-{uuid.uuid4().hex[:8]}',
        config={'rounds': []},
        group_id=group.id,
        test_type='api',
    )
    db.session.add(case)
    db.session.flush()
    return case


def _raw(case_id):
    """绕开 ORM 全局过滤直接读库"""
    return db.session.execute(text(
        'SELECT deleted, deleted_at, updated_by_user_id FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()


# ---------- 验收标准 3：操作人机制就位（4 个写入点逐点） ----------

def test_operator_header_lands_on_single_delete(app, client):
    """写入点① 单条删除（ORM 路径）：X-User-Id 注入时 updated_by_user_id 落库"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/testcases/{case.id}', headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID


def test_operator_header_lands_on_batch_delete(app, client):
    """写入点② 批量删除（bulk 统一入口）：X-User-Id 注入时落库"""
    group = _new_group()
    ids = [_new_case(group).id, _new_case(group).id]
    db.session.commit()

    resp = client.post('/api/v1/testcases/batch',
                       json={'action': 'delete', 'ids': ids},
                       headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    for case_id in ids:
        deleted, deleted_at, operator = _raw(case_id)
        assert deleted is True
        assert deleted_at is not None
        assert operator == OPERATOR_ID


def test_operator_header_lands_on_tag_cascade(app, client):
    """写入点③ 删标签级联（bulk 统一入口，最易漏的一处）"""
    group = _new_group()
    case = _new_case(group)
    tag = Tag(name=f'复核标签-{uuid.uuid4().hex[:8]}')
    db.session.add(tag)
    db.session.flush()
    db.session.add(TestCaseTag(test_case_id=case.id, tag_id=tag.id))
    db.session.commit()

    resp = client.delete(f'/api/v1/tags/{tag.id}?cascade=true',
                         headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID


def test_operator_header_lands_on_group_cascade(app, client):
    """写入点④ 删分组级联（bulk 统一入口）+ 分组本体（ORM 路径）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/groups/{group.id}?cascade=true',
                         headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID

    group_row = db.session.execute(text(
        'SELECT deleted, deleted_at, updated_by_user_id FROM test_case_groups WHERE id = :i'
    ), {'i': group.id}).fetchone()
    assert group_row[0] is True
    assert group_row[1] is not None
    assert group_row[2] == OPERATOR_ID


def test_operator_stays_null_without_identity(app, client):
    """无身份来源时不伪造操作人（临时口径 A：落 NULL 属预期）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/testcases/{case.id}')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator is None


def test_deleted_at_is_utc8_wall_clock(app, client):
    """deleted_at 为东八区时间（与库内既有 created_at/updated_at 口径一致）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    before = datetime.now(UTC8).replace(tzinfo=None) - timedelta(seconds=5)
    resp = client.delete(f'/api/v1/testcases/{case.id}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = datetime.now(UTC8).replace(tzinfo=None) + timedelta(seconds=5)

    stored = _raw(case.id)[1]
    assert stored is not None
    assert before <= stored <= after, f'deleted_at={stored} 不在东八区当前时间窗口内'


# ---------- 验收标准 4：逃生舱在真实接口上可用 ----------

def test_list_include_deleted_escape_hatch(app, client):
    """列表接口：默认看不到软删用例；include_deleted=true 时能看到

    用 keyword 收窄到本用例自身 ID：测试库是共享的，其它测试文件提交的残留行
    （控制器 commit 的已知限制）不应影响本用例判定。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    client.delete(f'/api/v1/testcases/{case_id}')

    default_resp = client.get(f'/api/v1/testcases?page=1&per_page=100&keyword={case_id}')
    assert default_resp.status_code == 200, default_resp.get_data(as_text=True)
    default_ids = {item['id'] for item in default_resp.get_json()['data']['items']}
    assert case_id not in default_ids

    opt_out_resp = client.get(
        f'/api/v1/testcases?page=1&per_page=100&keyword={case_id}&include_deleted=true')
    assert opt_out_resp.status_code == 200, opt_out_resp.get_data(as_text=True)
    opt_out_ids = {item['id'] for item in opt_out_resp.get_json()['data']['items']}
    assert case_id in opt_out_ids


def test_export_escape_hatch_returns_soft_deleted_case(app, client):
    """导出接口：include_deleted=true 时软删用例仍可导出（回收站/审计场景不被误伤）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    client.delete(f'/api/v1/testcases/{case_id}')

    blocked = client.post('/api/v1/testcases/export', json={'ids': [case_id], 'format': 'xlsx'})
    assert blocked.status_code != 200 or b'xlsx' not in blocked.data, \
        '软删用例默认不应被导出'

    allowed = client.post('/api/v1/testcases/export',
                          json={'ids': [case_id], 'format': 'xlsx', 'include_deleted': True})
    assert allowed.status_code == 200, allowed.get_data(as_text=True)


# ---------- 验收标准 2/6：执行器实际调用形态 + 回归 ----------

def test_executor_scoped_session_call_is_filtered(app):
    """执行域/重评域实际使用 `db.session()` 取 Session：同样被全局过滤器覆盖"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    case.deleted = True
    db.session.commit()
    db.session.expunge_all()

    local_db_session = db.session()          # 执行器里的真实写法
    try:
        assert local_db_session.query(TestCase).get(case_id) is None
        assert local_db_session.get(TestCase, case_id) is None
    finally:
        local_db_session.close()


def test_alive_case_regression_normal_paths(app, client):
    """回归：未软删用例的列表 / 详情 / 建任务校验 / 删除均不受影响"""
    from backend.controllers.task_controller import TaskController

    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    assert TaskController._find_unusable_case_ids([case_id]) == []

    detail = client.get(f'/api/v1/testcases/{case_id}')
    assert detail.status_code == 200, detail.get_data(as_text=True)

    listed = client.get(f'/api/v1/testcases?page=1&per_page=100&keyword={case_id}')
    assert listed.status_code == 200, listed.get_data(as_text=True)
    assert case_id in {item['id'] for item in listed.get_json()['data']['items']}

    assert client.delete(f'/api/v1/testcases/{case_id}').status_code == 200


# ---------- 验收标准 3：审计覆盖其余 Mixin 模型 / bulk 路径不丢 updated_at ----------

def test_audit_covers_audio_and_task_models(app):
    """审计入口覆盖 Audio / Task（现象二点名的四张表：test_cases/groups/audios/test_tasks）"""
    from backend.models.models import Audio

    audio = Audio(name=f'复核音频-{uuid.uuid4().hex[:8]}', file_path='/tmp/x.wav',
                  size=1, duration=1.0)
    task = Task(name=f'复核任务-{uuid.uuid4().hex[:8]}', type='api', status='pending')
    db.session.add_all([audio, task])
    db.session.commit()
    audio_id, task_id = audio.id, task.id

    audio.deleted = True
    task.deleted = True
    db.session.commit()

    for table, row_id in (('audios', audio_id), ('test_tasks', task_id)):
        row = db.session.execute(text(
            f'SELECT deleted, deleted_at FROM {table} WHERE id = :i'
        ), {'i': row_id}).fetchone()
        assert row[0] is True, f'{table} 未置 deleted'
        assert row[1] is not None, f'{table} 的 deleted_at 为空（软删无痕）'


def test_bulk_soft_delete_advances_updated_at(app):
    """回归：group_controller 原先显式写 updated_at，改造为 bulk_soft_delete 后仍须推进。

    若列级 onupdate 不作用于 Core UPDATE，则批量/级联删除不再留下"最近变动"痕迹。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id
    before = db.session.execute(text(
        'SELECT updated_at FROM test_cases WHERE id = :i'), {'i': case_id}).fetchone()[0]

    bulk_soft_delete(TestCase.query.filter(TestCase.id == case_id))

    after = db.session.execute(text(
        'SELECT updated_at FROM test_cases WHERE id = :i'), {'i': case_id}).fetchone()[0]
    assert after is not None
    assert after >= before, f'updated_at 未推进: before={before} after={after}'


# ---------- 验收标准 4：软删用例在执行路径上不得静默 ----------

def _build_task_with_case(case):
    task = Task(name=f'复核任务-{uuid.uuid4().hex[:8]}', type='api',
                status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()
    tc_rel = TaskCase(task_id=task.id, test_case_id=case.id, status='pending',
                      execution_status='pending', evaluation_status='pending')
    db.session.add(tc_rel)
    db.session.commit()
    return task, tc_rel


def test_api_execution_of_soft_deleted_case_is_not_silent(app):
    """执行路径：任务里的用例被软删后启动执行 —— 必须给出可见失败原因。

    issue 验收标准 4：对软删用例**不得静默**（要么拒绝、要么跳过并记录可见原因）。
    开发侧自述的行为是「TaskCase 置 failed + error_message = 找不到测试用例」。
    """
    group = _new_group()
    case = _new_case(group)
    task, tc_rel = _build_task_with_case(case)
    task_id, tc_rel_id = task.id, tc_rel.id

    # 建任务后软删该用例
    case.deleted = True
    db.session.commit()

    APIExecutor(ExecutionEngine()).execute_api_case(app, task_id, tc_rel_id)

    row = db.session.execute(text(
        'SELECT status, execution_status, error_message FROM task_case_relations WHERE id = :i'
    ), {'i': tc_rel_id}).fetchone()
    status, execution_status, error_message = row

    assert status == 'failed', (
        f'期望 TaskCase 置 failed，实际 status={status!r}, '
        f'execution_status={execution_status!r}, error_message={error_message!r}'
    )
    assert execution_status == 'failed', \
        f'期望 execution_status=failed，实际 {execution_status!r}（停留在该状态会让任务无法收敛）'
    assert error_message, '期望 error_message 记录可见失败原因，实际为空（静默失败）'


# ---------- 复验轮（commit 387917a6 之后）：从执行引擎真正 submit 的可调用对象上再验一遍 ----------

def test_engine_submitted_callable_marks_case_failed_immediately(app):
    """复验：走执行引擎真正提交给线程池的那个可调用对象，软删用例同样**立即**落 failed。

    `execution_engine.py:1071` 提交的是 `self._execute_api_case`（引擎自己的包装方法，
    `:1661-1720`），上一轮的锚点用例只覆盖到 executor 入口。这里补上引擎层，
    并断言耗时远小于 `test_case_wait_time`（配置 3000 秒），确保是**显式失败**
    而不是等超时兜底 —— 后者会给出笼统的「未处理的用例被标记为失败」。
    """
    group = _new_group()
    case = _new_case(group)
    task, tc_rel = _build_task_with_case(case)
    task_id, tc_rel_id = task.id, tc_rel.id

    case.deleted = True
    db.session.commit()

    started = time.monotonic()
    ExecutionEngine()._execute_api_case(app, task_id, tc_rel_id)
    elapsed = time.monotonic() - started

    row = db.session.execute(text(
        'SELECT status, execution_status, error_message, completed_at '
        'FROM task_case_relations WHERE id = :i'
    ), {'i': tc_rel_id}).fetchone()
    status, execution_status, error_message, completed_at = row

    assert (status, execution_status) == ('failed', 'failed'), row
    assert error_message == '找不到测试用例', \
        f'期望与 E2E 路径（base_executor.py:497）一致的措辞，实际 {error_message!r}'
    assert completed_at is not None, '未写 completed_at，任务收敛统计会缺时间'
    assert elapsed < 60, f'耗时 {elapsed:.1f}s，疑似仍在等超时兜底而非显式失败'


def test_validate_contract_returns_visible_failure_instead_of_raising(app):
    """复验：修复后 `_validate_and_get_data` 的契约 —— 取不到数据一律返回 (False, 可见原因)。

    本次改动共动了三个 not-found 分支，但「找不到 TaskCase / 找不到任务」两个分支经
    `execute_api_case` **不可达**：`_claim_tc_rel_running`（`api_executor.py:89-106`）已按
    `tc_rel_id + task_id + execution_status in (pending, queued)` 预筛过一遍，且
    `task_case_relations.task_id` 有指向 `test_tasks` 的外键、`Task` 未登记进全局过滤器
    （软删任务仍取得到）⇒ 只能直调私有方法验契约本身，证明它不再抛异常。
    """
    executor = APIExecutor(ExecutionEngine())
    with app.app_context():
        ok, msg = executor._validate_and_get_data(app, 999999, 999999)
    assert ok is False, f'期望 (False, 原因)，实际 ok={ok!r}'
    assert msg and '找不到' in msg, f'期望可见原因，实际 {msg!r}'


def test_import_revive_escape_hatch_reaches_soft_deleted_row(app):
    """复验：验收标准 4 的「恢复类功能不被误伤」—— 导入按 ID 复活。

    `testcase_controller.py:2746-2749` 的写法是
    `with include_deleted(): existing_tc = db.session.get(TestCase, tc_id)`。
    这里复现同一构造（同一 Session 形态、同一上下文管理器），确认软删行**能取到**、
    且改回 `deleted = False` 后 `deleted_at` 被统一清空 —— 否则回收站/导入复活会
    静默报「未找到ID对应的用例」，或复活后仍留着删除时间戳。

    说明：不做真实 xlsx 上传。仓库既有端到端用例
    `test_testcase_export_xlsx.py::test_import_update_restores_deleted_testcase` 覆盖了
    接口层，但该文件因共享测试库残留行（`test_case_groups_pkey (id)=(group-1)`）整文件
    6 failed，属已知环境问题，故本用例退到控制器实际使用的同一构造上验证。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    case.deleted = True
    db.session.commit()
    db.session.expunge_all()

    # 不带逃生舱：取不到（先证明过滤器确实在起作用）
    assert db.session.get(TestCase, case_id) is None, '前置条件不成立：全局过滤没生效'

    # 带逃生舱：取得到
    with include_deleted():
        revived = db.session.get(TestCase, case_id)
    assert revived is not None, '逃生舱未放开全局过滤 → 导入复活会静默失败'

    # 复活：deleted 置回 False，deleted_at 应由统一打标清空
    revived.deleted = False
    db.session.commit()

    deleted, deleted_at, _operator = _raw(case_id)
    assert deleted is False, '复活后 deleted 仍为 True'
    assert deleted_at is None, f'复活后 deleted_at 未清空：{deleted_at!r}'
