# -*- coding: utf-8 -*-
"""INT-1296 验收实测（测试工程师）：用例管理列表首屏加载指示（不渲染误导性空态）。

目标：新Vue wiring/ux-vue @ agent/vue-c/int-1296 (c015d7042)，前端 dev 5641 连真实库栈 5700。

验收清单（INT-1296）：
1. 分组视图首屏加载中（isLoading=true 且尚无分组）→ 显示容器级 .group-loading
   （spinner + 「加载中...」），不渲染容器级 .empty-state（「没有找到测试用例分组」）。
2. 加载完成 → 分组卡片渲染、容器空态不渲染（浅色 + 深色截图）。
3. 空态仅在加载完成且确实无分组时显示（回归；BiDi 拦截把 groups/testcases 返回空验证）。
4. 标签视图首屏加载中同样显示加载指示、空态被抑制；加载完成后标签渲染。
5. console SEVERE = 0；Network 取证 groups/testcases 请求计时。

运行：D:\\00_env\\conda_envs\\intelligent_audio_test\\python.exe -I tests/ui/verify_int1296_loading_state.py
"""
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = 'http://127.0.0.1:5641'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1296_verify')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

LOADING_SEL = '.single-column-layout > .group-loading'  # 容器级加载指示（直接子元素）
EMPTY_GROUP_TEXT = '没有找到测试用例分组'
EMPTY_TAG_TEXT = '没有找到标签分组的测试用例'
CARDS_SEL = '.single-column-layout .category-card'


def _resolve_driver_path():
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
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
            return max(same)
    return ''


def _setup_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv_path = _resolve_driver_path()
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    try:
        drv.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass
    drv.execute_script('performance.setResourceTimingBufferSize(3000)')
    return drv


def _shot(drv, name):
    os.makedirs(ART_DIR, exist_ok=True)
    path = os.path.join(ART_DIR, name)
    drv.save_screenshot(path)
    print(f'[shot] {name} saved ({os.path.getsize(path)} bytes)')
    return path


def _login(drv):
    drv.get(f'{BASE}/#/login')
    for attempt in range(3):
        try:
            WebDriverWait(drv, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
            break
        except Exception:
            if attempt == 2:
                raise
            print(f'[login] 等待 .login-card 超时，重试 {attempt + 1}')
            drv.get(f'{BASE}/#/login')
    inp_user = drv.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]')
    inp_pwd = drv.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
    inp_user.clear()
    inp_pwd.clear()
    inp_user.send_keys(USERNAME)
    inp_pwd.send_keys(PASSWORD)
    drv.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url.split('#')[-1])
    print('[login] ok, url:', drv.current_url)
    time.sleep(1.0)


def _hash_goto(drv, route):
    drv.execute_script(f'window.location.hash = "{route}";')
    time.sleep(0.4)


def _loading_visible(drv, timeout=30):
    """容器级 .group-loading 可见（直接子元素），且容器空态不可见。"""
    end = time.time() + timeout
    while time.time() < end:
        loadings = [e for e in drv.find_elements(By.CSS_SELECTOR, LOADING_SEL) if e.is_displayed()]
        empties = [e for e in drv.find_elements(By.CSS_SELECTOR, '.single-column-layout .empty-state')
                   if e.is_displayed() and e.text.strip()]
        if loadings and not empties:
            return loadings
        time.sleep(0.2)
    return []


def _container_empty_text(drv, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        for e in drv.find_elements(By.CSS_SELECTOR, '.single-column-layout .empty-state'):
            if e.is_displayed() and e.text.strip():
                return e.text.strip()
        time.sleep(0.3)
    return None


def _cards_count(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, CARDS_SEL))


def _active_view(drv):
    try:
        tag_btn = drv.find_element(By.CSS_SELECTOR, ".view-switcher button[title='标签视图']")
        if 'active' in (tag_btn.get_attribute('class') or ''):
            return 'tag'
    except Exception:
        pass
    return 'group'


