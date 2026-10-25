# -*- coding: utf-8 -*-
"""INT-1538 终审退回补测（round 2）：试听配置/播放器双通道、导出/分组/回收站深色截图。

目标（终审不通过清单）：
- P1-5 试听播放器成功态的解阻归属：实验室播放（POST /audios/{id}/preview）与
  浏览器播放（GET /audios/{id}/stream + <audio crossOrigin>)两条链路的真实失败态取证。
- P3 深色截图补：播放器 / 导出 / 分组 / 回收站。

只读页面，唯一写操作是夹具用例（由本 run 的 mk fixture 脚本创建，run 结束删除）。
"""
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

NAME = os.environ.get('CASE_NAME', '')
GROUP = os.environ.get('CASE_GROUP', '接线测试_INT1538_复走组')
OUT = {'case_name': NAME, 'group': GROUP, 'sections': {}}


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


def shot(name):
    return L.shot(d, name)


def alerts():
    return [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]


def player_time():
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)]
    return els[-1].text.strip() if els else ''


def search_case():
    """关键词搜索不筛分组视图，这里直接用「分组」facet 圈定自建分组。"""
    # 先重置筛选（避免上一轮已选分组导致触发钮文案变化），再按分组圈定
    rst = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '重置'), None)
    if rst:
        L.js_click(d, rst)
        time.sleep(4)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and GROUP in (b.text or '')), None), 20)
    L.js_click(d, opt)
    time.sleep(5)
    # 分组卡默认收起：组头是 div.cursor-pointer（onToggleExpanded），点它展开后再懒加载用例卡
    if not [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)]:
        try:
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
        except Exception:
            pass
        time.sleep(6)


def preview_btn():
    return retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 30)


def open_preview():
    L.js_click(d, preview_btn())
    w = L.wait_dialog(d, '音频试听配置', 25)
    time.sleep(1)
    return w


def close_all_dialogs():
    for _ in range(4):
        ds = L.dialogs(d)
        if not ds:
            return
        closed = False
        for dl in ds:
            for c in dl.find_elements(By.TAG_NAME, 'button'):
                if vis(c) and (c.text or '').strip() in ('取消', '关闭', '返回试听配置'):
                    L.js_click(d, c)
                    time.sleep(0.8)
                    closed = True
                    break
            if closed:
                break
        if not closed:
            break
    try:
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    except Exception:
        pass
    time.sleep(1)


def choose_mode(label_text):
    lab = retry(lambda: next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '%s')]" % label_text) if vis(x)), None), 15)
    L.js_click(d, lab)
    time.sleep(0.6)
    st = d.execute_script("const rs=[...document.querySelectorAll(\"input[name='preview-mode']\")]; return rs.map(r=>({checked:r.checked}))")
    return st


def start_preview():
    b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None), 20)
    L.js_click(d, b)
    time.sleep(1)


