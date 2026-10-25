# -*- coding: utf-8 -*-
"""INT-1538 F：UI 新建用例2（已有音频 + 两轮 + 五步 + 试听播放器真实流）+ 保存回读。"""
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
from selenium.common.exceptions import StaleElementReferenceException

OUT = {'sections': {}}
NAME = '接线测试_INT1538_带音频用例'
GROUP = '接线测试_INT1538_组'


def sec(name):
    def deco(fn):
        t0 = time.time()
        try:
            fn()
            OUT['sections'][name] = {'ok': True, 'dur': round(time.time() - t0, 1)}
        except Exception:
            OUT['sections'][name] = {'ok': False, 'err': traceback.format_exc()[-800:],
                                     'dur': round(time.time() - t0, 1)}
            L.save_evidence('create2_evidence', OUT)
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


def safe(fn, attempts=4, wait=1.0):
    for i in range(attempts):
        try:
            return fn()
        except StaleElementReferenceException:
            time.sleep(wait)
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(wait)
    return None


def drawer():
    ds = [x for x in L.dialogs(d) if ('新增测试用例' in (x.text or '') or '编辑测试用例' in (x.text or ''))]
    return ds[-1] if ds else None


def audio_dlg():
    ds = [x for x in L.dialogs(d) if '选择音频文件' in (x.text or '')]
    return ds[-1] if ds else None


def combos(scope):
    return [c for c in scope.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(c)]


def combo_by_text(scope, needle):
    for c in safe(lambda: combos(scope)) or []:
        if needle in (c.text or ''):
            return c
    return None


def options():
    return [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(o)]


def pick(scope, needle, text=None, index=0):
    trig = retry(lambda: combo_by_text(scope, needle), 30)
    L.js_click(d, trig)
    WebDriverWait(d, 15).until(lambda x: len(options()) > 0)
    time.sleep(0.4)
    opts = options()
    labels = [(o.text or '').strip() for o in opts]
    target = None
    if text:
        for o in opts:
            if text in (o.text or ''):
                target = o
                break
    if target is None:
        target = opts[min(index, len(opts) - 1)]
    L.js_click(d, target)
    time.sleep(0.8)
    return labels


def fill(el, value):
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


def step_tab(label):
    def f():
        db = drawer()
        if db is None:
            return None
        for t in db.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if (t.text or '').strip() == label and vis(t):
                L.js_click(d, t)
                return True
        return None
    retry(f, 15)
    time.sleep(1.2)


def step_body():
    return drawer().find_element(By.CSS_SELECTOR, '[data-testid="case-step-body"]')


def step_text():
    return (safe(lambda: step_body()) or drawer()).text or ''


def btns(scope, text):
    return [b for b in (safe(lambda: scope.find_elements(By.TAG_NAME, 'button')) or []) if text in (b.text or '') and vis(b)]


def search_audio(keyword):
    w = audio_dlg()
    sb = [i for i in w.find_elements(By.TAG_NAME, 'input') if (i.get_attribute('aria-label') or '') == '搜索音频文件名或描述']
    fill(sb[0], keyword)
    end = time.time() + 60
    while time.time() < end:
        w = audio_dlg()
        if w is None:
            return []
        rs = [b for b in w.find_elements(By.CSS_SELECTOR, 'div.max-h-64 > button') if vis(b)]
        if rs:
            return rs
        if '没有匹配的音频文件' in (w.text or ''):
            return []
        time.sleep(2)
    return []


def add_audios(keyword, count):
    L.js_click(d, btns(drawer(), '从音频库选择')[0])
    retry(lambda: audio_dlg(), 30)
    time.sleep(2.5)
    rs = safe(lambda: search_audio(keyword), 3, 1.5) or []
    info = {'keyword': keyword, 'rows': [(b.text or '').split('\n')[0] for b in rs][:8]}
    names = []
    for i in range(min(count, len(rs))):
        def click_row(i=i):
            w = audio_dlg()
            rows = [b for b in w.find_elements(By.CSS_SELECTOR, 'div.max-h-64 > button') if vis(b)]
            if i >= len(rows):
                return None
            nm = (rows[i].text or '').split('\n')[0]
            L.js_click(d, rows[i])
            return nm
        nm = safe(click_row, 4, 0.8)
        if nm:
            names.append(nm)
        time.sleep(0.5)
    info['picked'] = names
    info['footer'] = [t for t in (audio_dlg().text or '').split('\n') if '已选择' in t]
    L.shot(d, 'f_picker_' + keyword)
    for b in audio_dlg().find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '确认选择' and vis(b):
            L.js_click(d, b)
            break
    time.sleep(3)
    retry(lambda: drawer(), 20)
    OUT.setdefault('pickers', []).append(info)
    return info


