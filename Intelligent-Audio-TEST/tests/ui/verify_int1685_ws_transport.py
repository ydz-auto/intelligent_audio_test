# -*- coding: utf-8 -*-
"""INT-1685 验收：React 日志实时通道 socket.io 改 websocket-only 后，4 worker 网关上的
建连与 task_log 推送（Network 证据 + 浅/深色截图）。

前置：本 run 的 4 worker 旁路容器 iat-int1685-gw4（15300，同镜像同库 intelligent_audio_test），
本卡 dev server 5371（/api /socket.io 代理指 15300）。

用法：
    python tests/ui/verify_int1685_ws_transport.py --label fix
    python tests/ui/verify_int1685_ws_transport.py --label baseline   # 旧配置 polling+websocket
环境变量：CHROMEDRIVER 默认本机证书缓存驱动；REACT_BASE 默认 http://127.0.0.1:5371
"""
import argparse
import json
import os
import subprocess
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DEFAULT_DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5371')
HERE = os.path.dirname(os.path.abspath(__file__))

STATE_JS = """
return {
  text: document.body ? document.body.innerText : '',
  rows: document.querySelectorAll('table tbody tr').length,
};
"""

# 实时监控 Switch（base-ui 渲染为 [role=switch]）默认关闭，需先打开才建 /socket.io 连接
TOGGLE_JS = """
const switches = Array.from(document.querySelectorAll('[role=switch]'));
const target = switches.find(function (s) {
  const row = s.closest('div');
  const txt = (row && row.innerText) || '';
  return txt.indexOf('实时监控') >= 0;
}) || switches[0];
if (!target) return 'no-switch';
target.click();
return 'clicked:' + (target.getAttribute('aria-checked') || target.getAttribute('data-state') || '');
"""


def build_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1200')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    opts.set_capability('pageLoadStrategy', 'eager')
    exe = os.environ.get('CHROMEDRIVER', DEFAULT_DRIVER)
    if not os.path.isfile(exe):
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        versions = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
        exe = os.path.join(cache, versions[-1], 'chromedriver.exe') if versions else None
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(service=srv, options=opts)
    drv.set_script_timeout(60)
    drv.set_page_load_timeout(180)
    return drv


def drain(drv, acc):
    """收集 /socket.io 的网络事件与 WebSocket 帧。"""
    try:
        entries = drv.get_log('performance')
    except Exception:
        return
    for e in entries:
        try:
            msg = json.loads(e['message'])['message']
        except Exception:
            continue
        method = msg.get('method')
        params = msg.get('params') or {}
        if method == 'Network.requestWillBeSent':
            url = (params.get('request') or {}).get('url') or ''
            if '/socket.io' in url:
                acc['requests'].append(url)
        elif method == 'Network.webSocketCreated':
            acc['ws_created'].append(params.get('url'))
        elif method == 'Network.webSocketFrameReceived':
            data = (params.get('response') or {}).get('payloadData') or ''
            acc['frames_received'].append(data[:400])
            if 'task_log' in data:
                acc['task_log_frames'].append(data[:400])
        elif method == 'Network.webSocketFrameSent':
            data = (params.get('response') or {}).get('payloadData') or ''
            acc['frames_sent'].append(data[:400])
        elif method == 'Network.loadingFailed':
            acc['failed'].append({
                'requestId': params.get('requestId'),
                'error': params.get('errorText'),
                'type': params.get('type'),
            })


# 制造真实的 TASK_LOG 事件：任何服务写日志都会经 EventBus 推到 /ws/logs（只读接口，不写业务数据）
ACTIVITY_JS = """
window.__int1685Activity = [];
const urls = [
  '/api/v1/tasks?page=1&per_page=5',
  '/api/v1/devices?page=1&per_page=5',
  '/api/v1/audios?page=1&per_page=5',
  '/api/v1/testcases?page=1&per_page=5',
  '/api/v1/logs/stats',
  '/api/v1/evaluation-categories',
];
urls.forEach(function (u) {
  fetch(u, { headers: { Accept: 'application/json' } })
    .then(function (r) { window.__int1685Activity.push(u + ' ' + r.status); })
    .catch(function (e) { window.__int1685Activity.push(u + ' ERR ' + e); });
});
return urls.length;
"""


MARKER = '接线测试_INT1685_WS_PUSH_MARKER'


