# -*- coding: utf-8 -*-
"""INT-1533 编辑元数据「标签」不落库（audio_tags.tag_id 恒 NULL）回归单测。

缺陷：update_metadata 收到 tags（逗号分隔字符串）时，get_or_create_tag 在
task_service 标签服务不可达/创建被拒时返回 id=None 的代理，调用方把 None
写进 audio_tags.tag_id，接口仍回「元数据更新成功」。

覆盖：
- handler：标签解析失败 → 整单失败 + rollback，不再回成功
- handler：标签正常解析 → 按 id 落关联
- ACL：按名命中 / 不存在则创建 / 创建撞并发后复查 / 彻底失败抛 TagResolutionError
- 持久层：add_audio_tag(tag_id=None) 拒绝写入
"""
import json
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='int1533_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

import pytest
from unittest import mock

from audio_service.domain.exceptions import TagResolutionError
from audio_service.application.commands.audio_commands import UpdateAudioMetadataCommand
from audio_service.application.handlers.audio_command_handler import AudioCommandHandler
from audio_service.infrastructure.acl.tag_acl_repository import TagAclRepository
from audio_service.infrastructure.persistence._audio_relation_mixin import AudioRelationMixin


class FakeAudio:
    def __init__(self, audio_id=7):
        self.id = audio_id
        self.name = 'sample.wav'


class FakeRepo:
    """handler 依赖的仓储子集。tags 参数为 名称→ID 映射；失败名在 fail_names 中。"""

    def __init__(self, tag_map=None, fail_names=()):
        self.audio = FakeAudio()
        self.tag_map = tag_map or {}
        self.fail_names = set(fail_names)
        self.added_tags = []
        self.committed = False
        self.rolled_back = False
        self.deleted_tags = 0

    def get_audio(self, audio_id):
        return self.audio if audio_id == self.audio.id else None

    def update_audio(self, audio_id, update_fields):
        for key, value in update_fields.items():
            setattr(self.audio, key, value)

    def delete_audio_tags(self, audio_id):
        self.deleted_tags += 1
        return 1

    def get_or_create_tag(self, tag_name):
        if tag_name in self.fail_names:
            raise TagResolutionError(tag_name, 'task_service 不可达')
        return mock.Mock(id=self.tag_map.get(tag_name, 100), name=tag_name)

    def add_audio_tag(self, audio_id, tag_id):
        assert tag_id is not None
        self.added_tags.append((audio_id, tag_id))

    def delete_audio_annotations(self, audio_id):
        return 0

    def create_audio_annotation(self, audio_id, ann):
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _handler(repo):
    h = AudioCommandHandler.__new__(AudioCommandHandler)
    h.repo = repo
    return h


def _cmd(data):
    return UpdateAudioMetadataCommand(audio_id=7, data=data)


# ---------------- handler ----------------

def test_update_metadata_persists_tag_ids():
    repo = FakeRepo(tag_map={'标签A': 74, '标签B': 75})
    result = _handler(repo).handle_update_metadata(
        _cmd({'name': 'a.wav', 'tags': '标签A, 标签B'}))

    assert result['success'] is True
    assert result['message'] == '元数据更新成功'
    assert repo.added_tags == [(7, 74), (7, 75)]
    assert repo.committed is True


def test_update_metadata_fails_loudly_when_tag_unresolved():
    """核心回归：解析失败不得回「成功」，更不得退化为 NULL 关联。"""
    repo = FakeRepo(tag_map={'标签A': 74}, fail_names={'坏标签'})
    result = _handler(repo).handle_update_metadata(
        _cmd({'name': 'a.wav', 'tags': '标签A,坏标签'}))

    assert result['success'] is False
    assert '坏标签' in result['message']
    assert repo.rolled_back is True
    assert repo.committed is False


def test_update_metadata_blank_tags_writes_nothing():
    repo = FakeRepo()
    result = _handler(repo).handle_update_metadata(_cmd({'tags': ' , ,'}))

    assert result['success'] is True
    assert repo.added_tags == []
    assert repo.deleted_tags == 1  # 清空标签仍然生效


# ---------------- ACL ----------------

class _FakeStub:
    def __init__(self, pages=None, create=None, list_exc=None, create_exc=None):
        self._pages = list(pages or [])
        self._create = create
        self._list_exc = list_exc
        self._create_exc = create_exc
        self.create_calls = 0

    def ListTags(self, req, timeout=None):
        if self._list_exc:
            raise self._list_exc
        items = self._pages.pop(0) if self._pages else []
        return mock.Mock(success=True, message='',
                         data=json.dumps({'items': items, 'pages': 1}))

    def CreateTag(self, req, timeout=None):
        self.create_calls += 1
        if self._create_exc:
            raise self._create_exc
        return mock.Mock(success=self._create[0], message=self._create[1],
                         data=json.dumps(self._create[2]))


def _patch_stub(stub):
    return mock.patch('shared.clients.grpc_clients.get_tag_config_service_stub',
                      return_value=stub)


def test_acl_returns_existing_tag_id():
    stub = _FakeStub(pages=[[{'id': 233, 'name': 'INT1417_6f1a835c'}]])
    with _patch_stub(stub):
        tag = TagAclRepository().get_or_create_tag('INT1417_6f1a835c')
    assert tag.id == 233
    assert stub.create_calls == 0


def test_acl_creates_missing_tag():
    stub = _FakeStub(pages=[[]], create=(True, 'ok', {'id': 300, 'name': '新标签'}))
    with _patch_stub(stub):
        tag = TagAclRepository().get_or_create_tag('新标签')
    assert tag.id == 300
    assert tag.name == '新标签'
    assert stub.create_calls == 1


def test_acl_recovers_when_create_hits_concurrent_duplicate():
    """创建撞并发（CreateTag 失败）后复查一次，能拿到已存在的 id。"""
    stub = _FakeStub(pages=[[], [{'id': 301, 'name': '并发标签'}]],
                     create=(False, '标签名已存在', {}))
    with _patch_stub(stub):
        tag = TagAclRepository().get_or_create_tag('并发标签')
    assert tag.id == 301


def test_acl_raises_instead_of_returning_none_id():
    stub = _FakeStub(pages=[], list_exc=RuntimeError('connection refused'),
                     create_exc=RuntimeError('connection refused'))
    with _patch_stub(stub):
        with pytest.raises(TagResolutionError) as ei:
            TagAclRepository().get_or_create_tag('孤儿标签')
    assert '孤儿标签' in str(ei.value)


# ---------------- 持久层守卫 ----------------

def test_add_audio_tag_rejects_none_tag_id():
    class _Repo(AudioRelationMixin):
        pass

    with pytest.raises(TagResolutionError):
        _Repo().add_audio_tag(7, None)
