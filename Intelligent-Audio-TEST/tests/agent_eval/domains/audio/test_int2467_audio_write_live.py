# -*- coding: utf-8 -*-
"""INT-2467 音频写工具实测（真实 docker 网关）。

默认跳过；显式给出网关地址时运行：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/audio/test_int2467_audio_write_live.py -s

验收口径（卡面 1 / 5）：URL 导入 → 批量标注 → 删除，全部真实副作用且清理干净；
数据一律用「接线测试_」前缀。音频字节由本地 HTTP 服务提供（audio_service 跑宿主机，
可达 127.0.0.1），验证 url_import 真实下载 / 入库。
"""
import functools
import http.server
import os
import socket
import struct
import tempfile
import threading
import wave

import pytest

from tests.agent_eval import live_support

pytestmark = pytest.mark.skipif(
    not live_support.available(),
    reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')

AUDIO_PERMISSIONS = ('audio:read', 'audio:upload', 'audio:update',
                     'audio:delete')


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _write_sample_wav(path: str) -> None:
    """写一个 1 秒 16kHz 单声道正弦 wav（真实可解码，不依赖仓库样例）。"""
    import math
    frames = bytearray()
    for index in range(16000):
        value = int(12000 * math.sin(2 * math.pi * 440 * index / 16000))
        frames += struct.pack('<h', value)
    with wave.open(path, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(bytes(frames))


@pytest.fixture(scope='module')
def wav_server():
    directory = tempfile.mkdtemp(prefix='int2467_audio_')
    filename = f'{live_support.LIVE_PREFIX}INT2467_导入.wav'
    _write_sample_wav(os.path.join(directory, filename))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=directory)
    port = _free_port()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{port}/{filename}'
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope='module')
def live():
    token = live_support.login()
    return live_support.gateway_client(token), token


def _execute(gateway, name, arguments, permissions=AUDIO_PERMISSIONS):
    from agent_service.domain.model.entities import ToolCallRequest

    return gateway.execute(
        ToolCallRequest(tool_call_id=f'live-{name}', name=name,
                        arguments=arguments),
        live_support.approved_ctx(permissions=permissions))


def test_live_audio_import_annotate_delete(live, wav_server):
    """URL 导入 → 批量标注（annotations）→ 元数据 → 算法 → 删除，全部真实写库。"""
    import json

    gateway, token = live

    def detail(audio_id):
        result = _execute(gateway, 'audio_query',
                          {'action': 'detail', 'audio_id': audio_id})
        assert result.ok, result.content[:300]
        return json.loads(result.content)['data']

    imported_id = None
    try:
        result = _execute(gateway, 'audio_import', {
            'action': 'url_import', 'url': wav_server, 'audio_type': 'dry'})
        assert result.ok, f'{result.error_code} {result.content[:300]}'
        payload = json.loads(result.content)
        assert payload['success'] is True, payload
        imported_id = payload['data']['id']
        # 入库名由 audio_service 加 ``url_`` 前缀后再拼原文件名，前缀仍在名字里
        assert live_support.LIVE_PREFIX in payload['data']['name']

        # 批量标注（annotations 真实写库）
        annotate = _execute(gateway, 'audio_annotate', {
            'action': 'batch_annotate',
            'items': [{'audio_id': imported_id,
                       'annotations': [{'format': 'text', 'code': 'int2467',
                                        'data': {'text': '接线测试'}}]}]})
        assert annotate.ok, f'{annotate.error_code} {annotate.content[:300]}'
        annotated = json.loads(annotate.content)
        assert annotated['data']['updated_count'] == 1, annotated
        data = detail(imported_id)
        assert data.get('annotations'), data

        # 元数据（改名 + 标签 + 描述）
        meta = _execute(gateway, 'audio_annotate', {
            'action': 'update_meta', 'audio_id': imported_id,
            'metadata': {'name': f'{live_support.LIVE_PREFIX}INT2467_改名.wav',
                         'tags': f'{live_support.LIVE_PREFIX}INT2467,'
                                 f'{live_support.LIVE_PREFIX}标签',
                         'description': '接线测试'}})
        assert meta.ok, f'{meta.error_code} {meta.content[:300]}'
        data = detail(imported_id)
        assert data['name'] == f'{live_support.LIVE_PREFIX}INT2467_改名.wav'
        assert f'{live_support.LIVE_PREFIX}INT2467' in (data.get('tags') or [])
        assert data['description'] == '接线测试'

        # 算法配置（写入 + 读回）
        algo = _execute(gateway, 'audio_annotate', {
            'action': 'set_algorithms', 'audio_id': imported_id,
            'algorithms': [{'algorithm_type': 'voice_llm'}]})
        assert algo.ok, f'{algo.error_code} {algo.content[:300]}'
        read_algo = _execute(gateway, 'audio_query',
                             {'action': 'algorithms',
                              'audio_id': imported_id})
        assert read_algo.ok, read_algo.content[:300]
        assert json.loads(read_algo.content)['data'][0]['algorithm_type'] ==             'voice_llm'
    finally:
        if imported_id:
            deleted = _execute(gateway, 'audio_delete',
                               {'audio_id': imported_id})
            assert deleted.ok, f'清理失败 {deleted.content[:300]}'
    status, _body = live_support.raw(
        'GET', f'/api/v1/audios/{imported_id}', token)
    assert status in (400, 404)


def test_live_audio_import_rejects_bad_url(live):
    """URL 不可达：真实失败（不是静默成功），且不留下记录。"""
    gateway, _token = live
    result = _execute(gateway, 'audio_import', {
        'action': 'url_import',
        'url': 'http://127.0.0.1:1/接线测试_不存在.wav'})
    assert result.ok is False
    # 上游是 400 + 失败文案，工具层按普通失败回灌（不是 JSON success 信封）
    assert '下载失败' in result.content or '400' in result.content
