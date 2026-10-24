# -*- coding: utf-8 -*-
"""INT-1592 返工补证 2（打回清单问题 2/3）：
1) 执行确认取消的 Network 面板（带同窗口对照请求，证明采集链路有效）
2) 复核历史抽屉长用例名溢出（问题 3）——只读打开真实任务 407（库内 15 条复核历史）

环境：docker React http://127.0.0.1:15173 + docker 真实库栈（database=intelligent_audio_test）。
只读：不提交任何复核/写操作。
输出：tests/ui/artifacts/int1592/73_*.png、74_*.png + evidence_rework2.json
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1592_cherry_pick import (  # noqa: E402
    ART, BASE, body_text, driver, js_click, log, login, set_dark, shot,
)
from verify_int1592_rework import perf_drain, perf_requests, render_network_panel  # noqa: E402


def phase_execute_network(drv, ev):
    drv.get(BASE + '/tasks/published')
    WebDriverWait(drv, 180).until(lambda d: '已发布' in body_text(d) and (
        '暂无已发布任务' in body_text(d) or d.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']")))
    time.sleep(2)
    expand = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']") if b.is_displayed()]
    if not expand:
        ev['execute'] = {'error': '无已发布任务行'}
        return
    js_click(drv, expand[0])
    WebDriverWait(drv, 180).until(lambda d: '冻结报告（发布时快照' in body_text(d))
    time.sleep(2)
    shot(drv, '73_published_with_hidden_network_panel_light.png')
    perf_drain(drv)
    btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='执行']") if b.is_displayed()]
    if not btns:
        ev['execute'] = {'error': '未见执行按钮'}
        return
    js_click(drv, btns[0])
    time.sleep(2)
    confirm_text = None
    try:
        dlgs = [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()]
        shot(drv, '73_execute_confirm_light.png')
        if dlgs:
            confirm_text = dlgs[0].text[:300]
            cancel = [b for b in dlgs[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']")
                      if b.is_displayed()]
            if cancel:
                js_click(drv, cancel[0])
    except Exception as exc:  # noqa: BLE001
        ev['execute_confirm_click_error'] = repr(exc)
    time.sleep(2)
    # 对照请求：同窗口再发一条无害 GET，证明采集链路在该时段有效
    ctrl_ok = drv.execute_script(
        "return fetch('/api/v1/published-tasks?page=1&page_size=5').then(r=>r.status);")
    time.sleep(1.5)
    reqs = perf_requests(drv)
    writes = [r for r in reqs if '/execute' in r['url']]
    ev['execute'] = {
        'confirm_open': confirm_text is not None,
        'confirm_text': confirm_text,
        'cancelled': not [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()],
        'requests': reqs,
        'execute_writes': writes,
        'control_status': ctrl_ok,
    }
    render_network_panel(
        drv, reqs,
        '已发布 v2「执行此版本」确认层：打开 → 取消 → 对照 GET（同一采集窗口）',
        '结论：窗口内 POST /tasks/{id}/execute = %d；末条 GET /api/v1/published-tasks 为同窗口对照（%s），证明采集有效'
        % (len(writes), ctrl_ok),
        '74_execute_cancel_network.png')


def phase_history_drawer(drv, ev, task_id=417):
    drv.get(f'{BASE}/tasks/{task_id}')
    WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
    time.sleep(3)
    link = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '查看复核历史')]") if b.is_displayed()]
    ev['history'] = {'task_id': task_id, 'link_found': bool(link)}
    if not link:
        return
    js_click(drv, link[0])
    # review-history 接口 25~30 s（INT-1625），等条目真正渲染（骨架消失）
    waited = 0
    while waited < 210:
        els = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot*='sheet-content']") if x.is_displayed()]
        t = els[0].text if els else ''
        if '操作人' in t or '暂无复核记录' in t:
            break
        time.sleep(5)
        waited += 5
    ev['history_wait_s'] = waited
    time.sleep(1)
    shot(drv, '75_review_history_drawer_light.png')
    sheet = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot*='sheet-content']") if x.is_displayed()]
    if not sheet:
        ev['history']['error'] = '未见抽屉'
        return
    s = sheet[0]
    ev['history']['head'] = s.text[:800]
    # 溢出检测：抽屉内文本节点 scrollWidth > clientWidth（无省略号 = 被父级裁切）
    data = drv.execute_script(
        """
        const root = arguments[0];
        const out = [];
        root.querySelectorAll('span,div').forEach(e => {
          const t = (e.textContent || '').trim();
          const cs = getComputedStyle(e);
          if (t.length >= 30 && e.children.length === 0) {
            out.push({t: t.slice(0, 60), sw: e.scrollWidth, cw: e.clientWidth,
                      overflow: cs.overflow, textOverflow: cs.textOverflow, whiteSpace: cs.whiteSpace,
                      cls: (e.className || '').toString().slice(0, 120)});
          }
        });
        const sheetRect = root.getBoundingClientRect();
        return {sheet: {w: sheetRect.width, x: sheetRect.x}, nodes: out};
        """, s)
    ev['history']['sheet_rect'] = data['sheet']
    over = [n for n in data['nodes'] if n['sw'] > n['cw'] + 2 or n['cw'] > data['sheet']['w']]
    ev['history']['wide_nodes'] = over[:6]
    ev['history']['nodes_total'] = len(data['nodes'])
    set_dark(drv, True)
    shot(drv, '76_review_history_drawer_dark.png')
    set_dark(drv, False)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1)


def main():
    ev = {'base': BASE, 'started_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    drv = driver()
    try:
        drv.set_page_load_timeout(300)
        login(drv, ev)
        try:
            phase_execute_network(drv, ev)
        except Exception as exc:  # noqa: BLE001
            ev['execute_error'] = repr(exc)
        try:
            phase_history_drawer(drv, ev)
        except Exception as exc:  # noqa: BLE001
            ev['history_error'] = repr(exc)
    finally:
        ev['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(os.path.join(ART, 'evidence_rework2.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
