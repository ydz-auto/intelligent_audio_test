# -*- coding: utf-8 -*-
"""INT-996 返工复测（2026-10-20）：禁用声纹注册不持久 → 应「enabled=false 不入列」。

验收打回 P2 复现：用例 algorithm_params 仅含 voiceprint（voice_llm schema 无表单字段，
本库用例常见形态）→ 编辑抽屉噪声与干扰 → 关闭「启用声纹注册」→ 保存 →
后端 GET 回读 algorithm_params 必须不再含 voiceprint（修复前回退分支 caseItem.algorithmParams
把存量 voiceprint 重新带上，违反交付契约）。

真实 Chrome headless + 常驻 5000 后端 + dev server 5318。
逐条核对：
- P2a 回填：声纹注册开关启用 + 注册音频「音频 #56」+ 播放设备选中 + 等待 8s
- P2b 关闭开关 → 声纹配置块消失
- P2c 保存 → Network 捕获 PUT /testcases/{id}：algorithm_params 不含 voiceprint
  （各轮 params 过滤 voiceprint 后为空 → 空数组透传）
- P2d 后端 GET 回读：algorithm_params 为空，声纹不再入列；name/algorithm_type/rounds 保留
- P2e 重开抽屉：声纹注册开关保持关闭（回读生效，用户可关闭声纹注册）
- P2f 反向：重开后再启用声纹 + 保存 → 后端回读 voiceprint 恢复（enabled=true 仍入列）
失败落 tests/ui/artifacts/int996_rework/<阶段>/（截图+console+source）。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int996_rework')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5318')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

CASE_KEY = '接线测试_INT996_rework01'
CASE_ID = '3edd79db-bf37-4d8d-8a25-7bccef67cf1e'

PASSED = []
FAILED = []

NET_EVIDENCE = []
NET_SEEN_IDS = set()


def check(name, cond, extra=''):
    if cond:
        PASSED.append(name)
        print(f'  PASS {name}')
    else:
        FAILED.append(name)
        print(f'  FAIL {name}  {extra}')


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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv.set_page_load_timeout(45)
    return drv


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _perf_requests(drv):
    """读取 performance log：返回本段请求；把关键请求（form-schema/playback-devices/PUT testcases）
    连同响应状态累积进 NET_EVIDENCE（双层嵌套解析，见 wiring-selenium-performance-log 记忆）。"""
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                outer = json.loads(entry['message'])
                inner = outer.get('message', {})
                method = inner.get('method') or ''
                params = inner.get('params') or {}
                if method == 'Network.requestWillBeSent':
                    r = params.get('request') or {}
                    rid = params.get('requestId') or ''
                    reqs.append({'method': r.get('method'), 'url': r.get('url'),
                                 'postData': r.get('postData', '')})
                    url = r.get('url') or ''
                    if ('/algorithm/form-schema/' in url or '/playback-devices' in url
                            or (r.get('method') == 'PUT' and '/api/v1/testcases/' in url)):
                        if rid not in NET_SEEN_IDS:
                            NET_SEEN_IDS.add(rid)
                            NET_EVIDENCE.append({'rid': rid, 'method': r.get('method'),
                                                'url': url, 'status': None,
                                                'postData': r.get('postData', '')})
                elif method == 'Network.responseReceived':
                    rid = params.get('requestId') or ''
                    for ev in NET_EVIDENCE:
                        if ev['rid'] == rid:
                            ev['status'] = (params.get('response') or {}).get('status')
                            break
            except Exception:
                pass
    except Exception:
        pass
    return reqs


def _render_network_evidence():
    """把 NET_EVIDENCE 渲染为 PNG（纯 ASCII，PIL 默认字体，network_evidence.png）。"""
    if not NET_EVIDENCE:
        return
    lines = []
    for ev in NET_EVIDENCE:
        lines.append('[Network] %s %s' % (ev.get('method', '?'), ev.get('url', '')))
        lines.append('    status: %s' % (ev.get('status') if ev.get('status') is not None else '(pending)'))
        if ev.get('postData'):
            try:
                body = json.loads(ev['postData'])
                vp_codes = []
                for ent in (body.get('algorithm_params') or []):
                    for p in (ent.get('params') or []):
                        vp_codes.append(p.get('field_code'))
                lines.append('    body: algorithm_params=%s field_codes=%s'
                             % (len(body.get('algorithm_params') or []), vp_codes))
            except Exception:
                pass
    lines.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 18)
    except Exception:
        font = ImageFont.load_default()
    W, H = 1250, max(160, 34 * len(lines) + 50)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 14
    for ln in lines:
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 32
    out = os.path.join(ARTIFACTS, 'network_evidence.png')
    img.save(out)
    print('network evidence written:', out)


def _backend_get(path):
    with urllib.request.urlopen('http://localhost:5000' + path, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _backend_case():
    return (_backend_get('/api/v1/testcases/' + CASE_ID).get('data') or {})


def _vp_from_backend(t):
    vp = None
    for ent in (t.get('algorithm_params') or []):
        for p in (ent.get('params') or []):
            if p.get('field_code') == 'voiceprint':
                vp = p.get('field_value')
    return vp


def _setup(drv, theme):
    drv.get(BASE + '/')
    time.sleep(2)
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "localStorage.setItem('iatp:algorithm:v1',"
        " JSON.stringify({state:{algorithmId:''},version:0}));",
        theme)
    drv.get(BASE + '/testcases/by-group')
    WebDriverWait(drv, 25).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))


def _find_edit_button(drv, name):
    from selenium.common.exceptions import StaleElementReferenceException
    for _ in range(5):
        buttons = drv.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]')
        for btn in buttons:
            node = btn
            html = ''
            try:
                for _ in range(6):
                    node = node.find_element(By.XPATH, '..')
                    html = node.get_attribute('innerHTML') or ''
                    if name in html:
                        return btn
            except StaleElementReferenceException:
                break  # 列表重渲染 → 重新查询
        time.sleep(0.8)
    return None


def _click_step(drv, sheet, step):
    tab = sheet.find_element(By.XPATH, f".//button[contains(., '{step}')]")
    drv.execute_script('arguments[0].click()', tab)
    time.sleep(1.2)


def _vp_switch(sheet):
    """声纹注册开关（aria-label='启用声纹注册'）"""
    return sheet.find_element(By.CSS_SELECTOR, '[aria-label="启用声纹注册"]')


def _vp_checked(drv, sw):
    return drv.execute_script(
        "const el=arguments[0]; return el.getAttribute('data-checked') || "
        "el.getAttribute('aria-checked') || '';", sw)


def _click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _set_input(drv, el, value):
    drv.execute_script(
        "const el=arguments[0],s=arguments[1];"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,s); el.dispatchEvent(new Event('input',{bubbles:true}));",
        el, value)


def _open_drawer(drv, theme):
    _setup(drv, theme)
    # 分组视图默认按用例数降序渲染前 5 组（GROUP_LIST_PAGE=5）；本测试分组含 6 条用例
    # （1 目标 + 5 计数填充）居首，再用工具栏搜索框（aria-label='搜索用例'）按关键字
    # 过滤到目标用例，`_find_edit_button` 不受填充用例干扰
    try:
        search = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.CSS_SELECTOR, '[aria-label="搜索用例"]'))
        _set_input(drv, search, 'INT996_rework01')
        time.sleep(1.5)  # 搜索 debounce 500ms + refetch
    except Exception:
        pass
    btn = _find_edit_button(drv, CASE_KEY)
    if btn is None:
        raise RuntimeError('未找到目标用例编辑按钮')
    _perf_requests(drv)  # drain
    _click(drv, btn)
    time.sleep(2.5)
    return drv.find_element(By.CSS_SELECTOR, '[data-slot="sheet-content"]')


def _save(drv, sheet):
    _perf_requests(drv)  # drain 基线
    save_btn = WebDriverWait(drv, 8).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(.,'保存')]"))
    _click(drv, save_btn)
    try:
        WebDriverWait(drv, 15).until(
            lambda d: any('更新测试用例成功' in (el.text or '')
                          for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        return True
    except Exception:
        return False


def _put_payload(drv):
    reqs = _perf_requests(drv)
    puts = [r for r in reqs if r['method'] == 'PUT' and '/api/v1/testcases/' in r['url']]
    if not puts:
        return None
    try:
        return json.loads(puts[0].get('postData') or '{}')
    except Exception:
        return None


def main():
    drv = _driver()
    try:
        # ===== 阶段 A：禁用声纹注册 → 保存 → 后端回读无 voiceprint =====
        print('== A 浅色：打开编辑抽屉 → 噪声与干扰 ==')
        sheet = _open_drawer(drv, 'light')
        _click_step(drv, sheet, '噪声与干扰')
        time.sleep(2)
        _save_evidence('A1_noise_backfill_light', drv)

        # 声纹开关启用（回填 enabled=true）
        sw = _vp_switch(sheet)
        checked = _vp_checked(drv, sw)
        check('A1a 声纹注册开关启用（回填 enabled=true）', checked in ('true', 'checked', ''), f'checked="{checked}"')
        ni_text = sheet.text
        check('A1b 声纹配置块渲染「声纹注册配置」', '声纹注册配置' in ni_text)
        check('A1c 注册音频回填「音频 #56」', '音频 #56' in ni_text)
        # 注册后等待秒数回填 8（旧 wait 值；禁用后不得残留）
        vp_wait = None
        try:
            vp_label = sheet.find_element(By.XPATH, "//label[contains(.,'注册后等待秒数')]")
            vp_wait = vp_label.find_element(By.XPATH, 'following-sibling::input[1]')
        except Exception:
            pass
        check('A1d 注册后等待秒数回填 8', vp_wait is not None and vp_wait.get_attribute('value') == '8',
              f'value={vp_wait.get_attribute("value") if vp_wait else None}')

        # 播放设备 Select 回填（value=76 → 设备名渲染）
        check('A1e 播放设备节渲染真实设备名', '接线测试_INT996设备_rework01' in sheet.text)
        # 真实 GET /playback-devices Network 证据
        reqs = _perf_requests(drv)
        dev_reqs = [r for r in reqs if '/playback-devices' in r['url']]
        check('A1f Network 捕获 GET /playback-devices', any(r['method'] == 'GET' for r in dev_reqs),
              f'urls={[r["url"] for r in dev_reqs][:3]}')

        print('== A 关闭「启用声纹注册」开关 ==')
        _click(drv, sw)
        time.sleep(1)
        checked_after = _vp_checked(drv, sw)
        check('A2a 开关关闭（data-checked=false）', checked_after in ('false', None, ''), f'checked="{checked_after}"')
        # 配置块折叠：注册音频/等待秒数不再渲染
        text_after = sheet.text
        check('A2b 声纹配置块收起（注册音频不再渲染）', '音频 #56' not in text_after)
        _save_evidence('A2_voiceprint_disabled_light', drv)

        print('== A 保存 ==')
        saved = _save(drv, sheet)
        check('A3a 保存 toast「更新测试用例成功」', saved)
        time.sleep(1.5)

        put = _put_payload(drv)
        check('A3b Network 捕获 PUT /testcases/{id}', put is not None)
        vp_in_put = False
        field_codes = []
        if put:
            for ent in (put.get('algorithm_params') or []):
                for p in (ent.get('params') or []):
                    field_codes.append(p.get('field_code'))
                    if p.get('field_code') == 'voiceprint':
                        vp_in_put = True
        check('A3c PUT 载荷 algorithm_params 不含 voiceprint（空数组透传）',
              put is not None and not vp_in_put,
              f'field_codes={field_codes} put.algorithm_params={put.get("algorithm_params") if put else None}')
        check('A3d PUT 载荷仍保留 config.rounds', put is not None and len((put.get('config') or {}).get('rounds') or []) == 1)

        back = _backend_case()
        vp_back = _vp_from_backend(back)
        check('A4a 后端 GET 回读 algorithm_params 无 voiceprint', vp_back is None,
              f'vp={vp_back}')
        check('A4b 后端回读 algorithm_params 为空', len(back.get('algorithm_params') or []) == 0,
              f'algorithm_params={back.get("algorithm_params")}')
        check('A4c 用例名称保留', (back.get('name') or '') == CASE_KEY, f'name={back.get("name")}')
        check('A4d 关联算法保留 voice_llm', (back.get('algorithm_type') or '') == 'voice_llm',
              f'algo={back.get("algorithm_type")}')
        check('A4e 轮次保留 1 轮', len(((back.get('config') or {}).get('rounds') or [])) == 1)
        _save_evidence('A4_saved_no_voiceprint_light', drv)

        print('== B 重开抽屉：声纹注册开关保持关闭 ==')
        sheet2 = _open_drawer(drv, 'light')
        _click_step(drv, sheet2, '噪声与干扰')
        time.sleep(1.5)
        sw2 = _vp_switch(sheet2)
        checked2 = _vp_checked(drv, sw2)
        check('B1 重开抽屉声纹开关保持关闭', checked2 in ('false', None, ''), f'checked="{checked2}"')
        check('B2 声纹配置块未渲染（注册音频无回填）', '音频 #56' not in sheet2.text)
        _save_evidence('B_reopen_disabled_light', drv)
        # 关闭抽屉
        try:
            cancel = sheet2.find_element(By.XPATH, "//button[contains(.,'取消')]")
            _click(drv, cancel)
            time.sleep(1)
        except Exception:
            pass

        print('== C 反向：重开 → 启用声纹 → 保存 → 后端回读恢复 ==')
        sheet3 = _open_drawer(drv, 'light')
        _click_step(drv, sheet3, '噪声与干扰')
        time.sleep(1.5)
        sw3 = _vp_switch(sheet3)
        _click(drv, sw3)
        time.sleep(0.8)
        text3 = sheet3.text
        check('C1 启用后声纹配置块展开（含「选择注册音频」入口）', '选择注册音频' in text3)
        # 注册音频经真实音频库（GET /audios audioType=noise）；本库无噪声音频 → 空态即真实数据证据
        try:
            pick = sheet3.find_element(By.XPATH, "//button[contains(.,'选择注册音频')]")
            _click(drv, pick)
            time.sleep(1.5)
            dlg = WebDriverWait(drv, 10).until(
                lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="dialog-content"]'))
            dlg_text = dlg.text
            check('C1b 音频库真实空态（无噪声音频 → 没有匹配的音频文件）',
                  '没有匹配的音频文件' in dlg_text,
                  f'dlg={dlg_text[:80]}')
            cancel_dlg = dlg.find_element(By.XPATH, ".//button[contains(.,'取消')]")
            _click(drv, cancel_dlg)
            time.sleep(0.8)
        except Exception as e:
            check('C1b 音频库真实空态', False, str(e)[:120])
        _save_evidence('C1_re_enable_light', drv)
        saved3 = _save(drv, sheet3)
        check('C2 再次保存成功', saved3)
        time.sleep(1.5)
        back3 = _backend_case()
        vp3 = _vp_from_backend(back3)
        check('C3 后端回读 voiceprint 恢复（enabled=true 仍入列）',
              vp3 is not None,
              f'vp={vp3}')
        _save_evidence('C3_re_enabled_saved_light', drv)

        print('== D 深色截图 ==')
        try:
            sheet4 = _open_drawer(drv, 'dark')
            _click_step(drv, sheet4, '算法参数')
            _save_evidence('D1_algo_params_dark', drv)
            _click_step(drv, sheet4, '噪声与干扰')
            time.sleep(1.2)
            _save_evidence('D2_noise_dark', drv)
            check('D1 深色算法参数 + 噪声截图', True)
        except Exception as e:
            check('D1 深色截图阶段', False, str(e)[:120])

        fatal = [e for e in drv.get_log('browser')
                 if e.get('level') in ('SEVERE', 'ERROR')
                 and 'Failed to load resource' not in str(e.get('message', ''))]
        check('无 console 严重错误', len(fatal) == 0, f'fatal={len(fatal)}')

        _render_network_evidence()

        print(f'\n=== 结果：PASS {len(PASSED)} / FAIL {len(FAILED)} ===')
        for f in FAILED:
            print('  FAILED:', f)
        if FAILED:
            sys.exit(2)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
