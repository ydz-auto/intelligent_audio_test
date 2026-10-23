# -*- coding: utf-8 -*-
"""INT-1583 自测：音频管理页列表接口失败不得伪装成「暂无音频文件」空态。

- 正常态：/audio-import 真实数据（docker 栈 15000 → 主库 intelligent_audio_test）；
- 首屏失败：页内 fetch 打点把 POST /api/v1/audios（列表）返回 500，
  断言出现「音频列表加载失败 + 重试」、「共 — 个」，且**不得**出现「暂无音频文件」空态文案；
- 重试：解除拦截后点「重试」，列表恢复；
- 翻页失败：已加载过数据后置失败、点「下一页」，断言保留旧行 + 行内提示 + toast；
- 浅色 / 深色截图 + /api/v1/audios 请求记录。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5353')
DRIVER = os.environ.get(
    'CHROMEDRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
ART = 'tests/ui/artifacts/int1583'
os.makedirs(ART, exist_ok=True)

PATCH = r"""
window.__int1583FailAudios = localStorage.getItem('int1583FailAudios') === '1';
window.__int1583Net = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
  const path = url.split('?')[0];
  const isList = method === 'POST' && /\/api\/v1\/audios$/.test(path);
  if (isList && window.__int1583FailAudios) {
    window.__int1583Net.push({url: path, method: method, status: 500, failed: true, t: Date.now()});
    return Promise.resolve(new Response(
      JSON.stringify({code: 500, message: 'INT-1583 模拟接口失败'}),
      {status: 500, headers: {'Content-Type': 'application/json'}}
    ));
  }
  return __origFetch.apply(this, arguments).then(function(res) {
    if (isList) {
      window.__int1583Net.push({url: path, method: method, status: res.status, failed: false, t: Date.now()});
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
    # AUTH_MODE=off 的开放模式入口（默认不自动跳转时点「进入工作台」）
    enter = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if enter:
        js_click(drv, enter[0])
        try:
            WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
            time.sleep(1.0)
            return
        except Exception as exc:
            log('open-mode enter: %s' % exc)
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.get('about:blank')
    time.sleep(0.5)


def set_fail(drv, flag):
    drv.execute_script(
        "localStorage.setItem('int1583FailAudios', arguments[0] ? '1' : '0');"
        'window.__int1583FailAudios = arguments[0];', flag)


def body_text(drv):
    return drv.execute_script('return document.body.innerText')


def row_count(drv):
    return drv.execute_script(
        "return document.querySelectorAll('table tbody tr').length")


def net_log(drv):
    return drv.execute_script('return window.__int1583Net || []')


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('shot %s' % path)


def wait_text(drv, text, timeout=60):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.innerText'))


def wait_rows(drv, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: row_count(d) > 0)


def header_badge(drv):
    """页头 Title 旁的计数徽标（共 N 个）"""
    return drv.execute_script(
        "const els = [...document.querySelectorAll('span')].map(e => (e.innerText||'').trim());"
        "return els.filter(t => /^共 .* 个$/.test(t)).slice(0, 1)[0] || ''")


def retry_buttons(drv):
    return drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")


def click_next_page(drv):
    """分页条在页脚 Portal 里，JS .click() 不触发 React 合成事件，用原生 click"""
    btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='下一页']")
    if not btns:
        return False
    btns[-1].click()
    return True


def main():
    drv = webdriver.Chrome(options=_opts(), service=Service(DRIVER))
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    result = {}
    try:
        login(drv)
        set_theme(drv, 'light')

        # ── 1. 正常态（真实数据） ──
        drv.get(BASE + '/audio-import')
        wait_text(drv, '音频管理', 60)
        wait_rows(drv, 120)
        time.sleep(1.5)
        normal_rows = row_count(drv)
        normal_badge = header_badge(drv)
        result['normal'] = {'rows': normal_rows, 'badge': normal_badge}
        log('normal: rows=%s badge=%s' % (normal_rows, normal_badge))
        shot(drv, '01_audio_normal_light.png')

        # ── 2. 首屏失败态（浅色） ──
        set_fail(drv, True)
        drv.refresh()
        wait_text(drv, '音频列表加载失败', 60)
        time.sleep(1.2)
        txt = body_text(drv)
        result['error_light'] = {
            '标题_音频列表加载失败': '音频列表加载失败' in txt,
            '描述_获取失败请重试': '音频列表获取失败，请重试' in txt,
            '无「暂无音频文件」': '暂无音频文件' not in txt,
            '无导入首批音频空态': '点击「上传音频」导入首批音频' not in txt,
            '计数占位 共 — 个': header_badge(drv),
            '无 共 0 个': '共 0 个' not in txt,
            '行数': row_count(drv),
            '重试按钮数': len(retry_buttons(drv)),
            '分页条不可见': drv.execute_script(
                "return [...document.querySelectorAll('span')]"
                ".filter(e => (e.innerText||'').indexOf('共 0 条') !== -1).length === 0"),
        }
        log('error_light: %s' % json.dumps(result['error_light'], ensure_ascii=False))
        log('error_light net(failed): %s' % [
            n for n in net_log(drv) if n.get('failed')][-3:])
        shot(drv, '02_audio_error_light.png')

        # ── 3. 重试恢复（浅色） ──
        set_fail(drv, False)
        btns = retry_buttons(drv)
        if btns:
            js_click(drv, btns[0])
        wait_rows(drv, 90)
        WebDriverWait(drv, 60).until(lambda d: '音频列表加载失败' not in body_text(d))
        time.sleep(1.2)
        result['retry_light'] = {
            '错误态消失': '音频列表加载失败' not in body_text(drv),
            '行数': row_count(drv),
            '徽标': header_badge(drv),
        }
        log('retry_light: %s' % json.dumps(result['retry_light'], ensure_ascii=False))
        shot(drv, '03_audio_retry_ok_light.png')

        # ── 4. 翻页失败：保留旧数据 + 行内提示 + toast ──
        rows_before = row_count(drv)
        set_fail(drv, True)
        clicked = click_next_page(drv)
        alert_txt = ''
        toast_txt = ''
        try:
            WebDriverWait(drv, 45).until(
                lambda d: d.execute_script(
                    "return !!document.querySelector(\"[role='alert']\")"))
            alert_txt = drv.execute_script(
                "const a = document.querySelector(\"[role='alert']\");"
                "return a ? a.innerText : ''")
        except Exception as exc:
            log('alert wait: %s' % exc)
        time.sleep(0.8)
        txt = body_text(drv)
        toast_txt = '音频列表加载失败，已保留上一次加载的数据' if '已保留上一次加载的数据' in txt else ''
        result['paging_error'] = {
            '点下一页': clicked,
            '页码': drv.execute_script(
                "return [...document.querySelectorAll('span')].map(e => (e.innerText||'').trim())"
                ".filter(t => t.indexOf(' / ') !== -1).slice(0, 1)[0] || ''"),
            '行内提示': alert_txt.strip(),
            'toast': toast_txt,
            '行数（保留旧数据）': row_count(drv),
            '翻页前行数': rows_before,
            '无「暂无音频文件」': '暂无音频文件' not in txt,
            '徽标': header_badge(drv),
        }
        log('paging_error: %s' % json.dumps(result['paging_error'], ensure_ascii=False))
        shot(drv, '04_audio_paging_error_light.png')

        # 行内重试恢复（行内提示专指 role=alert，避免与 toast 文案混淆）
        set_fail(drv, False)
        btns = retry_buttons(drv)
        log('paging retry buttons: %s' % len(btns))
        if btns:
            btns[0].click()
        try:
            WebDriverWait(drv, 90).until(
                lambda d: not d.execute_script(
                    "return !!document.querySelector(\"[role='alert']\")"))
        except Exception as exc:
            log('paging retry wait: %s' % exc)
            log('body: %s' % body_text(drv)[:300].replace('\n', ' | '))
            log('net: %s' % json.dumps(net_log(drv)[-5:], ensure_ascii=False))
        time.sleep(1.2)
        result['paging_retry'] = {
            '行内提示消失': not drv.execute_script(
                "return !!document.querySelector(\"[role='alert']\")"),
            '行数': row_count(drv),
            '徽标': header_badge(drv),
        }
        log('paging_retry: %s' % json.dumps(result['paging_retry'], ensure_ascii=False))
        shot(drv, '05_audio_paging_retry_ok_light.png')

        # ── 5. 深色失败态 + 重试 ──
        set_fail(drv, True)
        set_theme(drv, 'dark')
        drv.get(BASE + '/audio-import')
        wait_text(drv, '音频列表加载失败', 60)
        time.sleep(1.2)
        txt = body_text(drv)
        result['error_dark'] = {
            'is_dark': drv.execute_script(
                "return document.documentElement.classList.contains('dark')"),
            '音频列表加载失败': '音频列表加载失败' in txt,
            '无「暂无音频文件」': '暂无音频文件' not in txt,
            '徽标': header_badge(drv),
        }
        log('error_dark: %s' % json.dumps(result['error_dark'], ensure_ascii=False))
        shot(drv, '06_audio_error_dark.png')

        set_fail(drv, False)
        btns = retry_buttons(drv)
        if btns:
            js_click(drv, btns[0])
        wait_rows(drv, 90)
        WebDriverWait(drv, 60).until(lambda d: '音频列表加载失败' not in body_text(d))
        time.sleep(1.0)
        shot(drv, '07_audio_retry_ok_dark.png')

        result['net'] = net_log(drv)[-10:]
        log('NET(/api/v1/audios) last 10: %s' % json.dumps(
            result['net'], ensure_ascii=False))
    finally:
        log('RESULT=' + json.dumps(result, ensure_ascii=False, indent=2))
        drv.quit()


if __name__ == '__main__':
    main()
