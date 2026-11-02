# -*- coding: utf-8 -*-
"""INT-2358 验收：参数策略列表「字段 / 映射」按详情计数 + 删除文案按作用域。

用法：
  修复侧（交付 sha 构建的旁路容器，15258）：
    python verify_int2358_param_profile_counts.py --base http://localhost:15258 --mode fix
  缺陷侧（共享 15173 旧镜像，不含本卡改动）：
    python verify_int2358_param_profile_counts.py --base http://localhost:15173 --mode old

验收标准（卡内）：
  ① 算法配置 → 参数策略（算法类型「全部算法」/作用域「全部作用域」）每行「字段 / 映射」
     与详情接口 GET /algorithm/param-profiles/{id} 的 params / mappings 条数一致，
     不再恒为 0；列表接口本身不带计数（修复侧为逐条详情请求）。
  ② 删除二次确认按作用域给文案：api → 「API 将回落为未绑定（实例覆盖行保留）」，
     device → 「设备将回落为未绑定」。
  ③ 浅色 / 深色截图；浏览器控制台无 SEVERE；涉及接口均 200。
数据卫生：本脚本只读（删除弹窗点「取消」），不写入任何数据。
输出：tests/ui/artifacts/int2358_<mode>/run.log + summary.json + 截图。
"""
import argparse
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _int2102_api as gw  # noqa: E402  docker :15000 网关 + RSA-OAEP 登录

PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DLG = "[data-slot='dialog-content']"


# ---------------------------------------------------------------- selenium --
def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)


def wait_for(cond, timeout=30, desc='condition', interval=0.3):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            value = cond()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(interval)
    raise AssertionError('timeout waiting for %s (last error: %r)' % (desc, last))


def shot(drv, artifacts, name):
    os.makedirs(artifacts, exist_ok=True)
    path = os.path.join(artifacts, name)
    drv.save_screenshot(path)
    return path


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.toggle('dark', arguments[0]==='dark');",
        mode,
    )
    time.sleep(0.8)


def collect_requests(drv):
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
        except Exception:  # noqa: BLE001
            continue
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            reqs[params.get('requestId')] = {
                'method': req.get('method', 'GET'),
                'url': req.get('url') or '',
                'status': None,
            }
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                reqs[rid]['status'] = (params.get('response') or {}).get('status')
    return list(reqs.values())


def console_severe(drv):
    out = []
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                out.append(entry.get('message', '')[:300])
    except Exception:  # noqa: BLE001
        pass
    return out


# -------------------------------------------------------------------- page --
def login(drv, base):
    drv.get(base + '/login')
    wait_for(lambda: drv.find_elements(By.ID, 'username'), timeout=60, desc='登录页')
    drv.find_element(By.ID, 'username').send_keys('dev_user')
    drv.find_element(By.ID, 'password').send_keys('dev_password')
    drv.execute_script("document.querySelector('form').requestSubmit()")
    wait_for(
        lambda: drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')"),
        timeout=60,
        desc='登录 token 落库',
    )
    wait_for(lambda: '/login' not in drv.current_url, timeout=30, desc='离开登录页')
    time.sleep(1.0)


def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, DLG) if e.is_displayed()]


def top_dialog(drv):
    els = visible_dialogs(drv)
    return els[-1] if els else None


def visible_select_items(drv):
    return drv.execute_script(
        "return [...document.querySelectorAll('[data-slot=\"select-item\"]')]"
        ".filter(e => (e.offsetWidth||e.offsetHeight)).map(e => e.innerText.trim())"
    ) or []


def click_select_option(drv, dlg, index, label, timeout=15):
    """在 dlg 里第 index 个 select 上选 label；已选则直接返回。"""
    trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    trig = trigs[index]
    cur = (trig.text or '').strip()
    if cur == label:
        return cur
    drv.execute_script('arguments[0].click()', trig)
    try:
        wait_for(lambda: label in visible_select_items(drv), timeout=timeout, desc='下拉项 %s' % label)
        drv.execute_script(
            "const items=[...document.querySelectorAll('[data-slot=\"select-item\"]')]"
            ".filter(e => (e.offsetWidth||e.offsetHeight));"
            "const t=items.find(e => e.innerText.trim()===arguments[0]);"
            "if (t) t.click();",
            label,
        )
    except AssertionError:
        # 再试一次：弹层可能因重渲染被关掉
        drv.execute_script('arguments[0].click()', trig)
        wait_for(lambda: label in visible_select_items(drv), timeout=timeout, desc='下拉项 %s(重试)' % label)
        drv.execute_script(
            "const items=[...document.querySelectorAll('[data-slot=\"select-item\"]')]"
            ".filter(e => (e.offsetWidth||e.offsetHeight));"
            "const t=items.find(e => e.innerText.trim()===arguments[0]);"
            "if (t) t.click();",
            label,
        )
    time.sleep(0.5)
    return cur


