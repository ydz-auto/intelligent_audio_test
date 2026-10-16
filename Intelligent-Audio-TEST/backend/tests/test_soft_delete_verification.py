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
import json
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
        group_id=group.id if group is not None else None,
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


# ==========================================================================
# 复验轮 2（commit 14b3ca96）：D2 报告域端到端 / M3 幂等 / M4 开关
#
# 与开发侧 `test_soft_delete_semantics.py` 第 7~9 节**不复用夹具、不复用断言**：
# 开发侧直接调 `ReportUtils.calculate_core_metrics`（只覆盖聚合兜底层），
# 本组走**真实报告生成入口**（`_generate_task_report_async` + 同步前置门禁），
# 断言落库的 `report_cases` / `report_metric_stats` 内容，覆盖上游门禁那一层。
# ==========================================================================

def _new_reportable_task(case_specs):
    """造一个"能生成报告"的任务（设备 + 启用维度 + 每例一条带维度得分的结果）

    :param case_specs: [(TestCase, 是否挂到分组)] 列表
    :return: dict(task_id / device_id / dimension_id / case_ids / result_ids)
    """
    from backend.models.models import (
        Device, Dimension, TaskCase, TestResult, TestResultDimension,
    )

    suffix = uuid.uuid4().hex[:8]
    device = Device(name=f'复核报告设备_{suffix}', model='M1', type='phone', system='Android',
                    system_version='14', app_name='App', app_version='1.0', status='online')
    dimension = Dimension(name=f'复核报告维度_{suffix}', type='auto', result_type=1, weight=1,
                          status=True, deleted=False, statistic_method='average')
    db.session.add_all([device, dimension])
    db.session.flush()

    task = Task(name=f'复核报告任务_{suffix}', type='e2e', status='completed',
                total_cases=len(case_specs), completed_cases=len(case_specs), failed_cases=0,
                algorithm_type='asr')
    db.session.add(task)
    db.session.flush()

    result_ids = {}
    for case, _in_group in case_specs:
        db.session.add(TaskCase(task_id=task.id, test_case_id=case.id, status='completed',
                                execution_status='completed', evaluation_status='completed',
                                deleted=False))
        result = TestResult(task_id=task.id, test_case_id=case.id, device_id=device.id,
                            api_id=None, execution_status='completed',
                            result_data={'result_type': 'default'}, deleted=False)
        db.session.add(result)
        db.session.flush()
        db.session.add(TestResultDimension(
            test_result_id=result.id, dimension_id=dimension.id, round_number=None,
            dimension_value=0.5, score=0.5, status='passed', evaluation_status='completed',
        ))
        result_ids[case.id] = result.id
    db.session.commit()

    return {
        'task_id': task.id,
        'device_id': device.id,
        'dimension_id': dimension.id,
        'case_ids': [c.id for c, _ in case_specs],
        'result_ids': result_ids,
    }


_REPORT_CHILD_TABLES = [
    'report_summaries', 'report_summary_meta', 'report_raw_data',
    'report_cases', 'report_metric_stats', 'report_comparison_matrix',
]


def _drop_reports(task_id):
    """清掉该任务的报告（含子表），使 `_generate_task_report_async` 不再走 exists 短路"""
    scope = 'SELECT id FROM test_reports WHERE task_id = :tid'
    for table in _REPORT_CHILD_TABLES:
        try:
            db.session.execute(text(f'DELETE FROM {table} WHERE report_id IN ({scope})'),
                               {'tid': task_id})
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text('DELETE FROM test_reports WHERE task_id = :tid'), {'tid': task_id})
        db.session.commit()
    except Exception:
        db.session.rollback()


