# -*- coding: utf-8 -*-
"""INT-849 复测 v2：真实「编辑 API」弹窗（CRUDFormModal）代理字段接线浏览器验证。
前置：并行隔离栈 shift=2500 已就绪（网关 :7500，前端 :7773）。
跳转步骤：/APITest → 点击进度步骤3「选择被测API」→ 资源卡片编辑。
"""
import os
import re
import json
import sys

PROJECT_ROOT = r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-849-12feb1d70b3b\worktree\Intelligent-Audio-TEST'
sys.path.insert(0, PROJECT_ROOT)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select

from tests.ui.pages.base_page import BasePage
from tests.ui.pages.login_page import LoginPage

FRONTEND = 'http://127.0.0.1:7773'
OUT = os.path.join(PROJECT_ROOT, 'int849_shots')
os.makedirs(OUT, exist_ok=True)

CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = r'D:\00_code\V9.7.31\Intelligent-Audio-TEST\e2e_tests\selenium\drivers\chromedriver-win32\chromedriver.exe'
cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
if os.path.isdir(cache_root):
    cands = []
    for vd in os.listdir(cache_root):
        exe = os.path.join(cache_root, vd, 'chromedriver.exe')
        if os.path.isfile(exe):
            cands.append((tuple(int(x) for x in re.findall(r'\d+', vd)[:4]), exe))
    if cands:
        cands.sort(reverse=True)
        DRIVER = cands[0][1]

opts = Options()
opts.binary_location = CHROME_BINARY
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1680,1050')
opts.add_argument('--force-device-scale-factor=1')
opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

driver = webdriver.Chrome(service=Service(DRIVER), options=opts)
page = BasePage(driver, FRONTEND)

def shot(name):
    path = os.path.join(OUT, name)
    driver.save_screenshot(path)
    print(f'[shot] {path}')

def set_select(css, value):
    el = page.find_visible(css)
    Select(el).select_by_value(value)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", el)

def set_input(css, value):
    page.fill(css, value)

def perf_requests(method_filter='', url_filter=''):
    out = []
    for entry in driver.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.requestWillBeSent':
            continue
        req = msg.get('params', {}).get('request', {})
        url = req.get('url', '')
        m = req.get('method', '')
        if url_filter in url and (not method_filter or m in method_filter):
            out.append((m, url, req.get('postData', '')))
    return out