def open_manager(drv, base, log):
    drv.get(base + '/AlgorithmConfig')
    wait_for(
        lambda: drv.find_elements(By.XPATH, "//button[normalize-space(.)='参数策略']"),
        timeout=60,
        desc='算法配置页「参数策略」按钮',
    )
    btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='参数策略']")
    drv.execute_script('arguments[0].click()', btn)
    dlg = wait_for(lambda: top_dialog(drv), timeout=30, desc='参数策略弹窗')
    wait_for(
        lambda: dlg.find_elements(By.XPATH, ".//*[normalize-space(.)='字段']"),
        timeout=30,
        desc='表头 字段',
    )
    trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    log('dialog select triggers: %s' % [(t.text or '').strip() for t in trigs])
    click_select_option(drv, dlg, 0, '全部算法')
    click_select_option(drv, dlg, 1, '全部作用域')
    log('filters now: %s' % [
        (t.text or '').strip()
        for t in dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    ])
    return dlg


def read_rows(dlg):
    rows = dlg.find_elements(By.XPATH, './/table/tbody/tr')
    out = []
    for row in rows:
        tds = row.find_elements(By.XPATH, './td')
        texts = [(td.text or '').strip() for td in tds]
        if len(texts) < 7:
            continue
        out.append({
            'name': texts[0].split('\n')[0],
            'algorithm': texts[1],
            'scope': texts[2],
            'status': texts[3],
            'paramCount': texts[4],
            'mappingCount': texts[5],
        })
    return out


def wait_counts_settled(dlg, timeout=45):
    def ready():
        rows = read_rows(dlg)
        if not rows:
            return None
        if all(r['paramCount'].isdigit() and r['mappingCount'].isdigit() for r in rows):
            return rows
        return None
    return wait_for(ready, timeout=timeout, desc='字段/映射计数加载完成（不再是 —）')


def open_delete_confirm(drv, dlg, scope_label):
    rows = dlg.find_elements(By.XPATH, './/table/tbody/tr')
    target = None
    for row in rows:
        tds = row.find_elements(By.XPATH, './td')
        if len(tds) >= 3 and (tds[2].text or '').strip() == scope_label:
            target = row
            break
    if target is None:
        raise AssertionError('未找到作用域为 %s 的策略行' % scope_label)
    btns = target.find_elements(By.XPATH, ".//button[normalize-space(.)='删除']")
    drv.execute_script('arguments[0].click()', btns[-1])
    cd = wait_for(
        lambda: next(
            (d for d in visible_dialogs(drv) if '删除参数策略' in (d.text or '')),
            None,
        ),
        timeout=20,
        desc='删除确认弹窗',
    )
    desc_el = cd.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-description']")
    text = (desc_el[-1].text or '').strip() if desc_el else (cd.text or '').strip()
    cancel = cd.find_elements(By.XPATH, ".//button[normalize-space(.)='取消']")
    drv.execute_script('arguments[0].click()', cancel[-1])
    wait_for(lambda: not any('删除参数策略' in (d.text or '') for d in visible_dialogs(drv)),
             timeout=20, desc='删除确认弹窗关闭')
    time.sleep(0.4)
    return text


