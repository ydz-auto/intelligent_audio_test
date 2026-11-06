# -*- coding: utf-8 -*-
"""INT-1747 / C2 守卫（第二次打回）：参数来源判定。

断点不在白名单，而在类型判定：
  ``algorithm_service.GetParam`` 先查 device 再回落 api，请求里不带来源；
  ``task_service.get_device_param`` 只看「返回非空」，于是任何 API 参数都能拿到，
  投影成 ``DeviceParamDTO`` 后 ``update_param`` 的 ``is_device`` 恒 True，
  新加的白名单分支永远进不去，P1 的 field_path 仍被静默丢弃；P2 详情读同理。

修法：``GetParam`` 响应带出 ``param_type_source``，ACL 按它判类型，不再跨表回落。
本文件用**真实** algorithm_service GetParam 逻辑 / 真实 task_service ACL mixin
（只替身 gRPC stub 与仓储写操作），避免上一轮「把 get_device_param 桩成 None」的假绿。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


# ==================== algorithm_service.GetParam 带出来源 ====================

class _FakeQueryHandler:
    """替身 handler：按 param_type_source 返回对应表的行（模拟两张表）。"""

    def __init__(self, rows):
        self._rows = rows

    def handle_get_param(self, query):
        row = self._rows.get(query.param_type_source)
        if row is None or row.get('id') != query.param_id:
            return None
        return dict(row)


def _algorithm_get_param_payload(rows, param_id):
    """直调真实 algorithm_service.GetParam，返回解析后的 payload（失败返回 None）。"""
    from shared.proto import algorithm_service_pb2 as algo_pb
    from algorithm_service.interfaces.grpc.mixins.param_query_mixin import (
        _ParamQueryMixin,
    )

    servicer = _ParamQueryMixin.__new__(_ParamQueryMixin)
    servicer.param_query_handler = _FakeQueryHandler(rows)
    resp = _ParamQueryMixin.GetParam(
        servicer, algo_pb.GetParamRequest(param_id=param_id)
    )
    if not resp.success:
        return None
    return json.loads(resp.data)


def test_algorithm_get_param_reports_api_source():
    payload = _algorithm_get_param_payload(
        {'api': {'id': 101, 'param_code': 'text',
                 'field_path': 'data.translation.text'}},
        101,
    )
    assert payload['param_type_source'] == 'api'
    assert payload['field_path'] == 'data.translation.text'


def test_algorithm_get_param_reports_device_source():
    payload = _algorithm_get_param_payload(
        {'device': {'id': 202, 'param_code': 'device_code'}}, 202
    )
    assert payload['param_type_source'] == 'device'


def test_algorithm_get_param_device_first_on_same_id():
    """同 id 两表都有：沿用 device 优先，来源如实报告，不静默混表。"""
    payload = _algorithm_get_param_payload(
        {'device': {'id': 29, 'param_code': 'device_code'},
         'api': {'id': 29, 'param_code': 'text'}},
        29,
    )
    assert payload['param_type_source'] == 'device'
    assert payload['param_code'] == 'device_code'


def test_algorithm_get_param_missing_returns_failure():
    assert _algorithm_get_param_payload({'api': {'id': 1}}, 999) is None


# ==================== task_service ACL 按来源判类型 ====================

class _FakeParamStub:
    """替身 gRPC stub：复刻 GetParam 的「先 device 再回落 api」真实语义。"""

    def __init__(self, *, device=None, api=None):
        self._device = dict(device) if device else None
        self._api = dict(api) if api else None
        self.calls = []

    def GetParam(self, request):
        from shared.proto import algorithm_service_pb2 as algo_pb
        self.calls.append(request.param_id)
        if self._device is not None and self._device.get('id') == request.param_id:
            payload = dict(self._device, param_type_source='device')
        elif self._api is not None and self._api.get('id') == request.param_id:
            payload = dict(self._api, param_type_source='api')
        else:
            return algo_pb.AlgorithmResponse(
                success=False, message='Parameter not found', data=''
            )
        return algo_pb.AlgorithmResponse(
            success=True, message='ok',
            data=json.dumps(payload, ensure_ascii=False),
        )


class _RealGetParamStub:
    """用**真实** algorithm_service.GetParam 实现构造的 stub：两层契约对接。

    ``_FakeParamStub`` 里的 ``param_type_source`` 是手写的；这里由真实 servicer
    序列化（grpc_json.dumps），ACL 侧用真实 ``_loads`` 解析，验证线上口径一致。
    """

    def __init__(self, rows):
        from algorithm_service.interfaces.grpc.mixins.param_query_mixin import (
            _ParamQueryMixin,
        )
        self._mixin = _ParamQueryMixin
        self._servicer = _ParamQueryMixin.__new__(_ParamQueryMixin)
        self._servicer.param_query_handler = _FakeQueryHandler(rows)

    def GetParam(self, request):
        return self._mixin.GetParam(self._servicer, request)


def _acl_repo(monkeypatch, stub):
    """真实 ACL mixin + 替身 stub 组装仓储（不连库，只记录下发字段）。"""
    from task_service.infrastructure.acl import algorithm_acl_param_mixin as mod

    monkeypatch.setattr(mod, '_get_stub', lambda: stub)

    class _Repo(mod.AlgorithmParamMixin):
        def __init__(self):
            self.sent_fields = None
            self.commits = 0

        def update_param_attrs(self, param, fields):
            self.sent_fields = fields

        def commit(self):
            self.commits += 1

    return _Repo()


def test_acl_api_param_is_not_projected_as_device(monkeypatch):
    """API 参数 id 经真实 GetParam 判定为 api，不再被投影成 DeviceParamDTO。"""
    from task_service.domain.dto.task_acl_dto import ApiParamDTO

    stub = _FakeParamStub(api={'id': 101, 'param_code': 'text',
                               'field_path': 'data.translation.text'})
    repo = _acl_repo(monkeypatch, stub)

    assert repo.get_device_param(101) is None
    api = repo.get_api_param(101)
    assert isinstance(api, ApiParamDTO)
    assert api.field_path == 'data.translation.text'


def test_acl_device_param_keeps_no_field_path(monkeypatch):
    from task_service.domain.dto.task_acl_dto import DeviceParamDTO

    stub = _FakeParamStub(device={'id': 202, 'param_code': 'device_code'})
    repo = _acl_repo(monkeypatch, stub)

    assert repo.get_api_param(202) is None
    device = repo.get_device_param(202)
    assert isinstance(device, DeviceParamDTO)
    assert not hasattr(device, 'field_path')


def test_acl_collision_id_stays_device(monkeypatch):
    """主库 29/30/31 两表同 id：GetParam device 优先，api 身份仍不可达（既有问题不动）。"""
    stub = _FakeParamStub(
        device={'id': 29, 'param_code': 'device_code'},
        api={'id': 29, 'param_code': 'text', 'field_path': 'data.translation.text'},
    )
    repo = _acl_repo(monkeypatch, stub)

    assert repo.get_api_param(29) is None
    assert repo.get_device_param(29).param_code == 'device_code'


# ==================== 全链：UpdateParam / GetParam ====================

def test_acl_consumes_real_get_param_payload(monkeypatch):
    """真实 GetParam 序列化 → 真实 ACL 解析：API 行取到 field_path，设备行不被误认。"""
    rows = {
        'api': {'id': 101, 'algorithm_type': 'voice_llm', 'param_code': 'text',
                'direction': 'output', 'field_path': 'data.translation.text'},
        'device': {'id': 202, 'algorithm_type': 'asr',
                   'param_code': 'device_code', 'direction': 'input'},
    }
    repo = _acl_repo(monkeypatch, _RealGetParamStub(rows))

    assert repo.get_device_param(101) is None
    assert repo.get_api_param(101).field_path == 'data.translation.text'
    assert repo.get_api_param(202) is None
    assert repo.get_device_param(202).param_code == 'device_code'


def test_update_param_full_chain_sends_field_path_via_real_acl(monkeypatch):
    """P1 全链：UpdateParamRequest → servicer → 白名单 → 真实 ACL 来源判定 → 下发字段。"""
    from shared.proto import task_service_pb2 as task_pb
    from task_service.application.algorithm.algorithm_param_crud_service import (
        AlgorithmParamCrudService,
    )
    from task_service.interfaces.grpc.algorithm_config import (
        AlgorithmConfigServiceServicer,
    )

    stub = _FakeParamStub(api={'id': 101, 'algorithm_type': 'voice_llm',
                               'param_code': 'text', 'direction': 'output'})
    repo = _acl_repo(monkeypatch, stub)

    svc = AlgorithmParamCrudService.__new__(AlgorithmParamCrudService)
    svc.repo = repo
    servicer = AlgorithmConfigServiceServicer()
    servicer._svc = svc

    resp = servicer.UpdateParam(task_pb.UpdateParamRequest(
        param_id=101,
        data=json.dumps({'fieldPath': 'data.translation.text', 'uiOrder': 9}),
    ))

    assert resp.success is True
    assert repo.sent_fields == {'field_path': 'data.translation.text', 'ui_order': 9}


def test_update_param_full_chain_ignores_field_path_for_device(monkeypatch):
    from task_service.application.algorithm.algorithm_param_crud_service import (
        AlgorithmParamCrudService,
    )

    stub = _FakeParamStub(device={'id': 202, 'algorithm_type': 'asr',
                                  'param_code': 'device_code',
                                  'direction': 'input'})
    repo = _acl_repo(monkeypatch, stub)
    svc = AlgorithmParamCrudService.__new__(AlgorithmParamCrudService)
    svc.repo = repo

    result = svc.update_param(
        202, {'field_path': 'data.translation.text', 'ui_order': 3}
    )

    assert result['success'] is True
    assert repo.sent_fields == {'ui_order': 3}


def test_get_param_detail_full_chain_returns_field_path(monkeypatch):
    """P2 全链：GET 参数详情经真实 ACL 返回 ApiParamDTO，序列化后含 field_path。"""
    from task_service.application.algorithm.algorithm_param_query_service import (
        AlgorithmParamQueryService,
    )

    stub = _FakeParamStub(api={'id': 101, 'algorithm_type': 'voice_llm',
                               'param_code': 'text', 'direction': 'output',
                               'field_path': 'data.translation.text'})
    repo = _acl_repo(monkeypatch, stub)
    svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
    svc.repo = repo

    result = svc.get_param(101)

    assert result['success'] is True
    assert result['data']['field_path'] == 'data.translation.text'
    assert result['data']['param_code'] == 'text'
