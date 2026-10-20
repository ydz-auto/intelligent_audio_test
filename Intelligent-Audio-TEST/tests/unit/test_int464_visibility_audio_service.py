# -*- coding: utf-8 -*-
"""INT-464 数据可见性 audio_service 域单测。

覆盖（sqlite 文件库，不依赖真库）：
- audios PO visibility 列（默认 shared）+ 复合索引（PO 同步验收）
- list_audios / get_all_audio_ids / collect_folder_files 行级过滤
  （私有音频非 owner 不可见；owner/admin/共享三视角）
- get_audio_stats 与列表同口径（统计只含可见行）
- UpdateAudioVisibility gRPC 命令侧：按值落列 / 非法值 400 / 不存在 404
- 跟随用例同步（task_service 侧）：取最宽松聚合（任一 shared → shared；
  单私有用例 → private；gRPC 失败不抛出）
- _audio_to_dict 序列化透出 visibility / created_by_user_id

验收口径对齐原卡：
1. audios 列表行级过滤生效（私有非 owner 不可见）
2. 用例建/改后引用音频 visibility 与用例同步（经 gRPC）
3. 同一音频多用例引用取最宽松（任一 shared → shared）
4. 共享音频 / 管理场景零回归
5. pytest audio_service 套件全绿
"""
import os
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int464_unit_') + '/unit.db')

import pytest

from shared.models.common_enums import Visibility
from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from shared.infrastructure.user_context import (
    set_current_user_id, set_current_user_is_admin,
)
from shared.proto import audio_service_pb2 as audio_pb


