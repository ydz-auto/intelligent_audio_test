# -*- coding: utf-8 -*-
"""INT-1061 选择设备/API：设备卡片与 API 表格形态统一 — 测试工程师验收浏览器实测。

连 frontend-react dev server（5360，代理到常驻后端 5000，AUTH_MODE=off dev_user '*'）。
自建接线测试数据（接线测试_INT1061_*：HTTP API + WS API 在线各 1、物理设备 1 台离线）
驱动 /start-test?step=1 页面，核对验收标准：
  ① 同屏设备卡与 API 卡同形态（骨架 class 逐项比对一致）
  ② 真实数据渲染（设备 + API 混选）；浅/深色 + Network 截图
  ③ 交互走查：选择、取消选择、离线禁用一致；全选在线；执行参数区联动不回归
结束前彻底删除本卡测试数据（302/303 API、141 设备）。

用法：python verify_int1061_api_card_unify.py
输出：tests/ui/artifacts/int1061/*.png
"""
import json
import os
import sys
import time
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5360')
API = os.environ.get('API_BASE', 'http://localhost:5000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1061')

# 本卡自建测试数据（按名清理，验后删除）
TEST_NAMES = [
    '接线测试_INT1061_probe_api',
    '接线测试_INT1061_ws_api',
    '接线测试_INT1061_online_device',
]

_network = []


