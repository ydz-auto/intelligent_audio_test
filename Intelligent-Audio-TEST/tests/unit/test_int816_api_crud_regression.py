# -*- coding: utf-8 -*-
"""INT-816 返工回归 — apis 导入导出下游（api_test_service）两处缺陷修复。

打回失败项（测试工程师 2026-10-19，均在 apis 资源，根因在 api_crud_service）：
1. API 导入「新建」路径被下游拒绝（默认空 meta）：ApiCreateInput 恒输出
   meta={}（schema 默认值），旧 `not data.get('meta')` 把空 dict 判为缺失
   → 任何默认形态的新 API 都 imported 不了。修复：`data.get('meta') is None`
   （空 dict 是合法 meta，与 _validate_api_data 的 `meta is not None` 口径一致）。
2. API 导出→再导入 round-trip 失败：update 带 endpoints（导出行恒含
   `endpoints: []`）时 `api.default_max_process` 直取聚合根不存在的属性
   → AttributeError → 400。修复：getattr + 5/30/60 兜底（对齐 create）。
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
    """get_api 返回聚合根形态（_api_po_to_entity 丢弃 default_max_*/meta/endpoints）。"""

    def __init__(self):
        self.captured = {}

    @staticmethod
    def _api():
        return SimpleNamespace(
            id=9, name='API-1', url='http://example.com', status='online',
            output_types=[], device_type='http_api', api_endpoints=[],
        )

    def get_api(self, api_id):
        return self._api()

    def update_api(self, api_id, fields):
        self.captured.update(fields)
        return self._api()


class TestApiCreateEmptyMeta:

    def test_create_accepts_import_default_meta(self, monkeypatch):
        """导入行（无 meta，ApiCreateInput 默认 meta={}）可新建，不被判缺失。"""
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({
            'name': 'API-New', 'api_url': 'http://example.com',
            'vendor': 'vendor-x', 'status': 'online', 'meta': {},
        })

        assert res['code'] == 201
        assert repo.captured['name'] == 'API-New'
        assert repo.captured['meta'] == {}

    def test_create_rejects_missing_meta_key(self, monkeypatch):
        """meta 键完全缺失仍按必填拒绝（错误信息不变，仅空 dict 放行）。"""
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.create({'name': 'API-New', 'api_url': 'http://example.com'})

        assert res['code'] == 400
        assert '缺少必要字段' in res['message']
        assert not repo.captured


class TestApiUpdateWithEndpoints:

    def test_update_with_empty_endpoints_no_attr_error(self, monkeypatch):
        """round-trip 导出行含 endpoints: [] → update 不再 AttributeError。"""
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.update(9, {'endpoints': []})

        assert res['code'] == 200
        assert repo.captured['api_endpoints'] == []

    def test_update_round_trip_endpoint_shape(self, monkeypatch):
        """round-trip 导出行端点（含 priority，显式 max_*）→ 原样重建、不再 AttributeError。

        导出端点的 api_endpoints 恒带 max_process/max_timeout/max_audio_duration/priority，
        _validate_endpoint_data 要求这些键为 int（键存在即校验），故端点为全字段形态。
        """
        repo = _UpdateRepo()
        _install_repo(monkeypatch, repo)

        res = APICrudService.update(9, {'endpoints': [
            {'endpoint': 'http://example.com/api', 'name': 'ep1',
             'max_process': 8, 'max_timeout': 45, 'max_audio_duration': 90,
             'priority': 0, 'status': 'online', 'health_score': 100},
        ]})

        assert res['code'] == 200
        built = repo.captured['api_endpoints'][0]
        assert built['endpoint'] == 'http://example.com/api'
        assert built['max_process'] == 8
        assert built['max_timeout'] == 45
        assert built['max_audio_duration'] == 90

    def test_build_endpoints_none_defaults_fall_back(self):
        """update 修复后 getattr→None 经 or 5/30/60 兜底，_build_endpoints_list 产出 5/30/60。

        聚合根不承载 default_max_*（_api_po_to_entity 丢弃），update 侧 getattr 恒 None，
        `or 5/30/60` 兜底后传给 builder；端点缺显式值时落到兜底默认。
        """
        eps = [{'endpoint': 'http://example.com/api', 'name': 'ep1',
                'max_process': None, 'max_timeout': None,
                'max_audio_duration': None}]
        built = APICrudService._build_endpoints_list(eps, 5, 30, 60)
        assert built[0]['max_process'] == 5
        assert built[0]['max_timeout'] == 30
        assert built[0]['max_audio_duration'] == 60