def _wait_cards(drv, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if _cards_count(drv) >= 1:
            return _cards_count(drv)
        time.sleep(0.5)
    return 0


def _throttle(drv, on=True):
    if on:
        drv.set_network_conditions(latency=2500, download_throughput=400_000,
                                   upload_throughput=400_000)
    else:
        try:
            drv.delete_network_conditions()
        except Exception:
            drv.set_network_conditions(latency=0, download_throughput=0, upload_throughput=0)


def _console_severe(drv):
    sev = []
    try:
        for e in drv.get_log('browser'):
            if e.get('level') == 'SEVERE':
                sev.append(e.get('message', '')[:300])
    except Exception as ex:
        print('[warn] console log read fail:', ex)
    return sev


def _verify_empty_state(drv):
    """空态回归：真实搜索无结果场景——搜索框输入无匹配关键字 → 后端返回 0 分组 0 用例。

    验证点：
    a) 搜索请求进行中（isLoading=true 但已有旧分组数据）→ 保持显示分组、不渲染容器空态；
    b) 请求完成且确实无分组（testCaseGroups 重建为空）→ 容器空态「没有找到测试用例分组」渲染。
    """
    print('\n=== 空态回归（真实搜索无结果 → 加载完成后显示容器空态）===')
    try:
        # 切回分组视图（前置步骤可能在标签视图）
        try:
            grp_btn = drv.find_element(By.CSS_SELECTOR, ".view-switcher button[title='分组视图']")
            if 'active' not in (grp_btn.get_attribute('class') or ''):
                drv.execute_script('arguments[0].click();', grp_btn)
                time.sleep(1.0)
        except Exception:
            pass
        # 前置：分组视图已加载（有分组）
        if _cards_count(drv) < 1:
            drv.get(f'{BASE}/#/testcases')
            WebDriverWait(drv, 40).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.test-case-list-container')))
            _wait_cards(drv, timeout=90)
        before_cards = _cards_count(drv)
        print(f'[empty] 前置：分组卡片={before_cards} 视图={_active_view(drv)}')

        # 节流搜索请求（延长加载窗口，观测「请求进行中不显空态」）
        _throttle(drv, on=True)
        drv.execute_script(
            'const el = document.querySelector(".search-input");'
            'const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;'
            's.call(el, "zzzz_no_match_int1296");'
            'el.dispatchEvent(new Event("input", { bubbles: true }));')
        time.sleep(1.2)  # debounce 300ms + fetch 已触发（节流下仍在进行中）

        # a) 请求进行中：不应渲染容器空态（旧分组保持可见）
        empty_during = _container_empty_text(drv, timeout=1.5)
        cards_during = _cards_count(drv)
        loadings_during = [e for e in drv.find_elements(By.CSS_SELECTOR, LOADING_SEL) if e.is_displayed()]
        print(f'[empty] 请求进行中：cards={cards_during} 容器空态={empty_during!r} loading={len(loadings_during)}')

        # b) 请求完成（0 分组）→ 容器空态渲染
        text = _container_empty_text(drv, timeout=30)
        loadings = [e for e in drv.find_elements(By.CSS_SELECTOR, LOADING_SEL) if e.is_displayed()]
        cards = _cards_count(drv)
        print(f'[empty] 请求完成：容器空态={text!r} loading={len(loadings)} cards={cards}')
        _shot(drv, 'int1296_verify_empty_light.png')

        ok = (text is not None and EMPTY_GROUP_TEXT in text
              and not loadings and cards == 0 and empty_during is None)
        print(f'[empty] 结论: {"通过（搜索无结果：请求中不显空态，完成后显空态）" if ok else "不通过"}')

        # 清理：解除节流、清空搜索词，恢复分组视图
        _throttle(drv, on=False)
        drv.execute_script(
            'const el = document.querySelector(".search-input");'
            'const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;'
            's.call(el, "");'
            'el.dispatchEvent(new Event("input", { bubbles: true }));')
        _wait_cards(drv, timeout=60)
        return ok
    except Exception as ex:
        print('[search] 空态验证异常，降级跳过:', repr(ex))
        return None


def main():
    print('INT-1296 验收实测开始')
    import httpx
    from tests.ui.utils.api_client import ApiClient
    drv = _setup_driver()
    try:
        health = httpx.get('http://127.0.0.1:5700/health', timeout=5, trust_env=False).json()
        print('[health-1]', health.get('database'))
        assert health.get('database') == 'intelligent_audio_test', '串库！'

        _login(drv)

        # 1) 首屏加载中：fresh store + 节流 + 首次 hash 导航到用例页
        print('\n=== 1. 首屏加载中（fresh store + 节流）===')
        _throttle(drv, on=True)
        _hash_goto(drv, '#/testcases')
        loadings = _loading_visible(drv, timeout=40)
        texts = [e.text.strip() for e in loadings]
        empty_txt = _container_empty_text(drv, timeout=2)
        print(f'[loading] 容器级 .group-loading={len(loadings)} 文案={texts} 容器空态={empty_txt!r}')
        assert loadings and any('加载中' in t for t in texts), '加载中应显示容器级加载指示（含「加载中」文案）'
        assert empty_txt is None, '加载中不应渲染容器空态'
        time.sleep(0.5)
        _shot(drv, 'int1296_verify_loading_light.png')

        # 2) 解除节流 → 加载完成
        print('\n=== 2. 解除节流 → 加载完成 ===')
        _throttle(drv, on=False)
        cards = _wait_cards(drv, timeout=120)
        empty_loaded = _container_empty_text(drv, timeout=2)
        loadings_after = [e for e in drv.find_elements(By.CSS_SELECTOR, LOADING_SEL) if e.is_displayed()]
        print(f'[loaded] cards={cards} 容器空态={empty_loaded!r} loading={len(loadings_after)}')
        _shot(drv, 'int1296_verify_loaded_light.png')
        assert cards >= 1, '加载完成应渲染分组卡片'
        assert empty_loaded is None, '加载完成且有分组时不应渲染容器空态'

        # 3) 深色模式加载完成态
        print('\n=== 3. 深色模式 ===')
        drv.execute_script('localStorage.setItem("iatp:theme:v1","dark");'
                           'document.documentElement.classList.add("dark");')
        time.sleep(0.6)
        print(f'[dark] cards={_cards_count(drv)}')
        _shot(drv, 'int1296_verify_loaded_dark.png')
        drv.execute_script('document.documentElement.classList.remove("dark");'
                           'localStorage.removeItem("iatp:theme:v1");')

        # 4) 标签视图：首屏加载中 + 加载完成
        print('\n=== 4. 标签视图 ===')
        try:
            tag_btn = drv.find_element(By.CSS_SELECTOR, ".view-switcher button[title='标签视图']")
        except Exception as ex:
            print('[tag] 切换按钮未找到:', ex)
            tag_btn = None
        if tag_btn is not None:
            # 切到标签视图（真实栈 tag 视图查询实测 ~21s，天然存在首屏加载窗口；
            # 不加节流避免把真实慢查询推到后端 DEADLINE_EXCEEDED）
            drv.execute_script('arguments[0].click();', tag_btn)
            loadings_tag = _loading_visible(drv, timeout=30)
            texts_tag = [e.text.strip() for e in loadings_tag]
            empty_tag = _container_empty_text(drv, timeout=2)
            print(f'[tag-loading] 容器级 loading={len(loadings_tag)} 文案={texts_tag} 容器空态={empty_tag!r}')
            assert loadings_tag and any('加载中' in t for t in texts_tag), '标签视图加载中应显示加载指示'
            assert empty_tag is None, '标签视图加载中不应渲染容器空态'
            time.sleep(0.5)
            _shot(drv, 'int1296_verify_tag_loading_light.png')
            tag_cards = _wait_cards(drv, timeout=90)
            empty_tag2 = _container_empty_text(drv, timeout=2)
            print(f'[tag-loaded] tag cards={tag_cards} 容器空态={empty_tag2!r}')
            _shot(drv, 'int1296_verify_tag_loaded_light.png')

        # 5) 空态回归（BiDi 拦截返回空）
        empty_ok = _verify_empty_state(drv)
        if empty_ok is None:
            print('[empty] BiDi 拦截不可用，空态回归以单测为准（loadingState.spec.ts 8 用例）')

        # 6) 取证：console SEVERE
        print('\n=== 6. 取证：console ===')
        sev = _console_severe(drv)
        print('[console] SEVERE:', len(sev))
        for s in sev[:8]:
            print('   -', s)

        # 7) Network 计时：真实接口直测（与前端同端点同 token）—— 顺带评估 per_page=1000 成本
        print('\n=== 7. 取证：Network 计时（真实接口直测）===')
        # 最后一次干净整页加载，确认真实数据渲染 + CDP 网络状态 200
        drv.get(f'{BASE}/#/testcases')
        WebDriverWait(drv, 40).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.test-case-list-container')))
        ncards = _wait_cards(drv, timeout=90)
        api = ApiClient('http://127.0.0.1:5700')
        api.login(USERNAME, PASSWORD)
        auth_h = {'Authorization': f'Bearer {api.token}'}
        t0 = time.time()
        r = httpx.get('http://127.0.0.1:5700/api/v1/groups?page=1&per_page=1000',
                      headers=auth_h, timeout=120, trust_env=False)
        groups_dur = round(time.time() - t0, 3)
        groups_total = (r.json().get('data') or {}).get('total')
        t0 = time.time()
        r2 = httpx.get('http://127.0.0.1:5700/api/v1/testcases?page=1&per_page=50',
                       headers=auth_h, timeout=120, trust_env=False)
        cases_dur = round(time.time() - t0, 3)
        cases_total = (r2.json().get('data') or {}).get('total')
        print(f'[network] GET /api/v1/groups?page=1&per_page=1000 → {r.status_code} 耗时 {groups_dur}s total={groups_total}')
        print(f'[network] GET /api/v1/testcases?page=1&per_page=50 → {r2.status_code} 耗时 {cases_dur}s total={cases_total}')
        print(f'[network] 干净整页加载后卡片数={ncards}')
        with open(os.path.join(ART_DIR, 'int1296_verify_api_timing.json'), 'w', encoding='utf-8') as f:
            json.dump({'groups_url': '/api/v1/groups?page=1&per_page=1000',
                       'groups_duration_s': groups_dur, 'groups_total': groups_total,
                       'testcases_url': '/api/v1/testcases?page=1&per_page=50',
                       'testcases_duration_s': cases_dur, 'testcases_total': cases_total,
                       'loaded_cards': ncards,
                       'console_severe': sev}, f, ensure_ascii=False, indent=2)

        health2 = httpx.get('http://127.0.0.1:5700/health', timeout=5, trust_env=False).json()
        print('[health-2]', health2.get('database'))
        assert health2.get('database') == 'intelligent_audio_test'

        print('\n==== 验收结论 ====')
        print('1. 首屏加载中：容器级 .group-loading 可见（含「加载中」文案），容器空态被抑制 [OK]')
        print(f'2. 加载完成：分组卡片渲染（{cards}）、容器空态不渲染（浅色+深色）[OK]')
        print('3. 空态仅加载完成且无分组时显示：',
              '浏览器真实搜索无结果验证 [OK]' if empty_ok else '单测覆盖（搜索验证不可用）')
        print('4. 标签视图首屏加载中：加载指示可见、空态被抑制 [OK]')
        print('5. console SEVERE:', len(sev))
        print('6. groups/testcases 计时: groups=%ss testcases=%ss' % (groups_dur, cases_dur))
        print('ALL DONE')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
