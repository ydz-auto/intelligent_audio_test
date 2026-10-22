# -*- coding: utf-8 -*-
"""INT-1177 密钥池 CRUD（endpoint 级，INT-1230 审计 D1'/D2'/D6' 返工口径）：
api_endpoints[].api_keys 校验 + 逐端点 api_keys_summary 响应摘要 +
写侧拒收摘要字段（阶段A 范围 1·5 / 验收 5·6·7）。

覆盖：
- create/update 校验每端点 api_keys：必须字符串数组、元素非空、去重、≤20
- _api_to_dict 逐端点内嵌 api_keys_summary（聚合根 endpoint_keys_summary
  派生态 + PO 原始态双兼容派生）
- _api_to_dict 对端点中完整 api_keys 一律不输出（防御，零明文响应）
- 写侧忽略入参 api_keys_summary（顶层 + 端点级，防前端回传污染存储）
- 未配置 api_keys 时摘要为 None（向后兼容，响应形态不变）
- update 合并语义：入参端点未含 api_keys 时按 endpoint URL 匹配保留既有池
"""
import os

# api_crud_service 导入链拉起 shared BaseConfig，补齐必填环境变量（不触库/不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService


class _FakeEventBus:
    def publish(self, channel, event_type, payload):
        pass


def _install_repo(monkeypatch, repo):
    monkeypatch.setattr(api_crud_module, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(api_crud_module, 'api_test_repository', repo)


def _endpoint(url='https://ep.example.com', keys=None, **extra):
    ep = {
        'endpoint': url,
        'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60,
        'priority': 1,
    }
    if keys is not None:
        ep['api_keys'] = keys
    ep.update(extra)
    return ep


class _CreateRepo:
    def __init__(self):
        self.captured = {}

    def create_api(self, data):
        self.captured.update(data)
        return SimpleNamespace(id=21)


class _UpdateRepo:
    def __init__(self, stored_meta=None, stored_endpoints=None):
        self.captured = {}
        # 写侧合并用：get_api_meta 读取存储 meta / get_api_endpoints 读原始端点
        self.stored_meta = stored_meta
        self.stored_endpoints = stored_endpoints

    @staticmethod
    def _api():
        return SimpleNamespace(
            id=9, name='API-1', url='http://example.com', status='online',
            output_types=[], device_type='http_api', api_endpoints=[],
        )

    def get_api(self, api_id):
        return self._api()

    def get_api_meta(self, api_id):
        return self.stored_meta

    def get_api_endpoints(self, api_id):
        return self.stored_endpoints

    def update_api(self, api_id, fields):
        self.captured.update(fields)
        return self._api()


# ── 端点级 api_keys 校验 ───────────────────────────────────────

class TestEndpointApiKeysValidation:

    def test_create_accepts_valid_api_keys(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys=['sk-a1', 'sk-b2'])],
        })
        assert res['code'] == 201
        assert repo.captured['api_endpoints'][0]['api_keys'] == ['sk-a1', 'sk-b2']

    def test_create_rejects_non_list(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys='sk-a1')],
        })
        assert res['code'] == 400
        assert '必须是字符串数组' in res['message']
        assert not repo.captured

    def test_create_rejects_empty_element(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys=['sk-a1', ''])],
        })
        assert res['code'] == 400
        assert '非空字符串' in res['message']

    def test_create_rejects_non_string_element(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys=['sk-a1', 123])],
        })
        assert res['code'] == 400
        assert '非空字符串' in res['message']

    def test_create_rejects_duplicate(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys=['sk-a1', 'sk-a1'])],
        })
        assert res['code'] == 400
        assert '不能重复' in res['message']

    def test_create_rejects_over_limit(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        too_many = [f'sk-{i}' for i in range(21)]
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint(keys=too_many)],
        })
        assert res['code'] == 400
        assert '最多支持 20 个密钥' in res['message']

    def test_create_no_api_keys_endpoint_stored_empty(self, monkeypatch):
        """未配 api_keys 的端点：落库 api_keys 为空数组（池单例/无池语义，
        向后兼容回退单值链）"""
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {},
            'endpoints': [_endpoint()],
        })
        assert res['code'] == 201
        assert repo.captured['api_endpoints'][0]['api_keys'] == []

    def test_update_validates_api_keys(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'endpoints': [_endpoint(keys=['sk-a1'])],
        })
        assert res['code'] == 200
        assert repo.captured['api_endpoints'][0]['api_keys'] == ['sk-a1']

    def test_update_rejects_duplicate(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'endpoints': [_endpoint(keys=['sk-a1', 'sk-a1'])],
        })
        assert res['code'] == 400
        assert '不能重复' in res['message']


# ── 逐端点 api_keys_summary 响应摘要 ────────────────────────────

