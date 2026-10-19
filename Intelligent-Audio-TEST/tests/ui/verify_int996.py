# -*- coding: utf-8 -*-
"""INT-996 用例编辑抽屉「算法参数 schema + 噪声与干扰」真实数据接线复测
（真实 Chrome headless + 常驻 5000 后端 + dev server 5318）。

卡内验收：真实数据回填 + 保存生效 + Network 截图。
逐条核对：
- P1-1 算法参数步骤走真实 GET /algorithm/form-schema/voice_llm（Network 证据），
  schema 空字段时渲染「该算法暂无参数配置」空态 + 算法名「小艺语音大模型」。
- P1-2 噪声与干扰回填：背景噪声节显示 audio_name（audios[0].background_noise）、
  声纹注册节启用 + 注册音频回填（algorithm_params voiceprint）、干扰人列表 2 条
  （audios[0].interferers）。
- P1-3 播放设备走真实 GET /playback-devices（Network 证据；库空则显示空态）。
- P1-4 保存生效：改背景噪声声压级 + 声纹等待秒数 → 保存 → Network 捕获
  PUT /testcases/{id}（config.rounds[].audios[].background_noise/interferers +
  algorithm_params voiceprint 均在载荷）→ 后端 GET 回读变更落库。
失败落 tests/ui/artifacts/int996_seg_noise/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int996_seg_noise')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5318')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# INT-996 自建测试用例（run 结束前删除；segment 级 background_noise/interferers + voiceprint + 算法参数）
CASE_KEY = 'INT996_segnoise'

PASSED = []
FAILED = []

# Network 证据累积（真实请求 + 状态；渲染 network_evidence.png）
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
    """读取 performance log：返回本段请求；同时把关键请求（form-schema/playback-devices/PUT testcases）
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
                cfg = body.get('config') or {}
                rounds = cfg.get('rounds') or []
                a0 = (rounds[0].get('audios') or [{}])[0] if rounds else {}
                bn = a0.get('background_noise') or {}
                itf = a0.get('interferers') or []
                vp = None
                for ent in (body.get('algorithm_params') or []):
                    for p in (ent.get('params') or []):
                        if p.get('field_code') == 'voiceprint':
                            vp = p.get('field_value')
                lines.append('    body: background_noise.spl=%s interferers=%d voiceprint.wait=%s'
                             % (bn.get('spl'), len(itf),
                                (vp or {}).get('voiceprint_wait_time')))
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


def _find_case_id():
    data = _backend_get('/api/v1/testcases?keyword=' + CASE_KEY + '&per_page=10')
    items = ((data.get('data') or {}).get('items')) or []
    for it in items:
        if CASE_KEY in (it.get('name') or ''):
            return it['id']
    return None


def _find_edit_button(drv, name):
    buttons = drv.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]')
    for btn in buttons:
        node = btn
        html = ''
        for _ in range(6):
            node = node.find_element(By.XPATH, '..')
            html = node.get_attribute('innerHTML') or ''
            if name in html:
                return btn
    return None


def _set_input(drv, el, value):
    drv.execute_script(
        "const el=arguments[0],s=arguments[1];"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,s); el.dispatchEvent(new Event('input',{bubbles:true}));",
        el, value)


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


def _click_step(drv, sheet, step):
    tab = sheet.find_element(By.XPATH, f"//button[contains(., '{step}')]")
    drv.execute_script('arguments[0].click()', tab)
    time.sleep(1.2)


