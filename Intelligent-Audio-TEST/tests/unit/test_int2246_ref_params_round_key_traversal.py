# -*- coding: utf-8 -*-
"""INT-2246 参考参数存储 key 路径穿越单测（隔离存储，不连 DB / OSS / gRPC）。

卡面验收：
- 非正整数 round_number 不产生写入；
- `..` 构造被拒（不能拼出越出存储根目录的 key）；
- 正常轮次写入/读取不受影响。

三处 `_apply_reference_params_to_config`（task_service crud / batch mixin、
api_gateway command service）同口径验证。
"""
import importlib
import json
import os
from types import SimpleNamespace

import pytest

# BaseConfig 在首次导入即校验 OSS 凭据（类属性冻结），先伪造再导入
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig  # noqa: E402
from shared.infrastructure.storage import Storage  # noqa: E402
from shared.utils import testcase_helpers as helpers  # noqa: E402

CASE_ID = 'd2b8a465-9f48-46f6-9624-7702e9ae2145'
REF_PARAMS = [{'code': 'ref_text', 'value': 'hello'}]
TRAVERSAL_VALUES = ['../../../../tmp/pwned', '../x', '1/../../x', 0, -3, 'abc', '1.0', True]


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
    monkeypatch.setattr(BaseConfig, 'STORAGE_FALLBACK_ENABLED', True)
    monkeypatch.setattr(Storage, '_oss',
                        property(lambda self: _NoOssClient()))
    instance = Storage()
    monkeypatch.setattr(instance, '_oss_checked', False)
    monkeypatch.setattr(instance, '_oss_ok', False, raising=False)
    yield tmp_path


def _make_case(rounds):
    return SimpleNamespace(
        id=CASE_ID,
        name='接线测试_参考参数穿越',
        config={'rounds': rounds},
        reference_params=None,
        algorithm_type='asr',
    )


def _files_under(root):
    """列出目录下全部文件（相对路径），用于断言没有越界落盘。"""
    found = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            found.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(found)


# ==================== 轮次号归一 ====================


@pytest.mark.parametrize('raw, expected', [
    (1, 1), (2, 2), ('3', 3), (' 4 ', 4), (5.0, 5),
    (0, None), (-1, None), ('0', None), (-3.0, None),
    ('abc', None), ('1.0', None), ('1e3', None), ('+1', None), ('  ', None),
    ('../../../../tmp/pwned', None), ('1/../../x', None), ('1\\..\\x', None),
    (True, None), (None, None), ([], None), ({}, None),
])
def test_parse_round_number_whitelist(raw, expected):
    assert helpers.parse_round_number(raw) == expected


@pytest.mark.parametrize('round_item, expected', [
    ({'round_number': 2}, 2),
    ({'roundNumber': '3'}, 3),
    ({'round_number': 2, 'roundNumber': 9}, 2),
    ({'round_number': None, 'roundNumber': 3}, 3),
    ({'round_number': ''}, 1),               # 空值按缺省第 1 轮
    ({}, 1),
    ({'round_number': '../../../../tmp/pwned'}, None),
    ({'roundNumber': 0}, None),
])
def test_resolve_round_number(round_item, expected):
    assert helpers.resolve_round_number(round_item, default=1) == expected


# ==================== key 构建白名单 ====================


def _key_builders():
    # 包 __init__ 里 testcase_crud_service 是单例对象，按 importlib 取模块本体
    gw = importlib.import_module(
        'api_gateway.application.services.testcase.testcase_command_service')
    batch_ref = importlib.import_module(
        'task_service.application.testcase.testcase_batch_reference_mixin')
    crud = importlib.import_module(
        'task_service.application.testcase.testcase_crud_service')

    return [gw._build_ref_params_key, batch_ref._build_ref_params_key,
            crud._build_ref_params_key]


@pytest.mark.parametrize('bad', TRAVERSAL_VALUES + [None, '', '  '])
def test_build_ref_params_key_rejects_traversal(bad):
    for builder in _key_builders():
        with pytest.raises(ValueError):
            builder(CASE_ID, bad)


def test_build_ref_params_key_rejects_traversal_filename():
    for builder in _key_builders():
        with pytest.raises(ValueError):
            builder(CASE_ID, 1, '../../../../tmp/pwned.json')
        with pytest.raises(ValueError):
            builder(CASE_ID, 1, 'a/b.json')


