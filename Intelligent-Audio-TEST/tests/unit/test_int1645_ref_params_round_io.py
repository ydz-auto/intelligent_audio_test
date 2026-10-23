# -*- coding: utf-8 -*-
"""INT-1645 用例参考参数读写端点单测（隔离存储，不连 DB / OSS / gRPC）。

覆盖卡面 §八.1 验收清单：
- 路径只在 reference_params 列（snake_case round_number）→ 200 有内容；
- 路径只在 config.rounds（camelCase roundNumber + path）→ 200 兜底成功；
- 未登记轮次 → 404「未找到第 N 轮」；有轮无路径 → 404「未生成」；
- 有路径但对象不存在 → 404 且不是 200 空数组；内容为空数组 → 200 []；
- PUT 缺字段/非数组 → 400；PUT 后 GET 一致；无路径轮 PUT 后列内出现规范
  路径且其它轮不变、config.rounds 不被回写；
- 路径归一化（历史 Windows 绝对路径 → oss://ref_params/<case_id>/round_N.json）。
"""
import json
import os
from types import SimpleNamespace

import pytest

# BaseConfig 在首次导入即校验 OSS 凭据（类属性冻结），先伪造再导入
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig  # noqa: E402
from shared.infrastructure.storage import Storage  # noqa: E402
from task_service.application.testcase.testcase_crud_service import (  # noqa: E402
    TestCaseCrudService as CrudService,
)
from task_service.application.testcase.testcase_query_service import (  # noqa: E402
    TestCaseQueryService as QueryService,
)
from task_service.infrastructure.oss.ref_params_store import (  # noqa: E402
    build_ref_params_path,
    normalize_ref_params_path,
    to_round_number,
    upsert_round_ref_path,
)

CASE_ID = 'd2b8a465-9f48-46f6-9624-7702e9ae2145'
LEGACY_PATH = r'D:\00_static\static\ref_params\{}\round_1.json'.format(CASE_ID)
REF_PARAMS = [
    {'code': 'ref_text', 'value': 'hello'},
    {'code': 'ref_energy', 'value': '1.0'},
]


class _NoOssClient:
    """OSS 不可用替身：读写一律失败，逼出本地降级路径。"""

    def is_available(self):
        return False

    def upload_bytes(self, *args, **kwargs):
        raise RuntimeError('OSS 不可用（单测替身）')

    def download_bytes(self, *args, **kwargs):
        raise FileNotFoundError('OSS 不可用（单测替身）')


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """隔离存储：OSS 不可用 + 本地降级根目录指向临时目录。"""
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))
    monkeypatch.setattr(Storage, '_oss',
                        property(lambda self: _NoOssClient()))
    # 单例缓存复位，避免污染其它用例
    instance = Storage()
    monkeypatch.setattr(instance, '_oss_checked', False)
    monkeypatch.setattr(instance, '_oss_ok', False, raising=False)
    yield


class _FakeRepo:
    def __init__(self, testcase):
        self._testcase = testcase
        self.committed = 0

    def get_testcase(self, tc_id):
        if self._testcase is not None and self._testcase.id == tc_id:
            return self._testcase
        return None

    def commit(self):
        self.committed += 1


def _make_case(config=None, ref_params=None):
    return SimpleNamespace(
        id=CASE_ID,
        name='接线测试_参考参数',
        config=config if config is not None else {'rounds': []},
        reference_params=ref_params,
        created_by_user_id=None,
        visibility='shared',
    )


def _query_service(testcase):
    return QueryService(repo=_FakeRepo(testcase))


def _crud_service(testcase, monkeypatch):
    repo = _FakeRepo(testcase)
    service = CrudService()
    service.repo = repo
    service._query_service.repo = repo

    from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
    monkeypatch.setattr(AlgorithmRepository, 'algo_get_all_reference_params',
                        lambda self, params=None: list(params or []))
    return service, repo


def _put_object(key, payload):
    """把对象写进本地降级根（等价 upload 后的 oss 对象，读取时走本地兜底）。"""
    from shared.infrastructure.storage import storage
    return storage.save_bytes(
        json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        'ref_params', key, content_type='application/json')


# ==================== 路径归一化 ====================


