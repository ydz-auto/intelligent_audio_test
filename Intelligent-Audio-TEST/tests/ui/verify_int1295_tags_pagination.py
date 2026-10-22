# -*- coding: utf-8 -*-
"""INT-1295 标签页右表首屏/页脚 + 批量标签弹窗已有标签分页 浏览器实测（真实库栈 5700）。

验证点：
1. /TagManagement 右表页脚：「已显示 20 / N 个标签 · 加载更多」→ 点击 →「已显示 40 / N」→
   加载完全部 →「已加载全部 N 个标签」；与表头「共 N 个标签」计数一致（N>20 时）。
2. /testcases 批量管理标签弹窗：已有标签点选区 20 条/页 + 上一页/下一页分页（页码 1 / M → 2 / M）；
   已选 chips 从候选剔除；模式切换重置页码。
3. 浅/深色截图 + Network 捕获 /tags 真实请求。

启动方式：dev server http://localhost:5315（rsbuild proxy → 5700 真实库栈）。
"""
import json
import os
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5315')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.dirname(os.path.abspath(__file__)) + '/artifacts/int1295_tags_pagination'

os.makedirs(ARTIFACTS, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1280,800')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--no-proxy-server')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-features=OptimizationGuideModelDownloading,MediaRouter')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    if not drv_path:
        drv_path = 'chromedriver'
    service = Service(drv_path)
    return webdriver.Chrome(service=service, options=options)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _wait(drv, by, value, timeout=20):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _capture(drv, name):
    drv.save_screenshot(os.path.join(ARTIFACTS, name))
    print(f'  captured {name}')


