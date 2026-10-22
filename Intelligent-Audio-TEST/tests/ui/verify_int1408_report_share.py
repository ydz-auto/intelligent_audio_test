# -*- coding: utf-8 -*-
"""INT-1408 报告分享前端接线浏览器实测（真实库栈 intelligent_audio_test）。

环境：
- dev server: http://localhost:5322（本 run 起，/api 代理 → 真实库栈 :5700）
- 真实库栈 :5700 AUTH_MODE=dev（表单登录 RSA-OAEP 加密链路）

验证点（INT-1408 卡内「验证」）：
1. 防串库：/health database=intelligent_audio_test。
2. 登录 → 打开 /report/493 → 「分享」弹窗 → 「生成分享链接」：
   - Network 捕获 POST /api/v1/reports/493/share（body 真实表单）。
   - 弹窗输入框显示真实 URL（share_url 归一化为当前前端 origin）。
3. 复制真实 URL 新标签打开 → 报告正常加载。
4. 页内 fetch GET /api/v1/reports/shared/{token}（带 Authorization）→ 200 且 visits +1；
   「刷新统计」→ Network 捕获 GET /api/v1/reports/493/share，弹窗显示 访问 1 次。
5. 「撤销链接」→ Network 捕获 DELETE /api/v1/reports/493/share/{token}；
   弹窗清空链接；页内 fetch GET /api/v1/reports/shared/{token} → 404。
6. 浅色 / 深色截图。

失败落 tests/ui/artifacts/int1408_report_share/<步骤>/。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5322')
REPORT_ID = os.environ.get('REPORT_ID', '493')
GATEWAY = 'http://127.0.0.1:5700'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1408_report_share')
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
        if msg.get('method') == 'Network.requestWillBeSent':
            out.append(msg.get('params', {}))
    return out


def _find_req(reqs, sub, method=None):
    """从 requestWillBeSent 里找 URL 含 sub 的请求（方法可选）。"""
    hit = []
    for r in reqs:
        req = r.get('request', {})
        url = req.get('url', '')
        if sub in url and (method is None or req.get('method') == method):
            hit.append({'method': req.get('method'), 'url': url,
                        'postData': req.get('postData')})
    return hit


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
    """从 localStorage 取当前 JWT（iatp:auth:token:v1）。"""
    return drv.execute_script("return window.localStorage.getItem('iatp:auth:token:v1')")


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
        # 1) 防串库
        import urllib.request
        with urllib.request.urlopen(GATEWAY + '/health', timeout=5) as resp:
            health = json.loads(resp.read().decode())
        print('health.database =', health.get('database'))
        check('防串库 /health database=intelligent_audio_test',
              health.get('database') == 'intelligent_audio_test', health.get('database'))

        # 2) 登录
        _login(drv)
        check('登录成功（URL 离开 /login）', drv.current_url and '/login' not in drv.current_url,
              drv.current_url)
        token = _get_token(drv)
        print('token found:', bool(token), (token[:25] + '...') if token else '')
        check('localStorage 有 JWT', bool(token))

        # 3) 打开报告页
        _goto(drv, f'/report/{REPORT_ID}')
        time.sleep(3)
        body = _body_text(drv)
        check(f'报告页 /report/{REPORT_ID} 加载（含报告管理导航）',
              '报告' in body and f'report/{REPORT_ID}' in drv.current_url,
              drv.current_url)
        net0 = _drain_perf(drv)
        check('Network 含 GET /reports/493（报告详情真实请求）',
              len(_find_req(net0, f'/api/v1/reports/{REPORT_ID}')) > 0,
              str([n['url'] for n in _find_req(net0, f'/api/v1/reports/{REPORT_ID}')][:3]))

        # 4) 打开分享弹窗
        _drain_perf(drv)
        share_btns = drv.find_elements(By.XPATH, "//button[contains(., '分享')]")
        print('  share buttons:', [b.text for b in share_btns[:5]])
        share_btn = None
        for b in share_btns:
            if b.text.strip() == '分享' and b.is_displayed():
                share_btn = b
                break
        check('报告头「分享」按钮存在', share_btn is not None)
        share_btn.click()
        WebDriverWait(drv, 10).until(
            lambda d: '分享报告' in d.execute_script('return document.body.textContent || ""'))
        check('分享弹窗打开（标题「分享报告」）', '分享报告' in _body_text(drv))
        _save_evidence('01_share_dialog_light', drv)

        # 5) 生成分享链接（排除方式切换 tab 钮，取最后一个「生成分享链接」）
        _drain_perf(drv)
        gen_btns = drv.find_elements(By.XPATH, "//button[contains(., '生成分享链接')]")
        print('  generate buttons:', [b.text for b in gen_btns])
        assert gen_btns, '应存在「生成分享链接」按钮'
        gen_btn = gen_btns[-1]
        gen_btn.click()
        time.sleep(2.5)
        net_gen = _drain_perf(drv)
        create_req = _find_req(net_gen, f'/api/v1/reports/{REPORT_ID}/share', method='POST')
        print('  POST share captured:', json.dumps(create_req, ensure_ascii=False))
        check('Network 捕获 POST /reports/493/share',
              len(create_req) == 1, json.dumps(create_req, ensure_ascii=False))
        body_txt = _body_text(drv)
        check('弹窗显示分享统计区（生成后）', '分享统计' in body_txt)
        _save_evidence('02_share_generated_light', drv, net_gen)

        # 6) 取 shareUrl 并验证归一化
        inputs = drv.find_elements(By.TAG_NAME, 'input')
        share_url = ''
        for inp in inputs:
            val = inp.get_attribute('value') or ''
            if val.startswith('http'):
                share_url = val
                break
        print('  share_url =', share_url)
        check('弹窗显示真实 URL（以当前 origin 开头）',
              share_url.startswith(BASE) and f'report/{REPORT_ID}' in share_url,
              share_url)
        share_token = share_url.split('share=')[-1] if 'share=' in share_url else ''
        check('shareUrl 含 token 参数', bool(share_token), share_token)
        check('shareUrl origin 为前端 dev（非网关 5700）',
              '127.0.0.1:5700' not in share_url, share_url)

        # 7) 复制真实 URL 新标签打开
        drv.execute_script('window.open(arguments[0], "_blank");', share_url)
        WebDriverWait(drv, 10).until(lambda d: len(d.window_handles) >= 2)
        drv.switch_to.window(drv.window_handles[-1])
        WebDriverWait(drv, 25).until(
            lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        new_url = drv.current_url
        new_body = _body_text(drv)
        print('  new tab url:', new_url)
        check('复制 URL 新标签打开报告（report/493 路由）',
              f'/report/{REPORT_ID}' in new_url and '登录' not in new_url,
              new_url)
        check('新标签报告正文加载', '报告' in new_body and '分享' in new_body)
        _save_evidence('03_share_url_new_tab', drv)
        drv.close()
        drv.switch_to.window(drv.window_handles[0])
        time.sleep(1)

        # 8) 页内公开读取（带 Authorization）→ 200 且 visits +1；刷新统计回读
        fetch_public = drv.execute_async_script("""
          const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
          const r = await fetch('/api/v1/reports/shared/' + arguments[0], {
            headers: {'Authorization': 'Bearer ' + token}
          });
          const body = await r.text();
          arguments[arguments.length - 1](JSON.stringify({status: r.status, body: body}));
        """, share_token)
        print('  public read:', fetch_public)
        check('公开读取 GET /reports/shared/{token} → 200',
              '"status":200' in fetch_public, fetch_public[:160])
        time.sleep(1)
        _drain_perf(drv)
        refresh_btns = drv.find_elements(By.XPATH, "//button[contains(., '刷新统计')]")
        assert refresh_btns, '生成后应有「刷新统计」按钮'
        refresh_btns[-1].click()
        time.sleep(2)
        net_stats = _drain_perf(drv)
        stats_req = _find_req(net_stats, f'/api/v1/reports/{REPORT_ID}/share', method='GET')
        print('  GET list captured:', json.dumps(stats_req, ensure_ascii=False))
        check('「刷新统计」Network 捕获 GET /reports/493/share',
              len(stats_req) >= 1, json.dumps(stats_req, ensure_ascii=False))
        stats_body = _body_text(drv)
        check('弹窗显示 访问 1 次（公开读取计数 + 回读）', '访问 1 次' in stats_body,
              [ln for ln in stats_body.splitlines() if '访问' in ln][:3])
        _save_evidence('04_stats_refreshed_light', drv, net_stats)

        # 9) 撤销分享链接
        _drain_perf(drv)
        revoke_btns = drv.find_elements(By.XPATH, "//button[contains(., '撤销链接')]")
        assert revoke_btns, '生成后应有「撤销链接」按钮'
        revoke_btns[-1].click()
        time.sleep(2.5)
        net_revoke = _drain_perf(drv)
        revoke_req = _find_req(net_revoke, f'/api/v1/reports/{REPORT_ID}/share/{share_token}', method='DELETE')
        print('  DELETE captured:', json.dumps(revoke_req, ensure_ascii=False))
        check('Network 捕获 DELETE /reports/493/share/{token}',
              len(revoke_req) == 1, json.dumps(revoke_req, ensure_ascii=False))
        time.sleep(1)
        revoked_body = _body_text(drv)
        check('撤销后弹窗清空链接（回到「生成分享链接」按钮）', '生成分享链接' in revoked_body,
              [ln for ln in revoked_body.splitlines() if '分享统计' in ln][:3])
        check('撤销后分享统计区消失', '分享统计' not in revoked_body)
        _save_evidence('05_revoked_light', drv, net_revoke)

        # 10) 撤销后公开读取 → 404
        fetch_after = drv.execute_async_script("""
          const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
          const r = await fetch('/api/v1/reports/shared/' + arguments[0], {
            headers: {'Authorization': 'Bearer ' + token}
          });
          const body = await r.text();
          arguments[arguments.length - 1](JSON.stringify({status: r.status, body: body}));
        """, share_token)
        print('  public read after revoke:', fetch_after)
        check('撤销后公开读取 GET /reports/shared/{token} → 404',
              '"status":404' in fetch_after, fetch_after[:160])

        # 11) 深色截图（重新生成一次，弹窗深色）
        _set_theme(drv, 'dark')
        time.sleep(1.5)
        gen_btns2 = drv.find_elements(By.XPATH, "//button[contains(., '生成分享链接')]")
        if gen_btns2:
            gen_btns2[-1].click()
            time.sleep(2.5)
            # 捕获本次新 token（兜底清理用）
            for inp in drv.find_elements(By.TAG_NAME, 'input'):
                val = inp.get_attribute('value') or ''
                if val.startswith('http'):
                    share_token = val.split('share=')[-1]
                    break
        _save_evidence('06_share_dialog_dark', drv, _drain_perf(drv))
        # 撤销深色这次生成（清理残留）
        rb = drv.find_elements(By.XPATH, "//button[contains(., '撤销链接')]")
        if rb:
            _drain_perf(drv)
            rb[-1].click()
            time.sleep(2)

        print('share_token_used =', share_token)

    except Exception:
        _save_evidence('FAILURE_dump', drv, _drain_perf(drv))
        raise
    finally:
        # 兜底清理：若主流程或深色步未撤销当前 token，浏览器会话仍有效则页内撤销
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
        f.write('share_token: ' + str(share_token) + '\n')

    print('=' * 50)
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
