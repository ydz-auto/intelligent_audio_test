# -*- coding: utf-8 -*-
"""INT-510 验收：V9.7.10 VEGA-7/VEGA-10 驱动防护移植到 V9.7.31 的离线回归测试。

覆盖本卡从 V9.7.10 合入 device_service 驱动层的跨用例污染防护（VEGA-10）与
打断布尔归一（VEGA-7 _as_bool）中可离线验证的部分：
- _recv_pcm 落盘时序：先写 *.part 临时文件，用例纪元校验通过后才原子替换；
  纪元变化（拉取期间用例已切换）时丢弃写入
- _pull_record_file 录屏名一致性校验：驱动状态属于别的用例时拒绝拉取
- _start_recorder 启动失败路径复位 _record_device_path，防旧 VID 路径残留
- _pick_pcm / DoubaoChat._find_ai_pcm_remote 残留基线排除：清理失败的跨用例
  残留文件（size 未变化）不再被选中；size 增长的基线文件（本用例正在写）允许选取
- _as_bool kwargs 兼容性：True/'true'/'1'/1（及 'True'/'yes'/'是' 等扩展形态）
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from device_service.infrastructure.drivers.harmony_xiaoyichat import Xiaoyilivechat
from device_service.infrastructure.drivers.harmony_doubaochat import DoubaoChat


# ──────────────────────────────────────────────
#  公共工具：构造不依赖真机的驱动实例
# ──────────────────────────────────────────────

def _make_xiaoyi_driver():
    driver = Xiaoyilivechat.__new__(Xiaoyilivechat)
    driver._log = lambda **kw: None
    driver._case_epoch = 'EPOCH-A'
    driver._pcm_baseline = {}
    return driver


def _make_doubao_driver():
    driver = DoubaoChat.__new__(DoubaoChat)
    driver._log = lambda **kw: None
    driver._case_epoch = 'EPOCH-A'
    driver._pcm_baseline = {}
    return driver


# ──────────────────────────────────────────────
#  VEGA-7：_as_bool kwargs 布尔归一
# ──────────────────────────────────────────────

@pytest.mark.parametrize('value', [True, 'true', '1', 1, 'True', 'yes', '是', 'Y'])
def test_as_bool_truthy_forms(value):
    assert Xiaoyilivechat._as_bool(value) is True


@pytest.mark.parametrize('value', [False, 'false', '0', 0, None, '', 'no'])
def test_as_bool_falsy_forms(value):
    assert Xiaoyilivechat._as_bool(value) is False


# ──────────────────────────────────────────────
#  _recv_pcm 落盘时序：*.part 临时文件 + 用例纪元校验
# ──────────────────────────────────────────────

def _fake_hdc_recv(monkeypatch, driver, mutate_epoch_to=None, content=b'PCM-DATA'):
    import device_service.infrastructure.drivers.harmony_xiaoyichat as hxc

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
#  _pull_record_file 录屏名一致性校验
# ──────────────────────────────────────────────

def test_pull_record_file_rejects_foreign_case_record(tmp_path, monkeypatch):
    """滞留 teardown 兜底：驱动录屏名已属于新用例，旧用例参数的拉取必须被拒绝"""
    import device_service.infrastructure.drivers.harmony_xiaoyichat as hxc

    driver = _make_xiaoyi_driver()
    # 驱动单例状态已被下个用例污染：录屏名是 case-B 的
    driver._record_file_name = 'case-B.mp4'
    driver._record_device_path = '/storage/media/VID_B.mp4'

    def boom(*a, **k):
        raise AssertionError('一致性校验失败时不得触达设备')

    driver._hdc_shell = boom
    driver._upload_file_to_oss = boom
    monkeypatch.setattr(hxc.subprocess, 'run', boom)

    # 本调用是 case-A 的滞留 teardown（参数仍绑定 case-A）
    got = driver._pull_record_file('SN', task_id=407, test_case_id='case-A')
    assert got is None


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
