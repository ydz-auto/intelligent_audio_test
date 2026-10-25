# -*- coding: utf-8 -*-
"""INT-1538 I：导出弹窗裁定 + 分组弹窗（重命名/删除确认）+ 深色截图（抽屉/音频库）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

OUT = {'sections': {}}
GROUP = '接线测试_INT1538_组'


def sec(name):
    def deco(fn):
        t0 = time.time()
        try:
            fn()
            OUT['sections'][name] = {'ok': True, 'dur': round(time.time() - t0, 1)}
        except Exception:
            OUT['sections'][name] = {'ok': False, 'err': traceback.format_exc()[-700:],
                                     'dur': round(time.time() - t0, 1)}
            L.save_evidence('misc_evidence', OUT)
        return fn
    return deco


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


def drawer():
    ds = [x for x in L.dialogs(d) if ('新增测试用例' in (x.text or '') or '编辑测试用例' in (x.text or ''))]
    return ds[-1] if ds else None


def audio_dlg():
    ds = [x for x in L.dialogs(d) if '选择音频文件' in (x.text or '')]
    return ds[-1] if ds else None


def btns(scope, text):
    return [b for b in scope.find_elements(By.TAG_NAME, 'button') if text in (b.text or '') and vis(b)]


def fill(el, value):
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)

    @sec('export_dialog')
    def _():
        b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if (x.text or '').strip() == '导出' and vis(x)), None), 25)
        L.js_click(d, b)
        w = L.wait_dialog(d, '导出用例', 20)
        time.sleep(1)
        OUT['export_text'] = (w.text or '')[:500]
        L.clear_fetch_log(d)
        L.shot(d, 'i01_export_light')
        for x in w.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '开始导出' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(3)
        OUT['export_toasts'] = L.wait_toast(d, 12)
        OUT['export_fetch'] = [(e.get('method'), e.get('url', '')[:70], e.get('status')) for e in L.fetch_log(d)]
        OUT['export_dialog_closed'] = len([x for x in L.dialogs(d) if '导出用例' in (x.text or '')]) == 0

    @sec('group_dialog')
    def _():
        trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 20)
        L.js_click(d, trig)
        time.sleep(1.2)
        opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == GROUP), None), 15)
        L.js_click(d, opt)
        time.sleep(5)
        OUT['filtered_text'] = L.body_text(d)[-500:]
        # 组头「编辑」按钮
        edit_btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '编辑']
        OUT['group_edit_btns'] = len(edit_btns)
        if edit_btns:
            L.js_click(d, edit_btns[0])
            time.sleep(1.5)
            w = [x for x in L.dialogs(d) if '分组' in (x.text or '') and '用例' not in (x.text or '')[:6]]
            OUT['group_dialog_texts'] = [(x.text or '')[:400] for x in w]
            L.shot(d, 'i02_group_edit_dialog')
            if w:
                top = w[-1]
                inp = [i for i in top.find_elements(By.TAG_NAME, 'input') if vis(i)]
                if inp:
                    nm0 = inp[0].get_attribute('value')
                    OUT['group_name_before'] = nm0
                    fill(inp[0], GROUP + '_改')
                    for c in top.find_elements(By.TAG_NAME, 'button'):
                        if (c.text or '').strip() in ('保存', '确定', '确认') and vis(c):
                            L.js_click(d, c)
                            break
                    time.sleep(3)
                    OUT['rename_toasts'] = L.wait_toast(d, 12)
                    # 改回
                    time.sleep(1)
                    ebs = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '编辑']
                    if ebs:
                        L.js_click(d, ebs[0])
                        time.sleep(1.5)
                        w2 = [x for x in L.dialogs(d) if '分组' in (x.text or '')]
                        if w2:
                            inp2 = [i for i in w2[-1].find_elements(By.TAG_NAME, 'input') if vis(i)]
                            if inp2:
                                fill(inp2[0], GROUP)
                                for c in w2[-1].find_elements(By.TAG_NAME, 'button'):
                                    if (c.text or '').strip() in ('保存', '确定', '确认') and vis(c):
                                        L.js_click(d, c)
                                        break
                                time.sleep(3)
                                OUT['rename_back_toasts'] = L.wait_toast(d, 12)
        # 删除入口
        del_btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '删除']
        OUT['group_delete_btns'] = len(del_btns)
        if del_btns:
            L.js_click(d, del_btns[0])
            time.sleep(1.5)
            ws = [x for x in L.dialogs(d) if '删除' in (x.text or '')]
            OUT['group_delete_dialog'] = [(x.text or '')[:400] for x in ws]
            L.shot(d, 'i03_group_delete_dialog')
            for x in ws:
                for c in x.find_elements(By.TAG_NAME, 'button'):
                    if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                        L.js_click(d, c)
                        time.sleep(1)
                        break
        # 新建分组入口（断头复核）
        OUT['new_group_entry'] = [b.text.strip() for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and '新建分组' in (b.text or '')]

    @sec('dark_shots')
    def _():
        # 关掉筛选回全部
        trig = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').replace('\n', '') == '分组' + GROUP), None)
        if trig:
            L.js_click(d, trig)
            time.sleep(1)
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if vis(b) and '接线测试_INT1538_组' in (b.text or ''):
                    L.js_click(d, b)
                    break
            time.sleep(3)
        L.apply_theme(d, 'dark')
        time.sleep(1)
        # 打开新增抽屉
        btn = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if (x.text or '').strip() == '新增用例' and vis(x)), None), 20)
        L.js_click(d, btn)
        retry(lambda: drawer(), 20)
        time.sleep(1.5)
        OUT['dark_html_class'] = d.execute_script("return document.documentElement.className")
        OUT['dark_body_bg'] = d.execute_script("return getComputedStyle(document.body).backgroundColor")
        L.shot(d, 'i04_drawer_dark')
        # 音频库深色
        db = drawer()
        for t in db.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if (t.text or '').strip() == '音频列表' and vis(t):
                L.js_click(d, t)
                break
        time.sleep(1.2)
        L.js_click(d, btns(drawer(), '从音频库选择')[0])
        retry(lambda: audio_dlg(), 25)
        time.sleep(4)
        L.shot(d, 'i05_audio_dialog_dark')
        OUT['dark_audio_dialog_text'] = (audio_dlg().text or '')[:200]
        for x in L.dialogs(d):
            for c in x.find_elements(By.TAG_NAME, 'button'):
                if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                    try:
                        L.js_click(d, c)
                    except Exception:
                        pass
                    break
        time.sleep(1)
        L.apply_theme(d, 'light')
        L.shot(d, 'i06_after_light')
finally:
    L.save_evidence('misc_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
