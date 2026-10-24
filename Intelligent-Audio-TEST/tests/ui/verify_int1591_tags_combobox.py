# -*- coding: utf-8 -*-
"""INT-1591 浏览器实测（React 5391 → docker 网关 15000，主库 intelligent_audio_test）。

1. 批量管理标签「修改标签名字」：新旧同名时「确定」禁用，且不发 POST /testcases/batch；
   改成不同名后恢复可用；
2. 用例抽屉「标签」：§5.2.1 Combobox 建议下拉——GET /tags/names 真实候选（84 个）、
   keyword 服务端搜索、「新建「{词}」」创建项、已添加项置灰禁选；回车 / 逗号 chips 不回退；
3. 浅色 + 深色截图，并用 performance log 记录 Network（window.fetch 抓不到 bundle 内请求）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

try:
    import sys

    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5391')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1591')
os.makedirs(ARTIFACTS, exist_ok=True)

RESULT = {}
NET_KEEP = ('/api/v1/tags/names', '/api/v1/testcases/batch', '/api/v1/tags?')


def log(msg):
    print(msg, flush=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1100')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    # 固定用本地缓存 driver（不联网下载）
    cache_root = os.path.join(
        os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        if cands:
            cands.sort(key=lambda t: t[0])
            drv_path = cands[-1][1]
    return webdriver.Chrome(service=Service(drv_path), options=options)


def health():
    import urllib.request

    with urllib.request.urlopen('http://localhost:15000/health', timeout=30) as resp:
        data = json.loads(resp.read().decode())
    log('health = %s' % data)
    assert data.get('database') == 'intelligent_audio_test', '连到非主库，停！'
    RESULT['health'] = data
    return data


def shot(drv, name):
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    log('shot %s' % path)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def net_drain(drv):
    """performance log 里的 Network 请求（含 bundle 内部 fetch / xhr）"""
    out = []
    for entry in drv.get_log('performance'):
        msg = entry.get('message')
        if not isinstance(msg, str):
            continue
        try:
            payload = json.loads(msg)
        except Exception:
            continue
        inner = payload.get('message') or {}
        if inner.get('method') != 'Network.responseReceived':
            continue
        resp = inner.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if any(k in url for k in NET_KEEP):
            out.append({
                'method': resp.get('requestHeadersText', '').split(' ')[0] or '',
                'url': url,
                'status': resp.get('status'),
                'mimeType': resp.get('mimeType'),
            })
    return out


def wait_text(drv, text, timeout=45):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.innerText'))


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(3)
    if '/login' in drv.current_url:
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
        WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    log('logged in url = %s' % drv.current_url)


def set_theme(drv, mode):
    """INT-1591：深色截图必须同源 reload（about:blank 会丢主题）"""
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.refresh()
    WebDriverWait(drv, 40).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)
    if mode == 'dark':
        WebDriverWait(drv, 20).until(
            lambda d: d.execute_script(
                "return document.documentElement.classList.contains('dark')"))
    log('theme=%s dark=%s bg=%s' % (
        mode,
        drv.execute_script("return document.documentElement.classList.contains('dark')"),
        drv.execute_script('return getComputedStyle(document.body).backgroundColor')))


def open_testcases(drv):
    drv.get(BASE + '/testcases/by-group')
    WebDriverWait(drv, 60).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    # 分组视图首屏列表（用例卡 / 表格）
    WebDriverWait(drv, 120).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="全选用例"]'))
    time.sleep(2.0)


def open_batch_dialog(drv):
    select_all = drv.find_elements(By.CSS_SELECTOR, '[aria-label="全选用例"]')[0]
    js_click(drv, select_all)
    time.sleep(1.2)
    btn = WebDriverWait(drv, 30).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]"))
    js_click(drv, btn[0])
    time.sleep(1.5)
    dlg = drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]')[-1]
    assert '批量管理标签' in dlg.text, '批量管理标签弹窗未打开'
    return dlg


def confirm_button(drv):
    for b in drv.find_elements(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='确定']"):
        if b.is_displayed():
            return b
    raise AssertionError('找不到「确定」')


def pick_first_original_tag(drv):
    """打开「原标签」Select，取第一个选项名并选中"""
    trigger = drv.find_elements(
        By.XPATH, "//div[@role='dialog']//button[@role='combobox']")[0]
    js_click(drv, trigger)
    WebDriverWait(drv, 30).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
    time.sleep(0.8)
    options = [o for o in drv.find_elements(By.CSS_SELECTOR, '[role="option"]')
               if o.is_displayed()]
    name = options[0].text.strip()
    js_click(drv, options[0])
    time.sleep(1.0)
    return name


def step_batch_rename(drv):
    open_testcases(drv)
    dlg = open_batch_dialog(drv)
    js_click(drv, dlg.find_elements(By.XPATH, ".//label[contains(., '修改标签名字')]")[0])
    time.sleep(1.0)

    original = pick_first_original_tag(drv)
    name_input = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[placeholder='输入新标签名称']")
    name_input.send_keys(original)
    time.sleep(0.8)
    confirm = confirm_button(drv)
    same_disabled = not confirm.is_enabled()
    log('rename same-name: original=%r disabled=%s' % (original, same_disabled))
    shot(drv, '01_batch_rename_same_light.png')

    # 同名时点击也不发请求
    js_click(drv, confirm)
    time.sleep(1.5)
    same_net = [n for n in net_drain(drv) if '/testcases/batch' in n['url']]
    log('rename same-name net(batch)=%s' % same_net)

    # 改名后恢复可用
    name_input.send_keys('_INT1591改')
    time.sleep(0.8)
    confirm = confirm_button(drv)
    diff_enabled = confirm.is_enabled()
    log('rename different-name: enabled=%s' % diff_enabled)
    shot(drv, '02_batch_rename_diff_light.png')

    # 还原成同名再深色截一张
    name_input.clear()
    name_input.send_keys(original)
    time.sleep(0.8)
    set_theme(drv, 'dark')
    open_testcases(drv)
    dlg = open_batch_dialog(drv)
    js_click(drv, dlg.find_elements(By.XPATH, ".//label[contains(., '修改标签名字')]")[0])
    time.sleep(1.0)
    pick_first_original_tag(drv)
    name_input = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[placeholder='输入新标签名称']")
    name_input.send_keys(original)
    time.sleep(0.8)
    dark_disabled = not confirm_button(drv).is_enabled()
    dark_is_dark = drv.execute_script(
        "return document.documentElement.classList.contains('dark')")
    shot(drv, '03_batch_rename_same_dark.png')
    log('rename same-name dark: disabled=%s dark=%s' % (dark_disabled, dark_is_dark))

    RESULT['batch_rename'] = {
        'original_tag': original,
        'same_name_disabled': same_disabled,
        'same_name_net_batch': same_net,
        'different_name_enabled': diff_enabled,
        'dark_disabled': dark_disabled,
        'dark_class': dark_is_dark,
    }
    # 关闭弹窗，回浅色
    try:
        drv.find_elements(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")[-1].click()
    except Exception:
        drv.refresh()
    set_theme(drv, 'light')


def open_case_drawer(drv):
    open_testcases(drv)
    btns = [b for b in drv.find_elements(
        By.XPATH, "//button[normalize-space(.)='新增用例']") if b.is_displayed()]
    assert btns, '找不到「新增用例」'
    js_click(drv, btns[0])
    WebDriverWait(drv, 40).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "input[aria-label='标签']"))
    time.sleep(1.2)
    return drv.find_element(By.CSS_SELECTOR, "input[aria-label='标签']")



def open_dropdown(drv, tag_input):
    """原生 click：base-ui Combobox.Input 在 focus 时展开（JS .click() 不聚焦）"""
    tag_input.click()
    WebDriverWait(drv, 30).until(
        lambda d: [o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
                   if o.is_displayed()])
    time.sleep(1.2)


def combo_options(drv):
    out = []
    for o in drv.find_elements(By.CSS_SELECTOR, '[role="option"]'):
        if not o.is_displayed():
            continue
        out.append({
            'name': o.text.strip(),
            'disabled': o.get_attribute('aria-disabled') == 'true',
        })
    return out


def step_drawer_combobox(drv):
    tag_input = open_case_drawer(drv)
    open_dropdown(drv, tag_input)
    time.sleep(1.5)
    opts = combo_options(drv)
    log('combobox default options=%d first=%s' % (len(opts), opts[:3]))
    shot(drv, '04_case_tag_combobox_light.png')

    # keyword 服务端搜索
    tag_input.send_keys('INT')
    time.sleep(2.5)
    searched = combo_options(drv)
    net_after_search = [n for n in net_drain(drv) if '/tags/names' in n['url']]
    log('combobox keyword=INT options=%d keyword_requests=%d last=%s'
        % (len(searched), len(net_after_search),
           net_after_search[-1] if net_after_search else None))

    # 选中一条真实标签 → chip（真实候选来自 GET /tags/names）
    real = [o for o in searched
            if not o['name'].startswith('新建「') and not o['disabled']]
    picked_name = real[0]['name'] if real else ''
    if real:
        el = [o for o in drv.find_elements(By.CSS_SELECTOR, '[role="option"]')
              if o.is_displayed() and o.text.strip() == picked_name][0]
        js_click(drv, el)
        time.sleep(1.2)

    # 已添加项置灰禁选：重新搜同一 keyword，该标签项 aria-disabled=true
    open_dropdown(drv, tag_input)
    tag_input.send_keys('INT')
    time.sleep(2.5)
    added_opts = [o for o in combo_options(drv) if o['disabled']]
    log('combobox disabled(added) options=%s (picked=%r)'
        % (added_opts[:3], picked_name))
    shot(drv, '06_case_tag_added_disabled_light.png')

    # 「新建「{词}」」创建项（输入词无同名候选）
    tag_input.send_keys(Keys.CONTROL, 'a')
    tag_input.send_keys(Keys.DELETE)
    time.sleep(0.5)
    tag_input.send_keys('INT_新标签')
    time.sleep(2.5)
    create_opts = [o for o in combo_options(drv) if o['name'].startswith('新建「')]
    log('combobox create options=%s' % create_opts[:3])
    if create_opts:
        shot(drv, '05_case_tag_create_item_light.png')
        el = [o for o in drv.find_elements(By.CSS_SELECTOR, '[role="option"]')
              if o.is_displayed() and o.text.strip().startswith('新建「')]
        js_click(drv, el[0])
        time.sleep(1.2)
        tag_input = drv.find_element(By.CSS_SELECTOR, "input[aria-label='标签']")
    body_after_create = drv.execute_script('return document.body.innerText')

    # 回车 chips（原 TagInput 语义不回退）
    open_dropdown(drv, tag_input)
    tag_input.send_keys(Keys.CONTROL, 'a')
    tag_input.send_keys(Keys.DELETE)
    time.sleep(0.4)
    tag_input.send_keys('回车标签_INT1591')
    time.sleep(0.4)
    tag_input.send_keys(Keys.ENTER)
    time.sleep(1.0)
    after_enter = drv.execute_script('return document.body.innerText')

    # 深色
    set_theme(drv, 'dark')
    tag_input = open_case_drawer(drv)
    open_dropdown(drv, tag_input)
    time.sleep(2.0)
    dark_opts = combo_options(drv)
    dark_is_dark = drv.execute_script(
        "return document.documentElement.classList.contains('dark')")
    shot(drv, '07_case_tag_combobox_dark.png')
    log('dark combobox options=%d dark=%s' % (len(dark_opts), dark_is_dark))

    # 关闭抽屉（不保存，避免写真实库）
    from selenium.webdriver.common.action_chains import ActionChains

    ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(1.0)
    if drv.find_elements(By.CSS_SELECTOR, "input[aria-label='标签']"):
        try:
            drv.find_elements(
                By.XPATH, "//button[normalize-space(.)='取消']")[-1].click()
        except Exception:
            pass
    time.sleep(0.8)

    RESULT['drawer_combobox'] = {
        'default_option_count': len(opts),
        'keyword_options': len(searched),
        'keyword_requests': len(net_after_search),
        'create_options': create_opts[:3],
        'created_chip_visible': 'INT_新标签' in body_after_create,
        'disabled_added_options': added_opts[:3],
        'enter_chip_visible': '回车标签_INT1591' in after_enter,
        'dark_option_count': len(dark_opts),
        'dark_class': dark_is_dark,
    }
    set_theme(drv, 'light')


def render_network_shot(drv, net):
    """把 performance log 抓到的相关请求渲染成一张图（Network 证据）"""
    rows = ''.join(
        '<tr><td>%s</td><td>%s</td><td>%s</td></tr>'
        % (n.get('status'), n['url'].replace('&', '&amp;'), n.get('mimeType'))
        for n in net
    )
    head = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:Segoe UI,sans-serif;padding:24px;background:#111;color:#eee}'
        'h2{font-size:18px}table{border-collapse:collapse;width:100%;font-size:12px}'
        'td,th{border:1px solid #444;padding:6px;text-align:left;word-break:break-all}'
        'th{background:#1d1d1d;color:#9ae6b4}</style></head><body>'
        '<h2>INT-1591 Network（Selenium performance log，docker 网关 :15000）</h2>'
        '<table><tr><th>status</th><th>url</th><th>mime</th></tr>'
    )
    html = head + rows + '</table></body></html>'
    path = os.path.join(ARTIFACTS, 'network_int1591.html')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(0.8)
    shot(drv, '08_network_int1591.png')


def main():
    drv = _driver()
    try:
        health()
        login(drv)
        set_theme(drv, 'light')
        step_batch_rename(drv)
        step_drawer_combobox(drv)
        net = net_drain(drv)
        RESULT['network'] = net
        render_network_shot(drv, net)
        with open(os.path.join(ARTIFACTS, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2)
        log('RESULT = %s' % json.dumps(RESULT, ensure_ascii=False))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
