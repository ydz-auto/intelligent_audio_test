# -*- coding: utf-8 -*-
"""INT-1498 真实库栈浏览器实测：日常任务列表渲染「挑选合并」标识。

dev server 5311（临时配置 rsbuild.realstack.tmp.ts）→ 网关 5700（真实库栈）。
验证点：
  1. 挑选合并容器行（接线测试_INT1498_挑选合并容器 / id=527）行内 Badge「挑选合并」
     且次行含「结果挑选 · 来源 2 个任务 · 结果 3 条」；
  2. 普通任务行无该徽章；
  3. 行操作「查看详情」快览弹窗同步展示标识；
  4. 浅色 / 深色两套截图 + Network（GET /api/v1/tasks 200）。
"""
import json, os, sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
TOKEN = open(os.environ['IAT_TOKEN_FILE'], encoding='utf-8').read().strip()
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.abspath('tests/ui/artifacts/int1498')
os.makedirs(ART, exist_ok=True)
TARGET_NAME = '接线测试_INT1498_挑选合并容器'


def _driver(theme):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    service = Service()
    drv = webdriver.Chrome(options=options, service=service)
    boot = (
        "try{localStorage.setItem('iatp:auth:token:v1', %s);"
        "localStorage.setItem('iatp:theme:v1:mode', '%s');}catch(e){}"
    ) % (json.dumps(TOKEN), theme)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': boot})
    return drv


def tasks_network(drv):
    hits = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        url = msg['params']['response']['url']
        if '/api/v1/tasks' in url:
            hits.append((msg['params']['response']['status'], url))
    return hits


def wait_table(drv):
    # 真实库栈列表偶发首查较慢：等行出现，0 行时点一次「查询」重取
    for attempt in range(3):
        try:
            WebDriverWait(drv, 30).until(
                EC.presence_of_element_located((By.XPATH, "//table//tbody//tr"))
            )
            return
        except Exception:
            if attempt == 2:
                raise
            try:
                btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='查询']")
                drv.execute_script("arguments[0].click();", btn)
            except Exception:
                pass
            time.sleep(2)


def container_row(drv):
    return WebDriverWait(drv, 40).until(
        EC.presence_of_element_located(
            (By.XPATH, "//table//tbody//tr[.//span[normalize-space(.)='%s']]" % TARGET_NAME)
        )
    )


def row_info(drv, row):
    text = row.text.replace('\n', ' | ')
    badges = [b.text.strip() for b in row.find_elements(By.XPATH, ".//span[normalize-space(.)='挑选合并']")]
    return text, badges


def shot(drv, name, element=None):
    path = os.path.join(ART, name)
    if element is None:
        drv.save_screenshot(path)
    else:
        try:
            element.screenshot(path)
        except Exception:
            drv.save_screenshot(path)
    return path


def main():
    result = {'base': BASE, 'target': TARGET_NAME}
    drv = _driver('light')
    try:
        drv.get(BASE + '/tasks/daily')
        wait_table(drv)
        # 选中容器行并滚入视口
        row = container_row(drv)
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        time.sleep(0.6)
        text, badges = row_info(drv, row)
        result['container_row_text'] = text
        result['container_badges'] = badges
        result['container_has_badge'] = len(badges) > 0
        result['container_text_checks'] = {
            '结果挑选': '结果挑选' in text,
            '来源 2 个任务': '来源 2 个任务' in text,
            '结果 3 条': '结果 3 条' in text,
        }
        result['light_shot'] = shot(drv, 'int1498_daily_light.png')
        result['light_row_shot'] = shot(drv, 'int1498_row_light.png', row)

        # 普通任务行无标识
        rows = drv.find_elements(By.XPATH, "//table//tbody//tr")
        normal = None
        for r in rows:
            t = r.text
            if TARGET_NAME in t or '已删除' in t or not t.strip():
                continue
            if '挑选合并' in t:
                continue
            normal = r
            break
        result['normal_row_found'] = normal is not None
        if normal is not None:
            ntext, nbadges = row_info(drv, normal)
            result['normal_row_text'] = ntext[:160]
            result['normal_has_badge'] = len(nbadges) > 0

        # 快览弹窗：行操作 → 查看详情
        try:
            trigger = row.find_element(By.XPATH, ".//button[@aria-label='任务操作']")
            drv.execute_script("arguments[0].click();", trigger)
            time.sleep(0.8)
            item = WebDriverWait(drv, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[@role='menuitem'][contains(., '快速查看')]"))
            )
            drv.execute_script("arguments[0].click();", item)
            time.sleep(1.5)
            dlg = WebDriverWait(drv, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[@role='dialog']"))
            )
            dtext = dlg.text.replace('\n', ' | ')
            result['quickview_text'] = dtext[:300]
            result['quickview_has_badge'] = '挑选合并' in dtext
            result['quickview_shot'] = shot(drv, 'int1498_quickview_light.png', dlg)
            body = drv.find_element(By.TAG_NAME, 'body')
            body.send_keys('\ue00c')  # ESC
            time.sleep(0.6)
        except Exception as exc:
            result['quickview_error'] = repr(exc)[:300]

        result['network_light'] = tasks_network(drv)
    finally:
        drv.quit()

    # 深色
    drv = _driver('dark')
    try:
        drv.get(BASE + '/tasks/daily')
        wait_table(drv)
        row = container_row(drv)
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        time.sleep(0.6)
        text, badges = row_info(drv, row)
        result['dark_row_text'] = text
        result['dark_has_badge'] = len(badges) > 0
        result['dark_shot'] = shot(drv, 'int1498_daily_dark.png')
        result['dark_row_shot'] = shot(drv, 'int1498_row_dark.png', row)
        result['network_dark'] = tasks_network(drv)
    finally:
        drv.quit()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = (
        result.get('container_has_badge')
        and all(result.get('container_text_checks', {}).values())
        and result.get('normal_row_found')
        and not result.get('normal_has_badge')
        and result.get('dark_has_badge')
    )
    sys.exit(0 if ok else 3)


if __name__ == '__main__':
    main()
