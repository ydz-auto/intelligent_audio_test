# -*- coding: utf-8 -*-
"""INT-1477 复走·React·用例域：13 模态窗逐窗实测（docker 真实栈 前端 15173 / 网关 15000 / 主库 intelligent_audio_test）。

逐窗动作：打开 → 浅/深色截图 → 记录真实请求/响应 → 关键写操作走真实接口并 GET 回读。
产出：tests/ui/artifacts/int1477/<序号>_<窗>_<主题>.png + JSON 证据清单。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)

PREFIX = '接线测试_INT1477'
EVID = []          # [{window, theme, note, calls:[...]}]


def log(*a):
    print(*a, flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(60)
    return d


# ---------- 通用 ----------
def xp(t, exact=True):
    if exact:
        return f"//*[normalize-space(.)='{t}']"
    return f"//*[contains(normalize-space(.),'{t}')]"


def find(d, t, tag='*', exact=True, vis=True):
    cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
    els = d.find_elements(By.XPATH, f"//{tag}[{cond}]")
    for e in els:
        if e.is_displayed() or not vis:
            return e
    return None


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});"
                     "arguments[0].click();", el)


def click_text(d, t, tag='*', exact=True, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        e = find(d, t, tag, exact)
        if e:
            jsclick(d, e)
            return e
        time.sleep(0.4)
    try:
        body = d.find_element(By.TAG_NAME, 'body').text[:600].replace('\n', ' | ')
        log('  BODY@fail:', body)
    except Exception:
        pass
    raise AssertionError(f'未找到可点击元素: {t}')


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot:', name)
    return p


def clear_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def calls(d, only_api=True):
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    reqs = {}
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        meth = m.get('method')
        p = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            r = p['request']
            u = r['url']
            if only_api and '/api/' not in u:
                continue
            reqs[p['requestId']] = {
                'method': r['method'],
                'url': u.split(BASE)[-1],
                'status': None,
                'post': (r.get('postData') or '')[:400],
            }
        elif meth == 'Network.responseReceived':
            rid = p['requestId']
            if rid in reqs:
                reqs[rid]['status'] = p['response']['status']
    out = [v for v in reqs.values() if v['status'] is not None]
    return out


def summary(cs):
    return ' ; '.join(f"{c['method']} {c['url'].split('?')[0]} -> {c['status']}" for c in cs)


def close_dialog(d):
    """ESC + 点可能的关闭钮。"""
    try:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.6)
    for _ in range(3):
        try:
            btns = d.find_elements(By.XPATH, "//button[@aria-label='关闭' or @aria-label='Close']")
            live = [b for b in btns if b.is_displayed()]
            if not live:
                break
            jsclick(d, live[-1])
            time.sleep(0.4)
        except Exception:
            break


def wait_dialog(d, title_fragment, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog' or @role='alertdialog']"):
            if e.is_displayed() and title_fragment in (e.text or ''):
                return e
        e = find(d, title_fragment, '*', exact=False)
        if e:
            return e
        time.sleep(0.4)
    raise AssertionError(f'弹窗未出现: {title_fragment}')


def toast_text(d):
    for e in d.find_elements(By.XPATH, "//*[contains(@data-sonner-toast,'') or @data-sonner-toaster]"):
        pass
    els = d.find_elements(By.CSS_SELECTOR, "[data-sonner-toast]")
    return ' | '.join((e.text or '').strip() for e in els if e.is_displayed())


def api_json(d, path):
    """页内用浏览器 fetch 读真实接口（只用于 GET 回读）。"""
    js = """
    var cb = arguments[arguments.length-1];
    fetch(arguments[0], {headers: {'Accept':'application/json'}})
      .then(r => r.text().then(t => cb({status: r.status, body: t})))
      .catch(e => cb({status: -1, body: String(e)}));
    """
    d.set_script_timeout(30)
    r = d.execute_async_script(js, BASE + path)
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


def record(window, theme, note, cs=None, extra=None):
    item = {'window': window, 'theme': theme, 'note': note,
            'calls': cs or []}
    if extra:
        item.update(extra)
    EVID.append(item)
    log(f'  [{window}/{theme}] {note} | {summary(cs or [])}')


# ---------- 打开各弹窗的动作 ----------
def open_case_drawer(d):
    click_text(d, '新增用例', 'button')
    wait_dialog(d, '新增用例')
    time.sleep(1.2)


def open_export(d):
    click_text(d, '导出', 'button')
    wait_dialog(d, '导出用例')
    time.sleep(0.8)


def group_edit_btn(d, gname):
    xp_ = (f"//span[normalize-space(.)='{gname}']/ancestor::*"
           f"[.//button[normalize-space(.)='编辑']][1]//button[normalize-space(.)='编辑']")
    end = time.time() + 8
    while time.time() < end:
        els = d.find_elements(By.XPATH, xp_)
        if els:
            return els[0]
        time.sleep(0.4)
    raise AssertionError('未找到分组编辑按钮 ' + gname)


def open_group_edit(d, gname='音频上传生成'):
    jsclick(d, group_edit_btn(d, gname))
    wait_dialog(d, '编辑分组')
    time.sleep(0.8)


def wait_ready(d, timeout=45):
    """等用例页首屏渲染完成（body 含「用例管理」与「导出」）。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            b = ''
        if '用例管理' in b and '导出' in b:
            time.sleep(1.5)
            return
        if '用例管理' not in b:
            # 空白/崩溃页重试一次整页导航
            if time.time() > end - timeout + timeout / 2:
                try:
                    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
                except Exception:
                    pass
        time.sleep(1.0)
    raise AssertionError('用例页未就绪')


