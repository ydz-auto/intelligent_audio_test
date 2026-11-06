# -*- coding: utf-8 -*-
"""INT-564 数据可见性 audio_bp 详情/CRUD owner 校验单测。

覆盖验收标准 1~4（下游命令侧 + 网关 audio_bp 直连边界）：
1. 非 owner GET 私有音频 → 404（audio_bp 直连详情端点 / 流式 / 路径式）
2. 非 owner update / delete 私有音频 → 403（audio_service 命令侧强制）
3. owner / admin 全操作正常；admin 私有态审计保留（网关旁路既有测试覆盖）
4. 共享音频零回归；宿主语境只读豁免——下游详情读（handle_get_audio / by_ids）
   维持宽松语义（用例 preview/playback 与编辑回填不被阻断），严格校验在
   audio_bp 直连 HTTP 边界强制（网关 AudioQueryService.get_one）

DB：sqlite 文件库（对齐 test_int464 范式），不依赖真库。
"""
import os
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int564_unit_') + '/unit.db')

import pytest

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from shared.infrastructure.user_context import (
    set_current_user_id, set_current_user_is_admin,
)


def _clear_audio_tables():
    """清空本模块用到的 audio 相关表（模块级共享 sqlite，保证与其他测试文件
    组合运行时数据不串扰——run 前后各清一次）。"""
    from audio_service.infrastructure.persistence.models import (
        Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
    )
    session = get_db_session()
    for model in (AudioAlgorithmRelation, AudioAnnotation, AudioTag, Audio):
        session.query(model).delete()
    session.commit()
    remove_db_session()


