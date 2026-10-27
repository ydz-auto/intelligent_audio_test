# -*- coding: utf-8 -*-
"""INT-2097 验收：「连接你的 agent」按钮图标/文案垂直居中。

浏览器实测两个落点 + 灵犀Agent 魔法按钮对照：
- 落点① /ai-chat 右上角非 compact 按钮（a[aria-label=打开连接你的 agent]）
- 落点② Agent 工作台浮窗头行 compact 按钮（浮窗 fixed.right-4.bottom-4.z-50 内）
- 对照：灵犀Agent 魔法按钮（button[aria-label=打开全局 Agent 工作台]，<button> 浏览器默认垂直居中）

用法：
  D:/00_env/conda_envs/intelligent_audio_test/python.exe verify_int2097.py --base http://127.0.0.1:15277 --side fix
  D:/00_env/conda_envs/intelligent_audio_test/python.exe verify_int2097.py --base http://127.0.0.1:15173 --side before
"""
import argparse
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from PIL import Image

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2097')
SHOTS = os.path.join(ART, 'shots')
os.makedirs(SHOTS, exist_ok=True)

MEASURE_ALL_JS = """return (() => {
  const anchors = [...document.querySelectorAll('a[aria-label="打开连接你的 agent"]')];
  return anchors.map(a => {
    const r = a.getBoundingClientRect();
    const span = a.querySelector('span.ai-discount-word');
    const s = span.getBoundingClientRect();
    const aCenter = r.top + r.height / 2;
    const sCenter = s.top + s.height / 2;
    return {
      inWorkbench: !!a.closest('div.fixed.right-4.bottom-4'),
      compact: a.className.indexOf('h-7') !== -1,
      dev: Math.round(Math.abs(aCenter - sCenter) * 100) / 100,
      a: { top: Math.round(r.top * 100) / 100, height: Math.round(r.height * 100) / 100,
           left: Math.round(r.left * 100) / 100, width: Math.round(r.width * 100) / 100 },
      c: { top: Math.round(s.top * 100) / 100, height: Math.round(s.height * 100) / 100,
           left: Math.round(s.left * 100) / 100, width: Math.round(s.width * 100) / 100 },
    };
  });
})()"""

MEASURE_MAGIC_JS = """return (() => {
  const btn = document.querySelector('button[aria-label="打开全局 Agent 工作台"]');
  if (!btn) return null;
  const r = btn.getBoundingClientRect();
  const span = btn.querySelector('span.ai-discount-word');
  const s = span.getBoundingClientRect();
  const aCenter = r.top + r.height / 2;
  const sCenter = s.top + s.height / 2;
  return {
    dev: Math.round(Math.abs(aCenter - sCenter) * 100) / 100,
    a: { top: Math.round(r.top * 100) / 100, height: Math.round(r.height * 100) / 100,
         left: Math.round(r.left * 100) / 100, width: Math.round(r.width * 100) / 100 },
    c: { top: Math.round(s.top * 100) / 100, height: Math.round(s.height * 100) / 100,
         left: Math.round(s.left * 100) / 100, width: Math.round(s.width * 100) / 100 },
  };
})()"""

BUNDLE_JS = """return [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src'))"""


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_script_timeout(90)
    return d


def js(d, code, *args):
    return d.execute_script(code, *args)


