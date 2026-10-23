# -*- coding: utf-8 -*-
"""INT-1592 补充取证：复核历史抽屉（源任务 419）+ 快速复核真实发起（POST /tasks/results/ai-review）。

背景：本卡自建挑选合并容器（接线测试_INT1592_容器B, 556）上提交人工复核成功，但
GET /tasks/results/556/review-history 为空、review_count=0；复核记录实际落在结果归属的
源任务 419（GET /tasks/results/419/review-history 有本条）。故抽屉 UI 取证改在 419 详情页
（只读），快速复核在同一结果上真实发起以取得 POST 契约证据。

用法：python tests/ui/verify_int1592_review_evidence.py
输出：tests/ui/artifacts/int1592/42~46_*.png + evidence_review_extra.json
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
    ART, BASE, api, body_text, data_of, driver, js_click, log, login, set_dark, shot, toast_texts,
)


def drain(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def new_requests(drv):
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for entry in entries:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:  # noqa: BLE001
            continue
        p = msg.get('message') or {}
        if p.get('method') != 'Network.requestWillBeSent':
            continue
        req = (p.get('params') or {}).get('request') or {}
        url = req.get('url') or ''
        if '/api/' in url:
            out.append({'method': req.get('method'), 'url': url, 'postData': req.get('postData')})
    return out


def main():
    ev = {'base': BASE}
    ev['history_556'] = data_of(api('GET', '/api/v1/tasks/results/556/review-history'))
    ev['count_556'] = data_of(api('GET', '/api/v1/tasks/results/556/review-count'))
    ev['history_419'] = data_of(api('GET', '/api/v1/tasks/results/419/review-history'))
    ev['count_419'] = data_of(api('GET', '/api/v1/tasks/results/419/review-count'))

    drv = driver()
    try:
        login(drv, ev)
        drv.get(BASE + '/tasks/419')
        WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
        time.sleep(3)
        # 复核计数/历史入口
        txt = body_text(drv)
        ev['detail_419'] = {'review_count_text': [t for t in txt.splitlines() if '已复核' in t][:2],
                            'has_history_link': '查看复核历史' in txt}
        shot(drv, '42_task419_detail_light.png')
        link = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '查看复核历史')]") if b.is_displayed()]
        if link:
            js_click(drv, link[0])
            time.sleep(2.5)
            sheet = None
            for sel in ("[data-slot*='sheet-content']", "[role='dialog']"):
                els = [x for x in drv.find_elements(By.CSS_SELECTOR, sel) if x.is_displayed()]
                if els:
                    sheet = els[0]
                    break
            text = sheet.text if sheet else body_text(drv)
            ev['history_drawer'] = {
                'title': [t for t in text.splitlines() if '复核历史' in t][:2],
                'count_line': [t for t in text.splitlines() if t.strip().startswith('共 ')][:1],
                'has_operator': '操作人' in text,
                'has_arrow': '→' in text,
                'has_comment': '接线测试_INT1592 人工复核备注' in text,
                'head': text[:900],
            }
            shot(drv, '43_review_history_drawer_light.png')
            set_dark(drv, True)
            shot(drv, '44_review_history_drawer_dark.png')
            set_dark(drv, False)
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.5)
        else:
            ev['history_drawer'] = {'error': '未见「查看复核历史」入口'}

        # 快速复核 → 真实发起
        quick = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='快速复核']") if b.is_displayed()]
        if quick:
            js_click(drv, quick[0])
            time.sleep(3)
            drain(drv)
            initiate = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '发起快速复核')]") if b.is_displayed()]
            ev['quick_initiate_btn'] = bool(initiate)
            if initiate:
                js_click(drv, initiate[0])
                time.sleep(4)
                shot(drv, '45_quick_review_initiated_light.png')
                state = ''
                for _ in range(30):
                    els = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']") if x.is_displayed()]
                    if els:
                        state = els[0].text
                    if state and ('失败' in state or '错误' in state or 'AI 复核结论' in state or '存疑' in state):
                        break
                    time.sleep(2)
                ev['quick_state'] = state[:1000]
                ev['quick_toasts'] = toast_texts(drv)
                ev['quick_requests'] = [r for r in new_requests(drv)
                                        if 'ai-review' in r['url'] or 'ai_review' in r['url']]
                ev['ai_history_419'] = data_of(api('GET', '/api/v1/tasks/results/419/ai-review-history'))
                shot(drv, '46_quick_review_final_light.png')
                # 关闭
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    finally:
        with open(os.path.join(ART, 'evidence_review_extra.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
