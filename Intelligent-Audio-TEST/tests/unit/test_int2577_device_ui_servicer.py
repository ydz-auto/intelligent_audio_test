# -*- coding: utf-8 -*-
"""INT-2577：设备 UI 探索 gRPC servicer 单测（mock 驱动，不连真机）。

覆盖卡面可测验收标准 1~5：

1. 七枚举逐个下发成功；非枚举值被拒 ``ACTION_NOT_ALLOWED``；平台不支持 /
   驱动异常 → 显式降级码；同 SN 并发第二次调用按 deadline 排队或 ``BUSY`` + 持锁快照。
2. 树 RPC：``format`` / ``node_count`` / ``payload`` 齐备；>8MB → ``TREE_TOO_LARGE``；
   不返回截断后的「假完整树」。
3. 截图 RPC：stub OSS 断言上传键形如 ``device-ui/<sn>/<ts>-<rand>.png`` 且返回该键。
4. proto 重生成后可导入，``_grpc_stubs`` 的 getter 可调用。
5. ``device.ui.action`` 结构化日志：每下发一个动作写一行（失败也写，带结果）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
import logging
import re
import threading
import time

import pytest

from shared.proto import device_service_pb2 as pb
from shared.constants.ui_capture import (
    UiActionType,
    UiCaptureDegradeReason,
    UiCaptureErrorCode,
    UiCaptureUnavailable,
    UiCapturePlatform,
    UiTreeFormat,
)
from shared.utils.grpc_json import loads as _loads
from device_service.interfaces.grpc import device_runtime_servicers as lock_mod
from device_service.interfaces.grpc.device_ui_servicers import (
    DeviceUiServiceServicer,
    device_ui_serial_section,
)

SN = 'INT2577_SN_5SM0125701000999'
SCREENSHOT_KEY_RE = re.compile(r'^device-ui/' + re.escape(SN) + r'/\d+-\w{8}\.png$')


@pytest.fixture(autouse=True)
def _clean_step_state():
    """锁表 / 持锁者 / 排队者是模块级按 SN 常驻，用例间必须清空。"""
    tables = (lock_mod._device_step_locks,
              lock_mod._device_step_holders,
              lock_mod._device_step_waiters)
    for table in tables:
        table.clear()
    yield
    for table in tables:
        table.clear()


# ---------------------------------------------------------------- 桩件


_UNSET = object()


class _FakeQuery:
    def __init__(self, device=_UNSET):
        self.device = {
            'id': 1, 'system': 'Android', 'keywords': 'android.base.v1',
            'serial_number': SN, 'name': 'INT2577 设备',
        } if device is _UNSET else device
        self.calls = []

    def get_one(self, device_id):
        self.calls.append(device_id)
        if self.device is None:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': dict(self.device), 'code': 200}


class _FakeFactory:
    def __init__(self, driver):
        self.driver = driver
        self.calls = []

    def get_driver_for_device(self, system, keywords=None, device_sn=None):
        self.calls.append((system, keywords, device_sn))
        if isinstance(self.driver, ValueError):
            raise self.driver
        return self.driver


class _FakeDriver:
    """记录调用并可按需抛 ``UiCaptureUnavailable`` / 返回指定树与截图。"""

    def __init__(self, *, tree=None, shot=None, action_error=None,
                 tree_error=None, shot_error=None):
        self.tree = tree or {
            'platform': UiCapturePlatform.ANDROID.value,
            'format': UiTreeFormat.ANDROID_XML.value,
            'payload': '<hierarchy><node text="登录" bounds="[0,0][10,10]" /></hierarchy>',
            'node_count': 1,
        }
        self.shot = shot if shot is not None else {
            'png': b'\x89PNG\r\n\x1a\nfake', 'format': 'PNG',
            'width': 1080, 'height': 2400,
        }
        self.action_error = action_error
        self.tree_error = tree_error
        self.shot_error = shot_error
        self.actions = []
        self.tree_calls = 0
        self.shot_calls = 0

    def dump_ui_tree(self, device_sn, **kwargs):
        self.tree_calls += 1
        if self.tree_error:
            raise self.tree_error
        return dict(self.tree)

    def perform_ui_action(self, device_sn, action_type, *, node=None, params=None):
        self.actions.append((device_sn, action_type, node, params))
        if self.action_error:
            raise self.action_error
        return {'action_type': action_type, 'performed': True}

    def capture_ui_screenshot(self, device_sn, **kwargs):
        self.shot_calls += 1
        if self.shot_error:
            raise self.shot_error
        return dict(self.shot)


class _FakeOSS:
    def __init__(self, fail=False):
        self.fail = fail
        self.uploads = []

    def upload_bytes(self, data, category, key, content_type=None):
        self.uploads.append({'data': data, 'category': category, 'key': key,
                             'content_type': content_type})
        if self.fail:
            raise RuntimeError('OSS 不可用')
        return key


def _servicer(driver=None, device=_UNSET, oss=None, query=None, factory=None):
    driver = driver or _FakeDriver()
    return DeviceUiServiceServicer(
        query=query if query is not None else _FakeQuery(device),
        factory=factory or _FakeFactory(driver),
        oss_client=oss or _FakeOSS(),
    ), driver


# ---------------------------------------------------------------- 读树 RPC


def test_dump_ui_tree_ok():
    servicer, driver = _servicer()
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is True
    assert resp.code == ''
    data = _loads(resp.data, {})
    assert data['platform'] == UiCapturePlatform.ANDROID.value
    assert data['format'] == UiTreeFormat.ANDROID_XML.value
    assert data['payload'].startswith('<hierarchy')
    assert data['node_count'] == 1
    assert data['degraded'] is False
    assert data['degrade_reason'] is None
    assert driver.tree_calls == 1


def test_dump_ui_tree_too_large_is_explicit_failure(monkeypatch):
    """>8MB 必须 TREE_TOO_LARGE，不得截断后冒充完整树。"""
    big = 'x' * (8 * 1024 * 1024 + 1)
    driver = _FakeDriver(tree={
        'platform': 'ANDROID', 'format': 'ANDROID_XML',
        'payload': big, 'node_count': 12345,
    })
    servicer, _ = _servicer(driver=driver)
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.TREE_TOO_LARGE.value
    data = _loads(resp.data, {})
    assert data['size_bytes'] > 8 * 1024 * 1024
    assert 'payload' not in data  # 不返回截断的「假完整树」


def test_dump_ui_tree_empty_payload_never_claims_success():
    driver = _FakeDriver(tree={'platform': 'ANDROID', 'format': 'ANDROID_XML',
                               'payload': None, 'node_count': 0})
    servicer, _ = _servicer(driver=driver)
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
    assert _loads(resp.data, {})['degraded'] is True


# ---------------------------------------------------------------- 动作 RPC


@pytest.mark.parametrize('action', [a.value for a in UiActionType])
def test_seven_action_types_dispatch(action):
    servicer, driver = _servicer()
    node = {'resource_id': 'com.demo:id/btn', 'bounds': [0, 0, 10, 10]}
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=1, action_type=action,
        node=json.dumps(node), params='{"text": "hello"}'))
    assert resp.success is True, resp.message
    data = _loads(resp.data, {})
    assert data['action_type'] == action
    assert data['performed'] is True
    assert isinstance(data['elapsed_ms'], int)
    assert driver.actions[-1][1] == action


def test_action_not_in_whitelist_rejected():
    servicer, driver = _servicer()
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=1, action_type='SCROLL'))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.ACTION_NOT_ALLOWED.value
    assert driver.actions == []  # 未下发到设备


def test_action_driver_degrade_reports_reason():
    driver = _FakeDriver(action_error=UiCaptureUnavailable(
        'hypium 缺失', reason=UiCaptureDegradeReason.HYPIUM_MISSING))
    servicer, _ = _servicer(driver=driver)
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=1, action_type='TAP'))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
    assert _loads(resp.data, {})['degrade_reason'] == \
        UiCaptureDegradeReason.HYPIUM_MISSING.value


def test_malformed_node_json_rejected():
    """node / params 非法 JSON 必须显式拒绝，不能抛未捕获异常或当空参数下发。"""
    servicer, driver = _servicer()
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=1, action_type='TAP', node='{not-json'))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.ACTION_NOT_ALLOWED.value
    assert driver.actions == []


def test_element_not_found_is_explicit():
    from shared.constants.ui_capture import UiElementNotFound
    driver = _FakeDriver(action_error=UiElementNotFound('未定位到目标元素'))
    servicer, _ = _servicer(driver=driver)
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=1, action_type='TAP'))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.ELEMENT_NOT_FOUND.value


def test_platform_not_supported_maps_platform_unsupported():
    """驱动默认实现（平台不支持）→ PLATFORM_UNSUPPORTED，而不是笼统的不可用。"""
    driver = _FakeDriver(tree_error=UiCaptureUnavailable(
        '未实现', reason=UiCaptureDegradeReason.PLATFORM_NOT_SUPPORTED))
    servicer, _ = _servicer(driver=driver)
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value


@pytest.mark.parametrize('system', ['iOS', 'Symbian', ''])
def test_unsupported_device_platform(system):
    servicer, driver = _servicer(device={
        'id': 1, 'system': system, 'keywords': 'x', 'serial_number': SN})
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value
    assert driver.tree_calls == 0


def test_device_not_found():
    servicer, _ = _servicer(query=_FakeQuery(device=None))
    resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
        device_id=999, action_type='TAP'))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.DEVICE_NOT_FOUND.value


def test_driver_resolution_error_is_capture_unavailable():
    servicer = DeviceUiServiceServicer(
        query=_FakeQuery(),
        factory=_FakeFactory(ValueError('未注册驱动 keywords: x')),
        oss_client=_FakeOSS())
    resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
    assert _loads(resp.data, {})['degrade_reason'] == \
        UiCaptureDegradeReason.DRIVER_UNAVAILABLE.value


# ---------------------------------------------------------------- 同 SN 串行


def _hold_sn_lock_in_thread(sn, action='initialize'):
    """在另一线程持有 SN 锁，返回 (thread, release_event)。"""
    release = threading.Event()
    acquired = threading.Event()

    def _hold():
        with device_ui_serial_section(sn, None, action):
            acquired.set()
            release.wait(timeout=10)

    thread = threading.Thread(target=_hold, daemon=True)
    thread.start()
    assert acquired.wait(timeout=5), '持锁线程未能取得 SN 锁'
    return thread, release


def test_same_sn_busy_with_holder_snapshot(monkeypatch):
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', 1, raising=False)
    servicer, driver = _servicer()
    thread, release = _hold_sn_lock_in_thread(SN)
    try:
        resp = servicer.DumpUiTree(pb.DumpUiTreeRequest(device_id=1))
    finally:
        release.set()
        thread.join(timeout=5)
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.BUSY.value
    data = _loads(resp.data, {})
    assert data['holder'].get('action') is not None
    assert data['waited_seconds'] >= 1
    assert driver.tree_calls == 0  # 未下发


def test_action_also_serialized_per_sn(monkeypatch):
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', 1, raising=False)
    servicer, driver = _servicer()
    thread, release = _hold_sn_lock_in_thread(SN)
    try:
        resp = servicer.PerformUiAction(pb.PerformUiActionRequest(
            device_id=1, action_type='BACK'))
    finally:
        release.set()
        thread.join(timeout=5)
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.BUSY.value
    assert driver.actions == []


def test_two_threads_serialized_not_concurrent():
    """同 SN 两个动作串行执行：第二个必须等第一个结束。"""
    order = []

    class _SlowDriver(_FakeDriver):
        def perform_ui_action(self, device_sn, action_type, *, node=None, params=None):
            order.append(('enter', action_type))
            time.sleep(0.2)
            order.append(('leave', action_type))
            return {'action_type': action_type, 'performed': True}

    servicer, _ = _servicer(driver=_SlowDriver())
    threads = [
        threading.Thread(target=servicer.PerformUiAction,
                         args=(pb.PerformUiActionRequest(device_id=1, action_type='TAP'),))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert order == [('enter', 'TAP'), ('leave', 'TAP'),
                     ('enter', 'TAP'), ('leave', 'TAP')]


# ---------------------------------------------------------------- 截图 RPC


def test_screenshot_uploads_object_key():
    oss = _FakeOSS()
    driver = _FakeDriver()
    servicer, _ = _servicer(driver=driver, oss=oss)
    resp = servicer.CaptureUiScreenshot(pb.CaptureUiScreenshotRequest(
        device_id=1, label='a3'))
    assert resp.success is True
    data = _loads(resp.data, {})
    assert SCREENSHOT_KEY_RE.match(data['screenshot_ref']), data['screenshot_ref']
    assert data['format'] == 'PNG'
    assert (data['width'], data['height']) == (1080, 2400)
    assert len(oss.uploads) == 1
    upload = oss.uploads[0]
    assert upload['key'] == data['screenshot_ref']
    assert upload['content_type'] == 'image/png'
    assert upload['data'] == b'\x89PNG\r\n\x1a\nfake'


def test_screenshot_empty_bytes_degraded():
    driver = _FakeDriver(shot={'png': b'', 'format': 'PNG', 'width': 0, 'height': 0})
    servicer, _ = _servicer(driver=driver)
    resp = servicer.CaptureUiScreenshot(pb.CaptureUiScreenshotRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
    assert _loads(resp.data, {})['degrade_reason'] == \
        UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE.value


def test_screenshot_upload_failure_degraded():
    servicer, _ = _servicer(oss=_FakeOSS(fail=True))
    resp = servicer.CaptureUiScreenshot(pb.CaptureUiScreenshotRequest(device_id=1))
    assert resp.success is False
    assert resp.code == UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
    assert _loads(resp.data, {})['degrade_reason'] == \
        UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE.value


# ---------------------------------------------------------------- 结构化日志


def test_action_log_one_line_per_dispatch(caplog):
    servicer, _ = _servicer()
    with caplog.at_level(logging.INFO):
        servicer.PerformUiAction(pb.PerformUiActionRequest(
            device_id=1, action_type='TAP'))
        servicer.PerformUiAction(pb.PerformUiActionRequest(
            device_id=1, action_type='HOME'))
    lines = [r for r in caplog.records if 'device.ui.action' in r.getMessage()]
    assert len(lines) == 2
    text = '\n'.join(r.getMessage() for r in lines)
    assert 'action_type=TAP' in text and 'action_type=HOME' in text
    assert 'result=performed' in text
    assert 'device_id=1' in text


def test_action_log_written_on_failure(caplog):
    driver = _FakeDriver(action_error=UiCaptureUnavailable(
        'hypium 缺失', reason=UiCaptureDegradeReason.HYPIUM_MISSING))
    servicer, _ = _servicer(driver=driver)
    with caplog.at_level(logging.INFO):
        servicer.PerformUiAction(pb.PerformUiActionRequest(
            device_id=1, action_type='TAP'))
    lines = [r for r in caplog.records if 'device.ui.action' in r.getMessage()]
    assert len(lines) == 1
    assert 'result=UI_CAPTURE_UNAVAILABLE' in lines[0].getMessage()


def test_action_log_written_when_rejected(caplog):
    servicer, _ = _servicer()
    with caplog.at_level(logging.INFO):
        servicer.PerformUiAction(pb.PerformUiActionRequest(
            device_id=1, action_type='SCROLL'))
    lines = [r for r in caplog.records if 'device.ui.action' in r.getMessage()]
    assert len(lines) == 1
    assert 'result=ACTION_NOT_ALLOWED' in lines[0].getMessage()


# ---------------------------------------------------------------- proto / stub


def test_proto_service_and_messages_regenerated():
    service = pb.DESCRIPTOR.services_by_name['DeviceUiService']
    assert set(service.methods_by_name) == {
        'DumpUiTree', 'PerformUiAction', 'CaptureUiScreenshot'}
    assert pb.DumpUiTreeRequest(device_id=3).device_id == 3
    resp = pb.PerformUiActionResponse(success=False, message='m',
                                      code=UiCaptureErrorCode.BUSY.value, data='{}')
    assert resp.code == 'BUSY'


def test_grpc_stub_getter_available():
    from shared.clients import _grpc_stubs
    stub = _grpc_stubs.get_device_ui_service_stub()
    assert type(stub).__name__ == 'DeviceUiServiceStub'
    for rpc in ('DumpUiTree', 'PerformUiAction', 'CaptureUiScreenshot'):
        assert callable(getattr(stub, rpc))
    # 懒加载单例
    assert _grpc_stubs.get_device_ui_service_stub() is stub


def test_server_registers_device_ui_servicer():
    """server.py 注册表包含 DeviceUiService（不真起服务，只校验注册调用）。"""
    import device_service.interfaces.grpc.server as server_mod
    src = open(server_mod.__file__, encoding='utf-8').read()
    assert 'add_DeviceUiServiceServicer_to_server' in src
