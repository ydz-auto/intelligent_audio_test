# -*- coding: utf-8 -*-
"""INT-68 补充验收测试（测试工程师）：真库落库 + servicer 全委托 + 网关路由层

开发自测（test_int68_api_rms_spl_foundation.py）中映射 CRUD/校准/spl_to_gain
走内存假仓储、servicer 委托仅覆盖 GetRmsSplMapping 单点、网关层未测。本文件补：

1. 真实 SQLAlchemy 落库链路（SQLite 临时文件库 + 真实 ApiRmsSplRepositoryImpl
   + 真实 DistributedLock 降级路径）：验收「api_rms_spl_mappings 落库并与 API
   关联」「apis 扩展列落库」「执行期 spl_to_gain 与校准点一致」
2. gRPC ApiRmsSplConfigServiceServicer 8 个 RPC 全量委托断言（CRUD 全 gRPC）
3. api_gateway /api/v1/digital-spl 路由层：RBAC 依赖、404/409 错误映射
   （最小 FastAPI app + 真实 router + 假 ACL）
"""
import os
import tempfile

# BaseConfig 在 import 时校验必填环境变量（本文件不触网不触真实 Redis）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

import pytest

import shared.models.database as database
from shared.models.common_enums import CalibrationStatus


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建本卡两张表。"""
    from sqlalchemy import create_engine

    from api_test_service.infrastructure.persistence.models.api_models import (
        API,
        ApiRmsSplMappingPO,
    )

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(
        engine, tables=[API.__table__, ApiRmsSplMappingPO.__table__])
    yield database
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


# ==================== 1a. UC-0901：apis 扩展列真库落库 ====================

class TestApisNewColumnsPersistence:
    def _new_api(self, **kwargs):
        from api_test_service.infrastructure.persistence.models.api_models import API
        return API(name='ChatGPT Realtime', meta={'api_key': 'sk-x'}, **kwargs)

    def test_new_columns_roundtrip(self, db):
        from api_test_service.infrastructure.persistence.models.api_models import API
        session = db.get_db_session()
        try:
            po = self._new_api(
                device_type='websocket_api',
                adapter_class='OpenAIRealtimeAdapter',
                audio_config={'sample_rate': 24000, 'bit_depth': 's16',
                              'channels': 1, 'container': 'pcm'},
                output_types=['audio', 'text'],
            )
            session.add(po)
            session.commit()
            po_id = po.id
            session.expire_all()  # 强制从库里重读，排除同 session 身份映射假阳性
            row = session.query(API).filter(API.id == po_id).first()
            assert row.device_type == 'websocket_api'
            assert row.adapter_class == 'OpenAIRealtimeAdapter'
            assert row.audio_config == {'sample_rate': 24000, 'bit_depth': 's16',
                                        'channels': 1, 'container': 'pcm'}
            assert row.output_types == ['audio', 'text']
        finally:
            db.remove_db_session()

    def test_new_columns_defaults(self, db):
        from api_test_service.infrastructure.persistence.models.api_models import API
        session = db.get_db_session()
        try:
            po = self._new_api()
            session.add(po)
            session.commit()
            po_id = po.id
            session.expire_all()
            row = session.query(API).filter(API.id == po_id).first()
            assert row.device_type == 'http_api'
            assert row.output_types == []
            assert row.audio_config is None
            assert row.adapter_class is None
            assert row.rms_spl_mapping_id is None
        finally:
            db.remove_db_session()


# ==================== 1b. UC-0902：api_rms_spl_mappings 真实仓储落库 ====================

class TestRmsSplMappingPersistence:
    def test_create_and_get_roundtrip(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )
        repo = ApiRmsSplRepositoryImpl()
        created = repo.create_mapping({'api_id': 5, 'name': 'OpenAI 灵敏度校准',
                                       'vendor': 'openai'})
        assert created.id > 0
        m = repo.get_mapping(created.id)
        assert m is not None
        assert m.api_id == 5
        assert m.name == 'OpenAI 灵敏度校准'
        assert m.vendor == 'openai'
        assert m.calibration_status == CalibrationStatus.UNCALIBRATED.value
        assert m.reference_spl == pytest.approx(65.0)
        assert m.reference_gain_linear == pytest.approx(1.0)
        assert m.min_gain_linear == pytest.approx(0.001)
        assert m.max_gain_linear == pytest.approx(10.0)
        assert m.calibration_points == []

    def test_association_isolation_between_apis(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )
        repo = ApiRmsSplRepositoryImpl()
        a = repo.create_mapping({'api_id': 5, 'name': 'API5的映射'})
        b = repo.create_mapping({'api_id': 6, 'name': 'API6的映射'})
        ids5 = [m.id for m in repo.list_by_api(5)]
        ids6 = [m.id for m in repo.list_by_api(6)]
        assert a.id in ids5 and b.id not in ids5
        assert b.id in ids6 and a.id not in ids6

    def test_calibration_points_roundtrip(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )
        repo = ApiRmsSplRepositoryImpl()
        created = repo.create_mapping({'api_id': 5})
        updated = repo.update_mapping(created.id, {
            'calibration_status': CalibrationStatus.CALIBRATED.value,
            'calibration_data': {'points': [
                {'target_spl': 55.0, 'gain_linear': 0.5, 'rms_dbfs': -20.1},
                {'target_spl': 65.0, 'gain_linear': 1.0},
                {'target_spl': 75.0, 'gain_linear': 2.0},
            ]},
        })
        assert updated is not None and updated.id == created.id
        m = repo.get_mapping(created.id)
        assert m.calibration_status == CalibrationStatus.CALIBRATED.value
        assert [(p.target_spl, p.gain_linear) for p in m.calibration_points] == [
            (55.0, 0.5), (65.0, 1.0), (75.0, 2.0)]
        assert m.calibration_points[0].rms_dbfs == pytest.approx(-20.1)
        assert m.calibration_points[1].rms_dbfs is None

    def test_logical_delete(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )
        repo = ApiRmsSplRepositoryImpl()
        created = repo.create_mapping({'api_id': 5})
        assert repo.delete_mapping(created.id) is True
        assert repo.get_mapping(created.id) is None
        assert repo.list_by_api(5) == []
        assert repo.delete_mapping(created.id) is False  # 幂等：再删返回 False

    def test_default_mapping_pointer_priority(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )
        from api_test_service.infrastructure.persistence.models.api_models import API

        def _new_api(name):
            session = db.get_db_session()
            try:
                api = API(name=name, meta={}, device_type='http_api')
                session.add(api)
                session.commit()
                return api.id
            finally:
                db.remove_db_session()

        repo = ApiRmsSplRepositoryImpl()

        # 无指针：回退该 API 唯一一条映射
        api1 = _new_api('A1')
        m1 = repo.create_mapping({'api_id': api1, 'name': 'A1的映射'})
        assert repo.get_default_mapping(api1).id == m1.id

        # 有指针：指针指定项优先（即使它不是最新一条）
        api2 = _new_api('A2')
        m_old = repo.create_mapping({'api_id': api2, 'name': '旧映射'})
        repo.create_mapping({'api_id': api2, 'name': '新映射'})
        session = db.get_db_session()
        try:
            row = session.query(API).filter(API.id == api2).first()
            row.rms_spl_mapping_id = m_old.id
            session.commit()
        finally:
            db.remove_db_session()
        assert repo.get_default_mapping(api2).id == m_old.id

        # 无任何映射的 API：返回 None（执行期走线性近似回退）
        api3 = _new_api('A3')
        assert repo.get_default_mapping(api3) is None


# ==================== 1c. UC-0902：执行期 spl_to_gain 真库全链路 ====================

class TestSplGainRealDbChain:
    """真实仓储 + 真实 DistributedLock（无 Redis 降级放行）+ 应用服务"""

    POINTS = {'points': [
        {'target_spl': 55.0, 'gain_linear': 0.5},
        {'target_spl': 65.0, 'gain_linear': 1.0},
        {'target_spl': 75.0, 'gain_linear': 2.0},
    ]}

    def test_calibrate_then_gain_matches_points(self, db):
        from api_test_service.application.api_rms_spl_config_service import (
            ApiRmsSplConfigService,
        )
        service = ApiRmsSplConfigService()  # 缺省注入真实 ApiRmsSplRepositoryImpl
        created = service.create({'api_id': 5, 'name': '校准映射'})
        assert created['code'] == 201
        mapping_id = created['data']['id']

        res = service.calibrate(mapping_id, self.POINTS)
        assert res['code'] == 200
        assert res['data']['calibration_status'] == CalibrationStatus.CALIBRATED.value
        assert res['data']['is_calibrated'] is True

        # 真库回读 + 校准点精确命中
        assert service.get_spl_gain(5, 55.0)['data']['gain_linear'] == pytest.approx(0.5)
        assert service.get_spl_gain(5, 65.0)['data']['gain_linear'] == pytest.approx(1.0)
        assert service.get_spl_gain(5, 75.0)['data']['gain_linear'] == pytest.approx(2.0)
        # 点间线性插值
        assert service.get_spl_gain(5, 70.0)['data']['gain_linear'] == pytest.approx(1.5)

    def test_default_pointer_mapping_used_for_gain(self, db):
        """默认项指针生效：执行链路读 apis.rms_spl_mapping_id 指定映射的校准点"""
        from api_test_service.application.api_rms_spl_config_service import (
            ApiRmsSplConfigService,
        )
        from api_test_service.infrastructure.persistence.models.api_models import API
        service = ApiRmsSplConfigService()
        m_used = service.create({'api_id': 7, 'name': '指针指向的映射'})
        m_other = service.create({'api_id': 7, 'name': '更新的未校准映射'})
        service.calibrate(m_used['data']['id'],
                          {'points': [{'target_spl': 65.0, 'gain_linear': 2.5}]})

        session = db.get_db_session()
        try:
            api = API(name='A7', meta={}, rms_spl_mapping_id=m_used['data']['id'])
            session.add(api)
            session.commit()
            api_id = api.id
        finally:
            db.remove_db_session()

        # 默认项是被校准的 m_used（尽管 m_other 更新），增益 2.5 而非回退 1.0
        assert service.get_spl_gain(api_id, 65.0)['data']['gain_linear'] == pytest.approx(2.5)
        assert m_other['data']['id'] != m_used['data']['id']

    def test_unmapped_api_falls_back_to_linear_approx(self, db):
        from api_test_service.application.api_rms_spl_config_service import (
            ApiRmsSplConfigService,
        )
        service = ApiRmsSplConfigService()
        assert service.get_spl_gain(999, 65.0)['data']['gain_linear'] == pytest.approx(1.0)
        assert service.get_spl_gain(999, 85.0)['data']['gain_linear'] == pytest.approx(10.0)


# ==================== 2. gRPC servicer 8 RPC 全量委托 ====================

class _RecordingService:
    """记录调用参数的假 application 服务，按预设返回"""

    def __init__(self, result=None):
        self.calls = []
        self._result = result or {'success': True, 'message': 'ok',
                                  'data': {'id': 1}, 'code': 200}

    def create(self, data):
        self.calls.append(('create', data))
        return self._result

    def update(self, mapping_id, data):
        self.calls.append(('update', mapping_id, data))
        return self._result

    def delete(self, mapping_id):
        self.calls.append(('delete', mapping_id))
        return self._result

    def get_all(self, **kwargs):
        self.calls.append(('get_all', kwargs))
        return self._result

    def get_one(self, mapping_id):
        self.calls.append(('get_one', mapping_id))
        return self._result

    def get_by_api(self, api_id):
        self.calls.append(('get_by_api', api_id))
        return self._result

    def calibrate(self, mapping_id, calibration_data):
        self.calls.append(('calibrate', mapping_id, calibration_data))
        return self._result

    def set_default(self, api_id, mapping_id):
        self.calls.append(('set_default', api_id, mapping_id))
        return self._result


class TestServicerDelegationAllRpcs:
    def _servicer(self):
        from api_test_service.interfaces.grpc.servicers import (
            ApiRmsSplConfigServiceServicer,
        )
        servicer = ApiRmsSplConfigServiceServicer()
        fake = _RecordingService()
        servicer._config_service = fake
        return servicer, fake

    def test_all_eight_rpcs_delegate(self):
        from types import SimpleNamespace

        servicer, fake = self._servicer()

        r = servicer.CreateRmsSplMapping(SimpleNamespace(data='{"api_id": 5, "name": "x"}'))
        assert r.success and r.data
        r = servicer.UpdateRmsSplMapping(SimpleNamespace(mapping_id=3, data='{"name": "y"}'))
        assert r.success
        r = servicer.DeleteRmsSplMapping(SimpleNamespace(mapping_id=3))
        assert r.success
        r = servicer.ListRmsSplMappings(SimpleNamespace(page=2, per_page=20, api_id=5,
                                                        calibration_status='calibrated'))
        assert r.success
        r = servicer.GetRmsSplMapping(SimpleNamespace(mapping_id=3))
        assert r.success
        r = servicer.GetRmsSplMappingsByApi(SimpleNamespace(api_id=5))
        assert r.success
        r = servicer.CalibrateRmsSplMapping(SimpleNamespace(
            mapping_id=3, calibration_data='{"points": [{"target_spl": 65, "gain_linear": 1.0}]}'))
        assert r.success
        r = servicer.SetDefaultRmsSplMapping(SimpleNamespace(api_id=5, mapping_id=0))
        assert r.success  # mapping_id=0 → None（清除默认项）

        assert fake.calls == [
            ('create', {'api_id': 5, 'name': 'x'}),
            ('update', 3, {'name': 'y'}),
            ('delete', 3),
            ('get_all', {'page': 2, 'per_page': 20, 'api_id': 5,
                         'calibration_status': 'calibrated'}),
            ('get_one', 3),
            ('get_by_api', 5),
            ('calibrate', 3, {'points': [{'target_spl': 65, 'gain_linear': 1.0}]}),
            ('set_default', 5, None),
        ]

    def test_servicer_swallows_exception_into_success_false(self):
        from types import SimpleNamespace

        servicer, _ = self._servicer()

        def _boom(*a, **k):
            raise RuntimeError('grpc payload boom')

        servicer._config_service = SimpleNamespace(get_one=_boom)
        resp = servicer.GetRmsSplMapping(SimpleNamespace(mapping_id=3))
        assert resp.success is False
        assert 'grpc payload boom' in resp.message


# ==================== 3. 网关 /api/v1/digital-spl 路由层 ====================

class _FakeAcl:
    """记录调用并按脚本返回 CommandResultDTO 的假 ACL"""

    def __init__(self):
        self.calls = []
        self.script = {}

    def _ret(self, key, data=None):
        from api_gateway.domain.dto import CommandResultDTO
        spec = self.script.get(key, (True, 'ok', data, 200))
        return CommandResultDTO(success=spec[0], message=spec[1],
                                data=spec[2], code=spec[3])

    def create(self, data):
        self.calls.append(('create', data))
        return self._ret('create', {'id': 1})

    def update(self, mapping_id, data):
        self.calls.append(('update', mapping_id, data))
        return self._ret('update')

    def delete(self, mapping_id):
        self.calls.append(('delete', mapping_id))
        return self._ret('delete')

    def calibrate(self, mapping_id, calibration_data):
        self.calls.append(('calibrate', mapping_id, calibration_data))
        return self._ret('calibrate')

    def set_default(self, api_id, mapping_id):
        self.calls.append(('set_default', api_id, mapping_id))
        return self._ret('set_default')

    def get_all(self, **kwargs):
        self.calls.append(('get_all', kwargs))
        return self._ret('get_all', {'items': [], 'total': 0})

    def get_one(self, mapping_id):
        self.calls.append(('get_one', mapping_id))
        return self._ret('get_one', {'id': mapping_id})

    def get_by_api(self, api_id):
        self.calls.append(('get_by_api', api_id))
        return self._ret('get_by_api', {'items': [], 'total': 0})


@pytest.fixture()
def digital_spl_client(monkeypatch):
    """最小 FastAPI app + 真实 digital_spl 路由 + 真实 RequestAdapterMiddleware
    （JSON body 预解析，与生产一致）+ 假 ACL + 权限注入薄中间件。

    x-test-perms 头模拟 AuthMiddleware 注入 request.state.permissions
    （AUTH_MODE=off 时注入 ['*'] 的等价物）；缺省为空 → 403。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware

    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes.digital_spl_bp import router as digital_spl_router
    import api_gateway.application.services.api_rms_spl.rms_spl_command_service as cmd_mod
    import api_gateway.application.services.api_rms_spl.rms_spl_query_service as query_mod

    fake = _FakeAcl()
    monkeypatch.setattr(cmd_mod, '_rms_spl_acl', fake)
    monkeypatch.setattr(query_mod, '_rms_spl_acl', fake)

    app = FastAPI()
    app.include_router(digital_spl_router, prefix='/api/v1/digital-spl')

    class _TestPermMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            perms = request.headers.get('x-test-perms', '')
            request.state.permissions = [p for p in perms.split(',') if p]
            return await call_next(request)

    # add_middleware 后加的在外层：权限注入 → JSON 预解析+ContextVar → 路由
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(_TestPermMiddleware)

    return TestClient(app, raise_server_exceptions=False), fake


