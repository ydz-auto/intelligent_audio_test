# -*- coding: utf-8 -*-
"""INT-1482 补图轮 h2：报告中心 3 窗（生成报告 / 生成进度 / 删除确认）+ 统计报表表单，
浅色 + 深色各一张；生成进度用真实任务各生成一份「接线测试_」报告，跑完清理。

用法：python tests/ui/verify_int1482_h2_center_stats_dark.py [all|center|gen|stats|cleanup]
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
RES = os.path.join(L.ART, 'h2_result.json')
CREATED = []


def save():
    try:
        with open(RES, 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


def section(name, fn):
    t0 = time.time()
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1600:]
    OUT[name + '_seconds'] = round(time.time() - t0, 1)
    save()


def set_theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s')" % mode)
    d.refresh()
    end = time.time() + 40
    while time.time() < end:
        time.sleep(1.2)
        try:
            cls = d.execute_script("return document.documentElement.className")
            txt = L.body(d)
        except Exception:
            continue
        if (mode == 'dark') == ('dark' in cls) and '报告' in txt:
            break
    return {'html_class': d.execute_script("return document.documentElement.className"),
            'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}


def visible_dialogs(d):
    out = []
    for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
        try:
            if dl.is_displayed():
                out.append(dl)
        except Exception:
            pass
    return out


def wait_dialog(d, needle, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        for dl in visible_dialogs(d):
            try:
                if needle in (dl.text or ''):
                    time.sleep(1.2)
                    return dl
            except Exception:
                pass
        time.sleep(0.5)
    raise AssertionError('对话框未出现: %s' % needle)


def open_center(d):
    d.get(L.BASE + '/report-center')
    WebDriverWait(d, 90).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(2)


def click_text_button(d, text, root=None):
    root = root or d
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == text and b.is_displayed():
                L.js_click(d, b)
                return b
        except Exception:
            pass
    raise AssertionError('按钮未找到: %s' % text)


def set_input(d, el, value):
    d.execute_script("""
      const el = arguments[0], v = arguments[1];
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true}));
    """, el, value)


def pass_center(d, tag):
    state = {}
    open_center(d)
    state['page'] = {'html_class': d.execute_script("return document.documentElement.className"),
                     'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}
    L.shot(d, 'h2_%s_report_center' % tag)

    # 生成报告弹窗
    click_text_button(d, '生成报告')
    dl = wait_dialog(d, '生成报告')
    tasks = dl.find_elements(By.CSS_SELECTOR, 'li')
    state['generate'] = {'head': (dl.text or '')[:260], 'task_items': len(tasks),
                         'inputs': [i.get_attribute('id') or i.get_attribute('placeholder')
                                    for i in dl.find_elements(By.TAG_NAME, 'input')]}
    L.shot(d, 'h2_%s_generate_dialog' % tag)
    # 校验：不选任务直接提交（按钮应禁用）
    for b in dl.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '生成报告':
            state['generate']['submit_disabled_without_task'] = b.get_attribute('disabled') is not None
            break
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.5)
    for _ in range(3):
        if not visible_dialogs(d):
            break
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)

    # 删除确认
    menu = None
    ops = d.find_elements(By.CSS_SELECTOR, "[aria-label*='报告操作']")
    state['row_action_buttons'] = len(ops)
    state['row_action_displayed'] = [b.is_displayed() for b in ops[:5]]
    state['dialogs_after_esc'] = len(visible_dialogs(d))
    for b in ops:
        if b.is_displayed():
            menu = b
            break
    if menu is None and ops:
        menu = ops[0]
    if menu is None:
        raise AssertionError('行操作菜单未找到')
    state['row_menu_label'] = menu.get_attribute('aria-label')
    L.js_click(d, menu)
    time.sleep(1.2)
    items = [i for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if i.is_displayed()]
    state['menu_items'] = [i.text for i in items]
    target = None
    for i in items:
        if (i.text or '').strip() == '删除':
            target = i
            break
    if target is None:
        raise AssertionError('菜单无「删除」')
    L.js_click(d, target)
    cd = wait_dialog(d, '删除报告', timeout=20)
    state['delete_confirm'] = {'head': (cd.text or '')[:240],
                               'buttons': [b.text for b in cd.find_elements(By.TAG_NAME, 'button')]}
    L.shot(d, 'h2_%s_delete_confirm' % tag)
    # 取消（不删真实报告）
    for b in cd.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '取消':
            L.js_click(d, b)
            break
    time.sleep(1)
    state['after_cancel_dialogs'] = len(visible_dialogs(d))
    return state


def pass_generate(d, tag, task_id, task_hint, name):
    """真实生成一份报告，截进度弹窗（生成中/完成），返回报告 id。"""
    state = {'task_id': task_id}
    open_center(d)
    click_text_button(d, '生成报告')
    dl = wait_dialog(d, '生成报告')
    # 搜索任务
    inp = None
    for i in dl.find_elements(By.TAG_NAME, 'input'):
        if (i.get_attribute('placeholder') or '').startswith('搜索任务'):
            inp = i
            break
    if inp is None:
        raise AssertionError('任务搜索框未找到')
    set_input(d, inp, str(task_id))
    time.sleep(2)
    picked = False
    for li in dl.find_elements(By.CSS_SELECTOR, 'li'):
        if not li.is_displayed():
            continue
        if task_hint in (li.text or ''):
            b = li.find_element(By.TAG_NAME, 'button')
            L.js_click(d, b)
            picked = True
            break
    if not picked:
        raise AssertionError('任务列表中未找到 %s' % task_hint)
    time.sleep(0.8)
    name_inp = None
    for i in dl.find_elements(By.TAG_NAME, 'input'):
        if i.get_attribute('id') == 'report-name':
            name_inp = i
            break
    if name_inp is None:
        raise AssertionError('报告名称输入框未找到')
    set_input(d, name_inp, name)
    time.sleep(0.5)
    state['form_text'] = (dl.text or '')[:200]
    click_text_button(d, '生成报告', root=dl)
    # 进度弹窗
    pd = wait_dialog(d, '正在生成报告', timeout=40)
    L.shot(d, 'h2_%s_progress_generating' % tag)
    state['progress_head'] = (pd.text or '')[:220]
    end = time.time() + 180
    last = ''
    done = False
    while time.time() < end:
        txt = ' | '.join([(x.text or '')[:200] for x in visible_dialogs(d)])
        if txt and txt != last:
            last = txt
        if '生成完成' in txt or '生成失败' in txt or '失败' in txt:
            done = True
            L.shot(d, 'h2_%s_progress_done' % tag)
            state['progress_final'] = txt[:400]
            break
        # 完成后会自动跳详情
        if '/report/' in (d.current_url or '') and 'report-center' not in (d.current_url or ''):
            done = True
            state['progress_final'] = 'auto-navigated: %s' % d.current_url
            break
        time.sleep(2)
    state['done'] = done
    # 完成态点「查看报告」→ 从 URL 取真实报告 id（清理用）
    try:
        for b in visible_dialogs(d)[-1].find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() in ('查看报告', '完成'):
                L.js_click(d, b)
                time.sleep(3)
                break
    except Exception:
        pass
    state['url_after'] = d.current_url
    # 抓报告 id
    rid = None
    try:
        rid = int((d.current_url or '').rstrip('/').split('/')[-1])
    except Exception:
        pass
    state['report_id'] = rid
    if rid:
        CREATED.append(rid)
    # 收尾：关掉可能残留的弹窗
    try:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(1)
    return state


def pass_stats(d, tag):
    state = {}
    d.get(L.BASE + '/report-statistics')
    end = time.time() + 120
    while time.time() < end:
        txt = L.body(d)
        if '报表生成' in txt:
            break
        time.sleep(2)
    time.sleep(1)
    # 切到「报表生成」页签
    for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (t.text or '').strip() == '报表生成' and t.is_displayed():
            L.js_click(d, t)
            break
    time.sleep(2.5)
    state['page'] = {'html_class': d.execute_script("return document.documentElement.className"),
                     'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}
    form_text = ''
    for e in d.find_elements(By.XPATH, "//h4[normalize-space(.)='报表生成']/ancestor::div[1]"):
        form_text = e.text or ''
        break
    state['form_head'] = form_text[:320]
    state['combos'] = len([c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()])
    state['checkboxes'] = len([c for c in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']") if c.is_displayed()])
    L.shot(d, 'h2_%s_stats_report_form' % tag)
    # 报表类型下拉选项数
    combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
    if combos:
        L.js_click(d, combos[0])
        time.sleep(1)
        opts = [o.text for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        state['report_type_options'] = opts
        L.shot(d, 'h2_%s_stats_report_form_options' % tag)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
    return state


def cleanup(d):
    state = {'created': list(CREATED)}
    ids = list(CREATED)
    # 兜底：按名称前缀找（本 run 生成的报告名）
    r = L.api(d, '/reports?search=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1482_%E8%A1%A5%E5%9B%BE&page=1&page_size=50')
    try:
        data = r['json']['data']
        items = data.get('items') or []
        for it in items:
            rid = it.get('id')
            if rid and ('接线测试_INT1482_补图' in (it.get('name') or '')) and rid not in ids:
                ids.append(rid)
    except Exception:
        state['search_error'] = (r.get('text') or '')[:200]
    state['purge'] = []
    for rid in ids:
        a = L.api(d, '/reports/%s' % rid, 'DELETE')
        b = L.api(d, '/reports/%s/purge' % rid, 'DELETE')
        c = L.api(d, '/reports/%s' % rid)
        state['purge'].append({'id': rid, 'soft': a['status'], 'purge': b['status'], 'after_get': c['status']})
    state['attempted'] = ids
    return state


def main():
    global RES
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    RES = os.path.join(L.ART, 'h2_%s_result.json' % what)
    d = L.driver()
    try:
        L.login(d)
        OUT['base'] = L.BASE
        if what in ('all', 'center'):
            for tag in ('light', 'dark'):
                section('theme_' + tag, lambda t=tag: OUT.__setitem__('theme_' + tag, set_theme(d, t)))
                section('center_' + tag, lambda t=tag: OUT.__setitem__('center_' + tag, pass_center(d, t)))
        if what in ('all', 'gen', 'genlight'):
            section('gen_light', lambda: OUT.__setitem__('gen_light', pass_generate(
                d, 'light', 397, '拒识多轮E2E测试任务', '接线测试_INT1482_补图进度_light')))
        if what in ('all', 'gen'):
            section('theme_dark_gen', lambda: OUT.__setitem__('theme_dark_gen', set_theme(d, 'dark')))
            section('gen_dark', lambda: OUT.__setitem__('gen_dark', pass_generate(
                d, 'dark', 398, '拒识场景测试E2E测试任务', '接线测试_INT1482_补图进度_dark')))
        if what in ('all', 'stats'):
            section('theme_light_stats', lambda: OUT.__setitem__('theme_light_stats', set_theme(d, 'light')))
            section('stats_light', lambda: OUT.__setitem__('stats_light', pass_stats(d, 'light')))
            section('theme_dark_stats', lambda: OUT.__setitem__('theme_dark_stats', set_theme(d, 'dark')))
            section('stats_dark', lambda: OUT.__setitem__('stats_dark', pass_stats(d, 'dark')))
        if what in ('all', 'cleanup'):
            section('cleanup', lambda: OUT.__setitem__('cleanup', cleanup(d)))
        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.startswith('h2_')])
        print('DONE')
    finally:
        save()
        try:
            set_theme(d, 'light')
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()
