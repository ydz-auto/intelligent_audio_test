# -*- coding: utf-8 -*-
"""INT-1560 自测：标签管理页 / 用例页标签 facet 的错误态与重试。

- 正常态：/TagManagement 真实数据（docker 栈 15000 → 主库 intelligent_audio_test）；
- 失败态：页内 fetch 打点拦截 /api/v1/tags*（返回 reject，模拟接口失败），
  断言出现「分类加载失败 / 标签加载失败 + 重试」，且**不得**出现「暂无标签 / 创建第一个标签」；
- 重试：解除拦截后点「重试」，数据恢复；
- 用例页标签 facet 同样断言；
- 浅色 + 深色截图 + /api/v1/tags 请求记录。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
ART = 'tests/ui/artifacts/int1560'
os.makedirs(ART, exist_ok=True)

PATCH = r"""
window.__int1560FailTags = localStorage.getItem('int1560FailTags') === '1';
window.__int1560Net = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  const isTags = url.indexOf('/api/v1/tags') !== -1;
  if (isTags && window.__int1560FailTags) {
    window.__int1560Net.push({url: url, method: method, status: 0, failed: true, t: Date.now()});
    return Promise.reject(new TypeError('Failed to fetch (INT-1560 模拟接口失败)'));
  }
  return __origFetch.apply(this, arguments).then(function(res) {
    if (isTags) {
      window.__int1560Net.push({url: url, method: method, status: res.status, failed: false, t: Date.now()});
    }
    return res;
  });
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2.5)
    if '/login' not in drv.current_url:
        return
    try:
        WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
    except Exception as exc:
        log('login form: %s' % exc)
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.get('about:blank')
    time.sleep(0.5)


def set_fail(drv, flag):
    drv.execute_script(
        "localStorage.setItem('int1560FailTags', arguments[0] ? '1' : '0');"
        'window.__int1560FailTags = arguments[0];', flag)


def body_text(drv):
    return drv.execute_script('return document.body.innerText')


def net_log(drv):
    return drv.execute_script('return window.__int1560Net || []')


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('shot %s' % path)


def wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.innerText'))


def api_get(drv, path):
    js = """
    const cb = arguments[arguments.length - 1];
    fetch(arguments[0]).then(async r => cb({status: r.status, body: await r.text()}))
      .catch(e => cb({status: 0, body: String(e)}));
    """
    raw = drv.execute_async_script(js, path)
    try:
        payload = json.loads(raw['body'])
    except Exception:
        payload = raw['body']
    data = payload.get('data') if isinstance(payload, dict) else payload
    return raw['status'], data


def open_tags_page(drv):
    drv.get(BASE + '/TagManagement')
    wait_text(drv, '标签管理', 45)
    time.sleep(2)


def tag_rows(drv):
    return drv.execute_script(
        "return document.querySelectorAll(\"table tbody tr\").length")


