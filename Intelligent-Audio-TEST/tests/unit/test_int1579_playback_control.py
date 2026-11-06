# -*- coding: utf-8 -*-
"""INT-1579 播放设备 重启 / 重置配置 / 诊断 / 修复 端点（契约 §2.1/§2.2/§2.5）。

进程内打桩，不触 gRPC / 真实 DB / Redis：

1. device_service 应用层：404 / 409 守卫、restart 在线与不可枚举两支、
   reset-config 探测与「不动声压映射」、diagnosis 固定 6 项与 unsupported 口径、
   repair 白名单与 reopen-channel 复用 restart。
2. api_gateway HTTP 契约：路由注册 + 权限 403 + 后端 404/409/400 → HTTP 状态码映射
   （最小 FastAPI 应用 + TestClient，进程内 ASGI，不起端口）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import types  # noqa: E402

import pytest  # noqa: E402

from device_service.application.commands.playback_command_service import PlaybackCommandService  # noqa: E402
from device_service.application.queries.playback_query_service import PlaybackQueryService  # noqa: E402
from shared.models.common_enums import (  # noqa: E402
    PlaybackDiagnosisKey,
    PlaybackDiagnosisStatus,
    PlaybackRepairAction,
)

BUSY_MESSAGE = '设备正在执行测试，禁止执行该操作'

# 物理枚举结果：两个通道（同一 device_index=0），硬件默认采样率 44100
PHYSICAL_DEVICES = [
    {'unique_id': 'Speakers (RME Fireface 802) [Ch 1]', 'device_index': 0,
     'channel_index': 0, 'sample_rate': 44100, 'host_api': 'Windows WASAPI'},
    {'unique_id': 'Speakers (RME Fireface 802) [Ch 2]', 'device_index': 0,
     'channel_index': 1, 'sample_rate': 44100, 'host_api': 'Windows WASAPI'},
]
UNIQUE_ID = 'Speakers (RME Fireface 802) [Ch 1]'


# ── 桩 ────────────────────────────────────────────────────────────

class _FakeRepo:
    def __init__(self, device):
        self.device = device
        self.updates = []

    def get_playback_device(self, device_id):
        return self.device if self.device and self.device.id == device_id else None

    def update_playback_device(self, device_id, update_fields):
        self.updates.append(dict(update_fields))
        for key, value in update_fields.items():
            setattr(self.device, key, value)
        return self.device


class _FakeEvents:
    def __init__(self):
        self.events = []

    def record_status_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


def _make_device(**overrides):
    data = dict(
        id=11, name='接线测试_播放设备', device_type='dry',
        device_unique_id=UNIQUE_ID, channel_index=0, sample_rate=48000,
        status='online', current_spl_mapping_id=5,
    )
    data.update(overrides)
    return types.SimpleNamespace(**data)


def _patch_world(monkeypatch, *, device_index=0, physical=PHYSICAL_DEVICES, available=True,
                 busy=False, events=None):
    """统一打桩：设备索引 / 停播 / 物理枚举 / operation 事件 / 运行中任务守卫"""
    monkeypatch.setattr(PlaybackCommandService, '_get_device_index_via_grpc',
                        staticmethod(lambda unique_id: device_index))
    monkeypatch.setattr(PlaybackCommandService, '_stop_audio_via_grpc',
                        staticmethod(lambda task_id: True))

    import device_service.infrastructure.acl.audio_service_acl_repository as acl_module
    monkeypatch.setattr(acl_module.audio_service_acl_repository, 'enumerate_physical_devices',
                        lambda: (list(physical), available))

    import device_service.infrastructure.acl.task_acl_repository as task_acl_module
    monkeypatch.setattr(task_acl_module.task_acl_repository, 'has_running_e2e_tasks',
                        lambda: busy)

    event_sink = events if events is not None else _FakeEvents()
    import device_service.application.services.device_monitor_service as monitor_module
    monkeypatch.setattr(monitor_module.device_monitor_service, 'record_status_event',
                        event_sink.record_status_event)
    return event_sink


# ── 1. 404 / 409 守卫 ─────────────────────────────────────────────

def test_restart_unknown_device_404(monkeypatch):
    _patch_world(monkeypatch)
    svc = PlaybackCommandService(repo=_FakeRepo(None), spl_repo=None)

    result = svc.restart(999)

    assert result['code'] == 404 and result['message'] == '未找到播放设备'


@pytest.mark.parametrize('call', ['restart', 'reset_config', 'repair'])
def test_control_endpoints_blocked_when_busy(monkeypatch, call):
    """运行中 E2E 任务 → 三个控制动作均 409 且不改设备状态"""
    events = _patch_world(monkeypatch, busy=True)
    device = _make_device(status='offline')
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    payload = {'actions': [PlaybackRepairAction.RE_ENUMERATE.value]} if call == 'repair' else None
    result = getattr(svc, call)(11, payload) if payload else getattr(svc, call)(11)

    assert result['success'] is False and result['code'] == 409
    assert result['message'] == BUSY_MESSAGE
    assert repo.updates == [], '守卫命中时不得写设备'
    assert events.events == [], '守卫命中时不得落 operation 事件'
    assert device.status == 'offline'


@pytest.mark.parametrize('call', ['restart', 'reset_config', 'repair'])
def test_not_found_wins_over_busy_guard(monkeypatch, call):
    """卡面「id 不存在 → 404」：不存在的 id 即便有运行中任务也返回 404"""
    _patch_world(monkeypatch, busy=True)
    svc = PlaybackCommandService(repo=_FakeRepo(None), spl_repo=None)

    payload = {'actions': [PlaybackRepairAction.RE_ENUMERATE.value]} if call == 'repair' else None
    result = getattr(svc, call)(999, payload) if payload else getattr(svc, call)(999)

    assert result['code'] == 404 and result['message'] == '未找到播放设备'


# ── 2. restart ────────────────────────────────────────────────────

def test_restart_online_resolves_index_and_records_operation_event(monkeypatch):
    events = _patch_world(monkeypatch, device_index=3)
    device = _make_device(status='offline')
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.restart(11)

    assert result['code'] == 200 and result['success'] is True
    assert result['data'] == {'id': 11, 'status': 'online', 'device_index': 3}
    assert repo.updates == [{'status': 'online'}]
    assert len(events.events) == 1
    event = events.events[0]
    assert event['event_type'] == 'operation'
    assert event['detail']['operation'] == 'restart'
    assert event['to_status'] == 'online'
    # 文案边界：音频通道层重开，不是硬件重启
    assert result['message'] == '已重新连接音频通道'
    assert '设备已重启' not in result['message']


def test_restart_offline_when_not_enumerable(monkeypatch):
    events = _patch_world(monkeypatch, device_index=None, physical=[], available=True)
    device = _make_device(status='online')
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.restart(11)

    assert result['code'] == 200
    assert result['data'] == {'id': 11, 'status': 'offline', 'device_index': None}
    assert result['message'] == '设备不可枚举，已标记离线'
    assert repo.updates == [{'status': 'offline'}]
    assert events.events[0]['detail']['operation'] == 'restart'
    assert events.events[0]['to_status'] == 'offline'


# ── 3. reset-config ───────────────────────────────────────────────

def test_reset_config_aligns_sample_rate_and_keeps_spl_mapping(monkeypatch):
    _patch_world(monkeypatch)
    device = _make_device(sample_rate=48000, channel_index=0, current_spl_mapping_id=5)
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.reset_config(11)

    assert result['code'] == 200
    assert result['data'] == {'id': 11, 'changed': {'sample_rate': 44100}, 'status': 'online'}
    assert result['message'] == '配置已按硬件重新探测'
    assert repo.updates == [{'sample_rate': 44100}]
    # 关键回归点：声压映射关联不得被清除
    assert 'current_spl_mapping_id' not in repo.updates[0]
    assert device.current_spl_mapping_id == 5


def test_reset_config_second_call_is_noop(monkeypatch):
    _patch_world(monkeypatch)
    device = _make_device(sample_rate=48000, channel_index=0)
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    first = svc.reset_config(11)
    second = svc.reset_config(11)

    assert first['data']['changed'] == {'sample_rate': 44100}
    assert second['data']['changed'] == {}
    assert second['message'] == '配置与硬件一致，无变化'
    assert repo.updates == [{'sample_rate': 44100}], '第二次无变化不得再写库'


def test_reset_config_not_enumerable_409(monkeypatch):
    _patch_world(monkeypatch, physical=[], available=False)
    repo = _FakeRepo(_make_device())
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.reset_config(11)

    assert result['code'] == 409
    assert result['message'] == '设备不可枚举，无法探测配置'
    assert repo.updates == []


def test_reset_config_status_only_change_records_operation_event(monkeypatch):
    """配置已一致、仅补正在线状态：也要落 operation 事件，且文案说明状态变化"""
    events = _patch_world(monkeypatch)
    device = _make_device(status='offline', sample_rate=44100, channel_index=0)
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.reset_config(11)

    assert result['code'] == 200
    assert result['data']['changed'] == {}
    assert result['data']['status'] == 'online'
    assert '状态已更新为 online' in result['message']
    assert repo.updates == [{'status': 'online'}]
    assert len(events.events) == 1
    assert events.events[0]['detail']['operation'] == 'reset-config'
    assert events.events[0]['from_status'] == 'offline'
    assert events.events[0]['to_status'] == 'online'


# ── 4. diagnosis ──────────────────────────────────────────────────

def _diagnosis_items(query, device_id=11):
    result = query.diagnosis(device_id)
    assert result['code'] == 200, result
    items = result['data']['items']
    assert result['data']['checkedAt']
    return {item['key']: item for item in items}


def test_diagnosis_returns_fixed_six_items(monkeypatch):
    _patch_world(monkeypatch)
    device = _make_device(sample_rate=44100, status='online', current_spl_mapping_id=None)
    query = PlaybackQueryService(repo=_FakeRepo(device), spl_repo=None)

    items = _diagnosis_items(query)

    assert list(items) == [k.value for k in PlaybackDiagnosisKey]
    legal = {s.value for s in PlaybackDiagnosisStatus}
    for item in items.values():
        assert item['status'] in legal, item
        assert item['label'] and item['detail'], item
    # 未关联声压映射 → warn + 建议
    assert items['spl_mapping']['status'] == PlaybackDiagnosisStatus.WARN.value
    assert items['spl_mapping']['suggestion']
    assert items['sample_rate']['status'] == PlaybackDiagnosisStatus.OK.value
    assert items['channel_index']['status'] == PlaybackDiagnosisStatus.OK.value
    assert items['enumerable']['status'] == PlaybackDiagnosisStatus.OK.value
    assert items['busy']['status'] == PlaybackDiagnosisStatus.OK.value


def test_diagnosis_not_enumerable_is_error(monkeypatch):
    _patch_world(monkeypatch, physical=[], available=True)
    query = PlaybackQueryService(repo=_FakeRepo(_make_device(status='offline')), spl_repo=None)

    items = _diagnosis_items(query)

    assert items['enumerable']['status'] == PlaybackDiagnosisStatus.ERROR.value
    assert items['enumerable']['suggestion']
    assert items['status']['status'] == PlaybackDiagnosisStatus.WARN.value


def test_diagnosis_missing_device_does_not_blame_audio_service(monkeypatch):
    """枚举可用但没枚举到该设备：不得写「音频服务不可用」，建议指向连接检查与重启（P2-1）"""
    _patch_world(monkeypatch, physical=[], available=True)
    query = PlaybackQueryService(repo=_FakeRepo(_make_device(status='offline')), spl_repo=None)

    items = _diagnosis_items(query)

    assert items['enumerable']['status'] == PlaybackDiagnosisStatus.ERROR.value
    assert '未在物理设备枚举中找到该设备' in items['enumerable']['detail']
    for key in ('channel_index', 'sample_rate'):
        item = items[key]
        assert item['status'] != PlaybackDiagnosisStatus.OK.value
        assert '音频服务不可用' not in item['detail'], item
        assert 'audio_service' not in (item['suggestion'] or ''), item
        assert '未在物理设备枚举中找到该设备' in item['detail']
        assert '重启' in (item['suggestion'] or '')


def test_diagnosis_matches_channel_by_device_channel_index(monkeypatch):
    """同标识多通道时按 channel_index 区分（P3-5：参数不得是死参数）"""
    # 同一标识的两个通道，硬件采样率不同，据此判定选中的是哪条
    same_name_devices = [
        {'unique_id': 'Speakers (RME Fireface 802)', 'device_index': 0,
         'channel_index': 0, 'sample_rate': 44100, 'host_api': 'Windows WASAPI'},
        {'unique_id': 'Speakers (RME Fireface 802)', 'device_index': 0,
         'channel_index': 1, 'sample_rate': 48000, 'host_api': 'Windows WASAPI'},
    ]
    _patch_world(monkeypatch, physical=same_name_devices)
    device = _make_device(device_unique_id='Speakers (RME Fireface 802)',
                          channel_index=1, sample_rate=48000, status='online')
    query = PlaybackQueryService(repo=_FakeRepo(device), spl_repo=None)

    items = _diagnosis_items(query)

    # 匹配到 channel 1（采样率 48000）而不是 candidates[0]（44100）
    assert items['channel_index']['status'] == PlaybackDiagnosisStatus.OK.value
    assert items['sample_rate']['status'] == PlaybackDiagnosisStatus.OK.value


def test_diagnosis_unsupported_when_enumeration_unavailable(monkeypatch):
    """枚举不可用必须 unsupported（不是 error），避免噪声告警。"""
    _patch_world(monkeypatch, physical=[], available=False)
    query = PlaybackQueryService(repo=_FakeRepo(_make_device()), spl_repo=None)

    items = _diagnosis_items(query)

    for key in ('enumerable', 'channel_index', 'sample_rate'):
        assert items[key]['status'] == PlaybackDiagnosisStatus.UNSUPPORTED.value, items[key]
        assert items[key]['suggestion']
    assert items['enumerable']['status'] != PlaybackDiagnosisStatus.ERROR.value


def test_diagnosis_unknown_device_404(monkeypatch):
    _patch_world(monkeypatch)
    query = PlaybackQueryService(repo=_FakeRepo(None), spl_repo=None)

    assert query.diagnosis(404)['code'] == 404


# ── 5. repair ─────────────────────────────────────────────────────

def test_repair_runs_both_actions_and_reopen_matches_restart(monkeypatch):
    events = _patch_world(monkeypatch, device_index=2)
    device = _make_device(status='offline')
    repo = _FakeRepo(device)
    svc = PlaybackCommandService(repo=repo, spl_repo=None)
    actions = [PlaybackRepairAction.RE_ENUMERATE.value, PlaybackRepairAction.REOPEN_CHANNEL.value]

    result = svc.repair(11, {'actions': actions})

    assert result['code'] == 200 and result['success'] is True
    results = result['data']['results']
    assert [r['action'] for r in results] == actions
    assert all(r['success'] for r in results)
    assert device.status == 'online'
    # reopen-channel 复用 restart：落 restart 事件（与单点 restart 一致）
    operations = [e['detail']['operation'] for e in events.events]
    assert 'restart' in operations


def test_repair_unknown_action_400_lists_legal_values(monkeypatch):
    _patch_world(monkeypatch)
    repo = _FakeRepo(_make_device())
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    result = svc.repair(11, {'actions': ['reboot-hardware']})

    assert result['code'] == 400
    assert 'reboot-hardware' in result['message']
    assert 're-enumerate' in result['message'] and 'reopen-channel' in result['message']
    assert repo.updates == []


def test_repair_missing_actions_400(monkeypatch):
    _patch_world(monkeypatch)
    svc = PlaybackCommandService(repo=_FakeRepo(_make_device()), spl_repo=None)

    assert svc.repair(11, {})['code'] == 400
    assert svc.repair(11, None)['code'] == 400


def test_repair_partial_failure_reports_failure_not_completed(monkeypatch):
    """单个动作失败时不得返回 success=True + 「修复完成」（P3-4）"""
    _patch_world(monkeypatch, device_index=0)
    repo = _FakeRepo(_make_device(status='online'))
    svc = PlaybackCommandService(repo=repo, spl_repo=None)

    monkeypatch.setattr(
        PlaybackCommandService, '_re_enumerate',
        lambda self, dev: {'action': 're-enumerate', 'success': False,
                           'message': '重新扫描失败: audio grpc down'})

    result = svc.repair(11, {'actions': ['re-enumerate', 'reopen-channel']})

    assert result['success'] is False
    assert result['code'] == 400
    assert '修复完成' not in result['message']
    assert 're-enumerate' in result['message']
    assert [r['success'] for r in result['data']['results']] == [False, True]


# ── 6. 网关 HTTP 契约（路由 + 权限 + 状态码映射） ──────────────────

class _FakePlaybackAcl:
    """网关 ACL 桩：按预设信封返回，记录调用"""

    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.envelope
        return _call


def _gateway_client(monkeypatch, envelope):
    from api_gateway.domain.dto import CommandResultDTO
    dto = CommandResultDTO(**envelope) if isinstance(envelope, dict) else envelope
    fake = _FakePlaybackAcl(dto)

    import api_gateway.application.services.playback.playback_command_service as cmd_module
    import api_gateway.application.services.playback.playback_query_service as query_module
    monkeypatch.setattr(cmd_module, '_playback_acl', fake)
    monkeypatch.setattr(query_module, '_playback_acl', fake)

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
    return TestClient(app)


def test_gateway_routes_registered():
    from api_gateway.routes.playback_bp import router
    paths = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    assert ('/{device_id}/restart', ('POST',)) in paths
    assert ('/{device_id}/reset-config', ('POST',)) in paths
    assert ('/{device_id}/diagnosis', ('GET',)) in paths
    assert ('/{device_id}/repair', ('POST',)) in paths


def test_gateway_control_requires_control_permission(monkeypatch):
    client = _gateway_client(monkeypatch, {'success': True, 'message': 'ok',
                                           'data': {'id': 1, 'status': 'online'}, 'code': 200})

    resp = client.post('/api/v1/playback-devices/1/restart',
                       headers={'x-perms': 'playback:read'})

    assert resp.status_code == 403


def test_gateway_diagnosis_requires_read_permission(monkeypatch):
    client = _gateway_client(monkeypatch, {'success': True, 'message': 'ok',
                                           'data': {'items': []}, 'code': 200})

    resp = client.get('/api/v1/playback-devices/1/diagnosis', headers={'x-perms': ''})

    assert resp.status_code == 403


def test_gateway_busy_maps_409(monkeypatch):
    client = _gateway_client(monkeypatch, {'success': False, 'message': BUSY_MESSAGE,
                                           'data': None, 'code': 409})

    resp = client.post('/api/v1/playback-devices/1/restart',
                       headers={'x-perms': 'playback:control'})

    assert resp.status_code == 409
    assert resp.json()['message'] == BUSY_MESSAGE


def test_gateway_not_found_maps_404(monkeypatch):
    client = _gateway_client(monkeypatch, {'success': False, 'message': '未找到播放设备',
                                           'data': None, 'code': 404})

    resp = client.get('/api/v1/playback-devices/999/diagnosis',
                      headers={'x-perms': 'playback:read'})

    assert resp.status_code == 404
    assert resp.json()['message'] == '未找到播放设备'


def test_gateway_restart_success_passes_data_through(monkeypatch):
    data = {'id': 1, 'status': 'online', 'device_index': 2}
    client = _gateway_client(monkeypatch, {'success': True,
                                           'message': '已重新连接音频通道',
                                           'data': data, 'code': 200})

    resp = client.post('/api/v1/playback-devices/1/restart',
                       headers={'x-perms': 'playback:control'})

    assert resp.status_code == 200
    assert resp.json()['data'] == data


def test_gateway_repair_passes_actions_body(monkeypatch):
    fake_envelope = {'success': True, 'message': '修复完成',
                     'data': {'results': []}, 'code': 200}
    client = _gateway_client(monkeypatch, fake_envelope)

    resp = client.post('/api/v1/playback-devices/1/repair',
                       headers={'x-perms': 'playback:control'},
                       json={'actions': ['re-enumerate', 'reopen-channel']})

    assert resp.status_code == 200
    import api_gateway.application.services.playback.playback_command_service as cmd_module
    name, args, _ = cmd_module._playback_acl.calls[-1]
    assert name == 'repair' and args == (1, ['re-enumerate', 'reopen-channel'])


def test_gateway_repair_unknown_action_400(monkeypatch):
    client = _gateway_client(monkeypatch, {'success': False,
                                           'message': '不支持的修复动作: reboot，合法值: re-enumerate, reopen-channel',
                                           'data': None, 'code': 400})

    resp = client.post('/api/v1/playback-devices/1/repair',
                       headers={'x-perms': 'playback:control'},
                       json={'actions': ['reboot']})

    assert resp.status_code == 400
    assert 're-enumerate' in resp.json()['message']


def test_gateway_repair_partial_failure_maps_400_with_backend_message(monkeypatch):
    """部分动作失败：400 且 message 透出后端的「修复未完成」，不是「修复完成」"""
    message = '修复未完成: re-enumerate: 重新扫描失败: audio grpc down'
    client = _gateway_client(monkeypatch, {'success': False, 'message': message,
                                           'data': {'results': []}, 'code': 400})

    resp = client.post('/api/v1/playback-devices/1/repair',
                       headers={'x-perms': 'playback:control'},
                       json={'actions': ['re-enumerate']})

    assert resp.status_code == 400
    assert resp.json()['message'] == message
    assert '修复完成' not in resp.json()['message']
