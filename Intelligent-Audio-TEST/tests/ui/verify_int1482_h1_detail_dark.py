# -*- coding: utf-8 -*-
"""INT-1482 补图轮 h1：报告详情域 5 窗（详情/音频/日志选择/日志下载/人工复核）
+ 复核历史抽屉（人工非空 484/387/493、AI 非空 481）——每窗浅色 + 深色各一张。

只补证据缺口（审计打回 P1①②），不重走已通过的功能项；每窗记录打开请求/回读数据作为陪伴证据。
用法：python tests/ui/verify_int1482_h1_detail_dark.py [detail|logs|drawers|all]
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
RES = os.path.join(L.ART, 'h1_all_result.json')


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
        OUT[name + '_error'] = traceback.format_exc()[-1500:]
    OUT[name + '_seconds'] = round(time.time() - t0, 1)
    save()


def set_theme(d, mode):
    """写 localStorage 主题 key 后整页重载（about:blank 打断 bfcache），等到 html class 与目标一致。"""
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s')" % mode)
    url = d.current_url
    if url in ('about:blank', ''):
        url = L.BASE + '/report-center'
    d.get('about:blank')
    d.get(url)
    end = time.time() + 45
    while time.time() < end:
        time.sleep(1.0)
        try:
            cls = d.execute_script("return document.documentElement.className") or ''
        except Exception:
            continue
        if (mode == 'dark') == ('dark' in cls):
            break
    return theme_state(d)


def theme_state(d):
    return {'html_class': d.execute_script("return document.documentElement.className") or '',
            'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}


def assert_theme(d, mode):
    st = theme_state(d)
    if mode == 'dark' and 'dark' not in st['html_class']:
        raise AssertionError('主题未切到 dark: %r' % (st,))
    if mode == 'light' and 'dark' in st['html_class']:
        raise AssertionError('主题未切到 light（html 仍带 dark class）: %r' % (st,))
    return st


def image_stats(path):
    """截图的平均亮度与暗像素占比（用于证明 light/dark 是两张不同主题的图）。"""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    im = im.resize((max(1, im.size[0] // 8), max(1, im.size[1] // 8)))
    px = im.load()
    w, h = im.size
    tot = 0.0
    dark = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            tot += lum
            if lum < 60:
                dark += 1
    n = float(w * h)
    return {'avg_lum': round(tot / n, 1), 'dark_pct': round(100.0 * dark / n, 1)}


def check_shot_theme(path, mode):
    st = image_stats(path)
    if mode == 'light' and not (st['avg_lum'] >= 150 and st['dark_pct'] <= 25):
        raise AssertionError('浅色截图不亮: %s %r' % (os.path.basename(path), st))
    if mode == 'dark' and not (st['avg_lum'] <= 90 and st['dark_pct'] >= 70):
        raise AssertionError('深色截图不暗: %s %r' % (os.path.basename(path), st))
    return st


def open_report(d, rid, timeout=90):
    L.reset_fetch_log(d)
    d.get(L.BASE + '/report/%s' % rid)
    WebDriverWait(d, timeout).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
    end = time.time() + 180
    while time.time() < end:
        if any(b.is_displayed() for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='详情']")):
            time.sleep(1.5)
            return
        time.sleep(3)
    raise AssertionError('用例卡未渲染 rid=%s' % rid)


def filter_by_name(d, name):
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    inp = None
    for i in root.find_elements(By.TAG_NAME, 'input'):
        if (i.get_attribute('placeholder') or '').startswith('输入用例ID'):
            inp = i
            break
    if inp is None:
        raise AssertionError('未找到用例名称输入框')
    d.execute_script("""
      const el = arguments[0], v = arguments[1];
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true}));
    """, inp, name)
    time.sleep(0.8)
    for b in root.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '应用筛选' and b.is_displayed():
            L.js_click(d, b)
            break
    time.sleep(5)
    return len([b for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='详情']") if b.is_displayed()])


def visible_dialogs(d):
    out = []
    for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        try:
            if dl.is_displayed():
                out.append(dl)
        except Exception:
            pass
    return out


def wait_dialog_text(d, needle, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        for dl in visible_dialogs(d):
            try:
                if dl.is_displayed() and needle in (dl.text or ''):
                    time.sleep(1.3)
                    return dl
            except Exception:
                pass
        time.sleep(0.5)
    raise AssertionError('对话框未出现: %s' % needle)


def wait_sheet(d, timeout=30):
    """复核历史抽屉（Sheet）：标题「复核历史 — …」+「共 N 条」；与人工复核弹窗（含「查看复核历史」按钮）区分。"""
    end = time.time() + timeout
    while time.time() < end:
        for dl in visible_dialogs(d):
            try:
                t = dl.text or ''
            except Exception:
                continue
            if '复核历史' in t and '共 ' in t and '条' in t:
                time.sleep(1.2)
                return dl
        time.sleep(0.5)
    raise AssertionError('复核历史抽屉未出现')


def open_case_button(d, label):
    for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % label):
        if b.is_displayed():
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
            time.sleep(0.3)
            L.js_click(d, b)
            return b
    raise AssertionError('按钮未找到: %s' % label)


def close_top(d, times=1):
    for _ in range(times):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.9)


def reqs(d, contains=None, since=0):
    out = []
    for e in L.fetch_log(d, since):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody')
                    if e.get(k) is not None})
    return out


def audio_resource_entries(d):
    try:
        return d.execute_script("""
          return performance.getEntriesByType('resource')
            .filter(e => e.name.indexOf(':9000/') !== -1 || e.name.indexOf('stream') !== -1)
            .map(e => ({name: e.name.slice(0,160), status: e.responseStatus, size: e.transferSize, dur: Math.round(e.duration)}));
        """)
    except Exception:
        return []


CASE_484 = '测试用例_DD001_一次打断-纠正否定型打断'
CASE_387 = '测试用例_DD197_恢复前文-一次插入'
CASE_493_REVIEW = '测试用例_JS007_多轮拒识-非目标人拒识'
CASE_493_LOGS = '测试用例_JS151_多轮拒识'
LOG_REPORT = 566  # 报告 566 / 任务 527：JS151 用例有真实日志文件（其余报告该用例 logs 为空）
CASE_481 = '测试用例_JS151_多轮拒识'


def pass_detail(d, tag):
    """报告 484 用例卡：用例结果详情 / 音频播放 / 人工复核 三窗。"""
    state = {}
    open_report(d, 484)
    state['cards'] = filter_by_name(d, CASE_484)
    state['page'] = {'html_class': d.execute_script("return document.documentElement.className"),
                     'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}
    L.shot(d, 'h1_%s_report_detail' % tag)

    # 用例结果详情
    L.reset_fetch_log(d)
    open_case_button(d, '详情')
    dl = wait_dialog_text(d, '评分指标', timeout=30)
    state['case_detail'] = {'head': (dl.text or '')[:240], 'len': len(dl.text),
                            'has_round': ('轮' in dl.text),
                            'play_btns': len([b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']")])}
    L.shot(d, 'h1_%s_case_detail' % tag)

    # 音频播放 Modal
    plays = [b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']") if b.is_displayed()]
    state['audio'] = {'play_btns': len(plays)}
    if plays:
        L.reset_fetch_log(d)
        d.execute_script("return performance.clearResourceTimings && performance.clearResourceTimings()")
        L.js_click(d, plays[0])
        time.sleep(3)
        adl = visible_dialogs(d)[-1]
        state['audio'].update({'dialog_head': (adl.text or '')[:300],
                               'audio_tag': len(adl.find_elements(By.TAG_NAME, 'audio')),
                               'src': [a.get_attribute('src') for a in adl.find_elements(By.TAG_NAME, 'audio')][:2],
                               'reqs': reqs(d, '/audios'),
                               'resources': audio_resource_entries(d)})
        L.shot(d, 'h1_%s_audio_player' % tag)
        for b in adl.find_elements(By.TAG_NAME, 'button'):
            if '播放' in (b.text or '') and '暂停' not in (b.text or ''):
                L.js_click(d, b)
                break
        time.sleep(2.5)
        state['audio']['after_play'] = (visible_dialogs(d)[-1].text or '')[-220:]
        state['audio']['resources_after'] = audio_resource_entries(d)
        L.shot(d, 'h1_%s_audio_playing' % tag)
        close_top(d)
    close_top(d)

    # 人工复核
    L.reset_fetch_log(d)
    open_case_button(d, '人工复核')
    dl = wait_dialog_text(d, '人工复核', timeout=25)
    state['manual_review'] = {'head': (dl.text or '')[:320],
                              'combos': len(dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")),
                              'textareas': len(dl.find_elements(By.TAG_NAME, 'textarea')),
                              'buttons': [b.text for b in dl.find_elements(By.TAG_NAME, 'button')],
                              'reqs': reqs(d, '/reviews')}
    L.shot(d, 'h1_%s_manual_review' % tag)
    close_top(d)
    return state


def pass_logs(d, tag):
    """报告 566（任务 527）+ 用例 JS151：日志文件选择 / 日志下载进度 两窗。"""
    state = {}
    open_report(d, LOG_REPORT)
    state['cards'] = filter_by_name(d, CASE_493_LOGS)
    state['page'] = {'html_class': d.execute_script("return document.documentElement.className"),
                     'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor")}
    L.reset_fetch_log(d)
    open_case_button(d, '下载日志')
    dl = wait_dialog_text(d, '下载日志', timeout=25)
    # 等文件列表加载完
    end = time.time() + 60
    head = ''
    while time.time() < end:
        head = dl.text or ''
        if '正在加载日志文件' not in head:
            break
        time.sleep(1.5)
    time.sleep(1.5)
    state['log_select'] = {'head': head[:320],
                           'checkboxes': len(dl.find_elements(By.CSS_SELECTOR, "[role='checkbox']")),
                           'reqs': reqs(d, '/logs')}
    L.shot(d, 'h1_%s_log_select' % tag)

    btn = None
    for b in dl.find_elements(By.TAG_NAME, 'button'):
        if '下载所选文件' in (b.text or ''):
            btn = b
            break
    state['log_progress'] = {}
    if btn is None or btn.get_attribute('disabled') is not None:
        state['log_progress']['error'] = '下载按钮缺失或禁用'
        close_top(d)
        return state
    L.reset_fetch_log(d)
    L.js_click(d, btn)
    time.sleep(2)
    L.shot(d, 'h1_%s_log_progress' % tag)
    dls = visible_dialogs(d)
    state['log_progress']['text'] = (dls[-1].text or '')[:300] if dls else ''
    end = time.time() + 120
    done_txt = ''
    while time.time() < end:
        time.sleep(2)
        txt = ' | '.join([(x.text or '')[:220] for x in visible_dialogs(d)])
        if '下载完成' in txt or '失败' in txt or '错误' in txt:
            done_txt = txt
            break
    state['log_progress']['final'] = done_txt[:420]
    state['log_progress']['reqs'] = reqs(d, '/logs')
    L.shot(d, 'h1_%s_log_done' % tag)
    close_top(d, 2)
    return state


def drawer_pass(d, tag, rid, case_name):
    """某用例的复核历史抽屉：人工 Tab + AI Tab 各一张。

    tag 决定主题：**必须在抽屉取证前自己切主题**。旧版把这段跑在主题循环之后，
    主题停在 dark，导致 light/dark 两遍拍出同一张深色图（审计打回 P1）。
    """
    theme = set_theme(d, tag)          # 先切主题并重载页面，再开报告
    theme_pre = assert_theme(d, tag)
    open_report(d, rid)
    n = filter_by_name(d, case_name)
    if not n:
        raise AssertionError('筛选后无用例卡 rid=%s' % rid)
    L.reset_fetch_log(d)
    entry = 'badge'
    badges = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='查看复核明细']") if b.is_displayed()]
    if badges:
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", badges[0])
        L.js_click(d, badges[0])
    else:
        entry = 'review-dialog'
        open_case_button(d, '人工复核')
        dl = wait_dialog_text(d, '人工复核', timeout=25)
        hist = None
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                hist = b
                break
        if hist is None:
            raise AssertionError('无查看复核历史入口')
        L.js_click(d, hist)
    sheet = wait_sheet(d, timeout=30)
    time.sleep(1.5)
    theme_sheet = assert_theme(d, tag)   # 抽屉打开后主题仍必须是目标主题
    state = {'theme': theme_sheet, 'theme_pre': theme_pre, 'entry': entry,
             'head': (sheet.text or '')[:420],
             'reqs': reqs(d, 'review'),
             'tabs': [t.text for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']")],
             'manual_rows': len([x for x in sheet.find_elements(By.CSS_SELECTOR, '.space-y-2 > div') if x.is_displayed()])}
    p_manual = L.shot(d, 'drawer_%s_%s_manual' % (tag, rid))
    state['shot_manual'] = os.path.basename(p_manual)
    state['manual_shot_stats'] = check_shot_theme(p_manual, tag)
    for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if 'AI' in (t.text or ''):
            L.js_click(d, t)
            time.sleep(2.5)
            break
    dls = [s for s in visible_dialogs(d) if '复核历史' in (s.text or '') and '共 ' in (s.text or '')]
    sheet = dls[-1] if dls else sheet
    state['ai_tail'] = (sheet.text or '')[-420:]
    state['ai_rows'] = len([x for x in sheet.find_elements(By.CSS_SELECTOR, '.space-y-2 > div') if x.is_displayed()])
    p_ai = L.shot(d, 'drawer_%s_%s_ai' % (tag, rid))
    state['shot_ai'] = os.path.basename(p_ai)
    state['ai_shot_stats'] = check_shot_theme(p_ai, tag)
    close_top(d, 2)
    return state


def main():
    global RES
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    RES = os.path.join(L.ART, 'h1_%s_result.json' % what)
    d = L.driver()
    try:
        L.login(d)
        OUT['base'] = L.BASE
        for tag in ('light', 'dark'):
            section('theme_' + tag, lambda t=tag: OUT.__setitem__('theme_' + tag, set_theme(d, t)))
            if what in ('all', 'detail'):
                section('detail_' + tag, lambda t=tag: OUT.__setitem__('detail_' + tag, pass_detail(d, t)))
            if what in ('all', 'logs'):
                section('logs_' + tag, lambda t=tag: OUT.__setitem__('logs_' + tag, pass_logs(d, t)))
        if what in ('all', 'drawers'):
            # 报告 493（任务 417）的用例集中不含本任务 5 条复核记录所在的用例（362f8d40 / b512e54b，DB 复核 0 行），
            # 因此人工非空抽屉取 484（task 407，9 条）与 387（task 415，2 条）；AI 非空取 481（task 418，24 条）。
            for rid, case in ((484, CASE_484), (387, CASE_387), (481, CASE_481)):
                for tag in ('light', 'dark'):
                    section('drawer_%s_%s' % (rid, tag), lambda r=rid, c=case, t=tag: OUT.__setitem__(
                        'drawer_%s_%s' % (r, t), drawer_pass(d, t, r, c)))
        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.startswith('h1_') or f.startswith('drawer_')])
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