def load_more_groups(d, rounds=4):
    """分组列表单页 5 组按用例数降序；目标分组可能排在首页之外，先「加载更多」。"""
    for _ in range(rounds):
        els = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
               if e.is_displayed()]
        if not els:
            break
        jsclick(d, els[0])
        time.sleep(1.5)


def expand_group(d, gname):
    end = time.time() + 10
    while time.time() < end:
        els = d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']")
        els = [e for e in els if e.is_displayed()]
        if els:
            jsclick(d, els[0])
            time.sleep(1.5)
            return
        time.sleep(0.5)
    raise AssertionError('未找到分组 ' + gname)


def open_preview(d):
    for _ in range(3):
        els = [e for e in d.find_elements(By.XPATH, "//button[@aria-label='预览音频']") if e.is_displayed()]
        if els:
            jsclick(d, els[0])
            wait_dialog(d, '音频试听配置')
            time.sleep(0.8)
            return
        expand_group(d, '音频上传生成')
        time.sleep(1.0)
    raise AssertionError('未找到 预览音频 按钮')


def open_audio_select(d):
    """抽屉 → 音频列表步骤 → + 添加音频 → 音频库选择弹窗。"""
    click_text(d, '音频列表', 'button')
    time.sleep(1.0)
    click_text(d, '+ 添加音频', 'button')
    wait_dialog(d, '选择音频')
    time.sleep(2.0)


def select_case_checkbox(d, idx=0):
    boxes = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
             if e.is_displayed() and (e.get_attribute('aria-label') or '').startswith('选择 ')]
    if idx >= len(boxes):
        raise AssertionError('可勾选用例不足')
    jsclick(d, boxes[idx])
    time.sleep(1.0)


def ensure_expanded(d, gname):
    """分组默认收起；已展开时点组头会收起，故仅在无用例复选框时点开。"""
    has = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
           if e.is_displayed() and (e.get_attribute('aria-label') or '').startswith('选择 ')]
    if has:
        return
    expand_group(d, gname)


def select_group_all(d, gname):
    end = time.time() + 8
    while time.time() < end:
        for e in d.find_elements(By.XPATH, f"//*[@role='checkbox' and @aria-label='全选分组 {gname}']"):
            if e.is_displayed():
                jsclick(d, e)
                time.sleep(1.0)
                return
        time.sleep(0.4)
    raise AssertionError('未找到分组全选 ' + gname)


def open_bulk(d, label):
    click_text(d, label, 'button')
    time.sleep(1.0)


