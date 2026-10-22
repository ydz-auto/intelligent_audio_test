# -*- coding: utf-8 -*-
"""INT-1364 回归 — API 读路径聚合根补承载字段，编辑回显 + 改名保存不抹数据。

根因：api_test_repository._api_po_to_entity 丢弃 vendor/meta/algorithm_type/
default_max_*/api_endpoints/health_score，读侧（GET /apis/{id} / 列表）全返 null，
前端编辑弹窗空回显；改名保存把空值发成默认/空覆盖 DB（静默数据丢失）。

覆盖：
- 创建全字段 → 读侧 dict（网关 GET /apis/{id} 同源）逐字段回显一致；
- 列表聚合根同样承载；
- 只改名称保存（回显值提交）后 DB meta/endpoints/default_max_* 不被抹、不被默认覆盖；
- DDD save 路径（get_by_id 加载 → save）不丢字段。

DB：SQLite 临时文件库（check_same_thread=False），仅建 apis 表，
对齐 test_int842_api_operator_user_id.py 的 db 夹具口径。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

import tempfile

import pytest

import shared.models.database as database


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建 apis 表。"""
    from sqlalchemy import create_engine

    from api_test_service.infrastructure.persistence.models.api_models import API

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(
        f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[API.__table__])
    yield database
    database.remove_db_session()
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


def _get_api_po(db, api_id):
    from api_test_service.infrastructure.persistence.models import API
    session = db.get_db_session()
    try:
        return session.get(API, api_id)
    finally:
        db.remove_db_session()


_FULL_FIELDS = {
    'name': '接线测试_INT1364_apiC',
    'vendor': 'volc_ast',
    'api_url': 'http://master.local:5000',
    'description': 'INT-1364 回归',
    'meta': {'protocol': 'https', 'environment': 'testing',
             'version': 'v2', 'apiKey': 'sk-test-1364'},
    'algorithm_type': 'voice_llm',
    'default_max_process': 3,
    'default_max_timeout': 20,
    'default_max_audio_duration': 30,
    'status': 'online',
    'api_endpoints': [{
        'endpoint': 'http://api.test.local/v1/asr',
        'name': 'ASR端点',
        'max_process': 2,
        'max_timeout': 15,
        'max_audio_duration': 25,
        'priority': 1,
        'status': 'online',
        'health_score': 100,
        'description': '',
    }],
    'device_type': 'http_api',
}


@pytest.fixture()
def neutralize_side_effects(monkeypatch):
    """隔离 update 的无关副作用（Redis 事件发布 + 首页统计刷新）。"""
    from api_test_service.application import api_crud_service as api_crud_module

    class _FakeEventBus:
        def publish(self, channel, event_type, payload):
            pass

    monkeypatch.setattr(api_crud_module, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(api_crud_module, 'refresh_stats_cache', lambda: None)


class TestApiReadEchoRoundTrip:

    def test_create_get_echo_all_fields(self, db):
        """读侧 dict（GET /apis/{id} 同源）对已创建 API 逐字段回显一致。"""
        from api_test_service.application.api_crud_service import APICrudService
        from api_test_service.infrastructure.persistence import (
            api_test_repository as repo_mod,
        )

        repo = repo_mod.api_test_repository
        created = repo.create_api(dict(_FULL_FIELDS))
        api = repo.get_api(created.id)
        d = APICrudService._api_to_dict(api)

        assert d['vendor'] == 'volc_ast'
        assert d['description'] == 'INT-1364 回归'
        assert d['algorithm_type'] == 'voice_llm'
        assert d['meta'] == {'protocol': 'https', 'environment': 'testing',
                             'version': 'v2', 'apiKey': 'sk-test-1364'}
        assert d['default_max_process'] == 3
        assert d['default_max_timeout'] == 20
        assert d['default_max_audio_duration'] == 30
        assert len(d['endpoints']) == 1
        assert d['endpoints'][0]['endpoint'] == 'http://api.test.local/v1/asr'
        assert d['endpoints'][0]['name'] == 'ASR端点'
        assert d['endpoints'][0]['max_process'] == 2
        assert d['endpoints'][0]['max_timeout'] == 15
        assert d['endpoints'][0]['max_audio_duration'] == 25

    def test_list_aggregate_carries_fields(self, db):
        """列表聚合根同样承载业务字段，不再丢 vendor/meta/default_max_*。"""
        from api_test_service.infrastructure.persistence import (
            api_test_repository as repo_mod,
        )

        repo = repo_mod.api_test_repository
        repo.create_api(dict(_FULL_FIELDS))
        result = repo.list_apis(page=1, per_page=10)
        item = result['items'][0]
        assert item.vendor == 'volc_ast'
        assert item.meta.get('apiKey') == 'sk-test-1364'
        assert item.algorithm_type == 'voice_llm'
        assert item.default_max_process == 3
        assert len(item.api_endpoints) == 1

    def test_rename_save_preserves_persisted_fields(self, db,
                                                    neutralize_side_effects):
        """只改名称保存（回显值提交）后 DB meta/endpoints/default_max_* 不被抹。"""
        from api_test_service.application.api_crud_service import APICrudService
        from api_test_service.infrastructure.persistence import (
            api_test_repository as repo_mod,
        )

        repo = repo_mod.api_test_repository
        created = repo.create_api(dict(_FULL_FIELDS))
        echo = APICrudService._api_to_dict(repo.get_api(created.id))

        res = APICrudService.update(created.id, {
            'name': '接线测试_INT1364_apiC_renamed',
            'vendor': echo['vendor'],
            'description': echo['description'],
            'meta': echo['meta'],
            'algorithm_type': echo['algorithm_type'],
            'default_max_process': echo['default_max_process'],
            'default_max_timeout': echo['default_max_timeout'],
            'default_max_audio_duration': echo['default_max_audio_duration'],
            'endpoints': echo['endpoints'],
        })
        assert res['code'] == 200, res

        po = _get_api_po(db, created.id)
        assert po.name == '接线测试_INT1364_apiC_renamed'
        assert po.vendor == 'volc_ast'
        assert po.meta.get('apiKey') == 'sk-test-1364'
        assert po.algorithm_type == 'voice_llm'
        assert po.default_max_process == 3
        assert po.default_max_timeout == 20
        assert po.default_max_audio_duration == 30
        assert po.api_endpoints[0]['endpoint'] == 'http://api.test.local/v1/asr'
        assert po.api_endpoints[0]['name'] == 'ASR端点'

    def test_ddd_save_keeps_fields(self, db):
        """DDD save 路径：get_by_id 加载聚合根 → 改 name → save 不丢字段。"""
        from api_test_service.infrastructure.persistence import (
            api_test_repository as repo_mod,
        )

        repo = repo_mod.api_test_repository
        created = repo.create_api(dict(_FULL_FIELDS))
        agg = repo.get_by_id(created.id)
        agg.name = '接线测试_INT1364_save'
        repo.save(agg)

        po = _get_api_po(db, created.id)
        assert po.name == '接线测试_INT1364_save'
        assert po.vendor == 'volc_ast'
        assert po.meta.get('apiKey') == 'sk-test-1364'
        assert po.default_max_process == 3
        assert len(po.api_endpoints) == 1
