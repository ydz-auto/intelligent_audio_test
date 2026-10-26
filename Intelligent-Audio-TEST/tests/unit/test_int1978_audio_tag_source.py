# -*- coding: utf-8 -*-
"""INT-1978 tag_source 标签来源（json / path / both）后端链路单测

覆盖验收标准：
1. both（默认）：请求 tags + 路径目录标签合并去重，与改动前逐条等价
2. json：只有请求 tags，路径目录标签不出现
3. path：请求 tags + 路径目录标签都在（后端不过滤请求 tags）
4. 缺失 / 空串 / 未知值 → 等价 both，不抛异常
5. tagSource（camelCase）在 gRPC data 中同样生效
6. 秒传（md5 命中已有音频）在 tag_source='json' 下仍沿用已有音频标签
7. inherit_tags=true 时用例标签 = 该模式下的 audio_tags
8. 网关 MergeChunksRequest 接受 tag_source / tagSource，默认 both，非法值 422，
   extra='ignore' 行为不变；网关把原始 data 原样透传给 audio_service
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from audio_service.application.services.audio_testcase_creation_service import (
    AudioTestCaseCreationService,
)
from audio_service.application.services.audio_upload.merge_mixin import AudioMergeMixin
from audio_service.application.services.audio_upload.round_config_service import (
    AudioRoundConfigService,
)
from audio_service.domain.entities import UploadStatus
from api_gateway.application.services.audio import audio_upload_service as _audio_upload_service
from shared.constants.audio_tag import (
    AudioTagSource,
    resolve_tag_source,
    should_resolve_path_tags,
)


# ==================== 标签链路：_process_audio_tags ====================

class _TagRepo:
    """只实现标签相关的仓储替身，记录关联的标签名顺序"""

    def __init__(self):
        self._tags = {}
        self.links = []

    def get_or_create_tag(self, name):
        tag = self._tags.get(name)
        if tag is None:
            tag = SimpleNamespace(id=len(self._tags) + 1, name=name)
            self._tags[name] = tag
        return tag

    def add_audio_tag(self, audio_id, tag_id):
        self.links.append((audio_id, tag_id))

    def linked_names(self):
        by_id = {tag.id: name for name, tag in self._tags.items()}
        return [by_id[tag_id] for _audio_id, tag_id in self.links]


def _apply_tags(tag_source, user_tags, relative_path='客户A/日常对话/a.wav'):
    svc = AudioMergeMixin.__new__(AudioMergeMixin)
    svc.repo = _TagRepo()
    names = svc._process_audio_tags(
        SimpleNamespace(id=1), list(user_tags),
        SimpleNamespace(relative_path=relative_path), tag_source,
    )
    return names, svc.repo


class TestProcessAudioTagsModes:

    def test_both_merges_request_tags_and_path_tags(self):
        """both：请求 tags + 路径目录标签，重名不重复关联（改动前行为）"""
        names, repo = _apply_tags(
            AudioTagSource.BOTH, ['手填', '客户A'], '客户A/日常对话/a.wav')
        assert names == ['手填', '客户A', '日常对话']
        assert repo.linked_names() == ['手填', '客户A', '日常对话']

    def test_default_equals_both(self):
        """不传 tag_source（旧客户端）与显式 both 逐条等价"""
        default_names, default_repo = _apply_tags(None, ['手填'], '客户A/b.wav')
        both_names, both_repo = _apply_tags(AudioTagSource.BOTH, ['手填'], '客户A/b.wav')
        assert default_names == both_names == ['手填', '客户A']
        assert default_repo.linked_names() == both_repo.linked_names()

    def test_json_skips_path_tags_only(self):
        """json：只有请求 tags（含前端解析的 JSON tags），路径目录标签不出现"""
        names, _ = _apply_tags(
            AudioTagSource.JSON, ['手填', 'JSON标签'], '客户A/日常对话/a.wav')
        assert names == ['手填', 'JSON标签']
        assert '客户A' not in names and '日常对话' not in names

    def test_path_keeps_request_tags_and_path_tags(self):
        """path：后端不过滤请求 tags，请求 tags 与路径目录标签都在"""
        names, _ = _apply_tags(
            AudioTagSource.PATH, ['手填', 'JSON标签'], '客户A/日常对话/a.wav')
        assert names == ['手填', 'JSON标签', '客户A', '日常对话']

    def test_json_without_relative_path_is_noop(self):
        """json + 无 relative_path：等于只关联请求 tags"""
        names, _ = _apply_tags(AudioTagSource.JSON, ['手填'], '')
        assert names == ['手填']


class TestTagSourceDegrade:
    """audio_service 侧防御降级：缺失 / 空串 / 未知值一律 both，不抛异常"""

    @pytest.mark.parametrize('raw', [None, '', '   ', 'folder', 123, ['json']])
    def test_resolve_degrades_to_both(self, raw):
        assert resolve_tag_source(raw) is AudioTagSource.BOTH
        assert should_resolve_path_tags(raw) is True

    @pytest.mark.parametrize('raw,expected', [
        ('json', AudioTagSource.JSON),
        # INT-1991 F3：改为精确匹配后，大小写 / 首尾空白变体在 service 侧同为未知值 → both
        # （网关对同输入本就 422，两侧口径收敛）
        ('JSON', AudioTagSource.BOTH),
        (' json ', AudioTagSource.BOTH),
        ('JSoN', AudioTagSource.BOTH),
        ('path', AudioTagSource.PATH),
        ('both', AudioTagSource.BOTH),
        (AudioTagSource.JSON, AudioTagSource.JSON),
    ])
    def test_resolve_normalizes_known_values(self, raw, expected):
        assert resolve_tag_source(raw) is expected

    def test_unknown_value_does_not_raise_in_tag_chain(self):
        names, _ = _apply_tags('folder', ['手填'], '客户A/a.wav')
        assert names == ['手填', '客户A']


# ==================== 参数解析：extract_merge_params ====================

class TestExtractMergeParamsTagSource:

    def _params(self, data):
        return AudioRoundConfigService().extract_merge_params(data)

    def test_default_both_when_absent(self):
        assert self._params({'tags': []})['tag_source'] is AudioTagSource.BOTH

    def test_snake_case(self):
        assert self._params({'tag_source': 'json'})['tag_source'] is AudioTagSource.JSON

    def test_camel_case(self):
        """camelCase（gRPC data 双口径）同样生效"""
        assert self._params({'tagSource': 'json'})['tag_source'] is AudioTagSource.JSON

    def test_empty_and_unknown_degrade(self):
        assert self._params({'tag_source': ''})['tag_source'] is AudioTagSource.BOTH
        assert self._params({'tagSource': 'nope'})['tag_source'] is AudioTagSource.BOTH

    def test_camel_case_wins_when_both_keys_present(self):
        """INT-1991 F4：两键同时出现时 camelCase 优先，与网关 alias 优先级一致

        网关 pydantic alias=tagSource 优先，{'tag_source': 'folder', 'tagSource': 'json'}
        按 'json' 放行 200；service 侧若 snake 优先会取到 'folder' 并降级 both，形成绕过校验门的双口径。
        """
        params = self._params({'tag_source': 'folder', 'tagSource': 'json'})
        assert params['tag_source'] is AudioTagSource.JSON


# ==================== 秒传：tag_source 不生效 ====================

_EXISTING_AUDIO = SimpleNamespace(id=11, name='a.wav', original_filename='a.wav', md5='md5-x')


def _upload_file(relative_path='客户A/日常对话/a.wav'):
    return SimpleNamespace(
        total_chunks=0, status=UploadStatus.completed, completed_chunks=0,
        md5='md5-x', upload_task_id=1, filename='a.wav',
        original_filename='a.wav', relative_path=relative_path, id=5,
    )


class _InstantRepo:
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
        return ['已有A', '已有B']

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _instant_mixin(captured):
    mixin = AudioMergeMixin.__new__(AudioMergeMixin)
    mixin.repo = _InstantRepo()
    mixin._round_config_service = AudioRoundConfigService()
    mixin._annotation_service = SimpleNamespace(
        persist_annotations_and_raw=lambda *a, **kw: [])
    mixin._testcase_creation_service = SimpleNamespace(
        create_test_case_from_audio=lambda *a, **kw: (
            captured.append((a, kw)) or [100]))
    return mixin


class TestInstantUploadKeepsExistingTags:

    def test_json_mode_still_uses_existing_audio_tags(self):
        """秒传 json：沿用已有音频标签，不解析路径、不写请求 tags"""
        captured = []
        mixin = _instant_mixin(captured)
        result = mixin.merge_chunks({
            'file_id': 5, 'task_id': 1, 'create_test_case': True,
            'tag_source': 'json', 'tags': ['新标签'],
        })

        assert result['success'] is True
        assert captured, '秒传建用例应被调用'
        args, kwargs = captured[0]
        assert args[2] == ['已有A', '已有B']  # audio_tags 参数
        assert '客户A' not in args[2] and '新标签' not in args[2]
        assert kwargs['inherit_tags'] is True
        assert mixin.repo.commits == 1


# ==================== inherit_tags：用例标签 = 该模式 audio_tags ====================

DRY_DEVICES = [{'id': 7, 'name': 'Dry Speaker', 'device_type': 'dry', 'is_deleted': False}]


def _creation_service(captured):
    """真实 AudioTestCaseCreationService + 仓储/ACL 替身（参照 INT-113 做法）"""
    audio = SimpleNamespace(id=1, name='a.wav', md5='md5-1',
                           original_filename='a.wav', created_at=None)

    class _Repo:
        def get_audio(self, _id):
            return audio

        def find_audio_by_name(self, name):
            return audio if name == audio.name else None

        def list_audios(self, _query):
            return SimpleNamespace(items=[audio], total=1)

        def list_upload_files(self, _task_id):
            return []

        def get_audios_by_md5_list(self, _md5s):
            return []

    svc = AudioTestCaseCreationService.__new__(AudioTestCaseCreationService)
    svc.repo = _Repo()
    svc._playback_acl = SimpleNamespace(list_playback_devices=lambda: DRY_DEVICES)
    svc._testcase_acl = SimpleNamespace(
        list_testcases=lambda **kw: {'items': [], 'total': 0},
        create_testcase_config=lambda data: (captured.append(data), {'id': 100})[1],
    )
    svc._algorithm_acl = SimpleNamespace(list_case_params=lambda _t: [])
    return svc


class TestInheritTagsFollowsMode:

    def _case_tags(self, tag_source, inherit_tags=True):
        audio_tags, _repo = _apply_tags(
            tag_source, ['手填'], '客户A/日常对话/a.wav')
        captured = []
        svc = _creation_service(captured)
        svc.create_test_case_from_audio(
            1, ['api'], audio_tags, raw_annotations=None,
            inherit_tags=inherit_tags, upload_task_id='task-1978')
        assert len(captured) == 1
        return captured[0].get('tags'), audio_tags

    @pytest.mark.parametrize('tag_source,expected', [
        (AudioTagSource.BOTH, ['手填', '客户A', '日常对话']),
        (AudioTagSource.JSON, ['手填']),
        (AudioTagSource.PATH, ['手填', '客户A', '日常对话']),
    ])
    def test_inherit_tags_equals_mode_audio_tags(self, tag_source, expected):
        case_tags, audio_tags = self._case_tags(tag_source)
        assert audio_tags == expected
        assert case_tags == audio_tags

    def test_inherit_tags_false_drops_tags(self):
        case_tags, _audio_tags = self._case_tags(AudioTagSource.BOTH, inherit_tags=False)
        assert case_tags is None


# ==================== 网关契约 ====================

MERGE_BODY = {'file_id': 'f-1', 'task_id': 't-1'}


class TestMergeChunksRequestSchema:

    def test_default_both(self):
        m = _schema(MERGE_BODY)
        assert m.tag_source is AudioTagSource.BOTH

    def test_snake_case(self):
        assert _schema({**MERGE_BODY, 'tag_source': 'json'}).tag_source is AudioTagSource.JSON

    def test_camel_case(self):
        assert _schema({**MERGE_BODY, 'tagSource': 'path'}).tag_source is AudioTagSource.PATH

    @pytest.mark.parametrize('bad', ['folder', 'JSON ', 1, True, ['json']])
    def test_invalid_value_rejected(self, bad):
        with pytest.raises(ValidationError):
            _schema({**MERGE_BODY, 'tag_source': bad})

    def test_extra_fields_still_ignored(self):
        """extra='ignore' 不变：旧请求体 / 未知字段不受影响"""
        m = _schema({**MERGE_BODY, 'unknownField': 1, 'tagSource': 'json'})
        assert m.tag_source is AudioTagSource.JSON
        assert not hasattr(m, 'unknownField')


def _schema(body):
    from api_gateway.schemas.audio import MergeChunksRequest
    return MergeChunksRequest.model_validate(body)


def _make_app():
    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes.audio_bp import router as audio_router
    from api_gateway.utils.error_handlers import register_error_handlers
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(audio_router, prefix='/api/v1/audios', tags=['audios'])
    return app


class TestMergeEndpoint:

    def test_invalid_tag_source_returns_422(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            _audio_upload_service, '_audio_acl',
            SimpleNamespace(merge_chunks=lambda data: (calls.append(data), {
                'success': True, 'data': {}, 'message': 'ok', 'code': 200})[1]))
        r = TestClient(_make_app()).post(
            '/api/v1/audios/upload/merge', json={**MERGE_BODY, 'tag_source': 'folder'})
        assert r.status_code == 422
        assert calls == [], '校验失败不得调到 audio_service'

    def test_body_validation_failure_is_422_invalid_params(self, monkeypatch):
        """INT-1991 F2：端点级契约——请求体校验失败统一 422 + code=INVALID_PARAMS(100)

        此前为 400 / code=203；响应体形如 {success:false, code:100, message:"参数验证失败: ..."}。
        """
        monkeypatch.setattr(
            _audio_upload_service, '_audio_acl',
            SimpleNamespace(merge_chunks=lambda data: {
                'success': True, 'data': {}, 'message': 'ok', 'code': 200}))
        r = TestClient(_make_app()).post(
            '/api/v1/audios/upload/merge', json={**MERGE_BODY, 'tag_source': 'folder'})
        assert r.status_code == 422
        body = r.json()
        assert body['success'] is False
        assert body['code'] == 100
        assert body['message'].startswith('参数验证失败')

    def test_tag_source_four_cases(self, monkeypatch):
        """INT-1991 F2 实测四例：缺失/null → 200 + both；空串/非法枚举 → 422"""
        seen = []
        monkeypatch.setattr(
            _audio_upload_service, '_audio_acl',
            SimpleNamespace(merge_chunks=lambda data: (seen.append(data), {
                'success': True, 'data': {}, 'message': 'ok', 'code': 200})[1]))
        client = TestClient(_make_app())

        # 1) 字段缺失（不传）→ 200，service 侧降级 both
        r = client.post('/api/v1/audios/upload/merge', json=dict(MERGE_BODY))
        assert r.status_code == 200
        assert AudioRoundConfigService().extract_merge_params(
            seen[-1])['tag_source'] is AudioTagSource.BOTH

        # 2) 显式 null → 200 + both
        r = client.post('/api/v1/audios/upload/merge',
                        json={**MERGE_BODY, 'tag_source': None})
        assert r.status_code == 200
        assert AudioRoundConfigService().extract_merge_params(
            seen[-1])['tag_source'] is AudioTagSource.BOTH

        # 3) 空串 → 422，且不落到 audio_service
        before = len(seen)
        r = client.post('/api/v1/audios/upload/merge',
                        json={**MERGE_BODY, 'tag_source': ''})
        assert r.status_code == 422
        assert len(seen) == before

        # 4) 非法枚举值 → 422，且不落到 audio_service
        r = client.post('/api/v1/audios/upload/merge',
                        json={**MERGE_BODY, 'tag_source': 'folder'})
        assert r.status_code == 422
        assert len(seen) == before

    def test_camel_case_passed_through_raw(self, monkeypatch):
        """网关校验后仍原样透传 data（tagSource 不被改名/丢弃）"""
        calls = []
        monkeypatch.setattr(
            _audio_upload_service, '_audio_acl',
            SimpleNamespace(merge_chunks=lambda data: (calls.append(data), {
                'success': True, 'data': {}, 'message': 'ok', 'code': 200})[1]))
        r = TestClient(_make_app()).post(
            '/api/v1/audios/upload/merge', json={**MERGE_BODY, 'tagSource': 'json'})
        assert r.status_code == 200
        assert calls[0]['tagSource'] == 'json'
