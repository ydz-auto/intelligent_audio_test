# -*- coding: utf-8 -*-
"""INT-2252 回归：行内启停（本卡改了提交载荷）不得清掉真实「关联算法」。

夹具 = 接线测试_2252_有关联维度（带 voice_llm 关联），启停前后比对
GET /evaluation/dimensions/{id} 的 associated_algorithms。
"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import _int2252_ui as U  # noqa: E402

NAME = '接线测试_2252_有关联维度'


def detail_assoc(drv, name):
    """列表拿 id → 详情拿真实 associated_algorithms（列表端点按契约恒 []）。"""
    st, d, _ = L.api_json(drv, '/evaluation/dimensions?per_page=1000')
    dd = (d or {}).get('data', d) if isinstance(d, dict) else d
    fid = None
    for it in (dd or {}).get('items') or []:
        if it.get('name') == name:
            fid = it.get('id')
            break
    if fid is None:
        return None, None, None
    st2, det, _ = L.api_json(drv, '/evaluation/dimensions/%s' % fid)
    det = (det or {}).get('data', det) if isinstance(det, dict) else det
    if not isinstance(det, dict) or not det.get('name'):
        # 详情可能被包一层
        det = ((det or {}).get('dimension') if isinstance(det, dict) else None) or {}
    return fid, det.get('associated_algorithms'), det.get('status')


def main():
    base = sys.argv[1]
    tag = sys.argv[2]
    drv = L.driver()
    res = {'base': base, 'tag': tag}
    try:
        U.login(drv, base)
        drv.get(base + '/Evaluation')
        WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        U.wait_index(drv)
        time.sleep(1.5)

        fid, assoc_before, status_before = detail_assoc(drv, NAME)
        res['fixture_id'] = fid
        res['assoc_before'] = assoc_before
        res['status_before'] = status_before

        U.set_search(drv, NAME) if hasattr(U, 'set_search') else None
        drv.execute_script("""
          const el = document.querySelector("input[aria-label='搜索评估维度']");
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          setter.call(el, ''); el.dispatchEvent(new Event('input',{bubbles:true}));
          setter.call(el, arguments[0]); el.dispatchEvent(new Event('input',{bubbles:true}));
        """, NAME)
        time.sleep(1.5)
        res['before_state'] = U.page_state(drv)
        res['shot_before'] = U.shot(drv, tag, 'toggle_before')

        # 点启停（按当前状态取 禁用维度/启用维度）
        clicked = None
        for lab in ('禁用维度', '启用维度'):
            for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='%s %s']" % (lab, NAME)):
                if b.is_displayed():
                    L.js_click(drv, b)
                    clicked = lab
                    break
            if clicked:
                break
        res['clicked'] = clicked
        toasts = L.wait_toast(drv, 20)
        res['toasts'] = toasts
        time.sleep(2.0)

        fid2, assoc_after, status_after = detail_assoc(drv, NAME)
        res['assoc_after'] = assoc_after
        res['status_after'] = status_after

        # 重载再查一次列（确保不是本地缓存造成）
        time.sleep(0.5)
        res['shot_after'] = U.shot(drv, tag, 'toggle_after')

        try:
            sev = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
            res['console_severe'] = sev[:5]
        except Exception as e:  # noqa: BLE001
            res['console_severe'] = 'n/a: %s' % e
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    print('JSON_RESULT ' + json.dumps(res, ensure_ascii=True))


if __name__ == '__main__':
    main()
