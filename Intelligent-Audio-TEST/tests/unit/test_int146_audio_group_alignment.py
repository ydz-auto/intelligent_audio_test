# -*- coding: utf-8 -*-
"""INT-146 音频/分组域 V9.7.10 对齐缺陷包（缺陷 2/3/4/5）单测。

- 缺陷2：音频列表/全选 ID 查询恢复 algorithm_type 过滤（按音频-算法关联表，
  软删关联不参与匹配），网关查询模型与透传链路恢复该参数。
- 缺陷3：分组列表筛选（keyword / test_type / dimension_id）端到端恢复——
  网关 GroupListQuery 接参、GetTestCaseStats gRPC 扩展过滤、task_service
  仓储 keyword SQL 过滤 + test_type 按配置形态派生（列已废弃）过滤。
- 缺陷4：本地存储降级模式回退地址 /api/v1/audios/download 网关路由补齐
  （扩展名白名单 / 目录穿越拒绝 / 绝对路径白名单 / storage 回退读取），
  stream 与 stream-by_path 的本地模式回退 URL 统一到该路由。
- 缺陷5：merge 死参数（group_name_type/custom_group_name）对齐——前端已清理，
  服务端 tcConfig.groupName camelCase 双口径读取使补偿生效。
"""
import os
import tempfile
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles
from types import SimpleNamespace

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session
from api_gateway.infrastructure.request_adapter import set_current_request


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


_RUN = uuid.uuid4().hex[:8]


def _fake_request(json_body=None, query=None):
    """构造 request_adapter 所需的最小请求替身（含 method 属性）。"""
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


# ==================== 缺陷2：音频列表 algorithm_type 过滤 ====================

@pytest.fixture(scope='module')
def audio_db():
    """真实文件型 sqlite：audios + audio_algorithm_relations 两表。"""
    init_db(pool_size=3)
    remove_db_session()
    from shared.models.database import Base
    from audio_service.infrastructure.persistence.models import (
        Audio, AudioAlgorithmRelation,
    )
    engine = get_engine()
    Base.metadata.create_all(
        bind=engine,
        tables=[Audio.__table__, AudioAlgorithmRelation.__table__],
    )

    session = get_db_session()
    a_related = Audio(name=f'关联音频_{_RUN}', file_path='x/related.wav',
                      size=1, duration=1.0, format='wav', audio_type='dry')
    a_plain = Audio(name=f'无关联音频_{_RUN}', file_path='x/plain.wav',
                    size=1, duration=1.0, format='wav', audio_type='dry')
    session.add_all([a_related, a_plain])
    session.flush()
    session.add(AudioAlgorithmRelation(
        audio_id=a_related.id, algorithm_type='translation'))
    # 软删关联：不应参与匹配
    session.add(AudioAlgorithmRelation(
        audio_id=a_plain.id, algorithm_type='translation', deleted=True))
    session.commit()
    ids = {'related': a_related.id, 'plain': a_plain.id}
    session.close()
    yield ids
    remove_db_session()


