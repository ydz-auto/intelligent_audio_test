# -*- coding: utf-8 -*-
"""INT-1447 报告分享弹窗对齐 INT-1363 规格 浏览器实测（真实库栈 intelligent_audio_test）。

环境：
- dev server: http://localhost:5315（本 run 起，rsbuild.realstack.config.ts /api 代理 → 真实库栈 :5700）
- 真实库栈 :5700 AUTH_MODE=dev（表单登录 RSA-OAEP 加密链路）

验收点（INT-1447 卡内「验证」）：
1. 防串库：/health database=intelligent_audio_test。
2. 登录 → 打开 /report/{REPORT_ID} → 「分享」弹窗：
   - P2：分享方式仅「生成分享链接 / 导出后分享」两项，无「邮件分享」入口（收件人输入 / 发送邮件分享按钮 均不出现）。
3. P1 custom 有效期：
   - 有效期下拉选「自定义」→ 出现必填 datetime-local 输入；
   - 不填日期直接生成 → toast「请选择自定义有效期的日期时间」且 Network 无 POST /share；
   - 填日期生成 → Network 捕获 POST /api/v1/reports/{id}/share（body 含 expires_at）→ 200；
   - 生成后分享 URL 回填（origin 归一化为前端）。
4. 撤销（清理本 run 产物）→ Network 捕获 DELETE。
5. 深色模式同样核验（无邮件入口 + 自定义日期输入出现）。
6. 防串库二验：截图批次前后各查一次 /health。

失败落 tests/ui/artifacts/int1447_report_share_custom/<步骤>/。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5315')
REPORT_ID = os.environ.get('REPORT_ID', '497')
GATEWAY = 'http://127.0.0.1:5700'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1447_report_share_custom')
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
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _drain_perf(drv):
    logs = drv.get_log('performance')
    out = []
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method', '').startswith('Network.'):
            out.append(msg)
    return out


def _find_req(reqs, sub, method=None):
    """从 performance 日志里找 requestWillBeSent 且 URL 含 sub 的请求（方法可选）。"""
    hit = []
    for msg in reqs:
        if msg.get('method') != 'Network.requestWillBeSent':
            continue
        req = msg.get('params', {}).get('request', {})
        url = req.get('url', '')
        if sub in url and (method is None or req.get('method') == method):
            hit.append({'method': req.get('method'), 'url': url,
                        'postData': req.get('postData')})
    return hit


def _find_response(entries, url_sub):
    """从 performance 日志里找 responseReceived 且 URL 含 url_sub 的响应（含 status）。"""
    for msg in entries:
        if msg.get('method') != 'Network.responseReceived':
            continue
        params = msg.get('params', {})
        resp = params.get('response', {})
        if url_sub in resp.get('url', ''):
            return {'status': resp.get('status'), 'url': resp.get('url')}
    return None


def _save_evidence(name, drv, net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        if net:
            with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
                json.dump(net, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)


def _inpage_revoke(drv, report_id, token):
    """页内 fetch DELETE 撤销分享（浏览器会话仍有效时）。"""
    try:
        return drv.execute_async_script("""
          const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
          const r = await fetch('/api/v1/reports/' + arguments[0] + '/share/' + arguments[1], {
            method: 'DELETE',
            headers: {'Authorization': 'Bearer ' + token}
          });
          arguments[arguments.length - 1](JSON.stringify({status: r.status}));
        """, str(report_id), token)
    except Exception as e:
        return f'cleanup-fetch-failed: {e}'


def _login(drv):
    _goto(drv, '/login')
    time.sleep(1.5)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def _get_token(drv):
    return drv.execute_script("return window.localStorage.getItem('iatp:auth:token:v1')")


def _click_js(drv, el):
    drv.execute_script('arguments[0].click();', el)


def _health_db():
    import urllib.request
    with urllib.request.urlopen(GATEWAY + '/health', timeout=5) as resp:
        return json.loads(resp.read().decode()).get('database')


def _select_expiry_custom(drv):
    """打开「有效期」Select 并选「自定义」。返回是否成功。"""
    # 「有效期」label 的兄弟 combobox 才是有效期下拉（页面上另有导出弹窗的
    # 导出格式 combobox，不能按全局第几个取）。
    triggers = drv.find_elements(
        By.XPATH, "//label[normalize-space(.)='有效期']/following-sibling::button[@role='combobox']")
    if not triggers:
        return False, '未找到「有效期」下拉'
    _click_js(drv, triggers[0])
    time.sleep(0.8)
    opts = drv.find_elements(By.XPATH, "//*[@role='option'][contains(., '自定义')]")
    if not opts:
        # 兜底：按文本找列表项
        opts = drv.find_elements(By.XPATH, "//*[contains(@class,'base-SelectItem')][contains(., '自定义')]")
    if not opts:
        return False, '未找到「自定义」选项'
    _click_js(drv, opts[-1])
    time.sleep(0.8)
    return True, 'selected custom'


def _set_datetime(drv, value):
    drv.execute_script("""
      const el = document.querySelector('input[type="datetime-local"]');
      if (!el) return false;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, arguments[0]);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return true;
    """, value)


def main():
    drv = _driver()
    failures = []
    results = []
    share_token = None

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        results.append((tag, name, detail))
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
        if not cond:
            failures.append(name)

    try:
        # 1) 防串库一验
        db0 = _health_db()
        print('health.database (start) =', db0)
        check('防串库一验 /health database=intelligent_audio_test',
              db0 == 'intelligent_audio_test', str(db0))

        # 2) 登录
        _login(drv)
        check('登录成功（URL 离开 /login）', drv.current_url and '/login' not in drv.current_url,
              drv.current_url)
        check('localStorage 有 JWT', bool(_get_token(drv)))

        # 3) 打开报告页
        _goto(drv, f'/report/{REPORT_ID}')
        time.sleep(3)
        body = _body_text(drv)
        check(f'报告页 /report/{REPORT_ID} 加载', f'/report/{REPORT_ID}' in drv.current_url
              and '报告不存在' not in body, drv.current_url)
        net0 = _drain_perf(drv)
        check(f'Network 含 GET /api/v1/reports/{REPORT_ID}（报告详情真实请求）',
              len(_find_req(net0, f'/api/v1/reports/{REPORT_ID}')) > 0,
              str([n['url'] for n in _find_req(net0, f'/api/v1/reports/{REPORT_ID}')][:3]))

        # 4) 打开分享弹窗
        _drain_perf(drv)
        share_btns = drv.find_elements(By.XPATH, "//button[contains(., '分享')]")
        share_btn = None
        for b in share_btns:
            if b.text.strip() == '分享' and b.is_displayed():
                share_btn = b
                break
        check('报告头「分享」按钮存在', share_btn is not None)
        _click_js(drv, share_btn)
        WebDriverWait(drv, 10).until(
            lambda d: '分享报告' in d.execute_script('return document.body.textContent || ""'))
        check('分享弹窗打开（标题「分享报告」）', '分享报告' in _body_text(drv))

        # 5) P2：分享方式仅两项，无邮件入口
        body_dlg = _body_text(drv)
        method_btns = drv.find_elements(By.XPATH,
            "//div[@role='group' and @aria-label='分享方式']//button")
        method_labels = [b.text.strip() for b in method_btns]
        check('分享方式按钮恰 2 项（生成分享链接 / 导出后分享）',
              len(method_labels) == 2 and method_labels == ['生成分享链接', '导出后分享'],
              str(method_labels))
        check('弹窗无「邮件分享」入口文字', '邮件分享' not in body_dlg, '')
        check('弹窗无「收件人」输入', '收件人' not in body_dlg, '')
        check('弹窗无「发送邮件分享」按钮',
              len(drv.find_elements(By.XPATH, "//button[contains(., '发送邮件分享')]")) == 0, '')
        _save_evidence('01_share_dialog_no_email_light', drv)

        # 6) P1：有效期选「自定义」→ datetime-local 出现
        ok, detail = _select_expiry_custom(drv)
        check('有效期 Select 选「自定义」成功', ok, detail)
        dt_inputs = drv.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']")
        check('选「自定义」后出现 datetime-local 输入', len(dt_inputs) == 1, str(len(dt_inputs)))
        check('datetime-local 标必填（required 属性）', dt_inputs and dt_inputs[0].get_attribute('required') is not None, '')
        _save_evidence('02_custom_expiry_input_light', drv)

        # 7) 不填日期直接生成 → toast 拦截 + 无 POST
        _drain_perf(drv)
        gen_btns = drv.find_elements(By.XPATH, "//button[contains(., '生成分享链接')]")
        check('弹窗有「生成分享链接」生成钮', len(gen_btns) >= 1, str(len(gen_btns)))
        gen_btn = gen_btns[-1]
        _click_js(drv, gen_btn)
        time.sleep(2)
        toast_body = _body_text(drv)
        check('不填日期生成 → toast「请选择自定义有效期的日期时间」',
              '请选择自定义有效期的日期时间' in toast_body, '')
        net_blocked = _drain_perf(drv)
        blocked_req = _find_req(net_blocked, f'/api/v1/reports/{REPORT_ID}/share', method='POST')
        check('不填日期生成 → Network 无 POST /share', len(blocked_req) == 0,
              json.dumps(blocked_req, ensure_ascii=False))
        _save_evidence('03_custom_empty_toast_blocked', drv)

        # 8) 填日期生成 → Network POST 含 expires_at → 200
        _set_datetime(drv, '2099-12-31T23:59')
        time.sleep(0.5)
        _drain_perf(drv)
        gen_btns2 = drv.find_elements(By.XPATH, "//button[contains(., '生成分享链接')]")
        _click_js(drv, gen_btns2[-1])
        time.sleep(2.5)
        net_gen = _drain_perf(drv)
        create_req = _find_req(net_gen, f'/api/v1/reports/{REPORT_ID}/share', method='POST')
        print('  POST share captured:', json.dumps(create_req, ensure_ascii=False))
        check('填日期生成 → Network 捕获 POST /reports/{id}/share', len(create_req) == 1,
              json.dumps(create_req, ensure_ascii=False))
        if create_req:
            post_body = json.loads(create_req[0]['postData']) if create_req[0].get('postData') else {}
            print('  request body:', json.dumps(post_body, ensure_ascii=False))
            check('POST body 含 expires_at=custom 日期', post_body.get('expires_at') == '2099-12-31T23:59',
                  str(post_body.get('expires_at')))
            check('POST body expiry=custom', post_body.get('expiry') == 'custom', str(post_body.get('expiry')))
        resp = _find_response(net_gen, f'/api/v1/reports/{REPORT_ID}/share')
        check('POST /share 响应 200', resp and resp.get('status') == 200, json.dumps(resp, ensure_ascii=False))
        check('生成后弹窗显示分享统计区', '分享统计' in _body_text(drv))
        _save_evidence('04_share_generated_with_expires_light', drv, net_gen)

        # 9) 取 shareUrl 验证归一化 + 清理 token
        for inp in drv.find_elements(By.TAG_NAME, 'input'):
            val = inp.get_attribute('value') or ''
            if val.startswith('http'):
                share_url = val
                break
        else:
            share_url = ''
        print('  share_url =', share_url)
        check('弹窗显示真实 URL（前端 origin 归一化）',
              share_url.startswith(BASE) and f'report/{REPORT_ID}' in share_url, share_url)
        share_token = share_url.split('share=')[-1] if 'share=' in share_url else ''
        check('shareUrl 含 token 参数', bool(share_token), share_token)

        # 10) 防串库二验（截图批次前）
        db1 = _health_db()
        print('health.database (mid) =', db1)
        check('防串库二验 /health database=intelligent_audio_test', db1 == 'intelligent_audio_test', str(db1))

        # 11) 撤销（UI）→ Network DELETE
        _drain_perf(drv)
        revoke_btns = drv.find_elements(By.XPATH, "//button[contains(., '撤销链接')]")
        check('生成后弹窗有「撤销链接」按钮', len(revoke_btns) >= 1, '')
        _click_js(drv, revoke_btns[-1])
        time.sleep(2.5)
        net_revoke = _drain_perf(drv)
        revoke_req = _find_req(net_revoke, f'/api/v1/reports/{REPORT_ID}/share/{share_token}', method='DELETE')
        check('Network 捕获 DELETE /reports/{id}/share/{token}', len(revoke_req) == 1,
              json.dumps(revoke_req, ensure_ascii=False))
        check('撤销后分享统计区消失', '分享统计' not in _body_text(drv))
        _save_evidence('05_revoked_light', drv, net_revoke)
        share_token = None

        # 12) 深色：重新开弹窗，无邮件入口 + 自定义日期输入出现
        _set_theme(drv, 'dark')
        time.sleep(1.2)
        share_btns2 = drv.find_elements(By.XPATH, "//button[contains(., '分享')]")
        share_btn2 = None
        for b in share_btns2:
            if b.text.strip() == '分享' and b.is_displayed():
                share_btn2 = b
                break
        if share_btn2:
            _click_js(drv, share_btn2)
            time.sleep(1.2)
        dlg_dark = _body_text(drv)
        check('深色弹窗无「邮件分享」入口', '邮件分享' not in dlg_dark, '')
        ok2, detail2 = _select_expiry_custom(drv)
        check('深色「自定义」可选', ok2, detail2)
        dt_dark = drv.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']")
        check('深色选自定义后 datetime-local 出现', len(dt_dark) == 1, str(len(dt_dark)))
        _save_evidence('06_share_dialog_dark_no_email_custom', drv)

        # 13) 防串库三验（交付前）
        db2 = _health_db()
        print('health.database (end) =', db2)
        check('防串库三验 /health database=intelligent_audio_test', db2 == 'intelligent_audio_test', str(db2))

    except Exception:
        _save_evidence('FAILURE_dump', drv, _drain_perf(drv))
        raise
    finally:
        if share_token:
            try:
                cleanup = _inpage_revoke(drv, REPORT_ID, share_token)
                print('cleanup revoke:', cleanup)
            except Exception:
                pass
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ARTIFACTS, 'results.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{tag}\t{name}\t{detail}' for tag, name, detail in results))
        f.write('\n')
        f.write('FAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')

    print('=' * 50)
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
