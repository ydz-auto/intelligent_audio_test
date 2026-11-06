# -*- coding: utf-8 -*-
"""INT-364 实机验收：幽灵行清理 + 逐轮失败兜底 + 无维度可提交收敛
（真实 Postgres + 进程内 gRPC mesh + 评估端点替身全链）

单测（tests/unit/test_int364_reeval_ghost_rows_and_fallback.py）以 ACL 桩验证
三机制语义矩阵；本文件按 INT-103/INT-120 验收同款方式补真实链路集成面：

- 场景 A（验收标准#1，幽灵行）：E2E 用例每轮未配评估维度 + 顶层整体维度 +
  per_round 投影残留 failed 逐轮行（幽灵行）+ failed 重评 → 评估在途窗口内
  断言幽灵行已删除（提交前删除语义）、兜底走整体重评（整体行旧分被新评估
  覆盖）、用例收敛 completed、任务终态收尾；
- 场景 B：整体口径自身失败 + 幽灵行 → 整体口径正常重评，幽灵行清理且不复活；
- 场景 C（验收标准#2）：失败维度已软删 → 重评零提交 → 用例不卡 queued 收
  终态、任务收敛、重评队列释放可再次发起。回滚写侧（收尾失效时 failed 终态
  + error_message）由单测矩阵承载——真实健康链路中评估入口收尾先于兜底生效，
  回滚为防御性兜底不触发。

评估端点替身：异步任务协议，整体评估结果（data.result，即异步流提取后的
resp_data）携带 per_round（仅回填有值轮 round 0，轮 1 无值不产出——幽灵行
删除后不被重建），受理后 1.2s 内 get_status=running，为「提交前删除」提供
稳定的评估在途观测窗口。
"""
import time
import uuid
from datetime import datetime

import pytest

from tests.integration.test_task_execute_real_chain import (
    _query,
    _start_double,
    grpc_mesh,      # noqa: F401  pytest fixture（进程内 gRPC mesh）
    oss_fast_fail,  # noqa: F401  pytest fixture
    pg_db,          # noqa: F401  pytest fixture（真实 Postgres 临时库，用后即删）
    storage_env,    # noqa: F401  pytest fixture
)

_RUNNING_WINDOW_SECONDS = 1.2
_eval_task_created_at = {}


@pytest.fixture(autouse=True)
def _fresh_main_thread_session():
    """清主线程 session scope：单测文件先行运行时会在主线程 scope 里创建
    并缓存默认 engine（sqlite）绑定的 session，pg_db 的 _SessionFactory
    rebind 只影响新建 session、registry 残留 session 仍被 get_db_session
    返回——用例前后各清一次，保证临时 PG 库绑定生效（测试数据不落库外）。"""
    from shared.models.database import remove_db_session
    remove_db_session()
    yield
    remove_db_session()


def _eval_double_responder(method, path):
    """评估端点替身：受理后短窗 running（观测窗口），完成后返回整体
    结果 WER=7.2 + per_round 投影（仅 round 0 有值，round 1 无值不产出）。"""
    if method == 'POST' and path == '/api/create_task':
        eval_task_id = f'eval-{uuid.uuid4().hex[:8]}'
        _eval_task_created_at[eval_task_id] = time.time()
        return True, {'code': 0, 'msg': 'success',
                      'data': {'eval_task_id': eval_task_id}}, 200
    if method == 'GET' and path.startswith('/api/get_status/'):
        eval_task_id = path.rsplit('/', 1)[-1]
        created = _eval_task_created_at.get(eval_task_id)
        status = ('running' if created and time.time() - created < _RUNNING_WINDOW_SECONDS
                  else 'completed')
        return True, {'code': 0, 'msg': 'success',
                      'data': {'status': status,
                               'progress': 100 if status == 'completed' else 10}}, 200
    if method == 'GET' and path.startswith('/api/get_final_result/'):
        # 异步协议 _process_async_result 仅提取 data.result 作为 resp_data
        # （evaluation_api_client.py:307），per_round 须随 result 携带，
        # process_group_dimension_results 再按 resp_data 顶层键读取
        return True, {'code': 0, 'msg': 'success',
                      'data': {'result': {'WER': 7.2,
                                          'per_round': [{'round_number': 0,
                                                         'WER': 7.2}]}}}, 200
    if method == 'DELETE' and path.startswith('/api/cancel_task/'):
        return True, {'code': 0, 'msg': 'success'}, 200
    if method == 'GET' and path == '/health':
        return True, {'code': 0, 'msg': 'success', 'status': 'healthy'}, 200
    return False, None, 404