class TestEndpointApiKeysSummary:

    def test_to_dict_aggregate_carries_per_endpoint_summary(self):
        """聚合根派生态（endpoint_keys_summary）：逐端点内嵌摘要，完整密钥
        零响应"""
        api = SimpleNamespace(
            id=1, name='A', status='online',
            endpoint_keys_summary=[
                {'endpoint': 'https://ep1.example.com',
                 'api_keys_summary': {'count': 2, 'tails': ['a1b2', 'c3d4']}},
            ],
            meta={}, created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        assert out['endpoints'][0]['api_keys_summary'] == {
            'count': 2, 'tails': ['a1b2', 'c3d4']}
        assert 'api_keys' not in out['endpoints'][0]
        assert 'api_keys_summary' not in out

    def test_to_dict_po_derives_summary_and_strips_keys(self):
        """PO 原始态（防御）：从端点 api_keys 派生逐端点摘要，完整密钥剥离"""
        api = SimpleNamespace(
            id=2, name='B', status='online',
            meta={'protocol': 'https'},
            api_endpoints=[
                {'endpoint': 'https://ep.example.com',
                 'api_keys': ['sk-abcdef12', 'sk-xyz98765']},
            ],
            created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        ep = out['endpoints'][0]
        assert ep['api_keys_summary']['count'] == 2
        assert ep['api_keys_summary']['tails'] == ['ef12', '8765']
        assert 'api_keys' not in ep
        assert out['meta']['protocol'] == 'https'

    def test_to_dict_no_api_keys_summary_none(self):
        """未配置端点密钥池：逐端点摘要为 None（响应形态向后兼容）"""
        api = SimpleNamespace(
            id=3, name='C', status='online',
            meta={},
            endpoint_keys_summary=[
                {'endpoint': 'https://ep.example.com'},
            ],
            created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        assert out['endpoints'][0]['api_keys_summary'] is None


# ── 写侧拒收摘要字段（顶层 + 端点级） ─────────────────────────

class TestWriteSideRejectSummary:

    def test_create_ignores_api_keys_summary(self, monkeypatch):
        """前端回传顶层/端点级 api_keys_summary 不污染存储：仅端点 api_keys
        明文入库"""
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A',
            'meta': {},
            'api_keys_summary': {'count': 1, 'tails': ['a1']},
            'endpoints': [_endpoint(keys=['sk-a1'], api_keys_summary={
                'count': 1, 'tails': ['a1']})],
        })
        assert res['code'] == 201
        assert 'api_keys_summary' not in repo.captured
        ep = repo.captured['api_endpoints'][0]
        assert 'api_keys_summary' not in ep
        assert ep['api_keys'] == ['sk-a1']

    def test_update_ignores_api_keys_summary(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'endpoints': [_endpoint(keys=['sk-a1'], api_keys_summary={
                'count': 1, 'tails': ['a1']})],
        })
        assert res['code'] == 200
        ep = repo.captured['api_endpoints'][0]
        assert 'api_keys_summary' not in ep
        assert ep['api_keys'] == ['sk-a1']


# ── update 合并语义：编辑无关字段保存时保留既有端点密钥池 ──────

class TestUpdatePreservesEndpointKeyPool:
    """update 合并语义（INT-1230 审计 D2'/D6'，endpoint 级返工）：读侧剥离
    完整 api_keys，编辑表单拿不到池、回传端点必无 api_keys——整块覆盖会静默
    清空既有池。入参端点未含 api_keys 时按 endpoint URL 匹配保留既有池；
    显式传完整数组才覆盖。"""

    def test_update_without_api_keys_preserves_pool(self, monkeypatch):
        """编辑无关字段（端点 URL 不变、未重发 api_keys）→ 既有池保留"""
        repo = _UpdateRepo(stored_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': ['sk-k1', 'sk-k2']},
        ])
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'name': 'A-renamed',
            'endpoints': [_endpoint(url='https://ep.example.com')],
        })
        assert res['code'] == 200
        assert repo.captured['api_endpoints'][0]['api_keys'] == ['sk-k1', 'sk-k2']

    def test_update_explicit_api_keys_overrides_pool(self, monkeypatch):
        """显式传完整 api_keys 数组才覆盖（重新输入完整密钥列表替换池）"""
        repo = _UpdateRepo(stored_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': ['sk-old-1']},
        ])
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'endpoints': [_endpoint(url='https://ep.example.com',
                                    keys=['sk-new-1', 'sk-new-2'])],
        })
        assert res['code'] == 200
        assert repo.captured['api_endpoints'][0]['api_keys'] == ['sk-new-1', 'sk-new-2']
        # 既有池被显式数组替换，未残留旧 key
        assert 'sk-old-1' not in repo.captured['api_endpoints'][0]['api_keys']

    def test_update_no_existing_pool_unchanged(self, monkeypatch):
        """无既有池 + 入参端点无 api_keys → 端点 api_keys 落空数组（无池）"""
        repo = _UpdateRepo(stored_endpoints=[
            {'endpoint': 'https://ep.example.com'},
        ])
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'name': 'B',
            'endpoints': [_endpoint(url='https://ep.example.com')],
        })
        assert res['code'] == 200
        assert repo.captured['api_endpoints'][0]['api_keys'] == []

    def test_update_new_endpoint_no_existing_pool(self, monkeypatch):
        """新增端点（URL 不匹配既有）→ 无池可保留，落空数组"""
        repo = _UpdateRepo(stored_endpoints=[
            {'endpoint': 'https://old.example.com', 'api_keys': ['sk-old-1']},
        ])
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'endpoints': [_endpoint(url='https://new.example.com')],
        })
        assert res['code'] == 200
        assert repo.captured['api_endpoints'][0]['api_keys'] == []
