# -*- coding: utf-8 -*-
"""hw_params 回复完成检测的纯逻辑自检(不连设备、不用 DB 夹具)"""
from backend.utils.device_driver.harmony_xiaoyichat import Xiaoyilivechat


def test_classify_hw_params():
    cls = Xiaoyilivechat._classify_hw_params
    # 正在回复: 播放流打开,输出参数
    assert cls("access: RW_INTERLEAVED\nformat: S24_LE\nsubformat: STD\n"
               "channels: 2\nrate: 48000 (48000/1)\nperiod_size: 960\n"
               "buffer_size: 1920\n") is True
    # 回复完成
    assert cls("closed\n") is False
    assert cls("closed") is False
    # 读取失败/无输出 → 未知
    assert cls("") is None
    assert cls(None) is None
    assert cls("   \n") is None


def test_wait_end_debounce_and_fallback(monkeypatch):
    drv = Xiaoyilivechat.__new__(Xiaoyilivechat)  # 跳过 __init__(不需要设备配置)
    drv._log = lambda **kw: None
    drv._check_stop = lambda name: False
    monkeypatch.setattr(drv, 'HW_PARAMS_CLOSED_CONFIRM', 3)
    monkeypatch.setattr(drv, 'HW_PARAMS_END_TIMEOUT', 30)
    # sleep 跳过,避免测试变慢
    monkeypatch.setattr('backend.utils.device_driver.harmony_xiaoyichat.time.sleep', lambda s: None)

    # 序列: 回复中×2 → 瞬时 closed×1(句间) → 回复中×1 → closed×3(结束)
    seq = iter([True, True, False, True, False, False, False])
    monkeypatch.setattr(drv, '_hw_params_replying', lambda sn: next(seq))
    assert drv._wait_ai_reply_end_via_hw_params('sn') is True

    # 连续 3 次读不到 → False(调用方回退 UI 法)
    monkeypatch.setattr(drv, '_hw_params_replying', lambda sn: None)
    assert drv._wait_ai_reply_end_via_hw_params('sn') is False


def test_stop_recorder_idempotent(monkeypatch):
    """aa start 录屏是 toggle 语义: 重复 stop 必须只 toggle 一次(防双开)"""
    drv = Xiaoyilivechat.__new__(Xiaoyilivechat)
    drv._recording = True
    calls = []
    monkeypatch.setattr(drv, '_hdc_shell', lambda *a, **kw: calls.append(a))
    assert drv._stop_recorder('sn') is True
    assert drv._stop_recorder('sn') is True   # teardown 兜底再调一次
    assert len(calls) == 1                     # 第二次被 _recording=False 挡掉
    assert drv._recording is False
    # 未录制时直接调也是 no-op
    assert drv._stop_recorder('sn') is True
    assert len(calls) == 1
