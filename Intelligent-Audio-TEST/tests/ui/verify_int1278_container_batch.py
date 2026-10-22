# -*- coding: utf-8 -*-
"""INT-1278 挑选合并容器级批量操作浏览器实测（真实库栈 intelligent_audio_test，auth dev）。

验证点：
1. /tasks/cherry-picks 容器列表「选择」列 Checkbox 已启用（不再 disabled/待接线占位）。
2. 表头全选 → 行勾选 → 批量浮条出现（批量收藏 / 批量删除）。
3. 批量收藏发真实请求（POST /tasks/{id}/favorite 逐容器）；Network 捕获。
4. 浅色 / 深色截图各一张。

启动方式：dev server http://localhost:5321（rsbuild proxy → 5700 真实库栈）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.dirname(os.path.abspath(__file__)) + '/artifacts/int1278_container_batch'

os.makedirs(ARTIFACTS, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _wait(drv, by, value, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _texts(drv, by, value):
    return [e.text.strip() for e in drv.find_elements(by, value) if e.text.strip()]


def _drain_perf(drv):
    logs = drv.get_log('performance')
    out = []
    for entry in logs:
        msg = json.loads(entry['message'])['message']
        if msg['method'] == 'Network.requestWillBeSent':
            out.append(msg['params'])
    return out


def _find_mutations(requests):
    """提取本页关键写请求（/favorite /batch-action），含请求体。"""
    result = []
    for r in requests:
        url = r.get('request', {}).get('url', '')
        method = r.get('request', {}).get('method', '')
        if '/api/v1/tasks/' in url and any(
                k in url for k in ('/favorite', 'batch-action')):
            post = r.get('request', {}).get('postData')
            result.append({'method': method, 'url': url, 'body': post})
    return result


def _capture(drv, name):
    drv.save_screenshot(os.path.join(ARTIFACTS, name))
    print(f'  captured {name}')


def _login(drv):
    _goto(drv, '/login')
    time.sleep(1.5)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def main():
    drv = _driver()
    try:
        # 真实库栈防串库核验（devlet §4.3）
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=5) as resp:
            health = json.loads(resp.read().decode())
        print('health.database =', health.get('database'))
        assert health.get('database') == 'intelligent_audio_test', '连到非主库，停！'

        # 登录真实库栈
        _login(drv)
        print('logged in, url =', drv.current_url)

        # 进入挑选合并页签
        _goto(drv, '/tasks/cherry-picks')
        time.sleep(2.5)

        # 页面标题确认
        title_texts = _texts(drv, By.XPATH, '//*[self::h1 or self::h2 or self::h3]')
        print('page titles:', title_texts)

        # 1) 行选择 Checkbox 已启用（无 disabled 属性）
        row_boxes = _wait(drv, By.CSS_SELECTOR, '[aria-label^="选择合并容器「"]')
        print(f'  row checkboxes found: {len(row_boxes)}')
        assert len(row_boxes) >= 1, '容器列表应至少有 1 行'
        disabled_count = sum(1 for c in row_boxes if c.get_attribute('disabled') is not None)
        print(f'  disabled row checkboxes: {disabled_count}')
        assert disabled_count == 0, '选择列 Checkbox 不应再禁用（待接线占位已移除）'
        titles = [c.get_attribute('title') for c in row_boxes]
        print('  titles:', titles)
        assert all('待接线' not in (t or '') for t in titles), '不应再有「容器级批量操作待接线」title'

        # 截图：浅色
        _capture(drv, '01_container_list_light.png')

        # 2) 勾选前两行 → 批量浮条出现
        row_boxes[0].click()
        time.sleep(0.4)
        row_boxes[1].click()
        time.sleep(0.6)
        bulk = _wait(drv, By.XPATH, "//*[contains(., '个容器已选择')]")
        bulk_btns = [e.text for e in drv.find_elements(By.CSS_SELECTOR, 'button') if '批量' in (e.text or '')]
        print('  bulk bar buttons:', bulk_btns)
        assert bulk, '勾选后批量浮条应出现'
        assert any('批量收藏' in b for b in bulk_btns), '浮条应有「批量收藏」'
        assert any('批量删除' in b for b in bulk_btns), '浮条应有「批量删除」'
        # 截图：勾选态
        _capture(drv, '02_container_bulk_selected_light.png')

        # 3) 表头全选：先清空（当前 2 行均已勾），再全选→应全勾，再取消全选→应清空
        try:
            clear_btn = drv.find_elements(By.CSS_SELECTOR, '[aria-label="清除选择 (Esc)"]')
            if clear_btn:
                clear_btn[0].click()
                time.sleep(0.4)
        except Exception:
            pass
        checked_now = len(drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择合并容器「"][data-checked]'))
        print(f'  checked rows after clear: {checked_now}')
        header_box = _wait(drv, By.CSS_SELECTOR, '[aria-label="全选合并容器"]')
        header_box[0].click()
        time.sleep(0.5)
        checked_after = len(drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择合并容器「"][data-checked]'))
        print(f'  checked rows after header select-all: {checked_after}')
        assert checked_after > checked_now, '表头全选应勾选全部当前容器'
        _wait(drv, By.XPATH, "//*[contains(., '个容器已选择')]")
        _capture(drv, '03_container_select_all_light.png')
        # 取消全选
        header_box[0].click()
        time.sleep(0.4)
        checked_none = len(drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择合并容器「"][data-checked]'))
        print(f'  checked rows after header clear-all: {checked_none}')
        assert checked_none == 0, '表头再次点击应清空勾选'

        # 4) 批量收藏发真实请求（勾 2 行 → 点批量收藏）
        row_boxes = _wait(drv, By.CSS_SELECTOR, '[aria-label^="选择合并容器「"]')
        row_boxes[0].click()
        row_boxes[1].click()
        time.sleep(0.5)
        fav_btn = _wait(drv, By.XPATH, "//button[contains(., '批量收藏')]")
        assert fav_btn, '批量收藏按钮应出现'
        # 清空 perf log 再点
        _drain_perf(drv)
        fav_btn[0].click()
        time.sleep(2.5)
        reqs = _drain_perf(drv)
        mutations = _find_mutations(reqs)
        print('  favorite/batch mutations captured:')
        for m in mutations:
            print('   ', m)
        fav_req = [m for m in mutations if m['method'] == 'POST' and '/favorite' in m['url']]
        assert len(fav_req) >= 2, f'批量收藏应发 2 个 POST /tasks/{{id}}/favorite，实际 {len(fav_req)}'
        # 收藏成功后浮条应清空（onClear）
        time.sleep(0.8)
        bulk_gone = len(drv.find_elements(By.XPATH, "//*[contains(., '个容器已选择')]")) == 0
        print('  bulk bar cleared after favorite:', bulk_gone)

        # 5) 深色截图（同一会话，切主题）
        try:
            drv.execute_script(
                "window.localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('dark'));")
        except Exception:
            drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get(BASE + '/tasks/cherry-picks')
        time.sleep(1.8)
        # 重新勾选以显示浮条
        rb = _wait(drv, By.CSS_SELECTOR, '[aria-label^="选择合并容器「"]')
        if rb:
            rb[0].click()
            rb[1].click()
            time.sleep(0.6)
        _capture(drv, '04_container_bulk_dark.png')

        # 5b) 批量删除确认弹窗（勾 1 行 → 点批量删除 → 弹确认）
        try:
            clear_btn = drv.find_elements(By.CSS_SELECTOR, '[aria-label="清除选择 (Esc)"]')
            if clear_btn:
                clear_btn[0].click()
                time.sleep(0.3)
        except Exception:
            pass
        rb = _wait(drv, By.CSS_SELECTOR, '[aria-label^="选择合并容器「"]')
        rb[0].click()
        time.sleep(0.5)
        del_btn = _wait(drv, By.XPATH, "//button[contains(., '批量删除')]")
        assert del_btn, '批量删除按钮应出现'
        del_btn[0].click()
        time.sleep(0.8)
        confirm = _wait(drv, By.XPATH, "//*[contains(., '将把 1 个合并容器移入回收站')]")
        print('  delete confirm dialog:', [e.text[:60] for e in confirm])
        assert confirm, '批量删除应弹确认框'
        _capture(drv, '05_container_bulk_delete_confirm_dark.png')
        # 取消（不真删真实数据）
        cancel = _wait(drv, By.XPATH, "//button[contains(., '取消')]")
        if cancel:
            cancel[0].click()
            time.sleep(0.5)
        print('ALL ASSERTIONS PASSED')

    finally:
        drv.quit()


if __name__ == '__main__':
    main()