def _drain_logs():
    """等异步日志管道把队列写完再删 `test_tasks` 行

    log_handler 是队列 + 后台线程批量落库（batch_timeout=1.0s）。若在日志还没写完时
    就删掉 test_tasks 行，后台线程随后插入 logs 会撞 logs_task_id_fkey 外键，
    且该失败会污染本测试共用的那条连接（StaticPool），殃及后续用例。
    """
    try:
        from backend.utils.web.log_handler import get_db_handler
        handler = get_db_handler()
    except Exception:
        return
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            if handler.queue.empty():
                break
        except Exception:
            return
        time.sleep(0.1)
    time.sleep(1.5)  # 跨过一次 batch_timeout，确保批次已落库


def _purge_report_task(built):
    """收尾：按外键倒序清掉造出的数据，避免污染共享测试库"""
    task_id = built.get('task_id')
    if not task_id:
        return
    _drain_logs()
    _drop_reports(task_id)
    for sql, params in (
        ('DELETE FROM test_result_dimensions WHERE test_result_id IN '
         '(SELECT id FROM test_results WHERE task_id = :tid)', {'tid': task_id}),
        ('DELETE FROM test_results WHERE task_id = :tid', {'tid': task_id}),
        ('DELETE FROM task_case_relations WHERE task_id = :tid', {'tid': task_id}),
    ):
        try:
            db.session.execute(text(sql), params)
            db.session.commit()
        except Exception:
            db.session.rollback()
    for cid in built.get('case_ids') or []:
        try:
            db.session.execute(text('DELETE FROM test_cases WHERE id = :cid'), {'cid': cid})
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text('DELETE FROM logs WHERE task_id = :tid'), {'tid': task_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text('DELETE FROM test_tasks WHERE id = :tid'), {'tid': task_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text('DELETE FROM dimensions WHERE id = :did'),
                           {'did': built.get('dimension_id')})
        db.session.execute(text('DELETE FROM devices WHERE id = :did'),
                           {'did': built.get('device_id')})
        db.session.commit()
    except Exception:
        db.session.rollback()


@pytest.fixture
def reportable():
    """造可生成报告的任务 + 收尾清理"""
    created = {}

    def _make(case_specs):
        created.clear()
        created.update(_new_reportable_task(case_specs))
        return created

    yield _make
    _purge_report_task(created)


def _report_artifacts(task_id):
    """读回该任务最新报告的分组信息与 header 计数"""
    from backend.models.models import (
        Report, ReportCase, ReportMetricStats, ReportRawData, ReportSummary,
    )

    report = Report.query.filter(Report.task_id == task_id, Report.deleted == False).first()
    if report is None:
        return None

    def _json_norm(value):
        for _ in range(2):
            if not isinstance(value, str):
                break
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                break
        return value

    cases = ReportCase.query.filter_by(report_id=report.id).all()
    stats = ReportMetricStats.query.filter_by(report_id=report.id).first()
    raw = ReportRawData.query.filter_by(report_id=report.id).first()
    summary = ReportSummary.query.filter_by(report_id=report.id).first()

    case_type_stats = _json_norm(stats.case_type_stats) if stats else None
    # 落库前被规范化为 [{group_id, group_name, metrics}, ...]
    if isinstance(case_type_stats, list):
        group_keys = [item.get('group_id') for item in case_type_stats if isinstance(item, dict)]
    elif isinstance(case_type_stats, dict):
        group_keys = list(case_type_stats.keys())
    else:
        group_keys = []

    return {
        'report_id': report.id,
        'case_categories': [c.category for c in cases],
        'case_ids': [c.test_case_id for c in cases],
        'group_keys': group_keys,
        'raw_resources': list((_json_norm(raw.raw_data) or {}) if raw else {}),
        'header_total': summary.total_cases if summary else None,
        'header_completed': summary.completed_cases if summary else None,
        'header_pass_rate': summary.pass_rate if summary else None,
    }


def test_d2_single_case_report_generation_fails_explicitly_after_soft_delete(app, reportable):
    """D2 主复现（总控指定）：任务唯一用例被软删 → 生成本身显式失败，不产出 default_group 报告

    这是审计 D2 的原始复现路径：软删前 A 的分数归在真实分组；软删后报告层若按 id
    取不到元数据就会静默归到 `default_group`（报告里凭空多一个分组、原分组少一个样本）。
    """
    from backend.controllers.report_controller_task import ReportControllerTask

    group = _new_group()
    case = _new_case(group)
    built = reportable([(case, True)])
    task_id = built['task_id']

    # 基线：未软删 → 报告生成成功，A 归在真实分组下，无 default_group
    ReportControllerTask._generate_task_report_async(task_id, f'复核D2基线_{uuid.uuid4().hex[:6]}', None)
    baseline = _report_artifacts(task_id)
    assert baseline is not None, '基线报告未生成'
    assert baseline['case_categories'] == [group.name], \
        f"基线明细应归到真实分组 {group.name!r}，实际 {baseline['case_categories']!r}"
    assert group.id in baseline['group_keys'], \
        f"基线 case_type_stats 应含真实分组 {group.id}，实际 {baseline['group_keys']!r}"
    assert 'default_group' not in baseline['group_keys'], \
        f"基线不应出现 default_group：{baseline['group_keys']!r}"

    # 软删该用例（任务唯一用例）→ 重新生成
    case.deleted = True
    db.session.commit()
    _drop_reports(task_id)

    ReportControllerTask._generate_task_report_async(task_id, f'复核D2软删后_{uuid.uuid4().hex[:6]}', None)
    after = _report_artifacts(task_id)
    assert after is None, (
        f'软删用例被剔除后应显式失败、不产出报告；实际产出报告 {after!r}'
    )

    # 同步门禁（HTTP 调用方看到的那个）也必须失败且给出可见原因
    error = ReportControllerTask._check_generation_preconditions(
        db.session.get(Task, task_id), task_id)
    assert error is not None, '同步前置门禁未拦截：HTTP 调用方会"看起来成功"'
    body = error[0].get_json()
    message = json.dumps(body, ensure_ascii=False)
    assert '无法生成报告' in message or '生成失败' in message, f'未见可见原因：{message}'


def test_d2_multi_case_report_drops_soft_deleted_case_without_default_group(app, reportable):
    """D2 强化复现（本组自加）：任务 2 例、软删 1 例 → 报告只含存活用例，且无 default_group

    单例场景靠"整单失败"兜住了，但线上真正的形态是「任务里 N 例、报告里 N-1 例」
    （开卡实测 63 条关系）。这条验证部分剔除路径：报告仍生成成功，但软删用例
    既不出现在明细里，也不被改归到 default_group。
    """
    from backend.controllers.report_controller_task import ReportControllerTask

    group = _new_group()
    case_a = _new_case(group)
    case_b = _new_case(group)
    built = reportable([(case_a, True), (case_b, True)])
    task_id = built['task_id']

    ReportControllerTask._generate_task_report_async(task_id, f'复核D2双例基线_{uuid.uuid4().hex[:6]}', None)
    baseline = _report_artifacts(task_id)
    assert baseline is not None and sorted(baseline['case_ids']) == sorted([case_a.id, case_b.id]), \
        f'基线应含 2 例，实际 {baseline!r}'

    case_a.deleted = True
    db.session.commit()
    _drop_reports(task_id)

    ReportControllerTask._generate_task_report_async(task_id, f'复核D2双例软删后_{uuid.uuid4().hex[:6]}', None)
    after = _report_artifacts(task_id)
    assert after is not None, '部分剔除场景不应整单失败（还有存活用例）'
    assert after['case_ids'] == [case_b.id], \
        f'报告明细应只剩存活用例 {case_b.id}，实际 {after["case_ids"]!r}'
    assert 'default_group' not in after['group_keys'], \
        f'软删用例被静默改归到 default_group：{after["group_keys"]!r}'
    assert after['case_categories'] == [group.name], \
        f'存活用例应仍归在真实分组，实际 {after["case_categories"]!r}'


def test_d2_alive_ungrouped_case_keeps_default_group_in_real_report(app, reportable):
    """D2 误伤回归（总控指定）：**未软删但确实没有分组**的用例，default_group 仍是合法桶

    开发侧把判据收窄为「test_case_id 非空且取不到用例才跳过」。这条在**真实报告**上
    确认收窄没有把「未分类」这个合法桶一起打掉 —— `report_query_builder.py:232` /
    `report_controller_secondary.py:347` 前端就是按 `default_group` 展示「未分类」。
    """
    from backend.controllers.report_controller_task import ReportControllerTask

    case = _new_case(None)          # 未软删、无分组
    built = reportable([(case, False)])
    task_id = built['task_id']

    ReportControllerTask._generate_task_report_async(task_id, f'复核D2未分类_{uuid.uuid4().hex[:6]}', None)
    payload = _report_artifacts(task_id)

    assert payload is not None, '无分组用例的报告应正常生成'
    assert payload['case_ids'] == [case.id]
    assert payload['case_categories'] == ['未分类'], \
        f'无分组用例在报告明细里应仍显示「未分类」：{payload["case_categories"]!r}'
    assert 'default_group' in payload['group_keys'], \
        f'case_type_stats 丢了 default_group 桶（合法桶被误伤）：{payload["group_keys"]!r}'


def test_d2_partial_exclusion_records_reason_and_keeps_counts_consistent(app, reportable):
    """D2 残留（**本卡目标 4 未达成，红锚点**）：部分剔除既无日志，报告头计数还与明细矛盾

    口径是「软删即不可用 + 执行/报告口径一致」。整单剔除时开发侧做成了显式失败（已验）；
    但**任务里还有存活用例**时（开卡实测的 63 条关系就是这种形态），软删用例的结果被
    上游门禁静默丢掉：`logs` 表里没有任何一行提到它，且报告 header 的
    `total_cases`/`completed_cases` 仍取自 `task.total_cases`（任务级计数器，软删不改），
    于是出现本卡点名的「任务里 N 例、报告里 N-1 例」—— 报告头写 2 例/通过 2 例
    （pass_rate 100%），明细只有 1 行。

    期望（目标 4「要么拒绝、要么跳过并**记录可见原因**」+「执行/报告口径一致」）：
    1. 被剔除的用例留下可见记录（`logs` 行含其 id 或明确说明被剔除）；
    2. 报告 header 计数与明细口径一致（软删用例不计入）。
    """
    from backend.controllers.report_controller_task import ReportControllerTask

    group = _new_group()
    case_a = _new_case(group)
    case_b = _new_case(group)
    built = reportable([(case_a, True), (case_b, True)])
    task_id = built['task_id']

    case_a.deleted = True
    db.session.commit()
    _drop_reports(task_id)

    ReportControllerTask._generate_task_report_async(
        task_id, f'复核D2残留_{uuid.uuid4().hex[:6]}', None)

    payload = _report_artifacts(task_id)
    assert payload is not None, '还有存活用例时报告应生成成功'
    assert payload['case_ids'] == [case_b.id], f'明细应只剩存活用例：{payload["case_ids"]!r}'

    # ① 报告 header 计数必须与明细口径一致（软删用例不计入）
    assert payload['header_total'] == len(payload['case_ids']), (
        f"报告头 total_cases={payload['header_total']} 与明细行数 "
        f"{len(payload['case_ids'])} 不一致：软删用例仍被计入报告头"
        f"（pass_rate={payload['header_pass_rate']}）"
    )
    assert payload['header_completed'] == len(payload['case_ids']), (
        f"报告头 completed_cases={payload['header_completed']} 与明细行数 "
        f"{len(payload['case_ids'])} 不一致"
    )

    # ② 被剔除的用例必须留下可见记录（否则就是"静默跳过"）
    _drain_logs()
    rows = db.session.execute(text(
        'SELECT level, content FROM logs WHERE task_id = :tid'
    ), {'tid': task_id}).fetchall()
    trace = '\n'.join(f'{lvl}: {content}' for lvl, content in rows)
    assert case_a.id in trace, (
        '软删用例被静默剔除：报告生成全程没有留下任何可见记录提到它。'
        f'该任务本次的日志共 {len(rows)} 行：\n{trace}'
    )


# ---------- M3：幂等守卫收敛后的真实级联路径 ----------

def _raw_trace(case_id):
    """读回 (deleted, deleted_at, updated_by_user_id)"""
    row = db.session.execute(text(
        'SELECT deleted, deleted_at, updated_by_user_id FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()
    return row


def test_m3_group_cascade_only_marks_alive_rows(app, client):
    """M3：守卫从 `group_controller` 调用方移入 `bulk_soft_delete` 后，分组级联仍只打标未软删行

    分组下放两个用例：A 存活、B 已被单条删除接口软删（带首次痕迹）。
    删分组级联后：A 必须被软删并留下痕迹；B 的首次痕迹**不得被覆盖**。
    """
    group = _new_group()
    case_alive = _new_case(group)
    case_gone = _new_case(group)
    db.session.commit()
    alive_id, gone_id = case_alive.id, case_gone.id

    # B 先经单条删除接口软删，留下首次痕迹（操作人 111111）
    resp = client.delete(f'/api/v1/testcases/{gone_id}', headers={'X-User-Id': '111111'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    first = _raw_trace(gone_id)
    assert first[1] is not None and first[2] == 111111

    # 删分组级联（操作人 222222）
    resp = client.delete(f'/api/v1/groups/{group.id}?cascade=true',
                         headers={'X-User-Id': '222222'})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    alive = _raw_trace(alive_id)
    assert alive[0] is True, '级联未软删分组下的存活用例（守卫是否把未软删行也挡掉了）'
    assert alive[1] is not None, '存活用例经级联软删后 deleted_at 为空'
    assert alive[2] == 222222, f'存活用例的操作人应为本次级联的操作人，实际 {alive[2]!r}'

    gone = _raw_trace(gone_id)
    assert gone[1] == first[1], f'级联覆盖了已软删用例的首次 deleted_at：{first[1]!r} → {gone[1]!r}'
    assert gone[2] == 111111, f'级联覆盖了已软删用例的首次操作人：{gone[2]!r}'


def test_m3_tag_cascade_idempotent_on_already_deleted_case(app, client):
    """M3 真实路径：标签级联的 case_ids 取自关联表（含已软删用例）→ 必然重复软删

    与开发侧用例的差别：本用例断言**两条用例的最终状态同时正确**（一条首次软删、
    一条重复软删），确认守卫是"逐行判定"而不是"整批跳过"。
    """
    group = _new_group()
    case_soft = _new_case(group)
    case_alive = _new_case(group)
    tag = Tag(name=f'复核幂等标签-{uuid.uuid4().hex[:8]}')
    db.session.add(tag)
    db.session.flush()
    db.session.add_all([
        TestCaseTag(test_case_id=case_soft.id, tag_id=tag.id),
        TestCaseTag(test_case_id=case_alive.id, tag_id=tag.id),
    ])
    db.session.commit()
    soft_id, alive_id, tag_id = case_soft.id, case_alive.id, tag.id

    resp = client.delete(f'/api/v1/testcases/{soft_id}', headers={'X-User-Id': '111111'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    first = _raw_trace(soft_id)

    resp = client.delete(f'/api/v1/tags/{tag_id}?cascade=true', headers={'X-User-Id': '222222'})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    soft_after = _raw_trace(soft_id)
    assert soft_after[1] == first[1], f'重复软删覆盖了 deleted_at：{first[1]!r} → {soft_after[1]!r}'
    assert soft_after[2] == 111111, f'重复软删覆盖了操作人：{soft_after[2]!r}'

    alive_after = _raw_trace(alive_id)
    assert alive_after[0] is True, '守卫把同批的存活用例一起挡掉了（幂等判定不是逐行）'
    assert alive_after[1] is not None and alive_after[2] == 222222, \
        f'存活用例的本次级联痕迹缺失：{alive_after!r}'


def test_m3_bulk_soft_delete_returns_zero_on_repeat(app):
    """M3：统一入口的返回值语义 —— 只计「本次真正由未删转为已删」的行数

    守卫收敛进 `bulk_soft_delete` 后返回值从"命中行数"变成"新软删行数"，
    调用方（3 处）均未使用返回值，但语义必须与 docstring 一致，否则后续调用方
    会拿它当"命中数"用。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    first = bulk_soft_delete(TestCase.query.filter(TestCase.id == case_id),
                             operator_user_id=111111)
    db.session.commit()
    assert first == 1, f'首次软删应命中 1 行，实际 {first}'

    again = bulk_soft_delete(TestCase.query.filter(TestCase.id == case_id),
                             operator_user_id=222222)
    db.session.commit()
    assert again == 0, f'重复软删应返回 0（未覆盖首次痕迹），实际 {again}'


# ---------- M4：AUTH_ENABLED 开关（过渡期专用请求头） ----------

def test_m4_auth_enabled_ignores_header_on_every_write_point(app, client):
    """M4：`AUTH_ENABLED=true` 时 4 个写入点一律不采信 `X-User-Id`，但 deleted_at 照写

    开发侧把开关放在 `operator.py` 的公共解析里，所以四个写入点应当同时失效；
    本用例逐个写入点实跑（单条 / 批量 / 标签级联 / 分组级联）。
    """
    original = app.config.get('AUTH_ENABLED', False)
    app.config['AUTH_ENABLED'] = True
    try:
        group = _new_group()
        single = _new_case(group)
        batch = [_new_case(group).id, _new_case(group).id]
        tag_case = _new_case(group)
        tag = Tag(name=f'复核开关标签-{uuid.uuid4().hex[:8]}')
        db.session.add(tag)
        db.session.flush()
        db.session.add(TestCaseTag(test_case_id=tag_case.id, tag_id=tag.id))
        cascade_group = _new_group()
        cascade_case = _new_case(cascade_group)
        db.session.commit()
        single_id, tag_id, tag_case_id = single.id, tag.id, tag_case.id
        cascade_group_id, cascade_case_id = cascade_group.id, cascade_case.id

        headers = {'X-User-Id': str(OPERATOR_ID)}

        assert client.delete(f'/api/v1/testcases/{single_id}', headers=headers).status_code == 200
        assert client.post('/api/v1/testcases/batch',
                           json={'action': 'delete', 'ids': batch},
                           headers=headers).status_code == 200
        assert client.delete(f'/api/v1/tags/{tag_id}?cascade=true',
                             headers=headers).status_code == 200
        assert client.delete(f'/api/v1/groups/{cascade_group_id}?cascade=true',
                             headers=headers).status_code == 200
    finally:
        app.config['AUTH_ENABLED'] = original

    checked = {
        '单条删除': single_id,
        '批量删除': batch[0],
        '标签级联': tag_case_id,
        '分组级联': cascade_case_id,
    }
    for label, case_id in checked.items():
        row = _raw_trace(case_id)
        assert row[0] is True, f'{label}：未置 deleted'
        assert row[1] is not None, f'{label}：deleted_at 为空（开关不应影响软删审计写入）'
        assert row[2] is None, f'{label}：认证落地后仍采信了客户端自带的 X-User-Id（{row[2]!r}）'


def test_m4_auth_disabled_restores_header_trust(app, client):
    """M4 回归：开关置回 `false` 后，过渡期行为不变（请求头仍作为操作人来源）"""
    assert app.config.get('AUTH_ENABLED', False) is False, \
        '前置：测试配置下 AUTH_ENABLED 应为 false'

    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/testcases/{case.id}', headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _raw_trace(case.id)
    assert row[1] is not None
    assert row[2] == OPERATOR_ID, f'过渡期请求头应仍生效，实际 {row[2]!r}'
