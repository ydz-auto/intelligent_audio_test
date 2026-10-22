# -*- coding: utf-8 -*-
"""INT-1295 批量标签弹窗分页 浏览器实测（真实库栈 5700）——最小脚本。

验证点：批量管理标签弹窗「已有标签点选区」20 条/页 + 上一页/下一页分页；
翻遍所有页累计候选标签名（验证全部已有标签可点选到）。浅色截图 2 张。
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
    service = Service(drv_path)
    return webdriver.Chrome(service=service, options=options)


def _health():
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=8) as resp:
        health = json.loads(resp.read().decode())
    print('health.database =', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test', '连到非主库，停！'


def _dialog_root(drv):
    return WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, '[role="dialog"]'))[0]


def _candidate_chips(dlg):
    return dlg.find_elements(
        By.XPATH, ".//button[@type='button'][.//span[contains(@class, 'rounded-full')]]")


def _pager_text(dlg):
    out = []
    for s in dlg.find_elements(By.XPATH, ".//span[contains(@class, 'tabular-nums')]"):
        t = (s.text or '').strip()
        if re.match(r'^\d+ / \d+$', t):
            out.append(t)
    return out


def main():
    drv = _driver()
    try:
        _health()
        drv.get(BASE + '/login')
        time.sleep(2)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        time.sleep(2)
        print('logged in, url =', drv.current_url)

        drv.get(BASE + '/testcases/by-group')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)

        # 表头全选用例 → 批量浮条
        select_all = WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="全选用例"]'))
        drv.execute_script('arguments[0].click();', select_all[0])
        time.sleep(1.0)
        tag_btn = WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]"))
        assert tag_btn, '批量浮条应有「批量管理标签」'
        drv.execute_script('arguments[0].click();', tag_btn[0])
        time.sleep(1.8)

        dlg = _dialog_root(drv)
        assert dlg.find_elements(By.XPATH, ".//h2[contains(., '批量管理标签')]"), '弹窗标题应为「批量管理标签」'
        assert dlg.find_elements(By.XPATH, ".//span[contains(., '已有标签（点击添加）：')]"), '应有「已有标签（点击添加）：」提示'

        # 第 1 页：20 chips + 页码
        chips = _candidate_chips(dlg)
        chip_texts = [c.text.strip() for c in chips]
        print('page1 chips =', len(chip_texts), 'first3:', chip_texts[:3])
        assert len(chip_texts) == 20, f'弹窗首屏候选应 20 条，实际 {len(chip_texts)}'
        pager = _pager_text(dlg)
        assert pager and len(pager) == 1, f'应有唯一页码，实际 {pager}'
        m = re.match(r'^(\d+) / (\d+)$', pager[0])
        assert m, f'页码格式: {pager[0]}'
        page1, total_pages = int(m.group(1)), int(m.group(2))
        assert page1 == 1 and total_pages >= 2, f'首屏应为 1 / M (M>=2)，实际 {pager[0]}'
        print('pager =', pager[0], '-> expected pages >=2 OK')
        drv.save_screenshot(os.path.join(ARTIFACTS, '04_batch_tags_dialog_light_p1.png'))
        print('captured 04_batch_tags_dialog_light_p1.png')

        # 翻到最后一页，累计候选
        seen = set(chip_texts)
        last_pager = pager[0]
        safety = 0
        while safety < 12:
            next_btns = dlg.find_elements(By.XPATH, ".//button[@aria-label='下一页']")
            if not next_btns or next_btns[0].get_attribute('disabled'):
                break
            drv.execute_script('arguments[0].click();', next_btns[0])
            time.sleep(0.8)
            safety += 1
            seen |= {c.text.strip() for c in _candidate_chips(dlg)}
            last_pager = _pager_text(dlg)[0]
        m2 = re.match(r'^(\d+) / (\d+)$', last_pager)
        page_last, total_pages_last = int(m2.group(1)), int(m2.group(2))
        last_chips = len([c for c in _candidate_chips(dlg) if c.text.strip()])
        print(f'last pager = {last_pager}; last-page chips = {last_chips}; total unique = {len(seen)}')
        assert page_last == total_pages_last, '应翻到最后一页'
        assert total_pages_last == total_pages, f'页码总数一致 {total_pages} vs {total_pages_last}'
        assert 0 < last_chips <= 20, f'末页候选应在 1..20，实际 {last_chips}'
        assert len(seen) > 40, f'翻遍所有页应可见 >40 个已有标签（旧实现仅 10），实际 {len(seen)}'
        assert len(seen) <= total_pages_last * 20, '候选总数不应超过 20×页数'
        drv.save_screenshot(os.path.join(ARTIFACTS, '05_batch_tags_dialog_light_last.png'))
        print('captured 05_batch_tags_dialog_light_last.png')

        # 回翻到第 1 页
        for _ in range(total_pages_last - 1):
            prev_btns = dlg.find_elements(By.XPATH, ".//button[@aria-label='上一页']")
            drv.execute_script('arguments[0].click();', prev_btns[0])
            time.sleep(0.6)
        pager = _pager_text(dlg)
        assert pager and pager[0] == f'1 / {total_pages_last}', f'回翻后应为 1 / {total_pages_last}，实际 {pager}'

        # 点选候选 → 已选 Badge + 从候选剔除
        first_chip = _candidate_chips(dlg)[0]
        chosen_name = first_chip.text.strip()
        drv.execute_script('arguments[0].click();', first_chip)
        time.sleep(0.8)
        assert dlg.find_elements(By.XPATH, f".//button[@aria-label='移除 {chosen_name}']"), '已选 Badge 应出现'
        cand_now = {c.text.strip() for c in _candidate_chips(dlg)}
        assert chosen_name not in cand_now, f'已选 {chosen_name} 应从候选剔除'

        # 模式切换「移除标签」→ 提示变 + 页码重置第 1 页
        remove_label = dlg.find_elements(
            By.XPATH, ".//label[.//input[@name='batch-tag-mode'] and contains(., '移除标签')]")
        drv.execute_script('arguments[0].click();', remove_label[0])
        time.sleep(0.8)
        assert dlg.find_elements(By.XPATH, ".//span[contains(., '已有标签（点击移除）：')]"), '移除模式提示应有'
        pager = _pager_text(dlg)
        assert pager and re.match(r'^1 / \d+$', pager[0]), f'模式切换后应重置第 1 页，实际 {pager}'

        # 取消关闭（不写数据）
        cancel = dlg.find_elements(By.XPATH, ".//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click();', cancel[0])
        time.sleep(0.8)

        _health()
        print('BATCH DIALOG ALL ASSERTIONS PASSED')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
