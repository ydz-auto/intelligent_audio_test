# -*- coding: utf-8 -*-
"""INT-2577：设备 UI 探索驱动层三方法 + 真实 gRPC 回环。

补充 ``test_int2577_device_ui_servicer.py``（servicer 层）之下的驱动层验证：

- ``BaseDeviceDriver`` 默认三方法必须显式抛 ``PLATFORM_NOT_SUPPORTED``（不返回空树）；
- Android（uiautomator2）/ HarmonyOS（hypium UiTree）覆写的取树 / 七动作 / 截图；
- 真 gRPC server + stub 进程内回环（临时端口，不占常驻端口、不连真机）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
import re

import pytest

from shared.proto import device_service_pb2 as pb
from shared.proto import device_service_pb2_grpc as pb_grpc
from shared.constants.ui_capture import (
    UiActionType,
    UiCaptureDegradeReason,
    UiCaptureErrorCode,
    UiCaptureUnavailable,
    UiElementNotFound,
    UiTreeFormat,
)
from device_service.infrastructure.drivers import driver_constants as dc

SN = 'INT2577_SN_5SM0125701000999'
SCREENSHOT_KEY_RE = re.compile(r'^device-ui/' + re.escape(SN) + r'/\d+-\w{8}\.png$')


# ---------------------------------------------------------------- 桩件


class _FakeUiObject:
    def exists(self, timeout=0):
        return True

    def bounds(self):
        class _B:
            left, top, width, height = 0, 0, 100, 100
        return _B()


class _FakeU2Device:
    def __init__(self, xml='<hierarchy><node text="a"/><node text="b"/></hierarchy>'):
        self.xml = xml
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(('select', kwargs))
        return _FakeUiObject()

    def dump_hierarchy(self):
        return self.xml

    def click(self, x, y):
        self.calls.append(('click', x, y))

    def long_click(self, x, y, duration=0.5):
        self.calls.append(('long_click', x, y, duration))

    def send_keys(self, text):
        self.calls.append(('send_keys', text))

    def press(self, key):
        self.calls.append(('press', key))

    def sleep(self, seconds):
        self.calls.append(('sleep', seconds))

    def window_size(self):
        return 1080, 2400

    def swipe(self, fx, fy, tx, ty, duration=None):
        self.calls.append(('swipe', fx, fy, tx, ty, duration))


class _FakeUiTree:
    def __init__(self, layout):
        self.layout = layout
        self.dumped_to = None

    def dump_to_file(self, path):
        self.dumped_to = path
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.layout, f)
        return path


class _FakeHarmonyUiDriver:
    def __init__(self, layout):
        self.UiTree = _FakeUiTree(layout)
        self.clicked = self.long_clicked = self.inputted = self.slid = None
        self.backed = self.homed = False
        self.waited = None

    def get_display_size(self):
        return 1260, 2720

    def find_component(self, selector):
        return 'component'

    def click(self, target):
        self.clicked = target

    def long_click(self, target, press_time=2):
        self.long_clicked = (target, press_time)

    def input_text(self, component, text):
        self.inputted = (component, text)

    def slide(self, start, end, slide_time=0.3):
        self.slid = (start, end, slide_time)

    def press_back(self):
        self.backed = True

    def press_home(self):
        self.homed = True

    def wait(self, seconds):
        self.waited = seconds


# ---------------------------------------------------------------- 基类默认实现


def test_base_driver_defaults_explicitly_unsupported():
    """未覆写的驱动必须显式抛 PLATFORM_NOT_SUPPORTED，绝不返回空树冒充成功。"""
    from device_service.infrastructure.drivers.base_driver import BaseDeviceDriver
    driver = BaseDeviceDriver()
    for call in (lambda: driver.dump_ui_tree(SN),
                 lambda: driver.perform_ui_action(SN, 'TAP'),
                 lambda: driver.capture_ui_screenshot(SN)):
        with pytest.raises(UiCaptureUnavailable) as excinfo:
            call()
        assert excinfo.value.reason == UiCaptureDegradeReason.PLATFORM_NOT_SUPPORTED.value


# ---------------------------------------------------------------- Android 驱动


def _android_driver(monkeypatch, u2_device):
    from device_service.infrastructure.drivers.android_driver import AndroidDriver
    driver = AndroidDriver()
    monkeypatch.setattr(driver, '_get_driver', lambda sn: u2_device)
    return driver


def test_android_driver_dump_tree_reports_format_and_node_count(monkeypatch):
    driver = _android_driver(monkeypatch, _FakeU2Device())
    tree = driver.dump_ui_tree(SN)
    assert tree['platform'] == 'ANDROID'
    assert tree['format'] == UiTreeFormat.ANDROID_XML.value
    assert tree['node_count'] == 2
    assert '<hierarchy' in tree['payload']


def test_android_driver_unavailable_is_explicit(monkeypatch):
    driver = _android_driver(monkeypatch, None)
    with pytest.raises(UiCaptureUnavailable) as excinfo:
        driver.dump_ui_tree(SN)
    assert excinfo.value.reason == UiCaptureDegradeReason.DRIVER_UNAVAILABLE.value


def test_android_driver_empty_hierarchy_never_succeeds(monkeypatch):
    driver = _android_driver(monkeypatch, _FakeU2Device(xml=''))
    with pytest.raises(UiCaptureUnavailable) as excinfo:
        driver.dump_ui_tree(SN)
    assert excinfo.value.reason == UiCaptureDegradeReason.TREE_UNREADABLE.value


def test_android_driver_seven_actions_dispatched(monkeypatch):
    fake = _FakeU2Device()
    driver = _android_driver(monkeypatch, fake)
    node = {'resource_id': 'com.demo:id/btn', 'text': '登录', 'bounds': [10, 20, 110, 220]}
    for action in [a.value for a in UiActionType]:
        driver.perform_ui_action(SN, action, node=node,
                                 params={'text': 'hi', 'direction': 'up', 'seconds': 0})
    kinds = [c[0] for c in fake.calls]
    # 顺序：TAP / LONG_PRESS / SWIPE / INPUT_TEXT / BACK / HOME / WAIT
    assert kinds == ['select', 'click', 'select', 'long_click', 'swipe',
                     'select', 'click', 'send_keys', 'press', 'press', 'sleep']


def test_android_driver_unresolved_target_is_element_not_found(monkeypatch):
    """定位不到元素必须显式 ELEMENT_NOT_FOUND，不静默成功。"""
    driver = _android_driver(monkeypatch, _FakeU2Device())
    monkeypatch.setattr(driver, '_resolve_ui_target',
                        lambda d, s, n: (_ for _ in ()).throw(
                            UiElementNotFound('未定位到目标元素')))
    with pytest.raises(UiElementNotFound):
        driver.perform_ui_action(SN, 'TAP', node={})


def test_android_driver_screenshot_png(monkeypatch):
    from PIL import Image
    image = Image.new('RGB', (12, 34), color='white')

    class _ShotDevice(_FakeU2Device):
        def screenshot(self, format='pillow'):
            assert format == 'pillow'
            return image

    driver = _android_driver(monkeypatch, _ShotDevice())
    shot = driver.capture_ui_screenshot(SN)
    assert shot['format'] == 'PNG'
    assert (shot['width'], shot['height']) == (12, 34)
    assert shot['png'].startswith(b'\x89PNG')


# ---------------------------------------------------------------- HarmonyOS 驱动


def _harmony_driver(monkeypatch, ui_driver):
    from device_service.infrastructure.drivers import harmony_driver as hd
    driver = hd.HarmonyDriver()
    monkeypatch.setattr(hd, 'UiDriver', object())  # 视为 hypium 可用
    monkeypatch.setattr(driver, '_get_driver', lambda sn: ui_driver)
    return driver


def test_harmony_driver_dump_tree_flattens_layout(monkeypatch):
    layout = {
        'attributes': {'type': 'root', 'bounds': '[0,0][1260,2720]'},
        'children': [
            {'attributes': {'type': 'Text', 'text': '登录',
                            'id': 'login_btn', 'bounds': '[0,0][100,100]'}},
        ],
    }
    driver = _harmony_driver(monkeypatch, _FakeHarmonyUiDriver(layout))
    tree = driver.dump_ui_tree(SN)
    assert tree['platform'] == 'HARMONYOS'
    assert tree['format'] == UiTreeFormat.HARMONY_COMPONENTS.value
    assert tree['node_count'] == 2
    components = json.loads(tree['payload'])
    assert components[0]['type'] == 'root'
    assert components[0]['children'][0]['id'] == 'login_btn'


def test_harmony_driver_missing_hypium_is_explicit(monkeypatch):
    from device_service.infrastructure.drivers import harmony_driver as hd
    driver = hd.HarmonyDriver()
    monkeypatch.setattr(hd, 'UiDriver', None)
    with pytest.raises(UiCaptureUnavailable) as excinfo:
        driver.dump_ui_tree(SN)
    assert excinfo.value.reason == UiCaptureDegradeReason.HYPIUM_MISSING.value


def test_harmony_driver_seven_actions_dispatched(monkeypatch):
    fake = _FakeHarmonyUiDriver({})
    driver = _harmony_driver(monkeypatch, fake)
    node = {'resource_id': 'login_btn'}
    for action in [a.value for a in UiActionType]:
        driver.perform_ui_action(SN, action, node=node,
                                 params={'text': 'hi', 'direction': 'up',
                                         'seconds': dc.UI_EXPLORE_WAIT_MAX_SECONDS + 5})
    assert fake.clicked == 'component'
    assert fake.long_clicked[0] == 'component'
    assert fake.inputted == ('component', 'hi')
    assert fake.slid[0] != fake.slid[1]
    assert fake.backed and fake.homed
    # 超过上限的 WAIT 被截断到上限（防止挂死请求）
    assert fake.waited == dc.UI_EXPLORE_WAIT_MAX_SECONDS


def test_flatten_layout_keeps_attribute_names():
    """只做结构解包：属性名原样保留，归一化留给 agent 侧 parse_harmony_components。"""
    from device_service.infrastructure.drivers.harmony_driver import HarmonyDriver
    out = []
    HarmonyDriver._flatten_layout_node(
        {'attributes': {'type': 'Button', 'text': 'ok', 'clickable': 'true'},
         'children': [{'attributes': {'type': 'Text', 'text': 'x'}}]}, out)
    assert out[0]['type'] == 'Button'
    assert out[0]['clickable'] == 'true'
    assert out[0]['children'][0]['text'] == 'x'


# ---------------------------------------------------------------- 真实 gRPC 回环


class _LoopQuery:
    def __init__(self, device):
        self.device = device

    def get_one(self, device_id):
        return {'success': True, 'message': 'ok', 'data': dict(self.device), 'code': 200}


class _LoopFactory:
    def __init__(self, driver):
        self.driver = driver

    def get_driver_for_device(self, system, keywords=None, device_sn=None):
        return self.driver


class _LoopOSS:
    def __init__(self):
        self.keys = []

    def upload_bytes(self, data, category, key, content_type=None):
        self.keys.append(key)
        return key


class _LoopDriver:
    def __init__(self):
        self.actions = []

    def dump_ui_tree(self, device_sn, **kwargs):
        return {'platform': 'ANDROID', 'format': UiTreeFormat.ANDROID_XML.value,
                'payload': '<hierarchy><node text="a"/></hierarchy>', 'node_count': 1}

    def perform_ui_action(self, device_sn, action_type, *, node=None, params=None):
        self.actions.append(action_type)
        return {'action_type': action_type, 'performed': True}

    def capture_ui_screenshot(self, device_sn, **kwargs):
        return {'png': b'\x89PNG\r\n\x1a\nx', 'format': 'PNG',
                'width': 1080, 'height': 2400}


def test_grpc_loopback_roundtrip():
    """真 gRPC 通道 + stub 回环：证明 proto / servicer / 信封在线上一致。"""
    from concurrent import futures
    import grpc
    from device_service.interfaces.grpc.device_ui_servicers import DeviceUiServiceServicer

    driver = _LoopDriver()
    oss = _LoopOSS()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_DeviceUiServiceServicer_to_server(
        DeviceUiServiceServicer(
            query=_LoopQuery({'id': 1, 'system': 'Android',
                              'keywords': 'android.base.v1',
                              'serial_number': SN}),
            factory=_LoopFactory(driver), oss_client=oss),
        server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')
    try:
        stub = pb_grpc.DeviceUiServiceStub(channel)

        tree = stub.DumpUiTree(pb.DumpUiTreeRequest(device_id=1), timeout=10)
        assert tree.success is True
        tree_data = json.loads(tree.data)
        assert tree_data['format'] == UiTreeFormat.ANDROID_XML.value
        assert tree_data['node_count'] == 1

        act = stub.PerformUiAction(
            pb.PerformUiActionRequest(device_id=1, action_type='TAP',
                                      node='{"resource_id": "x"}'), timeout=10)
        assert act.success is True
        assert json.loads(act.data)['action_type'] == 'TAP'

        bad = stub.PerformUiAction(
            pb.PerformUiActionRequest(device_id=1, action_type='SCROLL'), timeout=10)
        assert bad.success is False
        assert bad.code == UiCaptureErrorCode.ACTION_NOT_ALLOWED.value

        shot = stub.CaptureUiScreenshot(
            pb.CaptureUiScreenshotRequest(device_id=1, label='a1'), timeout=10)
        assert shot.success is True
        ref = json.loads(shot.data)['screenshot_ref']
        assert SCREENSHOT_KEY_RE.match(ref)
        assert oss.keys == [ref]
        assert driver.actions == ['TAP']
    finally:
        channel.close()
        server.stop(0)
