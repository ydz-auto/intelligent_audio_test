# -*- coding: utf-8 -*-
"""INT-1484 复跑：INT-1549/1550/1551/1552 修复项实测（临时 React 构建 15318，wiring/react + 4 修复）。

只写「接线测试_INT1484_R_」前缀数据，结束前经 API 删除并复核无残留。
"""
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15318')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int1484_eval_deep as V  # noqa: E402
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

STAMP = str(int(time.time()))[-6:]
C1 = '接线测试_INT1484_R_分类1_' + STAMP
C1_NEW = '接线测试_INT1484_R_分类1改_' + STAMP
C2 = '接线测试_INT1484_R_分类2_' + STAMP
C3 = '接线测试_INT1484_R_内联分类_' + STAMP
DIM = '接线测试_INT1484_R_维度_' + STAMP

RESULT = []


def log(step, ok, detail=None):
    RESULT.append({'step': step, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + step + ' :: ' +
          json.dumps(detail, ensure_ascii=False, default=str)[:1200], flush=True)


def api(method, path, body=None):
    return V.api_call(method, path, body)


def cat_by_name(name):
    return [c for c in V.api_cats() if c.get('name') == name]


def create_cat(name, desc='INT-1484 修复复测分类'):
    st, body = api('POST', '/evaluation/categories',
                   {'name': name, 'description': desc, 'icon': 'fas fa-folder'})
    data = (body or {}).get('data') or {} if isinstance(body, dict) else {}
    return st, data.get('id')


def group_view(drv):
    V.tab_click(drv, '分组视图', scope='//*')
    time.sleep(1.2)


def list_view(drv):
    V.tab_click(drv, '列表视图', scope='//*')
    time.sleep(0.8)


def open_cat_edit(drv, name):
    V.row_button(drv, '编辑分类 %s' % name)
    return V.dialog(drv, '编辑分类')


def submit_cat(drv, dlg):
    V.js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))


def phase_int1549(drv):
    before = len(V.api_cats())
    group_view(drv)
    dlg = open_cat_edit(drv, C1)
    V.clear_and_type(drv, dlg.find_element(By.ID, 'category-name'), C2)
    submit_cat(drv, dlg)
    hits = V.wait_net(drv, '/evaluation/categories', 'PUT', timeout=30)
    time.sleep(1.5)
    toasts = V.toast_texts(drv)
    still_open = bool(drv.find_elements(
        By.XPATH, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'编辑分类')]]"))
    hit = hits[-1] if hits else {}
    log('INT-1549a 分类编辑改名冲突 → PUT 400 + 可见提示 + 弹窗不关闭',
        hit.get('method') == 'PUT' and int(hit.get('status') or 0) >= 400
        and bool(toasts) and still_open,
        {'method': hit.get('method'), 'status': hit.get('status'),
         'resp': (hit.get('resBody') or '')[:200], 'toasts': toasts, 'dialog_open': still_open})
    V.shot(drv, 'R01_int1549_dup_error_light')

    if still_open:
        dlg = V.dialog(drv, '编辑分类')
        V.clear_and_type(drv, dlg.find_element(By.ID, 'category-name'), C1_NEW)
        V.clear_and_type(drv, dlg.find_element(By.ID, 'category-description'), 'INT-1484 分类描述(改)')
        submit_cat(drv, dlg)
        hits = V.wait_net(drv, '/evaluation/categories', 'PUT', timeout=30)
        time.sleep(1.5)
    after = V.api_cats()
    mine = [c for c in after if c.get('name') == C1_NEW]
    hit = hits[-1] if hits else {}
    log('INT-1549b 分类编辑保留 id 走 PUT → 200 + GET 回读新名/描述（总数不增）',
        hit.get('method') == 'PUT' and 200 <= int(hit.get('status') or 0) < 300
        and len(mine) == 1 and mine[0].get('description') == 'INT-1484 分类描述(改)'
        and len(after) == before,
        {'method': hit.get('method'), 'status': hit.get('status'),
         'readback': [(c['name'], c['description']) for c in mine],
         'cats_before': before, 'cats_after': len(after)})
    V.shot(drv, 'R02_int1549_edit_put_light')
    return mine[0]['id'] if mine else None


def phase_int1550(drv):
    group_view(drv)
    btns = drv.find_elements(By.XPATH, "//button[@aria-label='删除分类 %s']" % C2)
    disabled = btns[0].get_attribute('disabled') is not None if btns else None
    log('INT-1550a 0 维度分类仍渲染分组 + 删除按钮可达可点',
        bool(btns) and disabled is False,
        {'present': bool(btns), 'disabled': disabled})
    V.shot(drv, 'R03_int1550_empty_group_delete_light')
    if not btns:
        return
    V.js_click(drv, btns[0])
    dlg = V.alert_dialog(drv, '删除分类')
    txt = ' '.join(dlg.text.split())[:200]
    confirm = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']")
    V.js_click(drv, confirm)
    hits = V.wait_net(drv, '/evaluation/categories/', 'DELETE', timeout=30)
    time.sleep(1.5)
    remain = cat_by_name(C2)
    hit = hits[-1] if hits else {}
    log('INT-1550b 删除确认 → DELETE 200 + GET 回读分类已消失',
        bool(hit) and 200 <= int(hit.get('status') or 0) < 300 and not remain,
        {'confirm_text': txt, 'status': hit.get('status'), 'remain': len(remain)})
    V.shot(drv, 'R04_int1550_category_deleted_light')


