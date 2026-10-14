# -*- coding: utf-8 -*-
"""录音跨用例污染防护离线回归测试（VEGA-10）。

覆盖「用例↔录音 1:1 对应」修复中可离线验证的部分：
- 评估上传文件名契约（25bfd05d 演进后）：提取层保留原始可读名、不加随机前缀；
  唯一化收敛至 eval_server 落盘层——按用例分目录 uploads/<task_id>/<case_id>/，
  回退共享目录时加 12 位随机前缀（见 eval_server tests/test_api_storage_id.py）
- _recv_pcm 落盘时序：先写 *.part 临时文件，用例纪元校验通过后才原子替换；
  纪元变化（拉取期间用例已切换）时丢弃写入
- _pull_record_file / get_results 录屏名一致性校验：驱动状态属于别的用例时拒绝拉取
- _pick_pcm / _find_ai_pcm_remote 残留基线排除：清理失败的跨用例残留文件
  （size 未变化）不再被选中；size 增长的基线文件（本用例正在写）允许选取
- DoubaoChat/ChatGptVoiceChat initialize 补齐 _record_device_path 等状态复位
- _start_recorder 启动失败路径复位 _record_device_path
"""
import base64
import os
from types import SimpleNamespace

import pytest


# ──────────────────────────────────────────────
#  公共工具：构造不依赖真机的驱动实例
# ──────────────────────────────────────────────

def _make_xiaoyi_driver():
    from backend.utils.device_driver.harmony_xiaoyichat import Xiaoyilivechat

    driver = Xiaoyilivechat.__new__(Xiaoyilivechat)
    driver._log = lambda **kw: None
    driver._case_epoch = 'EPOCH-A'
    driver._pcm_baseline = {}
    return driver


def _make_doubao_driver():
    from backend.utils.device_driver.harmony_doubaochat import DoubaoChat

    driver = DoubaoChat.__new__(DoubaoChat)
    driver._log = lambda **kw: None
    driver._case_epoch = 'EPOCH-A'
    driver._pcm_baseline = {}
    return driver


# ──────────────────────────────────────────────
#  评估上传文件名：提取层保留原始可读名（唯一化收敛至落盘层）
# ──────────────────────────────────────────────

def test_upload_filename_preserves_original_basename(tmp_path):
    """提取层保留原始可读文件名（25bfd05d 契约）：同名录音提取名一致且为原名。

    跨用例防覆盖不再由后端加随机前缀；唯一化由 eval_server create_task_upload
    落盘时保证：按用例分目录 uploads/<task_id>/<case_id>/，回退共享目录时加
    12 位随机前缀（见 eval_server tests/test_api_storage_id.py）。
    """
    from backend.services.evaluation.api_request_handler import ApiRequestHandler

    # 模拟 4667/4721 两用例目录下的同名 wav（流槽位号批次重置导致重名）
    name = 'r1_100016_48000_2_1_client_in..wav'
    dir_a = tmp_path / '0d1bd2c0-case-4667'
    dir_b = tmp_path / 'e0a54917-case-4721'
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / name).write_bytes(b'AAAA')
    (dir_b / name).write_bytes(b'BBBB')

    files_a, files_b = {}, {}
    assert ApiRequestHandler._extract_single_file('rounds_1_ai_wav', str(dir_a / name), files_a)
    assert ApiRequestHandler._extract_single_file('rounds_1_ai_wav', str(dir_b / name), files_b)

    upload_name_a = files_a['rounds_1_ai_wav'][0]
    upload_name_b = files_b['rounds_1_ai_wav'][0]
    # 提取名 = 原始 basename，无任何随机前缀；同名输入提取名一致
    assert upload_name_a == name
    assert upload_name_b == name
    # 内容各归各（未串）
    assert files_a['rounds_1_ai_wav'][1] == b'AAAA'
    assert files_b['rounds_1_ai_wav'][1] == b'BBBB'