@pytest.fixture(scope='module')
def db():
    """初始化 sqlite 文件库并建 audio 相关表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from audio_service.infrastructure.persistence.models import Audio
    from audio_service.infrastructure.persistence.models import AudioAnnotation
    from audio_service.infrastructure.persistence.models import AudioTag
    from audio_service.infrastructure.persistence.models import AudioAlgorithmRelation
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Audio.__table__, AudioAnnotation.__table__,
            AudioTag.__table__, AudioAlgorithmRelation.__table__,
        ],
    )
    _clear_audio_tables()
    yield
    _clear_audio_tables()
    remove_db_session()


@pytest.fixture(autouse=True)
def _clean_ctx_and_db(db):
    """每个用例清理 user context 与表数据。"""
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)
    remove_db_session()


def _insert_audio(audio_id, owner, visibility, file_path=None, **extra):
    """插入一条音频记录（file_path 等必填列给最小占位）。"""
    from audio_service.infrastructure.persistence.models import Audio
    session = get_db_session()
    po = Audio(
        id=audio_id,
        name=extra.get('name') or f'audio_{audio_id}',
        file_path=file_path or f'/tmp/a{audio_id}.wav',
        size=extra.get('size', 100),
        duration=extra.get('duration', 1.0),
        format=extra.get('format', 'wav'),
        audio_type=extra.get('audio_type', 'dry'),
        created_by_user_id=owner,
        visibility=visibility,
    )
    session.add(po)
    session.flush()
    return po.id


def _cmd_handler():
    """构造写命令处理器（注入真实仓储）。"""
    from audio_service.application.handlers.audio_command_handler import (
        AudioCommandHandler,
    )
    from audio_service.infrastructure.persistence.audio_repository import (
        audio_repository,
    )
    return AudioCommandHandler(repository=audio_repository)


def _qry_handler():
    """构造读查询处理器（注入真实仓储）。"""
    from audio_service.application.handlers.audio_query_handler import (
        AudioQueryHandler,
    )
    from audio_service.infrastructure.persistence.audio_repository import (
        audio_repository,
    )
    return AudioQueryHandler(repository=audio_repository)


def _stub_ref_acl(handler):
    """替换 handler 的跨域引用检查 ACL（返回 0 引用，放行删除路径）。"""
    from types import SimpleNamespace
    handler._task_acl = SimpleNamespace(
        check_audio_in_testcases=lambda _: 0,
        check_audio_in_testcase_noise=lambda _: 0,
        check_audio_in_tasks=lambda _: 0,
        # 合入适配（INT-1722）：INT-1306 已把引用检查改为批量 gRPC，桩需同步补
        # check_audio_references_batch（本用例只关注 owner 校验，引用恒 0 放行）
        check_audio_references_batch=lambda ids: {i: {} for i in ids},
    )
    handler._device_acl = SimpleNamespace(
        check_audio_in_devices=lambda _: 0,
    )


# ---------------- 命令侧（写路径）：私有非 owner → 403 ----------------

class TestCommandWriteOwnerChecks:
    """验收②：非 owner update / delete 私有音频 → 403（无宿主豁免）。"""

    def _update_metadata(self, audio_id, data=None):
        from audio_service.application.commands.audio_commands import (
            UpdateAudioMetadataCommand,
        )
        handler = _cmd_handler()
        return handler.handle_update_metadata(
            UpdateAudioMetadataCommand(audio_id=audio_id, data=data or {}))

    def test_update_private_non_owner_403(self, db):
        _insert_audio(6001, 100, 'private')
        set_current_user_id(200)
        resp = self._update_metadata(6001)
        assert resp['success'] is False
        assert resp['code'] == 403

    def test_update_private_owner_ok(self, db):
        _insert_audio(6002, 100, 'private')
        set_current_user_id(100)
        resp = self._update_metadata(6002)
        assert resp['success'] is True

    def test_update_private_admin_ok(self, db):
        _insert_audio(6003, 100, 'private')
        set_current_user_id(1)
        set_current_user_is_admin(True)
        resp = self._update_metadata(6003)
        assert resp['success'] is True

    def test_update_shared_non_owner_ok(self, db):
        """验收④：共享音频零回归——非 owner 可更新。"""
        _insert_audio(6004, 100, 'shared')
        set_current_user_id(200)
        resp = self._update_metadata(6004)
        assert resp['success'] is True

    def test_update_missing_audio_404(self, db):
        set_current_user_id(200)
        resp = self._update_metadata(99999)
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_delete_private_non_owner_403(self, db):
        from audio_service.application.commands.audio_commands import (
            DeleteAudioCommand,
        )
        _insert_audio(6005, 100, 'private')
        handler = _cmd_handler()
        _stub_ref_acl(handler)
        set_current_user_id(200)
        resp = handler.handle_delete(DeleteAudioCommand(audio_id=6005))
        assert resp['success'] is False
        assert resp['code'] == 403

    def test_delete_private_owner_ok(self, db):
        from audio_service.application.commands.audio_commands import (
            DeleteAudioCommand,
        )
        _insert_audio(6006, 100, 'private')
        handler = _cmd_handler()
        _stub_ref_acl(handler)
        set_current_user_id(100)
        resp = handler.handle_delete(DeleteAudioCommand(audio_id=6006))
        assert resp['success'] is True

    def test_update_algorithms_private_non_owner_403(self, db):
        from audio_service.application.commands.audio_commands import (
            UpdateAudioAlgorithmsCommand,
        )
        _insert_audio(6007, 100, 'private')
        handler = _cmd_handler()
        set_current_user_id(200)
        resp = handler.handle_update_audio_algorithms(
            UpdateAudioAlgorithmsCommand(audio_id=6007, data={'algorithms': []}))
        assert resp['success'] is False
        assert resp['code'] == 403

    def test_update_algorithms_private_owner_ok(self, db):
        from audio_service.application.commands.audio_commands import (
            UpdateAudioAlgorithmsCommand,
        )
        _insert_audio(6008, 100, 'private')
        handler = _cmd_handler()
        set_current_user_id(100)
        resp = handler.handle_update_audio_algorithms(
            UpdateAudioAlgorithmsCommand(audio_id=6008, data={'algorithms': []}))
        assert resp['success'] is True


# ---------------- 读路径：私有非 owner → 404（非宿主语境） ----------------

class TestQueryReadOwnerChecks:
    """验收①：stream / stream-by-path / algorithms 读路径私有非 owner → 404。"""

    def _stream(self, audio_id):
        from audio_service.application.queries.audio_queries import StreamAudioQuery
        handler = _qry_handler()
        return handler.handle_stream_audio(StreamAudioQuery(audio_id=audio_id, data={}))

    def test_stream_private_non_owner_404(self, db, monkeypatch):
        _insert_audio(6011, 100, 'private')
        set_current_user_id(200)
        resp = self._stream(6011)
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_stream_private_owner_ok(self, db, monkeypatch):
        _insert_audio(6012, 100, 'private')
        import importlib
        qry_mod = importlib.import_module('audio_service.application.handlers.audio_query_handler')
        monkeypatch.setattr(qry_mod.storage, 'get_url', lambda *a, **k: None)
        set_current_user_id(100)
        resp = self._stream(6012)
        assert resp['success'] is True
        assert resp['data']['url']

    def test_stream_shared_non_owner_ok(self, db, monkeypatch):
        """验收④：共享音频零回归。"""
        _insert_audio(6013, 100, 'shared')
        import importlib
        qry_mod = importlib.import_module('audio_service.application.handlers.audio_query_handler')
        monkeypatch.setattr(qry_mod.storage, 'get_url', lambda *a, **k: None)
        set_current_user_id(200)
        resp = self._stream(6013)
        assert resp['success'] is True

    def test_stream_missing_audio_404(self, db):
        set_current_user_id(200)
        resp = self._stream(99999)
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_stream_by_path_private_non_owner_404(self, db):
        from audio_service.application.queries.audio_queries import (
            StreamAudioByPathQuery,
        )
        _insert_audio(6014, 100, 'private', file_path='audios/priv14.wav')
        handler = _qry_handler()
        set_current_user_id(200)
        resp = handler.handle_stream_audio_by_path(
            StreamAudioByPathQuery(data={'path': 'audios/priv14.wav'}))
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_stream_by_path_private_owner_ok(self, db, monkeypatch):
        from audio_service.application.queries.audio_queries import (
            StreamAudioByPathQuery,
        )
        _insert_audio(6015, 100, 'private', file_path='audios/priv15.wav')
        import importlib
        qry_mod = importlib.import_module('audio_service.application.handlers.audio_query_handler')
        monkeypatch.setattr(qry_mod.storage, 'get_url', lambda *a, **k: None)
        handler = _qry_handler()
        set_current_user_id(100)
        resp = handler.handle_stream_audio_by_path(
            StreamAudioByPathQuery(data={'path': 'audios/priv15.wav'}))
        assert resp['success'] is True

    def test_get_audio_algorithms_private_non_owner_404(self, db):
        from audio_service.application.queries.audio_queries import (
            GetAudioAlgorithmsQuery,
        )
        _insert_audio(6016, 100, 'private')
        handler = _qry_handler()
        set_current_user_id(200)
        resp = handler.handle_get_audio_algorithms(
            GetAudioAlgorithmsQuery(audio_id=6016))
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_get_audio_algorithms_private_owner_ok(self, db):
        from audio_service.application.queries.audio_queries import (
            GetAudioAlgorithmsQuery,
        )
        _insert_audio(6017, 100, 'private')
        handler = _qry_handler()
        set_current_user_id(100)
        resp = handler.handle_get_audio_algorithms(
            GetAudioAlgorithmsQuery(audio_id=6017))
        assert resp['success'] is True
        assert resp['data'] == []


# ---------------- 宿主语境只读豁免（规划师裁定 INT-564 §2/§3） ----------------

class TestHostContextReadExemption:
    """宿主优先只读豁免：严格详情读在 audio_service 强制（私有非 owner 404），
    宿主语境批量读（by_ids）维持宽松语义——用例预览改走 by-ids、用例编辑
    模态窗回填音频元数据不被私有音频 404 阻断。
    """

    def test_get_audio_detail_strict_private_non_owner_404(self, db):
        """下游详情读与六域同口径：私有非 owner 详情 404（防探测）。"""
        from audio_service.application.queries.audio_queries import GetAudioQuery
        _insert_audio(6021, 100, 'private')
        handler = _qry_handler()
        set_current_user_id(200)
        resp = handler.handle_get_audio(GetAudioQuery(audio_id=6021))
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_get_audio_detail_owner_ok(self, db):
        from audio_service.application.queries.audio_queries import GetAudioQuery
        _insert_audio(6022, 100, 'private')
        handler = _qry_handler()
        set_current_user_id(100)
        resp = handler.handle_get_audio(GetAudioQuery(audio_id=6022))
        assert resp['success'] is True
        assert resp['data']['id'] == 6022

    def test_by_ids_host_context_stays_permissive(self, db):
        """宿主语境批量读（by_ids）不做二次 owner 过滤：用例编辑模态窗回填/
        用例预览批量取数不被私有音频 404 阻断。"""
        from audio_service.application.queries.audio_queries import (
            GetAudiosByIdsQuery,
        )
        _insert_audio(6023, 100, 'private')
        handler = _qry_handler()
        set_current_user_id(200)
        resp = handler.handle_get_by_ids(GetAudiosByIdsQuery(ids=[6023]))
        assert resp['success'] is True
        assert [a['id'] for a in resp['data']] == [6023]


# ---------------- 网关 audio_bp 直连边界（私有非 owner 详情 404 / 写 403） ----------------

def _fake_request(user_id=100, permissions=None, json_body=None):
    from types import SimpleNamespace
    state = SimpleNamespace(
        user_id=user_id,
        permissions=list(permissions or []),
        username='dev_user',
        role_id=1,
        _json_body=json_body or {},
    )
    return SimpleNamespace(state=state, query_params={})


class TestGatewayAudioBoundary:
    """验收①/②：audio_bp 直连 HTTP 边界私有非 owner 详情 404、写 403。"""

    @pytest.fixture(autouse=True)
    def _reset_request(self):
        yield
        from api_gateway.infrastructure.request_adapter import set_current_request
        set_current_request(None)

    def _stub_audio_acl(self, monkeypatch, audio_dict, write_result=None):
        from api_gateway.application.services.audio import (
            audio_query_service as qry_mod,
            audio_command_service as cmd_mod,
        )
        from types import SimpleNamespace
        stub = SimpleNamespace(
            get_one=lambda _id: {'success': True, 'data': audio_dict},
            update_metadata=lambda *_a, **_k: (write_result or
                                               {'success': True, 'data': None, 'message': 'ok'}),
            delete=lambda *_a, **_k: (write_result or
                                       {'success': True, 'data': None, 'message': 'ok'}),
            update_audio_algorithms=lambda *_a, **_k: (write_result or
                                                       {'success': True, 'data': None, 'message': 'ok'}),
            stream_audio_by_path=lambda *_a, **_k: {'success': True, 'data': {'url': 'x'}},
        )
        monkeypatch.setattr(qry_mod, '_audio_acl', stub)
        monkeypatch.setattr(cmd_mod, '_audio_acl', stub)
        return stub

    def _audio_dict(self, audio_id, owner, visibility):
        return {
            'id': audio_id, 'name': 'a', 'file_path': '/tmp/a.wav',
            'duration': 1.0, 'size': 100, 'format': 'wav',
            'audio_type': 'dry', 'visibility': visibility,
            'created_by_user_id': owner,
        }

    def test_get_one_private_non_owner_404(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_query_service import (
            AudioQueryService,
        )
        self._stub_audio_acl(monkeypatch, self._audio_dict(6031, 100, 'private'))
        set_current_request(_fake_request(user_id=200, permissions=['audio:read']))
        payload, http_code = AudioQueryService.get_one(6031)
        assert http_code == 404
        assert payload['success'] is False

    def test_get_one_private_owner_200(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_query_service import (
            AudioQueryService,
        )
        self._stub_audio_acl(monkeypatch, self._audio_dict(6032, 100, 'private'))
        set_current_request(_fake_request(user_id=100, permissions=['audio:read']))
        payload, http_code = AudioQueryService.get_one(6032)
        assert http_code == 200
        assert payload['success'] is True
        assert payload['data']['visibility'] == 'private'

    def test_get_one_private_admin_200(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_query_service import (
            AudioQueryService,
        )
        self._stub_audio_acl(monkeypatch, self._audio_dict(6033, 100, 'private'))
        set_current_request(_fake_request(user_id=1, permissions=['*']))
        payload, http_code = AudioQueryService.get_one(6033)
        assert http_code == 200
        assert payload['success'] is True

    def test_get_one_shared_non_owner_200(self, monkeypatch):
        """验收④：共享音频零回归。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_query_service import (
            AudioQueryService,
        )
        self._stub_audio_acl(monkeypatch, self._audio_dict(6034, 100, 'shared'))
        set_current_request(_fake_request(user_id=200, permissions=['audio:read']))
        payload, http_code = AudioQueryService.get_one(6034)
        assert http_code == 200
        assert payload['success'] is True

    def test_update_metadata_private_non_owner_403(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_command_service import (
            AudioCommandService,
        )
        self._stub_audio_acl(
            monkeypatch, self._audio_dict(6035, 100, 'private'),
            write_result={'success': False, 'data': None, 'message': '资源不存在或无权访问',
                          'code': 403})
        set_current_request(_fake_request(user_id=200, permissions=['audio:update'],
                                          json_body={'name': 'x'}))
        payload, http_code = AudioCommandService.update_metadata(6035)
        assert http_code == 403
        assert payload['success'] is False

    def test_delete_private_non_owner_403(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_command_service import (
            AudioCommandService,
        )
        self._stub_audio_acl(
            monkeypatch, self._audio_dict(6036, 100, 'private'),
            write_result={'success': False, 'data': None, 'message': '资源不存在或无权访问',
                          'code': 403})
        set_current_request(_fake_request(user_id=200, permissions=['audio:delete']))
        payload, http_code = AudioCommandService.delete(6036)
        assert http_code == 403
        assert payload['success'] is False

    def test_update_metadata_owner_200(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.audio.audio_command_service import (
            AudioCommandService,
        )
        self._stub_audio_acl(monkeypatch, self._audio_dict(6037, 100, 'private'))
        set_current_request(_fake_request(user_id=100, permissions=['audio:update'],
                                          json_body={'name': 'x'}))
        payload, http_code = AudioCommandService.update_metadata(6037)
        assert http_code == 200
        assert payload['success'] is True