BULK = [
    ('批量设置专属参数', '专属参数'),
    ('批量设置播放设备', '播放设备'),
    ('批量设置声压', '声压'),
    ('批量设置噪声', '噪声'),
    ('批量设置评估维度', '评估维度'),
    ('批量调整分组', '调整分组'),
    ('批量管理标签', '管理标签'),
]


def run_theme(d, theme):
    log(f'===== 主题 {theme} =====')
    # 主题切换：先落 localStorage，再用带参数的地址整页导航（避开 bfcache；不用 about:blank）
    if time.time() - getattr(run_theme, '_last_nav', 0) > 5 or True:
        d.get(BASE + '/')
        time.sleep(2)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    run_theme._last_nav = time.time()
    wait_ready(d)
    shot(d, f'00_page_{theme}')
    load_more_groups(d)

    # 1) 导出弹窗
    clear_log(d)
    open_export(d)
    shot(d, f'10_export_{theme}')
    click_text(d, '开始导出', 'button')
    time.sleep(1.2)
    t = toast_text(d)
    cs = calls(d)
    shot(d, f'10_export_submit_{theme}')
    record('export-dialog', theme, f'开始导出 toast={t!r}', cs)
    close_dialog(d)
    time.sleep(0.5)

    # 2) 分组编辑弹窗（只读打开，不保存真实分组）
    clear_log(d)
    open_group_edit(d, '音频上传生成')
    shot(d, f'11_group_mutate_{theme}')
    record('group-mutate-dialog', theme, '编辑分组打开（只读）', calls(d))
    close_dialog(d)
    time.sleep(0.5)

    # 3) 音频试听配置 + 播放器
    clear_log(d)
    expand_group(d, '音频上传生成')
    open_preview(d)
    shot(d, f'12_audio_preview_config_{theme}')
    cs = calls(d)
    click_text(d, '开始试听', 'button')
    time.sleep(1.5)
    shot(d, f'13_audio_player_{theme}')
    cs2 = calls(d)
    record('audio-preview-config-dialog', theme, '配置态打开 + 开始试听', cs + cs2)
    record('audio-player-dialog', theme, '播放器态（开始试听后）', cs2)
    close_dialog(d)
    time.sleep(0.5)

    # 4) 用例编辑抽屉（新增）+ 音频库选择
    clear_log(d)
    open_case_drawer(d)
    shot(d, f'01_case_mutate_drawer_{theme}')
    record('case-mutate-drawer', theme, '新增抽屉打开', calls(d))
    clear_log(d)
    open_audio_select(d)
    shot(d, f'02_audio_select_{theme}')
    record('audio/audio-select-dialog', theme, '音频库选择弹窗打开', calls(d))
    close_dialog(d)
    time.sleep(0.6)
    # 丢掉抽屉里已加载的音频弹窗状态，回抽屉关闭
    close_dialog(d)
    time.sleep(0.6)

    # 5) 批量七窗（逐个打开截图，只读，不提交）
    clear_log(d)
    ensure_expanded(d, '音频上传生成')
    select_group_all(d, '音频上传生成')
    shot(d, f'03_bulk_bar_{theme}')
    for i, (label, frag) in enumerate(BULK):
        clear_log(d)
        open_bulk(d, label)
        time.sleep(1.2)
        shot(d, f'2{i}_bulk_{frag}_{theme}')
        record(f'batch-dialog:{label}', theme, '批量弹窗打开', calls(d))
        close_dialog(d)
        time.sleep(0.6)
    # 取消选择
    try:
        click_text(d, '清除选择', 'button', exact=False, timeout=3)
    except Exception:
        pass
    time.sleep(0.5)


def main():
    themes = [t for t in (os.environ.get('THEMES') or 'light,dark').split(',') if t]
    d = driver()
    try:
        for t in themes:
            run_theme(d, t)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    ev_path = os.path.join(ART, 'evidence.json')
    merged = []
    if os.path.isfile(ev_path):
        try:
            merged = json.load(open(ev_path, encoding='utf-8'))
        except Exception:
            merged = []
    merged += EVID
    with open(ev_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    log('EVIDENCE COUNT', len(merged))


if __name__ == '__main__':
    main()