def select_round(n):
    def f():
        for b in drawer().find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').startswith('第 %d 轮' % n) and vis(b):
                L.js_click(d, b)
                return True
        return None
    retry(f, 10)
    time.sleep(1.2)


def round_labels():
    return [(b.text or '').replace('\n', ' ').strip() for b in drawer().find_elements(By.TAG_NAME, 'button') if '第 ' in (b.text or '')]


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)

    @sec('open_drawer')
    def _():
        btn = WebDriverWait(d, 30).until(lambda x: next((b for b in x.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '新增用例' and vis(b)), None))
        L.js_click(d, btn)
        retry(lambda: drawer(), 25)
        time.sleep(1)

    @sec('basic')
    def _():
        fill(retry(lambda: drawer().find_element(By.ID, 'case-name'), 15), NAME)
        OUT['group_opts'] = pick(drawer(), '请选择分组', GROUP)
        time.sleep(0.8)
        OUT['algo_opts'] = pick(drawer(), '请选择算法', index=0)
        db = drawer()
        tag_input = db.find_element(By.CSS_SELECTOR, "input[placeholder*='输入标签']")
        tag_input.send_keys('接线测试_INT1538')
        tag_input.send_keys(Keys.ENTER)
        time.sleep(0.5)
        fill(drawer().find_element(By.ID, 'case-desc'), 'INT-1538 带音频 + 2 轮用例')
        OUT['combos'] = [(c.text or '').strip() for c in combos(drawer())]
        L.shot(d, 'f01_basic')

    @sec('audio_r1')
    def _():
        step_tab('音频列表')
        time.sleep(1)
        OUT['pick_r1'] = add_audios('HJ05', 2)
        body = step_body()
        cs = combos(body)
        OUT['device_opts'] = pick(body, (cs[0].text or '').strip(), index=0) if cs else []
        nums = [i for i in body.find_elements(By.TAG_NAME, 'input') if vis(i) and (i.get_attribute('type') == 'number')]
        OUT['spl_inputs'] = len(nums)
        if nums:
            fill(nums[0], '72')
        time.sleep(1)
        OUT['r1_cards'] = step_text()[:1200]
        OUT['r1_combo_display'] = [(c.text or '').strip() for c in combos(step_body())]
        L.shot(d, 'f02_r1_audio')

    @sec('preview_player')
    def _():
        L.clear_fetch_log(d)
        b = [x for x in step_body().find_elements(By.CSS_SELECTOR, "button[aria-label='试听']") if vis(x)]
        OUT['preview_btns'] = len(b)
        L.js_click(d, b[0])
        time.sleep(2)
        w = L.wait_dialog(d, '音频试听配置', 20)
        OUT['config_text'] = (w.text or '')[:400]
        L.shot(d, 'f03_preview_config')
        # 浏览器播放（默认前端）
        for x in w.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '开始试听' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(6)
        OUT['player_text_browser'] = (L.wait_dialog(d, '测试用例预览', 20).text or '')[:500]
        L.shot(d, 'f04_player_browser')
        OUT['player_time_browser_1'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(t)]
        # 点播放
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '播放' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(3)
        OUT['player_time_browser_2'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(t)]
        OUT['player_buttons_after_play'] = [(x.text or '').strip() for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() in ('播放', '暂停', '停止')]
        OUT['player_alert'] = [a.text for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
        OUT['stream_fetch'] = [(e.get('method'), e.get('url', '')[:80], e.get('status')) for e in L.fetch_log(d) if '/audios/' in (e.get('url') or '')]
        L.shot(d, 'f05_player_browser_playing')
        # 停止
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '停止' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(1)
        # 返回配置 → 实验室播放
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '返回试听配置' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(1.5)
        for lab in d.find_elements(By.XPATH, "//label[contains(normalize-space(.),'实验室播放')]"):
            if vis(lab):
                L.js_click(d, lab)
                break
        time.sleep(0.6)
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '开始试听' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(2)
        L.clear_fetch_log(d)
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '播放' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(4)
        OUT['player_text_lab'] = (L.wait_dialog(d, '测试用例预览', 10).text or '')[:500]
        OUT['player_time_lab'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(t)]
        OUT['lab_alert'] = [a.text for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
        OUT['preview_fetch'] = [(e.get('method'), e.get('url', '')[:80], e.get('status'), (e.get('resBody') or '')[:160]) for e in L.fetch_log(d) if '/audios/' in (e.get('url') or '')]
        L.shot(d, 'f06_player_lab')
        # 停止 → 返回试听配置 → 取消（只关试听弹窗，不动抽屉）
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '停止' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(1)
        for x in d.find_elements(By.TAG_NAME, 'button'):
            if (x.text or '').strip() == '返回试听配置' and vis(x):
                L.js_click(d, x)
                break
        time.sleep(1.2)
        for x in L.dialogs(d):
            if '测试用例预览' in (x.text or '') or '音频试听配置' in (x.text or ''):
                for c in x.find_elements(By.TAG_NAME, 'button'):
                    if (c.text or '').strip() == '取消' and vis(c):
                        L.js_click(d, c)
                        time.sleep(1)
                        break

    @sec('round2')
    def _():
        if drawer() is None:
            raise RuntimeError('drawer gone after preview')
        L.js_click(d, btns(drawer(), '添加轮次')[0])
        time.sleep(1.5)
        OUT['rounds'] = round_labels()
        select_round(2)
        step_tab('音频列表')
        time.sleep(1)
        OUT['pick_r2'] = add_audios('HJ048', 1)
        OUT['r2_cards'] = step_text()[:700]
        OUT['rounds_after'] = round_labels()
        L.shot(d, 'f07_round2')

    @sec('steps_other')
    def _():
        step_tab('算法参数')
        time.sleep(1.5)
        OUT['algo_text'] = step_text()[:400]
        step_tab('噪声与干扰')
        time.sleep(1)
        OUT['noise_text'] = step_text()[:600]
        b = btns(step_body(), '添加噪声')
        if b:
            L.js_click(d, b[0])
            time.sleep(3)
            OUT['noise_dialog'] = [(x.text or '')[:260] for x in L.dialogs(d) if '选择噪声音频' in (x.text or '')]
            L.shot(d, 'f08_noise_picker')
            for x in [x for x in L.dialogs(d) if '选择噪声音频' in (x.text or '')]:
                for c in x.find_elements(By.TAG_NAME, 'button'):
                    if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                        L.js_click(d, c)
                        time.sleep(1)
                        break
        step_tab('评估维度')
        time.sleep(1)
        OUT['eval_text'] = step_text()[:500]
        step_tab('参考参数')
        time.sleep(1)
        OUT['ref_text'] = step_text()[:500]
        L.shot(d, 'f09_ref')

    @sec('save_readback')
    def _():
        OUT['dialogs'] = [(x.text or '')[:60] for x in L.dialogs(d)]
        L.clear_fetch_log(d)
        L.js_click(d, btns(drawer(), '保存')[0])
        time.sleep(6)
        OUT['toasts'] = L.wait_toast(d, 20)
        OUT['drawer_closed'] = drawer() is None
        OUT['save_fetch'] = [(e.get('method'), e.get('url', '')[:60], e.get('status'), (e.get('reqBody') or '')[:600]) for e in L.fetch_log(d) if '/testcases' in (e.get('url') or '')]
        st, payload, _ = L.api_json(d, '/testcases?page=1&per_page=20&keyword=' + NAME)
        items = ((payload or {}).get('data') or {}).get('items') or []
        hit = [x for x in items if x.get('name') == NAME]
        OUT['list_status'] = st
        OUT['list_hit'] = bool(hit)
        if hit:
            OUT['case_id'] = hit[0]['id']
            st2, det, _ = L.api_json(d, '/testcases/' + str(hit[0]['id']))
            OUT['detail_status'] = st2
            OUT['detail'] = det
        L.shot(d, 'f10_after_save')
finally:
    L.save_evidence('create2_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
