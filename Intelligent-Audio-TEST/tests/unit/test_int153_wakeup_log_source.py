# -*- coding: utf-8 -*-
"""INT-153 专项：唤醒/播放测试 _log source 关键字冲突回归锁定。

缺陷（INT-153）：DeviceCommandService._log / PlaybackCommandService._log 未声明
source 形参，调用方 source=f'Device:{name}' 落入 **kwargs，与 _log 内部硬编码传给
log_not_emit 的 source='backend' 同名冲突 → TypeError → 唤醒测试对任意设备必 400
（报错原文回传 Python 内部异常）。

覆盖：
- Device._log 对 source= 正确透传至 log_not_emit（category/module 同时校验）
- Device._log 缺省 source 仍为 'backend'（既有行为不回归）
- test() 成功路径：真实 _log 链路携带 source='Device:<设备名>'、category='DeviceTest'
- log_not_emit 同签名替身端到端：关键字冲突若回归必在调用点抛 TypeError（替身
  复刻 log_not_emit 真实形参表，解释器在调用点即做重复关键字检查，可锁死本缺陷；
  不触真实 DB handler，避免单测写库副作用）
- INT-206 口径：get_driver_for_device 抛 ValueError（真因）→ 400 携带真因
- Playback._log source= 透传 + stop_test 真实链路同样可用
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.application.commands.device_command_service import DeviceCommandService
from device_service.application.commands.playback_command_service import PlaybackCommandService

DEVICE_SVC = 'device_service.application.commands.device_command_service'
PLAYBACK_SVC = 'device_service.application.commands.playback_command_service'
FACTORY_TARGET = 'device_service.infrastructure.drivers.device_driver.device_driver_factory'


def real_signature_log_not_emit(level, module, content, category='system', source='backend',
                                task_id=None, device_id=None, api_id=None, test_case_id=None,
                                algorithm_type=None, push_to_websocket=False,
                                enable_console_log=None, **kwargs):
    """log_not_emit（shared/utils/log_handler/_api.py）的同形参替身。

    形参表与真实函数逐项一致：若 _log 再次把 source 同时落入位置参数默认值与
    **kwargs，解释器在本函数调用点即抛 TypeError（INT-153 原始缺陷形态）。
    """
    real_signature_log_not_emit.captured = dict(
        level=level, module=module, content=content, category=category, source=source,
        task_id=task_id, device_id=device_id, api_id=api_id, test_case_id=test_case_id,
        algorithm_type=algorithm_type, **kwargs)
    return None


real_signature_log_not_emit.captured = {}


def make_device(**overrides):
    return SimpleNamespace(
        id=1, name='测试设备', system='Android', keywords='android_base',
        serial_number='SN-001', ip='192.168.1.10', status='online',
        **overrides)


class FakeRepo:
    def __init__(self, device):
        self._device = device

    def get_device(self, device_id):
        return self._device


def make_online_factory():
    factory = MagicMock()
    scan_driver = MagicMock()
    scan_driver.scan.return_value = [{'serial': 'SN-001'}]
    factory.get_driver_by_system.return_value = scan_driver
    wake_driver = MagicMock()
    factory.get_driver_for_device.return_value = wake_driver
    return factory, wake_driver


# ---------- Device._log 直测 ----------

def test_device_log_passes_source_through():
    svc_module_log = MagicMock()
    with patch(f'{DEVICE_SVC}.log_not_emit', svc_module_log):
        DeviceCommandService._log('INFO', '内容', source='Device:客厅音箱')
    assert svc_module_log.call_count == 1
    kwargs = svc_module_log.call_args.kwargs
    assert kwargs['source'] == 'Device:客厅音箱'
    assert kwargs['module'] == 'TestDevice'
    assert kwargs['category'] == 'execution'


def test_device_log_default_source_is_backend():
    svc_module_log = MagicMock()
    with patch(f'{DEVICE_SVC}.log_not_emit', svc_module_log):
        DeviceCommandService._log('INFO', '内容')
    kwargs = svc_module_log.call_args.kwargs
    assert kwargs['source'] == 'backend'


def test_wakeup_success_log_carries_device_source():
    factory, wake_driver = make_online_factory()
    svc = DeviceCommandService(repo=FakeRepo(make_device()))
    with patch(FACTORY_TARGET, factory), \
         patch(f'{DEVICE_SVC}.log_not_emit', real_signature_log_not_emit):
        result = svc.test(1)
    assert result['success'] is True
    assert result['message'] == '唤醒指令已发送，正在测试'
    assert result['code'] == 200
    wake_driver.unlock.assert_called_once_with('SN-001')
    captured = real_signature_log_not_emit.captured
    assert captured['source'] == 'Device:测试设备'
    assert captured['category'] == 'DeviceTest'
    assert captured['module'] == 'TestDevice'
    assert captured['device_id'] == 1


def test_wakeup_real_signature_no_keyword_conflict():
    """同签名替身 + 真实 _log + source= 实参：INT-153 的 TypeError 若回归必在此复现。"""
    with patch(f'{DEVICE_SVC}.log_not_emit', real_signature_log_not_emit):
        DeviceCommandService._log(
            'INFO', 'INT-153 回归探针',
            category='DeviceTest', source='Device:任意设备', device_id=1)
    assert real_signature_log_not_emit.captured['source'] == 'Device:任意设备'


def test_wakeup_valueerror_reason_passthrough():
    """INT-206 口径：get_driver_for_device 抛 ValueError（真因），400 携带真因。"""
    factory, _ = make_online_factory()
    factory.get_driver_for_device.side_effect = ValueError('不支持的设备系统: xxx')
    svc = DeviceCommandService(repo=FakeRepo(make_device()))
    with patch(FACTORY_TARGET, factory), \
         patch(f'{DEVICE_SVC}.log_not_emit', real_signature_log_not_emit):
        result = svc.test(1)
    assert result['success'] is False
    assert result['code'] == 400
    assert result['message'] == '唤醒测试失败: 不支持的设备系统: xxx'


# ---------- Playback ----------

def test_playback_log_passes_source_through():
    playback_module_log = MagicMock()
    with patch(f'{PLAYBACK_SVC}.log_not_emit', playback_module_log):
        PlaybackCommandService._log('INFO', '内容', source='Device:播放设备1')
    kwargs = playback_module_log.call_args.kwargs
    assert kwargs['source'] == 'Device:播放设备1'
    assert kwargs['module'] == 'Playback'
    assert kwargs['category'] == 'execution'


def test_playback_stop_test_source_link():
    device = SimpleNamespace(id=5, name='播放设备1', device_unique_id='pb-001')
    repo = MagicMock()
    repo.get_playback_device.return_value = device
    svc = PlaybackCommandService(repo=repo)
    with patch.object(svc, '_stop_audio_via_grpc'), \
         patch(f'{PLAYBACK_SVC}.log_not_emit', real_signature_log_not_emit):
        result = svc.stop_test(5)
    assert result['success'] is True
    assert result['code'] == 200
    captured = real_signature_log_not_emit.captured
    assert captured['source'] == 'Device:播放设备1'
    assert captured['category'] == 'DeviceTest'
    assert captured['module'] == 'Playback'
    assert captured['playback_device_id'] == 5
