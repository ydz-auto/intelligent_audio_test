# -*- coding: utf-8 -*-
"""INT-116 评估终态可靠性回归守卫。

事故：评估端点不可达（30s 级连接超时）+ task_service 过载时，
- 评估服务终态写库（gRPC）失败后无重试无兜底，task_case_relations 永久停留
  evaluating，task_service 执行引擎无限忙等（日志 24.5 万行）；
- soft_delete_cleaner.run_once() 每次扫描调 init_db()（默认 pool_size=3），
  把宿主服务 lifespan 初始化的连接池整体替换成 3+overflow5（事故日志
  "QueuePool limit of size 3 overflow 5 reached" 的直接来源）。

守卫：
1. 软删除清理器不再重建全局 engine（engine 未就绪跳过本轮）
2. ACL 仓储 TaskCase/Task 读写对传输级失败内联重试（域层 ABC 模式不变）
3. update_task_case_status_with_retry / update_task_status_with_retry：
   仓储内联重试仍失败 → 转延迟重试队列；队列按退避持续补写直至成功
4. 同一 (task_id, case_id) 的待重试请求只保留最新一条
5. mark_case_failed_if_active：仅当评估状态仍活跃才落 failed，不覆盖终态
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int116_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import importlib
import shared.models.database as dbmod
import evaluation_service.infrastructure.acl.task_case_status_retry as retry_mod
# 包 __init__ 以同名实例 re-export 了 task_acl_repository，需取模块本身
repo_mod = importlib.import_module(
    'evaluation_service.infrastructure.acl.task_acl_repository')
from shared.models.database import get_engine, init_db
from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

from evaluation_service.infrastructure.acl import task_acl_repository
from evaluation_service.infrastructure.acl.task_case_status_retry import (
    TaskStatusRetryQueue,
)
from evaluation_service.infrastructure import evaluation_mixin as em
from evaluation_service.infrastructure.persistence.evaluation_result_processor import (
    EvaluationResultProcessor,
)


# ==================== 1. 软删除清理器不得重建 engine ====================

class _Int116Cleaner(SoftDeleteCleanerBase):
    def hard_delete_expired(self, session, threshold_dt):
        return {}


def test_cleaner_run_once_does_not_rebuild_engine():
    """run_once() 不得调用 init_db() 重建全局 engine（原缺陷复现点）。"""
    init_db(pool_size=20)
    engine_before = get_engine()

    cleaner = _Int116Cleaner(service_name='evaluation_service')
    cleaner.run_once()  # Redis 不可用等失败路径也不得重建 engine

    assert get_engine() is engine_before


def test_cleaner_run_once_skips_when_engine_missing(monkeypatch):
    """engine 未初始化时跳过本轮，不再隐式 init_db()（默认 pool_size=3）。"""
    monkeypatch.setattr(dbmod, '_engine', None)

    cleaner = _Int116Cleaner(service_name='evaluation_service')
    counts = cleaner.run_once()

    assert counts == {}
    assert get_engine() is None  # 全程未创建 engine


# ==================== 2. ACL 仓储内联重试（传输级失败） ====================

@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """测试中关闭仓储内联重试的真实退避等待（仅本模块常量，不动全局 time）。"""
    monkeypatch.setattr(repo_mod, '_TRANSIENT_BACKOFF_SECONDS', (0, 0))


class _Resp:
    def __init__(self, success=True, data='[]'):
        self.success = success
        self.data = data
        self.message = '' if success else 'db pool exhausted'


def test_repo_read_retries_on_exception_then_succeeds(monkeypatch):
    """GetTaskCaseByIds 传输异常 → 内联重试后成功返回数据。"""
    calls = {'n': 0}

    class _Stub:
        def GetTaskCaseByIds(self, req):
            calls['n'] += 1
            if calls['n'] < 3:
                raise RuntimeError('transient timeout')
            return _Resp(success=True, data='[{"test_case_id": "c1"}]')

    monkeypatch.setattr(repo_mod, 'get_task_data_service_stub', lambda: _Stub())
    result = task_acl_repository.get_task_case_by_ids(task_id=1)

    assert len(result) == 1 and result[0].test_case_id == 'c1'
    assert calls['n'] == 3


def test_repo_read_retries_on_success_false(monkeypatch):
    """服务端 success=False（task_service 内部失败）同样走内联重试。"""
    calls = {'n': 0}

    class _Stub:
        def GetTaskCaseByIds(self, req):
            calls['n'] += 1
            if calls['n'] < 2:
                return _Resp(success=False)
            return _Resp(success=True, data='[{"test_case_id": "c1"}]')

    monkeypatch.setattr(repo_mod, 'get_task_data_service_stub', lambda: _Stub())
    result = task_acl_repository.get_task_case_by_ids(task_id=1)

    assert len(result) == 1 and result[0].test_case_id == 'c1'
    assert calls['n'] == 2


def test_repo_update_task_case_status_inline_retry(monkeypatch):
    """UpdateTaskCaseStatus 异常后重试成功 → True。"""
    calls = {'n': 0}

    class _Stub:
        def UpdateTaskCaseStatus(self, req):
            calls['n'] += 1
            if calls['n'] < 2:
                raise RuntimeError('boom')
            return _Resp()

    monkeypatch.setattr(repo_mod, 'get_task_data_service_stub', lambda: _Stub())
    ok = task_acl_repository.update_task_case_status(
        task_id=1, case_id='c1', status='failed', evaluation_status='failed')

    assert ok is True
    assert calls['n'] == 2


def test_repo_update_task_case_status_persistent_failure(monkeypatch):
    """持续失败 → 内联重试耗尽返回 False（不抛出）。"""
    calls = {'n': 0}

    class _Stub:
        def UpdateTaskCaseStatus(self, req):
            calls['n'] += 1
            raise RuntimeError('down')

    monkeypatch.setattr(repo_mod, 'get_task_data_service_stub', lambda: _Stub())
    ok = task_acl_repository.update_task_case_status(
        task_id=1, case_id='c1', status='failed')

    assert ok is False
    assert calls['n'] == repo_mod._TRANSIENT_ATTEMPTS


def test_repo_empty_result_is_not_retried(monkeypatch):
    """空结果是合法应答（无关联用例），不得触发内联重试。"""
    calls = {'n': 0}

    class _Stub:
        def GetTaskCaseByIds(self, req):
            calls['n'] += 1
            return _Resp(success=True, data='[]')

    monkeypatch.setattr(repo_mod, 'get_task_data_service_stub', lambda: _Stub())
    result = task_acl_repository.get_task_case_by_ids(task_id=1)

    assert result == []
    assert calls['n'] == 1


# ==================== 3. 终态写库：内联重试失败 → 延迟队列补写 ====================

@pytest.fixture()
def retry_queue(monkeypatch):
    """独立队列实例：关掉后台线程，直接同步驱动处理循环。"""
    monkeypatch.setattr(TaskStatusRetryQueue, '_ensure_worker_locked',
                        lambda self: None)
    return TaskStatusRetryQueue()


def _patch_retry_singleton(monkeypatch, queue):
    """*_with_retry 内部按函数级 import 取单例，需 patch 源模块属性。"""
    monkeypatch.setattr(retry_mod, 'task_status_retry_queue', queue)


def test_case_status_deferred_when_write_fails(monkeypatch, retry_queue):
    """仓储内联重试仍失败 → 入延迟队列；队列补写成功后出队。"""
    _patch_retry_singleton(monkeypatch, retry_queue)
    monkeypatch.setattr(task_acl_repository, 'update_task_case_status',
                        lambda **kwargs: False)
    ok = em.update_task_case_status_with_retry(
        task_id=1, case_id='c1', status='failed', evaluation_status='failed',
        error_message='e')
    assert ok is False
    assert (1, 'c1') in retry_queue._pending_case     # 已入延迟队列

    calls = {'n': 0}

    def _succeed(**kwargs):
        calls['n'] += 1
        return True

    monkeypatch.setattr(task_acl_repository, 'update_task_case_status', _succeed)
    retry_queue._pending_case[(1, 'c1')].next_attempt_at = 0.0
    retry_queue._process_due_cases()
    assert calls['n'] == 1
    assert (1, 'c1') not in retry_queue._pending_case


def test_case_status_success_no_defer(monkeypatch, retry_queue):
    """写库一次成功：不进延迟队列。"""
    monkeypatch.setattr(task_acl_repository, 'update_task_case_status',
                        lambda **kwargs: True)
    ok = em.update_task_case_status_with_retry(
        task_id=2, case_id='c2', status='completed',
        evaluation_status='completed')
    assert ok is True
    assert retry_queue._pending_case == {}


def test_task_status_deferred_when_write_fails(monkeypatch, retry_queue):
    """任务终态写库失败同样入延迟队列并持续补写。"""
    _patch_retry_singleton(monkeypatch, retry_queue)
    monkeypatch.setattr(task_acl_repository, 'update_task_status',
                        lambda task_id, status: False)
    ok = em.update_task_status_with_retry(3, 'completed')
    assert ok is False
    assert 3 in retry_queue._pending_task

    calls = {'n': 0}

    def _task_succeed(task_id, status):
        calls['n'] += 1
        return True

    monkeypatch.setattr(task_acl_repository, 'update_task_status', _task_succeed)
    retry_queue._pending_task[3].next_attempt_at = 0.0
    retry_queue._process_due_tasks()
    assert calls['n'] == 1
    assert 3 not in retry_queue._pending_task


def test_retry_queue_keeps_latest_state_per_case(retry_queue):
    """同 (task_id, case_id) 重复入队只保留最新终态，旧请求不得落地覆盖新状态。"""
    retry_queue.enqueue_case_status(task_id=4, case_id='c4', status='failed',
                                    evaluation_status='failed')
    retry_queue.enqueue_case_status(task_id=4, case_id='c4', status='completed',
                                    evaluation_status='completed')
    assert len(retry_queue._pending_case) == 1
    item = retry_queue._pending_case[(4, 'c4')]
    assert item.status == 'completed'
    assert item.evaluation_status == 'completed'


def test_retry_queue_replaces_pending_when_newer_enqueued(monkeypatch, retry_queue):
    """补写进行中同 key 入队新状态：旧条目结果不作用于新请求（is 守卫）。"""
    monkeypatch.setattr(task_acl_repository, 'update_task_case_status',
                        lambda **kwargs: False)
    retry_queue.enqueue_case_status(task_id=5, case_id='c5', status='failed',
                                    evaluation_status='failed')
    old_item = retry_queue._pending_case[(5, 'c5')]
    old_item.next_attempt_at = 0.0
    # 补写前同 key 入队新请求（覆盖同一 key）
    retry_queue.enqueue_case_status(task_id=5, case_id='c5', status='completed',
                                    evaluation_status='completed')
    retry_queue._process_due_cases()  # 旧条目尝试失败
    new_item = retry_queue._pending_case[(5, 'c5')]
    assert new_item is not old_item
    assert new_item.status == 'completed'  # 新请求未被旧失败回滚/移除


def test_retry_queue_gives_up_after_max_window(monkeypatch, retry_queue):
    """超过最大重试窗仍失败：放弃并出队（可观测，不再无限占用）。"""
    retry_queue.enqueue_case_status(task_id=6, case_id='c6', status='failed',
                                    evaluation_status='failed')
    item = retry_queue._pending_case[(6, 'c6')]
    # 模拟已到重试窗上限
    item.next_attempt_at = 0.0
    item.enqueued_at -= retry_mod.MAX_RETRY_WINDOW_SECONDS + 1
    monkeypatch.setattr(task_acl_repository, 'update_task_case_status',
                        lambda **kwargs: False)

    retry_queue._process_due_cases()

    assert (6, 'c6') not in retry_queue._pending_case


# ==================== 4. mark_case_failed_if_active 兜底守卫 ====================

class _FakeTaskCase:
    def __init__(self, evaluation_status):
        self.evaluation_status = evaluation_status


def test_mark_case_failed_if_active_marks_active_case(monkeypatch):
    """评估状态仍活跃（calculating）→ 落 failed 终态。"""
    monkeypatch.setattr(task_acl_repository, 'get_task_case_by_ids',
                        lambda task_id, case_ids=None: [_FakeTaskCase('calculating')])
    marked = {}

    def _fake_update(*a, **kw):
        marked['args'] = a
        marked['kwargs'] = kw
        return 1

    monkeypatch.setattr(em, 'update_task_case_status_in_db', _fake_update)

    EvaluationResultProcessor().mark_case_failed_if_active(10, 'c10', '处理异常')

    assert marked['args'][3] == 'failed'       # status = TaskCaseStatus.FAILED
    assert marked['args'][4] == 'failed'       # evaluation_status


@pytest.mark.parametrize('terminal', ['completed', 'failed', 'stopped'])
def test_mark_case_failed_if_active_skips_terminal(monkeypatch, terminal):
    """已是终态 → 不写，避免覆盖并发链路已落的状态。"""
    monkeypatch.setattr(task_acl_repository, 'get_task_case_by_ids',
                        lambda task_id, case_ids=None: [_FakeTaskCase(terminal)])
    marked = {}

    def _fake_update(*a, **kw):
        marked['called'] = True
        return 1

    monkeypatch.setattr(em, 'update_task_case_status_in_db', _fake_update)

    EvaluationResultProcessor().mark_case_failed_if_active(11, 'c11', '处理异常')

    assert marked == {}


def test_mark_case_failed_if_active_read_failure_is_swallowed(monkeypatch):
    """状态读取失败（gRPC 异常）→ 记日志不抛出，不影响调用方。"""
    def _boom(**kwargs):
        raise RuntimeError('gRPC down')

    monkeypatch.setattr(task_acl_repository, 'get_task_case_by_ids', _boom)

    EvaluationResultProcessor().mark_case_failed_if_active(12, 'c12', 'err')