def test_upload_filename_data_uri_uses_field_name():
    """data URI 分支同样保留可读名：<field_name>.wav，后端不再加唯一前缀"""
    from backend.services.evaluation.api_request_handler import ApiRequestHandler

    payload = 'data:audio/wav;base64,' + base64.b64encode(b'RIFFxxxx').decode()
    files_a, files_b = {}, {}
    assert ApiRequestHandler._extract_single_file('rounds_0_ai_wav', payload, files_a)
    assert ApiRequestHandler._extract_single_file('rounds_0_ai_wav', payload, files_b)
    # 相同输入提取名一致且为 <field_name>.wav；唯一化由落盘层负责
    assert files_a['rounds_0_ai_wav'][0] == 'rounds_0_ai_wav.wav'
    assert files_b['rounds_0_ai_wav'][0] == 'rounds_0_ai_wav.wav'


# ──────────────────────────────────────────────
#  _recv_pcm 落盘时序：*.part 临时文件 + 用例纪元校验
# ──────────────────────────────────────────────

def _fake_hdc_recv(monkeypatch, driver, mutate_epoch_to=None, content=b'PCM-DATA'):
    """monkeypatch subprocess.run 模拟 hdc file recv：把内容写到目标路径"""
    import backend.utils.device_driver.harmony_xiaoyichat as hxc

    def fake_run(args, **kwargs):
        target = args[-1]
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as f:
            f.write(content)
        if mutate_epoch_to is not None:
            driver._case_epoch = mutate_epoch_to
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(hxc.subprocess, 'run', fake_run)


def test_recv_pcm_atomic_write_when_epoch_unchanged(tmp_path, monkeypatch):
    driver = _make_xiaoyi_driver()
    local_path = str(tmp_path / '407' / 'case-A' / 'r0_100016_x.pcm')
    _fake_hdc_recv(monkeypatch, driver)

    got = driver._recv_pcm('SN', '/dev/cache/100016_x.pcm', local_path,
                           task_id=407, test_case_id='case-A', app='doubao', role='ai')
    assert got == local_path
    assert os.path.exists(local_path)
    with open(local_path, 'rb') as f:
        assert f.read() == b'PCM-DATA'
    # 临时文件已原子替换，不残留
    assert not os.path.exists(local_path + driver.PART_FILE_SUFFIX)


def test_recv_pcm_discards_write_when_case_switched(tmp_path, monkeypatch):
    """拉取期间用例已切换（纪元变化）→ 丢弃写入，正式路径不得出现文件"""
    driver = _make_xiaoyi_driver()
    local_path = str(tmp_path / '407' / 'case-A' / 'r0_100016_x.pcm')
    # recv 完成瞬间 simulate 下个用例的 initialize 推进了纪元
    _fake_hdc_recv(monkeypatch, driver, mutate_epoch_to='EPOCH-B')

    got = driver._recv_pcm('SN', '/dev/cache/100016_x.pcm', local_path,
                           task_id=407, test_case_id='case-A', app='doubao', role='ai')
    assert got is None
    assert not os.path.exists(local_path)
    assert not os.path.exists(local_path + driver.PART_FILE_SUFFIX)


# ──────────────────────────────────────────────
#  _pull_record_file / get_results 录屏名一致性校验
# ──────────────────────────────────────────────

