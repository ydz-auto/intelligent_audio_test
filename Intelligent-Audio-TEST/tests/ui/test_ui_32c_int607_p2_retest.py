# -*- coding: utf-8 -*-
"""INT-607 代码审计 P2/P3/P4 返修复测（浏览器实测，打回后复测只测失败项）。

审计打回清单（代码审计 01a14bd0）：
- P2（阻断）：壳 useAlgorithmOptions queryKey ['algorithm','options'] → ['shell','algorithm','options']，
  与评估域「关联算法」facet（evaluation-api mock {value,label}）共享 React Query 缓存 → 双契约互相污染，
  一方字段读空白。返修后需在评估页实测「关联算法」facet 下拉不空白、且切换器下拉正常。
- P3：切换器改经 application 层 useGlobalAlgorithm 封装消费 algorithm store（结构核对 + 交互回归）。
- P4：删除 top-nav.config.ts 同值副本，TOP_NAV_DEFS 唯一源（结构核对 + 顶栏渲染回归）。

本用例环境：真实 Chrome headless + 常驻后端 :5000（AUTH_MODE=off dev_user '*' 全放行）+ 本 worktree dev server。
算法 gRPC 服务（51067）由本测试 run 自起（真实 GET /algorithm/options → data.algorithms [{value,name}]）。

P2 核心断言设计：评估页 /Evaluation 同屏下，壳切换器（真实 {value,name}）与评估域 facet（mock {value,label}）
两个 hook 同时挂载。修复前共 key 时先填充方决定 data 形态、另一方字段空白；修复后各自渲染——
① facet 下拉渲染 mock 标签（通用识别引擎/流式识别引擎/多维评估集成/实验识别引擎），且不含真实算法名；
② 切换器下拉渲染真实「小艺语音大模型」，且不含 mock 标签。双向隔离即证明 queryKey 独立。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5337')
GATEWAY = os.environ.get('GATEWAY_BASE', 'http://127.0.0.1:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int607_p2')
os.makedirs(ARTIFACTS, exist_ok=True)

ALGO_STORE_KEY = 'iatp:algorithm:v1'

# 评估域 mock 契约（evaluation-api MOCK_ALGORITHM_OPTIONS，{value,label}）
MOCK_FACET_LABELS = ['通用识别引擎', '流式识别引擎', '多维评估集成', '实验识别引擎']
# 壳真实契约（GET /algorithm/options data.algorithms，{value,name}）
REAL_ALGO_NAME = '小艺语音大模型'

results = []


def check(name, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name} {detail}')
    results.append((status, name, detail))
    return condition


def set_theme(driver, theme):
    driver.execute_script(
        f"localStorage.setItem('iatp:theme:v1:mode', '{theme}');"
    )


def wait_top_nav(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return document.querySelector('header nav') != null || document.querySelector('[data-slot=\"sidebar-menu-button\"]') != null"
        )
    )


def click_button_containing(driver, text, timeout=15):
    """按文本找 <button> 并用 JS 点击（规避 Popover trigger 虚元素/浮层遮挡的
    element_to_be_clickable 误判；按钮可见性由调用方先用 presence 等待保证）。"""
    btn = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//button[contains(normalize-space(.), {json.dumps(text, ensure_ascii=False)})]")
        )
    )
    driver.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    driver.execute_script('arguments[0].click();', btn)


def visible_buttons_text(driver):
    """当前视口中所有可见 <button> 的归一化文本（去空白）。"""
    els = driver.find_elements(By.XPATH, '//button')
    texts = []
    for el in els:
        t = el.text.strip()
        if t:
            texts.append(t)
    return texts


def has_text_in(container_texts, needle):
    """needle 是否以整段（或子串）出现在任一容器文本里（防 span 拆词）。"""
    for t in container_texts:
        if needle in t:
            return True
    return False


def main():
    global results
    results = []
    ok_all = True

    # ===== 0. 前置：真实 /algorithm/options 返回 data.algorithms voice_llm =====
    try:
        with urllib.request.urlopen(f'{GATEWAY}/api/v1/algorithm/options', timeout=8) as r:
            body = json.loads(r.read().decode('utf-8'))
        real_ok = (body.get('success') is True
                   and body.get('data', {}).get('algorithms')
                   and body['data']['algorithms'][0].get('value') == 'voice_llm')
        detail = f"body={json.dumps(body, ensure_ascii=False)[:200]}"
    except Exception as e:
        real_ok = False
        detail = f'请求异常: {e}'
    results.append(('PASS' if real_ok else 'FAIL', '前置-真实 /algorithm/options', detail))
    ok_all = ok_all and real_ok
    if not real_ok:
        print('[FAIL] 前置：真实算法接口不可用，P2 实测定点无法验证真实数据；继续执行结构断言')
        # 前置失败不阻断继续（结构/单测证据可独立成立），但核心真实数据断言会失败

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1440,900')
    options.add_argument('--hide-scrollbars')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 900)

    try:
        # ===== 1. P4 回归：顶栏渲染正常（TOP_NAV_DEFS 单源后仍渲染 6 项） =====
        driver.get(BASE + '/dashboard')
        wait_top_nav(driver)
        time.sleep(2)
        nav_texts = [e.text.strip() for e in driver.find_elements(By.CSS_SELECTOR, 'header nav a') if e.text.strip()]
        p4_ok = check('P4-顶栏渲染回归（6 项）', nav_texts == ['主页', '工作台', '报告', '排行榜', '文档', '关于'],
                      f'实际={nav_texts}')

        # ===== 2. P2 核心：评估页同屏双 hook 共存 =====
        driver.get(BASE + '/Evaluation')
        wait_top_nav(driver)
        # 等待评估页工具栏出现（关联算法 facet 触发钮）
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[.//span[text()='关联算法']]"))
        )
        time.sleep(2)  # mock 数据 120ms 延迟 + 壳真实 query 落定

        # 2.1 壳切换器在评估页可见（算法:read）
        switcher_visible = len(driver.find_elements(By.CSS_SELECTOR, '[aria-label="切换全局算法"]')) > 0
        check('P2-评估页壳切换器可见', switcher_visible)

        # 2.2 关联算法 facet 打开 → mock 标签渲染（P2 核心断言 1）
        click_button_containing(driver, '关联算法')
        WebDriverWait(driver, 10).until(
            lambda d: has_text_in(visible_buttons_text(d), '通用识别引擎')
        )
        time.sleep(0.5)
        open_btn_texts = visible_buttons_text(driver)
        facet_labels_ok = all(has_text_in(open_btn_texts, lab) for lab in MOCK_FACET_LABELS)
        check('P2-评估 facet 下拉渲染 mock 标签（4 项）',
              facet_labels_ok, f'实际={[t for t in open_btn_texts if any(l in t for l in MOCK_FACET_LABELS)]}')
        # 反向：facet 下拉不含真实算法名（契约隔离）
        facet_no_real = not has_text_in(open_btn_texts, REAL_ALGO_NAME)
        check('P2-评估 facet 下拉不含真实算法名（双契约隔离）', facet_no_real)
        driver.save_screenshot(os.path.join(ARTIFACTS, 'eval_facet_light.png'))
        # 关闭 facet（点击页面空白区域收起）
        driver.execute_script('document.body.click();')
        time.sleep(0.5)

        # 2.3 切换器打开 → 真实算法渲染（P2 核心断言 2）
        switcher_btn = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[aria-label="切换全局算法"]'))
        )
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', switcher_btn)
        driver.execute_script('arguments[0].click();', switcher_btn)
        WebDriverWait(driver, 10).until(
            lambda d: has_text_in(visible_buttons_text(d), REAL_ALGO_NAME)
        )
        time.sleep(0.5)
        sw_texts = visible_buttons_text(driver)
        switcher_real_ok = has_text_in(sw_texts, REAL_ALGO_NAME) and has_text_in(sw_texts, '全部算法')
        check('P2-切换器下拉渲染真实「小艺语音大模型」+全部算法', switcher_real_ok,
              f'实际={[t for t in sw_texts if REAL_ALGO_NAME in t or "全部算法" in t]}')
        # 反向：切换器下拉不含 mock 标签（契约隔离）
        switcher_no_mock = not any(has_text_in(sw_texts, lab) for lab in MOCK_FACET_LABELS)
        check('P2-切换器下拉不含 mock 标签（双契约隔离）', switcher_no_mock)
        driver.save_screenshot(os.path.join(ARTIFACTS, 'switcher_light.png'))

        # 2.4 写入路径：选中小艺语音大模型 → localStorage iatp:algorithm:v1 = voice_llm
        real_item = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//button[contains(normalize-space(.), {json.dumps(REAL_ALGO_NAME, ensure_ascii=False)})]")
            )
        )
        driver.execute_script('arguments[0].click();', real_item)
        time.sleep(1.5)
        stored_raw = driver.execute_script(f"return localStorage.getItem('{ALGO_STORE_KEY}')")
        try:
            stored_algo = json.loads(stored_raw)['state']['algorithmId']
        except Exception:
            stored_algo = stored_raw
        write_ok = check('P2-选中后 localStorage iatp:algorithm:v1 写入 voice_llm',
                         stored_algo == 'voice_llm', f'实际={stored_raw}')
        # 按钮文本收敛
        btn_texts = [e.text.strip() for e in driver.find_elements(By.CSS_SELECTOR, '[aria-label="切换全局算法"]')]
        converge_ok = check('P2-切换器按钮文本收敛为小艺语音大模型',
                            any(REAL_ALGO_NAME in t for t in btn_texts), f'实际={btn_texts}')

        # 2.5 Network 证据：真实 /api/v1/algorithm/options 请求
        perf = driver.execute_script(
            "return performance.getEntriesByType('resource').map(e => e.name).filter(n => n.includes('/algorithm/options'))"
        )
        net_ok = check('P2-Network 捕获真实 /algorithm/options 请求', len(perf) > 0,
                       f'实际={perf}')

        # 2.6 深色：评估 facet + 切换器各一张
        set_theme(driver, 'dark')
        driver.get(BASE + '/Evaluation')
        wait_top_nav(driver)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[.//span[text()='关联算法']]"))
        )
        time.sleep(2)
        click_button_containing(driver, '关联算法')
        WebDriverWait(driver, 10).until(
            lambda d: has_text_in(visible_buttons_text(d), '通用识别引擎')
        )
        time.sleep(0.5)
        dark_facet_ok = all(has_text_in(visible_buttons_text(driver), lab) for lab in MOCK_FACET_LABELS)
        check('P2-深色评估 facet 下拉渲染 mock 标签', dark_facet_ok)
        driver.save_screenshot(os.path.join(ARTIFACTS, 'eval_facet_dark.png'))
        driver.execute_script('document.body.click();')
        time.sleep(0.5)
        sw_btn_dark = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[aria-label="切换全局算法"]'))
        )
        driver.execute_script('arguments[0].scrollIntoView({block:"center"});', sw_btn_dark)
        driver.execute_script('arguments[0].click();', sw_btn_dark)
        WebDriverWait(driver, 10).until(
            lambda d: has_text_in(visible_buttons_text(d), REAL_ALGO_NAME)
        )
        time.sleep(0.5)
        dark_sw_ok = has_text_in(visible_buttons_text(driver), REAL_ALGO_NAME)
        check('P2-深色切换器下拉渲染真实算法', dark_sw_ok)
        driver.save_screenshot(os.path.join(ARTIFACTS, 'switcher_dark.png'))

        # ===== 汇总 =====
        passed = sum(1 for s, _, _ in results if s == 'PASS')
        failed = sum(1 for s, _, _ in results if s == 'FAIL')
        print(f'\n==== INT-607 P2/P3/P4 复测：{passed} 通过 / {failed} 失败 ====')
        for s, name, detail in results:
            print(f'  [{s}] {name} {detail}')
        ok_all = ok_all and all(s == 'PASS' for s, _, _ in results)
        return ok_all
    finally:
        driver.quit()


if __name__ == '__main__':
    import sys
    ok = main()
    sys.exit(0 if ok else 1)
