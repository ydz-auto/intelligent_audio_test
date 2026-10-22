# -*- coding: utf-8 -*-
"""INT-1338 读侧回显缺口回归 — API PO → 聚合根 → _api_to_dict 全字段回显。

根因（V9.7.31 api_test_service）：APIAggregate 未承载 vendor / meta /
description / algorithm_type / default_max_* / health_score / api_endpoints /
created_at / updated_at → 读侧 `_api_to_dict` 经 getattr 兜底全部得
None / []（GET /apis、GET /apis/{id}、PUT 响应逐字段回显缺）。

本文件对齐 test_int68 的 INT-300 回归写法：真实 PO → `_api_po_to_entity`
→ `_api_to_dict` 全字段回显一致；同时守住 INT-1177（meta 剥离 api_keys、
摘要派生、零明文）与 INT-816（无新字段的遗留聚合根/SimpleNamespace 经
getattr 兜底不回归）。
"""
import os
from datetime import datetime, timezone

# api_crud_service 导入链拉起 shared BaseConfig，补齐必填环境变量（不触库/不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService
from api_test_service.domain.entities import APIAggregate
from api_test_service.infrastructure.persistence.api_test_repository import (
    _api_po_to_entity,
    _apply_aggregate_to_po,
)
from api_test_service.infrastructure.persistence.models import API


