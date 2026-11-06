# -*- coding: utf-8 -*-
"""INT-134 测试工程师独立验收：compare 模式 audios_list 重复 append 修复。

开发侧回归（test_int134_compare_audios_no_dup.py）覆盖了主场景；本文件
从验收角度补充其未覆盖的口径：

1. 多轮×多音频：每音频恰好一次、噪声仅末尾一次（开发用例每轮仅一音频）
2. 同一音频 id 出现在多轮属合法重复（每轮各一条、roundNumber 区分）——
   修复删除的是 extend 引入的对象级重复，不得误伤跨轮重复
3. 轮间 timeline 偏移：per_round_dry 排序与 global_offset 机制在修复后完好
4. task 模式多轮多音频同口径核验（task 不涉及 extend，行为应与修复前一致）
5. task / compare 字段口径在修复后仍各自正确（type 键、label 有无）
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int134_accept_') + '/accept.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import report_service.application.services.report_helpers as rh
import report_service.infrastructure.clients.grpc_clients as rh_grpc
from report_service.application.services.report_helpers import ReportHelpers


@pytest.fixture(autouse=True)
def _stub_grpc_clients(monkeypatch):
    """gRPC 全打桩：音频/设备恒命中，算法参数规范化短路为空 dict（无 overlap）。"""
    monkeypatch.setattr(rh, '_grpc_get_audio',
                        lambda audio_id: {'id': audio_id, 'name': f'audio-{audio_id}',
                                          'original_filename': f'a{audio_id}.wav', 'duration': 3.0})
    monkeypatch.setattr(rh, '_grpc_get_playback_devices_by_ids',
                        lambda ids: {i: {'name': f'pb-{i}'} for i in ids})
    monkeypatch.setattr(rh, '_grpc_get_devices_by_ids',
                        lambda ids: {i: {'name': f'dev-{i}'} for i in ids})
    monkeypatch.setattr(rh_grpc, '_grpc_algo_normalize_algorithm_params', lambda params: {})


def _case(config, name='对比用例'):
    return {'id': 'tc-134-accept', 'name': name, 'config': config}


def _round(round_number, audio_ids, noise_audio_id=None):
    audios = [{'audio_id': aid, 'spl': 70, 'play_order': i + 1,
               'device_id': 7, 'playback_device_id': 7}
              for i, aid in enumerate(audio_ids)]
    rnd = {'roundNumber': round_number, 'audios': audios}
    if noise_audio_id:
        rnd['backgroundNoise'] = {'audio_id': noise_audio_id, 'spl': 40}
    return rnd


def test_compare_multiround_multiaudio_each_once_noise_last():
    """多轮×多音频：每音频恰好一次、噪声仅末尾一次、无对象级重复。"""
    config = {'rounds': [
        _round(1, [11, 12], noise_audio_id=15),
        _round(2, [13, 14]),
    ]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='compare')

    ids = [a['id'] for a in audios]
    assert sorted(ids) == [11, 12, 13, 14, 15], f'每音频一次+噪声末尾，实际 {ids}'
    assert ids[-1] == 15, '噪声应位于列表末尾且仅一条'
    assert len({id(a) for a in audios}) == len(audios), '不得出现同一 dict 对象二次入列'
    # (id, roundNumber) 无重复对：同轮内同一音频不得出现两次
    pairs = [(a['id'], a['roundNumber']) for a in audios]
    assert len(pairs) == len(set(pairs))


def test_compare_same_audio_across_rounds_not_collapsed():
    """同一音频 id 出现在两轮属合法重复：每轮各一条、roundNumber 区分。

    修复删除的是 extend 造成的对象级重复，不得误伤跨轮复用同一音频的场景
    （验收口径：每轮音频各渲染一次、带轮次前缀）。
    """
    config = {'rounds': [_round(1, [11]), _round(2, [11])]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='compare')

    entries = [a for a in audios if a['id'] == 11]
    assert len(entries) == 2, f'跨轮同音频应每轮各一条，实际 {len(entries)} 条'
    assert {a['roundNumber'] for a in entries} == {1, 2}
    assert entries[0] is not entries[1], '两轮条目应为不同 dict 对象（非同一对象重复）'
    assert len({id(a) for a in audios}) == len(audios)


def test_compare_timeline_round_offset_after_dedup():
    """轮间 timeline 偏移：修复后 per_round_dry 排序与 global_offset 机制完好。

    r1 两音频各 3s（play_order 1→2），r2 一音频应从 6.0 起播；
    噪声 timeline 恒 [0, duration]。
    """
    config = {'rounds': [
        _round(1, [11, 12], noise_audio_id=15),
        _round(2, [13]),
    ]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='compare')

    by_id = {a['id']: a for a in audios}
    assert by_id[11]['timelineStart'] == pytest.approx(0.0)
    assert by_id[11]['timelineEnd'] == pytest.approx(3.0)
    assert by_id[12]['timelineStart'] == pytest.approx(3.0)
    assert by_id[12]['timelineEnd'] == pytest.approx(6.0)
    assert by_id[13]['timelineStart'] == pytest.approx(6.0), '第二轮应接在第一轮末尾'
    assert by_id[13]['timelineEnd'] == pytest.approx(9.0)
    assert by_id[15]['timelineStart'] == pytest.approx(0.0)
    assert by_id[15]['timelineEnd'] == pytest.approx(3.0)


def test_task_mode_multiround_multiaudio_each_once():
    """task 模式多轮多音频：每音频一次、噪声末尾一次（修复未触及 task 路径）。"""
    config = {'rounds': [
        _round(1, [11, 12], noise_audio_id=15),
        _round(2, [13, 14]),
    ]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='task')

    ids = [a['id'] for a in audios]
    assert sorted(ids) == [11, 12, 13, 14, 15]
    assert ids[-1] == 15
    assert len({id(a) for a in audios}) == len(audios)


def test_field_shape_per_mode_preserved():
    """修复后 task / compare 字段口径仍各自正确（label 有无、设备键名）。"""
    config = {'rounds': [_round(1, [11], noise_audio_id=15)]}

    compare_items = ReportHelpers._build_audios_list(_case(config), mode='compare')
    task_items = ReportHelpers._build_audios_list(_case(config), mode='task')

    cmp_audio = next(a for a in compare_items if a['id'] == 11)
    assert 'audio_type' not in cmp_audio
    assert 'label' not in cmp_audio
    assert 'device_id' in cmp_audio and 'device_name' in cmp_audio
    assert 'play_order' in cmp_audio

    tsk_audio = next(a for a in task_items if a['id'] == 11)
    assert 'testType' not in tsk_audio
    assert 'playOrder' in tsk_audio and 'playbackDeviceId' in tsk_audio

    cmp_noise = compare_items[-1]
    assert 'noise_spl' in cmp_noise
    tsk_noise = task_items[-1]
    assert 'spl' in tsk_noise