def test_build_ref_params_key_normal():
    for builder in _key_builders():
        assert builder(CASE_ID, 2) == f'{CASE_ID}/round_2.json'
        assert builder(CASE_ID, '3') == f'{CASE_ID}/round_3.json'


# ==================== 写入路径（三处同口径） ====================


def _apply_functions(monkeypatch):
    """返回 [(名称, apply_fn)]，并把算法侧生成替换成常量。"""
    gw = importlib.import_module(
        'api_gateway.application.services.testcase.testcase_command_service')
    batch_ref = importlib.import_module(
        'task_service.application.testcase.testcase_batch_reference_mixin')
    crud = importlib.import_module(
        'task_service.application.testcase.testcase_crud_service')
    from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository

    monkeypatch.setattr(AlgorithmRepository, 'algo_generate_reference_params',
                        lambda self, test_case_config=None, round_data=None: [dict(REF_PARAMS[0])])
    monkeypatch.setattr(AlgorithmRepository, 'algo_get_all_reference_params',
                        lambda self, params=None: list(params or []))

    import api_gateway.infrastructure.grpc_proxies as proxies
    import api_gateway.infrastructure.grpc_proxies.algorithm_proxies as algo_proxies

    fake = SimpleNamespace(
        generate_reference_params=lambda test_case_config=None, round_data=None: [dict(REF_PARAMS[0])],
        get_all_reference_params=lambda params=None: list(params or []),
    )
    monkeypatch.setattr(proxies, 'algorithm_query_service', fake)
    monkeypatch.setattr(algo_proxies, 'algorithm_query_service', fake)

    return [
        ('crud', crud._apply_reference_params_to_config),
        ('batch', batch_ref._apply_reference_params_to_config),
        ('gateway', gw._apply_reference_params_to_config),
    ]


@pytest.mark.parametrize('bad', TRAVERSAL_VALUES)
def test_apply_reference_params_skips_invalid_round(bad, monkeypatch, _isolated_storage):
    storage_root = _isolated_storage
    for name, apply_fn in _apply_functions(monkeypatch):
        test_case = _make_case([{'round_number': bad}])

        apply_fn(test_case)

        assert test_case.reference_params == [], f'{name}: 非正整数轮次不应写入'
        # 本地降级根目录下不产生文件，且父目录不会出现 pwned.json
        assert _files_under(storage_root) == [], f'{name}: 不应落盘'
        parent = os.path.dirname(str(storage_root))
        assert not os.path.exists(os.path.join(parent, 'pwned.json')), \
            f'{name}: 构造值逃出了存储根目录'


def test_apply_reference_params_writes_valid_round_inside_root(monkeypatch, _isolated_storage):
    storage_root = _isolated_storage
    for name, apply_fn in _apply_functions(monkeypatch):
        test_case = _make_case([{'round_number': 2, 'referenceParamsPath': 'ignored'}])

        apply_fn(test_case)

        assert len(test_case.reference_params) == 1, name
        entry = test_case.reference_params[0]
        assert entry['round_number'] == 2
        # OSS 不可用时返回 local:// 降级路径，落点仍在存储根目录内
        assert entry['reference_params_path'].endswith(f'ref_params/{CASE_ID}/round_2.json')
        written = os.path.join(str(storage_root), 'ref_params', CASE_ID, 'round_2.json')
        assert os.path.isfile(written), f'{name}: 正常轮次应落盘'
        with open(written, 'r', encoding='utf-8') as fh:
            assert json.load(fh) == REF_PARAMS


def test_apply_reference_params_mixed_rounds_skip_only_invalid(monkeypatch, _isolated_storage):
    for name, apply_fn in _apply_functions(monkeypatch):
        test_case = _make_case([
            {'round_number': '../../../../tmp/pwned'},
            {'roundNumber': 3},
            {'round_number': 0},
            {},  # 缺省第 1 轮
        ])

        apply_fn(test_case)

        summary = [(item['round_number'],
                    item['reference_params_path'].endswith(f'{CASE_ID}/round_{item["round_number"]}.json'))
                   for item in test_case.reference_params]
        assert summary == [(3, True), (1, True)], name