def create_dim_with_inline_category(drv):
    sh, title, tabs = V.open_create_drawer(drv)
    V.clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM)
    V.select_open(drv, '所属分类')
    opt = V.one(drv, "//*[@data-slot='select-item'][normalize-space(.)='+ 新建分类']", timeout=10)
    V.js_click(drv, opt)
    time.sleep(0.5)
    inp = V.one(drv, "//input[@aria-label='新分类名称']", timeout=10)
    V.clear_and_type(drv, inp, C3)
    create_btn = V.one(drv, "//button[normalize-space(.)='创建']", timeout=10)
    V.js_click(drv, create_btn)
    hits = V.wait_net(drv, '/evaluation/categories', 'POST', timeout=30)
    time.sleep(1.5)
    hit = hits[-1] if hits else {}
    created = cat_by_name(C3)
    trig_text = V.trigger_by_label(drv, '所属分类').text.strip()
    log('INT-1552a 抽屉内联新建分类 → 真实 POST 201 + 回填真实分类',
        bool(hit) and 200 <= int(hit.get('status') or 0) < 300 and len(created) == 1
        and trig_text == C3,
        {'status': hit.get('status'), 'reqBody': hit.get('reqBody'),
         'readback': [c.get('name') for c in created], 'select_trigger': trig_text})
    V.shot(drv, 'R05_int1552_inline_category_light')
    new_cat_id = created[0]['id'] if created else None

    # 输入/输出参数改真实值，供编辑反填核验
    V.tab_click(drv, 'API配置')
    in1 = V.one(drv, V.SHEET + "//input[@aria-label='输入参数键名 1']", timeout=10)
    V.clear_and_type(drv, in1, 'q_text')
    out1 = V.one(drv, V.SHEET + "//input[@aria-label='输出字段代码 1']", timeout=10)
    V.clear_and_type(drv, out1, 'q_score')
    tab_click_basic = V.SHEET + "//button[@role='tab'][normalize-space(.)='基本信息']"
    V.js_click(drv, V.one(drv, tab_click_basic, timeout=10))
    time.sleep(0.5)
    hit = V.save_drawer(drv, 'POST')
    dims = [d for d in V.api_dims() if d.get('name') == DIM]
    info = V.verify_dim_readback(DIM) if dims else None
    log('INT-1552b 维度保存带内联新分类 id + 输入/输出参数落库回读',
        bool(hit) and 200 <= int(hit.get('status') or 0) < 300 and info
        and new_cat_id is not None and info.get('category_id') == new_cat_id
        and [i[0] for i in info.get('inputs') or []] == ['q_text', 'asr_ref']
        and [o[0] for o in info.get('outputs') or []] == ['q_score'],
        info)
    V.shot(drv, 'R06_int1552_dim_saved_light')
    return info


def phase_prefill(drv):
    V.search_dim(drv, DIM)
    V.row_button(drv, '编辑维度 %s' % DIM)
    sh = V.sheet(drv)
    WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
    time.sleep(1.0)
    cat_text = V.trigger_by_label(drv, '所属分类').text.strip()
    V.tab_click(drv, 'API配置')
    in_codes = [e.get_attribute('value') for e in
                sh.find_elements(By.XPATH, ".//input[starts-with(@aria-label,'输入参数键名')]")]
    out_codes = [e.get_attribute('value') for e in
                 sh.find_elements(By.XPATH, ".//input[starts-with(@aria-label,'输出字段代码')]")]
    log('INT-1553-retest 编辑反填输入/输出参数为已保存值（非表单默认行）',
        in_codes == ['q_text', 'asr_ref'] and out_codes == ['q_score'] and cat_text == C3,
        {'inputs': in_codes, 'outputs': out_codes, 'category': cat_text})
    V.shot(drv, 'R07_dim_edit_prefill_light')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)


def cleanup(cat_ids):
    dims = [d for d in V.api_dims() if str(d.get('name', '')).startswith('接线测试_INT1484_R_')]
    deleted = []
    for d in dims:
        st, _ = api('DELETE', '/evaluation/dimensions/%s' % d['id'])
        deleted.append({'id': d['id'], 'name': d['name'], 'status': st})
    for cid in cat_ids:
        if cid:
            api('DELETE', '/evaluation/categories/%s' % cid)
    time.sleep(1.2)
    remain_d = [d['name'] for d in V.api_dims() if str(d.get('name', '')).startswith('接线测试_INT1484_R_')]
    remain_c = [c['name'] for c in V.api_cats() if str(c.get('name', '')).startswith('接线测试_INT1484_R_')]
    log('清理：删除本 run 自建维度/分类并复核无残留',
        not remain_d and not remain_c,
        {'deleted': deleted, 'remain_dims': remain_d, 'remain_cats': remain_c})


def main():
    t0 = time.time()
    st1, id1 = create_cat(C1)
    st2, id2 = create_cat(C2)
    print('seeded categories', st1, id1, st2, id2, flush=True)
    drv = V._driver()
    cat_ids = [id1, id2]
    try:
        V.login(drv)
        V.goto_eval(drv)
        log('环境-0 /Evaluation 首屏加载', True, V.page_metrics(drv))
        new_id = phase_int1549(drv)
        cat_ids.append(new_id)
        phase_int1550(drv)
        info = create_dim_with_inline_category(drv)
        if info:
            cat_ids.append(info.get('category_id'))
        phase_prefill(drv)
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-2000:])
    finally:
        try:
            cleanup(cat_ids)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-800:])
        with open(os.path.join(V.ART, 'result_fixes_retest.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1), 'result': RESULT},
                      f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