class TestAudioListAlgorithmTypeFilter:
    """缺陷2：list_audios / get_all_audio_ids 的 algorithm_type 过滤。"""

    def test_list_filters_by_algorithm_relation(self, audio_db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        pagination = audio_repository.list_audios({
            'page': 1, 'per_page': 10, 'algorithm_type': 'translation'})
        got_ids = [a.id for a in pagination.items]
        assert audio_db['related'] in got_ids
        assert audio_db['plain'] not in got_ids, '无有效算法关联的音频不应命中'

    def test_list_without_filter_returns_all(self, audio_db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        pagination = audio_repository.list_audios({'page': 1, 'per_page': 10})
        got_ids = [a.id for a in pagination.items]
        assert audio_db['related'] in got_ids
        assert audio_db['plain'] in got_ids

    def test_get_all_audio_ids_filters_by_algorithm(self, audio_db):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        ids = audio_repository.get_all_audio_ids({'algorithm_type': 'translation'})
        assert audio_db['related'] in ids
        assert audio_db['plain'] not in ids

    def test_gateway_list_query_passthrough(self, monkeypatch):
        """网关查询模型接受并透传 algorithm_type（list 与 ids 两入口）。"""
        import api_gateway.application.services.audio.audio_query_service as svc_mod
        captured = {}

        class _StubAcl:
            def get_all(self, params):
                captured['list'] = params
                return {'success': True, 'data': {'items': [], 'total': 0,
                        'page': 1, 'per_page': 10, 'pages': 0, 'stats': {}}}

            def get_all_ids(self, params):
                captured['ids'] = params
                return {'success': True, 'data': {'ids': [], 'total': 0}}

        monkeypatch.setattr(svc_mod, '_audio_acl', _StubAcl())
        set_current_request(_fake_request(query={
            'page': '1', 'per_page': '10', 'algorithm_type': 'translation'}))
        try:
            svc_mod.AudioQueryService.get_all()
            svc_mod.AudioQueryService.get_all_ids()
        finally:
            set_current_request(None)

        assert captured['list']['algorithm_type'] == 'translation'
        assert captured['ids']['algorithm_type'] == 'translation'


# ==================== 缺陷3：分组列表筛选 ====================

@pytest.fixture(scope='module')
def testcase_db():
    """真实文件型 sqlite：test_case_groups + test_cases 两表。"""
    init_db(pool_size=3)
    remove_db_session()
    from shared.models.database import Base
    from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup
    engine = get_engine()
    Base.metadata.create_all(
        bind=engine, tables=[TestCaseGroup.__table__, TestCase.__table__])

    session = get_db_session()
    g1 = TestCaseGroup(id=f'g1_{_RUN}', name=f'登录组_{_RUN}', algorithm_type='translation')
    g2 = TestCaseGroup(id=f'g2_{_RUN}', name=f'空组_{_RUN}', algorithm_type='asr')
    session.add_all([g1, g2])
    session.flush()

    api_config = {'rounds': [{'round_number': 1,
                              'audios': [{'audio_id': 1, 'audio_name': 'a.wav'}]}]}
    e2e_config = {'rounds': [{'round_number': 1,
                              'audios': [{'audio_id': 1, 'audio_name': 'a.wav',
                                          'playback_device_id': 3}]}]}
    dim_config = {'dimensions': [{'id': 7, 'name': 'WER'}],
                  'rounds': [{'round_number': 1,
                              'audios': [{'audio_id': 2, 'audio_name': 'b.wav'}]}]}
    c1 = TestCase(id=f'c1_{_RUN}', name=f'登录功能用例_{_RUN}', description='登录',
                  config=api_config, group_id=g1.id, algorithm_type='translation')
    c2 = TestCase(id=f'c2_{_RUN}', name=f'播放用例_{_RUN}', description='E2E',
                  config=e2e_config, group_id=g1.id, algorithm_type='asr')
    c3 = TestCase(id=f'c3_{_RUN}', name=f'维度用例_{_RUN}', description='评估',
                  config=dim_config, group_id=g2.id, algorithm_type='translation')
    c4 = TestCase(id=f'c4_{_RUN}', name=f'已删用例_{_RUN}', description='gone',
                  config=api_config, group_id=g1.id, algorithm_type='translation',
                  deleted=True)
    session.add_all([c1, c2, c3, c4])
    session.commit()
    ids = {'g1': g1.id, 'g2': g2.id, 'c1': c1.id, 'c2': c2.id,
           'c3': c3.id, 'c4': c4.id}
    session.close()
    yield ids
    remove_db_session()


class TestTestCaseStatsFilters:
    """缺陷3：task_service 仓储统计的 keyword / test_type / dimension_id 过滤。"""

    def test_keyword_filters_by_name_and_description(self, testcase_db):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        assert repo.get_testcase_stats(keyword='登录功能')['total'] == 1
        # 描述命中
        assert repo.get_testcase_stats(keyword='评估')['total'] == 1

    def test_keyword_combined_with_group_by(self, testcase_db):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        items = repo.get_testcase_stats(keyword='用例', group_by='group_id')['items']
        counts = {i['key']: i['count'] for i in items}
        assert counts.get(testcase_db['g1']) == 2
        assert counts.get(testcase_db['g2']) == 1

    def test_dimension_id_filter(self, testcase_db):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        assert repo.get_testcase_stats(dimension_id=7)['total'] == 1

    def test_no_filter_grouped_not_regressed(self, testcase_db):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        items = repo.get_testcase_stats(group_by='group_id')['items']
        counts = {i['key']: i['count'] for i in items}
        assert counts.get(testcase_db['g1']) == 2
        assert counts.get(testcase_db['g2']) == 1

    def test_deleted_true_counts_trashed_only(self, testcase_db):
        """INT-528：deleted=True 统计回收站（软删除）用例，默认口径不受影响。"""
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        # 默认未删除口径：c4（已删）不计入
        assert repo.get_testcase_stats()['total'] == 3
        assert repo.get_testcase_stats(group_by='group_id')['items'] == [
            {'key': testcase_db['g1'], 'count': 2},
            {'key': testcase_db['g2'], 'count': 1},
        ]
        # 回收站口径：仅 c4
        assert repo.get_testcase_stats(deleted=True)['total'] == 1
        assert repo.get_testcase_stats(deleted=True, group_by='group_id')['items'] == [
            {'key': testcase_db['g1'], 'count': 1},
        ]

    def test_keyword_matches_trashed_case_in_recycle_scope(self, testcase_db):
        """INT-528：回收站态 keyword 可命中已删用例（分组列表空白根因）。"""
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()
        # 默认活跃口径：已删用例名不命中
        assert repo.get_testcase_stats(keyword='已删')['total'] == 0
        # 回收站口径：命中已删用例
        assert repo.get_testcase_stats(keyword='已删', deleted=True)['total'] == 1
        # 分组收敛口径：命中分组为 g1
        items = repo.get_testcase_stats(keyword='已删', deleted=True, group_by='group_id')['items']
        assert items == [{'key': testcase_db['g1'], 'count': 1}]


class TestGroupServiceFilters:
    """缺陷3：网关 GroupService.get_all 过滤转发与分组收敛。"""

    def _run(self, monkeypatch, query, stats_items):
        import api_gateway.application.services.group_service as group_mod
        captured = {}

        class _StubTds:
            def list_testcase_groups(self, algorithm_type=None, search=None,
                                     page=0, per_page=0):
                captured['list_kwargs'] = {'algorithm_type': algorithm_type,
                                           'page': page, 'per_page': per_page}
                # INT-1470 P1：test_case_count 随列表 RPC 一并返回
                return {'items': [
                    {'id': 'g1', 'name': '组1', 'algorithm_type': 'translation',
                     'test_case_count': 2},
                    {'id': 'g2', 'name': '组2', 'algorithm_type': 'asr',
                     'test_case_count': 0},
                ], 'total': 2}

            def get_testcase_stats(self, **kwargs):
                captured['stats_kwargs'] = kwargs
                return {'items': stats_items}

        import api_gateway.infrastructure.grpc_proxies as proxies_pkg
        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        set_current_request(_fake_request(query=query))
        try:
            payload, http_code = group_mod.GroupService.get_all()
        finally:
            set_current_request(None)
        return payload, http_code, captured

    def test_filters_forwarded_and_groups_converged(self, monkeypatch):
        payload, http_code, captured = self._run(
            monkeypatch,
            query={'keyword': '登录', 'dimension_id': '7'},
            stats_items=[{'key': 'g1', 'count': 2}])

        assert captured['stats_kwargs']['keyword'] == '登录'
        assert captured['stats_kwargs']['dimension_id'] == 7
        assert captured['stats_kwargs']['group_by'] == 'group_id'

        items = payload['data']['items']
        assert [i['id'] for i in items] == ['g1'], '无匹配用例的分组应被过滤'
        assert items[0]['test_case_count'] == 2
        assert payload['data']['total'] == 1

    def test_no_filter_keeps_all_groups(self, monkeypatch):
        payload, http_code, captured = self._run(
            monkeypatch, query={}, stats_items=[])
        # INT-1470 P1：默认口径不再发第二次聚合 RPC（GetTestCaseStats），
        # 计数由 ListTestCaseGroups 随列表带回；收藏/回收站口径仍下推统计。
        assert 'stats_kwargs' not in captured
        assert payload['data']['total'] == 2
        assert [i['test_case_count'] for i in payload['data']['items']] == [2, 0]

    def test_recycle_scope_forwarded_with_keyword(self, monkeypatch):
        """INT-528：回收站态 keyword 筛选下 favorite/deleted 随统计下推。"""
        payload, http_code, captured = self._run(
            monkeypatch,
            query={'keyword': '已删', 'only_deleted': 'true'},
            stats_items=[{'key': 'g1', 'count': 1}])

        assert captured['stats_kwargs']['keyword'] == '已删'
        assert captured['stats_kwargs']['group_by'] == 'group_id'
        assert captured['stats_kwargs']['favorite'] is False
        assert captured['stats_kwargs']['deleted'] is True
        assert [i['id'] for i in payload['data']['items']] == ['g1']

    def test_recycle_scope_forwarded_without_filters(self, monkeypatch):
        """INT-528：回收站态无关键字时分组计数也走已删口径。"""
        payload, http_code, captured = self._run(
            monkeypatch,
            query={'only_deleted': 'true'},
            stats_items=[{'key': 'g1', 'count': 1}])

        assert captured['stats_kwargs'] == {'group_by': 'group_id', 'favorite': False, 'deleted': True}
        assert payload['data']['total'] == 2

    def test_favorite_scope_forwarded(self, monkeypatch):
        """INT-528：收藏态筛选 favorite=True 随统计下推。"""
        payload, http_code, captured = self._run(
            monkeypatch,
            query={'favorite': 'true', 'keyword': '收藏'},
            stats_items=[{'key': 'g2', 'count': 1}])

        assert captured['stats_kwargs']['favorite'] is True
        assert captured['stats_kwargs']['deleted'] is False
        assert [i['id'] for i in payload['data']['items']] == ['g2']


# ==================== 缺陷4：本地存储回退下载路由 ====================

@pytest.fixture()
def audio_client(monkeypatch):
    """仅装配 audio 路由的 TestClient（request 注入 + admin 放行）。"""
    from api_gateway.routes.audio_bp import router as audio_router
    from api_gateway.middleware import RequestAdapterMiddleware
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.include_router(audio_router, prefix='/api/v1/audios')

    @app.middleware('http')
    async def _grant_admin_permissions(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    yield TestClient(app)


class TestGatewayAudioDownload:
    """缺陷4：GET /api/v1/audios/download（本地降级模式字节流回退）。"""

    def test_download_logical_key_via_storage(self, audio_client, monkeypatch):
        from shared.infrastructure.storage import storage
        captured = {}

        def _fake_load_bytes(path):
            captured['path'] = path
            return b'RIFFxxxx'

        monkeypatch.setattr(storage, 'load_bytes', _fake_load_bytes)
        resp = audio_client.get('/api/v1/audios/download', params={'path': 'demo.wav'})
        assert resp.status_code == 200, resp.text
        assert resp.content == b'RIFFxxxx'
        assert resp.headers['content-type'].startswith('audio/wav')
        # 裸 key 归一到 audios 分类（与 stream 口径一致）
        assert captured['path'] == 'oss://audios/demo.wav'

    def test_download_rejects_unsupported_ext(self, audio_client, monkeypatch):
        resp = audio_client.get('/api/v1/audios/download', params={'path': 'evil.exe'})
        assert resp.status_code == 403

    def test_download_rejects_path_traversal(self, audio_client, monkeypatch):
        resp = audio_client.get(
            '/api/v1/audios/download', params={'path': 'a/../secret.wav'})
        assert resp.status_code == 403

    def test_download_missing_path_400(self, audio_client):
        resp = audio_client.get('/api/v1/audios/download')
        assert resp.status_code == 400

    def test_download_not_found_404(self, audio_client, monkeypatch):
        from shared.infrastructure.storage import storage

        def _raise_not_found(path):
            raise FileNotFoundError(path)

        monkeypatch.setattr(storage, 'load_bytes', _raise_not_found)
        resp = audio_client.get('/api/v1/audios/download', params={'path': 'gone.wav'})
        assert resp.status_code == 404

    def test_download_absolute_path_inside_audio_storage(self, audio_client, monkeypatch):
        import api_gateway.config.config as gw_config
        base = tempfile.mkdtemp(prefix='int146_audio_dl_')
        monkeypatch.setattr(gw_config.Config, 'AUDIO_STORAGE_PATH', base)
        abs_file = os.path.join(base, 'local.wav')
        with open(abs_file, 'wb') as f:
            f.write(b'RIFFlocal')

        resp = audio_client.get('/api/v1/audios/download', params={'path': abs_file})
        assert resp.status_code == 200, resp.text
        assert resp.content == b'RIFFlocal'

    def test_download_absolute_path_outside_rejected(self, audio_client, monkeypatch):
        import api_gateway.config.config as gw_config
        monkeypatch.setattr(gw_config.Config, 'AUDIO_STORAGE_PATH',
                            tempfile.mkdtemp(prefix='int146_allowed_'))
        outside = os.path.join(
            tempfile.mkdtemp(prefix='int146_outside_'), 'other.wav')
        with open(outside, 'wb') as f:
            f.write(b'RIFFoutside')

        resp = audio_client.get('/api/v1/audios/download', params={'path': outside})
        assert resp.status_code == 403


class TestStreamFallbackUrl:
    """缺陷4：本地模式 stream / stream-by-path 的回退地址指向网关下载路由。"""

    def _make_handler(self, audio):
        from audio_service.application.handlers.audio_query_handler import AudioQueryHandler

        class _StubRepo:
            def get_audio_with_deleted(self, audio_id):
                return audio

        return AudioQueryHandler(repository=_StubRepo())

    def test_stream_audio_fallback_url(self, monkeypatch):
        from shared.infrastructure.storage import storage
        from audio_service.application.queries import StreamAudioQuery

        audio = SimpleNamespace(
            id=1, deleted=False, file_path='local://audios/x.wav')
        monkeypatch.setattr(storage, 'get_url', lambda path, expires=3600: None)

        handler = self._make_handler(audio)
        result = handler.handle_stream_audio(StreamAudioQuery(audio_id=1))
        assert result['success'] is True
        assert result['data']['url'] == (
            f'/api/v1/audios/download?path=local://audios/x.wav')

    def test_stream_audio_presigned_url_unchanged(self, monkeypatch):
        from shared.infrastructure.storage import storage
        from audio_service.application.queries import StreamAudioQuery

        audio = SimpleNamespace(
            id=1, deleted=False, file_path='oss://audios/x.wav')
        monkeypatch.setattr(
            storage, 'get_url',
            lambda path, expires=3600: f'https://oss/{path}?sig=1')

        handler = self._make_handler(audio)
        result = handler.handle_stream_audio(StreamAudioQuery(audio_id=1))
        assert result['data']['url'] == 'https://oss/oss://audios/x.wav?sig=1'

    def test_stream_by_path_local_fallback_url(self, monkeypatch):
        from shared.infrastructure.storage import storage
        from audio_service.application.queries import StreamAudioByPathQuery

        monkeypatch.setattr(storage, 'get_url', lambda path, expires=3600: None)

        from audio_service.application.handlers.audio_query_handler import AudioQueryHandler
        handler = AudioQueryHandler(repository=_NoopRepo())
        result = handler.handle_stream_audio_by_path(
            StreamAudioByPathQuery(data={'path': 'local://audios/tree.wav'}))
        assert result['success'] is True
        assert result['data']['url'] == (
            f'/api/v1/audios/download?path=local://audios/tree.wav')


class _NoopRepo:
    """stream_by_path 不触库，占位仓储。"""


# ==================== 缺陷5：merge 分组命名口径对齐 ====================

class TestExtractMergeParamsGroupName:
    """缺陷5：tcConfig.groupName camelCase 双口径读取 + 死参数不消费。"""

    def _svc(self):
        from audio_service.application.services.audio_upload.round_config_service import (
            AudioRoundConfigService,
        )
        return AudioRoundConfigService()

    def test_camel_case_group_name_from_tc_config(self):
        params = self._svc().extract_merge_params({
            'test_case_config': {'rounds': [], 'groupName': '自定义组'},
        })
        assert params['test_case_group_name'] == '自定义组'

    def test_snake_case_group_name_from_tc_config(self):
        params = self._svc().extract_merge_params({
            'test_case_config': {'rounds': [], 'group_name': '自定义组'},
        })
        assert params['test_case_group_name'] == '自定义组'

    def test_top_level_camel_case_fallback(self):
        params = self._svc().extract_merge_params({'testCaseGroupName': '顶层组'})
        assert params['test_case_group_name'] == '顶层组'

    def test_dead_merge_params_not_consumed(self):
        """group_name_type/custom_group_name 已死：不参与分组名解析、不报错。"""
        params = self._svc().extract_merge_params({
            'group_name_type': 'custom',
            'custom_group_name': '死参数组',
            'test_case_config': {'rounds': [], 'groupName': '有效组'},
        })
        assert params['test_case_group_name'] == '有效组'

        params_none = self._svc().extract_merge_params({
            'group_name_type': 'custom',
            'custom_group_name': '死参数组',
        })
        assert params_none['test_case_group_name'] is None
