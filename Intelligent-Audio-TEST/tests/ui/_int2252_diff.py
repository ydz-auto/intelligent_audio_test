# -*- coding: utf-8 -*-
"""INT-2252 差分：证明「算法筛选真的过滤」而不是恒显示全部。

夹具 = 无算法关联的维度 接线测试_2252_无关联维度（_int2252_fixture.py 建/删）。
步骤：搜夹具名（全部算法）→ 选中算法 → 切回全部算法，比较 共 N 条 / 行 / 空态。
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

KEY = '接线测试_2252_无关联维度'


def set_search(drv, value):
    drv.execute_script("""
      const el = document.querySelector("input[aria-label='搜索评估维度']");
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, '');
      el.dispatchEvent(new Event('input', { bubbles: true }));
      setter.call(el, arguments[0]);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    """, value)
    time.sleep(1.5)


def switch_all(drv):
    U.open_global_switcher(drv)
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip() == '全部算法':
                L.js_click(drv, b)
                time.sleep(1.5)
                return True
        except Exception:
            pass
    return False


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

        set_search(drv, KEY)
        res['search_all'] = U.page_state(drv)
        res['shot_search_all'] = U.shot(drv, tag, 'diff_search_all')

        # 选中唯一算法
        st, opt, _ = L.api_json(drv, '/algorithm/options')
        dd = (opt or {}).get('data', opt) if isinstance(opt, dict) else opt
        algos = (dd or {}).get('algorithms') or []
        label = (algos[0].get('label') or algos[0].get('name')) if algos else None
        U.open_global_switcher(drv)
        res['picked'] = U.choose_global_algorithm(drv, label) if label else False
        time.sleep(2.0)
        res['search_with_algo'] = U.page_state(drv)
        res['shot_search_with_algo'] = U.shot(drv, tag, 'diff_search_with_algo')

        # 切回全部算法
        res['back_to_all'] = switch_all(drv)
        time.sleep(1.5)
        res['search_back_all'] = U.page_state(drv)
        res['shot_search_back_all'] = U.shot(drv, tag, 'diff_search_back_all')

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
