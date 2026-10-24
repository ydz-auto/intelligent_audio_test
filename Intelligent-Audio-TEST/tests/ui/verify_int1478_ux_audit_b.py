# -*- coding: utf-8 -*-
"""INT-1478 前端UX审计（B）：已发布页签（快照/冻结报告）+ 挑选合并（阶段1/购物车/挑选集）+ 人工复核入口。
只读为主：购物车/挑选集只验取消与空态，不提交；复核弹窗只打开不提交。
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
from selenium.webdriver.support.ui import WebDriverWait

ART = os.path.join('tests', 'ui', 'artifacts', 'int1478_audit')
os.makedirs(ART, exist_ok=True)
C.ART = ART

OUT = {'env': [], 'data': {}}


def api(path, params=None):
    url = C.API + '/api/v1' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode()).get('data')


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


def close_dialog(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.8)


def main():
    health = C.env_check('start')
    OUT['env'].append(health)
    pub = api('/published-tasks', {'page': 1, 'per_page': 20})
    OUT['data']['published_total'] = pub.get('total')
    pub0 = (pub.get('items') or [{}])[0]
    OUT['data']['published_item'] = {k: pub0.get(k) for k in ('id', 'name', 'has_task_snapshot', 'version', 'version_count', 'source_task_id')}
    pub_detail = api('/published-tasks/%s' % pub0.get('id'))
    rs = pub_detail.get('report_snapshot') or {}
    cases = rs.get('cases') or []
    OUT['data']['report_snapshot'] = {'cases': len(cases), 'has_summary': bool(rs.get('summary')), 'keys': list(rs.keys())}
    pickable = api('/tasks/cherry-picks/pickable-tasks', {'page': 1, 'per_page': 10})
    OUT['data']['pickable_total'] = pickable.get('total')

    drv = C._driver()
    try:
        login(drv)

        # ---------- 日常：删除二次确认取消路径 ----------
        drv.get(C.BASE + '/tasks/daily')
        WebDriverWait(drv, 90).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')) > 0)
        time.sleep(1.5)

        def delete_cancel():
            def any_dlg():
                for sel in ('[role="alertdialog"]', '[role="dialog"]'):
                    for x in drv.find_elements(By.CSS_SELECTOR, sel):
                        if x.is_displayed():
                            return x
                return None
            C.clear_fetch_log(drv)
            btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if b.is_displayed()]
            C.js_click(drv, btns[0])
            time.sleep(1.2)
            items = [i for i in drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if i.is_displayed()]
            labels = [(i.text or '').strip() for i in items]
            target = [i for i in items if (i.text or '').strip() == '删除']
            if not target:
                raise AssertionError('删除项缺失: %s' % labels)
            C.js_click(drv, target[0])
            d = WebDriverWait(drv, 20).until(lambda x: any_dlg())
            txt = d.text
            role = d.get_attribute('role')
            C.shot(drv, '04_confirm_delete_light.png')
            cancel = [b for b in d.find_elements(By.XPATH, './/button') if (b.text or '').strip() in ('取消', 'Cancel')]
            C.js_click(drv, cancel[0])
            time.sleep(1.5)
            writes = [e for e in C.fetch_log(drv) if e['method'] in ('DELETE', 'POST', 'PUT', 'PATCH')]
            return {'role': role, 'menu_labels': labels, 'snippet': txt[:160],
                    'closed_after_cancel': any_dlg() is None, 'writes_on_cancel': writes}
        C.step('delete_confirm_cancel', delete_cancel)

        # ---------- 已发布 ----------
        drv.get(C.BASE + '/tasks/published')
        WebDriverWait(drv, 90).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
        time.sleep(2.0)

        def published_page():
            txt = C.body(drv)
            m = re.search(r'共\s*([\d,]+)\s*条', txt)
            expand = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="展开版本详情"]') if b.is_displayed()]
            if not expand:
                raise AssertionError('展开版本详情按钮未找到')
            C.js_click(drv, expand[0])
            time.sleep(2.5)
            txt2 = C.body(drv)
            return {'total_text': m.group(1) if m else None, 'api_total': OUT['data']['published_total'],
                    'legacy_note': '历史版本（发布时未冻结任务详情）' in txt2,
                    'has_frozen_entry': '查看冻结任务详情' in txt2,
                    'has_report_entry': '查看冻结报告' in txt2,
                    'snippet': txt2[txt2.find('版本历史'):txt2.find('版本历史') + 400] if '版本历史' in txt2 else txt2[:300]}
        C.step('published_page', published_page)
        C.shot(drv, '11_published_expanded_light.png')

        def report_snapshot():
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看冻结报告')]") if b.is_displayed()]
            if not btns:
                raise AssertionError('查看冻结报告入口未找到')
            C.js_click(drv, btns[0])
            time.sleep(2.5)
            d = last_dialog(drv)
            if d is None:
                raise AssertionError('冻结报告弹窗未打开')
            txt = d.text
            tag_texts = drv.execute_script(
                "const d=arguments[0];const all=[...d.querySelectorAll('*')].filter(e=>e.children.length===0);"
                "const zh=all.map(e=>e.textContent.trim()).filter(t=>t&&t.length<=60);"
                "return {objectObject:(d.textContent.match(/\\[object Object\\]/g)||[]).length,"
                "sample:zh.slice(0,40)};", d)
            C.shot(drv, '12_report_snapshot_light.png')
            rows = len([e for e in d.find_elements(By.CSS_SELECTOR, '.border-b') if e.is_displayed()])
            return {'dialog_snippet': txt[:300], 'rows_border_b': rows,
                    'object_object_count': tag_texts['objectObject'],
                    'api_cases': OUT['data']['report_snapshot'],
                    'text_sample': tag_texts['sample'][:20]}
        C.step('report_snapshot', report_snapshot)

        def report_snapshot_dark():
            retheme(drv, 'dark')
            expand = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="展开版本详情"]') if b.is_displayed()]
            C.js_click(drv, expand[0])
            time.sleep(2.5)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看冻结报告')]") if b.is_displayed()]
            C.js_click(drv, btns[0])
            time.sleep(2.5)
            C.shot(drv, '12b_report_snapshot_dark.png')
            close_dialog(drv)
            retheme(drv, 'light')
            return {'ok': True}
        C.step('report_snapshot_dark', report_snapshot_dark)

        # ---------- 挑选合并 ----------
        C.clear_fetch_log(drv)
        drv.get(C.BASE + '/tasks/cherry-picks')
        WebDriverWait(drv, 90).until(lambda d: '开始挑选' in C.body(d))
        time.sleep(2.0)

        def cp_entry():
            C.click_button(drv, '开始挑选')
            WebDriverWait(drv, 30).until(lambda d: '挑选 · 阶段 1' in C.body(d))
            time.sleep(3.0)
            txt = C.body(drv)
            m = re.search(r'全选当前筛选将选中命中全部\s*([\d,]+)\s*个任务', txt)
            rows = len([e for e in drv.find_elements(By.CSS_SELECTOR, '[data-testid^="pick-task-"]') if e.is_displayed()])
            reqs = [(e['method'], e['url']) for e in C.fetch_log(drv)]
            cand = [r for r in reqs if 'cherry-picks/candidates' in r[1]]
            pick = [r for r in reqs if 'pickable-tasks' in r[1]]
            C.shot(drv, '13_cherry_pick_stage1_light.png')
            return {'total_text': m.group(1) if m else None, 'api_total': OUT['data']['pickable_total'],
                    'rows': rows, 'candidates_requests_on_stage1': cand, 'pickable_requests': pick[:3]}
        C.step('cp_stage1', cp_entry)

        def cp_stage2():
            boxes = [b for b in drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择任务 "]') if b.is_displayed()]
            if not boxes:
                raise AssertionError('阶段 1 任务勾选框未找到')
            C.js_click(drv, boxes[0])
            time.sleep(0.8)
            C.clear_fetch_log(drv)
            nexts = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'下一步')]") if b.is_displayed()]
            if not nexts:
                raise AssertionError('下一步按钮未找到')
            C.js_click(drv, nexts[0])
            WebDriverWait(drv, 60).until(lambda d: '挑选 · 阶段 2' in C.body(d))
            time.sleep(3.0)
            reqs = [(e['method'], e['url']) for e in C.fetch_log(drv)]
            cand = [r for r in reqs if 'cherry-picks/candidates' in r[1]]
            txt = C.body(drv)
            C.shot(drv, '13b_cherry_pick_stage2_light.png')
            return {'snippet': txt[txt.find('阶段 2'):txt.find('阶段 2') + 200] if '阶段 2' in txt else '',
                    'candidates_requests': cand[:3]}
        C.step('cp_stage2', cp_stage2)

        def cp_cart_empty():
            close = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'打开购物车')]")]
            # 阶段 1 无该按钮时退回列表页再开
            if not close:
                drv.get(C.BASE + '/tasks/cherry-picks')
                WebDriverWait(drv, 60).until(lambda d: '打开购物车' in C.body(d))
                time.sleep(1.5)
            C.click_button(drv, '打开购物车')
            time.sleep(2.0)
            d = last_dialog(drv)
            txt = d.text if d else C.body(drv)
            C.shot(drv, '14_cart_drawer_light.png')
            return {'snippet': txt[:300], 'empty_state': ('购物车为空' in txt or '暂无' in txt)}
        C.step('cp_cart', cp_cart_empty)

        def cp_save_set_cancel():
            # 打开另存挑选集（空购物车下按钮通常 disabled，记录状态即可）
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'另存') or contains(.,'保存挑选集')]") if b.is_displayed()]
            info = {'found': len(btns), 'disabled': [b.get_attribute('disabled') is not None for b in btns]}
            C.clear_fetch_log(drv)
            if btns and btns[0].get_attribute('disabled') is None:
                C.js_click(drv, btns[0])
                time.sleep(1.5)
                d = last_dialog(drv)
                if d is not None:
                    C.shot(drv, '15_save_set_light.png')
                    info['dialog'] = d.text[:200]
                    close_dialog(drv)
            info['writes'] = [e for e in C.fetch_log(drv) if e['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')]
            close_dialog(drv)
            return info
        C.step('cp_save_set', cp_save_set_cancel)

        # ---------- 人工复核入口（任务 417） ----------
        drv.get(C.BASE + '/tasks/417')
        WebDriverWait(drv, 90).until(lambda d: '关联用例列表' in (d.execute_script('return document.body.textContent') or '') or '查看复核历史' in C.body(d))
        time.sleep(2.5)

        def review_history():
            from selenium.webdriver.common.action_chains import ActionChains
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            if not btns:
                raise AssertionError('查看复核历史入口未找到')
            C.js_click(drv, btns[0])
            WebDriverWait(drv, 60).until(lambda d: re.search(r'共\s*\d+\s*条', C.body(d)) is not None)
            time.sleep(1.0)
            sheet = last_dialog(drv)
            txt = sheet.text
            items = [li for li in sheet.find_elements(By.TAG_NAME, 'li') if li.is_displayed()]
            badges = drv.execute_script(
                "return [...document.querySelectorAll('[data-slot=review-history-case-name]')].map(e=>{"
                "const s=e.querySelector('span');const r=e.getBoundingClientRect();"
                "return {w:Math.round(r.width),right:Math.round(r.right),sw:s?s.scrollWidth:null,cw:s?s.clientWidth:null,"
                "text:(s?s.textContent:'').slice(0,90),len:(s?s.textContent:'').length};});")
            sheet_rect = drv.execute_script('const e=arguments[0];const r=e.getBoundingClientRect();return {left:Math.round(r.left),right:Math.round(r.right)};', sheet)
            tooltip = None
            if items:
                try:
                    first_badge = drv.find_elements(By.CSS_SELECTOR, '[data-slot="review-history-case-name"]')[0]
                    ActionChains(drv).move_to_element(first_badge).perform()
                    time.sleep(1.5)
                    tips = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-slot*="tooltip"]') if e.is_displayed() and (e.text or '').strip()]
                    tooltip = tips[-1] if tips else None
                except Exception as e:
                    tooltip = 'hover_err:%r' % e
            C.shot(drv, '17_review_history_light.png')
            return {'count_text': re.search(r'共\s*\d+\s*条', txt).group(0) if re.search(r'共\s*\d+\s*条', txt) else None,
                    'li_count': len(items), 'snippet': txt[:200],
                    'badges': badges[:4], 'sheet_rect': sheet_rect, 'tooltip': (tooltip or '')[:120]}
        C.step('review_history', review_history)
        close_dialog(drv)

        def review_history_dark():
            retheme(drv, 'dark')
            WebDriverWait(drv, 90).until(lambda d: '查看复核历史' in C.body(d))
            time.sleep(1.5)
            btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'查看复核历史')]") if b.is_displayed()]
            C.js_click(drv, btns[0])
            WebDriverWait(drv, 60).until(lambda d: re.search(r'共\s*\d+\s*条', C.body(d)) is not None)
            time.sleep(1.0)
            C.shot(drv, '17b_review_history_dark.png')
            close_dialog(drv)
            retheme(drv, 'light')
            return {'ok': True}
        C.step('review_history_dark', review_history_dark)

        def manual_review_entry():
            btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='人工复核']") if b.is_displayed()]
            if not btns:
                raise AssertionError('人工复核按钮未找到')
            C.js_click(drv, btns[0])
            time.sleep(2.5)
            d = last_dialog(drv)
            if d is None:
                raise AssertionError('人工复核弹窗未打开')
            txt = d.text
            C.shot(drv, '16_manual_review_light.png')
            close_dialog(drv)
            writes = [e for e in C.fetch_log(drv) if e['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')]
            return {'snippet': txt[:400], 'writes_after_open_close': writes[-5:]}
        C.step('manual_review_entry', manual_review_entry)

        health2 = C.env_check('end')
        OUT['env'].append(health2)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    OUT['data']['cart_after'] = api('/tasks/cherry-picks/cart')
    OUT['data']['sets_after'] = api('/tasks/cherry-picks/sets')
    OUT['steps'] = C.RESULTS.get('steps', {})
    OUT['screenshots'] = C.RESULTS.get('screenshots', [])
    OUT['failed_steps'] = C.FAIL
    with open(os.path.join(ART, 'audit_b.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    print('FAILED STEPS:', C.FAIL)


if __name__ == '__main__':
    main()