def main():
    drv = webdriver.Chrome(options=_opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    result = {}
    try:
        login(drv)
        # 浅色为基线
        set_theme(drv, 'light')

        # ── 1. 正常态（真实数据） ──
        open_tags_page(drv)
        status, tags = api_get(drv, '/api/v1/tags')
        total_api = len(tags.get('items', [])) if isinstance(tags, dict) else -1
        WebDriverWait(drv, 30).until(lambda d: tag_rows(d) > 0)
        rows = tag_rows(drv)
        txt = body_text(drv)
        log('normal: api_status=%s api_total=%s rendered_rows=%s' % (status, total_api, rows))
        log('normal header: %s' % [l for l in txt.splitlines() if '个标签' in l][:2])
        result['normal'] = {'api_status': status, 'api_total': total_api, 'rows': rows}
        shot(drv, '01_tags_normal_light.png')

        # ── 2. 接口失败态（浅色） ──
        set_fail(drv, True)
        drv.refresh()
        wait_text(drv, '标签加载失败', 45)
        time.sleep(1)
        txt = body_text(drv)
        checks = {
            '分类加载失败': '分类加载失败' in txt,
            '标签加载失败': '标签加载失败' in txt,
            '无「暂无标签」': '暂无标签' not in txt,
            '无「创建第一个标签」': '创建第一个标签' not in txt,
            '计数占位 共 — 个': '共 — 个' in txt,
            '计数占位 共 — 个标签': '共 — 个标签' in txt,
            '重试按钮': drv.execute_script(
                "return document.querySelectorAll(\"button\").length && "
                "[...document.querySelectorAll('button')].filter(b => (b.innerText||'').trim() === '重试').length"),
        }
        result['error_light'] = checks
        log('error_light: %s' % checks)
        log('error_light net: %s' % [n for n in net_log(drv) if n.get('failed')][-4:])
        shot(drv, '02_tags_error_light.png')

        # ── 3. 重试恢复（浅色，两张卡各自的重试都点一遍） ──
        set_fail(drv, False)
        retry_btns = drv.find_elements(
            By.XPATH, "//button[normalize-space(.)='重试']")
        log('retry buttons: %s' % len(retry_btns))
        # 从后往前点（右侧标签表 → 左侧分类树），引用失效也不影响
        for _ in range(len(retry_btns)):
            btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
            if not btns:
                break
            js_click(drv, btns[-1])
            time.sleep(1.0)
        WebDriverWait(drv, 40).until(lambda d: '加载失败' not in body_text(d))
        time.sleep(1.5)
        txt = body_text(drv)
        result['retry_light'] = {
            'error_gone': '标签加载失败' not in txt,
            'rows': tag_rows(drv),
            'header': [l for l in txt.splitlines() if '个标签' in l][:1],
        }
        log('retry_light: %s' % result['retry_light'])
        shot(drv, '03_tags_retry_ok_light.png')

        # ── 4. 深色失败态 + 重试 ──
        set_fail(drv, True)
        set_theme(drv, 'dark')
        open_tags_page(drv)
        wait_text(drv, '标签加载失败', 45)
        time.sleep(1)
        txt = body_text(drv)
        result['error_dark'] = {
            'is_dark': drv.execute_script(
                "return document.documentElement.classList.contains('dark')"),
            '标签加载失败': '标签加载失败' in txt,
            '无「暂无标签」': '暂无标签' not in txt,
        }
        log('error_dark: %s' % result['error_dark'])
        shot(drv, '04_tags_error_dark.png')

        set_fail(drv, False)
        for _ in range(3):
            btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
            if not btns:
                break
            js_click(drv, btns[-1])
            time.sleep(1.0)
        WebDriverWait(drv, 40).until(lambda d: '加载失败' not in body_text(d))
        time.sleep(1.2)
        shot(drv, '05_tags_retry_ok_dark.png')

        # ── 5. 用例页标签 facet 失败态（浅色） ──
        set_fail(drv, True)
        set_theme(drv, 'light')
        drv.get(BASE + '/testcases')
        wait_text(drv, '用例', 60)
        time.sleep(3)
        trigger = WebDriverWait(drv, 30).until(
            lambda d: d.find_elements(
                By.XPATH, "//button[.//span[normalize-space(.)='标签']]"))
        js_click(drv, trigger[0])
        time.sleep(1.2)
        txt = body_text(drv)
        result['facet_error'] = {
            '标签加载失败': txt.count('标签加载失败'),
            '无「暂无标签」': '暂无标签' not in txt,
        }
        log('facet_error: %s' % result['facet_error'])
        shot(drv, '06_facet_error_light.png')

        # 重试
        set_fail(drv, False)
        facet_retry = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
        log('facet retry buttons: %s' % len(facet_retry))
        if facet_retry:
            js_click(drv, facet_retry[-1])
            WebDriverWait(drv, 40).until(
                lambda d: '标签加载失败' not in d.execute_script(
                    'return document.body.innerText'))
            # 等待 facet 选项回来（分类组头「未分类」或任一标签名）
            WebDriverWait(drv, 40).until(
                lambda d: d.execute_script(
                    "const p = document.querySelector(\"[data-slot='popover-content']\");"
                    "return p ? (p.innerText || '').indexOf('暂无标签') === -1 && "
                    "(p.innerText || '').trim().length > 2 : false"))
            time.sleep(0.8)
        txt = body_text(drv)
        facet_pop = drv.execute_script(
            "const p = document.querySelector(\"[data-slot='popover-content']\");"
            "return p ? p.innerText : ''")
        result['facet_retry'] = {
            '标签加载失败_remaining': txt.count('标签加载失败'),
            'popover_text_head': (facet_pop or '')[:120],
            'has_options': '暂无标签' not in (facet_pop or '')
            and len((facet_pop or '').strip()) > 2,
        }
        log('facet_retry: %s' % result['facet_retry'])
        shot(drv, '07_facet_retry_ok_light.png')

        result['net'] = [n for n in net_log(drv)]
        log('NET(tags) last 12: %s' % json.dumps(result['net'][-12:], ensure_ascii=False))
    finally:
        log('RESULT=' + json.dumps(result, ensure_ascii=False, indent=2))
        drv.quit()


if __name__ == '__main__':
    main()
