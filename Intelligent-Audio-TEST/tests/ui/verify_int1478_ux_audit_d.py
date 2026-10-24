# -*- coding: utf-8 -*-
"""INT-1478 前端UX审计（D）：复核历史抽屉（含 Tooltip/长名）、挑选阶段2 候选、发布弹窗选项。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1488_common as C
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait

ART = os.path.join('tests', 'ui', 'artifacts', 'int1478_audit')
os.makedirs(ART, exist_ok=True)
C.ART = ART
OUT = {'steps': {}, 'env': []}


def login(drv):
    drv.get(C.BASE + '/login')
    time.sleep(2)
    try:
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def retheme(drv, theme):
    drv.execute_script('localStorage.setItem(%r, %r)' % (C.THEME_KEY, theme))
    drv.refresh()
    time.sleep(2.0)
    if theme == 'dark':
        WebDriverWait(drv, 20).until(lambda d: 'dark' in (d.execute_script('return document.documentElement.className') or ''))


def last_dialog(drv):
    ds = [d for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if d.is_displayed()]
    return ds[-1] if ds else None


def wait_contains(drv, needle, timeout=60):
    return WebDriverWait(drv, timeout).until(lambda d: needle in C.body(d))


def main():
    OUT['env'].append(C.env_check('start'))
    drv = C._driver()
    try:
        login(drv)

        # ---- 复核历史（任务 417）----
        drv.get(C.BASE + '/tasks/417')
        wait_contains(drv, '查看复核历史', 180)
        time.sleep(2.0)

        def review_history():
            C.clear_fetch_log(drv)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            if not btns:
                raise AssertionError('查看复核历史入口未找到')
            C.js_click(drv, btns[0])
            WebDriverWait(drv, 120).until(lambda d: re.search(r'共\s*\d+\s*条', C.body(d)) is not None)
            time.sleep(1.2)
            sheet = last_dialog(drv)
            txt = sheet.text
            items = [li for li in sheet.find_elements(By.TAG_NAME, 'li') if li.is_displayed()]
            badges = drv.execute_script(
                "return [...document.querySelectorAll('[data-slot=review-history-case-name]')].map(e=>{"
                "const s=e.querySelector('span');const r=e.getBoundingClientRect();"
                "return {w:Math.round(r.width),right:Math.round(r.right),sw:s?s.scrollWidth:null,cw:s?s.clientWidth:null,"
                "len:(s?s.textContent:'').length};});")
            sheet_rect = drv.execute_script('const r=arguments[0].getBoundingClientRect();return {left:Math.round(r.left),right:Math.round(r.right)};', sheet)
            hover = {}
            try:
                badge = drv.find_elements(By.CSS_SELECTOR, '[data-slot=review-history-case-name]')[0]
                ActionChains(drv).move_to_element(badge).perform()
                time.sleep(1.5)
                tips = [e.text.strip() for e in drv.find_elements(By.CSS_SELECTOR, '[data-slot*=tooltip], [role=tooltip]') if e.is_displayed() and (e.text or '').strip()]
                hover['tooltip'] = tips[-1][:120] if tips else None
            except Exception as e:
                hover['error'] = repr(e)
            C.shot(drv, '17_review_history_light.png')
            reqs = [(e['method'], e['url'], e.get('status')) for e in C.fetch_log(drv)]
            return {'count_text': (re.search(r'共\s*\d+\s*条', txt).group(0) if re.search(r'共\s*\d+\s*条', txt) else None),
                    'li_count': len(items), 'badges': badges[:3], 'sheet_rect': sheet_rect,
                    'hover': hover, 'snippet': txt[:240],
                    'history_requests': [r for r in reqs if 'review' in r[1] or 'cherry-picks' in r[1]]}
        C.step('review_history', review_history)

        def review_history_dark():
            retheme(drv, 'dark')
            wait_contains(drv, '查看复核历史', 120)
            time.sleep(1.5)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            C.js_click(drv, btns[0])
            WebDriverWait(drv, 120).until(lambda d: re.search(r'共\s*\d+\s*条', C.body(d)) is not None)
            time.sleep(1.0)
            C.shot(drv, '17b_review_history_dark.png')
            retheme(drv, 'light')
            return {'ok': True}
        C.step('review_history_dark', review_history_dark)

        # ---- 挑选阶段 2 候选 ----
        drv.get(C.BASE + '/tasks/cherry-picks')
        wait_contains(drv, '开始挑选', 120)
        time.sleep(1.5)

        def stage2_candidates():
            C.click_button(drv, '开始挑选')
            wait_contains(drv, '挑选 · 阶段 1', 60)
            time.sleep(2.5)
            boxes = [b for b in drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择任务 "]') if b.is_displayed()]
            C.js_click(drv, boxes[0])
            time.sleep(1.0)
            C.clear_fetch_log(drv)
            nexts = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'下一步')]") if b.is_displayed()]
            C.js_click(drv, nexts[0])
            wait_contains(drv, '挑选 · 阶段 2', 60)
            deadline = time.time() + 60
            seen = None
            while time.time() < deadline:
                time.sleep(3)
                reqs = [(e['method'], e['url'], e.get('status')) for e in C.fetch_log(drv)]
                cand = [r for r in reqs if 'cherry-picks/candidates' in r[1]]
                if cand:
                    seen = cand
                    break
            time.sleep(2)
            txt = C.body(drv)
            m = re.search(r'已选\s*\d+\s*条结果\s*·\s*来自\s*(\d+)\s*个任务', txt)
            C.shot(drv, '18_stage2_candidates_light.png')
            return {'candidates_requests': seen, 'summary': m.group(0) if m else None,
                    'snippet': txt[txt.find('阶段 2'):txt.find('阶段 2') + 200] if '阶段 2' in txt else txt[:200]}
        C.step('stage2_candidates', stage2_candidates)

        # ---- 发布弹窗选项 ----
        drv.get(C.BASE + '/tasks/daily')
        WebDriverWait(drv, 120).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')) > 0)
        time.sleep(1.5)

        def publish_options():
            btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if b.is_displayed()]
            C.js_click(drv, btns[0])
            time.sleep(0.8)
            items = [i for i in drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if i.is_displayed()]
            for i in items:
                if '发布' in (i.text or ''):
                    C.js_click(drv, i)
                    break
            d = WebDriverWait(drv, 20).until(lambda x: last_dialog(x))
            try:
                WebDriverWait(drv, 45).until(lambda x: (last_dialog(x) is not None) and ('来源任务' in last_dialog(x).text) and ('加载中' not in last_dialog(x).text))
            except Exception:
                pass
            time.sleep(2)
            trig = [t for t in d.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if t.is_displayed()]
            if not trig:
                raise AssertionError('来源任务下拉未找到')
            C.js_click(drv, trig[0])
            time.sleep(1.5)
            opts = [o.text.strip() for o in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if o.is_displayed()]
            C.shot(drv, '19_publish_options_light.png')
            bare_ids = [o for o in opts if re.fullmatch(r'#?\d+', o)]
            return {'option_count': len(opts), 'head': opts[:3], 'bare_ids': bare_ids[:5],
                    'has_status_case': bool(opts) and ('用例' in opts[0])}
        C.step('publish_options', publish_options)

        OUT['env'].append(C.env_check('end'))
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    OUT['steps'] = C.RESULTS.get('steps', {})
    OUT['failed_steps'] = C.FAIL
    with open(os.path.join(ART, 'audit_d.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    print('FAILED STEPS:', C.FAIL)


if __name__ == '__main__':
    main()