def wait_alert(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        a = alerts()
        if a:
            return a
        time.sleep(1)
    return []


def audio_entries():
    out = []
    for e in L.fetch_log(d):
        u = e.get('url') or ''
        if '/audios/' in u and ('/stream' in u or '/preview' in u or '/stop-preview' in u):
            out.append({
                'method': e.get('method'), 'url': u[:120], 'status': e.get('status'),
                'resBody': (e.get('resBody') or '')[:300],
            })
    return out


def browser_logs():
    try:
        return [x.get('message', '')[:300] for x in d.get_log('browser')]
    except Exception:
        return []


d = L.driver()
try:
    for _attempt in range(4):
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
        time.sleep(2)
    time.sleep(2)
    OUT['base'] = L.BASE
    OUT['bundle'] = d.execute_script(
        "return [...document.querySelectorAll('script')].map(s=>s.src).filter(Boolean).join(' ')")

    # ---------- 浅色：试听配置 → 实验室播放失败态 ----------
    search_case()
    OUT['card_found'] = NAME in L.body_text(d)
    w = open_preview()
    OUT['config_text'] = (w.text or '')[:400]
    shot('p01_preview_config_light')

    OUT['mode_radio_lab'] = choose_mode('实验室播放')
    L.clear_fetch_log(d)
    start_preview()
    OUT['lab_stage_title'] = L.dialog_title(d) if hasattr(L, 'dialog_title') else (L.dialogs(d)[-1].text or '')[:80]
    OUT['lab_alerts'] = wait_alert(90)
    OUT['lab_fetch'] = audio_entries()
    OUT['lab_time'] = player_time()
    shot('p02_player_lab_error_light')

    # 返回配置 → 浏览器播放失败态
    back = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and '返回试听配置' in (x.text or '')), None)
    if back:
        L.js_click(d, back)
        time.sleep(1)
    OUT['mode_radio_browser'] = choose_mode('浏览器播放')
    L.clear_fetch_log(d)
    try:
        d.get_log('browser')
    except Exception:
        pass
    start_preview()
    OUT['browser_alerts'] = wait_alert(30)
    time.sleep(2)
    OUT['browser_fetch'] = audio_entries()
    OUT['browser_time'] = player_time()
    OUT['browser_console'] = [x for x in browser_logs() if 'CORS' in x or 'cross-origin' in x.lower() or 'ERR_' in x][:6]
    shot('p03_player_browser_error_light')
    close_all_dialogs()

    # ---------- 浅色：导出弹窗 ----------
    try:
        exp = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '导出'), None), 20)
        L.js_click(d, exp)
        ew = L.wait_dialog(d, '导出用例', 20)
        time.sleep(1)
        OUT['export_text'] = (ew.text or '')[:400]
        shot('p06_export_light')
        L.clear_fetch_log(d)
        sb = next((x for x in ew.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始导出'), None)
        if sb:
            L.js_click(d, sb)
            time.sleep(3)
            OUT['export_toasts'] = L.wait_toast(d, 12)
            OUT['export_fetch'] = [(e.get('method'), (e.get('url') or '')[:90], e.get('status')) for e in L.fetch_log(d) if '/testcases' in (e.get('url') or '')]
        close_all_dialogs()
    except Exception:
        OUT['export_err'] = traceback.format_exc()[-500:]
        close_all_dialogs()

    # ---------- 浅色：分组编辑弹窗 + 回收站视图 ----------
    try:
        # 清空搜索，回到分组视图
        inp = next((e for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']") if vis(e)), None)
        if inp:
            L.js_click(d, inp)
            inp.send_keys(Keys.CONTROL, 'a')
            inp.send_keys(Keys.DELETE)
            time.sleep(5)
        heads = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == GROUP]
        OUT['group_header_buttons'] = len(heads)
        if heads:
            L.js_click(d, heads[0])
            time.sleep(3)
        edit_btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '编辑']
        OUT['group_edit_btns'] = len(edit_btns)
        if edit_btns:
            L.js_click(d, edit_btns[0])
            time.sleep(1.5)
            gw = [x for x in L.dialogs(d) if '分组' in (x.text or '')]
            OUT['group_dialog_text'] = [(x.text or '')[:300] for x in gw]
            shot('p07_group_edit_light')
        close_all_dialogs()
    except Exception:
        OUT['group_err'] = traceback.format_exc()[-500:]
        close_all_dialogs()

    try:
        tb = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '回收站'), None), 15)
        L.js_click(d, tb)
        time.sleep(5)
        OUT['trash_text'] = L.body_text(d)[:300]
        shot('p08_trash_light')
        L.js_click(d, retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '回收站'), None), 15))
        time.sleep(4)
    except Exception:
        OUT['trash_err'] = traceback.format_exc()[-500:]

    # ---------- 深色：同源 reload 后重拍 ----------
    L.apply_theme(d, 'dark')
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    L.apply_theme(d, 'dark')
    OUT['dark_class'] = d.execute_script("return document.documentElement.className")
    OUT['dark_bg'] = d.execute_script("return getComputedStyle(document.body).backgroundColor")
    search_case()
    try:
        w = open_preview()
        shot('p04_preview_config_dark')
        choose_mode('浏览器播放')
        L.clear_fetch_log(d)
        start_preview()
        OUT['dark_browser_alerts'] = wait_alert(30)
        OUT['dark_browser_fetch'] = audio_entries()
        shot('p05_player_browser_error_dark')
        close_all_dialogs()
    except Exception:
        OUT['dark_player_err'] = traceback.format_exc()[-500:]
        close_all_dialogs()

    try:
        exp = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '导出'), None), 20)
        L.js_click(d, exp)
        L.wait_dialog(d, '导出用例', 20)
        time.sleep(1)
        shot('p06b_export_dark')
        close_all_dialogs()
    except Exception:
        OUT['dark_export_err'] = traceback.format_exc()[-500:]
        close_all_dialogs()

    try:
        inp = next((e for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']") if vis(e)), None)
        if inp:
            L.js_click(d, inp)
            inp.send_keys(Keys.CONTROL, 'a')
            inp.send_keys(Keys.DELETE)
            time.sleep(5)
        heads = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == GROUP]
        if heads:
            L.js_click(d, heads[0])
            time.sleep(3)
        edit_btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '编辑']
        if edit_btns:
            L.js_click(d, edit_btns[0])
            time.sleep(1.5)
            shot('p07b_group_edit_dark')
        close_all_dialogs()
        tb = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '回收站'), None), 15)
        L.js_click(d, tb)
        time.sleep(5)
        shot('p08b_trash_dark')
    except Exception:
        OUT['dark_misc_err'] = traceback.format_exc()[-600:]
finally:
    OUT['shots'] = sorted([f for f in os.listdir(L.ART) if f.startswith('p0')])
    L.save_evidence('round2_evidence', OUT)
    with open(os.path.join(L.HERE, 'evidence_int1538_round2.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    try:
        d.quit()
    except Exception:
        pass