def wait_vis(d, css, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(0.4)
    return None


def login(d, base):
    d.get(base + '/login')
    wait_vis(d, 'form', timeout=30)
    time.sleep(1.0)
    uname = d.find_element(By.ID, 'username')
    pwd = d.find_element(By.ID, 'password')
    uname.clear()
    pwd.clear()
    uname.send_keys('admin')
    pwd.send_keys('admin123')
    d.find_element(By.CSS_SELECTOR, 'button[type=submit]').click()
    end = time.time() + 40
    while time.time() < end:
        if '/login' not in d.current_url:
            break
        time.sleep(0.5)
    time.sleep(2.0)
    if '/login' in d.current_url:
        raise AssertionError('登录失败，仍在 /login：%s' % d.current_url)
    token = js(d, "return localStorage.getItem('iatp:auth:token:v1')")
    if not token:
        raise AssertionError('登录后无 token')
    return token


def set_theme(d, mode):
    js(d, "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    time.sleep(0.5)


def goto(d, base, path, ready_css=None, timeout=40):
    d.get(base + path)
    if ready_css:
        if wait_vis(d, ready_css, timeout) is None:
            raise AssertionError('页面未就绪：%s 等待 %s 超时' % (path, ready_css))
    else:
        time.sleep(3)


def crop_zoom(d, el, out, margin=60, scale=2):
    """截图按钮区域并 2x 放大：元素 rect 外扩 margin，再按 scale 放大。"""
    r = el.rect
    vw = js(d, 'return window.innerWidth')
    vh = js(d, 'return window.innerHeight')
    x = max(0, int(r['x'] - margin))
    y = max(0, int(r['y'] - margin))
    x2 = min(vw, int(r['x'] + r['width'] + margin))
    y2 = min(vh, int(r['y'] + r['height'] + margin))
    shot = os.path.join(SHOTS, '_raw_' + out)
    d.save_screenshot(shot)
    im = Image.open(shot)
    region = im.crop((x, y, x2, y2))
    region = region.resize((region.width * scale, region.height * scale), Image.LANCZOS)
    region.save(os.path.join(SHOTS, out))
    os.remove(shot)
    return out


def drain(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def net_api(d):
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
            method = msg.get('method', '')
            if method in ('Network.requestWillBeSent', 'Network.responseReceived'):
                params = msg.get('params', {})
                req = params.get('request', {}) if method == 'Network.requestWillBeSent' else None
                url = params.get('response', {}).get('url') or (req or {}).get('url')
                if url and '/api/' in url:
                    item = {
                        't': entry['timestamp'],
                        'method': req.get('method') if req else None,
                        'url': url,
                        'status': params.get('response', {}).get('status') if method == 'Network.responseReceived' else None,
                    }
                    out.append(item)
        except Exception:
            continue
    return out


def collect_severe(d):
    try:
        logs = d.get_log('browser')
    except Exception:
        return []
    return [{'level': e['level'], 'msg': e['message']} for e in logs if e.get('level') == 'SEVERE']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15277')
    ap.add_argument('--side', default='fix', choices=['fix', 'before'])
    args = ap.parse_args()
    base = args.base
    side = args.side

    d = driver()
    result = {'side': side, 'base': base, 'themes': {}, 'severe': [], 'network': [], 'bundle': {}}
    try:
        token = login(d, base)
        result['logged_in'] = True
        result['token_len'] = len(token)
        result['bundle_after_login'] = js(d, BUNDLE_JS)

        for mode in ('light', 'dark'):
            key = mode
            result['themes'][key] = {}
            set_theme(d, mode)
            # 工作台 open 态持久化到 localStorage，切主题导航后会恢复为打开；
            # 每轮先清掉，保证落点①测量时浮窗关闭、点魔法按钮是「打开」语义。
            js(d, "localStorage.removeItem('iatp:agent-workbench:v1')")
            time.sleep(0.3)

            # 落点① /ai-chat 右上角（工作台未打开，只有页面头按钮）
            goto(d, base, '/ai-chat', ready_css='a[aria-label="打开连接你的 agent"]')
            time.sleep(1.0)
            anchors = js(d, MEASURE_ALL_JS)
            header = [a for a in anchors if not a['inWorkbench']]
            assert header, '未找到 /ai-chat 头按钮'
            header = header[0]
            result['themes'][key]['header'] = header
            el = d.find_element(By.CSS_SELECTOR, 'a[aria-label="打开连接你的 agent"]')
            shot_h = crop_zoom(d, el, 'lot1_%s.png' % mode)
            result['themes'][key]['header_shot'] = shot_h

            # 打开 Agent 工作台 → 落点② 头行 compact 按钮
            drain(d)
            magic = wait_vis(d, 'button[aria-label="打开全局 Agent 工作台"]', timeout=15)
            js(d, 'arguments[0].click()', magic)
            time.sleep(2.0)
            wb = wait_vis(d, 'div.fixed.right-4.bottom-4.z-50 a[aria-label="打开连接你的 agent"]', timeout=15)
            if wb is None:
                raise AssertionError('工作台浮窗未出现 compact 按钮')
            anchors2 = js(d, MEASURE_ALL_JS)
            wb_item = [a for a in anchors2 if a['inWorkbench']]
            assert wb_item, '未找到浮窗内 compact 按钮'
            result['themes'][key]['workbench'] = wb_item[0]
            # 浮动窗口在右下角，滚动到可见后再截
            js(d, 'arguments[0].scrollIntoView({block:"center"})', wb)
            time.sleep(0.5)
            shot_w = crop_zoom(d, wb, 'lot2_%s.png' % mode)
            result['themes'][key]['workbench_shot'] = shot_w

            # 灵犀Agent 魔法按钮对照
            result['themes'][key]['magic'] = js(d, MEASURE_MAGIC_JS)

            # 主题断言
            html_cls = js(d, 'return document.documentElement.className')
            if mode == 'dark':
                assert 'dark' in html_cls, '深色未生效 html.class=%r' % html_cls
            else:
                assert 'dark' not in html_cls, '浅色未生效 html.class=%r' % html_cls
            result['themes'][key]['html_class'] = html_cls

            # 主题切回浅色再收尾（避免影响后续）
            set_theme(d, 'light')

        # 网络（真实 /api 请求记录，无 mock 残留）
        drain(d)
        goto(d, base, '/ai-chat', ready_css='a[aria-label="打开连接你的 agent"]')
        time.sleep(2.0)
        result['network'] = net_api(d)
        result['severe'] = collect_severe(d)
        result['bundle_end'] = js(d, BUNDLE_JS)
    finally:
        d.quit()

    out = os.path.join(ART, 'result_%s.json' % side)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'side': side, 'out': out, 'themes': result['themes'],
                      'severe_count': len(result['severe']),
                      'net_count': len(result['network'])}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
