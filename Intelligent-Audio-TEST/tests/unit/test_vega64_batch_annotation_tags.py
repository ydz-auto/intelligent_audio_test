# -*- coding: utf-8 -*-
"""VEGA-64 批量更新标注随行标签（items[].tags）追加合并写入。

模式参照 test_int2042_batch_annotation_async_refresh.py 的 handler 直测 + fake repo。
覆盖（方案 §5.4⑧）：
- tags 合并去重：已有标签跳过、列表内重复不重复写（audio_tags 表无唯一约束）；
- 不带 tags（None / 空列表）：完全不触碰该音频标签；
- 单标签 TagResolutionError：只跳过该标签，其余成功，响应 success（INT-1533 口径）；
- 私有非 owner 行：INT-564 过滤，标注与标签均跳过并计入 failed；
- 事务异常：rollback，已写的标注与标签不提交；
- tags 传字符串（gRPC 直连/旧客户端不经网关校验）：标注照写、无标签写入、
  无异常、响应 success（不逐字符建标签，R3 防御）。
"""
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('STORAGE_LOCAL_ROOT', tempfile.mkdtemp(prefix='vega64_'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')

from audio_service.application.commands.audio_commands import (
    BatchUpdateAnnotationsCommand,
)
from audio_service.application.handlers.audio_command_handler import (
    AudioCommandHandler,
)
from audio_service.domain.exceptions import TagResolutionError
from shared.infrastructure.user_context import set_current_user_id


class FakeAudio:
    def __init__(self, audio_id, visibility='shared', owner=None):
        self.id = audio_id
        self.name = f'audio_{audio_id}.wav'
        self.visibility = visibility
        self.created_by_user_id = owner


class FakeRepo:
    """handler 直测假仓储：标签三件套（查名 / 查建 / 加关联）内存记账。"""

    def __init__(self, audios):
        self.audios = audios
        self.committed = False
        self.rolled_back = False
        self.flushed = False
        # audio_id -> [tag_name]（既有标签 + 本次写入）
        self.audio_tags = {audio_id: [] for audio_id in audios}
        # tag_name -> tag_id 注册表（get_or_create_tag 查找/创建语义）
        self.tag_registry = {}
        self.next_tag_id = 100
        # 标签写入路径调用轨迹
        self.get_audio_tag_names_calls = []
        self.get_or_create_tag_calls = []
        self.added_tags = []  # [(audio_id, tag_name)]
        self.fail_tag_names = set()

    def get_audio(self, audio_id):
        return self.audios.get(int(audio_id))

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def get_audio_tag_names(self, audio_id):
        self.get_audio_tag_names_calls.append(int(audio_id))
        return list(self.audio_tags.get(int(audio_id), []))

    def get_or_create_tag(self, tag_name):
        self.get_or_create_tag_calls.append(tag_name)
        if tag_name in self.fail_tag_names:
            raise TagResolutionError(tag_name, 'task_service 不可达')
        if tag_name not in self.tag_registry:
            self.next_tag_id += 1
            self.tag_registry[tag_name] = self.next_tag_id
        return SimpleNamespace(id=self.tag_registry[tag_name], name=tag_name)

    def add_audio_tag(self, audio_id, tag_id):
        tag_name = next(
            name for name, tid in self.tag_registry.items() if tid == tag_id)
        self.added_tags.append((int(audio_id), tag_name))
        self.audio_tags[int(audio_id)].append(tag_name)


class FakeAnnotationService:
    def __init__(self, fail_audio=None):
        self.persisted = []
        self.fail_audio = fail_audio

    def persist_annotations_and_raw(self, audio_id, annotations, algorithm_type):
        if self.fail_audio is not None and int(audio_id) == self.fail_audio:
            raise RuntimeError('persist_annotations_and_raw 模拟失败')
        self.persisted.append(int(audio_id))
        return [{'code': 'reference', 'data': {'audio_id': audio_id}}]


def _make_handler(repo, fail_audio=None):
    handler = AudioCommandHandler(repository=repo)
    handler._annotation_service = FakeAnnotationService(fail_audio)
    # 标签用例不关心用例刷新（INT-2042 已覆盖），直接短路后台调度
    handler._schedule_testcase_refresh = lambda *args, **kwargs: False
    return handler


def _cmd(items):
    return BatchUpdateAnnotationsCommand(
        data={'items': items, 'refresh_test_cases': False})


def _item(audio_id, tags=None, annotations=None):
    item = {
        'audio_id': audio_id,
        'annotations': annotations or [{'code': 'reference', 'data': {'x': 1}}],
    }
    if tags is not None:
        item['tags'] = tags
    return item


def test_tags_merged_with_existing_dedup():
    """用例1（V64-01）：已有 [a] + 提交 [a,b,a] → [a,b]，无重复 add_audio_tag。"""
    repo = FakeRepo({1: FakeAudio(1)})
    repo.audio_tags[1] = ['a']
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(
        _cmd([_item(1, tags=['a', 'b', 'a'])]))

    assert result['success'] is True
    assert result['data']['updated_count'] == 1
    # 已有 a 跳过；b 新增一次；列表内重复 a / b 均不重复写
    assert repo.added_tags == [(1, 'b')]
    assert repo.audio_tags[1] == ['a', 'b']


def test_items_without_tags_do_not_touch_tags():
    """用例2（V64-02）：不带 tags（None）与空列表都不触碰标签。"""
    repo = FakeRepo({1: FakeAudio(1), 2: FakeAudio(2)})
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(
        _cmd([_item(1), _item(2, tags=[])]))

    assert result['success'] is True
    assert result['data']['updated_count'] == 2
    assert repo.get_audio_tag_names_calls == []
    assert repo.get_or_create_tag_calls == []
    assert repo.added_tags == []


def test_tag_resolution_error_skips_single_tag():
    """用例3（V64-03）：单标签解析失败只跳过，其余成功，响应仍 success。"""
    repo = FakeRepo({1: FakeAudio(1)})
    repo.fail_tag_names = {'bad'}
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(
        _cmd([_item(1, tags=['good', 'bad', 'good2'])]))

    assert result['success'] is True
    assert result['data']['updated_count'] == 1
    assert repo.added_tags == [(1, 'good'), (1, 'good2')]
    assert repo.audio_tags[1] == ['good', 'good2']


def test_private_non_owner_row_filtered():
    """用例4（V64-04）：私有非 owner 行标注与标签均被 INT-564 过滤，计入 failed。"""
    set_current_user_id(42)
    try:
        repo = FakeRepo({1: FakeAudio(1, visibility='private', owner=999)})
        handler = _make_handler(repo)

        result = handler.handle_batch_update_annotations(
            _cmd([_item(1, tags=['t1'])]))

        assert result['success'] is True
        assert result['data']['updated_count'] == 0
        assert result['data']['failed_count'] == 1
        assert handler._annotation_service.persisted == []
        assert repo.get_or_create_tag_calls == []
        assert repo.added_tags == []
    finally:
        set_current_user_id(None)


def test_exception_rolls_back_annotations_and_tags():
    """用例5（V64-03）：中途异常 rollback，已写标注与标签不提交。"""
    repo = FakeRepo({1: FakeAudio(1), 2: FakeAudio(2)})
    handler = _make_handler(repo, fail_audio=2)

    result = handler.handle_batch_update_annotations(
        _cmd([_item(1, tags=['t1']), _item(2)]))

    assert result['success'] is False
    assert repo.rolled_back is True
    assert repo.committed is False
    # audio 1 的标注与标签已写入但随异常回滚，绝不半提交
    assert handler._annotation_service.persisted == [1]
    assert repo.added_tags == [(1, 't1')]


def test_non_list_tags_string_is_ignored():
    """用例6（V64-15）：tags 传字符串 → 标注照写、无标签写入、无异常、success。"""
    repo = FakeRepo({1: FakeAudio(1)})
    handler = _make_handler(repo)

    result = handler.handle_batch_update_annotations(
        _cmd([_item(1, tags='abc')]))

    assert result['success'] is True
    assert result['data']['updated_count'] == 1
    assert handler._annotation_service.persisted == [1]
    # 不逐字符建标签（get_or_create_tag 从未被调用）
    assert repo.get_or_create_tag_calls == []
    assert repo.get_audio_tag_names_calls == []
    assert repo.added_tags == []
