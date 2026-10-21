# -*- coding: utf-8 -*-
"""INT-1177 密钥池 CRUD：meta.api_keys 校验 + api_keys_summary 响应摘要 +
写侧拒收摘要字段（阶段A 范围 4 / 验收 6·7）。

覆盖：
- create/update 校验 meta.api_keys：必须字符串数组、元素非空、去重、≤20
- _api_to_dict 顶层 api_keys_summary（聚合根承载 + PO 双兼容派生）
- _api_to_dict 对 meta 中完整 api_keys 一律不输出（防御，零明文响应）
- 写侧忽略入参 api_keys_summary（防前端回传污染存储）
- 未配置 api_keys 时摘要为 None（向后兼容，响应形态不变）
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


class _CreateRepo:
    def __init__(self):
        self.captured = {}

    def create_api(self, data):
        self.captured.update(data)
        return SimpleNamespace(id=21)


class _UpdateRepo:
    def __init__(self, stored_meta=None):
        self.captured = {}
        # 写侧合并用：get_api_meta 读取存储 meta（聚合根不承载完整 meta）
        self.stored_meta = stored_meta

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

    def update_api(self, api_id, fields):
        self.captured.update(fields)
        return self._api()


# ── meta.api_keys 校验 ───────────────────────────────────────

class TestApiKeysValidation:

    def test_create_accepts_valid_api_keys(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': ['sk-a1', 'sk-b2']},
        })
        assert res['code'] == 201
        assert repo.captured['meta']['api_keys'] == ['sk-a1', 'sk-b2']

    def test_create_rejects_non_list(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': 'sk-a1'},
        })
        assert res['code'] == 400
        assert '必须是字符串数组' in res['message']
        assert not repo.captured

    def test_create_rejects_empty_element(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': ['sk-a1', '']},
        })
        assert res['code'] == 400
        assert '非空字符串' in res['message']

    def test_create_rejects_non_string_element(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': ['sk-a1', 123]},
        })
        assert res['code'] == 400
        assert '非空字符串' in res['message']

    def test_create_rejects_duplicate(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': ['sk-a1', 'sk-a1']},
        })
        assert res['code'] == 400
        assert '不能重复' in res['message']

    def test_create_rejects_over_limit(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        too_many = [f'sk-{i}' for i in range(21)]
        res = APICrudService.create({
            'name': 'A', 'meta': {'api_keys': too_many},
        })
        assert res['code'] == 400
        assert '最多支持 20 个密钥' in res['message']

    def test_update_validates_api_keys(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {'meta': {'api_keys': ['sk-a1']}})
        assert res['code'] == 200
        assert repo.captured['meta']['api_keys'] == ['sk-a1']

    def test_update_rejects_duplicate(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {'meta': {'api_keys': ['sk-a1', 'sk-a1']}})
        assert res['code'] == 400
        assert '不能重复' in res['message']


# ── api_keys_summary 响应摘要 ────────────────────────────────

class TestApiKeysSummary:

    def test_to_dict_aggregate_carries_summary(self):
        """聚合根承载摘要：顶层透出 {count, tails[]}，meta 不含完整密钥"""
        api = SimpleNamespace(
            id=1, name='A', status='online',
            api_keys_summary={'count': 2, 'tails': ['a1b2', 'c3d4']},
            created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        assert out['api_keys_summary'] == {'count': 2, 'tails': ['a1b2', 'c3d4']}
        assert out['meta'] == {}

    def test_to_dict_po_derives_summary_and_strips_keys(self):
        """PO 双兼容（防御）：无聚合摘要字段时从 meta.api_keys 派生，
        meta 中完整 api_keys 一律不输出"""
        api = SimpleNamespace(
            id=2, name='B', status='online',
            meta={'api_keys': ['sk-abcdef12', 'sk-xyz98765'], 'protocol': 'https'},
            created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        assert out['api_keys_summary']['count'] == 2
        assert out['api_keys_summary']['tails'] == ['ef12', '8765']
        assert 'api_keys' not in out['meta']
        assert out['meta']['protocol'] == 'https'

    def test_to_dict_no_api_keys_summary_none(self):
        """未配置密钥池：摘要为 None（响应形态向后兼容）"""
        api = SimpleNamespace(
            id=3, name='C', status='online',
            meta={}, api_keys_summary=None, created_at=None, updated_at=None,
        )
        out = APICrudService._api_to_dict(api)
        assert out['api_keys_summary'] is None
        assert out['meta'] == {}


# ── 写侧拒收摘要字段 ─────────────────────────────────────────

class TestWriteSideRejectSummary:

    def test_create_ignores_api_keys_summary(self, monkeypatch):
        """前端回传 api_keys_summary 不污染存储：仅 meta.api_keys 明文入库"""
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'A',
            'meta': {'api_keys': ['sk-a1']},
            'api_keys_summary': {'count': 1, 'tails': ['a1']},
        })
        assert res['code'] == 201
        assert 'api_keys_summary' not in repo.captured
        assert repo.captured['meta']['api_keys'] == ['sk-a1']

    def test_update_ignores_api_keys_summary(self, monkeypatch):
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'meta': {'api_keys': ['sk-a1']},
            'api_keys_summary': {'count': 1, 'tails': ['a1']},
        })
        assert res['code'] == 200
        assert 'api_keys_summary' not in repo.captured
        assert repo.captured['meta']['api_keys'] == ['sk-a1']


# ── 返工(2) P1：编辑无关字段保存时保留既有密钥池（审计打回回归） ──────

class TestUpdatePreservesKeyPoolOnUnrelatedEdit:
    """update 合并语义：入参 meta 未含 api_keys 时保留既有池（读侧剥离
    api_keys，前端编辑表单拿不到池、回传必无 api_keys——整块覆盖会静默
    清空）；显式传完整数组才覆盖（重新输入完整密钥列表语义）。"""

    def test_update_without_api_keys_preserves_pool(self, monkeypatch):
        """前端 normalizeMetaForUpsert 对空密钥列表的真实输出（meta 无
        api_keys）→ 编辑无关字段后池保留"""
        repo = _UpdateRepo(stored_meta={
            'protocol': 'https', 'api_keys': ['sk-k1', 'sk-k2'],
        })
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'name': 'A-renamed',
            'meta': {'protocol': 'https', 'apiKey': ''},
        })
        assert res['code'] == 200
        assert repo.captured['meta']['api_keys'] == ['sk-k1', 'sk-k2']
        assert repo.captured['meta']['protocol'] == 'https'
        assert repo.captured['meta']['apiKey'] == ''

    def test_update_explicit_api_keys_overrides_pool(self, monkeypatch):
        """显式传完整 api_keys 数组才覆盖（重新输入完整密钥列表替换池）"""
        repo = _UpdateRepo(stored_meta={
            'protocol': 'https', 'api_keys': ['sk-old-1'],
        })
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'meta': {'api_keys': ['sk-new-1', 'sk-new-2']},
        })
        assert res['code'] == 200
        assert repo.captured['meta']['api_keys'] == ['sk-new-1', 'sk-new-2']
        # 既有池被显式数组替换，未残留旧 key
        assert 'sk-old-1' not in repo.captured['meta']['api_keys']

    def test_update_no_existing_pool_unchanged(self, monkeypatch):
        """无既有池 + 入参无 api_keys → meta 原样落库（不注入 api_keys）"""
        repo = _UpdateRepo(stored_meta={'protocol': 'https'})
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'name': 'B', 'meta': {'protocol': 'https'},
        })
        assert res['code'] == 200
        assert 'api_keys' not in repo.captured['meta']
        assert repo.captured['meta']['protocol'] == 'https'
