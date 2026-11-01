# -*- coding: utf-8 -*-
"""INT-2313：用例导出批量取数（B 卡）。

验收口径（卡面「可测验收标准·单测」）：
1. 批量替逐条：网关导出改调 `TestCaseConfigService.GetTestCasesByIds`，不再
   逐条 `GetTestCaseDetail`；
2. 分片：199/200/201 → 1/1/2 片；单片失败只影响该片（失败条进 missing）；
3. 可见性：task_service 批量详情套 `visible_condition` —— 私有非 owner 进
   `missing_ids`（不得被导出），admin 全量返回；
4. 窄字段音频：一片用例的音频一次批量投影取回，并按 `GetAudio` 同义逐行过滤；
5. 设备映射预载：一次 `get_all`，不再逐条 `get_one`；
6. 维度只取一次：xlsx/csv 扁平化不再逐用例重复查；
7. 批量与单条详情逐字段一致。

网关侧用替身隔离 gRPC；task_service 侧用进程级 SQLite 落真实可见性 SQL。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.testcase import testcase_export_service as module
from api_gateway.application.services.testcase.testcase_export_service import (
    MISSING_REASON_RPC_ERROR,
    TESTCASE_DETAIL_SHARD_SIZE,
    ExportSpec,
    TestCaseExportService,
)
from api_gateway.domain.dto import CommandResultDTO
from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)

OWNER_ID = 100
OTHER_ID = 200


# ----------------------------------------------------------------------
# 替身：网关侧 gRPC ACL
# ----------------------------------------------------------------------
def _case_row(case_id, config=None, audios=None):
    return {
        'id': case_id,
        'name': f'用例{case_id}',
        'description': None,
        'group_id': None,
        'group_name': None,
        'tags': [],
        'config': config or {},
        'algorithm_params': None,
        'reference_params': None,
        'algorithm_type': None,
        'strategy_id': None,
        'strategy_overrides': None,
        'audios': audios or [],
        'dimensions': [],
        'created_at': None,
        'updated_at': None,
    }


class _FakeTestCaseAcl:
    """记录分片入参；逐条详情一律视为违规调用。"""

    def __init__(self, cases=None, fail_shards=()):
        self.cases = cases or {}
        self.chunks = []
        self.detail_calls = 0
        self.fail_shards = set(fail_shards)

    def get_testcases_by_ids(self, ids, include_deleted=False):
        index = len(self.chunks)
        self.chunks.append(list(ids))
        if index in self.fail_shards:
            raise RuntimeError('task gRPC down')
        found = [self.cases[i] for i in ids if i in self.cases]
        missing = [i for i in ids if i not in self.cases]
        return CommandResultDTO(
            success=True, data={'test_cases': found, 'missing_ids': missing})

    def get_testcase_detail(self, tc_id):
        self.detail_calls += 1
        raise AssertionError('批量路径不得再逐条取详情')


class _FakePlaybackAcl:
    def __init__(self, devices=None):
        self.devices = devices or {}
        self.get_all_calls = []
        self.get_one_calls = []

    def get_all(self, **kwargs):
        self.get_all_calls.append(kwargs)
        items = [
            {'id': device_id, 'name': name}
            for device_id, name in self.devices.items()
        ]
        return CommandResultDTO(
            success=True,
            data={'items': items, 'total': len(items), 'page': 1,
                  'per_page': 500, 'pages': 1})

    def get_one(self, device_id):
        self.get_one_calls.append(device_id)
        name = self.devices.get(device_id)
        return CommandResultDTO(success=bool(name),
                                data={'id': device_id, 'name': name} if name else None)


class _FakeAudioAcl:
    def __init__(self):
        self.get_one_calls = []
        self.get_by_ids_calls = []

    def get_one(self, audio_id):
        self.get_one_calls.append(audio_id)
        return CommandResultDTO(success=False, data=None)

    def get_by_ids(self, payload):
        self.get_by_ids_calls.append(list(payload.get('ids') or []))
        return CommandResultDTO(success=True, data=[])


class _FakeDimensionAcl:
    def __init__(self, dims=None):
        self.dims = dims or {}
        self.calls = []

    def get_dimension_by_ids(self, dim_ids):
        self.calls.append(list(dim_ids))
        return CommandResultDTO(success=True, data={
            str(d): self.dims[d] for d in dim_ids if d in self.dims})


@pytest.fixture
def gateway(monkeypatch):
    tc_acl = _FakeTestCaseAcl()
    playback_acl = _FakePlaybackAcl()
    audio_acl = _FakeAudioAcl()
    dim_acl = _FakeDimensionAcl()
    monkeypatch.setattr(module, '_testcase_acl', tc_acl)
    monkeypatch.setattr(module, '_playback_acl', playback_acl)
    monkeypatch.setattr(module, '_audio_acl', audio_acl)
    monkeypatch.setattr(module, '_evaluation_acl', dim_acl)
    monkeypatch.setattr(module, '_tag_acl', _FakeAudioAcl())
    return tc_acl, playback_acl, audio_acl, dim_acl


def _spec(ids, **kwargs):
    return ExportSpec(ids=[str(i) for i in ids],
                      format=kwargs.pop('format', 'json'), **kwargs)


# ----------------------------------------------------------------------
# 1. 批量替逐条 + 音频名来自详情
# ----------------------------------------------------------------------
def test_export_uses_batch_rpc_and_detail_audio_names(gateway):
    tc_acl, playback_acl, audio_acl, _ = gateway
    config = {'rounds': [{'round_number': 1, 'audios': [
        {'audio_id': 7, 'spl': 65, 'playback_device_id': 3, 'play_order': 1}]}]}
    tc_acl.cases['c1'] = _case_row(
        'c1', config=config,
        audios=[{'audio_id': 7, 'audio_name': '音频七'}])

    export_data, missing = TestCaseExportService._fetch_export_data(_spec(['c1']))

    assert missing == []
    assert tc_acl.detail_calls == 0, '不得再逐条 GetTestCaseDetail'
    assert tc_acl.chunks == [['c1']]
    assert export_data[0]['audios'][0]['audio_name'] == '音频七'
    assert audio_acl.get_one_calls == [], '音频名必须取详情已返回的值'
    assert playback_acl.get_all_calls, '播放设备名必须走一次 get_all 预载'
    assert playback_acl.get_one_calls == []


# ----------------------------------------------------------------------
# 2. 分片边界：199 / 200 / 201
# ----------------------------------------------------------------------
@pytest.mark.parametrize('count,expected_chunks', [(199, 1), (200, 1), (201, 2)])
def test_shard_boundaries(gateway, count, expected_chunks):
    tc_acl, *_ = gateway
    ids = [f'c{i}' for i in range(count)]
    for case_id in ids:
        tc_acl.cases[case_id] = _case_row(case_id)

    export_data, missing = TestCaseExportService._fetch_export_data(_spec(ids))

    assert len(export_data) == count and missing == []
    assert len(tc_acl.chunks) == expected_chunks
    assert all(len(chunk) <= TESTCASE_DETAIL_SHARD_SIZE for chunk in tc_acl.chunks)


# ----------------------------------------------------------------------
# 3. 单片失败只影响该片
# ----------------------------------------------------------------------
def test_shard_failure_isolated(gateway):
    tc_acl, *_ = gateway
    tc_acl.fail_shards = {1}
    ids = [f'c{i}' for i in range(201)]
    for case_id in ids[:200]:
        tc_acl.cases[case_id] = _case_row(case_id)

    export_data, missing = TestCaseExportService._fetch_export_data(_spec(ids))

    assert len(tc_acl.chunks) == 2
    assert len(export_data) == 200
    assert missing == [{'id': 'c200', 'reason': MISSING_REASON_RPC_ERROR}]


def test_not_found_ids_go_to_missing(gateway):
    tc_acl, *_ = gateway
    tc_acl.cases['a'] = _case_row('a')

    export_data, missing = TestCaseExportService._fetch_export_data(_spec(['a', 'ghost']))

    assert [row['id'] for row in export_data] == ['a']
    assert missing == [{'id': 'ghost', 'reason': 'not_found'}]


# ----------------------------------------------------------------------
# 4. 设备映射预载
# ----------------------------------------------------------------------
def test_device_names_preloaded_once_for_export(gateway):
    tc_acl, playback_acl, _, _ = gateway
    playback_acl.devices = {3: '音箱A', 4: '音箱B'}
    for index in range(3):
        case_id = f'c{index}'
        tc_acl.cases[case_id] = _case_row(case_id, config={'rounds': [{
            'round_number': 1,
            'audios': [{'audio_id': 1, 'spl': 60,
                        'playback_device_id': 3 + index % 2, 'play_order': 1}],
        }]})

    export_data, _ = TestCaseExportService._fetch_export_data(
        _spec([f'c{i}' for i in range(3)]))

    assert [row['playback_devices'] for row in export_data] == [
        ['音箱A'], ['音箱B'], ['音箱A']]
    assert len(playback_acl.get_all_calls) == 1, '一次导出只预载一次'
    assert playback_acl.get_one_calls == []


def test_device_preload_failure_falls_back_to_get_one(gateway):
    tc_acl, playback_acl, _, _ = gateway
    playback_acl.devices = {3: '音箱A'}
    playback_acl.get_all = lambda **kwargs: CommandResultDTO(
        success=False, message='device down', data=None)
    tc_acl.cases['c1'] = _case_row('c1', config={'rounds': [{
        'round_number': 1,
        'audios': [{'audio_id': 1, 'spl': 60, 'playback_device_id': 3,
                    'play_order': 1}],
    }]})

    export_data, _ = TestCaseExportService._fetch_export_data(_spec(['c1']))

    assert export_data[0]['playback_devices'] == ['音箱A']
    assert playback_acl.get_one_calls == [3]


# ----------------------------------------------------------------------
# 5. 维度只取一次
# ----------------------------------------------------------------------
def test_dimensions_fetched_once_when_flattening(gateway):
    _, _, _, dim_acl = gateway
    dim_acl.dims = {11: {'id': 11, 'name': '字准', 'weight': 100},
                    12: {'id': 12, 'name': '句准', 'weight': 50}}
    rows = [
        {'id': f'c{i}', 'name': f'用例{i}', 'description': None, 'group': None,
         'group_id': None, 'tags': [], 'audios': [], 'dimension_ids': [11, 12],
         'tag_items': [], 'config': {}, 'reference_params': None,
         'noise_name': '无', 'noise_spl': '', 'noise_audio_id': None}
        for i in range(5)
    ]

    _, _, dimensions_data_list, _, _ = \
        TestCaseExportService._flatten_all_export_data(rows)

    assert len(dimensions_data_list) == 10
    assert len(dim_acl.calls) == 1, '整份导出只查一次维度'
    assert set(dim_acl.calls[0]) == {11, 12}


def test_build_case_row_reuses_preloaded_dimension_map(gateway):
    _, _, _, dim_acl = gateway
    dim_acl.dims = {11: {'id': 11, 'name': '字准'}}

    row = TestCaseExportService._build_case_row(
        _case_row('c1', config={'dimensions': [{'id': 11, 'weight': 100}]}),
        dim_map={'11': {'id': 11, 'name': '字准'}},
        device_map={})

    assert row['dimensions'] == ['字准']
    assert dim_acl.calls == [], '预载后不得再逐用例查维度'


# ----------------------------------------------------------------------
# 6. 音频包取数分片（不整包塞）
# ----------------------------------------------------------------------
def test_audio_package_fetch_is_chunked(gateway):
    _, _, audio_acl, _ = gateway
    audio_ids = list(range(1, 202))

    TestCaseExportService._fetch_audio_record_map(audio_ids)

    assert [len(chunk) for chunk in audio_acl.get_by_ids_calls] in ([200, 1], [1, 200])
    assert sorted(sum(audio_acl.get_by_ids_calls, [])) == audio_ids


# ======================================================================
# task_service 侧：批量详情（可见性 + 与单条同构）
# ======================================================================
class _FakeGroup:
    def __init__(self, group_id, name):
        self.id = group_id
        self.name = name


class _FakeTag:
    def __init__(self, name):
        self.name = name


class _FakeTc:
    def __init__(self, tc_id, config=None, visibility='shared', owner=OWNER_ID,
                 tags=(), group=None):
        self.id = tc_id
        self.name = f'用例{tc_id}'
        self.description = None
        self.config = config or {}
        self.group = group
        self.group_id = group.id if group else None
        self.tags = list(tags)
        self.algorithm_params = None
        self.reference_params = None
        self.algorithm_type = None
        self.strategy_id = None
        self.strategy_overrides = None
        self.visibility = visibility
        self.created_by_user_id = owner
        self.created_at = None
        self.updated_at = None


class _FakeQueryRepo:
    def __init__(self, tcs, audio_records=None, dims=None):
        self.tcs = {tc.id: tc for tc in tcs}
        self.audio_records = audio_records or {}
        self.dims = dims or {}
        self.detail_audio_calls = []
        self.summary_calls = []

    def get_testcase(self, tc_id):
        return self.tcs.get(tc_id)

    def list_testcases_by_ids_visible(self, ids, include_deleted=False):
        return [self.tcs[i] for i in ids if i in self.tcs]

    def get_audio_by_id(self, audio_id):
        self.detail_audio_calls.append(audio_id)
        return self.audio_records.get(int(audio_id))

    def list_audio_summaries_by_ids(self, audio_ids):
        self.summary_calls.append(sorted(audio_ids))
        return {int(i): self.audio_records[int(i)]
                for i in audio_ids if int(i) in self.audio_records}

    def list_dimensions_by_ids(self, dim_ids):
        return [self.dims[d] for d in dim_ids if d in self.dims]


def _query_service(repo):
    from task_service.application.testcase.testcase_query_service import (
        TestCaseQueryService,
    )
    return TestCaseQueryService(repo)


def _audio_record(audio_id, name, duration=2.0, owner=OWNER_ID, visibility='shared'):
    return {'id': audio_id, 'name': name, 'duration': duration,
            'visibility': visibility, 'created_by_user_id': owner}


@pytest.fixture(autouse=True)
def _reset_identity():
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def test_batch_detail_matches_single_detail():
    config = {
        'rounds': [{'round_number': 1, 'audios': [
            {'audio_id': 7, 'spl': 65, 'playback_device_id': 3, 'play_order': 1},
            {'audio_id': 7, 'spl': 70, 'playback_device_id': 3, 'play_order': 2}]}],
        'dimensions': [{'id': 11, 'weight': 100}],
    }
    tc = _FakeTc('c1', config=config, tags=[_FakeTag('标签A')],
                 group=_FakeGroup('g1', '分组一'))
    repo = _FakeQueryRepo(
        [tc],
        audio_records={7: _audio_record(7, '音频七')},
        dims={11: {'id': 11, 'name': '字准', 'type': 'accuracy'}},
    )
    set_current_user_id(OWNER_ID)

    single = _query_service(repo).get_testcase_detail('c1')
    batch = _query_service(repo).get_testcase_details_by_ids(['c1'])

    assert single['success'] and batch['success']
    assert batch['data']['missing_ids'] == []
    assert batch['data']['test_cases'] == [single['data']], '批量与单条必须逐字段一致'
    # 同一音频取两次的旧问题：单条路径现在也只取一次
    assert repo.detail_audio_calls == [7]


def test_batch_missing_ids_keep_request_order():
    tc = _FakeTc('c1')
    repo = _FakeQueryRepo([tc])
    set_current_user_id(OWNER_ID)

    result = _query_service(repo).get_testcase_details_by_ids(['ghost', 'c1', 'ghost2'])

    assert result['data']['missing_ids'] == ['ghost', 'ghost2']
    assert [item['id'] for item in result['data']['test_cases']] == ['c1']


def test_private_audio_name_hidden_for_non_owner():
    config = {'rounds': [{'round_number': 1, 'audios': [
        {'audio_id': 7, 'spl': 65, 'play_order': 1}]}]}
    repo = _FakeQueryRepo(
        [_FakeTc('c1', config=config)],
        audio_records={7: _audio_record(
            7, '私有音频', owner=OWNER_ID, visibility='private')},
    )

    set_current_user_id(OTHER_ID)
    other = _query_service(repo).get_testcase_details_by_ids(['c1'])
    assert other['data']['test_cases'][0]['audios'][0]['audio_name'] is None

    set_current_user_id(OWNER_ID)
    owner = _query_service(repo).get_testcase_details_by_ids(['c1'])
    assert owner['data']['test_cases'][0]['audios'][0]['audio_name'] == '私有音频'

    set_current_user_id(OTHER_ID)
    set_current_user_is_admin(True)
    admin = _query_service(repo).get_testcase_details_by_ids(['c1'])
    assert admin['data']['test_cases'][0]['audios'][0]['audio_name'] == '私有音频'


def test_narrow_audio_projection_uses_shared_db_read(monkeypatch):
    """窄字段批量投影：一次 IN 查询，只取白名单列，失败降级为空。"""
    from task_service.infrastructure.acl import audio_acl_repository as acl_module
    from task_service.infrastructure.acl import _read_projection

    captured = {}

    def _fake_fetch_rows(session, sql, ids, ids_name='ids', extra_params=None):
        captured['sql'] = sql
        captured['ids'] = list(ids)
        return [(7, '音频七', 2.5, 'wav', 'oss://a/7.wav', 'shared', OWNER_ID)]

    monkeypatch.setattr(_read_projection, 'fetch_rows', _fake_fetch_rows)
    # 隔离 DB 绑定：本用例只验证投影 SQL 与字段映射，不建表/不取真实会话
    import shared.models.database as database_module
    monkeypatch.setattr(database_module, 'get_db_session', lambda: None)

    records = acl_module.AudioAclRepository().list_audio_summaries_by_ids([7, '7', None])

    assert set(captured['ids']) == {7}
    assert 'FROM audios' in captured['sql'] and 'deleted = FALSE' in captured['sql']
    assert records[7]['name'] == '音频七' and records[7]['duration'] == 2.5


# ======================================================================
# 7. 可见性：真实 SQL（SQLite）批量详情不得越权
# ======================================================================
@pytest.fixture
def sqlite_repo():
    from shared.models.database import Base, get_db_session, get_engine, init_db
    from task_service.infrastructure.persistence.models import (
        Tag,
        TestCase,
        TestCaseGroup,
        TestCaseTag,
    )
    from task_service.infrastructure.persistence.testcase_repository import (
        TestCaseRepository,
    )

    init_db(pool_size=2)
    tables = [TestCaseGroup.__table__, TestCase.__table__,
              Tag.__table__, TestCaseTag.__table__]
    Base.metadata.create_all(bind=get_engine(), tables=tables)

    session = get_db_session()
    try:
        for table in reversed(tables):
            session.execute(table.delete())
        session.commit()
        yield session, TestCaseRepository()
    finally:
        session.rollback()
        session.close()


def _insert_case(session, tc_id, visibility, owner, deleted=False):
    from task_service.infrastructure.persistence.models import TestCase
    session.add(TestCase(
        id=tc_id, name=f'用例{tc_id}', config={}, visibility=visibility,
        created_by_user_id=owner, deleted=deleted,
    ))
    session.commit()


def _ids(result):
    return sorted(tc.id for tc in result)


def test_batch_repo_filters_private_non_owner(sqlite_repo):
    session, repo = sqlite_repo
    _insert_case(session, 'shared-1', 'shared', OWNER_ID)
    _insert_case(session, 'private-owner', 'private', OWNER_ID)
    _insert_case(session, 'private-other', 'private', OTHER_ID)

    set_current_user_id(OWNER_ID)
    visible = repo.list_testcases_by_ids_visible(
        ['shared-1', 'private-owner', 'private-other'])
    assert _ids(visible) == ['private-owner', 'shared-1'], '私有非 owner 不得放行'

    set_current_user_is_admin(True)
    assert _ids(repo.list_testcases_by_ids_visible(
        ['shared-1', 'private-owner', 'private-other'])) == [
            'private-other', 'private-owner', 'shared-1']


def test_batch_detail_private_case_goes_to_missing(sqlite_repo):
    session, repo = sqlite_repo
    _insert_case(session, 'shared-1', 'shared', OWNER_ID)
    _insert_case(session, 'private-other', 'private', OTHER_ID)
    service = _query_service(repo)

    set_current_user_id(OWNER_ID)
    result = service.get_testcase_details_by_ids(['shared-1', 'private-other'])

    assert [item['id'] for item in result['data']['test_cases']] == ['shared-1']
    assert result['data']['missing_ids'] == ['private-other'], '私有用例不得被导出'

    set_current_user_is_admin(True)
    admin = service.get_testcase_details_by_ids(['shared-1', 'private-other'])
    assert sorted(item['id'] for item in admin['data']['test_cases']) == [
        'private-other', 'shared-1']
    assert admin['data']['missing_ids'] == []


def test_crud_facade_delegates_batch_detail(monkeypatch):
    """servicer 路径经 TestCaseCrudService 门面委托（漏了它整条批量 RPC 恒失败）。"""
    from task_service.application.testcase.testcase_crud_service import (
        testcase_crud_service,
    )

    seen = {}

    class _QueryStub:
        def get_testcase_details_by_ids(self, ids, include_deleted=False):
            seen['call'] = (list(ids), include_deleted)
            return {'success': True, 'message': '', 'data': {'test_cases': [], 'missing_ids': []}}

    monkeypatch.setattr(testcase_crud_service, '_query_service', _QueryStub())

    result = testcase_crud_service.get_testcase_details_by_ids(
        ['a'], include_deleted=True)

    assert result['success'] is True
    assert seen['call'] == (['a'], True)