class TestDigitalSplRoutes:
    def test_crud_roundtrip_with_permission(self, digital_spl_client):
        client, fake = digital_spl_client
        headers = {'x-test-perms': 'digital_spl:create,digital_spl:read,digital_spl:update,digital_spl:delete'}

        resp = client.post('/api/v1/digital-spl', json={
            'api_id': 5, 'name': '映射A', 'reference_spl': 70.0,
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        assert resp.json()['success'] is True
        assert fake.calls[-1] == ('create', {'api_id': 5, 'name': '映射A', 'reference_spl': 70.0})

        resp = client.get('/api/v1/digital-spl/by-api/5', headers=headers)
        assert resp.status_code == 200
        assert fake.calls[-1] == ('get_by_api', 5)

        resp = client.put('/api/v1/digital-spl/3', json={'name': '改名'}, headers=headers)
        assert resp.status_code == 200
        assert fake.calls[-1] == ('update', 3, {'name': '改名'})

        resp = client.delete('/api/v1/digital-spl/3', headers=headers)
        assert resp.status_code == 200
        assert fake.calls[-1] == ('delete', 3)

    def test_calibrate_conflict_maps_to_409(self, digital_spl_client):
        """并发校准互斥：微服务 409 → 网关 HTTP 409 + ErrorCode.CONFLICT(204)"""
        client, fake = digital_spl_client
        fake.script['calibrate'] = (False, 'API 5 正在执行校准，请稍后再试', None, 409)
        resp = client.post('/api/v1/digital-spl/3/calibrate', json={
            'calibration_data': {'points': [{'target_spl': 65, 'gain_linear': 1.0}]},
        }, headers={'x-test-perms': 'digital_spl:create'})
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body['success'] is False
        assert body['code'] == 204  # ErrorCode.CONFLICT
        assert '正在执行校准' in body['message']

    def test_get_one_not_found_maps_to_404(self, digital_spl_client):
        client, fake = digital_spl_client
        fake.script['get_one'] = (False, '未找到映射记录', None, 404)
        resp = client.get('/api/v1/digital-spl/999',
                          headers={'x-test-perms': 'digital_spl:read'})
        assert resp.status_code == 404
        assert resp.json()['code'] == 201  # ErrorCode.NOT_FOUND

    def test_missing_permission_rejected_403(self, digital_spl_client):
        client, fake = digital_spl_client
        resp = client.post('/api/v1/digital-spl', json={'api_id': 5})
        assert resp.status_code == 403
        assert fake.calls == []  # 未触达 ACL

    def test_invalid_body_rejected_without_acl_call(self, digital_spl_client):
        client, fake = digital_spl_client
        resp = client.post('/api/v1/digital-spl', json={'name': '缺 api_id'},
                           headers={'x-test-perms': 'digital_spl:create'})
        assert resp.status_code == 400
        assert resp.json()['success'] is False
        assert fake.calls == []

    def test_set_default_routes_to_acl(self, digital_spl_client):
        client, fake = digital_spl_client
        resp = client.post('/api/v1/digital-spl/by-api/5/set-default',
                           json={'mapping_id': 3},
                           headers={'x-test-perms': 'digital_spl:update'})
        assert resp.status_code == 200
        assert fake.calls[-1] == ('set_default', 5, 3)


# ==================== 4. 真链路端到端：真实 servicer→gRPC→proxy（审计问题1） ====================
# 审计指出：信封 code 在 gRPC 边界丢失，此前 409 断言用假 ACL 注入掩盖了断链。
# 本节用进程内真实 gRPC server + 真实 pb2 序列化 + 真实应用服务/仓储，
# 验证业务码（200/201/404/409）经 servicer 透传后由代理 _envelope 正确还原。

@pytest.fixture()
def live_grpc_channel(db, monkeypatch):
    """真实 ApiRmsSplConfigServiceServicer 挂进程内 gRPC server（随机端口），
    网关代理的 stub 工厂指向该 server——完整走真实 pb2 序列化链路。"""
    import grpc
    from concurrent import futures

    from api_test_service.interfaces.grpc.servicers import ApiRmsSplConfigServiceServicer
    from shared.proto import api_test_service_pb2_grpc as pb_grpc
    from api_gateway.infrastructure.grpc_proxies import api_rms_spl_proxies

    servicer = ApiRmsSplConfigServiceServicer()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_ApiRmsSplConfigServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')
    monkeypatch.setattr(api_rms_spl_proxies, 'get_api_rms_spl_config_service_stub',
                        lambda: pb_grpc.ApiRmsSplConfigServiceStub(channel))
    yield channel
    channel.close()
    server.stop(grace=None)


class TestEnvelopeCodeEndToEnd:
    def test_create_and_calibrate_codes_passthrough(self, live_grpc_channel):
        from api_gateway.infrastructure.grpc_proxies import api_rms_spl_config_service as proxy

        created = proxy.create({'api_id': 5, 'name': 'e2e'})
        assert created['success'] is True
        assert created['code'] == 201  # 成功业务码 201 经真实 pb2 透传
        mapping_id = created['data']['id']

        res = proxy.calibrate(mapping_id, {'points': [
            {'target_spl': 55, 'gain_linear': 0.5},
            {'target_spl': 75, 'gain_linear': 2.0},
        ]})
        assert res['success'] is True
        assert res['code'] == 200

        # 真库写读回：点集与请求一致（全量替换语义经真实链路生效）
        by_api = proxy.get_by_api(5)
        assert by_api['code'] == 200
        pts = by_api['data']['items'][0]['calibration_points']
        assert [(p['target_spl'], p['gain_linear']) for p in pts] == [(55.0, 0.5), (75.0, 2.0)]

    def test_calibrate_conflict_409_end_to_end(self, live_grpc_channel, monkeypatch):
        """并发校准互斥 409 经真实 servicer→proxy 链透传（不再降级 400）"""
        from api_gateway.infrastructure.grpc_proxies import api_rms_spl_config_service as proxy
        from api_test_service.application import api_rms_spl_config_service as app_mod

        created = proxy.create({'api_id': 6, 'name': 'e2e-conflict'})
        mapping_id = created['data']['id']

        class _HeldLock:
            def __init__(self, key, **kwargs):
                pass

            def acquire(self, blocking=True):
                return False

            def release(self):
                pass

        monkeypatch.setattr(app_mod, 'DistributedLock', _HeldLock)
        res = proxy.calibrate(mapping_id, {'points': [{'target_spl': 65, 'gain_linear': 1.0}]})
        assert res['success'] is False
        assert res['code'] == 409
        assert '正在执行校准' in res['message']

    def test_get_one_missing_404_end_to_end(self, live_grpc_channel):
        from api_gateway.infrastructure.grpc_proxies import api_rms_spl_config_service as proxy

        res = proxy.get_one(424242)
        assert res['success'] is False
        assert res['code'] == 404
        assert '未找到映射记录' in res['message']

    def test_legacy_servicer_without_code_falls_back(self, monkeypatch):
        """旧版本 servicer 响应无 code（0）：代理按 success 回退 200/400，向后兼容"""
        from api_gateway.infrastructure.grpc_proxies.api_rms_spl_proxies import _envelope
        from types import SimpleNamespace

        legacy_ok = _envelope(SimpleNamespace(success=True, message='ok', data='{"id": 1}', code=0))
        assert legacy_ok['code'] == 200
        legacy_fail = _envelope(SimpleNamespace(success=False, message='x', data='', code=0))
        assert legacy_fail['code'] == 400