def test_pull_record_file_rejects_foreign_case_record(tmp_path, monkeypatch):
    """滞留 teardown 兜底：驱动录屏名已属于新用例，旧用例参数的拉取必须被拒绝"""
    import backend.utils.device_driver.harmony_xiaoyichat as hxc
    from config.config import Config

    monkeypatch.setattr(Config, 'STATIC_BASE_PATH', str(tmp_path))
    driver = _make_xiaoyi_driver()
    # 驱动单例状态已被下个用例污染：录屏名是 case-B 的
    driver._record_file_name = 'case-B.mp4'
    driver._record_device_path = '/storage/media/VID_B.mp4'

    def boom(*a, **k):
        raise AssertionError('一致性校验失败时不得触达设备')

    driver._hdc_shell = boom
    monkeypatch.setattr(hxc.subprocess, 'run', boom)

    # 本调用是 case-A 的滞留 teardown（参数仍绑定 case-A）
    got = driver._pull_record_file('SN', task_id=407, test_case_id='case-A')
    assert got is None
    # case-A 目录不得被创建/写入
    assert not os.path.exists(os.path.join(str(tmp_path), 'case_result', '407', 'case-A'))


def test_start_recorder_failure_resets_device_path():
    """aa start 失败路径必须复位 _record_device_path，防旧 VID 路径残留"""
    driver = _make_xiaoyi_driver()
    driver._record_device_path = '/storage/media/VID_STALE.mp4'
    driver._list_device_mp4_set = lambda sn: set()
    driver._hdc_shell = lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='fail')

    assert driver._start_recorder('SN', file_name='case-A.mp4') is False
    assert driver._record_device_path is None


# ──────────────────────────────────────────────
#  残留基线排除（残留复用形态）
# ──────────────────────────────────────────────

def test_pick_pcm_excludes_unchanged_residue():
    """清理失败的同槽位残留（size 未变化）不得因体积大而被选中"""
    driver = _make_xiaoyi_driver()
    residue = '/cache/100016_48000_2_1_client_in..pcm'   # 上个批次残留，体积大
    fresh = '/cache/100022_48000_2_1_client_in..pcm'     # 本用例新文件，体积小
    sizes = {residue: 999000, fresh: 100000}
    driver._get_device_file_size = lambda sn, f: sizes[f]
    driver._pcm_baseline = {residue: 999000}

    picked = driver._pick_pcm('SN', [residue, fresh], 'client_in..pcm')
    assert picked == fresh


def test_pick_pcm_allows_grown_baseline_file():
    """基线文件 size 增长 = 本用例 dump 正在同名写入，允许选取"""
    driver = _make_xiaoyi_driver()
    grown = '/cache/100016_48000_2_1_client_in..pcm'
    sizes = {grown: 999000}
    driver._get_device_file_size = lambda sn, f: sizes[f]
    driver._pcm_baseline = {grown: 500}   # 清理失败时只有 500 字节，现在被写大了

    assert driver._pick_pcm('SN', [grown], 'client_in..pcm') == grown


def test_pick_pcm_returns_none_when_all_residue():
    """候选全部为纯残留 → 宁缺毋错，返回 None"""
    driver = _make_xiaoyi_driver()
    residue = '/cache/100016_48000_2_1_client_in..pcm'
    driver._get_device_file_size = lambda sn, f: 999000
    driver._pcm_baseline = {residue: 999000}

    assert driver._pick_pcm('SN', [residue], 'client_in..pcm') is None


def test_find_ai_pcm_excludes_residue():
    """豆包 RMS 检测选 AI pcm 时同样排除残留（旧逻辑按名排序取最后会命中残留）"""
    driver = _make_doubao_driver()
    residue = '/cache/100022_48000_2_1_client_in..pcm'   # 残留但按名排序在最后
    fresh = '/cache/100016_48000_2_1_client_in..pcm'
    driver._hdc_shell = lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=f'{residue}\n{fresh}\n', stderr='')
    sizes = {residue: 777000, fresh: 100000}
    driver._get_device_file_size = lambda sn, f: sizes[f]
    driver._pcm_baseline = {residue: 777000}

    assert driver._find_ai_pcm_remote('SN') == fresh


def test_find_ai_pcm_returns_none_when_all_residue():
    driver = _make_doubao_driver()
    residue = '/cache/100022_48000_2_1_client_in..pcm'
    driver._hdc_shell = lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=f'{residue}\n', stderr='')
    driver._get_device_file_size = lambda sn, f: 777000
    driver._pcm_baseline = {residue: 777000}

    assert driver._find_ai_pcm_remote('SN') is None


