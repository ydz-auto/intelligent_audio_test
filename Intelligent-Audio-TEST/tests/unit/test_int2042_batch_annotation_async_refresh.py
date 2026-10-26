# -*- coding: utf-8 -*-
"""INT-2042 批量更新标注：用例参数刷新从命令里解耦为后台执行。

背景（缺陷卡实测）：默认勾选「同步刷新关联测试用例的参考参数」时，
刷新路径全表扫描全部用例 + 逐用例重算，总耗时 >60s，必然撞上网关 gRPC
客户端 deadline（GRPC_CLIENT_DEADLINE_SECONDS=60s）——标注已写库，客户端
却收到 400 DEADLINE_EXCEEDED，落库状态对用户不可知。

覆盖：
- 标注先落库提交，刷新入队后台执行，响应立刻返回（不等刷新）；
- 响应带 refresh_scheduled，refreshed_test_case_ids 保留为空列表；
- 刷新抛异常（DEADLINE_EXCEEDED 等）不影响标注结果；
- refresh_test_cases=false 不入队；
- 调度器单飞 + 合并，并透传操作人身份到工作线程。
"""
import os
import sys
import tempfile
import threading
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='int2042_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

import pytest

from audio_service.application.commands.audio_commands import (
    BatchUpdateAnnotationsCommand,
)
from audio_service.application.handlers.audio_command_handler import (
    AudioCommandHandler,
)
from audio_service.application.services import testcase_refresh_scheduler as sched_mod
from audio_service.application.services.testcase_refresh_scheduler import (
    TestCaseRefreshScheduler,
)
from shared.infrastructure.user_context import get_current_user_id, set_current_user_id


class FakeAudio:
    def __init__(self, audio_id):
        self.id = audio_id
        self.name = f'audio_{audio_id}.wav'
        self.visibility = 'shared'
        self.created_by_user_id = None


class FakeRepo:
    def __init__(self, audio_ids):
        self.audios = {aid: FakeAudio(aid) for aid in audio_ids}
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    def get_audio(self, audio_id):
        return self.audios.get(int(audio_id))

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeAnnotationService:
    def __init__(self):
        self.persisted = []

    def persist_annotations_and_raw(self, audio_id, annotations, algorithm_type):
        self.persisted.append((audio_id, algorithm_type))


def _make_handler(repo):
    handler = AudioCommandHandler(repository=repo)
    handler._annotation_service = FakeAnnotationService()
    return handler


def _cmd(items, refresh_test_cases=True):
    data = {'items': items}
    if refresh_test_cases is not None:
        data['refresh_test_cases'] = refresh_test_cases
    return BatchUpdateAnnotationsCommand(data=data)


def _items(*audio_ids):
    return [{'audio_id': aid, 'annotations': [{'code': 'reference', 'data': {'x': 1}}]}
            for aid in audio_ids]


@pytest.fixture
def scheduler(monkeypatch):
    """把调度器替换成注入假刷新函数的实例，避免真的走 gRPC。"""
    calls = []

    def fake_refresh(audio_ids, algorithm_type):
        calls.append({'audio_ids': list(audio_ids), 'algorithm_type': algorithm_type})
        return []

    sched = TestCaseRefreshScheduler(fake_refresh)
    monkeypatch.setattr(sched_mod, '_scheduler', sched)
    sched.calls = calls
    return sched


def test_annotations_committed_before_background_refresh(scheduler):
    """默认路径：标注先提交并立即返回，刷新在后台执行。"""
    repo = FakeRepo([1, 2])
    handler = _make_handler(repo)
    seen = []

    def record_refresh(audio_ids, algorithm_type):
        seen.append((sorted(audio_ids), repo.committed))
        return []

    scheduler._refresh_fn = record_refresh

    result = handler.handle_batch_update_annotations(_cmd(_items(1, 2), True))

    assert result['success'] is True
    assert repo.committed is True
    assert result['data']['updated_count'] == 2
    assert result['data']['refresh_scheduled'] is True
    # 旧字段保留为空列表，避免调用方解析失败
    assert result['data']['refreshed_test_case_ids'] == []
    assert '后台执行' in result['message']

    assert scheduler.wait_idle(5)
    # 刷新看到的是已提交状态（原先刷新与提交同在一条命令里）
    assert seen == [([1, 2], True)]


def test_response_does_not_wait_for_slow_refresh(scheduler):
    """刷新即使远超客户端 deadline，批量标注响应也不等待它。"""
    release = threading.Event()

    def slow_refresh(audio_ids, algorithm_type):
        release.wait(5)
        return []

    scheduler._refresh_fn = slow_refresh
    handler = _make_handler(FakeRepo([7]))

    started = time.monotonic()
    result = handler.handle_batch_update_annotations(_cmd(_items(7), True))
    elapsed = time.monotonic() - started

    assert result['success'] is True
    assert elapsed < 2, f'批量标注响应被刷新阻塞了 {elapsed:.1f}s'
    release.set()
    assert scheduler.wait_idle(5)


def test_refresh_failure_keeps_annotation_success(scheduler):
    """刷新抛 DEADLINE_EXCEEDED 类异常时，标注结果不受影响。"""
    def boom(audio_ids, algorithm_type):
        raise RuntimeError(
            '<_InactiveRpcError ... StatusCode.DEADLINE_EXCEEDED>')

    scheduler._refresh_fn = boom
    handler = _make_handler(FakeRepo([3]))

    result = handler.handle_batch_update_annotations(_cmd(_items(3), True))

    assert result['success'] is True
    assert result['data']['updated_count'] == 1
    assert scheduler.wait_idle(5)


def test_refresh_disabled_is_not_queued(scheduler):
    """取消勾选：不入队、不声明后台刷新。"""
    repo = FakeRepo([5])
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(_cmd(_items(5), False))

    assert result['success'] is True
    assert repo.committed is True
    assert result['data']['refresh_scheduled'] is False
    assert scheduler.pending_batches() == 0
    assert scheduler.calls == []


def test_failed_audio_not_scheduled():
    """全部音频不存在时，无刷新任务入队。"""
    repo = FakeRepo([])
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(_cmd(_items(99), True))

    assert result['success'] is True
    assert result['data']['updated_count'] == 0
    assert result['data']['failed_count'] == 1
    assert result['data']['refresh_scheduled'] is False


def test_scheduler_coalesces_and_propagates_identity():
    """运行期间新入队合并成下一批，并把操作人身份带进工作线程。"""
    started = threading.Event()
    release = threading.Event()
    seen = []

    def slow_refresh(audio_ids, algorithm_type):
        if not started.is_set():
            started.set()
            release.wait(5)
        seen.append((list(audio_ids), algorithm_type, get_current_user_id()))
        return []

    sched = TestCaseRefreshScheduler(slow_refresh)
    set_current_user_id(42)
    try:
        assert sched.enqueue([1, 2], None, sched_mod.capture_identity()) is True
        assert started.wait(5)
        # 第一个批次还在跑：这两次入队合并进同一待执行批次（下一轮）
        sched.enqueue([2, 3], None, sched_mod.capture_identity())
        sched.enqueue([4], None, sched_mod.capture_identity())
        release.set()
        assert sched.wait_idle(5)
    finally:
        set_current_user_id(None)

    assert [sorted(batch[0]) for batch in seen] == [[1, 2], [2, 3, 4]], \
        f'运行中的批次不应被改写，新入队合并成下一批: {seen}'
    assert seen[1][1] is None
    assert all(batch[2] == 42 for batch in seen), \
        '工作线程未恢复操作人身份（出站 gRPC 会缺 x-user-id）'