@pytest.fixture(scope='module')
def int364_eval_double():
    server, _thread = _start_double(_eval_double_responder)
    yield server
    server.shutdown()
    server.server_close()


# ──────────────────────────── 播种 ────────────────────────────

def _seed_reeval_scenario(double, *, device_type='physical', multi_round=True,
                          overall_status='completed', seed_ghost_row=True,
                          dim_deleted=False):
    """播种重评场景：Task/TaskCase/TestResult/TRD + 维度/映射，返回 ids dict。

    - multi_round=True（E2E）：algorithm_result 带 rounds、用例 config.rounds
      每轮均未配 evaluation.dimensions（幽灵场景前提）、顶层 config.dimensions
      配整体维度；TRD 播种「整体行 + 幽灵逐轮行（round 1 failed）」；
    - multi_round=False（API 单轮）：algorithm_result 无 rounds；dim_deleted=True
      时维度以软删形态播种（失败维度已不存在 → 无维度可提交）。
    """
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition,
        ParamMapping,
    )
    from evaluation_service.infrastructure.persistence.models import Dimension
    from evaluation_service.infrastructure.persistence.orm_models import (
        TestResultDimension,
    )
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from task_service.infrastructure.persistence.models import TestResult
    from task_service.infrastructure.persistence.models.testcase_models import TestCase

    s = get_db_session()
    now = datetime.now()
    try:
        if not s.query(AlgorithmDefinition).filter(
                AlgorithmDefinition.type == 'translation').first():
            s.add(AlgorithmDefinition(type='translation', name='翻译算法',
                                      status='online', deleted=False))
        s.flush()

        dim_name = f'WER-INT364-{uuid.uuid4().hex[:6]}'
        dim = Dimension(
            name=dim_name, dimension_type='main', task_type_code='wer',
            type='auto', result_type=1, weight=1,
            rule={'type': 'direct'},
            api_settings={'method': 'POST', 'headers': {},
                          'response_mapping': 'WER'},
            api_url=double.base_url,
            api_endpoints=[{'url': double.base_url, 'name': 'Master'}],
            api_status='online', status=True, deleted=dim_deleted)
        s.add(dim)
        s.flush()

        if not dim_deleted:
            s.add(ParamMapping(algorithm_type='translation',
                               source='device', source_param='text',
                               target_param='text', dimension_id=dim.id,
                               source_direction='output', transform_type='none',
                               deleted=False))
            s.flush()

        if multi_round:
            algo_result = {
                'round_count': 2, 'success_count': 2, 'success': True,
                'rounds': [
                    {'round': 0, 'success': True,
                     'output': {'text': '回答一'}, 'latency': 0.2},
                    {'round': 1, 'success': True,
                     'output': {'text': '回答二'}, 'latency': 0.2},
                ],
            }
            case_config = {
                'dimensions': [{'id': dim.id}],
                # 每轮未配置 evaluation.dimensions——幽灵场景前提（维度只配顶层）
                'rounds': [{'round_number': 1, 'algorithm_params': []},
                           {'round_number': 2, 'algorithm_params': []}],
                'api': {},
                'reference_params': [],
            }
        else:
            algo_result = {'answer': '今天天气怎么样',
                           'text_output': '今天天气怎么样'}
            case_config = {
                'dimensions': [{'id': dim.id}],
                'api': {},
                'reference_params': [],
            }

        case_id = f'INT364-{uuid.uuid4().hex[:12]}'
        s.add(TestCase(id=case_id, name='int364 重评实机用例',
                       config=case_config, algorithm_type='translation'))
        s.flush()

        task = Task(name=f'int364-reeval-{uuid.uuid4().hex[:8]}', status='failed',
                    total_cases=1, algorithm_type='translation')
        s.add(task)
        s.flush()
        s.add(TaskCase(task_id=task.id, test_case_id=case_id, status='failed',
                       execution_status='completed', evaluation_status='failed',
                       device_type=device_type, created_at=now))
        result = TestResult(task_id=task.id, test_case_id=case_id,
                            execution_status='completed',
                            algorithm_result=algo_result, result_data={},
                            algorithm_type='translation', created_at=now)
        s.add(result)
        s.flush()

        overall = TestResultDimension(
            test_result_id=result.id, dimension_id=dim.id, round_number=None,
            dimension_value=88.8 if overall_status == 'completed' else None,
            score=88.8 if overall_status == 'completed' else None,
            status=overall_status, evaluation_status=overall_status,
            error_message=None if overall_status == 'completed' else '整体评估历史失败')
        s.add(overall)
        ghost_id = None
        if seed_ghost_row:
            ghost = TestResultDimension(
                test_result_id=result.id, dimension_id=dim.id, round_number=1,
                dimension_value=None, score=None, status='failed',
                evaluation_status='failed',
                error_message='per_round 投影残留失败行（幽灵行模拟）')
            s.add(ghost)
            s.flush()
            ghost_id = ghost.id
        s.commit()
        return {'task_id': task.id, 'case_id': case_id, 'result_id': result.id,
                'dim_id': dim.id, 'overall_trd_id': overall.id,
                'ghost_trd_id': ghost_id}
    finally:
        s.close()


