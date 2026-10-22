# -*- coding: utf-8 -*-
"""INT-1306 音频删除引用检查单测（真实库走查修复）。

覆盖（sqlite 文件库，不依赖真库）：
- task_query_service.check_audio_references：用例音频 / 用例背景噪音 /
  任务（经 task_case_relations 关联用例 + 任务 config 内嵌 audio_id）计数
- audio_command_handler.handle_delete：无引用 → 成功；被引用 → 跳过文案；
  引用检查失败 → fail-closed（返回错误，不落库）
- audio_command_handler.handle_batch_action action=delete：逐项成功/跳过计数

验收口径对齐原卡：
1. 删除无引用音频秒级成功（引用检查单次 DB 扫描，无逐页 gRPC 全量拉取）
2. 被引用音频明确返回跳过文案
3. 批量删除返回逐项成功/跳过计数
"""
import os
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int1306_unit_') + '/unit.db')

import pytest

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from shared.infrastructure.storage import storage


@pytest.fixture(scope='module')
def db():
    """初始化 sqlite 文件库并建 test_cases / test_tasks / task_case_relations 表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TestCase.__table__, Task.__table__, TaskCase.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture(autouse=True)
def _clean_db(db):
    """每个用例清理表数据。"""
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    yield
    session = get_db_session()
    session.query(TaskCase).delete()
    session.query(TestCase).delete()
    session.query(Task).delete()
    session.commit()
    remove_db_session()


def _insert_case(case_id, config, deleted=False):
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    po = TestCase(
        id=case_id,
        name=f'case_{case_id}',
        config=config,
        deleted=deleted,
    )
    session.add(po)
    session.commit()


def _insert_task(task_id, config=None, deleted=False):
    from task_service.infrastructure.persistence.models import Task
    session = get_db_session()
    po = Task(
        id=task_id,
        name=f'task_{task_id}',
        config=config,
        deleted=deleted,
    )
    session.add(po)
    session.commit()


def _insert_task_case(task_id, case_id):
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    po = TaskCase(
        task_id=task_id,
        test_case_id=case_id,
    )
    session.add(po)
    session.commit()


def _call_check(audio_ids):
    """调 task_query_service.check_audio_references（进程级唯一导入）。"""
    from task_service.application.task.task_query_service import task_query_service
    return task_query_service.check_audio_references(audio_ids)


class TestCheckAudioReferences:
    def test_case_rounds_audios_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 11}, {'audio_id': 12}]}]})
        _insert_case('c2', {'rounds': [{'audios': [{'audio_id': 11}]}]})
        result = _call_check([11, 12, 13])
        assert result['success'] is True
        refs = result['data']['references']
        assert refs['11']['testcase_audio'] == 2
        assert refs['12']['testcase_audio'] == 1
        assert refs['13']['testcase_audio'] == 0

    def test_case_top_level_audios_counted(self):
        _insert_case('c1', {'audios': [{'audio_id': 21}]})
        result = _call_check([21])
        assert result['data']['references']['21']['testcase_audio'] == 1

    def test_case_background_noise_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30}]}],
                            'background_noise': {'audio_id': 31}})
        result = _call_check([30, 31])
        refs = result['data']['references']
        assert refs['30']['testcase_audio'] == 1
        assert refs['31']['testcase_noise'] == 1
        assert refs['31']['testcase_audio'] == 0

    def test_deleted_cases_not_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 41}]}]}, deleted=True)
        result = _call_check([41])
        assert result['data']['references']['41']['testcase_audio'] == 0

    def test_task_config_embedded_audio_id_counted(self):
        _insert_task(1, {'parallel': True, 'audio_id': 51})
        result = _call_check([51])
        assert result['data']['references']['51']['task'] == 1

    def test_task_linked_case_audio_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 61}]}]})
        _insert_case('c2', {'rounds': [{'audios': [{'audio_id': 62}]}]})
        _insert_task(1, {'parallel': True})
        _insert_task(2, {'parallel': True})
        _insert_task_case(1, 'c1')
        _insert_task_case(2, 'c2')
        result = _call_check([61, 62])
        refs = result['data']['references']
        assert refs['61']['task'] == 1
        assert refs['62']['task'] == 1

    def test_deleted_tasks_not_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 71}]}]})
        _insert_task(1, {'parallel': True}, deleted=True)
        _insert_task_case(1, 'c1')
        result = _call_check([71])
        # 用例引用仍计 1；任务已删不计
        assert result['data']['references']['71']['testcase_audio'] == 1
        assert result['data']['references']['71']['task'] == 0

    def test_empty_audio_ids_ok(self):
        result = _call_check([])
        assert result['success'] is True
        assert result['data']['references'] == {}


class FakeAudio:
    def __init__(self, **kw):
        self.id = kw['id']
        self.name = kw.get('name', 'sample.wav')
        # local:// 路径：后台尽力删除线程即使脱离 mock 也不触发 OSS 探测挂起
        self.file_path = kw.get('file_path', 'local://audios/direct/test/dry/a.wav')


class FakeRepo:
    """实现 handler 用到的仓储方法子集（内存版）。"""

    def __init__(self, audios):
        self.audios = {a.id: a for a in audios}
        self.committed = False
        self.rolled_back = False
        self.deleted = []

    def get_audio(self, audio_id):
        return self.audios.get(audio_id)

    def get_audios_by_ids(self, ids):
        return [self.audios[i] for i in ids if i in self.audios]

    def delete_audio(self, audio_id):
        self.deleted.append(audio_id)
        return True

    def delete_audio_annotations(self, audio_id):
        pass

    def delete_audio_tags(self, audio_id):
        pass

    def batch_soft_delete_audios(self, ids):
        self.deleted.extend(ids)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def flush(self):
        pass


class FakeTaskACL:
    """task_service ACL 替身：按引用表返回计数。"""

    def __init__(self, refs):
        # refs: {audio_id: {'testcase_audio': N, 'testcase_noise': N, 'task': N}}
        self.refs = refs

    def check_audio_references_batch(self, audio_ids):
        result = {}
        for aid in audio_ids:
            result[aid] = self.refs.get(aid, {})
        return result

    def check_audio_in_devices(self, audio_id):
        return 0


class FakeTaskACLFailure(FakeTaskACL):
    """gRPC 失败替身：抛异常（fail-closed 验证）。"""

    def check_audio_references_batch(self, audio_ids):
        raise RuntimeError('gRPC 不可达')


def _make_handler(repo, acl):
    from audio_service.application.handlers.audio_command_handler import AudioCommandHandler
    handler = AudioCommandHandler(repository=repo)
    handler._task_acl = acl
    handler._device_acl = acl  # 复用（check_audio_in_devices 返回 0）
    return handler


class TestHandleDelete:
    def test_unreferenced_audio_deleted(self):
        repo = FakeRepo([FakeAudio(id=1)])
        handler = _make_handler(repo, FakeTaskACL({1: {}}))
        with _patch_storage_delete():
            from audio_service.application.commands.audio_commands import DeleteAudioCommand
            result = handler.handle_delete(DeleteAudioCommand(audio_id=1))
        assert result['success'] is True
        assert repo.deleted == [1]
        assert repo.committed is True

    def test_referenced_audio_returns_skip_message(self):
        repo = FakeRepo([FakeAudio(id=2)])
        handler = _make_handler(
            repo, FakeTaskACL({2: {'testcase_audio': 1, 'testcase_noise': 0, 'task': 0}}))
        from audio_service.application.commands.audio_commands import DeleteAudioCommand
        result = handler.handle_delete(DeleteAudioCommand(audio_id=2))
        assert result['success'] is False
        assert '测试用例' in result['message']
        assert repo.deleted == []

    def test_noise_referenced_audio_returns_skip_message(self):
        repo = FakeRepo([FakeAudio(id=3)])
        handler = _make_handler(
            repo, FakeTaskACL({3: {'testcase_audio': 0, 'testcase_noise': 1, 'task': 0}}))
        from audio_service.application.commands.audio_commands import DeleteAudioCommand
        result = handler.handle_delete(DeleteAudioCommand(audio_id=3))
        assert result['success'] is False
        assert '背景噪音' in result['message']
        assert repo.deleted == []

    def test_task_referenced_audio_returns_skip_message(self):
        repo = FakeRepo([FakeAudio(id=4)])
        handler = _make_handler(
            repo, FakeTaskACL({4: {'testcase_audio': 0, 'testcase_noise': 0, 'task': 1}}))
        from audio_service.application.commands.audio_commands import DeleteAudioCommand
        result = handler.handle_delete(DeleteAudioCommand(audio_id=4))
        assert result['success'] is False
        assert '任务' in result['message']
        assert repo.deleted == []

    def test_reference_check_failure_fails_closed(self):
        repo = FakeRepo([FakeAudio(id=5)])
        handler = _make_handler(repo, FakeTaskACLFailure({}))
        from audio_service.application.commands.audio_commands import DeleteAudioCommand
        result = handler.handle_delete(DeleteAudioCommand(audio_id=5))
        assert result['success'] is False
        assert repo.deleted == []  # 未删除
        assert repo.rolled_back is True

    def test_missing_audio_404(self):
        repo = FakeRepo([])
        handler = _make_handler(repo, FakeTaskACL({}))
        from audio_service.application.commands.audio_commands import DeleteAudioCommand
        result = handler.handle_delete(DeleteAudioCommand(audio_id=99))
        assert result['success'] is False
        assert result['code'] == 404


class TestHandleBatchDelete:
    def test_mixed_referenced_unreferenced_counts(self):
        repo = FakeRepo([FakeAudio(id=1), FakeAudio(id=2), FakeAudio(id=3)])
        handler = _make_handler(repo, FakeTaskACL({
            1: {},  # 可删
            2: {'testcase_audio': 1, 'testcase_noise': 0, 'task': 0},  # 跳过
            3: {},  # 可删
        }))
        with _patch_storage_delete():
            from audio_service.application.commands.audio_commands import BatchActionAudiosCommand
            result = handler.handle_batch_action(BatchActionAudiosCommand(
                data={'audio_ids': [1, 2, 3], 'action': 'delete'}))
        assert result['success'] is True
        assert '成功删除 2' in result['message']
        assert '跳过了 1' in result['message']
        assert set(repo.deleted) == {1, 3}

    def test_all_referenced_no_delete(self):
        repo = FakeRepo([FakeAudio(id=1)])
        handler = _make_handler(repo, FakeTaskACL({1: {'task': 1}}))
        from audio_service.application.commands.audio_commands import BatchActionAudiosCommand
        result = handler.handle_batch_action(BatchActionAudiosCommand(
            data={'audio_ids': [1], 'action': 'delete'}))
        assert result['success'] is True
        assert '没有可删除的音频文件' in result['message']
        assert repo.deleted == []


def _patch_storage_delete():
    """桩化 storage.delete（内存语义，不落盘）。"""
    import unittest.mock as mock
    return mock.patch.object(storage, 'delete', return_value=None)
