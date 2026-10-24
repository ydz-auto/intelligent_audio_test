# -*- coding: utf-8 -*-
"""INT-1673 P3-1 验收实测：试听播放器错误条关闭钮布局（fix / base 双向对照）。

被测组件：frontend-react/src/features/testcases/modals/audio-player-dialog.tsx 的
`Alert variant='destructive'` + 关闭钮（播放器阶段，不是「音频试听配置」配置阶段的同名错误条）。

为什么自己写：交付脚本 verify_int1673_case_p3.py 的 P3-1 注入正则用 `/testcases/\\d+/preview`，
而本库用例 id 是 UUID，注入恒不命中 → 实测落到配置阶段那条**不在本卡范围**的错误条上，
量到的是旧形态（56px / 无 data-slot）。本脚本按 UUID 兼容匹配，并按弹窗标题圈定播放器阶段。

用法：REACT_BASE/API_BASE 环境变量；输出 tests/ui/artifacts/int1673_alert/<tag>/。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15268')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
TAG = os.environ.get('RUN_TAG', 'fix')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1673_alert', TAG)
THEME_KEY = 'iatp:theme:v1:mode'

REPORT = {'env': [], 'tag': TAG, 'base': BASE, 'cases': [], 'screenshots': [], 'fail': []}

# 注入：UUID 兼容的 POST /testcases/{id}/preview 假响应（frontend 模式 + 不存在的音频地址）
PATCH = r"""
window.__fetchLog = [];
window.__int1673ForcePreview = false;
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  if (window.__int1673ForcePreview && method === 'POST' && /\/testcases\/[^/]+\/preview(\?|$)/.test(url)) {
    const body = {
      success: true, code: 0, message: 'ok',
      data: {
        test_case_id: 'forced', preview_task_id: null,
        status: 'frontend_preview_ready', message: 'INT-1673 注入：播放器错误态',
        duration: 12, playback_mode: 'frontend', audio_id: 1,
        audio_stream_url: '/api/v1/audios/download?path=__int1673_missing__.wav',
        audio_stream_urls: ['/api/v1/audios/download?path=__int1673_missing__.wav'],
      },
    };
    window.__fetchLog.push({url: url, method: method, status: 200, injected: true});
    return new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}});
  }
  const res = await __origFetch.apply(this, arguments);
  window.__fetchLog.push({url: url, method: method, status: res.status});
  return res;
};
"""


def log(msg):
    print(msg, flush=True)


def check(name, ok, detail=''):
    item = {'name': name, 'ok': bool(ok), 'detail': detail}
    REPORT['cases'].append(item)
    if not ok:
        REPORT['fail'].append({'name': name, 'detail': detail})
        log('FAIL %s | %s' % (name, detail))
    else:
        log('OK   %s%s' % (name, (' | ' + str(detail)) if detail else ''))
    return ok


def api(path, params=None):
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode() or '{}')


def env_check(tag):
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=15).read().decode())
    REPORT['env'].append({'tag': tag, 'health': health})
    log('ENV[%s]: database=%s' % (tag, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', '串库: %s' % health


def driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == chrome_major:
                        drv_path = exe
                except Exception:
                    pass
    drv = webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())
    drv.set_page_load_timeout(120)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return drv


def wait(drv, cond, timeout=60):
    return WebDriverWait(drv, timeout, poll_frequency=0.4).until(lambda d: cond(d))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def xp(drv, xpath, root=None):
    return (root or drv).find_elements(By.XPATH, xpath)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    REPORT['screenshots'].append({'name': name, 'size': size})
    log('SHOT %s size=%d' % (name, size))
    assert size > 10_000, '截图过小 %s' % name
    return path


def goto_testcases(drv, theme='light'):
    drv.get(BASE + '/')
    time.sleep(1.0)
    drv.execute_script("localStorage.setItem(%r, %r)" % (THEME_KEY, theme))
    drv.get(BASE + '/testcases')
    wait(drv, lambda d: len([b for b in xp(d, "//*[contains(@aria-label,'批量修改')]") if b.is_displayed()]) > 0, 240)
    time.sleep(1.5)
    if theme == 'dark':
        wait(drv, lambda d: 'dark' in d.execute_script('return document.documentElement.className'), 20)


def ensure_group_loaded(drv, group_name, max_more=10):
    label = '%s 批量修改' % group_name
    for _ in range(max_more):
        btns = [b for b in xp(drv, "//button[@aria-label='%s']" % label) if b.is_displayed()]
        if btns:
            return btns[0]
        more = [b for b in xp(drv, "//button[contains(., '加载更多')]") if b.is_displayed()]
        if not more:
            break
        js_click(drv, more[0])
        time.sleep(3.5)
    raise AssertionError('分组未出现：%s' % group_name)


def expand_group(drv, group_btn, timeout=180):
    header = drv.execute_script(
        "let n=arguments[0];for(let i=0;i<8&&n.parentElement;i++){n=n.parentElement;"
        "if(String(n.className||'').includes('cursor-pointer'))return n;}return null;", group_btn)
    if header is not None:
        js_click(drv, header)
    time.sleep(1.0)
    wait(drv, lambda d: len([b for b in xp(d, "//button[@aria-label='预览音频']") if b.is_displayed()]) > 0, timeout)


def find_case_preview_button(drv, case_name):
    return drv.execute_script("""
      const name = arguments[0];
      const btns = Array.from(document.querySelectorAll('button[aria-label="预览音频"]'))
        .filter(b => b.offsetParent !== null && !b.disabled);
      for (const b of btns) {
        let n = b;
        for (let i = 0; i < 10 && n.parentElement; i++) {
          n = n.parentElement;
          if ((n.textContent || '').includes(name)) return b;
        }
      }
      return null;
    """, case_name)


def dialogs(drv):
    return [d for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if d.is_displayed()]


def dialog_by_title(drv, needle):
    for d in dialogs(drv):
        t = d.find_element(By.CSS_SELECTOR, '[role="heading"]').text if xp(d, './/*[@role="heading"]') else (d.text or '')
        if needle in (t or ''):
            return d
    return None


def pick_case_with_audio():
    data = api('/api/v1/testcases', {'page': 1, 'per_page': 50})
    for it in (data.get('data') or {}).get('items') or []:
        rounds = (it.get('config') or {}).get('rounds') or []
        if any((r.get('audios') or []) for r in rounds):
            return it.get('name'), it.get('group_name')
    return None, None


def measure_player_alert(drv, theme):
    dlg = dialog_by_title(drv, '测试用例预览')
    assert dlg is not None, '未进入播放器阶段（标题「测试用例预览」）'
    alert = None
    for a in dlg.find_elements(By.CSS_SELECTOR, '[role="alert"]'):
        if a.is_displayed():
            alert = a
    assert alert is not None, '播放器内没有错误条'
    metrics = drv.execute_script("""
      const a = arguments[0];
      const b = a.querySelector('button[aria-label="关闭错误提示"]');
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      return {
        alert: {x: ar.x, y: ar.y, w: ar.width, h: ar.height, right: ar.right, bottom: ar.bottom},
        button: {x: br.x, y: br.y, w: br.width, h: br.height, right: br.right, bottom: br.bottom},
        slot: b.getAttribute('data-slot'),
        cls: b.className,
        text: (a.textContent || '').trim(),
        title: (document.querySelector('[role="dialog"][data-slot], [role="dialog"]') || {}).textContent || '',
      };
    """, alert)
    REPORT['cases'].append({'measure_%s' % theme: metrics})
    log('MEASURE[%s] %s' % (theme, json.dumps(metrics, ensure_ascii=False)))
    return dlg, alert, metrics


def run_theme(drv, theme):
    log('== P3-1 播放器错误条（%s）' % theme)
    name = REPORT['case_name']
    group = REPORT['case_group']
    goto_testcases(drv, theme)
    drv.execute_script('window.__int1673ForcePreview = true')
    btn = ensure_group_loaded(drv, group)
    expand_group(drv, btn)
    time.sleep(1.0)
    target = find_case_preview_button(drv, name)
    if not check('[%s] 定位到带音频用例「%s」的预览音频钮' % (theme, name), target is not None, name):
        return
    js_click(drv, target)
    wait(drv, lambda d: dialog_by_title(d, '音频试听配置') is not None, 40)
    cfg = dialog_by_title(drv, '音频试听配置')
    start = [b for b in cfg.find_elements(By.XPATH, ".//button[contains(., '开始试听')]") if b.is_displayed()][0]
    js_click(drv, start)
    # 进入播放器阶段 + 错误条出现（注入已被消费）
    wait(drv, lambda d: dialog_by_title(d, '测试用例预览') is not None
         and any(a.is_displayed() for a in dialog_by_title(d, '测试用例预览').find_elements(By.CSS_SELECTOR, '[role="alert"]')), 60)
    time.sleep(0.8)

    injected = [r for r in (drv.execute_script('return window.__fetchLog || []') or []) if r.get('injected')]
    check('[%s] 注入的 preview 假响应被消费（量的是播放器阶段而非配置阶段）' % theme, len(injected) == 1, injected)

    dlg, alert, m = measure_player_alert(drv, theme)
    shot(drv, 'player_error_bar_%s.png' % theme)
    check('[%s] 错误条单行高度（≤44px；修复前 56px 两行）' % theme, m['alert']['h'] <= 44, m['alert']['h'])
    check('[%s] 关闭钮挂 Alert 约定动作位 data-slot=alert-action' % theme, m['slot'] == 'alert-action', m['slot'])
    check('[%s] 关闭钮绝对定位（absolute）' % theme, 'absolute' in (m['cls'] or ''), m['cls'])
    check('[%s] 关闭钮贴右上（右间距≤20px 且 顶间距≤12px）' % theme,
          (m['alert']['right'] - m['button']['right']) <= 20 and abs(m['button']['y'] - m['alert']['y']) <= 12,
          {'right_gap': m['alert']['right'] - m['button']['right'], 'top_gap': m['button']['y'] - m['alert']['y']})
    check('[%s] 关闭钮自身尺寸正常（≤24×24，不再拉满整行）' % theme,
          m['button']['w'] <= 24 and m['button']['h'] <= 24, {'w': m['button']['w'], 'h': m['button']['h']})
    check('[%s] 关闭钮不占满错误条宽度（<50%% 条宽）' % theme,
          m['button']['w'] < m['alert']['w'] * 0.5, {'button_w': m['button']['w'], 'alert_w': m['alert']['w']})

    # 真坐标点击错误文案区（非关闭钮）→ 不应关闭（CDP 命中测试，不是 element.click 旁路）
    px = int(m['alert']['x'] + 40)
    py = int(m['alert']['y'] + m['alert']['h'] / 2)
    for kind in ('mousePressed', 'mouseReleased'):
        drv.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': kind, 'x': px, 'y': py, 'button': 'left', 'clickCount': 1,
        })
    time.sleep(0.6)
    still = len([a for a in dlg.find_elements(By.CSS_SELECTOR, '[role="alert"]') if a.is_displayed()])
    check('[%s] 点错误文案区不关闭错误条' % theme, still >= 1, still)

    # 点关闭钮 → 关闭，且播放器弹窗仍在
    js_click(drv, alert.find_element(By.CSS_SELECTOR, 'button[aria-label="关闭错误提示"]'))
    time.sleep(0.8)
    gone = len([a for a in dlg.find_elements(By.CSS_SELECTOR, '[role="alert"]') if a.is_displayed()])
    check('[%s] 点关闭钮后错误条消失' % theme, gone == 0, gone)
    check('[%s] 关闭错误条后播放器弹窗仍在（只关提示）' % theme, dialog_by_title(drv, '测试用例预览') is not None, '')
    shot(drv, 'player_after_close_%s.png' % theme)


def main():
    os.makedirs(ART, exist_ok=True)
    env_check('开工')
    name, group = pick_case_with_audio()
    REPORT['case_name'] = name
    REPORT['case_group'] = group
    check('找到带音频的真实用例（只读，不改数据）', bool(name) and bool(group), (name, group))
    drv = driver()
    try:
        run_theme(drv, 'light')
        run_theme(drv, 'dark')
        env_check('交付前')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    out = os.path.join(ART, 'report_%s.json' % TAG)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    log('REPORT %s' % out)
    log('FAILS: %d' % len(REPORT['fail']))
    for item in REPORT['fail']:
        log(' - %s | %s' % (item['name'], item['detail']))
    return 1 if REPORT['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