# ──────────────────────────── 等待与查询 ────────────────────────────

def _trd_rows(result_id):
    from evaluation_service.infrastructure.persistence.orm_models import (
        TestResultDimension,
    )
    return _query(TestResultDimension, test_result_id=result_id)


def _wait_overall_pending(result_id, dim_id, timeout=15):
    """轮询整体行被评估入口重置为 pending（评估在途信号）。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        for row in _trd_rows(result_id):
            if row.dimension_id == dim_id and row.round_number is None:
                last = row.evaluation_status
                if last == 'pending':
                    return last
        time.sleep(0.05)
    return last


def _wait_case_evaluation_status(task_id, statuses, timeout=90):
    from task_service.infrastructure.persistence.models import TaskCase
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rows = _query(TaskCase, task_id=task_id)
        last = rows[0].evaluation_status if rows else None
        if last in statuses:
            return last
        time.sleep(0.2)
    return last


def _wait_task_status(task_id, statuses, timeout=30):
    from task_service.infrastructure.persistence.models import Task
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rows = _query(Task, id=task_id)
        last = rows[0].status if rows else None
        if last in statuses:
            return last
        time.sleep(0.2)
    return last


def _wait_case_leaves_initial(task_id, initial='failed', timeout=15):
    """等待用例评估状态离开播种初值（重评链已触达），返回当前状态。"""
    from task_service.infrastructure.persistence.models import TaskCase
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rows = _query(TaskCase, task_id=task_id)
        last = rows[0].evaluation_status if rows else None
        if last is not None and last != initial:
            return last
        time.sleep(0.1)
    return last


def _wait_task_leaves_initial(task_id, initial='failed', timeout=15):
    """等待任务状态离开播种初值（重评链已触达），返回当前状态。"""
    from task_service.infrastructure.persistence.models import Task
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rows = _query(Task, id=task_id)
        last = rows[0].status if rows else None
        if last is not None and last != initial:
            return last
        time.sleep(0.1)
    return last


# ──────────────────────────── 用例 ────────────────────────────

class TestInt364GhostRowRealChain:
    """真实链路：failed 重评三机制（幽灵行清理 / 兜底 / 无维度收敛）。"""

    def test_ghost_round_row_cleaned_and_case_converges_completed(
            self, pg_db, grpc_mesh, oss_fast_fail, int364_eval_double):
        """场景 A（验收标准#1）：幽灵行场景 failed 重评 → 收敛 completed。

        整体行已 completed、仅幽灵逐轮行（round 1）failed——旧逻辑下整体分支
        无 None 键失败维度即跳过、逐轮分支因轮未配维度 continue，幽灵行永清
        不掉、用例永 failed。修复后：幽灵行提交前删除 + 兜底走整体重评。
        """
        ids = _seed_reeval_scenario(int364_eval_double,
                                    overall_status='completed',
                                    seed_ghost_row=True)
        # 前置 sanity：幽灵行在库、用例评估 failed
        ghost_rows = [r for r in _trd_rows(ids['result_id'])
                      if r.id == ids['ghost_trd_id']]
        assert len(ghost_rows) == 1 and ghost_rows[0].evaluation_status == 'failed'

        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ok, msg = ReevaluationExecutor.get_instance().submit(
            ids['task_id'], reextract_device_output=False,
            reevaluate_type='failed')
        assert ok, f'failed 重评提交失败: {msg}'

        # 评估在途窗口：整体行被重置 pending 时，幽灵行必须已删除（提交前删除）
        overall_status_seen = _wait_overall_pending(ids['result_id'], ids['dim_id'])
        assert overall_status_seen == 'pending', \
            f'整体行应被评估入口重置 pending，实际 {overall_status_seen}'
        ghost_after = [r for r in _trd_rows(ids['result_id'])
                       if r.round_number == 1 and r.evaluation_status == 'failed']
        assert not ghost_after, '评估在途时幽灵行仍残留——提交前删除语义失效'

        # 收敛：用例 completed（旧逻辑被幽灵行永久判 failed）
        final = _wait_case_evaluation_status(
            ids['task_id'], {'completed', 'failed', 'skipped', 'stopped'})
        assert final == 'completed', f'幽灵行场景 failed 重评后用例应收敛 completed，实际 {final}'

        rows = _trd_rows(ids['result_id'])
        by_round = {(r.dimension_id, r.round_number): r for r in rows}
        overall = by_round[(ids['dim_id'], None)]
        assert overall.evaluation_status == 'completed'
        assert overall.dimension_value == 7.2, \
            f'整体行应被本次整体重评覆盖为新值 7.2（兜底生效），实际 {overall.dimension_value}'
        round0 = by_round.get((ids['dim_id'], 0))
        assert round0 is not None and round0.evaluation_status == 'completed', \
            'per_round 投影应为有值轮（round 0）重建 completed 逐轮行'
        assert not [r for r in rows if r.evaluation_status == 'failed'], \
            '收敛后不应残留任何 failed 维度行'
        assert (ids['dim_id'], 1) not in by_round, \
            '无值轮（round 1）幽灵行删除后不应被重建'

        task_status = _wait_task_status(ids['task_id'], {'completed'})
        assert task_status == 'completed', \
            f'任务应由 maybe_finalize 终态收尾 completed，实际 {task_status}'

    def test_overall_failed_with_ghost_row_reevaluates_and_cleans(
            self, pg_db, grpc_mesh, oss_fast_fail, int364_eval_double):
        """场景 B：整体口径自身失败 + 幽灵行 → 整体正常重评，幽灵行清理不复活。"""
        ids = _seed_reeval_scenario(int364_eval_double,
                                    overall_status='failed',
                                    seed_ghost_row=True)

        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ok, msg = ReevaluationExecutor.get_instance().submit(
            ids['task_id'], reextract_device_output=False,
            reevaluate_type='failed')
        assert ok, f'failed 重评提交失败: {msg}'

        # 评估在途门控：整体行被重置 pending（排除播种态 failed 的轮询竞态）
        overall_status_seen = _wait_overall_pending(ids['result_id'], ids['dim_id'])
        assert overall_status_seen == 'pending', \
            f'整体行应被评估入口重置 pending，实际 {overall_status_seen}'

        final = _wait_case_evaluation_status(
            ids['task_id'], {'completed', 'failed', 'skipped', 'stopped'})
        assert final == 'completed', f'用例应收敛 completed，实际 {final}'

        rows = _trd_rows(ids['result_id'])
        by_round = {(r.dimension_id, r.round_number): r for r in rows}
        overall = by_round[(ids['dim_id'], None)]
        assert overall.evaluation_status == 'completed'
        assert overall.dimension_value == 7.2, \
            f'整体失败行应被重评为新值 7.2，实际 {overall.dimension_value}'
        assert not [r for r in rows if r.evaluation_status == 'failed'], \
            '幽灵行应被清理且不被复建'
        assert (ids['dim_id'], 1) not in by_round, \
            '无值轮（round 1）不应有逐轮行残留'

        task_status = _wait_task_status(ids['task_id'], {'completed'})
        assert task_status == 'completed'

    def test_no_submittable_dim_converges_and_releases_queue(
            self, pg_db, grpc_mesh, oss_fast_fail, int364_eval_double):
        """场景 C（验收标准#2）：失败维度已软删 → 重评零提交 → 用例不卡
        queued 收终态、任务收敛、重评队列释放。

        旧逻辑：用例被置 queued 后无人提交评估，永久卡 queued 并阻塞后续
        重评（无回调、maybe_finalize 无法收尾）。健康链路中评估入口无维度
        路径先行收尾（终态），回滚兜底（单测矩阵承载）不触发。
        """
        ids = _seed_reeval_scenario(int364_eval_double, device_type='http_api',
                                    multi_round=False, overall_status='failed',
                                    seed_ghost_row=False, dim_deleted=True)

        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        executor = ReevaluationExecutor.get_instance()
        ok, msg = executor.submit(ids['task_id'], reextract_device_output=False,
                                  reevaluate_type='failed')
        assert ok, f'failed 重评提交失败: {msg}'

        # 两段等待：先确认重评链已触达（离开播种初值，排除轮询竞态），
        # 再等终态——旧逻辑用例卡 queued 时此处超时可见
        touched = _wait_case_leaves_initial(ids['task_id'])
        assert touched is not None, '重评链未触达用例（15s 内状态无变迁）'
        final = _wait_case_evaluation_status(
            ids['task_id'], {'completed', 'failed', 'skipped', 'stopped'})
        assert final == 'completed', \
            f'无维度可提交的用例应经评估入口收尾收敛 completed（不卡 queued），实际 {final}'

        # 任务收敛（零提交 → maybe_finalize 直接收尾；旧逻辑用例卡 queued
        # 时 maybe_finalize 拒绝收敛、任务置 running 永不终态）
        task_touched = _wait_task_leaves_initial(ids['task_id'])
        assert task_touched is not None, '重评链未触达任务（15s 内状态无变迁）'
        task_status = _wait_task_status(ids['task_id'], {'completed'})
        assert task_status == 'completed', \
            f'零提交重评任务应由 maybe_finalize 收敛 completed，实际 {task_status}'

        # 重评队列释放：不再占用（否则后续任何重评被拒）
        deadline = time.time() + 15
        while time.time() < deadline and (
                executor.is_reevaluating or executor.running_task_id == ids['task_id']):
            time.sleep(0.2)
        assert not executor.is_reevaluating, '重评队列应已释放（is_reevaluating=False）'
        assert executor.running_task_id != ids['task_id'], \
            'running_task_id 应已让出，后续重评不被拒'
