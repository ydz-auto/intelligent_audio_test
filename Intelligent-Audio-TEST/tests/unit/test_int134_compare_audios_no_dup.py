# -*- coding: utf-8 -*-
"""INT-134 回归：compare 模式 audios_list 同一音频项重复 append。

report_helpers._build_audios_list 中音频项在循环内被无条件
audios_list.append，compare 分支随后又 audios_list.extend(round_dry)，
同一 dict 二次入列（5ade26b4 合并 task/compare 两 builder 时引入，
先于 INT-79）。对比报告用例 audios 落库即含重复，前端全链路
（converter / adapter / prepareAudioList / normalizeAudioItem）均透传
不去重，AudioTimelineVisualization 将同一音频渲染为上下两层同位段，
且 v-for :key="audio.id" 产生重复键。修复：移除 compare 分支的
extend，task / compare 均保持每音频项恰好一次；per_round_dry 仅承担
轮内排序与 timeline 计算，不受影响。
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int134_audios_') + '/audios.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import report_service.application.services.report_helpers as rh
import report_service.infrastructure.clients.grpc_clients as rh_grpc
from report_service.application.services.report_helpers import ReportHelpers


@pytest.fixture(autouse=True)
def _stub_grpc_clients(monkeypatch):
    """gRPC 全打桩：音频/设备恒命中，算法参数规范化短路为空 dict。"""
    monkeypatch.setattr(rh, '_grpc_get_audio',
                        lambda audio_id: {'id': audio_id, 'name': f'audio-{audio_id}',
                                          'original_filename': f'a{audio_id}.wav', 'duration': 3.0})
    monkeypatch.setattr(rh, '_grpc_get_playback_devices_by_ids',
                        lambda ids: {i: {'name': f'pb-{i}'} for i in ids})
    monkeypatch.setattr(rh, '_grpc_get_devices_by_ids',
                        lambda ids: {i: {'name': f'dev-{i}'} for i in ids})
    monkeypatch.setattr(rh_grpc, '_grpc_algo_normalize_algorithm_params', lambda params: {})


def _case(config, name='对比用例'):
    return {'id': 'tc-134', 'name': name, 'config': config}


def _round(round_number, audio_ids, noise_audio_id=None):
    audios = [{'audio_id': aid, 'spl': 70, 'play_order': i + 1,
               'device_id': 7, 'playback_device_id': 7}
              for i, aid in enumerate(audio_ids)]
    rnd = {'roundNumber': round_number, 'audios': audios}
    if noise_audio_id:
        rnd['backgroundNoise'] = {'audio_id': noise_audio_id, 'spl': 40}
    return rnd


def test_compare_mode_no_duplicate_audio_items():
    """修复主场景：compare 模式两轮各一音频，每个音频项恰好出现一次。"""
    config = {'rounds': [_round(1, [11], noise_audio_id=13), _round(2, [12])]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='compare')

    ids = [a['id'] for a in audios]
    assert sorted(ids) == [11, 12, 13], f'每个音频应恰好一次，实际 {ids}'
    assert ids[-1] == 13, '噪声应位于列表末尾'
    # 修复前同一 dict 对象重复入列（extend 引用同一对象），以对象级唯一性兜底
    assert len({id(a) for a in audios}) == len(audios)


def test_task_mode_unchanged_single_append():
    """task 模式不受修复影响：每音频一次、噪声在末尾。"""
    config = {'rounds': [_round(1, [11], noise_audio_id=13), _round(2, [12])]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='task')

    ids = [a['id'] for a in audios]
    assert sorted(ids) == [11, 12, 13]
    assert len({id(a) for a in audios}) == len(audios)


def test_compare_mode_timeline_still_follows_round_sort():
    """修复后 timeline 仍按 per_round_dry 轮内 play_order 排序计算。"""
    # _round 中 play_order 按列表序生成：12→order 1，11→order 2
    config = {'rounds': [_round(1, [12, 11])]}
    audios = ReportHelpers._build_audios_list(_case(config), mode='compare')

    by_id = {a['id']: a for a in audios}
    assert 'timelineStart' in by_id[11] and 'timelineEnd' in by_id[11]
    assert by_id[12]['timelineStart'] < by_id[11]['timelineStart']
    assert by_id[11]['timelineEnd'] == pytest.approx(6.0)