def _health():
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=8) as resp:
        health = json.loads(resp.read().decode())
    print('health.database =', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test', '连到非主库，停！'


def _set_dark(drv, dark=True):
    mode = 'dark' if dark else 'light'
    try:
        drv.execute_script(
            "window.localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('%s'));" % mode
        )
    except Exception:
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', '%s');" % mode)


def _login(drv):
    _goto(drv, '/login')
    time.sleep(2.0)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _drain_perf(drv):
    logs = drv.get_log('performance')
    out = []
    for entry in logs:
        msg = json.loads(entry['message'])['message']
        if msg['method'] == 'Network.requestWillBeSent':
            out.append(msg['params'])
    return out


def _dialog_root(drv):
    dlg = _wait(drv, By.CSS_SELECTOR, '[role="dialog"]')
    return dlg[0]


def _candidate_chips(drv):
    """弹窗内候选点选 chips（带色点 span 的按钮；翻页钮/关闭钮/已选 Badge 除外）。"""
    dlg = _dialog_root(drv)
    return dlg.find_elements(
        By.XPATH,
        ".//button[@type='button'][.//span[contains(@class, 'rounded-full')]]",
    )


def _pager_text(drv):
    dlg = _dialog_root(drv)
    out = []
    for s in dlg.find_elements(By.XPATH, ".//span[contains(@class, 'tabular-nums')]"):
        t = (s.text or '').strip()
        if re.match(r'^\d+ / \d+$', t):
            out.append(t)
    return out


def verify_tag_page(drv):
    print('== /TagManagement 右表页脚 ==')
    _goto(drv, '/TagManagement')
    time.sleep(2.5)

    # 表头计数
    total = None
    for e in drv.find_elements(By.XPATH, "//*[contains(., '个标签')]"):
        t = (e.text or '').strip()
        m = re.search(r'共\s*(\d+)\s*个标签', t)
        if m and len(t) < 40:
            total = int(m.group(1))
            break
    assert total is not None, '未找到右表表头「共 N 个标签」'
    print(f'  total tags (header) = {total}')
    assert total > 20, f'真实库标签数应 > 20 才能验证分页，实际 {total}'

    # 首屏行数与页脚
    rows = _wait(drv, By.CSS_SELECTOR, 'tbody tr')
    print(f'  initial visible rows = {len(rows)}')
    assert len(rows) == 20, f'首屏应 20 行，实际 {len(rows)}'

    footer_btns = _wait(drv, By.XPATH, "//p/button[contains(., '个标签') and contains(., '加载更多')]")
    footer_text = footer_btns[0].text.strip()
    print('  initial footer =', footer_text)
    assert footer_text == f'已显示 20 / {total} 个标签 · 加载更多', f'页脚文案不符: {footer_text}'

    # 点击「加载更多」→ 40（JS click 绕开 base-ui 层叠拦截）
    drv.execute_script('arguments[0].click();', footer_btns[0])
    time.sleep(1.2)
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    footer_btns = drv.find_elements(By.XPATH, "//p/button[contains(., '个标签') and contains(., '加载更多')]")
    ft = footer_btns[0].text.strip()
    print(f'  after click rows = {len(rows)}, footer = {ft}')
    assert len(rows) == 40, f'点击后应 40 行，实际 {len(rows)}'
    assert ft == f'已显示 40 / {total} 个标签 · 加载更多'

    # 浅色截图（40 行）
    _capture(drv, '01_tag_page_light_40rows.png')

    # 点击「加载更多」追加直到全部加载（72 = 20+20+20+12，至多 4 次）
    for _ in range(6):
        btn = drv.find_elements(By.XPATH, "//p/button[contains(., '个标签') and contains(., '加载更多')]")
        if not btn:
            break
        drv.execute_script('arguments[0].click();', btn[0])
        time.sleep(1.0)
    footer_all = drv.find_elements(By.XPATH, "//p[contains(., '已加载全部') and contains(., '个标签')]")
    print('  final footer =', footer_all[0].text.strip() if footer_all else '未达全部')
    assert footer_all and footer_all[0].text.strip() == f'已加载全部 {total} 个标签'
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    print(f'  final visible rows = {len(rows)}')
    assert len(rows) == total, f'全部加载后应 {total} 行，实际 {len(rows)}'
    _capture(drv, '02_tag_page_light_all.png')

    # 滚动触底语义：全新打开后滚动右表容器到底应自动追加（20 → 40）
    _goto(drv, '/TagManagement')
    time.sleep(2.5)
    _wait(drv, By.CSS_SELECTOR, 'tbody tr')
    scroll_el = drv.find_element(By.XPATH, "//div[contains(@class, 'overflow-y-auto') and .//table]")
    before_rows = len(drv.find_elements(By.CSS_SELECTOR, 'tbody tr'))
    drv.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight;', scroll_el)
    time.sleep(1.5)
    after_rows = len(drv.find_elements(By.CSS_SELECTOR, 'tbody tr'))
    print(f'  scroll-trigger rows: {before_rows} -> {after_rows}')
    assert before_rows == 20 and after_rows > before_rows, '滚动触底应自动追加加载'
    _capture(drv, '03_tag_page_light_scroll_more.png')


def verify_batch_dialog(drv):
    print('== /testcases 批量管理标签弹窗 ==')
    _goto(drv, '/testcases/by-group')
    time.sleep(3.0)

    # 选择用例：表头全选（base-ui Checkbox JS click）
    select_all = _wait(drv, By.CSS_SELECTOR, '[aria-label="全选用例"]')
    drv.execute_script('arguments[0].click();', select_all[0])
    time.sleep(1.0)

    # 打开批量管理标签
    tag_btn = _wait(drv, By.XPATH, "//button[contains(., '批量管理标签')]")
    assert tag_btn, '批量浮条应有「批量管理标签」'
    drv.execute_script('arguments[0].click();', tag_btn[0])
    time.sleep(1.8)

    title = _wait(drv, By.XPATH, "//h2[contains(., '批量管理标签')]")
    print('  dialog title:', title[0].text.strip())

    hint = _wait(drv, By.XPATH, "//span[contains(., '已有标签（点击添加）：')]")
    assert hint, '应有「已有标签（点击添加）：」提示'

    chips = _candidate_chips(drv)
    chip_texts = [c.text.strip() for c in chips]
    print(f'  page1 chips = {len(chip_texts)} (first3: {chip_texts[:3]}, last3: {chip_texts[-3:]})')
    assert len(chip_texts) == 20, f'弹窗首屏候选应 20 条，实际 {len(chip_texts)}'

    pager_text = _pager_text(drv)
    print('  pager texts:', pager_text)
    assert pager_text and len(pager_text) == 1, f'应有唯一页码文本，实际 {pager_text}'
    m = re.match(r'^(\d+) / (\d+)$', pager_text[0])
    assert m, f'页码格式不符: {pager_text[0]}'
    page1_num, total_pages = int(m.group(1)), int(m.group(2))
    assert page1_num == 1, f'首屏页码应为 1，实际 {page1_num}'
    assert total_pages >= 2, f'已有标签应多页（>20 条），实际 {total_pages} 页'
    _capture(drv, '04_batch_tags_dialog_light_p1.png')

    # 翻到最后一页，累计候选标签名（验证全部已有标签可点选到、分页 20/页）
    seen = set(chip_texts)
    last_pager = pager_text[0]
    safety = 0
    while safety < 12:
        next_btn = drv.find_elements(By.XPATH, "//button[@aria-label='下一页']")
        if not next_btn or next_btn[0].get_attribute('disabled'):
            break
        drv.execute_script('arguments[0].click();', next_btn[0])
        time.sleep(0.8)
        safety += 1
        seen |= {c.text.strip() for c in _candidate_chips(drv)}
        last_pager = _pager_text(drv)[0]
    m2 = re.match(r'^(\d+) / (\d+)$', last_pager)
    assert m2, f'末页页码格式不符: {last_pager}'
    page_last, total_pages_last = int(m2.group(1)), int(m2.group(2))
    last_chips = len([c for c in _candidate_chips(drv) if c.text.strip()])
    print(f'  last pager = {last_pager}; last-page chips = {last_chips}; total unique chips = {len(seen)}')
    assert page_last == total_pages_last, '应翻到最后一页'
    assert total_pages_last == total_pages, f'页码总数应一致 {total_pages} vs {total_pages_last}'
    assert 0 < last_chips <= 20, f'末页候选应在 1..20 之间，实际 {last_chips}'
    assert len(seen) > 40, f'翻遍所有页应能看到 >40 个已有标签（旧实现仅 10/20），实际 {len(seen)}'
    assert len(seen) <= total_pages_last * 20, '候选总数不应超过 20×页数'
    _capture(drv, '05_batch_tags_dialog_light_last.png')

    # 回翻到第 1 页
    for _ in range(total_pages_last - 1):
        prev_btn = _wait(drv, By.XPATH, "//button[@aria-label='上一页']")
        drv.execute_script('arguments[0].click();', prev_btn[0])
        time.sleep(0.6)
    pager_text = _pager_text(drv)
    assert pager_text and pager_text[0] == f'1 / {total_pages_last}', \
        f'回翻后页码应为 1 / {total_pages_last}，实际 {pager_text}'

    # 已选 chips 剔除：点选一个候选 → 成为已选 Badge、从候选消失
    first_chip = _candidate_chips(drv)[0]
    chosen_name = first_chip.text.strip()
    print('  choosing chip:', chosen_name)
    drv.execute_script('arguments[0].click();', first_chip)
    time.sleep(0.8)
    badge = _wait(drv, By.XPATH, f"//button[@aria-label='移除 {chosen_name}']")
    assert badge, f'已选 Badge 应出现（可移除 {chosen_name}）'
    cand_names = [c.text.strip() for c in _candidate_chips(drv)]
    assert chosen_name not in cand_names, f'已选 {chosen_name} 应从候选剔除'

    # 模式切换重置页码：切「移除标签」→ 提示文案变 + 页码回到 1
    remove_label = _wait(drv, By.XPATH,
                         "//label[.//input[@name='batch-tag-mode'] and contains(., '移除标签')]")
    drv.execute_script('arguments[0].click();', remove_label[0])
    time.sleep(0.8)
    hint = _wait(drv, By.XPATH, "//span[contains(., '已有标签（点击移除）：')]")
    assert hint, '移除模式应有「已有标签（点击移除）：」提示'
    pager_text = _pager_text(drv)
    print('  remove-mode pager:', pager_text)
    assert pager_text and re.match(r'^1 / \d+$', pager_text[0]), \
        f'模式切换后页码应重置为第 1 页，实际 {pager_text}'

    # 取消关闭弹窗（不提交写操作）
    cancel = _wait(drv, By.XPATH, "//button[contains(., '取消')]")
    drv.execute_script('arguments[0].click();', cancel[0])
    time.sleep(1.0)
    print('  dialog closed')


def verify_dark(drv):
    print('== 深色截图 ==')
    _health()
    _set_dark(drv, True)
    _goto(drv, '/TagManagement')
    time.sleep(2.5)
    _wait(drv, By.CSS_SELECTOR, 'tbody tr')
    _capture(drv, '06_tag_page_dark.png')

    _goto(drv, '/testcases/by-group')
    time.sleep(3.0)
    select_all = _wait(drv, By.CSS_SELECTOR, '[aria-label="全选用例"]')
    drv.execute_script('arguments[0].click();', select_all[0])
    time.sleep(1.0)
    tag_btn = _wait(drv, By.XPATH, "//button[contains(., '批量管理标签')]")
    drv.execute_script('arguments[0].click();', tag_btn[0])
    time.sleep(1.8)
    _wait(drv, By.XPATH, "//h2[contains(., '批量管理标签')]")
    _capture(drv, '07_batch_tags_dialog_dark.png')
    cancel = _wait(drv, By.XPATH, "//button[contains(., '取消')]")
    drv.execute_script('arguments[0].click();', cancel[0])
    time.sleep(1.0)


def verify_network(drv):
    print('== Network 捕获 /tags 真实请求 ==')
    _health()
    _set_dark(drv, False)
    _drain_perf(drv)
    _goto(drv, '/TagManagement')
    time.sleep(2.5)
    _wait(drv, By.CSS_SELECTOR, 'tbody tr')
    reqs = _drain_perf(drv)
    tag_reqs = []
    for r in reqs:
        url = r.get('request', {}).get('url', '')
        if '/api/v1/tags' in url:
            tag_reqs.append(url)
    print('  /tags requests:')
    for u in tag_reqs:
        print('   ', u)
    assert any('per_page=100' in u for u in tag_reqs), '应有 GET /api/v1/tags?page=1&per_page=100'


def main():
    drv = _driver()
    try:
        _health()
        _login(drv)
        print('logged in, url =', drv.current_url)
        verify_tag_page(drv)
        verify_batch_dialog(drv)
        _health()
        verify_dark(drv)
        verify_network(drv)
        _health()
        print('ALL ASSERTIONS PASSED')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
