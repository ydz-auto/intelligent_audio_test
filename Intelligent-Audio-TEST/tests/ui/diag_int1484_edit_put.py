# -*- coding: utf-8 -*-
"""INT-1484 诊断：编辑维度抽屉保存 PUT 未发出（按钮 disabled / 校验 / 选择器）。"""
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int1484_eval_deep as V
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

STAMP = str(int(time.time()))[-6:]
DIM = '接线测试_INT1484_DIAG_' + STAMP
RES = []


def log(step, detail=None):
    RES.append({'step': step, 'detail': detail})
    print(step, '::', json.dumps(detail, ensure_ascii=False, default=str)[:1500], flush=True)


def main():
    st, body = V.api_call('POST', '/evaluation/dimensions', {
        'name': DIM, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
        'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
        'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [{'param_code': 'asr_result', 'param_name': 'ASR识别结果', 'default_value': 'A'},
                            {'param_code': 'asr_ref', 'param_name': '参考文本'}],
        'output_fields': [{'param_code': 'score', 'field_path': 'score'}],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '主端点',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60},
                          {'url': 'http://host.docker.internal:15000/health', 'name': '备端点',
                           'priority': 2, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    log('seed', {'status': st, 'id': dim_id})
    drv = V._driver()
    try:
        V.login(drv)
        V.goto_eval(drv)
        V.search_dim(drv, DIM)
        V.row_button(drv, '编辑维度 %s' % DIM)
        sh = V.sheet(drv)
        WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
        time.sleep(1.0)
        btn = V.one(drv, V.SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10)
        log('submit-before-edit', {'disabled': btn.get_attribute('disabled') is not None,
                                   'text': (btn.text or '').strip(),
                                   'class': btn.get_attribute('class')})
        # 与 deep 脚本相同的编辑动作
        V.tab_click(drv, '基本信息')
        V.clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM + '_改')
        V.clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 维度描述(已改)')
        V.tab_click(drv, 'API配置')
        V.clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), 'ASR识别结果(改)')
        V.clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']"), 'score_v2')
        V.clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 2']"), '备端点(改)')
        time.sleep(0.8)
        btn = V.one(drv, V.SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10)
        foot = ' '.join(sh.text.split())[:600]
        log('submit-after-edit', {'disabled': btn.get_attribute('disabled') is not None,
                                  'text': (btn.text or '').strip(),
                                  'sheet_text_tail': foot[-400:]})
        V.drain_net(drv)
        V.js_click(drv, btn)
        time.sleep(6)
        net = V.drain_net(drv)
        log('after-click-net', [{'m': n.get('method'), 'u': n.get('url'), 's': n.get('status')} for n in net])
        toasts = V.toast_texts(drv)
        still = bool(drv.find_elements(By.XPATH, V.SHEET))
        log('after-click-state', {'toasts': toasts, 'sheet_open': still})
        V.shot(drv, 'DIAG_edit_put')
        # 表单校验态：找出 aria-invalid / 红字
        inv = [e.get_attribute('aria-invalid') for e in sh.find_elements(By.XPATH, ".//input[@aria-invalid='true']")]
        log('aria-invalid-inputs', len(inv))
        for t in sh.find_elements(By.TAG_NAME, 'p'):
            if t.text.strip():
                log('p-text', t.text.strip()[:120])
        st2, body2 = V.api_call('GET', '/evaluation/dimensions/%s' % dim_id)
        log('api-readback', {'status': st2, 'name': ((body2 or {}).get('data') or {}).get('name')
                             if isinstance(body2, dict) else None})
    except Exception:
        log('EXC', traceback.format_exc()[-1500:])
    finally:
        try:
            st3, _ = V.api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)
            log('cleanup', st3)
        except Exception:
            log('cleanup-exc', traceback.format_exc()[-300:])
        with open(os.path.join(V.ART, 'diag_edit_put.json'), 'w', encoding='utf-8') as f:
            json.dump(RES, f, ensure_ascii=False, indent=1)
        drv.quit()


if __name__ == '__main__':
    main()