results = []
try:
    # 1. 登录
    lp = LoginPage(driver, FRONTEND)
    lp.goto('/login')
    lp.wait_visible(lp.CARD)
    lp.login('admin', 'admin123')
    lp.wait_left_login(timeout=25)
    lp.wait_home_rendered(timeout=25)
    print('[ok] 登录成功')
    results.append('login:ok')

    # 2. 进入 /APITest 并跳转资源步骤
    page.goto('/APITest')
    page.wait_visible('.progress-step', timeout=25)
    print(f'[debug] url={driver.current_url}')
    print(f'[debug] page-title={[t.text for t in page.find_all(".page-title")]}')
    steps = page.find_all('.progress-step')
    print(f'[check] progress-step 数: {len(steps)}')
    for i, s in enumerate(steps):
        print(f'  step{i}: {s.text.strip()[:30].replace(chr(10), " / ")}')
    if len(steps) < 3:
        raise SystemExit('progress-step < 3，页面未按预期渲染')
    # 资源步骤 = index 2
    steps[2].click()
    page.settle(0.8)

    # 3. 检查 API 数据
    cards = []
    try:
        page.wait_visible('.resource-card', timeout=15)
        cards = page.find_all('.resource-card')
    except Exception:
        pass
    print(f'[check] API 资源卡片数: {len(cards)}')

    # 诊断：/apis 请求
    apis_reqs = perf_requests(method_filter=('GET',), url_filter='/api/v1/apis')
    for m, u, d in apis_reqs[-3:]:
        print(f'[network] {m} {u[:120]}')

    if len(cards) == 0:
        print('[info] 无 API 数据，走「新增API」创建')
        # 点击 新增API（device-toolbar 内的 btn-primary）
        try:
            page.click('.device-toolbar .btn-primary')
        except Exception:
            for btn in page.find_all('.btn'):
                if '新增API' in btn.text:
                    btn.click()
                    break
        page.settle(0.6)
        if not page.exists('.crud-form-modal'):
            for btn in page.find_all('.btn'):
                if '新增API' in btn.text:
                    btn.click()
                    break
        page.wait_visible('.crud-form-modal', timeout=15)
        shot('int849_create_modal_light.png')
        # 填 name
        set_input('#field-name', 'INT849测试API')
        # 填端点 URL（meta 用默认值即可）
        if page.exists('#field-endpoints-0-url'):
            set_input('#field-endpoints-0-url', 'http://127.0.0.1:9999/v1/audio')
        else:
            ep = page.find_all('.array-item input[type="text"]')
            if ep:
                page.fill('.array-item input[type="text"]', 'http://127.0.0.1:9999/v1/audio')
        # 点保存
        page.click('.crud-form-modal .btn-primary[type="submit"]')
        page.settle(1.5)
        print('[info] 新增API已提交')
        page.wait_visible('.resource-card', timeout=15)
        cards = page.find_all('.resource-card')
        print(f'[check] 创建后卡片数: {len(cards)}')

    # 4. 打开编辑弹窗
    page.find('.resource-card .card-actions [title="编辑"]', timeout=10).click()
    page.wait_visible('.crud-form-modal', timeout=15)
    print('[ok] 编辑弹窗 CRUDFormModal 已打开')

    # 5. 代理字段存在性
    pt_exists = page.exists('#field-proxyType')
    pu_exists = page.exists('#field-proxyUrl')
    print(f'[check] 代理类型下拉存在: {pt_exists}; 代理地址输入存在: {pu_exists}')
    results.append(f'proxy_fields:{pt_exists}/{pu_exists}')

    pt = driver.find_element(By.CSS_SELECTOR, '#field-proxyType')
    print(f'[check] 代理类型初始选中: "{pt.get_attribute("value")}"')
    shot('int849_edit_modal_light.png')

    # 6. 校验A：类型=http + 地址空 → 阻止保存
    set_select('#field-proxyType', 'http')
    set_input('#field-proxyUrl', '')
    page.click('.crud-form-modal .btn-primary[type="submit"]')
    page.settle(0.8)
    stays = page.exists('.crud-form-modal')
    toast = [t for t in page.find_all('.el-message, .notification, .toast, .ant-message, [class*=notification], [class*=message]') if t.is_displayed()]
    print(f'[check] 校验A(缺地址): 弹窗仍开={stays}, 可见提示={len(toast)}')
    shot('int849_validation_missing_url.png')
    results.append(f'valA_modal_stays:{stays}')

    # 7. 校验B：地址缺 user:pass@
    set_input('#field-proxyUrl', '10.0.0.1:8080')
    page.click('.crud-form-modal .btn-primary[type="submit"]')
    page.settle(0.8)
    stays_b = page.exists('.crud-form-modal')
    print(f'[check] 校验B(缺user:pass@): 弹窗仍开={stays_b}')
    shot('int849_validation_no_userpass.png')
    results.append(f'valB_modal_stays:{stays_b}')

    # 8. 合法保存
    set_input('#field-proxyUrl', 'user:pass@10.0.0.1:8080')
    page.click('.crud-form-modal .btn-primary[type="submit"]')
    page.settle(1.2)
    shot('int849_edit_modal_valid_filled.png')
    put_reqs = perf_requests(method_filter=('PUT', 'POST'), url_filter='/api/v1/apis')
    for m, u, d in put_reqs[-3:]:
        print(f'[network] {m} {u[:120]}')
        if d:
            print(f'  payload: {d[:700]}')
            results.append(f'network_{m}:proxy_in_payload={"proxy_type" in d or "proxy_url" in d}')

    # 9. 深色截图
    driver.execute_script("document.documentElement.classList.add('dark');")
    style = """
    <style id="int849-dark-override">
      .dark .crud-form-modal, .dark .modal-content, .dark .basic-modal,
      .dark .crud-form-modal form, .dark .modal-body, .dark .modal-card,
      .dark .crud-form-modal .form-group-section, .dark .crud-form-modal .form-grid {
        background-color: #2a2a2a !important; color: #f5f5f5 !important; border-color: rgba(255,255,255,0.12) !important;
      }
      .dark .crud-form-modal input, .dark .crud-form-modal select, .dark .crud-form-modal textarea {
        background-color: #3a3a3a !important; color: #f5f5f5 !important; border-color: rgba(255,255,255,0.18) !important;
      }
      .dark .crud-form-modal label, .dark .crud-form-modal .section-title, .dark .crud-form-modal .field-hint {
        color: #f5f5f5 !important;
      }
    </style>
    """
    driver.execute_script("document.head.insertAdjacentHTML('beforeend', arguments[0]);", style)
    page.settle(0.4)
    shot('int849_edit_modal_dark.png')

    print('\n===== RESULTS =====')
    for r in results:
        print(r)
    print('VERIFY_DONE')
except Exception as e:
    import traceback
    traceback.print_exc()
    shot('int849_error.png')
    print(f'ERROR: {e}')
    raise
finally:
    driver.quit()
