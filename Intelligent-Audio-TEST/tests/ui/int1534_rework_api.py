# -*- coding: utf-8 -*-
"""INT-1534 返工：建临时用例 + 直连 15000 网关核验用例试听契约。

覆盖（返工只复测失败项与本次修复相关部分）：
1. 建「接线测试_INT1534_返工_试听」用例（rounds[0].audios 引一条新存储布局音频 + 真实播放设备）；
2. POST /testcases/{id}/preview frontend（offset 0）→ 返回 audio_stream_url(s)，且预签名 URL 可取字节；
3. POST /testcases/{id}/preview backend（offset 1）→ 载荷 offset/preview_type/playback_mode 生效；
4. POST /testcases/{id}/stop_preview；
5. 输出 CASE_ID 供浏览器取证脚本复用（run 结束前删用例，见 --cleanup）。
"""
import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

GW = os.environ.get('GW_BASE', 'http://127.0.0.1:15000/api/v1')
OUT = os.environ.get('OUT_DIR', r'D:\00_env\i1534')
CASE_NAME = '接线测试_INT1534_返工_试听'


def log(msg):
    print(msg, flush=True)


def request(method, path, payload=None, timeout=180):
    url = GW + path
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode('utf-8', 'replace')
            return res.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        return e.code, body


def unwrap(payload):
    if isinstance(payload, dict) and 'data' in payload:
        return payload['data']
    return payload


def pick_audio():
    """选一条在库音频（15000 栈 upload/register 报 Config.AUDIO_UPLOAD_CHUNK_SIZE_MB 缺失，
    无法现传；只读引用在库音频，不修改它）。"""
    status, body = request('GET', '/audios?page=1&per_page=60')
    log('GET /audios -> %s' % status)
    data = unwrap(body) or {}
    for item in data.get('items') or []:
        if (item.get('duration') or 0) > 0:
            return item
    raise SystemExit('列表无可用音频')


def pick_device():
    status, body = request('GET', '/playback-devices?page=1&per_page=20')
    log('GET /playback-devices -> %s' % status)
    data = unwrap(body) or {}
    items = data.get('items') or []
    if not items:
        raise SystemExit('无播放设备记录')
    return items[0]


def pick_group():
    status, body = request('GET', '/groups?page=1&per_page=200')
    log('GET /groups -> %s' % status)
    data = unwrap(body) or {}
    items = data.get('items') or []
    for item in items:
        if item.get('name') == '音频上传生成':
            return item
    return items[0]


def create_case(audio, device, group):
    config = {
        'rounds': [
            {
                'round_number': 1,
                'audios': [
                    {
                        'audio_id': audio['id'],
                        'audio_name': audio['name'],
                        'spl': 65,
                        'playback_device_id': device['id'],
                        'playback_device_name': device['name'],
                        'play_order': 1,
                    }
                ],
                'evaluation': {'enabled': False, 'dimensions': []},
            }
        ]
    }
    payload = {
        'name': CASE_NAME,
        'description': 'INT-1534 返工核验临时用例（run 结束删除）',
        'group_id': group['id'],
        'config': config,
    }
    status, body = request('POST', '/testcases', payload)
    log('POST /testcases -> %s %s' % (status, json.dumps(body, ensure_ascii=False)[:200]))
    data = unwrap(body) or {}
    case_id = data.get('id') if isinstance(data, dict) else None
    if status not in (200, 201) or not case_id:
        raise SystemExit('建用例失败')
    return str(case_id)


def fetch_bytes(url):
    """预签名 URL 主机是容器网络名 rustfs：用 curl --resolve 映射到本机 9000。"""
    cmd = [
        'curl', '-s', '-o', os.path.join(OUT, 'stream_probe.bin'),
        '-w', '%{http_code} %{size_download}',
        '--resolve', 'rustfs:9000:127.0.0.1', '-m', '60', url,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return out.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--case-id', default='')
    parser.add_argument('--audio-id', default='')
    args = parser.parse_args()
    os.makedirs(OUT, exist_ok=True)

    if args.cleanup:
        case_id = args.case_id or os.environ.get('CASE_ID', '')
        audio_id = args.audio_id or os.environ.get('AUDIO_ID', '')
        if case_id:
            s1, b1 = request('DELETE', '/testcases/%s' % case_id)
            s2, b2 = request('DELETE', '/testcases/%s/purge' % case_id)
            log('DELETE /testcases/%s -> %s | purge -> %s %s'
                % (case_id, s1, s2, json.dumps(b2, ensure_ascii=False)[:200]))
        if audio_id:
            s3, b3 = request('DELETE', '/audios/%s' % audio_id)
            log('DELETE /audios/%s -> %s %s'
                % (audio_id, s3, json.dumps(b3, ensure_ascii=False)[:200]))
        return

    audio = pick_audio()
    device = pick_device()
    group = pick_group()
    log('audio=%s name=%s path=%s duration=%s' % (audio['id'], audio['name'], audio['file_path'], audio['duration']))
    log('device=%s name=%s status=%s' % (device['id'], device['name'], device.get('status')))
    log('group=%s %s' % (group['id'], group['name']))

    case_id = create_case(audio, device, group)

    result = {'case_id': case_id, 'audio_id': audio['id'], 'device': device['name']}

    s, b = request('POST', '/testcases/%s/preview' % case_id,
                   {'offset': 0, 'preview_type': 'frontend', 'playback_mode': 'frontend'})
    front = unwrap(b)
    log('POST preview(frontend) -> %s %s' % (s, json.dumps(front, ensure_ascii=False)[:600]))
    result['frontend'] = {'status': s, 'data': front}
    stream_url = None
    if isinstance(front, dict):
        urls = front.get('audio_stream_urls') or []
        stream_url = urls[0] if urls else front.get('audio_stream_url')
    result['stream_url'] = stream_url
    if stream_url:
        result['stream_fetch'] = fetch_bytes(stream_url)
        log('GET stream -> %s' % result['stream_fetch'])

    s, b = request('POST', '/testcases/%s/preview' % case_id,
                   {'offset': 1, 'preview_type': 'backend', 'playback_mode': 'backend'})
    log('POST preview(backend, offset=1) -> %s %s' % (s, json.dumps(unwrap(b), ensure_ascii=False)[:400]))
    result['backend'] = {'status': s, 'data': unwrap(b)}

    s, b = request('POST', '/testcases/%s/stop_preview' % case_id)
    log('POST stop_preview -> %s %s' % (s, json.dumps(unwrap(b), ensure_ascii=False)[:200]))
    result['stop'] = {'status': s, 'data': unwrap(b)}

    with open(os.path.join(OUT, 'api_result.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log('CASE_ID=%s' % case_id)


if __name__ == '__main__':
    main()
