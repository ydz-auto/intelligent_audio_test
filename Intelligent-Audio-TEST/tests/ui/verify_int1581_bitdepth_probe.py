# -*- coding: utf-8 -*-
"""INT-1581 补充取证：位深度 24 bit 是否真正落到转换产物（DB 无 bit_depth 列，用 ffprobe 验）。

链路：URL 导入自建 WAV → POST /audios/{id}/convert
{format:WAV, sample_rate:22050, channels:2, bit_depth:24} → GET /stream 取流 → ffprobe。
结束前删除自建音频。
"""
import json
import os
import subprocess
import tempfile
import time
from urllib.parse import quote

import requests

GW = 'http://localhost:15000/api/v1'
AUDIO_HOST = os.environ.get('AUDIO_SRC_HOST', 'http://host.docker.internal:5398')
SRC = os.environ.get('AUDIO_SRC_NAME', 'src_A.wav')
NAME = '接线测试_INT1581_位深.wav'
FFPROBE = r'D:\00_env\ffmpeg-8.0.1-full_build\bin\ffprobe.exe'


def _url_of(resp):
    """stream 端点裸返回 {"url": ...}（未套 success/data 信封）。"""
    try:
        body = resp.json()
    except Exception:
        return None
    return body.get('url') or (body.get('data') or {}).get('url')


def main():
    audio_id = None
    try:
        r = requests.post(GW + '/audios/url-import',
                          json={'url': '%s/%s' % (AUDIO_HOST, quote(SRC)), 'audio_type': 'dry'},
                          timeout=120)
        r.raise_for_status()
        audio_id = r.json()['data']['id']
        requests.put(GW + '/audios/%s/metadata' % audio_id, json={'name': NAME}, timeout=60).raise_for_status()
        print('自建音频 id=%s' % audio_id, flush=True)

        conv = requests.post(GW + '/audios/%s/convert' % audio_id,
                             json={'format': 'WAV', 'sample_rate': 22050, 'channels': 2, 'bit_depth': 24},
                             timeout=180)
        print('convert -> %s %s' % (conv.status_code, conv.text[:200]), flush=True)
        assert conv.status_code == 200

        info = requests.get(GW + '/audios/%s' % audio_id, timeout=120).json()['data']
        print('回读 sample_rate=%s channels=%s format=%s' % (
            info.get('sample_rate'), info.get('channels'), info.get('format')), flush=True)
        assert info.get('sample_rate') == 22050 and info.get('channels') == 2

        st = requests.get(GW + '/audios/%s/stream' % audio_id, timeout=120)
        print('stream -> %s %s' % (st.status_code, st.text[:300]), flush=True)
        url = _url_of(st)
        if not url:
            fp = info.get('file_path')
            st = requests.get(GW + '/audios/stream-by-path', params={'path': fp}, timeout=120)
            print('stream-by-path -> %s %s' % (st.status_code, st.text[:300]), flush=True)
            url = _url_of(st)
        print('url=%s' % (url or '')[:160], flush=True)
        assert url
        blob = requests.get(url, timeout=180).content
        tmp = os.path.join(tempfile.gettempdir(), 'int1581_probe.wav')
        with open(tmp, 'wb') as f:
            f.write(blob)
        out = subprocess.run([FFPROBE, '-v', 'error', '-show_streams', '-of', 'json', tmp],
                             capture_output=True, text=True, check=True).stdout
        stream = json.loads(out)['streams'][0]
        print('ffprobe: codec_name=%s sample_rate=%s channels=%s sample_fmt=%s bits_per_raw_sample=%s' % (
            stream.get('codec_name'), stream.get('sample_rate'), stream.get('channels'),
            stream.get('sample_fmt'), stream.get('bits_per_raw_sample')), flush=True)
        assert stream.get('sample_rate') == '22050'
        assert stream.get('channels') == 2
        assert stream.get('bits_per_raw_sample') == '24', stream
        print('OK', flush=True)
    finally:
        if audio_id:
            d = requests.delete(GW + '/audios/%s' % audio_id, timeout=120)
            print('DELETE /audios/%s -> %s' % (audio_id, d.status_code), flush=True)
            time.sleep(1)


if __name__ == '__main__':
    main()