# ──────────────────────────────────────────────
#  DoubaoChat.initialize 状态复位完整性
# ──────────────────────────────────────────────

class _FakeUiDriver:
    def __init__(self):
        self.calls = []

    def shell(self, cmd):
        self.calls.append(cmd)

    def stop_app(self, bundle):
        pass

    def swipe_to_home(self):
        pass

    def press_home(self):
        pass

    def wait(self, s):
        pass

    def touch(self, *a):
        pass

    def find_component(self, *a, **k):
        return None


def _run_doubao_initialize(monkeypatch, driver):
    import backend.utils.device_driver.harmony_doubaochat as dbc

    fake = _FakeUiDriver()
    driver._get_driver = lambda sn: fake
    driver.unlock = lambda sn: None
    driver.close_popups = lambda sn: None
    driver._check_stop = lambda *a, **k: False
    driver._hdc_shell = lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr='')
    cleared = []
    driver._clear_pcm = lambda sn, app='xiaoyi', **k: cleared.append(app)
    monkeypatch.setattr(dbc.time, 'sleep', lambda s: None)
    ok = driver.initialize('SN', task_id=407, test_case_id='case-A')
    return ok, cleared


def test_doubao_initialize_resets_record_state_and_epoch(monkeypatch):
    """豆包 initialize 必须复位 _record_device_path/_recorder_first_frame_ms 并推进纪元"""
    driver = _make_doubao_driver()
    # 模拟上个用例的脏状态
    driver._record_device_path = '/storage/media/VID_STALE.mp4'
    driver._recorder_first_frame_ms = 1234567
    driver._case_epoch = 'EPOCH-OLD'
    driver._pcm_baseline = {'/cache/stale.pcm': 1}

    ok, cleared = _run_doubao_initialize(monkeypatch, driver)
    assert ok is True
    assert driver._record_device_path is None
    assert driver._recorder_first_frame_ms is None
    assert driver._case_epoch not in (None, 'EPOCH-OLD')
    assert driver._pcm_baseline == {}
    # docstring 声明的"清 pcm"步骤必须真实发生（此前实现遗漏）
    assert cleared == ['doubao']


def test_chatgpt_initialize_resets_record_state_and_epoch(monkeypatch):
    """ChatGPT initialize 同样补齐复位"""
    from backend.utils.device_driver.harmony_chatgpt import ChatGptVoiceChat
    import backend.utils.device_driver.harmony_chatgpt as hcg

    driver = ChatGptVoiceChat.__new__(ChatGptVoiceChat)
    driver._log = lambda **kw: None
    driver._record_device_path = '/storage/media/VID_STALE.mp4'
    driver._recorder_first_frame_ms = 1234567
    driver._case_epoch = 'EPOCH-OLD'
    driver._pcm_baseline = {'/cache/stale.pcm': 1}

    fake = _FakeUiDriver()
    driver._get_driver = lambda sn: fake
    driver.unlock = lambda sn: None
    driver.close_popups = lambda sn: None
    driver._check_stop = lambda *a, **k: False
    driver._hdc_shell = lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr='')
    driver.app_name = 'com.openai.chatgpt'   # __new__ 构造跳过 __init__，手动补实例属性
    # ChatGPT initialize 直接 subprocess.run 调 hdc aa start（不走 _hdc_shell）
    monkeypatch.setattr(hcg.subprocess, 'run',
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr=''))
    monkeypatch.setattr(hcg.time, 'sleep', lambda s: None)

    ok = driver.initialize('SN', task_id=407, test_case_id='case-A')
    assert ok is True
    assert driver._record_device_path is None
    assert driver._recorder_first_frame_ms is None
    assert driver._case_epoch not in (None, 'EPOCH-OLD')
    assert driver._pcm_baseline == {}
