# -*- coding: utf-8 -*-
"""INT-1484 诊断 4：编辑保存静默 no-op —— 找 RHF 校验错在哪个字段/页签。"""
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int1484_eval_deep as V
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

STAMP = str(int(time.time()))[-6:]
DIM = '接线测试_INT1484_DIAG4_' + STAMP
RES = []


def log(step, detail=None):
    RES.append({'step': step, 'detail': detail})
    print(step, '::', json.dumps(detail, ensure_ascii=False, default=str)[:2500], flush=True)


def dump_errors(drv, tag):
    d = drv.execute_script(r"""
      var out=[];
      document.querySelectorAll("[class*='text-destructive'],[aria-invalid='true'],[role='alert']").forEach(function(e){
        var t=(e.innerText||'').trim();
        out.push({cls:(e.className||'').toString().slice(0,60), tag:e.tagName,
                  aria:e.getAttribute('aria-invalid'), text:t.slice(0,120)});
      });
      return out;
    """)
    log('errors@' + tag, d)


def main():
    st, body = V.api_call('POST', '/evaluation/dimensions', {
        'name': DIM, 'description': 'INT-1484 诊断维度', 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0,
        'result_max': 100, 'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 95, 'score': 10},
                           {'condition': '>=', 'value': 90, 'score': 9},
                           {'condition': '>=', 'value': 80, 'score': 8},
                           {'condition': '>=', 'value': 70, 'score': 7},
                           {'condition': '<', 'value': 70, 'score': 0}]},
        'required_inputs': [{'param_code': 'asr_result', 'param_name': 'ASR识别结果', 'default_value': 'A'},
                            {'param_code': 'asr_ref', 'param_name': '参考文本'}],
        'output_fields': [{'param_code': 'score', 'field_path': 'score', 'display_name': '评分'}],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '主端点',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60},
                          {'url': 'http://host.docker.internal:15000/health', 'name': '备端点',
                           'priority': 2, 'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    log('seed', {'status': st, 'id': dim_id,
                 'resp': 'ok' if dim_id else json.dumps(body, ensure_ascii=False)[:300]})
    drv = V._driver()
    try:
        V.login(drv)
        V.goto_eval(drv)
        V.search_dim(drv, DIM)
        V.row_button(drv, '编辑维度 %s' % DIM)
        WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
        time.sleep(1.2)
        dump_errors(drv, 'open')
        btn = V.one(drv, V.SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10)
        drv.execute_script("arguments[0].click();", btn)
        time.sleep(3)
        dump_errors(drv, 'after-click')
        log('net-after-click', [{'m': n.get('method'), 'u': n.get('url'), 's': n.get('status')}
                                for n in V.drain_net(drv)])
        for tab in ['层级配置', '结果配置', 'API配置', '关联算法']:
            try:
                V.tab_click(drv, tab)
                time.sleep(0.8)
                dump_errors(drv, 'tab-' + tab)
            except Exception as e:
                log('tab-exc-' + tab, str(e)[:200])
        V.tab_click(drv, '基本信息')
        time.sleep(0.8)
        log('sheet-tail', ' '.join(drv.find_element(By.XPATH, V.SHEET).text.split())[-500:])
    except Exception:
        log('EXC', traceback.format_exc()[-1200:])
    finally:
        try:
            log('cleanup', V.api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)[0])
        except Exception:
            pass
        with open(os.path.join(V.ART, 'diag_edit_put4.json'), 'w', encoding='utf-8') as f:
            json.dump(RES, f, ensure_ascii=False, indent=1)
        drv.quit()


if __name__ == '__main__':
    main()
