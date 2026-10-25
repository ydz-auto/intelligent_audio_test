# -*- coding: utf-8 -*-
"""INT-1860 验收脚本：音频流对象 404 时试听弹窗总时长口径。

路径（卡面复现）：任务 402 → 关联资源用例 7bac162b… → 用例详情 → 「执行结果音频」→ user_wav 试听。
断言：
  fixed（含本卡修复的构建）：总时长显示「—」，页面不出现派生值 0:36，错误文案照旧，
                            <audio> readyState=0 / error.code=4，stream-by-path 200、预签名对象 404。
  base （修复前构建）：总时长显示派生值 0:36（缺陷形态），错误文案照旧。

用法：REACT_BASE=http://127.0.0.1:15261 RUN_TAG=fixed python verify_int1860_audio_duration.py
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = 'INT-1860'
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15261')
TAG = os.environ.get('RUN_TAG', 'fixed')
ART = os.path.join(HERE, '_int1860_artifacts')
os.makedirs(ART, exist_ok=True)

DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
USER = '接线测试_admin'
PWD = 'JieXianTest@2026'
TASK_ID = 402
CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'

RESULT = {'tag': TAG, 'base': BASE, 'task': TASK_ID, 'case': CASE_ID, 'steps': {}, 'error': None}


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def new_driver():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--force-device-scale-factor=1')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_script_timeout(180)
    d.set_page_load_timeout(120)
    return d


def drain(d):
    """performance log → [(kind, url, status_or_method)]，一次读空缓冲。"""
    out = []
    try:
        for entry in d.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            m = msg.get('method', '')
            p = msg.get('params', {})
            if m == 'Network.requestWillBeSent':
                req = p.get('request', {})
                out.append(['req', req.get('url', ''), req.get('method', '')])
            elif m == 'Network.responseReceived':
                r = p.get('response', {})
                out.append(['res', r.get('url', ''), r.get('status', 0)])
    except Exception as exc:  # noqa: BLE001
        out.append(['err', str(exc), 0])
    return out


def relevant(net):
    keep = [n for n in net if 'stream-by-path' in n[1] or '/audios/' in n[1] or ':9000/' in n[1]]
    # 去重，保留每个 url 的最后一条（响应覆盖请求）
    seen = {}
    for n in keep:
        seen[(n[1], n[0])] = n
    return list(seen.values())


def login(d):
    d.get(f'{BASE}/login')
    WebDriverWait(d, 60).until(EC.presence_of_element_located((By.ID, 'username')))
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PWD)
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    WebDriverWait(d, 90).until(lambda x: '/login' not in x.current_url)
    log(f'登录成功 → {d.current_url}')
    return d.current_url


def ensure_case_list(d):
    """容器任务详情把关联用例降级成「用例清单」折叠区，先展开；普通任务直接有行。"""
    if d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']"):
        return
    clicked = False
    js_click = """
        const sp = [...document.querySelectorAll('span')]
          .find(s => s.textContent.trim() === '用例清单');
        if (!sp) return false;
        const t = sp.closest('button') || sp.parentElement;
        t.click();
        return true;
        """
    try:
        clicked = WebDriverWait(d, 60).until(lambda x: x.execute_script(js_click))
    except Exception as exc:  # noqa: BLE001
        log(f'展开用例清单失败: {exc}')
    log(f'展开「用例清单」折叠区: {clicked}')
    WebDriverWait(d, 90).until(
        lambda x: x.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']")
    )


def open_case_detail(d):
    d.get(f'{BASE}/tasks/{TASK_ID}')
    WebDriverWait(d, 90).until(
        lambda x: x.find_elements(By.CSS_SELECTOR, "h1,[data-slot='section-page-layout'],nav")
    )
    ensure_case_list(d)
    # 用例行虚拟滚动，先用搜索框定位（名称/ID 子串）
    box = WebDriverWait(d, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']"))
    )
    box.click()
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(CASE_ID)
    time.sleep(1.5)
    rows = d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row']")
    target = None
    for r in rows:
        if r.get_attribute('data-case-id') == CASE_ID:
            target = r
            break
    if target is None:
        ids = [r.get_attribute('data-case-id') for r in rows]
        raise AssertionError(f'搜索后未找到用例行，当前行 case_id={ids}')
    # 用例名按钮（打开用例详情）
    name_btn = target.find_element(By.CSS_SELECTOR, 'button.truncate')
    d.execute_script('arguments[0].scrollIntoView({block:"center"})', name_btn)
    name_btn.click()
    WebDriverWait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='case-detail-dialog']"))
    )
    log('用例详情弹窗已打开')
    return target.get_attribute('data-case-id')


def open_audio_player(d):
    dlg = d.find_element(By.CSS_SELECTOR, "[data-slot='case-detail-dialog']")
    # 等详情数据（GET /tasks/{id}/cases/{cid}/detail）回来：「执行结果音频」块出现
    WebDriverWait(d, 120).until(
        lambda x: x.execute_script(
            "return [...document.querySelectorAll(\"[data-slot='case-detail-dialog'] *\")]"
            ".some(e => e.tagName === 'P' && e.textContent.trim() === '执行结果音频')"
        )
    )
    log('「执行结果音频」块已出现')
    # 该块内优先 user_wav 行的试听按钮
    btns = d.execute_script(
        """
        const dlg = document.querySelector("[data-slot='case-detail-dialog']");
        const blocks = [...dlg.querySelectorAll('div')].filter(
          d => [...d.children].some(c => c.tagName === 'P' && c.textContent.trim() === '执行结果音频')
            && d.querySelector('button'));
        const block = blocks[blocks.length - 1];
        if (!block) return [];
        const rows = [...block.querySelectorAll('div')].filter(
          d => d.querySelector('button') && /试听/.test(d.textContent));
        const pick = rows.find(r => /user_wav/.test(r.textContent)) || rows[0];
        if (!pick) return [];
        const b = pick.querySelector('button');
        b.setAttribute('data-int1860-target', '1');
        return [pick.textContent.trim()];
        """
    )
    if not btns:
        raise AssertionError('执行结果音频块内找不到试听按钮')
    log(f'点击试听行：{btns[0]}')
    d.find_element(By.CSS_SELECTOR, "[data-int1860-target='1']").click()
    # 播放器 Dialog（第二个 dialog）出现且 <audio> 有 src
    WebDriverWait(d, 90).until(
        lambda x: x.execute_script(
            "const ds=[...document.querySelectorAll('[role=dialog]')];"
            "if (ds.length < 2) return false;"
            "const a=ds[ds.length-1].querySelector('audio');"
            "return !!a && !!(a.currentSrc || a.src);"
        )
    )
    log('试听弹窗已挂载 <audio> 且拿到播放地址')


def read_state(d):
    return d.execute_script(
        """
        const ds = [...document.querySelectorAll('[role=dialog]')];
        const dlg = ds[ds.length - 1];
        const aud = dlg.querySelector('audio');
        const durEl = dlg.querySelector("[data-testid='audio-duration']");
        const row = dlg.querySelector('.flex.items-center.justify-between.px-1.font-mono.tabular-nums');
        const spans = row ? [...row.querySelectorAll(':scope > span')].map(s => s.textContent.trim()) : [];
        const errM = (dlg.innerText || '').match(/音频播放失败[^\\n]*/);
        return {
          dialogCount: ds.length,
          title: (dlg.querySelector('h2,[role=heading]') || {}).textContent || '',
          hasTestid: !!durEl,
          durationTestid: durEl ? durEl.textContent.trim() : null,
          timeSpans: spans,
          errorText: errM ? errM[0].trim() : null,
          audio: aud ? {
            src: aud.currentSrc || aud.src || '',
            readyState: aud.readyState,
            networkState: aud.networkState,
            errorCode: aud.error ? aud.error.code : null,
            errorMessage: aud.error ? aud.error.message : null,
          } : null,
          has036: /0:36/.test(dlg.innerText || ''),
          textSample: (dlg.innerText || '').slice(0, 400)
        };
        """
    )


def wait_error(d, timeout=60):
    end = time.time() + timeout
    st = read_state(d)
    while time.time() < end:
        st = read_state(d)
        if st['errorText'] or (st['audio'] and st['audio']['errorCode']):
            break
        time.sleep(0.5)
    return st


def screenshot(d, name):
    p = os.path.join(ART, f'{TAG}-{name}.png')
    d.save_screenshot(p)
    return p


def set_theme(d, mode):
    d.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode
    )
    d.refresh()
    WebDriverWait(d, 60).until(
        lambda x: x.execute_script("return document.readyState") == 'complete'
    )
    time.sleep(2)
    return d.execute_script(
        "return {dark: document.documentElement.classList.contains('dark'),"
        " bg: getComputedStyle(document.body).backgroundColor}"
    )


def main():
    d = new_driver()
    try:
        RESULT['steps']['login_url'] = login(d)
        RESULT['steps']['index_js'] = d.execute_script(
            "const s=[...document.querySelectorAll('script[src]')].map(e=>e.getAttribute('src'));"
            "return s.filter(x=>x.includes('index.')&&x.endsWith('.js'))"
        )
        log(f"index bundle: {RESULT['steps']['index_js']}")

        # ---- 浅色 ----
        drain(d)
        open_case_detail(d)
        drain(d)
        open_audio_player(d)
        st = wait_error(d)
        net = relevant(drain(d))
        st.update({'theme': 'light'})
        RESULT['light'] = st
        RESULT['network'] = net
        log(f"浅色状态: {json.dumps({k: v for k, v in st.items() if k != 'textSample'}, ensure_ascii=False)}")
        RESULT['screenshots'] = [screenshot(d, 'light')]

        # ---- 深色（同源：localStorage 切主题 + reload 后走同一路径）----
        theme = set_theme(d, 'dark')
        RESULT['dark_theme'] = theme
        drain(d)
        open_case_detail(d)
        open_audio_player(d)
        st2 = wait_error(d)
        st2.update({'theme': 'dark', 'html_dark': theme['dark'], 'body_bg': theme['bg']})
        RESULT['dark'] = st2
        log(f"深色状态: {json.dumps({k: v for k, v in st2.items() if k != 'textSample'}, ensure_ascii=False)}")
        RESULT['screenshots'].append(screenshot(d, 'dark'))

        # ---- 判定 ----
        expect_unknown = TAG == 'fixed'
        checks = []
        dur_text = (st['durationTestid'] if st['hasTestid'] else (st['timeSpans'][-1] if st['timeSpans'] else None))
        checks.append(['总时长位', dur_text, '—' if expect_unknown else '0:36'])
        checks.append(['页面无派生值 0:36', not st['has036'], True if expect_unknown else False])
        checks.append(['错误文案', st['errorText'], '音频播放失败，请检查音频文件是否有效'])
        checks.append(['audio.readyState', st['audio']['readyState'] if st['audio'] else None, 0])
        checks.append(['audio.error.code', st['audio']['errorCode'] if st['audio'] else None, 4])
        dur_urls = [n for n in net if 'stream-by-path' in n[1]]
        obj = [n for n in net if ':9000/' in n[1]]
        checks.append(['stream-by-path 响应', [n[2] for n in dur_urls if n[0] == 'res'], [200]])
        checks.append(['预签名对象响应', [n[2] for n in obj if n[0] == 'res'], [404]])
        RESULT['checks'] = checks

        ok = True
        informational = set() if expect_unknown else {'错误文案', 'audio.readyState', 'audio.error.code'}
        for name, actual, expected in checks:
            good = (actual == expected) if not isinstance(expected, list) else (expected[0] in actual)
            if name == '错误文案':
                good = actual is not None and '音频播放失败' in str(actual)
            if name == '页面无派生值 0:36':
                good = (actual is True) if expect_unknown else (actual is False)
            tag = 'INFO' if name in informational else ('PASS' if good else 'FAIL')
            if name not in informational:
                ok = ok and good
            log(f'{tag} {name}: 实际={actual!r} 期望≈{expected!r}')
        RESULT['pass'] = ok
    except Exception as exc:  # noqa: BLE001
        RESULT['error'] = f'{type(exc).__name__}: {exc}'
        try:
            RESULT['screenshots'] = RESULT.get('screenshots', []) + [screenshot(d, 'error')]
            RESULT['error_dom'] = d.execute_script("return document.body.innerText.slice(0,1200)")
        except Exception:  # noqa: BLE001
            pass
        log(f'ERROR {RESULT["error"]}')
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        out = os.path.join(ART, f'{TAG}-result.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(RESULT, f, ensure_ascii=False, indent=2)
        log(f'结果写入 {out}')
        print(json.dumps({k: RESULT[k] for k in RESULT if k not in ('light', 'dark', 'network')},
                         ensure_ascii=False, indent=2))
    return 0 if RESULT.get('pass') else 1


if __name__ == '__main__':
    sys.exit(main())
