# -*- coding: utf-8 -*-
"""INT-1538 round2 补拍：实验室播放点击「播放」→ POST /audios/{id}/preview 真实返回。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By

GROUP = os.environ.get('CASE_GROUP', '接线测试_INT1538_复走组')
OUT = {}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception:
            pass
        time.sleep(interval)
    return None


d = L.driver()
try:
    for _ in range(4):
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        if '/login' not in d.current_url:
            break
        for b in d.find_elements(By.TAG_NAME, 'button'):
            t = (b.text or '').strip()
            if t and ('进入' in t or '登录' in t) and vis(b):
                L.js_click(d, b)
                time.sleep(4)
                break
    time.sleep(3)
    # 重置 → 分组 facet
    rst = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '重置'), None), 40)
    if rst:
        L.js_click(d, rst)
        time.sleep(4)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 40)
    L.js_click(d, trig)
    time.sleep(1.5)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(6)
    if not [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)]:
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1)
        h = retry(lambda: d.execute_script("""
            const g = arguments[0];
            for (const el of document.querySelectorAll('div')) {
              const cls = (el.className || '').toString();
              if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
                  (el.innerText || '').trim().startsWith(g)) { return el; }
            }
            return null;
        """, GROUP), 25)
        d.execute_script('arguments[0].click();', h)
        time.sleep(6)
    pb = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 30)
    L.js_click(d, pb)
    L.wait_dialog(d, '音频试听配置', 25)
    time.sleep(1)
    lab = retry(lambda: next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '实验室播放')]") if vis(x)), None), 15)
    L.js_click(d, lab)
    time.sleep(0.8)
    OUT['radio'] = d.execute_script("return [...document.querySelectorAll(\"input[name='preview-mode']\")].map(r=>r.checked)")
    sb = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None)
    L.js_click(d, sb)
    time.sleep(2)
    OUT['stage'] = (L.dialogs(d)[-1].text or '')[:200] if L.dialogs(d) else ''
    L.clear_fetch_log(d)
    play = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='播放']") if vis(b)), None), 15)
    OUT['play_btn'] = bool(play)
    t0 = time.time()
    L.js_click(d, play)
    alerts = []
    end = time.time() + 100
    while time.time() < end:
        alerts = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
        if alerts:
            break
        time.sleep(1)
    OUT['wait_s'] = round(time.time() - t0, 1)
    OUT['lab_alerts'] = alerts
    OUT['time_text'] = (lambda els: els[-1].text.strip() if els else '')(
        [e for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)])
    OUT['fetch'] = [{'method': e.get('method'), 'url': (e.get('url') or '')[:110], 'status': e.get('status'),
                     'resBody': (e.get('resBody') or '')[:300]}
                    for e in L.fetch_log(d) if '/audios/' in (e.get('url') or '')]
    L.shot(d, 'p02b_player_lab_error_light')
finally:
    with open(os.path.join(L.HERE, 'evidence_int1538_labplay.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    L.save_evidence('labplay_evidence', OUT)
    print(json.dumps(OUT, ensure_ascii=False, default=str)[:1500])
    d.quit()