@pytest.mark.parametrize('raw, expected', [
    (r'D:\00_static\static\ref_params\abc\round_1.json',
     'oss://ref_params/abc/round_1.json'),
    ('D:/00_static/static/ref_params/abc/round_1.json',
     'oss://ref_params/abc/round_1.json'),
    (r'D:\00_static\static\ref_params\{}\round_1.json'.format(CASE_ID),
     'oss://ref_params/{}/round_1.json'.format(CASE_ID)),
    ('ref_params/abc/round_1.json', 'oss://ref_params/abc/round_1.json'),
    ('abc/round_1.json', 'oss://ref_params/abc/round_1.json'),
    ('oss://ref_params/abc/round_1.json', 'oss://ref_params/abc/round_1.json'),
    ('local://ref_params/abc/round_1.json', 'local://ref_params/abc/round_1.json'),
    ('/var/data/ref.json', '/var/data/ref.json'),
    ('', ''),
    (None, ''),
])
def test_normalize_ref_params_path(raw, expected):
    assert normalize_ref_params_path(raw) == expected


def test_build_ref_params_path_is_canonical():
    assert build_ref_params_path(CASE_ID, 2) == \
        f'oss://ref_params/{CASE_ID}/round_2.json'


@pytest.mark.parametrize('raw, expected', [
    (1, 1), ('1', 1), (' 2 ', 2), ('3.0', 3), (None, None), ('', None),
    ('abc', None), (True, None),
])
def test_to_round_number(raw, expected):
    assert to_round_number(raw) == expected


def test_upsert_round_ref_path_keeps_other_rounds_sorted():
    entries = [
        {'round_number': 3, 'reference_params_path': 'oss://ref_params/c/round_3.json'},
        {'round_number': 1, 'reference_params_path': r'D:\legacy\ref_params\c\round_1.json'},
        {'round_number': 1, 'reference_params_path': 'duplicate'},
    ]
    result = upsert_round_ref_path(entries, 1, 'oss://ref_params/c/round_1.json')
    assert [item['round_number'] for item in result] == [1, 3]
    assert result[0]['reference_params_path'] == 'oss://ref_params/c/round_1.json'
    assert result[1]['reference_params_path'] == 'oss://ref_params/c/round_3.json'


# ==================== GET ====================


def test_get_from_reference_params_column_snake_case():
    _put_object(f'{CASE_ID}/round_1.json', REF_PARAMS)
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}]},  # config 无路径，只有轮次
        ref_params=[{'round_number': 1, 'reference_params_path': LEGACY_PATH}],
    )

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 1)

    assert result['success'] is True
    assert result['data']['roundNumber'] == 1
    assert result['data']['referenceParamsPath'] == \
        f'oss://ref_params/{CASE_ID}/round_1.json'
    assert result['data']['referenceParams'] == REF_PARAMS


def test_get_falls_back_to_config_rounds_camel_case():
    _put_object(f'{CASE_ID}/round_2.json', REF_PARAMS)
    testcase = _make_case(
        config={'rounds': [{
            'roundNumber': 2,
            'referenceParamsPath': f'oss://ref_params/{CASE_ID}/round_2.json',
        }]},
        ref_params=[],
    )

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, '2')

    assert result['success'] is True
    assert result['data']['roundNumber'] == 2
    assert result['data']['referenceParams'] == REF_PARAMS


def test_get_unknown_round_returns_404():
    testcase = _make_case(config={'rounds': [{'round_number': 1}]}, ref_params=[])

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 2)

    assert result['success'] is False
    assert result['code'] == 404
    assert result['message'] == '未找到第 2 轮'


def test_get_round_without_path_returns_not_generated():
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}]},
        ref_params=[{'round_number': 1, 'reference_params_path': None}],
    )

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 1)

    assert result['success'] is False
    assert result['code'] == 404
    assert '未生成参考参数' in result['message']


def test_get_missing_object_returns_404_not_empty_list():
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}]},
        ref_params=[{'round_number': 1, 'reference_params_path': LEGACY_PATH}],
    )

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 1)

    assert result['success'] is False
    assert result['code'] == 404
    assert '读取失败' in result['message']
    assert LEGACY_PATH in result['message']
    assert result['data'] is None


def test_get_empty_array_object_returns_200():
    _put_object(f'{CASE_ID}/round_3.json', [])
    testcase = _make_case(
        config={'rounds': [{'round_number': 3}]},
        ref_params=[{'round_number': 3,
                     'reference_params_path': f'oss://ref_params/{CASE_ID}/round_3.json'}],
    )

    result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 3)

    assert result['success'] is True
    assert result['data']['referenceParams'] == []


# ==================== PUT ====================


@pytest.mark.parametrize('body', [{}, {'referenceParams': None}, {'referenceParams': 'x'}])
def test_update_rejects_missing_or_non_array(body, monkeypatch):
    testcase = _make_case(config={'rounds': [{'round_number': 1}]}, ref_params=[])
    service, repo = _crud_service(testcase, monkeypatch)

    result = service.update_ref_params(CASE_ID, 1, body)

    assert result['success'] is False
    assert result['code'] == 400
    assert repo.committed == 0


