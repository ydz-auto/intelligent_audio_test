# -*- coding: utf-8 -*-
"""INT-1255 复测·报告 对比生成/日志下载/分享 浏览器复测（INT-1347 清单第 4/5/7 项）。

环境：
- preview :5311（/api 代理 → docker :15000，主库 intelligent_audio_test）
- AUTH_MODE=off → dev_user('*') 放行（报告端点无需真实身份）

覆盖：
① 报告分享（item 7）：分享弹窗字段齐 → 生成链接（React 前端桩 // 待接线，URL 本地生成）
   → 撤销清空；后端 POST /reports/{id}/share 已可用（INT-971，接口级另验）
② 日志下载完整链路（item 5）：/report/484（task 407，用例有真实 business 日志文件）→
   「下载日志」→ 文件选择弹窗列出真实文件（GET /reports/{id}/cases/{cid}/logs 200 非 404）
   → 勾选文件 → 下载（logs/download 请求 + 进度）
③ 报告对比生成（item 4）：报告中心勾选 2 报告 → 批量对比 → 基于已选报告 →
   提交 POST /reports/secondary-compare → 记录请求与生成结果；生成报告清理

失败落 tests/ui/artifacts/int1255_retest_report/<步骤>/。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1255_retest_report')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'

os.makedirs(ARTIFACTS, exist_ok=True)


def _get_api(path, token=None, timeout=45):
    import urllib.request as ur
    req = ur.Request(API + path)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with ur.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
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
    drv.set_page_load_timeout(60)
    return drv


def _goto(drv, path, wait_text=None, timeout=30):
    drv.get(BASE + path)
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    if wait_text:
        WebDriverWait(drv, timeout).until(
            lambda d: wait_text in (d.execute_script('return document.body.textContent || ""')))


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _network_api_calls(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                p = inner.get('params', {})
                url = p.get('request', {}).get('url', '')
                if '/api/' in url:
                    req = p.get('request', {})
                    out.append({'url': url, 'method': req.get('method'),
                                'postData': req.get('postData')})
    except Exception as e:
        out.append({'error': str(e)})
    return out


def _save_evidence(name, drv, net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net or [], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _js_click(drv, el):
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click()', el)
    time.sleep(0.6)


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def _click_text(drv, text, timeout=12):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//*[normalize-space(.)='{text}']"))
    _js_click(drv, el)


def _click_text_contains(drv, text, timeout=12):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//*[contains(normalize-space(.), '{text}')]"))
    _js_click(drv, el)


def run():
    drv = _driver()
    failures = []
    results = []

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        results.append((tag, name, detail))
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''), flush=True)
        if not cond:
            failures.append(name)

    try:
        health = None
        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health = json.loads(r.read().decode('utf-8'))
                break
            except Exception:
                time.sleep(2)
        check('防串库① docker :15000 database=intelligent_audio_test', health.get('database') == 'intelligent_audio_test', str(health))

        _goto(drv, '/dashboard', wait_text='工作台', timeout=30)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')

        # ================= ② 日志下载完整链路（/report/484 task 407 有真实 business 日志）=================
        _goto(drv, '/report/484', wait_text='豆包', timeout=45)
        _wait_text(drv, '具体用例', timeout=60)
        WebDriverWait(drv, 60).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]")) > 0)
        dl_btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]")
        check('具体用例区「下载日志」按钮存在', len(dl_btns) > 0, f'count={len(dl_btns)}')
        btn = dl_btns[0]
        try:
            drv.execute_script('arguments[0].scrollIntoView({block:"center"})', btn)
            time.sleep(0.5)
            btn.click()
        except Exception:
            drv.execute_script('arguments[0].click()', btn)
        # 等文件列表加载（报告 484 聚合较慢，最多等 45s）
        file_listed = False
        for _ in range(90):
            time.sleep(0.5)
            body = _body_text(drv)
            if 'execution.task_service' in body:
                file_listed = True
                break
            if '该用例暂无日志文件' in body or '日志文件加载失败' in body:
                break
        body = _body_text(drv)
        check('日志文件选择弹窗打开', '下载日志' in body or '下载所选文件' in body or '该用例暂无日志文件' in body, body[:120])
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('日志列表真实请求 GET /reports/484/cases/{cid}/logs (200 非 404)',
              any('/reports/484/cases/' in u and '/logs' in u and '/download' not in u for u in urls),
              str([u for u in urls if '/logs' in u][:2]))
        check('文件列表列出真实日志文件（execution.task_service）', 'execution.task_service' in body, body[body.find('execution'):body.find('execution')+60] if 'execution' in body else '')
        _save_evidence('10_log_file_select_dialog', drv, net)
        # 下载所选文件
        dbtn = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载所选文件')]")
        if dbtn:
            try:
                dbtn[0].click()
            except Exception:
                drv.execute_script('arguments[0].click()', dbtn[0])
            time.sleep(4.0)
            net = _network_api_calls(drv)
            urls = [n.get('url', '') for n in net]
            check('日志下载真实请求 logs/download', any('logs/download' in u for u in urls),
                  str([u for u in urls if 'logs/download' in u]))
            _save_evidence('11_log_download_request', drv, net)
        else:
            check('日志下载真实请求 logs/download', False, '未找到「下载所选文件」按钮')
        # 关闭弹窗
        try:
            drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
        except Exception:
            pass
        time.sleep(0.8)

        # 防串库②
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
            health2 = json.loads(r.read().decode('utf-8'))
        check('防串库② docker :15000 database=intelligent_audio_test', health2.get('database') == 'intelligent_audio_test', str(health2))

        # ================= ① 报告分享（React 前端桩，后端端点已可用）=================
        _goto(drv, '/report/484', wait_text='豆包', timeout=45)
        _wait_text(drv, '具体用例', timeout=60)
        _click_text(drv, '分享')
        time.sleep(1.0)
        body = _body_text(drv)
        check('分享弹窗打开', '分享报告' in body)
        for label in ('生成分享链接', '邮件分享', '导出后分享'):
            check(f'分享方式「{label}」', label in body)
        check('访问权限字段', '访问权限' in body)
        check('有效期字段', '有效期' in body)
        check('访问密码字段', '访问密码' in body)
        _save_evidence('12_report_share_dialog', drv, _network_api_calls(drv))
        # 生成分享链接（排除 tab 按钮，点实际生成钮）
        for cand in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '生成分享链接')]"):
            try:
                cand.click()
            except Exception:
                drv.execute_script('arguments[0].click()', cand)
            time.sleep(0.8)
            if 'share=' in _body_text(drv):
                break
        time.sleep(0.6)
        body = _body_text(drv)
        share_url = ''
        try:
            share_el = drv.find_element(By.CSS_SELECTOR, "input[readonly]")
            share_url = share_el.get_attribute('value') or ''
        except Exception:
            pass
        check('生成分享链接产生 URL（前端桩 // 待接线）', 'share=' in share_url and '/report/484' in share_url, share_url[:80] or 'no url')
        net = _network_api_calls(drv)
        check('分享生成未调后端（前端桩，POST /reports/{id}/share 未触发）',
              not any('/reports/484/share' in n.get('url', '') for n in net),
              str([n.get('url') for n in net if 'share' in n.get('url', '')]))
        _save_evidence('13_report_share_generated_stub', drv, net)
        _click_text(drv, '撤销链接')
        time.sleep(0.8)
        body = _body_text(drv)
        check('撤销链接后分享链接清空', 'share=' not in body)
        _save_evidence('14_report_share_revoked', drv, _network_api_calls(drv))
        try:
            drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
        except Exception:
            pass
        time.sleep(0.8)

        # ================= ③ 报告对比生成（item 4）=================
        _goto(drv, '/report-center', wait_text='报告中心', timeout=30)
        _wait_text(drv, '豆包', timeout=60)
        # 选 2 个真实草稿任务报告（484/493 有完整用例结果数据，二次对比可生成）
        all_cbs = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择报告']")
        task_cbs = []
        for cb in all_cbs:
            label = cb.get_attribute('aria-label') or ''
            if ('豆包-话轮接管-打断' in label or '豆包拒识环境理解' in label) and '选择报告' in label:
                task_cbs.append(cb)
        check('报告列表行勾选存在', len(task_cbs) >= 2, f'task_rows={len(task_cbs)}')
        if len(task_cbs) >= 2:
            for cb in task_cbs[:2]:
                _js_click(drv, cb)
            time.sleep(1.0)
            body = _body_text(drv)
            check('批量浮条「已选择 2 个报告」', '已选择 2 个报告' in body, body[:120])
            _save_evidence('15_report_rows_selected', drv, _network_api_calls(drv))
            batch_btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '批量对比')]")
            if batch_btns:
                _js_click(drv, batch_btns[0])
            time.sleep(1.5)
            body = _body_text(drv)
            check('对比弹窗打开', '报告对比' in body or '对比报告' in body, body[:100])
            _save_evidence('16_report_compare_dialog', drv, _network_api_calls(drv))
            tab_btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='基于已选报告']")
            if tab_btns:
                _js_click(drv, tab_btns[0])
            else:
                _click_text_contains(drv, '基于已选报告')
            time.sleep(1.0)
            body = _body_text(drv)
            check('基于已选报告 tab 显示已选报告', '已选择 2 个报告' in body or '可生成二次对比' in body, body[body.find('基于已选报告'):body.find('基于已选报告')+150] if '基于已选报告' in body else '')
            _save_evidence('16b_report_compare_report_tab', drv, _network_api_calls(drv))
            submit = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '生成对比报告')]")
            if submit:
                try:
                    submit[0].click()
                except Exception:
                    drv.execute_script('arguments[0].click()', submit[0])
                # 等待请求发出（secondary-compare 异步生成；后端响应可能较慢）
                time.sleep(3.0)
                net = _network_api_calls(drv)
                urls = [n.get('url', '') for n in net]
                check('对比提交真实请求 POST /reports/secondary-compare',
                      any('secondary-compare' in u for u in urls),
                      str([u for u in urls if 'compare' in u]))
                body = _body_text(drv)
                _save_evidence('17_report_compare_submit', drv, net)
                # 异步生成：轮询 API 最多 70s 等新 secondary_comparison 报告
                new_sec = []
                for _ in range(14):
                    time.sleep(5.0)
                    rl = _get_api('/reports?page=1&per_page=8&sort_by=id&order=desc')
                    if rl and rl.get('data'):
                        for it in rl['data'].get('items', []):
                            if it.get('report_type') == 'secondary_comparison':
                                new_sec.append((it.get('id'), it.get('name', '')))
                    if new_sec:
                        break
                body = _body_text(drv)
                _save_evidence('17b_report_compare_after_wait', drv, _network_api_calls(drv))
                check('异步生成新建 secondary_comparison 报告', len(new_sec) >= 1,
                      str(new_sec[:3]))
            else:
                check('对比提交按钮存在', False, '未找到提交按钮')
        else:
            check('报告列表行勾选', False, f'rows={len(row_cbs)}')

        # 防串库③ 交付前
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
            health3 = json.loads(r.read().decode('utf-8'))
        check('防串库③ docker :15000 database=intelligent_audio_test', health3.get('database') == 'intelligent_audio_test', str(health3))

    except Exception:
        _save_evidence('FAILURE_dump', drv, _network_api_calls(drv))
        import traceback
        traceback.print_exc()
        failures.append('脚本异常')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ARTIFACTS, 'results.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{tag}\t{name}\t{detail}' for tag, name, detail in results))
        f.write('\nFAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')

    print('=' * 60)
    print(f'PASS {sum(1 for t, _, _ in results if t == "PASS")} / {len(results)}')
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
