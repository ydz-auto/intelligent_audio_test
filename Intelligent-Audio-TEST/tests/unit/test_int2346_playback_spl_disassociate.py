# -*- coding: utf-8 -*-
"""INT-2346 解除声压映射关联：PUT current_spl_mapping_id=null 不再被静默忽略。

选择方案 A（区分「字段缺省」与「显式 null」），不新增端点：
- device_service 写侧：仅 current_spl_mapping_id 的显式 null 表示清空引用，
  其它字段的 null 仍与缺省同义；对本来未关联的设备重复解除 = 成功且不写库。
- api_gateway 写侧：PlaybackUpdateSchema dump 的 exclude_none 会把显式 null
  一并抹掉，这里按「请求体是否真的带了该键」保留 null。

进程内打桩，不触 gRPC / 真实 DB / Redis。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import types  # noqa: E402

from device_service.application.commands.playback_command_service import PlaybackCommandService  # noqa: E402


# ── 桩 ────────────────────────────────────────────────────────────

class _FakeRepo:
    def __init__(self, device):
        self.device = device
        self.updates = []
        self.spl_ref_updates = []

    def get_playback_device(self, device_id):
        return self.device if self.device and self.device.id == device_id else None

    def update_playback_device(self, device_id, update_fields):
        self.updates.append(dict(update_fields))
        for key, value in update_fields.items():
            setattr(self.device, key, value)
        return self.device

    def update_playback_device_spl_ref(self, device_id, spl_mapping_id):
        self.spl_ref_updates.append(spl_mapping_id)
        self.device.current_spl_mapping_id = spl_mapping_id
        return True


class _FakeSplRepo:
    def __init__(self, mappings):
        self.mappings = {m.id: m for m in mappings}

    def get_spl_mapping(self, mapping_id):
        return self.mappings.get(mapping_id)


def _mapping(mapping_id, *, device_id=None, device_type='dry'):
    return types.SimpleNamespace(id=mapping_id, device_id=device_id, device_type=device_type)


def _make_device(**overrides):
    data = dict(
        id=46, name='INT2346_播放设备', device_type='dry',
        device_unique_id='INT2346_UNIQUE', channel_index=0, sample_rate=48000,
        status='online', description='原描述', current_spl_mapping_id=None,
    )
    data.update(overrides)
    return types.SimpleNamespace(**data)


def _service(device, mappings=None):
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=_FakeSplRepo(mappings or []))
    return svc, repo


# ── device_service：显式 null 解除关联 ─────────────────────────────

def test_explicit_null_clears_spl_mapping():
    device = _make_device(current_spl_mapping_id=7)
    svc, repo = _service(device)

    result = svc.update(46, {'current_spl_mapping_id': None})

    assert result['success'] is True and result['code'] == 200
    assert repo.updates == [{'current_spl_mapping_id': None}]
    assert device.current_spl_mapping_id is None


def test_absent_key_keeps_spl_mapping():
    device = _make_device(current_spl_mapping_id=7)
    svc, repo = _service(device)

    result = svc.update(46, {'name': 'INT2346_改名'})

    assert result['success'] is True
    assert repo.updates == [{'name': 'INT2346_改名'}]
    assert device.current_spl_mapping_id == 7


def test_null_for_other_fields_is_still_treated_as_not_provided():
    """其它字段的 null 与缺省同义：不误清空描述，也不影响同批的显式解除。"""
    device = _make_device(current_spl_mapping_id=7, description='原描述')
    svc, repo = _service(device)

    result = svc.update(46, {'name': 'INT2346_改名', 'description': None,
                             'current_spl_mapping_id': None})

    assert result['success'] is True
    assert repo.updates == [{'name': 'INT2346_改名', 'current_spl_mapping_id': None}]
    assert device.description == '原描述'
    assert device.current_spl_mapping_id is None


def test_disassociate_unassociated_device_is_idempotent_without_write():
    device = _make_device(current_spl_mapping_id=None)
    svc, repo = _service(device)

    result = svc.update(46, {'current_spl_mapping_id': None})

    assert result['success'] is True and result['code'] == 200
    assert repo.updates == []  # 无副作用：不再写库、不动 updated_at
    assert device.current_spl_mapping_id is None


def test_repeat_disassociate_after_clear_is_idempotent():
    device = _make_device(current_spl_mapping_id=7)
    svc, repo = _service(device)

    assert svc.update(46, {'current_spl_mapping_id': None})['success'] is True
    assert svc.update(46, {'current_spl_mapping_id': None})['success'] is True

    assert repo.updates == [{'current_spl_mapping_id': None}]


def test_associate_then_disassociate_then_reassociate_same_mapping():
    device = _make_device(current_spl_mapping_id=None)
    mapping = _mapping(9, device_id=None, device_type='dry')
    svc, repo = _service(device, mappings=[mapping])

    assert svc.associate_spl(46, {'spl_mapping_id': 9})['success'] is True
    assert device.current_spl_mapping_id == 9

    assert svc.update(46, {'current_spl_mapping_id': None})['success'] is True
    assert device.current_spl_mapping_id is None

    assert svc.associate_spl(46, {'spl_mapping_id': 9})['success'] is True
    assert device.current_spl_mapping_id == 9
    assert repo.spl_ref_updates == [9, 9]


def test_update_unknown_device_404():
    svc, repo = _service(None)

    result = svc.update(46, {'current_spl_mapping_id': None})

    assert result['success'] is False and result['code'] == 404
    assert repo.updates == []


# ── api_gateway：显式 null 穿过 schema dump ────────────────────────

class _FakePlaybackAcl:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []

    def update(self, device_id, data):
        self.calls.append(('update', (device_id, dict(data)), {}))
        return self.envelope


def _gateway_client(monkeypatch, envelope):
    from api_gateway.domain.dto import CommandResultDTO
    dto = CommandResultDTO(**envelope) if isinstance(envelope, dict) else envelope
    fake = _FakePlaybackAcl(dto)

    import api_gateway.application.services.playback.playback_command_service as cmd_module
    monkeypatch.setattr(cmd_module, '_playback_acl', fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware
    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes.playback_bp import router

    class _PermissionMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            header = request.headers.get('x-perms', '')
            request.state.permissions = [p for p in header.split(',') if p]
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(_PermissionMiddleware)
    app.include_router(router, prefix='/api/v1/playback-devices')
    return TestClient(app), fake


_OK = {'success': True, 'message': '播放设备信息更新成功', 'data': None, 'code': 200}


def test_gateway_put_explicit_null_reaches_acl(monkeypatch):
    client, fake = _gateway_client(monkeypatch, _OK)

    resp = client.put('/api/v1/playback-devices/46',
                      headers={'x-perms': 'playback:update'},
                      json={'current_spl_mapping_id': None})

    assert resp.status_code == 200
    name, args, _ = fake.calls[-1]
    assert name == 'update'
    assert args == (46, {'current_spl_mapping_id': None})


def test_gateway_put_without_key_does_not_send_spl_field(monkeypatch):
    client, fake = _gateway_client(monkeypatch, _OK)

    resp = client.put('/api/v1/playback-devices/46',
                      headers={'x-perms': 'playback:update'},
                      json={'name': 'INT2346_改名', 'sample_rate': 44100})

    assert resp.status_code == 200
    _, args, _ = fake.calls[-1]
    assert args == (46, {'name': 'INT2346_改名', 'sample_rate': 44100})
    assert 'current_spl_mapping_id' not in args[1]


def test_gateway_put_null_still_requires_update_permission(monkeypatch):
    client, fake = _gateway_client(monkeypatch, _OK)

    resp = client.put('/api/v1/playback-devices/46',
                      headers={'x-perms': 'playback:read'},
                      json={'current_spl_mapping_id': None})

    assert resp.status_code == 403
    assert fake.calls == []