def main():
    case_id = _find_case_id()
    if not case_id:
        print('FAIL 未找到 INT-996 测试用例，先创建再复测')
        sys.exit(2)
    drv = _driver()
    try:
        print('== 准备：浅色 / 清全局算法筛选 ==')
        _setup(drv, 'light')

        print('== 打开 INT-996 用例编辑抽屉 ==')
        target_btn = _find_edit_button(drv, CASE_KEY)
        check('找到目标用例「编辑用例」按钮', target_btn is not None)
        if target_btn is None:
            _save_evidence('01_case_not_found', drv)
            raise RuntimeError('未找到目标用例卡')
        # 打开前先 drain：抽屉默认落在「算法参数」步骤，form-schema 请求随抽屉打开即发起
        _perf_requests(drv)
        drv.execute_script('arguments[0].click()', target_btn)
        time.sleep(2.5)
        sheet = drv.find_element(By.CSS_SELECTOR, '[data-slot="sheet-content"]')
        _save_evidence('02_drawer_open_light', drv)

        # 关联算法回填（算法参数 schema 依赖）
        try:
            al = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.XPATH, "//label[contains(.,'关联算法')]"))
            sec_text = al.find_element(By.XPATH, 'ancestor::section').text
            check('关联算法回填显示 小艺语音大模型',
                  '小艺语音大模型' in sec_text and '请选择算法' not in sec_text,
                  f'section="{sec_text[:60]}"')
        except Exception as e:
            check('关联算法回填显示 小艺语音大模型', False, str(e)[:100])

        print('== P1-1 算法参数步骤：真实 form-schema ==')
        _click_step(drv, sheet, '算法参数')
        time.sleep(1.5)
        step_text = sheet.text
        check('算法参数步骤渲染算法名「小艺语音大模型」', '小艺语音大模型' in step_text)
        reqs = _perf_requests(drv)
        schema_reqs = [r for r in reqs if '/algorithm/form-schema/' in r['url']]
        check('Network 捕获 GET /algorithm/form-schema/voice_llm',
              any('voice_llm' in r['url'] for r in schema_reqs),
              f'urls={[r["url"] for r in schema_reqs][:3]}')
        check('schema 空字段 → 空态「该算法暂无参数配置」', '该算法暂无参数配置' in step_text)
        _save_evidence('03_algo_params_real_schema_light', drv)

        print('== P1-3 播放设备真实数据 ==')
        _perf_requests(drv)  # drain
        _click_step(drv, sheet, '噪声与干扰')
        time.sleep(2)
        reqs = _perf_requests(drv)
        dev_reqs = [r for r in reqs if '/playback-devices' in r['url']]
        check('Network 捕获 GET /playback-devices', any(r['method'] == 'GET' for r in dev_reqs),
              f'urls={[r["url"] for r in dev_reqs][:3]}')
        check('库空 → 空态「暂无可用的播放设备」', '暂无可用的播放设备' in sheet.text)

        print('== P1-2 噪声与干扰回填（segment 级 + voiceprint） ==')
        ni_text = sheet.text
        check('背景噪声节回填 audio_name「兼容测试_01.wav」', '兼容测试_01.wav' in ni_text)
        check('背景噪声声压级回填 94', '94' in ni_text)
        check('声纹注册节启用 + 注册音频回填「兼容测试_01.wav」',
              '声纹注册配置' in ni_text and '兼容测试_01.wav' in ni_text)
        check('干扰人列表回填 2 条', '干扰人 1' in ni_text and '干扰人 2' in ni_text)
        # 干扰人声压级（number input value 不在 textContent 中，读 DOM；
        # 干扰人卡片 label 恰为「声压级 dB」，与「噪声声压级 dB」「播放声压级 dB」精确区分）
        ifr_spl_values = []
        try:
            sec_ifr = drv.find_element(By.XPATH, "//section[contains(.,'干扰人配置')]")
            for inp in sec_ifr.find_elements(By.XPATH, ".//label[normalize-space(.)='声压级 dB']/following-sibling::input"):
                ifr_spl_values.append(inp.get_attribute('value'))
        except Exception as e:
            check('读取干扰人声压级输入', False, str(e)[:100])
        check('干扰人声压级回填 70 / 65', ifr_spl_values[:2] == ['70', '65'],
              f'values={ifr_spl_values}')
        _save_evidence('04_noise_backfill_light', drv)

        print('== P1-4 保存生效（改背景噪声声压级 + 声纹等待秒数） ==')
        # 背景噪声声压级输入（Label 的直接兄弟 input）
        bg_spl = None
        try:
            bg_label = drv.find_element(By.XPATH, "//label[contains(.,'噪声声压级 dB')]")
            bg_spl = bg_label.find_element(By.XPATH, 'following-sibling::input[1]')
        except Exception:
            pass
        check('定位背景噪声声压级输入', bg_spl is not None)
        if bg_spl:
            _set_input(drv, bg_spl, '90')
        # 声纹注册等待秒数输入（声纹节已启用）
        vp_wait = None
        try:
            vp_label = drv.find_element(By.XPATH, "//label[contains(.,'注册后等待秒数')]")
            vp_wait = vp_label.find_element(By.XPATH, 'following-sibling::input[1]')
        except Exception:
            pass
        check('定位声纹注册等待秒数输入', vp_wait is not None)
        if vp_wait:
            _set_input(drv, vp_wait, '8')
        time.sleep(0.5)
        # 回读当前输入值确认 state 已更新
        try:
            bg_now = bg_spl.get_attribute('value') if bg_spl else ''
            vp_now = vp_wait.get_attribute('value') if vp_wait else ''
            check('背景噪声声压级输入已改为 90', bg_now == '90', f'value="{bg_now}"')
            check('声纹等待秒数输入已改为 8', vp_now == '8', f'value="{vp_now}"')
        except Exception:
            pass

        _perf_requests(drv)  # drain 基线
        save_btn = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(.,'保存')]"))
        drv.execute_script('arguments[0].click()', save_btn)
        toast_ok = False
        try:
            WebDriverWait(drv, 15).until(
                lambda d: any('更新测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            toast_ok = True
        except Exception:
            pass
        check('P1-4a 保存 toast「更新测试用例成功」', toast_ok)

        reqs = _perf_requests(drv)
        puts = [r for r in reqs if r['method'] == 'PUT' and '/api/v1/testcases/' in r['url']]
        put = puts[0] if puts else None
        check('P1-4b Network 捕获 PUT /testcases/{id}', put is not None,
              f'puts={[r["url"] for r in puts][:2]}')
        payload_ok = False
        if put:
            try:
                body = json.loads(put.get('postData') or '{}')
                cfg = body.get('config') or {}
                rounds = cfg.get('rounds') or []
                a0 = (rounds[0].get('audios') or [{}])[0] if rounds else {}
                bn = a0.get('background_noise') or {}
                itf = a0.get('interferers') or []
                alg = body.get('algorithm_params') or []
                vp = None
                for ent in alg:
                    for p in (ent.get('params') or []):
                        if p.get('field_code') == 'voiceprint':
                            vp = p.get('field_value')
                payload_ok = (
                    bn.get('spl') == 90
                    and len(itf) == 2
                    and itf[0].get('spl') == 70
                    and vp is not None
                    and vp.get('voiceprint_wait_time') == 8
                )
            except Exception as e:
                check('解析 PUT payload', False, str(e)[:120])
        check('P1-4c PUT payload 含 background_noise.spl=90 + interferers×2 + voiceprint.wait=8',
              payload_ok,
              f'payload={put["postData"][:600] if put else ""}')

        time.sleep(1.5)
        back = _backend_get('/api/v1/testcases/' + case_id).get('data') or {}
        cfg = back.get('config') or {}
        a0 = ((cfg.get('rounds') or [{}])[0].get('audios') or [{}])[0]
        bn_back = a0.get('background_noise') or {}
        alg_back = back.get('algorithm_params') or []
        vp_back = None
        for ent in alg_back:
            for p in (ent.get('params') or []):
                if p.get('field_code') == 'voiceprint':
                    vp_back = p.get('field_value')
        check('P1-4d 后端回读 background_noise.spl=90', bn_back.get('spl') == 90,
              f'bn={bn_back}')
        check('P1-4e 后端回读 voiceprint.wait=8', vp_back and vp_back.get('voiceprint_wait_time') == 8,
              f'vp={vp_back}')
        check('P1-4f 后端回读 interferers 保留 2 条', len(a0.get('interferers') or []) == 2)
        _save_evidence('05_saved_light', drv)

        print('== 深色截图 ==')
        try:
            _setup(drv, 'dark')
            btn2 = _find_edit_button(drv, CASE_KEY)
            if btn2:
                drv.execute_script('arguments[0].click()', btn2)
                time.sleep(1.5)
                sheet2 = drv.find_element(By.CSS_SELECTOR, '[data-slot="sheet-content"]')
                _click_step(drv, sheet2, '算法参数')
                _save_evidence('06_algo_params_dark', drv)
                _click_step(drv, sheet2, '噪声与干扰')
                time.sleep(1)
                _save_evidence('07_noise_dark', drv)
                check('深色算法参数 + 噪声与干扰截图', True)
            else:
                _save_evidence('06_dark_list', drv)
                check('深色算法参数 + 噪声与干扰截图', False, '未找到目标卡')
        except Exception as e:
            check('深色截图阶段', False, str(e)[:120])

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
