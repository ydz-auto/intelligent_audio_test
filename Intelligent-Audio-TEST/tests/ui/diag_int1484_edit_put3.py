# -*- coding: utf-8 -*-
"""INT-1484 诊断 3：编辑抽屉保存——submit 事件是否触发、表单 id 是否重复、toast 时序、浏览器报错。"""
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int1484_eval_deep as V
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

STAMP = str(int(time.time()))[-6:]
DIM = '接线测试_INT1484_DIAG3_' + STAMP
RES = []


def log(step, detail=None):
    RES.append({'step': step, 'detail': detail})
    print(step, '::', json.dumps(detail, ensure_ascii=False, default=str)[:1800], flush=True)


PROBE = r"""
window.__submits = [];
document.addEventListener('submit', function(e){
  window.__submits.push({id: (e.target && e.target.id) || '', tag: e.target && e.target.tagName,
                         trusted: e.isTrusted});
}, true);
window.__errors = [];
window.addEventListener('error', function(e){ window.__errors.push(String(e.message)); });
window.addEventListener('unhandledrejection', function(e){ window.__errors.push('rej:' + String(e.reason)); });
"""


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
        drv.execute_script(PROBE)
        V.search_dim(drv, DIM)
        V.row_button(drv, '编辑维度 %s' % DIM)
        WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
        time.sleep(1.0)
        info = drv.execute_script(r"""
          var fs=[...document.querySelectorAll('form#dimension-mutate-form')];
          return fs.map(function(f){
            var sh=f.closest("[data-slot='sheet-content']");
            var r=f.getBoundingClientRect();
            return {inSheet: !!sh, w: r.width, h: r.height,
                    name: f.querySelector('#dim-name') ? f.querySelector('#dim-name').value : null};
          });
        """)
        log('forms', info)
        log('sheets', drv.execute_script(
            "return document.querySelectorAll(\"[data-slot='sheet-content']\").length"))
        # 侧边栏里可见的那个保存按钮
        btn = V.one(drv, V.SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10)
        V.drain_net(drv)
        drv.execute_script("arguments[0].click();", btn)
        seen = []
        end = time.time() + 10
        while time.time() < end:
            tst = V.toast_texts(drv)
            if tst and tst not in seen:
                seen.append(tst)
            time.sleep(0.25)
        log('submits', drv.execute_script("return window.__submits || []"))
        log('errors', drv.execute_script("return window.__errors || []"))
        log('toasts-seen', seen)
        log('net', [{'m': n.get('method'), 'u': n.get('url'), 's': n.get('status'), 'e': n.get('error')}
                    for n in V.drain_net(drv)])
        log('sheet-open', bool(drv.find_elements(By.XPATH, V.SHEET)))
        st2, body2 = V.api_call('GET', '/evaluation/dimensions/%s' % dim_id)
        log('readback-name', ((body2 or {}).get('data') or {}).get('name') if isinstance(body2, dict) else None)
        V.shot(drv, 'DIAG3_edit_save')
    except Exception:
        log('EXC', traceback.format_exc()[-1200:])
    finally:
        try:
            log('cleanup', V.api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)[0])
        except Exception:
            pass
        with open(os.path.join(V.ART, 'diag_edit_put3.json'), 'w', encoding='utf-8') as f:
            json.dump(RES, f, ensure_ascii=False, indent=1)
        drv.quit()


if __name__ == '__main__':
    main()