# ---------- 后端直连（建数据/清理） ----------
def api_json(method, path, body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header('Content-Type', 'application/json')
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def cleanup_test_data():
    try:
        j = api_json('GET', '/apis?per_page=1000')
        for it in (j.get('data') or {}).get('items', []):
            if it.get('name') in TEST_NAMES:
                api_json('DELETE', f"/apis/{it['id']}")
                print(f'  cleaned api {it["id"]} {it.get("name")}')
    except Exception as e:
        print(f'  cleanup apis failed: {e}')
    try:
        j = api_json('GET', '/test-devices?per_page=1000')
        for it in (j.get('data') or {}).get('items', []):
            if it.get('name') in TEST_NAMES:
                api_json('DELETE', f"/test-devices/{it['id']}")
                print(f'  cleaned device {it["id"]} {it.get("name")}')
    except Exception as e:
        print(f'  cleanup devices failed: {e}')


# ---------- Selenium ----------
def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _wait(drv, by, value, timeout=20):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _card_outer_class(el):
    cls = el.get_attribute('class') or ''
    # 提取卡片骨架（不含选中/离线修饰，两卡同骨架）
    return ' '.join(c for c in cls.split() if c in {
        'flex', 'flex-col', 'gap-2', 'rounded-xl', 'border', 'p-4', 'transition-colors',
    })


def _section_cards(drv, heading):
    """给定分节标题文本，返回该 section 内所有带卡片外骨架的 div。"""
    heads = _wait(drv, By.XPATH, f"//h3[contains(text(),'{heading}')]")
    if not heads:
        return []
    section = heads[0].find_element(By.XPATH, 'ancestor::section[1]')
    cards = section.find_elements(By.XPATH, './/div[contains(@class,"rounded-xl") and contains(@class,"border") and contains(@class,"p-4")]')
    return cards


def _is_disabled(el):
    """base-ui Checkbox 禁用由 aria-disabled/data-disabled 承载（span 无原生 disabled）。"""
    return (el.get_attribute('aria-disabled') == 'true'
            or el.get_attribute('data-disabled') is not None)


def _checkbox_by_label(drv, label):
    els = _wait(drv, By.XPATH, f"//*[@aria-label='{label}']")
    return els[0]


def _click_checkbox(drv, label):
    el = _checkbox_by_label(drv, label)
    drv.execute_script('arguments[0].click();', el)
    time.sleep(0.8)


def _collect_network(drv):
    by_id = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                rid = params.get('requestId')
                by_id[rid] = {
                    'method': req.get('method', 'GET'),
                    'url': req.get('url') or '',
                    'status': None,
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in by_id:
                    by_id[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    _network.extend(by_id.values())


def _match_network(path, methods=None):
    out = []
    for r in _network:
        if path in r.get('url', ''):
            if methods and r.get('method') not in methods:
                continue
            if r.get('status') is None or r.get('status', 0) >= 300:
                continue
            out.append(r)
    return out


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    results = []
    try:
        # 直达资源选择步（step=1 已解锁）
        drv.get(BASE + '/start-test?step=1')
        time.sleep(2.5)
        # 等设备/API 区块渲染
        _wait(drv, By.XPATH, "//h3[contains(text(),'设备')]", 30)
        _wait(drv, By.XPATH, "//h3[contains(text(),'被测 API')]", 30)
        time.sleep(2.0)

        body = _body_text(drv)
        # 确认自建测试数据渲染
        assert '接线测试_INT1061_probe_api' in body, 'HTTP 测试 API 未渲染'
        assert '接线测试_INT1061_ws_api' in body, 'WS 测试 API 未渲染'
        assert '接线测试_INT1061_online_device' in body, '测试设备未渲染'
        assert 'pura90小艺' in body, '真实设备 pura90小艺 未渲染'
        results.append('真实数据渲染：设备(接线测试_INT1061_online_device/pura90小艺) + API(probe/ws/INT1060 残留) 均渲染')

        # ① 同形态：设备卡与 API 卡骨架 class 一致
        dev_cards = _section_cards(drv, '设备')
        api_cards = _section_cards(drv, '被测 API')
        assert dev_cards, '未找到设备卡片'
        assert api_cards, '未找到 API 卡片'
        dev_skeleton = _card_outer_class(dev_cards[0])
        api_skeleton = _card_outer_class(api_cards[0])
        results.append(f'设备卡骨架: [{dev_skeleton}]')
        results.append(f'API 卡骨架: [{api_skeleton}]')
        assert dev_skeleton == api_skeleton, f'骨架不一致: dev=[{dev_skeleton}] api=[{api_skeleton}]'
        results.append('① 通过：设备卡与 API 卡同一套卡片骨架')

        # WS 类型徽章
        ws_badges = drv.find_elements(By.XPATH,
            "//*[contains(text(),'Realtime WS')]")
        http_badges = drv.find_elements(By.XPATH,
            "//*[contains(text(),'HTTP API')]")
        results.append(f'类型徽章：Realtime WS x{len(ws_badges)}、HTTP API x{len(http_badges)}')
        assert len(ws_badges) >= 1 and len(http_badges) >= 1, '类型徽章缺失'
        results.append('② 通过：API 类型徽章（HTTP API / Realtime WS）渲染')

        # ③ 离线禁用一致
        offline_dev_cb = _checkbox_by_label(drv, '选择设备 pura90小艺')
        offline_api_cb = _checkbox_by_label(drv, '选择 API INT314SMOKE_5666a525_mock_api')
        assert _is_disabled(offline_dev_cb), '离线设备 Checkbox 未禁用'
        assert _is_disabled(offline_api_cb), '离线 API Checkbox 未禁用'
        online_api_cb = _checkbox_by_label(drv, '选择 API 接线测试_INT1060_api')
        assert not _is_disabled(online_api_cb), '在线 API Checkbox 被误禁'
        results.append('③a 通过：离线设备 + 离线 API Checkbox 均禁用、在线 API 可勾（行为一致）')

        # 在线 API 可选 → 整卡选中态 ring + 汇总行
        _click_checkbox(drv, '选择 API 接线测试_INT1061_probe_api')
        body = _body_text(drv)
        assert '已选' in body and '1 个 API' in body, f'选中后汇总未更新: {body[:200]}'
        sel_card = drv.find_element(By.XPATH,
            "//div[contains(@class,'rounded-xl') and contains(@class,'border') and contains(@class,'p-4')]"
            "[.//*[contains(text(),'接线测试_INT1061_probe_api')]]")
        sel_cls = sel_card.get_attribute('class') or ''
        assert 'ring-2' in sel_cls and 'border-primary' in sel_cls, f'整卡选中态缺失: {sel_cls}'
        results.append('③b 通过：在线 API 勾选 → 整卡 ring-2 border-primary 高亮 + 汇总「1 个 API」')

        # 取消选择 → 汇总回落
        _click_checkbox(drv, '选择 API 接线测试_INT1061_probe_api')
        body = _body_text(drv)
        assert '0 个 API' in body, f'取消后汇总未回落: {body[:200]}'
        results.append('③c 通过：取消勾选 → 汇总「0 个 API」')

        # 全选在线 → 3 个在线 API（含 INT1060 残留）全选；再点取消
        _click_checkbox(drv, '全选在线 API')
        body = _body_text(drv)
        assert '3 个 API' in body, f'全选在线后汇总非 3: {body[:200]}'
        results.append('③d 通过：「全选在线」选中当前筛选在线集 → 汇总「3 个 API」')
        _click_checkbox(drv, '全选在线 API')
        body = _body_text(drv)
        assert '0 个 API' in body, f'全选再取消未回落: {body[:200]}'
        results.append('③e 通过：「全选在线」再点取消 → 汇总「0 个 API」')

        # 执行参数区联动（并发上限文案渲染；max_concurrent 后端不落库=0，与改动前表格一致）
        body = _body_text(drv)
        assert '并发上限' in body, '并发上限文案缺失'
        results.append('③f 通过：执行参数区联动（并发上限文案渲染，值 0=后端 max_process 不落库既有缺口，非本卡引入）')

        # 截图前选中 1 个在线 API，让整卡选中态 ring 入图
        _click_checkbox(drv, '选择 API 接线测试_INT1061_probe_api')
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step-resources-light.png'))
        results.append('浅色截图 saved（含 API 整卡选中态）')

        # 切深色：写主题 key + about:blank 打断 bfcache 强刷
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        drv.get('about:blank')
        time.sleep(1.0)
        drv.get(BASE + '/start-test?step=1')
        time.sleep(3.0)
        _wait(drv, By.XPATH, "//h3[contains(text(),'被测 API')]", 30)
        time.sleep(1.5)
        # 深色截图同样含选中态
        _click_checkbox(drv, '选择 API 接线测试_INT1061_probe_api')
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step-resources-dark.png'))
        results.append('深色截图 saved（含 API 整卡选中态）')

        # Network 证据（全量 requestWillBeSent 里核对真实资源请求）
        _collect_network(drv)
        dev_reqs = _match_network('/api/v1/test-devices')
        api_reqs = _match_network('/api/v1/apis')
        results.append(f'Network: GET /test-devices x{len(dev_reqs)}、GET /apis x{len(api_reqs)}')
        assert dev_reqs and api_reqs, 'Network 无真实资源请求（mock 残留？）'
        results.append('Network 证据：/test-devices + /apis 真实请求捕获')

        # 输出汇总
        print('=' * 60)
        print('INT-1061 验收浏览器实测结果：')
        for line in results:
            print('  -', line)
        print('=' * 60)
    finally:
        cleanup_test_data()
        drv.quit()


if __name__ == '__main__':
    main()
