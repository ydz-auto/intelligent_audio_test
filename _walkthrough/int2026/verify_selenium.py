# -*- coding: utf-8 -*-
"""INT-2026 验收：用例编辑抽屉横向步骤导航编号是否连续（浏览器实测，独立于实施者脚本）。

- 前端：本 run dev server http://127.0.0.1:5627（新 Vue 接线代码 agent/vue-c/int-2026）
- 后端：docker 常驻网关 http://127.0.0.1:15000（真实库 intelligent_audio_test），只读
- 断言可见状态：元素 rect / computed style / 文本，不只看 textContent
- 场景：新增 API（1..4）、新增端到端（1..5）、编辑真实端到端用例（1..5），浅/深各截图
"""
import json
import os
import sys
import time

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:5627')
GATEWAY = 'http://127.0.0.1:15000'
OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.environ.get('OUT_DIR', 'shots_selenium'))
CHROMEDRIVER = os.environ.get(
    'UI_CHROMEDRIVER',
    r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe')
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

os.makedirs(OUT, exist_ok=True)
result = {'scenarios': [], 'network': [], 'health': {}}


def log(*a):
    print(*a, flush=True)


JS_TOC = r"""
const overlays = [...document.querySelectorAll('.modal-overlay')];
const root = overlays.length ? overlays[overlays.length - 1] : null;
if (!root) return { ok: false, reason: 'no modal overlay' };
const toc = root.querySelector('.rce-step-toc');
if (!toc) return { ok: false, reason: 'no toc' };
const items = [...toc.querySelectorAll('.rce-toc-item')].map(el => {
  const numEl = el.querySelector('.rce-toc-num');
  const labelEl = el.querySelector('.rce-toc-label');
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const ncs = numEl ? getComputedStyle(numEl) : null;
  return {
    num: (numEl?.textContent || '').trim(),
    label: (labelEl?.textContent || '').trim(),
    visible: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.5,
    rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    active: el.classList.contains('active'),
    color: ncs ? ncs.color : null,
  };
});
// 步骤内容块按文档顺序（评估维度 / 参考参数）核顺序
const bodyIds = [...root.querySelectorAll('.rce-step, #step-eval, #step-algo, #step-audio, #step-noise')]
  .map(el => el.id || el.className).filter(Boolean);
return { ok: true, modalTitle: (root.querySelector('.modal-title, .modal-header')?.textContent || '').trim().slice(0, 40), items, bodyIds };
"""

JS_CLICK_TEXT = r"""
const text = arguments[0], scope = arguments[1] || 'button';
const root = document.querySelectorAll('.modal-overlay').length
  ? [...document.querySelectorAll('.modal-overlay')].slice(-1)[0] : document;
const els = [...root.querySelectorAll(scope)];
const el = els.find(x => (x.textContent || '').trim().includes(text));
if (!el) return false;
el.scrollIntoView({ block: 'center' });
el.click();
return true;
"""

JS_CLICK_CARD_ACTION = r"""
const layer = document.querySelectorAll('.modal-overlay').length ? [...document.querySelectorAll('.modal-overlay')].slice(-1)[0] : document;
const btn = layer.querySelector('button[title="编辑用例"]');
if (!btn) return false;
// 卡片操作默认悬停显示：直接派发 mouseover 再点
btn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
btn.scrollIntoView({ block: 'center' });
btn.click();
return true;
"""

JS_HAS_TOC = "return !!document.querySelector('.modal-overlay:last-of-type .rce-step-toc') || !!document.querySelector('.rce-step-toc');"
JS_CLOSE_MODAL = r"""
const overlays = [...document.querySelectorAll('.modal-overlay')];
const root = overlays[overlays.length - 1];
if (!root) return 'no-modal';
const btn = root.querySelector('.modal-close, [class*="close-btn"], [aria-label="关闭"]');
if (btn) { btn.click(); return 'closed'; }
return 'no-close-btn';
"""
JS_SET_DARK = "document.documentElement.classList.%s('dark')"


def shot(driver, name):
    path = os.path.join(OUT, name + '.png')
    driver.save_screenshot(path)
    return path


def wait(cond, timeout=30, interval=0.4):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def toc_state(driver):
    return driver.execute_script(JS_TOC)


def assert_toc(scenario, expected_pairs, expected_modal_kind):
    st = toc_state(driver_ref[0])
    if not st.get('ok'):
        return {'scenario': scenario, 'pass': False, 'reason': st.get('reason')}
    items = st['items']
    nums = [i['num'] for i in items]
    labels = [i['label'] for i in items]
    exp_nums = [str(i + 1) for i in range(len(expected_pairs))]
    exp_labels = [p for p in expected_pairs]
    visible_ok = all(i['visible'] for i in items)
    checks = {
        'count': len(items) == len(expected_pairs),
        'nums_continuous': nums == exp_nums,
        'labels': labels == exp_labels,
        'all_visible': visible_ok,
        'modal_kind': expected_modal_kind in (st.get('modalTitle') or ''),
    }
    return {
        'scenario': scenario,
        'pass': all(checks.values()),
        'checks': checks,
        'nums': nums,
        'labels': labels,
        'items': items,
        'modalTitle': st.get('modalTitle'),
        'bodyIds': st.get('bodyIds'),
    }


def wait_toc_ready(driver):
    def cond():
        st = toc_state(driver)
        return st.get('ok') and len(st['items']) > 0
    ok = wait(cond, 40)
    time.sleep(1.2)
    return ok


def capture_light_dark(driver, tag):
    driver.execute_script(JS_SET_DARK % 'remove')
    time.sleep(1.2)
    driver.execute_script("const t=document.querySelector('.rce-step-toc'); t && t.scrollIntoView({block:'center'});")
    time.sleep(0.8)
    l = shot(driver, tag + '-light')
    driver.execute_script(JS_SET_DARK % 'add')
    time.sleep(1.2)
    driver.execute_script("const t=document.querySelector('.rce-step-toc'); t && t.scrollIntoView({block:'center'});")
    time.sleep(0.6)
    d = shot(driver, tag + '-dark')
    driver.execute_script(JS_SET_DARK % 'remove')
    time.sleep(0.6)
    return [l, d]


def click_badge(driver, label):
    ok = driver.execute_script("""
    const els = [...document.querySelectorAll('.badge-filter__badge')];
    const el = els.find(x => (x.textContent || '').trim() === arguments[0]);
    if (!el) return false; el.click(); return true;
    """, label)
    time.sleep(2.5)
    return ok


def close_modal(driver):
    r = driver.execute_script(JS_CLOSE_MODAL)
    time.sleep(1.5)
    return r


driver_ref = [None]


def main():
    # 0) 真实库防串库核对
    h = httpx.get(GATEWAY + '/health', timeout=10).json()
    result['health']['start'] = h
    log('[health]', h)
    if h.get('database') != 'intelligent_audio_test':
        log('FATAL: gateway not on real db:', h)
        sys.exit(2)

    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1080')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    service = Service(executable_path=CHROMEDRIVER)
    driver = webdriver.Chrome(service=service, options=opts)
    driver_ref[0] = driver
    try:
        # 1) 登录
        driver.get(BASE + '/#/login')
        wait(lambda: driver.find_elements('css selector', "input[placeholder='请输入用户名或邮箱']"), 40)
        u = driver.find_element('css selector', "input[placeholder='请输入用户名或邮箱']")
        p = driver.find_element('css selector', "input[placeholder='请输入密码']")
        u.clear(); u.send_keys(USERNAME)
        p.clear(); p.send_keys(PASSWORD)
        driver.find_element('css selector', 'button.login-btn').click()
        logged = wait(lambda: 'login' not in driver.current_url, 40)
        log('[login]', logged, driver.current_url)
        if not logged:
            result['login'] = False
            raise SystemExit('login failed')

        # 2) 用例列表
        driver.get(BASE + '/#/testcases')
        wait(lambda: driver.find_elements('css selector', '.badge-filter__badge'), 60)
        time.sleep(3)

        # --- 场景 A：新增 · API ---
        api_filter = click_badge(driver, 'API测试')
        opened = driver.execute_script(JS_CLICK_TEXT, '新增用例', 'button')
        ok = wait_toc_ready(driver)
        log('[A] filter', api_filter, 'open', opened, 'toc', ok)
        if ok:
            result['scenarios'].append(assert_toc(
                'A·新增用例·API', ['算法参数', '音频列表', '评估维度', '参考参数'], '新增'))
            result['shots_A'] = capture_light_dark(driver, 'A-add-api')
        close_modal(driver)

        # --- 场景 B：新增 · 端到端 ---
        e2e_filter = click_badge(driver, '端到端测试')
        opened = driver.execute_script(JS_CLICK_TEXT, '新增用例', 'button')
        ok = wait_toc_ready(driver)
        log('[B] filter', e2e_filter, 'open', opened, 'toc', ok)
        if ok:
            result['scenarios'].append(assert_toc(
                'B·新增用例·端到端', ['算法参数', '音频列表', '噪声 & 干扰', '评估维度', '参考参数'], '新增'))
            result['shots_B'] = capture_light_dark(driver, 'B-add-e2e')
        close_modal(driver)

        # --- 场景 C：编辑真实端到端用例 ---
        click_badge(driver, '端到端测试')
        hovered = driver.execute_script(JS_CLICK_CARD_ACTION)
        ok = wait_toc_ready(driver)
        log('[C] edit-click', hovered, 'toc', ok)
        if ok:
            result['scenarios'].append(assert_toc(
                'C·编辑真实端到端用例', ['算法参数', '音频列表', '噪声 & 干扰', '评估维度', '参考参数'], '编辑'))
            result['shots_C'] = capture_light_dark(driver, 'C-edit-e2e')
            # 交互：点第 5 步（参考参数）应激活该步
            sel = driver.execute_script(r"""
            const root = [...document.querySelectorAll('.modal-overlay')].slice(-1)[0];
            const items = [...root.querySelectorAll('.rce-toc-item')];
            items[items.length - 1].click();
            return items[items.length - 1].className;
            """)
            time.sleep(1.2)
            st = toc_state(driver)
            result['click_ref_active'] = {
                'class_after_click': sel,
                'active_labels': [i['label'] for i in st['items'] if i['active']],
            }
        close_modal(driver)

        # 3) Network 取证
        logs = driver.get_log('performance')
        for e in logs:
            try:
                m = json.loads(e['message'])['message']
            except Exception:
                continue
            if m['method'] != 'Network.responseReceived':
                continue
            r = m['params']['response']
            if '/api/' in r['url'] or '/health' in r['url']:
                result['network'].append({'status': r['status'], 'url': r['url'][:160]})
        result['health']['end'] = httpx.get(GATEWAY + '/health', timeout=10).json()
    finally:
        driver.quit()

    with open(os.path.join(OUT, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log('=== SUMMARY ===')
    for s in result['scenarios']:
        log(s['scenario'], 'PASS' if s['pass'] else 'FAIL', s.get('nums'), s.get('checks'))
    log('network', len(result['network']), 'records; non-200:',
        [n for n in result['network'] if n['status'] >= 400])
    log('health', result['health'].get('end', {}).get('database'))


if __name__ == '__main__':
    main()
