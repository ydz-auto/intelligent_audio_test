# -*- coding: utf-8 -*-
"""INT-1668 验收测试 — 建用例失败不得静默

缺陷链路：音频上传合并 / 秒传建用例时 task_service 拒绝（例如多轮设备校验
「全或无」不满足），ACL 仓储只 logger.error 后 return None，merge 仍回
success:true + test_case_id:null / test_case_count:0，上游把「用例没生成」
误判成「列表缓存延迟」。

验收标准：
1. task_service 返回 success=false → ACL 仓储抛 TestCaseCreationError（消息含后端原文）
2. gRPC 调用异常 → 同样上抛，不返回 None
3. merge 建用例失败：success=false + code=400 + message 含后端原文，整体回滚
4. 秒传建用例失败：同上（_instant_upload_with_testcase 走同一传播路径）
5. create_test_case=false（本次不建用例）不误报失败
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

import pytest

from audio_service.application.services.audio_upload.merge_mixin import AudioMergeMixin
from audio_service.domain.entities import UploadStatus
from audio_service.domain.exceptions import TestCaseCreationError


BACKEND_REJECT = '第1轮第1个音频配置为 E2E（物理执行）形态用例，必须指定 playback_device_id'


# ---------------- ACL 仓储：失败上抛 ----------------

class _Stub:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc
        self.requests = []

    def CreateTestCaseConfig(self, req):
        self.requests.append(req)
        if self._exc is not None:
            raise self._exc
        return self._resp


@pytest.fixture()
def acl_repo():
    from audio_service.infrastructure.acl.testcase_acl_repository import (
        TestCaseConfigACLRepositoryImpl,
    )
    return TestCaseConfigACLRepositoryImpl()


def _patch_stub(monkeypatch, stub):
    import shared.clients.grpc_clients as grpc_clients
    monkeypatch.setattr(
        grpc_clients, 'get_testcase_config_service_stub', lambda: stub, raising=True
    )


class TestAclFailurePropagation:
    """create_testcase_config 失败必须上抛，不返回 None"""

    def test_rejected_raises_with_backend_message(self, monkeypatch, acl_repo):
        resp = SimpleNamespace(success=False, message=BACKEND_REJECT, data='')
        _patch_stub(monkeypatch, _Stub(resp=resp))
        with pytest.raises(TestCaseCreationError) as ei:
            acl_repo.create_testcase_config({'name': 'x'})
        assert BACKEND_REJECT in str(ei.value)

    def test_grpc_exception_raises(self, monkeypatch, acl_repo):
        _patch_stub(monkeypatch, _Stub(exc=RuntimeError('connection refused')))
        with pytest.raises(TestCaseCreationError) as ei:
            acl_repo.create_testcase_config({'name': 'x'})
        assert 'connection refused' in str(ei.value)

    def test_success_returns_data(self, monkeypatch, acl_repo):
        resp = SimpleNamespace(success=True, message='ok', data='{"id": 100}')
        _patch_stub(monkeypatch, _Stub(resp=resp))
        assert acl_repo.create_testcase_config({'name': 'x'}) == {'id': 100}


# ---------------- merge / 秒传：失败不得静默 ----------------

_EXISTING_AUDIO = SimpleNamespace(id=11, name='a.wav', original_filename='a.wav', md5='md5-x')


def _upload_file():
    return SimpleNamespace(
        total_chunks=0,
        status=UploadStatus.completed,
        completed_chunks=0,
        md5='md5-x',
        upload_task_id=1,
        filename='a.wav',
        original_filename='a.wav',
        relative_path='',
        id=5,
    )


class _Repo:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def get_upload_file(self, _fid):
        return _upload_file()

    def get_upload_task(self, _tid):
        return SimpleNamespace(id=1)

    def get_audio_by_md5(self, _md5):
        return _EXISTING_AUDIO

    def get_audio_tag_names(self, _aid):
        return []

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _params(create_test_case=True):
    return {
        'create_test_case': create_test_case,
        'device_type': 'http_api',
        'dimensions_data': None,
        'default_playback_device_id': 8,
        'default_spl': 65.0,
        'noise_spl': 60.0,
        'noise_audio_id': None,
        'noise_device_ids': [],
        'test_case_group_name': 'g',
        'algorithm_type': None,
        'algorithm_params': None,
        'algorithm_params_dict': None,
        'rounds_config': [{'roundNumber': 1, 'audios': [{'audio_name': 'a.wav'}]}],
        'tc_inherit_tags': True,
        'case_background_noise': None,
    }


def _make_mixin(create_test_case=True, error=None):
    mixin = AudioMergeMixin.__new__(AudioMergeMixin)
    mixin.repo = _Repo()
    mixin._round_config_service = SimpleNamespace(
        extract_merge_params=lambda data: _params(create_test_case),
        match_existing_audio_in_rounds=lambda *a, **kw: 0,
    )
    mixin._annotation_service = SimpleNamespace(
        persist_annotations_and_raw=lambda *a, **kw: [],
    )
    created = []

    def _create(*args, **kwargs):
        created.append((args, kwargs))
        if error is not None:
            raise error
        return [100]

    mixin._testcase_creation_service = SimpleNamespace(
        create_test_case_from_audio=_create,
    )
    return mixin, created


class TestMergeFailureNotSilent:
    """建用例失败：merge / 秒传回 success=false + 400，且回滚"""

    def test_instant_upload_merge_reports_failure(self):
        """秒传建用例被拒：success=false / code=400 / message 含后端原文 / 已回滚"""
        mixin, created = _make_mixin(error=TestCaseCreationError(BACKEND_REJECT))
        result = mixin.merge_chunks({'file_id': 5, 'task_id': 1})

        assert created, '建用例应被调用'
        assert result['success'] is False
        assert result['code'] == 400
        assert BACKEND_REJECT in result['message']
        assert mixin.repo.rollbacks == 1
        assert mixin.repo.commits == 0

    def test_create_test_case_false_not_reported_as_failure(self):
        """create_test_case=false：不建用例，不得误报失败"""
        mixin, created = _make_mixin(create_test_case=False,
                                     error=TestCaseCreationError(BACKEND_REJECT))
        result = mixin.merge_chunks({'file_id': 5, 'task_id': 1})

        assert created == [], 'create_test_case=false 不应调用建用例'
        assert result['success'] is True
        assert result['code'] == 200
        assert mixin.repo.rollbacks == 0

    def test_create_test_case_if_needed_skips_when_disabled(self):
        """非秒传链路：create_test_case=false 直接跳过，不触发建用例"""
        mixin, created = _make_mixin(create_test_case=False,
                                     error=TestCaseCreationError(BACKEND_REJECT))
        assert mixin._create_test_case_if_needed(
            _EXISTING_AUDIO, _params(False), [], []
        ) is None
        assert created == []
