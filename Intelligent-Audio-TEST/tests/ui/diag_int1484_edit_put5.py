# -*- coding: utf-8 -*-
"""INT-1484 诊断 5：用 CDP performance log 确认编辑保存是否真有 PUT 离站（fetch 打点看不到挂起请求）。"""
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int1484_eval_deep as V
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

STAMP = str(int(time.time()))[-6:]
DIM = '接线测试_INT1484_DIAG5_' + STAMP
RES = []


def log(step, detail=None):
    RES.append({'step': step, 'detail': detail})
    print(step, '::', json.dumps(detail, ensure_ascii=False, default=str)[:1800], flush=True)


def perf_net(drv):
    out = []
    try:
        for e in drv.get_log('performance'):
            m = json.loads(e['message'])['message']
            if m.get('method') in ('Network.requestWillBeSent', 'Network.responseReceived',
                                   'Network.loadingFailed'):
                p = m['params']
                if m['method'] == 'Network.requestWillBeSent':
                    r = p.get('request') or {}
                    out.append({'t': 'req', 'm': r.get('method'), 'u': (r.get('url') or '')[-90:],
                                'body': (r.get('postData') or '')[:80]})
                elif m['method'] == 'Network.responseReceived':
                    out.append({'t': 'res', 's': p.get('response', {}).get('status'),
                                'u': (p.get('response', {}).get('url') or '')[-90:]})
                else:
                    out.append({'t': 'fail', 'err': p.get('errorText'),
                                'u': (p.get('requestId') or '')})
    except Exception as e:
        log('perf-exc', str(e)[:200])
    return out


def main():
    st, body = V.api_call('POST', '/evaluation/dimensions', {
        'name': DIM, 'description': '诊断5', 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0,
        'result_max': 100, 'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [{'param_code': 'asr_result', 'param_name': 'ASR识别结果'}],
        'output_fields': [{'param_code': 'score', 'field_path': 'score'}],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '主端点',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    log('seed', {'status': st, 'id': dim_id})

    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    # 复用 V._driver 的驱动选择逻辑
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    drv = webdriver.Chrome(options=o, service=Service(executable_path=drv_path) if drv_path else Service())
    try:
        V.login(drv)
        V.goto_eval(drv)
        V.search_dim(drv, DIM)
        V.row_button(drv, '编辑维度 %s' % DIM)
        WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
        time.sleep(1.2)
        perf_net(drv)  # 清空已读
        V.tab_click(drv, '基本信息')
        sh = V.sheet(drv)
        V.clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM + '_改')
        btn = V.one(drv, V.SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10)
        drv.execute_script("arguments[0].click();", btn)
        samples = []
        for i in range(12):
            time.sleep(10)
            st2, body2 = V.api_call('GET', '/evaluation/dimensions/%s' % dim_id)
            nm = ((body2 or {}).get('data') or {}).get('name') if isinstance(body2, dict) else None
            samples.append({'t': (i + 1) * 10, 'name': nm, 'btn': (btn.text or '').strip()})
            if nm and nm.endswith('_改'):
                break
        log('poll-readback', samples)
        net = perf_net(drv)
        rel = [n for n in net if 'evaluation' in (n.get('u') or '')]
        log('perf-net-after-click', rel[-12:])
        log('btn-text', (btn.text or '').strip())
        st2, body2 = V.api_call('GET', '/evaluation/dimensions/%s' % dim_id)
        log('readback-name', ((body2 or {}).get('data') or {}).get('name') if isinstance(body2, dict) else None)
    except Exception:
        log('EXC', traceback.format_exc()[-1200:])
    finally:
        try:
            log('cleanup', V.api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)[0])
        except Exception:
            pass
        with open(os.path.join(V.ART, 'diag_edit_put5.json'), 'w', encoding='utf-8') as f:
            json.dump(RES, f, ensure_ascii=False, indent=1)
        drv.quit()


if __name__ == '__main__':
    main()