# --------------------------------------------------------------------- api --
def api_snapshot():
    token, resp = gw._login()
    if not token:
        raise AssertionError('网关登录失败: %r' % (resp,))
    status, payload = gw._req('GET', '/algorithm/param-profiles', token=token)
    if status != 200:
        raise AssertionError('列表接口 %s: %r' % (status, payload))
    profiles = (((payload or {}).get('data') or {}).get('profiles')) or []
    rows = []
    for p in profiles:
        st, detail = gw._req('GET', '/algorithm/param-profiles/%s' % p['id'], token=token)
        det = (detail or {}).get('data') or {}
        rows.append({
            'id': p['id'],
            'name': p.get('name'),
            'algorithm': p.get('algorithm_type') or '',
            'scope': 'API' if p.get('scope') == 'api' else '设备',
            'params': len(det.get('params') or []),
            'mappings': len(det.get('mappings') or []),
            'status': st,
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15258')
    ap.add_argument('--mode', choices=['fix', 'old'], default='fix')
    ap.add_argument('--artifacts', default='')
    args = ap.parse_args()
    artifacts = args.artifacts or os.path.join(HERE, 'artifacts', 'int2358_%s' % args.mode)
    os.makedirs(artifacts, exist_ok=True)
    log_path = os.path.join(artifacts, 'run.log')

    def log(msg):
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
        print(line)
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')

    errors = []
    drv = _driver()
    summary = {'base': args.base, 'mode': args.mode, 'artifacts': artifacts}
    try:
        login(drv, args.base)
        log('login ok -> %s' % drv.current_url)
        expected = api_snapshot()
        log('api rows: %s' % json.dumps(expected, ensure_ascii=False))

        dlg = open_manager(drv, args.base, log)
        rows = wait_counts_settled(dlg)
        log('ui rows: %s' % json.dumps(rows, ensure_ascii=False))
        summary['ui_rows'] = rows
        summary['api_rows'] = expected

        # ① 计数与详情一致（按 算法类型 + 作用域 配对：真实库 6 条策略同名 default）
        ui_key = {(r['algorithm'], r['scope']): (r['paramCount'], r['mappingCount']) for r in rows}
        api_key = {(r['algorithm'], r['scope']): (str(r['params']), str(r['mappings'])) for r in expected}
        summary['count_match'] = ui_key == api_key
        if args.mode == 'fix':
            if len(rows) != len(expected):
                errors.append('行数不一致：UI %d vs API %d' % (len(rows), len(expected)))
            if ui_key != api_key:
                errors.append('计数与详情不一致：UI %r vs API %r' % (ui_key, api_key))
            if any(r['name'] == 'default' and r['paramCount'] == '—' for r in rows):
                errors.append('仍有行未取到计数（—）')
        else:
            # 缺陷侧：旧实现恒 0 / 0，用 A/B 证明脚本能区分
            if not all(r['paramCount'] == '0' and r['mappingCount'] == '0' for r in rows):
                errors.append('旧镜像预期恒 0/0，实际 %r' % ui_key)

        # ② 删除文案按作用域
        shot(drv, artifacts, 'list_light.png')
        set_theme(drv, 'dark')
        shot(drv, artifacts, 'list_dark.png')
        set_theme(drv, 'light')

        api_text = open_delete_confirm(drv, dlg, 'API')
        device_text = open_delete_confirm(drv, dlg, '设备')
        summary['delete_text'] = {'api': api_text, 'device': device_text}
        log('delete text api=%r device=%r' % (api_text, device_text))
        if args.mode == 'fix':
            if '绑定该策略的 API 将回落为未绑定（实例覆盖行保留）' not in api_text:
                errors.append('API 策略删除文案不符：%r' % api_text)
            if '绑定该策略的设备将回落为未绑定' not in device_text:
                errors.append('设备策略删除文案不符：%r' % device_text)
        else:
            if '设备' in device_text:
                errors.append('旧镜像预期设备策略文案仍只提 API，实际 %r' % device_text)

        # 网络证据
        time.sleep(1.0)
        reqs = [r for r in collect_requests(drv) if '/algorithm/param-profiles' in r['url']]
        list_reqs = [r for r in reqs if r['url'].rstrip('/').endswith('param-profiles')]
        detail_reqs = [r for r in reqs if '/param-profiles/' in r['url']]
        summary['network'] = {
            'list': [{'status': r['status'], 'url': r['url']} for r in list_reqs],
            'details': [{'status': r['status'], 'url': r['url']} for r in detail_reqs],
        }
        log('network: list=%d detail=%d statuses=%s' % (
            len(list_reqs), len(detail_reqs),
            sorted({r['status'] for r in reqs})))
        bad = [r for r in reqs if r['status'] not in (200, 304)]
        if bad:
            errors.append('参数策略接口非 200：%r' % [(r['status'], r['url']) for r in bad[:5]])
        if args.mode == 'fix':
            if len(detail_reqs) != len(expected):
                errors.append('详情请求数 %d != 策略数 %d' % (len(detail_reqs), len(expected)))

        severe = console_severe(drv)
        summary['console_severe'] = severe
        if severe:
            errors.append('浏览器控制台 SEVERE %d 条：%r' % (len(severe), severe[:3]))
    except Exception as exc:  # noqa: BLE001
        errors.append('异常：%r' % exc)
        try:
            shot(drv, artifacts, 'error_state.png')
        except Exception:
            pass
    finally:
        summary['errors'] = errors
        summary['passed'] = not errors
        with open(os.path.join(artifacts, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        log('RESULT %s errors=%s' % ('PASS' if not errors else 'FAIL', json.dumps(errors, ensure_ascii=False)))
        try:
            drv.quit()
        except Exception:
            pass
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