def inject_task_log(marker=MARKER):
    """向真实 EventBus 频道 task_events 发布一条 task_log 信封（与任一服务写日志时的发布同构）。

    只走 Redis → EventBusForwarder → Socket.IO 转发链路，不写库、不改任何业务数据。
    """
    message = {
        'event_type': 'task_log',
        'payload': {
            'log_payload': {
                'id': -990685,
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'module': 'int1685_probe',
                'content': marker,
                'mark': '',
                'task_id': None,
                'test_case_id': None,
                'category': 'system',
                'source': 'system',
                'user_id': None,
            },
            'task_id': None,
            'test_case_id': None,
        },
    }
    body = json.dumps(message, ensure_ascii=False).encode('utf-8')
    proc = subprocess.run(
        ['docker', 'exec', '-i', 'intelligent-audio-test-redis-1', 'redis-cli', '-x', 'PUBLISH', 'task_events'],
        input=body, capture_output=True,
    )
    return {
        'rc': proc.returncode,
        'stdout': proc.stdout.decode('utf-8', 'replace').strip(),
        'stderr': proc.stderr.decode('utf-8', 'replace').strip()[:300],
    }


def enable_realtime(drv, wait=45):
    """点开实时监控 Switch，等状态文案（WS实时 / 轮询兜底）出现，返回命中文案。"""
    deadline = time.time() + 20
    clicked = None
    while time.time() < deadline:
        try:
            txt = drv.execute_script('return document.body ? document.body.innerText : "";')
        except Exception:
            txt = ''
        if 'WS实时' in txt or '轮询兜底' in txt:
            return 'WS实时' if 'WS实时' in txt else '轮询兜底'
        if clicked is None and '日志查看' in txt:
            clicked = drv.execute_script(TOGGLE_JS)
        time.sleep(1)
    return 'none'


def snapshot(drv, acc, out, tag, dark):
    mode = 'dark' if dark else 'light'
    if dark:
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
    else:
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light');")
    drv.refresh()
    time.sleep(6)
    status = enable_realtime(drv)
    time.sleep(2)
    drv.execute_script(ACTIVITY_JS)
    injects = [inject_task_log() for _ in range(3)]
    time.sleep(12)  # 收帧窗口（含真实 TASK_LOG 事件）
    drain(drv, acc)
    state = drv.execute_script(STATE_JS)
    path = os.path.join(out, f'{tag}-{mode}.png')
    drv.save_screenshot(path)
    return {
        'screenshot': path,
        'realtime_status_text': status,
        'ws_status_text_ws': 'WS实时' in state['text'],
        'ws_status_text_polling': '轮询兜底' in state['text'],
        'rows': state['rows'],
        'task_log_marker_hits': len([f for f in acc['frames_received'] if MARKER in f]),
        'inject_results': injects,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='fix')
    args = ap.parse_args()
    out = os.path.join(HERE, 'artifacts', 'int1685', args.label)
    os.makedirs(out, exist_ok=True)

    drv = build_driver()
    acc = {'requests': [], 'ws_created': [], 'frames_received': [], 'frames_sent': [],
           'task_log_frames': [], 'failed': []}
    result = {'label': args.label, 'base': BASE}
    try:
        drv.get(BASE + '/logs')
        result['light'] = snapshot(drv, acc, out, 'logs', dark=False)
        result['dark'] = snapshot(drv, acc, out, 'logs', dark=True)
    finally:
        try:
            drain(drv, acc)
        except Exception:
            pass
        drv.quit()

    polling_requests = [u for u in acc['requests'] if 'transport=polling' in u]
    transport_reqs = sorted({u.split('/socket.io/', 1)[-1].split('&')[0] for u in acc['requests'] if '/socket.io/' in u})
    result['network'] = {
        'socket_io_request_count': len(acc['requests']),
        'socket_io_requests_sample': acc['requests'][:6],
        'polling_request_count': len(polling_requests),
        'transport_queries': transport_reqs,
        'websocket_created': acc['ws_created'],
        'frames_received': len(acc['frames_received']),
        'frames_sent': len(acc['frames_sent']),
        'task_log_frames': len(acc['task_log_frames']),
        'task_log_sample': acc['task_log_frames'][:3],
        'frames_received_sample': acc['frames_received'][:5],
        'frames_sent_sample': acc['frames_sent'][:5],
        'loading_failed': acc['failed'][:10],
    }
    with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