@pytest.fixture(scope='module')
def db():
    """初始化 sqlite 文件库并建 audios / test_cases 表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from audio_service.infrastructure.persistence.models import Audio
    from task_service.infrastructure.persistence.models import TestCase
    Base.metadata.create_all(
        bind=engine,
        tables=[Audio.__table__, TestCase.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture(autouse=True)
def _clean_ctx_and_db(db):
    """每个用例清理 user context 与表数据。"""
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)
    remove_db_session()


def _insert_audio(audio_id, owner, visibility, **extra):
    """插入一条音频记录（file_path 等必填列给最小占位）。"""
    from audio_service.infrastructure.persistence.models import Audio
    session = get_db_session()
    po = Audio(
        id=audio_id,
        name=extra.get('name') or f'audio_{audio_id}',
        file_path=extra.get('file_path') or f'/tmp/a{audio_id}.wav',
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


def _insert_case(case_id, config, owner=None, visibility=None):
    """插入一条用例记录（config JSON 引用音频）。"""
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    tc = TestCase(
        id=case_id,
        name=f'case_{case_id}',
        config=config,
        group_id='g_test',
        created_by_user_id=owner,
    )
    if visibility is not None:
        tc.visibility = visibility
    session.add(tc)
    session.flush()
    return tc.id


class TestAudioVisibilityPO:
    """验收：audios 表加 visibility 列（PO 同步）。"""

    def test_visibility_column_exists_with_shared_default(self):
        from audio_service.infrastructure.persistence.models import Audio
        col = Audio.__table__.c.visibility
        assert col.nullable is False
        # 列级 default 与 server_default 均为 shared（新建/存量零回归）
        assert col.default is not None and col.default.arg == Visibility.SHARED.value
        assert col.server_default is not None

    def test_composite_index_exists(self):
        from audio_service.infrastructure.persistence.models import Audio
        names = {ix.name for ix in Audio.__table__.indexes}
        assert 'idx_audios_created_visibility' in names


class TestListAudiosVisibilityFiltering:
    """验收①：audios 列表行级过滤生效。"""

    AUDIOS = [
        # (audio_id, owner, visibility)
        (1, 1, 'private'),   # user1 的私有
        (2, 2, 'private'),   # user2 的私有
        (3, 2, 'shared'),    # user2 的共享
        (4, None, 'shared'),  # 无 owner 的共享
    ]

    @pytest.fixture(autouse=True)
    def _seed(self, db):
        for audio_id, owner, vis in self.AUDIOS:
            _insert_audio(audio_id, owner, vis)

    def _list_ids(self, user_id, is_admin):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        set_current_user_id(user_id)
        set_current_user_is_admin(is_admin)
        pagination = audio_repository.list_audios({'page': 1, 'per_page': 100})
        return sorted(a.id for a in pagination.items)

    def test_owner_sees_own_private_plus_shared(self):
        assert self._list_ids(1, False) == [1, 3, 4]

    def test_other_user_private_hidden(self):
        assert self._list_ids(2, False) == [2, 3, 4]

    def test_anonymous_only_shared(self):
        assert self._list_ids(None, False) == [3, 4]

    def test_admin_sees_all(self):
        assert self._list_ids(1, True) == [1, 2, 3, 4]
        assert self._list_ids(None, True) == [1, 2, 3, 4]


class TestGetAllAudioIdsAndFolderTreeFiltering:
    """列表类读路径同口径过滤（get_all_audio_ids / collect_folder_files）。"""

    def _seed(self, db):
        for audio_id, owner, vis in [
            (11, 1, 'private'),
            (12, 2, 'private'),
            (13, 2, 'shared'),
        ]:
            _insert_audio(audio_id, owner, vis)

    def test_get_all_audio_ids_filtered(self, db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        self._seed(db)
        set_current_user_id(1)
        set_current_user_is_admin(False)
        ids = audio_repository.get_all_audio_ids({'page': 1, 'per_page': 100})
        assert sorted(ids) == [11, 13]

    def test_collect_folder_files_filtered(self, db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        self._seed(db)
        set_current_user_id(1)
        set_current_user_is_admin(False)
        rows = audio_repository.collect_folder_files({})
        ids = [r[0] for r in rows]
        assert sorted(ids) == [11, 13]


class TestGetAudioStatsFiltered:
    """列表响应 stats 与列表同口径（统计只含可见行）。"""

    def test_stats_only_visible(self, db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        for audio_id, owner, vis in [
            (21, 1, 'private'),
            (22, 2, 'private'),
            (23, 2, 'shared'),
        ]:
            _insert_audio(audio_id, owner, vis, size=100)
        set_current_user_id(1)
        set_current_user_is_admin(False)
        stats = audio_repository.get_audio_stats()
        # 可见行 21（私有 owner）+ 23（共享），各 100B
        assert stats['total_size'] == 200

    def test_admin_stats_all(self, db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        for audio_id, owner, vis in [
            (24, 1, 'private'),
            (25, 2, 'private'),
            (26, 2, 'shared'),
        ]:
            _insert_audio(audio_id, owner, vis, size=100)
        set_current_user_id(1)
        set_current_user_is_admin(True)
        stats = audio_repository.get_audio_stats()
        assert stats['total_size'] == 300


class TestUpdateAudioVisibilityCommand:
    """验收②：audio_service 侧 UpdateAudioVisibility 命令按值落列。"""

    def _handler(self):
        from audio_service.application.commands.audio_commands import (
            UpdateAudioVisibilityCommand,
        )
        from audio_service.application.handlers.audio_command_handler import (
            AudioCommandHandler,
        )
        from audio_service.infrastructure.persistence.audio_repository import (
            audio_repository,
        )
        return AudioCommandHandler(repository=audio_repository), UpdateAudioVisibilityCommand

    def _current_visibility(self, audio_id):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        audio = audio_repository.get_audio(audio_id)
        return audio.visibility

    def test_set_private_and_shared(self, db):
        _insert_audio(101, 1, 'shared')
        handler, Cmd = self._handler()
        assert handler.handle_update_audio_visibility(Cmd(audio_id=101, visibility='private'))['success'] is True
        assert self._current_visibility(101) == 'private'
        assert handler.handle_update_audio_visibility(Cmd(audio_id=101, visibility='shared'))['success'] is True
        assert self._current_visibility(101) == 'shared'

    def test_accepts_enum_values_only(self, db):
        _insert_audio(102, 1, 'shared')
        handler, Cmd = self._handler()
        resp = handler.handle_update_audio_visibility(Cmd(audio_id=102, visibility='team'))
        assert resp['success'] is False
        assert resp['code'] == 400
        assert self._current_visibility(102) == 'shared'

    def test_missing_audio_returns_404(self, db):
        handler, Cmd = self._handler()
        resp = handler.handle_update_audio_visibility(Cmd(audio_id=99999, visibility='private'))
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_servicer_wires_rpc(self, db):
        """gRPC servicer UpdateAudioVisibility 委托命令处理器成功。"""
        from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
        _insert_audio(103, 1, 'shared')
        svc = AudioConfigServiceServicer()
        resp = svc.UpdateAudioVisibility(
            audio_pb.UpdateAudioVisibilityRequest(audio_id=103, visibility='private'))
        assert resp.success is True
        assert self._current_visibility(103) == 'private'


class TestSyncCaseAudioVisibility:
    """验收②③：跟随用例同步 + 取最宽松聚合。"""

    @pytest.fixture(autouse=True)
    def _monkey_acl(self, monkeypatch):
        """捕获 task_service → audio_service gRPC 调用，避免真 gRPC。"""
        calls = []
        import task_service.infrastructure.acl.audio_acl_repository as acl_mod
        monkeypatch.setattr(
            acl_mod.audio_acl_repository, 'update_audio_visibility',
            lambda audio_id, vis: calls.append((audio_id, vis)) or True,
        )
        return calls

    @staticmethod
    def _rounds_config(audio_ids, bg_noise_id=None):
        cfg = {'rounds': [{'roundNumber': 1, 'audios': [
            {'audio_id': a, 'spl': 70, 'play_order': i + 1} for i, a in enumerate(audio_ids)
        ]}]}
        if bg_noise_id is not None:
            cfg['rounds'][0]['backgroundNoise'] = {'audio_id': bg_noise_id, 'spl': 60}
        return cfg

    def test_shared_case_sets_audio_shared(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        sync_case_audio_visibility('case-1', 'shared', self._rounds_config([201]))
        assert _monkey_acl == [(201, 'shared')]

    def test_standalone_private_case_sets_audio_private(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        sync_case_audio_visibility('case-1', 'private', self._rounds_config([202]))
        assert _monkey_acl == [(202, 'private')]

    def test_private_case_keeps_audio_shared_when_other_shared_case_references(self, db, _monkey_acl):
        """验收③：任一用例 shared → audio shared（避免过度隐藏）。"""
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        # 既有共享用例引用 audio 203
        _insert_case('case-shared', self._rounds_config([203]), visibility='shared')
        sync_case_audio_visibility('case-new-private', 'private', self._rounds_config([203]))
        assert _monkey_acl == [(203, 'shared')]

    def test_private_case_audio_private_when_other_private_case_references(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        _insert_case('case-other-private', self._rounds_config([204]), visibility='private')
        sync_case_audio_visibility('case-new-private', 'private', self._rounds_config([204]))
        assert _monkey_acl == [(204, 'private')]

    def test_collects_rounds_and_background_noise(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        sync_case_audio_visibility('case-1', 'private',
                                   self._rounds_config([205], bg_noise_id=206))
        assert (205, 'private') in _monkey_acl
        assert (206, 'private') in _monkey_acl

    def test_shared_case_marks_both_audio_and_noise_shared(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        sync_case_audio_visibility('case-1', 'shared',
                                   self._rounds_config([207], bg_noise_id=208))
        assert (207, 'shared') in _monkey_acl
        assert (208, 'shared') in _monkey_acl

    def test_grpc_failure_does_not_raise(self, db, monkeypatch):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        import task_service.infrastructure.acl.audio_acl_repository as acl_mod

        def _fail(audio_id, vis):
            raise RuntimeError('audio_service 不可达')

        monkeypatch.setattr(acl_mod.audio_acl_repository, 'update_audio_visibility', _fail)
        # 不应抛出，主流程不受影响
        sync_case_audio_visibility('case-1', 'private', self._rounds_config([209]))

    def test_empty_config_noop(self, db, _monkey_acl):
        from task_service.application.testcase.audio_visibility_sync import (
            sync_case_audio_visibility,
        )
        sync_case_audio_visibility('case-1', 'private', {})
        sync_case_audio_visibility('case-1', 'private', None)
        assert _monkey_acl == []


class TestTestCaseCrudCreateSyncHook:
    """验收②：用例 create 流触发引用音频可见性同步（经 gRPC，非直写）。"""

    def test_create_fires_sync_with_case_visibility(self, db, monkeypatch):
        import task_service.infrastructure.acl.audio_acl_repository as acl_mod
        calls = []
        monkeypatch.setattr(
            acl_mod.audio_acl_repository, 'update_audio_visibility',
            lambda audio_id, vis: calls.append((audio_id, vis)) or True,
        )
        # 屏蔽统计缓存刷新（本进程无 gRPC 服务，属 create 的附带告警）
        monkeypatch.setattr(
            'api_gateway.application.services.stats_cache.refresh_stats_cache',
            lambda *a, **k: None,
        )
        _insert_audio(401, 7, 'shared')
        set_current_user_id(7)

        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        result = testcase_crud_service.create({
            'name': 'int464-create-hook',
            'group_id': 'grp-test',
            'audios': [{'audio_id': 401, 'spl': 70, 'play_order': 1}],
            'visibility': 'private',
        })
        assert result.get('success') is True
        assert calls == [(401, 'private')]

    def test_create_shared_case_marks_audio_shared(self, db, monkeypatch):
        import task_service.infrastructure.acl.audio_acl_repository as acl_mod
        calls = []
        monkeypatch.setattr(
            acl_mod.audio_acl_repository, 'update_audio_visibility',
            lambda audio_id, vis: calls.append((audio_id, vis)) or True,
        )
        monkeypatch.setattr(
            'api_gateway.application.services.stats_cache.refresh_stats_cache',
            lambda *a, **k: None,
        )
        _insert_audio(402, 7, 'shared')
        set_current_user_id(7)

        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        result = testcase_crud_service.create({
            'name': 'int464-create-shared',
            'group_id': 'grp-test',
            'audios': [{'audio_id': 402, 'spl': 70, 'play_order': 1}],
            'visibility': 'shared',
        })
        assert result.get('success') is True
        assert calls == [(402, 'shared')]


class TestAudioToDictSerialization:
    """接口序列化透出 visibility / created_by_user_id（供前端徽标/网关校验）。"""

    @staticmethod
    def _to_dict(audio):
        from audio_service.application.handlers.audio_query_handler import _audio_to_dict
        return _audio_to_dict(audio)

    def test_dict_includes_visibility_and_owner(self, db):
        _insert_audio(301, 7, 'private')
        from audio_service.infrastructure.persistence.audio_repository import (
            audio_repository,
        )
        audio = audio_repository.get_audio(301)
        d = self._to_dict(audio)
        assert d['visibility'] == 'private'
        assert d['created_by_user_id'] == 7

    def test_new_audio_defaults_shared(self, db):
        from audio_service.infrastructure.persistence.audio_repository import (
            audio_repository,
        )
        set_current_user_id(7)
        agg = audio_repository.create_audio({
            'name': 'new.wav', 'file_path': '/tmp/new.wav',
            'size': 1, 'duration': 1.0,
        })
        d = self._to_dict(agg)
        assert d['visibility'] == 'shared'
        assert d['created_by_user_id'] == 7
