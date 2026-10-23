# -*- coding: utf-8 -*-
"""INT-1484 诊断 2：编辑抽屉里同名 submit 按钮是否多个/不可见；点击后事件是否到达表单。"""
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
DIM = '接线测试_INT1484_DIAG2_' + STAMP
RES = []


def log(step, detail=None):
    RES.append({'step': step, 'detail': detail})
    print(step, '::', json.dumps(detail, ensure_ascii=False, default=str)[:1800], flush=True)


def btns(drv):
    out = []
    for b in drv.find_elements(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']"):
        try:
            r = drv.execute_script(
                "var r=arguments[0].getBoundingClientRect();var s=getComputedStyle(arguments[0]);"
                "return {w:r.width,h:r.height,vis:s.visibility,disp:s.display,op:s.opacity,"
                "sheet:!!arguments[0].closest('[data-slot=\\'sheet-content\\']')};", b)
        except Exception as e:
            r = {'err': str(e)}
        r['text'] = (b.text or '').strip()
        out.append(r)
    return out


def main():
    st, body = V.api_call('POST', '/evaluation/dimensions', {
        'name': DIM, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
        'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
        'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [{'param_code': 'asr_result', 'param_name': 'ASR识别结果', 'default_value': 'A'}],
        'output_fields': [{'param_code': 'score', 'field_path': 'score'}],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '主端点',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
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
        WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
        time.sleep(1.0)
        log('buttons-in-edit', btns(drv))
        log('form-exists', drv.execute_script(
            "return !!document.getElementById('dimension-mutate-form')"))
        # 直接在表单上派发 submit
        V.drain_net(drv)
        drv.execute_script("var f=document.getElementById('dimension-mutate-form');"
                           "if(f){f.requestSubmit?f.requestSubmit():f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}")
        time.sleep(6)
        net = V.drain_net(drv)
        log('after-requestSubmit-net', [{'m': n.get('method'), 'u': n.get('url'), 's': n.get('status')} for n in net])
        log('toasts', V.toast_texts(drv))
        log('sheet-open', bool(drv.find_elements(By.XPATH, V.SHEET)))
        st2, body2 = V.api_call('GET', '/evaluation/dimensions/%s' % dim_id)
        log('readback-name', ((body2 or {}).get('data') or {}).get('name') if isinstance(body2, dict) else None)
    except Exception:
        log('EXC', traceback.format_exc()[-1200:])
    finally:
        try:
            log('cleanup', V.api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)[0])
        except Exception:
            pass
        with open(os.path.join(V.ART, 'diag_edit_put2.json'), 'w', encoding='utf-8') as f:
            json.dump(RES, f, ensure_ascii=False, indent=1)
        drv.quit()


if __name__ == '__main__':
    main()
