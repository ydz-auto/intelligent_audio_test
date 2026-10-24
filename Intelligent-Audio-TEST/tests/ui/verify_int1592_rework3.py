# -*- coding: utf-8 -*-
"""INT-1592 返工补证 3：仅重采「执行确认 → 取消」Network 面板（带同窗口对照 GET）。

环境：docker React http://127.0.0.1:15173 + docker 真实库栈。只读（取消即不写）。
输出：tests/ui/artifacts/int1592/74_execute_cancel_network.png + evidence_rework3.json
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1592_cherry_pick import (  # noqa: E402
    ART, BASE, body_text, driver, js_click, log, login, shot,
)
from verify_int1592_rework import perf_drain, perf_requests, render_network_panel  # noqa: E402


def main():
    ev = {'base': BASE, 'started_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    drv = driver()
    try:
        drv.set_page_load_timeout(300)
        login(drv, ev)
        ok = False
        for attempt in range(3):
            try:
                drv.get(BASE + '/tasks/published')
                WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR,
                                                                        "button[aria-label='展开版本详情']"))
                time.sleep(2)
                expand = [b for b in drv.find_elements(By.CSS_SELECTOR,
                                                       "button[aria-label='展开版本详情']") if b.is_displayed()]
                js_click(drv, expand[0])
                WebDriverWait(drv, 240).until(lambda d: '冻结报告（发布时快照' in body_text(d))
                time.sleep(2)
                perf_drain(drv)
                btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='执行']")
                        if b.is_displayed()]
                js_click(drv, btns[0])
                time.sleep(2)
                dlgs = [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()]
                ev['confirm_text'] = dlgs[0].text[:300] if dlgs else None
                shot(drv, '73_execute_confirm_light.png')
                if dlgs:
                    cancel = [b for b in dlgs[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']")
                              if b.is_displayed()]
                    if cancel:
                        js_click(drv, cancel[0])
                time.sleep(2)
                ev['cancelled'] = not [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")
                                       if x.is_displayed()]
                ctrl = drv.execute_script(
                    "return fetch('/api/v1/published-tasks?page=1&page_size=5',"
                    "{headers:{Authorization:'Bearer '+(localStorage.getItem('iatp:auth:token:v1')||'')}})"
                    ".then(r=>r.status);")
                time.sleep(1.5)
                reqs = perf_requests(drv)
                writes = [r for r in reqs if '/execute' in r['url']]
                ev.update({'attempt': attempt + 1, 'control_status': ctrl, 'requests': reqs,
                           'execute_writes': writes, 'cancelled_ok': ev.get('cancelled')})
                render_network_panel(
                    drv, reqs,
                    '已发布 v2「执行此版本」确认层：打开 → 取消 → 对照 GET（同一采集窗口）',
                    '结论：窗口内 POST /tasks/{id}/execute = %d；末条 GET /api/v1/published-tasks 对照返回 %s，证明采集链路有效'
                    % (len(writes), ctrl),
                    '74_execute_cancel_network.png')
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                ev['attempt_%d_error' % (attempt + 1)] = repr(exc)
                time.sleep(3)
        ev['ok'] = ok
    finally:
        ev['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(os.path.join(ART, 'evidence_rework3.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
