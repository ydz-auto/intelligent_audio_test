# -*- coding: utf-8 -*-
"""INT-1643 回收站完整链路 + 导出弹窗缺陷 + 抽屉五步 + 深浅色截图。

链路：软删 → 回收站视图 → 恢复 → 再软删 → 彻底删除（每步 API 回读）。
另复现 INT-1642 五项修复的当前状态（修复卡未交付，均为断头复现）。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

GROUP = '接线测试_INT1643_目标组'
CID = '701fd9e8-dc88-456f-b5e6-04036fe37483'   # C
NAME = '接线测试_INT1643_批量_C'
OUT = {}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.4):
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


def find_dialog(kw):
    ds = [x for x in L.dialogs(d) if kw in (x.text or '')]
    return ds[-1] if ds else None


def confirm(texts=('删除', '恢复', '彻底删除', '确定', '确认')):
    for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog'], [role='dialog']"):
        if not vis(x):
            continue
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if vis(c) and (c.text or '').strip() in texts:
                nm = (c.text or '').strip()
                L.js_click(d, c)
                return nm
    return None


def api_trash():
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + NAME + '&only_deleted=1')
    items = ((p or {}).get('data') or {}).get('items') or []
    return st, [(x.get('name'), x.get('deleted'), x.get('id')) for x in items]


def api_live():
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + NAME)
    items = ((p or {}).get('data') or {}).get('items') or []
    return st, [(x.get('name'), x.get('deleted'), x.get('id')) for x in items]


def open_group():
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 15)
    L.js_click(d, opt)
    time.sleep(5)
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 15)
    L.js_click(d, hdr)
    time.sleep(5)


def reset_filters():
    r = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '重置'), None)
    if r is not None:
        L.js_click(d, r)
        time.sleep(3)


def click_trash():
    t = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                            if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.clear_fetch_log(d)
    L.js_click(d, t)

    def switched():
        btns = [x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例'], button[aria-label='彻底删除']") if vis(x)]
        txt = L.body_text(d)
        if btns or '回收站为空' in txt or '没有找到符合条件的回收站用例' in txt:
            return True
        # 分组视图折叠：展开目标组
        return None
    retry(switched, 20)
    time.sleep(2)
    return [(e.get('method'), (e.get('url') or '')[:90], e.get('status')) for e in L.fetch_log(d)]


def expand_if_needed():
    """回收站视图里组可能折叠：没有恢复/彻底删除按钮时点开组头。"""
    if any(vis(x) for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例'], button[aria-label='彻底删除']")):
        return 'already expanded'
    hdr = next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None)
    if hdr is None:
        return 'no group header'
    L.js_click(d, hdr)
    time.sleep(5)
    return 'clicked'


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    open_group()
    OUT['start_live'] = api_live()

    # 1) 软删（若已在上轮软删则跳过）
    b = next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除用例']") if vis(x)), None)
    if b is None:
        OUT['delete_skipped'] = 'no 删除用例 button (already deleted)'
        OUT['after_soft_delete'] = api_trash()
    else:
        L.js_click(d, b)
        time.sleep(1.2)
        L.shot(d, 'd01_delete_confirm')
        OUT['delete_confirm'] = confirm(('删除',))
        time.sleep(3)
        OUT['delete_toast'] = L.wait_toast(d, 15)
        OUT['after_soft_delete'] = api_trash()

    # 2) 回收站视图（保留分组筛选，组内展开）+ 恢复
    reset_filters()
    open_group()
    OUT['trash_switch_fetch'] = click_trash()
    OUT['trash_expand'] = expand_if_needed()
    L.shot(d, 'd02_trash_view')
    OUT['trash_view_text'] = L.body_text(d)[-500:]
    OUT['trash_view_rows'] = len([x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例']") if vis(x)])
    rb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例']") if vis(x)), None), 20)
    L.js_click(d, rb)
    time.sleep(1.2)
    L.shot(d, 'd03_restore_confirm')
    OUT['restore_confirm'] = confirm(('恢复', '确定', '确认'))
    time.sleep(3)
    OUT['restore_toast'] = L.wait_toast(d, 15)
    OUT['after_restore_live'] = api_live()
    OUT['after_restore_trash'] = api_trash()
    L.shot(d, 'd04_after_restore')

    # 3) 再软删
    exit_trash = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                       if vis(b) and (b.text or '').strip() == '回收站'), None)
    if exit_trash is not None:
        L.js_click(d, exit_trash)
        time.sleep(4)
    reset_filters()
    open_group()
    b2 = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除用例']") if vis(x)), None), 20)
    L.js_click(d, b2)
    time.sleep(1.2)
    OUT['delete2_confirm'] = confirm(('删除',))
    time.sleep(3)
    OUT['delete2_toast'] = L.wait_toast(d, 15)
    OUT['after_soft_delete2'] = api_trash()

    # 4) 彻底删除
    reset_filters()
    open_group()
    OUT['trash_switch2_fetch'] = click_trash()
    OUT['trash_expand2'] = expand_if_needed()
    pb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='彻底删除']") if vis(x)), None), 20)
    L.js_click(d, pb)
    time.sleep(1.2)
    L.shot(d, 'd05_purge_confirm')
    OUT['purge_confirm'] = confirm(('彻底删除', '删除', '确定', '确认'))
    time.sleep(4)
    OUT['purge_toast'] = L.wait_toast(d, 15)
    OUT['after_purge_trash'] = api_trash()
    OUT['after_purge_live'] = api_live()
    OUT['after_purge_detail_status'] = L.api_json(d, '/testcases/' + CID)[0]
    L.shot(d, 'd06_after_purge')

    # 5) 导出弹窗（P2 断头复现）
    exit_trash = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                       if vis(b) and (b.text or '').strip() == '回收站'), None)
    if exit_trash is not None:
        L.js_click(d, exit_trash)
        time.sleep(3)
    L.clear_fetch_log(d)
    eb = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                             if (x.text or '').strip() == '导出' and vis(x)), None), 20)
    L.js_click(d, eb)
    dlg = retry(lambda: find_dialog('导出用例'), 20)
    time.sleep(1)
    OUT['export_text'] = (dlg.text or '')[:400]
    L.shot(d, 'e01_export_light')
    for x in dlg.find_elements(By.TAG_NAME, 'button'):
        if (x.text or '').strip() == '开始导出' and vis(x):
            L.js_click(d, x)
            break
    time.sleep(3)
    OUT['export_toasts'] = L.wait_toast(d, 15)
    OUT['export_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status')) for e in L.fetch_log(d)]
    L.apply_theme(d, 'dark')
    L.shot(d, 'e02_export_dark')
    L.apply_theme(d, 'light')
    for x in L.dialogs(d):
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                L.js_click(d, c)
                break
    time.sleep(1)

    # 6) 抽屉五步（A 用例，编辑）
    reset_filters()
    open_group()
    L.clear_fetch_log(d)
    eb = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                             if vis(x) and (x.text or '').strip() == '编辑'), None), 20)
    # 行内「编辑」按钮：卡片上第一个（组头编辑是 '编辑' 同名，用编辑测试用例 aria 优先）
    eb2 = next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']") if vis(x)), None)
    L.js_click(d, eb2 or eb)
    drawer = retry(lambda: next((x for x in L.dialogs(d)
                                 if '测试用例' in (x.text or '') and any(t.text.strip() == '算法参数'
                                                                        for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 25)
    time.sleep(1.5)
    OUT['drawer_open'] = drawer is not None
    OUT['drawer_tabs'] = [(t.text or '').strip() for t in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(t)] if drawer else []
    L.shot(d, 'f01_drawer_step1')
    step_shots = {}
    for i, label in enumerate(['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'], start=1):
        tab = next((t for t in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
                    if vis(t) and (t.text or '').strip() == label), None)
        if tab is None:
            step_shots[label] = 'tab missing'
            continue
        L.js_click(d, tab)
        time.sleep(1.5)
        L.shot(d, 'f%02d_drawer_%s' % (i, label))
        step_shots[label] = (drawer.text or '')[-500:]
        if label == '音频列表':
            # 音频卡播放设备 Select 闭合态
            sel = [e for e in drawer.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                   if vis(e) and ('设备' in (e.text or '') or (e.get_attribute('aria-label') or '').find('播放设备') >= 0)]
            OUT['audio_step_device_selects'] = [(e.text or '').strip()[:60] for e in sel[:6]]
        if label == '噪声与干扰':
            OUT['noise_step_text'] = (drawer.text or '')[-700:]
            OUT['noise_hint_present'] = '演示提示条' in (drawer.text or '')
        if label == '参考参数':
            OUT['ref_step_text'] = (drawer.text or '')[-600:]
            L.clear_fetch_log(d)
            edit_btn = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
                             if vis(b) and '查看/编辑' in (b.text or '')), None)
            if edit_btn is not None:
                L.js_click(d, edit_btn)
                time.sleep(1)
                ta = next((t for t in drawer.find_elements(By.TAG_NAME, 'textarea') if vis(t)), None)
                if ta is not None:
                    ta.send_keys(Keys.CONTROL, 'a')
                    ta.send_keys(Keys.DELETE)
                    ta.send_keys('{"int1643":"probe"}')
                    sv = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').strip() == '保存'), None)
                    if sv is not None:
                        L.js_click(d, sv)
                        time.sleep(2)
                        OUT['ref_save_toasts'] = L.wait_toast(d, 12)
                        OUT['ref_save_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status'))
                                                 for e in L.fetch_log(d)]
            else:
                OUT['ref_edit_btn'] = 'not found (未生成态)'
    OUT['step_texts'] = step_shots
    L.apply_theme(d, 'dark')
    L.shot(d, 'f06_drawer_dark')
    L.apply_theme(d, 'light')
    # 保存抽屉（真实 PUT）后回读参考参数字段
    save_btn = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
                     if vis(b) and (b.text or '').strip() in ('保存', '确定')), None)
    if save_btn is not None:
        L.clear_fetch_log(d)
        L.js_click(d, save_btn)
        time.sleep(4)
        OUT['drawer_save_toasts'] = L.wait_toast(d, 15)
        OUT['drawer_save_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status'),
                                     (e.get('reqBody') or '')[:400]) for e in L.fetch_log(d)]
finally:
    L.save_evidence('recycle_drawer_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
