# -*- coding: utf-8 -*-
"""INT-1556：报告音频 url 必须指向网关已挂载的音频流端点。

缺陷：task 模式 `_build_audios_list` 输出 `/api/audios/play/{id}`，api_gateway
并无该路由（404），且 compare 模式输出的是 `/api/v1/audios/{id}/stream`——
同一份报告数据两种口径。修复后两模式统一到挂载中的流端点。

覆盖：
1. task 模式音频项与噪声项 url 均为 `/api/v1/audios/{id}/stream`
2. compare 模式不受影响（口径不变）
3. 生成的 url 不含已废弃的 `/api/audios/play`
4. 目标路径确实由 api_gateway 音频蓝图挂载（防止再次指向不存在的路由）
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1556_') + '/audio_url.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import report_service.application.services.report_helpers as rh
import report_service.infrastructure.clients.grpc_clients as rh_grpc
from report_service.application.services.report_helpers import (
    AUDIO_STREAM_URL_TEMPLATE,
    ReportHelpers,
)


@pytest.fixture(autouse=True)
def _stub_grpc_clients(monkeypatch):
    """gRPC 全打桩：音频/设备恒命中，算法参数规范化短路为空 dict（无 overlap）。"""
    monkeypatch.setattr(rh, '_grpc_get_audio',
                        lambda audio_id: {'id': audio_id, 'name': f'audio-{audio_id}',
                                          'original_filename': f'a{audio_id}.wav',
                                          'duration': 3.0})
    monkeypatch.setattr(rh, '_grpc_get_playback_devices_by_ids',
                        lambda ids: {i: {'name': f'pb-{i}'} for i in ids})
    monkeypatch.setattr(rh, '_grpc_get_devices_by_ids',
                        lambda ids: {i: {'name': f'dev-{i}'} for i in ids})
    monkeypatch.setattr(rh_grpc, '_grpc_algo_normalize_algorithm_params', lambda params: {})


def _case(config, name='报告音频用例'):
    return {'id': 'tc-1556', 'name': name, 'config': config}


def _config():
    return {'rounds': [{
        'roundNumber': 1,
        'audios': [{'audio_id': 1896, 'spl': 70, 'play_order': 1,
                    'device_id': 7, 'playback_device_id': 7}],
        'backgroundNoise': {'audio_id': 1897, 'spl': 40},
    }]}


def test_task_mode_audio_url_uses_mounted_stream_route():
    audios = ReportHelpers._build_audios_list(_case(_config()), mode='task')

    by_id = {a['id']: a for a in audios}
    assert by_id[1896]['url'] == '/api/v1/audios/1896/stream'
    assert by_id[1897]['url'] == '/api/v1/audios/1897/stream'


def test_compare_mode_audio_url_unchanged():
    audios = ReportHelpers._build_audios_list(_case(_config()), mode='compare')

    by_id = {a['id']: a for a in audios}
    assert by_id[1896]['url'] == '/api/v1/audios/1896/stream'
    assert by_id[1897]['url'] == '/api/v1/audios/1897/stream'


def test_no_legacy_unmounted_play_url_in_any_mode():
    for mode in ('task', 'compare'):
        for item in ReportHelpers._build_audios_list(_case(_config()), mode=mode):
            assert '/api/audios/play' not in item['url'], \
                f'{mode} 模式仍输出未挂载路由：{item["url"]}'
            assert item['url'] == AUDIO_STREAM_URL_TEMPLATE.format(id=item['id'])


def test_stream_route_is_registered_in_gateway_audio_blueprint():
    """目标模板必须能在 api_gateway 音频蓝图里找到对应路由（否则又是一条死链）。"""
    import api_gateway.routes.audio_bp as audio_bp

    mounted = {getattr(r, 'path', '') for r in audio_bp.router.routes}
    assert '/{audio_id}/stream' in mounted
    assert AUDIO_STREAM_URL_TEMPLATE == '/api/v1/audios/{id}/stream'