def _full_po(**overrides):
    """构造含全部读侧回显字段的真实 API PO（内存对象，不落库）。"""
    defaults = dict(
        id=38,
        name='接线测试_INT1338_读侧回显',
        vendor='WalkVendor',
        description='读侧回显验收用 API',
        status='offline',
        meta={'protocol': 'https', 'environment': 'testing',
              'api_keys': ['sk-abcdef12', 'sk-xyz98765']},
        algorithm_type='asr_streaming',
        default_max_process=5,
        default_max_timeout=30,
        default_max_audio_duration=60,
        health_score=100.0,
        api_endpoints=[{'endpoint': 'https://api.walk.test/v1/asr/stream',
                        'name': 'stream', 'max_process': 5, 'max_timeout': 30,
                        'max_audio_duration': 60, 'status': 'online',
                        'health_score': 100, 'priority': 0, 'description': ''}],
        output_types=['audio', 'text'],
        device_type='http_api',
        adapter_class=None,
        audio_config={'sample_rate': 24000, 'bit_depth': 's16',
                      'channels': 1, 'container': 'pcm'},
        rms_spl_mapping_id=None,
        proxy_type='http',
        proxy_url='user:pass@127.0.0.1:8080',
        created_at=datetime(2026, 10, 22, 11, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 22, 11, 30, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return API(**defaults)


class TestPoToAggregateCarriesReadFields:
    """真实 PO → 聚合根：新增承载字段全量映射（INT-1338 根因修复）。"""

    def test_full_po_maps_all_fields(self):
        po = _full_po()
        agg = _api_po_to_entity(po)

        assert agg.vendor == 'WalkVendor'
        assert agg.meta == {'protocol': 'https', 'environment': 'testing'}
        assert agg.description == '读侧回显验收用 API'
        assert agg.algorithm_type == 'asr_streaming'
        assert agg.default_max_process == 5
        assert agg.default_max_timeout == 30
        assert agg.default_max_audio_duration == 60
        assert agg.health_score == 100.0
        assert agg.api_endpoints == _full_po().api_endpoints
        assert agg.created_at == po.created_at
        assert agg.updated_at == po.updated_at

    def test_meta_api_keys_stripped_and_summary_derived(self):
        """INT-1177 守口：聚合根不承载完整 api_keys（零明文），摘要派生承载。"""
        po = _full_po()
        agg = _api_po_to_entity(po)

        assert 'api_keys' not in (agg.meta or {})
        assert agg.api_keys_summary == {'count': 2, 'tails': ['ef12', '8765']}

    def test_legacy_po_nullable_fields_default(self):
        """无新字段值的存量行：映射不炸，空值默认承载（None / []）。"""
        po = API(id=1, name='legacy', meta={}, status='online')
        agg = _api_po_to_entity(po)

        assert agg.vendor is None
        assert agg.meta == {}
        assert agg.description is None
        assert agg.algorithm_type is None
        assert agg.default_max_process is None
        assert agg.default_max_timeout is None
        assert agg.default_max_audio_duration is None
        assert agg.health_score is None
        assert agg.api_endpoints == []
        assert agg.created_at is None
        assert agg.updated_at is None


class TestAggregateToDictEcho:
    """聚合根 → _api_to_dict：GET /apis、GET /apis/{id}、PUT 响应逐字段回显。"""

    def test_full_echo(self):
        agg = _api_po_to_entity(_full_po())
        out = APICrudService._api_to_dict(agg)

        assert out['id'] == 38
        assert out['name'] == '接线测试_INT1338_读侧回显'
        assert out['vendor'] == 'WalkVendor'
        assert 'api_url' not in out  # INT-1361 api_url 移除后读侧不再输出
        assert out['description'] == '读侧回显验收用 API'
        assert out['status'] == 'offline'
        assert out['meta'] == {'protocol': 'https', 'environment': 'testing'}
        assert 'api_keys' not in out['meta']
        # INT-1230 读侧密钥池摘要在端点级内嵌（endpoints[].api_keys_summary），
        # 顶层不再直出；本 PO 端点未配密钥池 → 端点摘要为 None
        assert 'api_keys_summary' not in out
        assert out['algorithm_type'] == 'asr_streaming'
        assert out['default_max_process'] == 5
        assert out['default_max_timeout'] == 30
        assert out['default_max_audio_duration'] == 60
        assert out['health_score'] == 100.0
        assert out['endpoints'] == [{
            'id': '38_0', 'endpoint': 'https://api.walk.test/v1/asr/stream',
            'name': 'stream', 'max_process': 5, 'max_timeout': 30,
            'max_audio_duration': 60, 'status': 'online',
            'health_score': 100, 'priority': 0, 'description': '',
            'api_keys_summary': None,
        }]
        assert out['created_at'] == '2026-10-22T11:00:00+00:00'
        assert out['updated_at'] == '2026-10-22T11:30:00+00:00'

    def test_proxy_echo(self):
        agg = _api_po_to_entity(_full_po())
        out = APICrudService._api_to_dict(agg)
        assert out['proxy_type'] == 'http'
        assert out['proxy_url'] == 'user:pass@127.0.0.1:8080'

    def test_legacy_aggregate_without_new_fields_no_attr_error(self):
        """INT-816 回归：无新字段的遗留聚合根/SimpleNamespace 经 getattr 兜底，
        _api_to_dict 不抛 AttributeError，空值输出 None / []。"""
        api = SimpleNamespace(
            id=9, name='API-1', url='http://example.com', status='online',
            output_types=[], device_type='http_api', api_endpoints=[],
        )
        out = APICrudService._api_to_dict(api)
        assert out['vendor'] is None
        assert out['meta'] == {}
        assert out['description'] is None
        assert out['algorithm_type'] is None
        assert out['default_max_process'] is None
        assert out['default_max_timeout'] is None
        assert out['default_max_audio_duration'] is None
        assert out['health_score'] is None
        assert out['endpoints'] == []
        assert out['created_at'] is None
        assert out['updated_at'] is None


class TestAppReadSideEcho:
    """应用层读侧（get_one / get_all）经假仓储回显全字段。"""

    class _FullRepo:
        def get_api(self, api_id):
            return _api_po_to_entity(_full_po(id=api_id))

        def list_apis(self, page=1, per_page=10, keyword=None,
                      status=None, algorithm_type=None):
            po = _full_po(id=38)
            po2 = _full_po(id=40, name='接线测试_INT1338_列表2', vendor='WalkVendor2',
                           algorithm_type='tts_eval',
                           default_max_process=8, default_max_timeout=40,
                           default_max_audio_duration=90,
                           api_endpoints=[{'endpoint': 'https://api.walk.test/v1/stream',
                                           'name': 'ep1', 'max_process': 8,
                                           'max_timeout': 40, 'max_audio_duration': 90,
                                           'status': 'online', 'health_score': 100,
                                           'priority': 0, 'description': ''}])
            return {'items': [_api_po_to_entity(po), _api_po_to_entity(po2)],
                    'total': 2, 'page': page, 'per_page': per_page, 'pages': 1}

    class _FakeEventBus:
        def publish(self, channel, event_type, payload):
            pass

    def _install(self, monkeypatch):
        monkeypatch.setattr(api_crud_module, 'EventBus', self._FakeEventBus)
        monkeypatch.setattr(api_crud_module, 'api_test_repository', self._FullRepo())

    def test_get_one_echo(self, monkeypatch):
        self._install(monkeypatch)
        res = APICrudService.get_one(38)
        assert res['code'] == 200
        data = res['data']
        assert data['vendor'] == 'WalkVendor'
        assert data['algorithm_type'] == 'asr_streaming'
        assert data['default_max_process'] == 5
        assert data['endpoints'][0]['endpoint'] == 'https://api.walk.test/v1/asr/stream'
        assert data['created_at'] == '2026-10-22T11:00:00+00:00'

    def test_get_all_list_echo(self, monkeypatch):
        self._install(monkeypatch)
        res = APICrudService.get_all(page=1, per_page=10)
        assert res['code'] == 200
        items = res['data']['items']
        assert len(items) == 2
        assert items[0]['vendor'] == 'WalkVendor'
        assert items[0]['meta'] == {'protocol': 'https', 'environment': 'testing'}
        assert items[1]['vendor'] == 'WalkVendor2'
        assert items[1]['algorithm_type'] == 'tts_eval'
        assert items[1]['default_max_process'] == 8
        assert items[1]['default_max_timeout'] == 40
        assert items[1]['default_max_audio_duration'] == 90


class TestApplyAggregateToPoWriteBack:
    """save 路径回写一致性（低优先级）：新增字段回写 PO，NOT NULL 列不破坏。"""

    def test_full_aggregate_write_back(self):
        po = API(id=38, name='old', meta={'protocol': 'https',
                                          'api_keys': ['sk-keep-1']}, status='online')
        agg = _api_po_to_entity(_full_po())
        _apply_aggregate_to_po(agg, po)

        assert po.vendor == 'WalkVendor'
        assert po.description == '读侧回显验收用 API'
        assert po.algorithm_type == 'asr_streaming'
        assert po.default_max_process == 5
        assert po.default_max_timeout == 30
        assert po.default_max_audio_duration == 60
        assert po.health_score == 100.0
        assert po.api_endpoints == _full_po().api_endpoints
        # 聚合根不承载 api_keys → 回写保留 PO 既有密钥池（INT-1177 守口）
        assert po.meta['api_keys'] == ['sk-keep-1']
        assert po.meta['protocol'] == 'https'

    def test_sparse_aggregate_preserves_not_null(self):
        """手工构造的空缺值聚合根（新字段全 None）：NOT NULL 列不回写清空。"""
        po = API(id=1, name='n', meta={'protocol': 'https'}, status='online')
        po.default_max_process = 5
        po.default_max_timeout = 30
        po.default_max_audio_duration = 60
        po.health_score = 100.0
        po.api_endpoints = []
        agg = APIAggregate(id=1, name='n', status='online')

        _apply_aggregate_to_po(agg, po)

        assert po.meta == {'protocol': 'https'}  # 聚合根 meta=None → 不覆盖
        assert po.default_max_process == 5        # 聚合根默认 None → 不清空
        assert po.default_max_timeout == 30
        assert po.default_max_audio_duration == 60
        assert po.health_score == 100.0
        assert po.api_endpoints == []
        assert po.vendor is None