def test_update_unknown_round_returns_404(monkeypatch):
    testcase = _make_case(config={'rounds': [{'round_number': 1}]}, ref_params=[])
    service, _ = _crud_service(testcase, monkeypatch)

    result = service.update_ref_params(CASE_ID, 5, {'referenceParams': REF_PARAMS})

    assert result['success'] is False
    assert result['code'] == 404
    assert result['message'] == '未找到第 5 轮'


def test_update_creates_canonical_path_and_preserves_other_rounds(monkeypatch):
    other_path = f'oss://ref_params/{CASE_ID}/round_2.json'
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}, {'round_number': 2}]},
        ref_params=[{'round_number': 2, 'reference_params_path': other_path}],
    )
    config_before = json.loads(json.dumps(testcase.config))
    service, repo = _crud_service(testcase, monkeypatch)

    result = service.update_ref_params(CASE_ID, 1, {'referenceParams': REF_PARAMS})

    assert result['success'] is True
    stored_path = result['data']['referenceParamsPath']
    assert stored_path.endswith(f'{CASE_ID}/round_1.json')
    # 列内出现该轮条目，其它轮原样保留并按轮次升序
    assert testcase.reference_params == [
        {'round_number': 1, 'reference_params_path': stored_path},
        {'round_number': 2, 'reference_params_path': other_path},
    ]
    # 不回写 config.rounds
    assert testcase.config == config_before
    assert repo.committed == 1


def test_update_then_get_is_consistent(monkeypatch):
    testcase = _make_case(
        config={'rounds': [{'round_number': 2}]},
        ref_params=[{'round_number': 2,
                     'reference_params_path': f'oss://ref_params/{CASE_ID}/round_2.json'}],
    )
    service, _ = _crud_service(testcase, monkeypatch)

    put_result = service.update_ref_params(CASE_ID, 2, {'referenceParams': REF_PARAMS})
    get_result = _query_service(testcase).get_testcase_ref_params(CASE_ID, 2)

    assert put_result['success'] is True
    assert get_result['success'] is True
    assert get_result['data']['referenceParams'] == REF_PARAMS
    assert get_result['data']['referenceParamsPath'] == \
        put_result['data']['referenceParamsPath']


def test_update_legacy_windows_path_writes_normalized_key(monkeypatch):
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}]},
        ref_params=[{'round_number': 1, 'reference_params_path': LEGACY_PATH}],
    )
    service, _ = _crud_service(testcase, monkeypatch)

    result = service.update_ref_params(CASE_ID, 1, {'referenceParams': REF_PARAMS})

    assert result['success'] is True
    assert result['data']['referenceParamsPath'].endswith(f'{CASE_ID}/round_1.json')
    assert 'ref_params' in result['data']['referenceParamsPath']
    # 归一化后落点在 ref_params 分类下，宿主绝对路径不再参与写盘
    assert not result['data']['referenceParamsPath'].startswith('D:')


# ==================== 无法归一的路径 ====================


def test_update_unrecognized_path_fails_with_500_and_path(monkeypatch):
    """无法归一的原始绝对路径不能被当成 category 写进错误桶。"""
    raw = r'E:\export\round_1.json'
    testcase = _make_case(
        config={'rounds': [{'round_number': 1}]},
        ref_params=[{'round_number': 1, 'reference_params_path': raw}],
    )
    service, repo = _crud_service(testcase, monkeypatch)

    result = service.update_ref_params(CASE_ID, 1, {'referenceParams': REF_PARAMS})

    assert result['success'] is False
    assert result['code'] == 500
    assert raw in result['message']
    assert repo.committed == 0


# ==================== 网关状态码 ====================


def test_gateway_get_ref_params_maps_404_to_http_404(monkeypatch):
    """INT-1645：body code 404 时 HTTP 状态同为 404（原实现 HTTP 400）。"""
    import api_gateway.application.services.testcase.testcase_query_service as qs

    monkeypatch.setattr(
        qs._testcase_acl, 'get_testcase_ref_params',
        lambda *args, **kwargs: {'success': False, 'message': '未找到第 2 轮',
                                 'data': None, 'code': 404})

    body, http_code = qs.TestCaseQueryService.get_ref_params(CASE_ID, 2)

    assert http_code == 404
    assert body['code'] == 404
    assert body['success'] is False
    assert body['message'] == '未找到第 2 轮'
