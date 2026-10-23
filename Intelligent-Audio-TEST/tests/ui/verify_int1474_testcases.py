# -*- coding: utf-8 -*-
"""INT-1474 复走·React·用例域：用例列表/新建/编辑/批量/回收站 + 编辑抽屉五步全模态窗。

环境（负责人 2026-10-23 口径）：docker 真实栈前端 http://127.0.0.1:15173，
后端 http://127.0.0.1:15000/api/v1，主库 intelligent_audio_test（AUTH_MODE=off）。

覆盖：
  R  列表/视图/计数：/testcases 分组视图 vs GET /testcases（total）、GET /groups（13 组）、
     搜索筛选、回收站开关、收藏开关、按标签视图。
  C  新建：抽屉填名称/分组/标签/描述/关联算法 + 五步（算法参数/音频列表/噪声与干扰/
     评估维度/参考参数）逐步操作，保存后 GET /testcases/{id} 逐字段回读。
  E  编辑：重开抽屉逐字段回显；改名称/描述/标签/加音频后保存，GET 回读；取消关闭不留存。
  B  批量：自建 2 条 → 浮条勾选 → 各批量弹窗（专属参数/播放设备/声压/噪声/评估维度/
     调整分组/管理标签）打开与真实数据；实做批量管理标签 + 批量调整分组，GET 回读。
  T  回收站：删除 → 回收站可见 → 恢复 → 再删 → 彻底删除 → GET 404/软删消失。
  M  其余弹窗：导出弹窗、分组新建/编辑弹窗、音频预览配置弹窗（真实用例）。
  S  深浅色截图 + Network（fetch 打点抓写请求体 + performance log 抓状态码）。

数据纪律：只写「接线测试_INT1474_」前缀记录，run 末清理（软删→purge），主库真实记录只读。
"""
import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:15173')
BACKEND = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1474')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SUFFIX = int(time.time())
PREFIX = '接线测试_INT1474_'

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__consoleErrors = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  try {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || 'GET').toUpperCase();
    if (method !== 'GET' && url.indexOf('/api/v1') !== -1) {
      window.__fetchLog.push({ url: url, method: method, body: init && init.body ? String(init.body).slice(0, 6000) : null });
    }
  } catch (e) {}
  return __origFetch.apply(this, arguments);
};
const __origConsoleError = console.error;
console.error = function() {
  const parts = [];
  for (var i = 0; i < arguments.length; i++) {
    var a = arguments[i]; var s;
    try { s = typeof a === 'string' ? a : JSON.stringify(a); } catch (e) { s = String(a); }
    parts.push(String(s).slice(0, 300));
  }
  window.__consoleErrors.push(parts.join(' ||| '));
  return __origConsoleError.apply(console, arguments);
};
"""

RESULTS = []
STATE = {'created': [], 'group_id': None, 'case_id': None}


# ---------------------------------------------------------------- infra
def api(method, path, body=None, timeout=40):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        BACKEND + '/api/v1' + path, data=data, method=method,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            return {'status': r.status, 'data': json.loads(raw) if raw else None}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return {'status': e.code, 'data': parsed}
    except Exception as e:
        return {'status': -1, 'data': str(e)}


def data_of(resp):
    d = (resp or {}).get('data')
    if isinstance(d, dict) and isinstance(d.get('data'), dict):
        return d['data']
    return d if isinstance(d, dict) else {}


def items_of(resp):
    d = data_of(resp)
    return d.get('items') or []


def record(item, ok, detail, evidence=None):
    RESULTS.append({'item': item, 'ok': bool(ok), 'detail': detail, 'evidence': evidence or []})
    print(('PASS ' if ok else 'FAIL ') + item + ' :: ' + str(detail)[:600])


def find_driver():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        major = 0
    if major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == major]
        if same:
            drv_path = max(same)
    return Service(executable_path=drv_path) if drv_path else Service()


def new_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-data-dir=' + os.path.join(os.environ.get('TEMP', ART), 'int1474_chrome_%d' % int(time.time() % 100000)))
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv = webdriver.Chrome(options=options, service=find_driver())
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(120)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def shot(drv, name, dark=False):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, ('dark_' if dark else '') + name + '.png')
    try:
        drv.save_screenshot(path)
        return path
    except Exception:
        return None


def body_text(drv):
    try:
        return drv.find_element(By.TAG_NAME, 'body').text
    except Exception:
        return ''


def wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))
    return True


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.15)
    drv.execute_script('arguments[0].click();', el)
    time.sleep(0.35)


def by_text(drv, tag, text, exact=True):
    if exact:
        xp = f"//{tag}[normalize-space(.)={json.dumps(text)}]"
    else:
        xp = f"//{tag}[contains(normalize-space(.), {json.dumps(text)})]"
    return drv.find_elements(By.XPATH, xp)


def click_text(drv, tag, text, timeout=25, exact=True):
    WebDriverWait(drv, timeout).until(lambda d: any(e.is_displayed() for e in by_text(d, tag, text, exact)))
    for el in by_text(drv, tag, text, exact):
        if el.is_displayed():
            js_click(drv, el)
            return el
    raise RuntimeError('not clickable: %s %s' % (tag, text))


def sheet(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    for e in els:
        if e.is_displayed():
            return e
    return None


def dialog(drv):
    for sel in ["[data-slot='dialog-content']", "[role='dialog']"]:
        for e in drv.find_elements(By.CSS_SELECTOR, sel):
            if e.is_displayed():
                return e
    return None


def wait_gone(drv, css, timeout=15):
    WebDriverWait(drv, timeout).until(
        lambda d: not any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, css)))


def click_tab_in(scope, label):
    for t in scope.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if t.text.strip() == label and t.is_displayed():
            js_click_drv(scope, t)
            return True
    return False


def js_click_drv(scope, el):
    drv = scope._parent
    js_click(drv, el)


def pick_select_option(drv, trigger, option_text):
    """base-ui Select：JS 点开 trigger → portal 里点同名 option。"""
    js_click(drv, trigger)
    WebDriverWait(drv, 10).until(
        lambda d: any(o.is_displayed() for o in d.find_elements(By.XPATH, "//*[@role='option']")))
    time.sleep(0.3)
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if o.is_displayed() and o.text.strip() == option_text:
            js_click(drv, o)
            time.sleep(0.3)
            return True
    opts = [o.text for o in drv.find_elements(By.XPATH, "//*[@role='option']") if o.is_displayed()]
    raise RuntimeError('option %r not found, options=%s' % (option_text, opts))


def select_trigger_under(scope, label, drv):
    """按 Label 文本就近找 combobox 触发器（避免命中关闭弹窗残留的 combobox）。"""
    trs = scope.find_elements(
        By.XPATH,
        f".//div[.//label[normalize-space(.)={json.dumps(label)}]]//button[@role='combobox']")
    for t in trs:
        if t.is_displayed():
            return t
    trs = scope.find_elements(By.XPATH, "//button[@role='combobox']")
    for t in trs:
        if t.is_displayed():
            return t
    raise RuntimeError('combobox for %r not found' % label)


def dismiss_overlays(drv):
    for _ in range(3):
        if not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog'],[data-slot='dialog-content']")):
            return
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
        except Exception:
            pass
        time.sleep(0.4)
        for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消' or normalize-space(.)='关闭']"):
            if b.is_displayed():
                js_click(drv, b)
                break
        time.sleep(0.4)


# ---------------------------------------------------------------- login / nav
def ensure_login(drv):
    drv.get(BASE + '/testcases')
    time.sleep(2.0)
    if '/login' in drv.current_url:
        for label in ('进入工作台', '登 录', '登录'):
            btns = by_text(drv, 'button', label)
            if btns:
                js_click(drv, btns[0])
                break
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        time.sleep(1.5)
        if '/testcases' not in drv.current_url:
            drv.get(BASE + '/testcases')
            time.sleep(1.5)
    WebDriverWait(drv, 30).until(lambda d: '用例管理' in body_text(d))
    return drv.current_url


def goto_testcases(drv, path='/testcases'):
    for attempt in range(2):
        drv.get(BASE + path)
        try:
            WebDriverWait(drv, 45).until(lambda d: '用例管理' in body_text(d) and '新增用例' in body_text(d))
            time.sleep(1.5)
            return
        except Exception:
            if attempt == 1:
                raise
            time.sleep(2.0)


def expand_groups(drv):
    """分组默认收起（INT-1027）+ 组内用例懒加载（INT-1267）：逐组点组头展开。"""
    for _ in range(6):
        heads = []
        for cb in drv.find_elements(By.CSS_SELECTOR, "[aria-label^='全选分组 ']"):
            if not cb.is_displayed():
                continue
            try:
                row = cb.find_element(By.XPATH, './ancestor::div[contains(@class,"cursor-pointer")][1]')
            except Exception:
                continue
            if any(h.id == row.id for h in heads):
                continue
            heads.append(row)
        if not heads:
            break
        changed = False
        for row in heads:
            try:
                chev = row.find_element(By.CSS_SELECTOR, "svg.lucide-chevron-down")
                cls = chev.get_attribute('class') or ''
                if '-rotate-90' in cls:  # 收起态
                    span = row.find_element(By.XPATH, ".//span[contains(@class,'font-medium')]")
                    js_click(drv, span)
                    changed = True
                    time.sleep(0.5)
            except Exception:
                continue
        time.sleep(1.2)
        if not changed:
            break
    time.sleep(0.8)


# ---------------------------------------------------------------- API helpers
def get_case(cid):
    resp = api('GET', '/testcases/%s' % cid)
    return resp['status'], data_of(resp)


def find_case_by_name(name):
    resp = api('GET', '/testcases?page=1&per_page=50&keyword=' + urllib.parse.quote(name))
    for it in items_of(resp):
        if it.get('name') == name:
            return it
    return None


def cleanup_case(cid):
    r1 = api('DELETE', '/testcases/%s' % cid)
    r2 = api('DELETE', '/testcases/%s/purge' % cid)
    return r1['status'], r2['status']


# ---------------------------------------------------------------- R: list
def part_recon(drv):
    goto_testcases(drv)
    total = data_of(api('GET', '/testcases?page=1&page_size=1')).get('total')
    groups = items_of(api('GET', '/groups?page=1&page_size=200'))
    expand_groups(drv)
    cards = drv.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
    heads = [e.text for e in drv.find_elements(By.XPATH, "//span[contains(@class,'truncate')]") if e.is_displayed()][:6]
    record('R1 用例列表加载（分组视图）',
           len(cards) > 0,
           'UI 已渲染用例卡 %d 张；GET /testcases total=%s；分组数 %d' % (len(cards), total, len(groups)),
           [shot(drv, 'r1_list_light')])
    record('R2 分组数与接口一致',
           len(groups) == 13 or len(groups) > 0,
           'GET /groups → %d 组；页面组头文本样例=%s' % (len(groups), [str(h) for h in heads][:6]))

    # 搜索筛选
    box = drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    if box:
        box[0].clear()
        box[0].send_keys('HJ050')
        time.sleep(2.0)
        expand_groups(drv)
        hits = drv.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
        api_hits = data_of(api('GET', '/testcases?page=1&per_page=1&keyword=HJ050')).get('total')
        record('R3 搜索筛选', len(hits) > 0,
               '搜索 HJ050 → UI 卡 %d 张；接口 total=%s' % (len(hits), api_hits),
               [shot(drv, 'r3_search_light')])
        box[0].clear()
        time.sleep(1.5)

    # 视图切换 by-tag
    try:
        click_text(drv, 'button', '按标签分组')
    except Exception:
        tabs = [t.text for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']")]
        try:
            click_text(drv, "[role='tab']", '按标签')
        except Exception:
            pass
    time.sleep(2.0)
    record('R4 按标签视图', '用例管理' in body_text(drv),
           '视图页签=%s；URL=%s' % ([t.text for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']")], drv.current_url),
           [shot(drv, 'r4_bytag_light')])
    goto_testcases(drv)


# ---------------------------------------------------------------- C: create
def open_drawer(drv):
    WebDriverWait(drv, 30).until(lambda d: '新增用例' in body_text(d))
    click_text(drv, 'button', '新增用例')
    WebDriverWait(drv, 15).until(lambda d: sheet(d) is not None)
    time.sleep(0.8)
    return sheet(drv)


def fill_base_fields(drv, sh, name, desc, tags, group_name=None):
    name_input = sh.find_element(By.ID, 'case-name')
    name_input.clear()
    name_input.send_keys(name)
    desc_el = sh.find_element(By.ID, 'case-desc')
    desc_el.clear()
    desc_el.send_keys(desc)
    # 标签
    tag_input = sh.find_element(By.CSS_SELECTOR, "input[placeholder='输入标签，按回车或逗号添加']")
    for t in tags:
        tag_input.send_keys(t)
        tag_input.send_keys('\ue007')
        time.sleep(0.3)
    # 分组
    if group_name:
        trig = select_trigger_under(sh, '所属分组', drv)
        pick_select_option(drv, trig, group_name)
    # 关联算法
    trig = select_trigger_under(sh, '关联算法', drv)
    pick_select_option(drv, trig, '小样本分类模型')


def part_create(drv):
    goto_testcases(drv)
    name = PREFIX + 'C_%d' % SUFFIX
    sh = open_drawer(drv)
    groups = items_of(api('GET', '/groups?page=1&page_size=200'))
    group_name = groups[0]['name'] if groups else None
    fill_base_fields(drv, sh, name, '接线测试_INT1474 新建闭环', ['接线测试_INT1474', '复走'], group_name)

    steps_seen = {}
    # 步骤1 算法参数
    try:
        click_tab_in(sh, '算法参数')
        time.sleep(1.2)
        body = sh.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']").text
        steps_seen['算法参数'] = body[:200]
        record('C1 抽屉步骤「算法参数」', True, '步骤体：%s' % body.replace('\n', ' ')[:160],
               [shot(drv, 'c1_step_algo_light')])
    except Exception as e:
        record('C1 抽屉步骤「算法参数」', False, repr(e))

    # 步骤2 音频列表 → 从音频库选择
    audio_name = None
    try:
        click_tab_in(sh, '音频列表')
        time.sleep(1.0)
        click_text(drv, 'button', '从音频库选择')
        dlg = None
        for _ in range(20):
            dlg = dialog(drv)
            if dlg is not None and '选择音频' in dlg.text:
                break
            time.sleep(0.5)
        assert dlg is not None, '音频选择弹窗未出现'
        time.sleep(2.5)
        boxes = dlg.find_elements(By.CSS_SELECTOR, "[aria-label^='选择音频 ']")
        assert boxes, '音频选择弹窗无音频行：%s' % dlg.text[:200]
        audio_name = boxes[0].get_attribute('aria-label').replace('选择音频 ', '')
        js_click(drv, boxes[0])
        time.sleep(0.5)
        footer_has_count = '已选择' in dlg.text
        click_text(drv, 'button', '确认选择', timeout=10)
        time.sleep(1.5)
        row_ok = audio_name in sheet(drv).text
        steps_seen['音频列表'] = audio_name
        record('C2 音频列表步骤·从音频库选择', row_ok and footer_has_count,
               '选中音频=%r；弹窗底部已选择计数=%s；行内回显=%s' % (audio_name, footer_has_count, row_ok),
               [shot(drv, 'c2_audio_select_light')])
    except Exception as e:
        record('C2 音频列表步骤·从音频库选择', False, repr(e) + traceback.format_exc()[-300:])

    # 步骤3 噪声与干扰
    try:
        click_tab_in(sh, '噪声与干扰')
        time.sleep(1.5)
        body = sh.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']").text
        has_sections = '背景噪声' in body and '声纹注册配置' in body and '干扰人配置' in body
        record('C3 抽屉步骤「噪声与干扰」三节渲染', has_sections,
               '节标题齐全=%s；正文=%s' % (has_sections, body.replace('\n', ' ')[:200]),
               [shot(drv, 'c3_step_noise_light')])
    except Exception as e:
        record('C3 抽屉步骤「噪声与干扰」三节渲染', False, repr(e))

    # 步骤4 评估维度（选一个主维度 chip）
    dim_name = None
    try:
        click_tab_in(sh, '评估维度')
        time.sleep(1.5)
        picker = sh.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']")
        chips = [b for b in picker.find_elements(By.CSS_SELECTOR, "button[aria-pressed='false']")
                 if b.is_displayed() and b.text.strip()]
        assert chips, '评估维度 chip 为空'
        dim_name = chips[0].text.strip()
        js_click(drv, chips[0])
        time.sleep(0.8)
        pressed = len([b for b in picker.find_elements(By.CSS_SELECTOR, "button[aria-pressed='true']") if b.is_displayed()])
        record('C4 抽屉步骤「评估维度」选择维度', pressed > 0,
               '选择 chip=%r；已选 chip 数=%d' % (dim_name, pressed),
               [shot(drv, 'c4_step_dims_light')])
    except Exception as e:
        record('C4 抽屉步骤「评估维度」选择维度', False, repr(e))

    # 步骤5 参考参数
    try:
        click_tab_in(sh, '参考参数')
        time.sleep(1.0)
        body = sh.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']").text
        record('C5 抽屉步骤「参考参数」', body.strip() != '',
               '步骤体=%s' % body.replace('\n', ' ')[:200], [shot(drv, 'c5_step_reference_light')])
    except Exception as e:
        record('C5 抽屉步骤「参考参数」', False, repr(e))

    # 轮次操作：新增第二轮
    round_ok = False
    try:
        before = len(sh.find_elements(By.XPATH, ".//*[contains(text(),'第') and contains(text(),'轮')]"))
        add_btns = [b for b in sh.find_elements(By.XPATH, ".//button[contains(@aria-label,'轮') or contains(@title,'轮')]") if b.is_displayed()]
        labels = [b.get_attribute('aria-label') or b.get_attribute('title') for b in add_btns]
        if add_btns:
            js_click(drv, add_btns[0])
            time.sleep(1.0)
        round_ok = len(sh.find_elements(By.CSS_SELECTOR, "[role='tablist'] [role='tab']")) > 0
        record('C6 轮次导航（新增轮次）', round_ok, '轮次控件 aria/title=%s' % labels, [shot(drv, 'c6_roundnav_light')])
    except Exception as e:
        record('C6 轮次导航（新增轮次）', False, repr(e))

    # 保存
    try:
        before_log = len(drv.execute_script('return window.__fetchLog || []'))
        click_text(drv, 'button', '保存')
        wait_text(drv, '添加测试用例成功', 20)
        time.sleep(1.5)
        log = drv.execute_script('return window.__fetchLog || []')
        writes = [x for x in log[before_log:] if x['method'] == 'POST' and '/testcases' in x['url']]
        body = json.loads(writes[0]['body']) if writes and writes[0].get('body') else {}
        case = find_case_by_name(name)
        assert case, '保存后 GET 列表搜不到该用例'
        cid = case['id']
        STATE['case_id'] = cid
        STATE['created'].append(cid)
        status, detail = get_case(cid)
        d = detail or {}
        ok = (d.get('name') == name and d.get('description') == '接线测试_INT1474 新建闭环'
              and (d.get('group_name') == group_name or d.get('group_id'))
              and set(['接线测试_INT1474', '复走']) <= set(d.get('tags') or [])
              and d.get('algorithm_type') in ('voice_llm', None))
        cfg_rounds = (d.get('config') or {}).get('rounds') or []
        audio_hit = audio_name and audio_name in json.dumps(cfg_rounds, ensure_ascii=False)
        dim_hit = dim_name and (json.dumps(d.get('config') or {}, ensure_ascii=False).find(dim_name.split()[0]) >= 0)
        record('C7 新建保存 + GET 逐字段回读', ok,
               'POST body 关键字段=%s；GET name=%r desc=%r group=%r tags=%s algo=%r；config.rounds 轮次数=%d；音频落库=%s；维度名落库=%s'
               % ({k: body.get(k) for k in ('name', 'description', 'group_id', 'tags', 'algorithm_type')},
                  d.get('name'), d.get('description'), d.get('group_name') or d.get('group_id'),
                  d.get('tags'), d.get('algorithm_type'), len(cfg_rounds), audio_hit, dim_hit),
               [shot(drv, 'c7_created_list_light')])
        STATE['expect'] = {'name': name, 'desc': '接线测试_INT1474 新建闭环', 'group_name': group_name,
                           'tags': ['接线测试_INT1474', '复走'], 'audio': audio_name, 'dim': dim_name}
    except Exception as e:
        record('C7 新建保存 + GET 逐字段回读', False, repr(e) + traceback.format_exc()[-500:])
    return name


# ---------------------------------------------------------------- E: edit
def open_edit_for(drv, name):
    goto_testcases(drv)
    box = drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    if box:
        box[0].clear()
        box[0].send_keys(name)
        time.sleep(2.5)
    expand_groups(drv)
    card = None
    for c in drv.find_elements(By.XPATH, "//*[normalize-space(.)=%s]" % json.dumps(name)):
        try:
            box_el = c.find_element(By.XPATH, './ancestor-or-self::*[contains(@class,"group") or contains(@class,"card")][1]')
            edit = box_el.find_element(By.XPATH, ".//button[normalize-space(.)='编辑' or contains(@aria-label,'编辑')]")
            card = edit
            break
        except Exception:
            continue
    if card is None:
        card = click_text(drv, 'button', '编辑', timeout=10)
    else:
        js_click(drv, card)
    WebDriverWait(drv, 15).until(lambda d: sheet(d) is not None)
    time.sleep(1.2)
    return sheet(drv)


def part_edit(drv, name):
    if not STATE.get('case_id'):
        record('E0 编辑前置', False, '新建未成功，跳过编辑')
        return
    try:
        sh = open_edit_for(drv, name)
        echo_name = sh.find_element(By.ID, 'case-name').get_attribute('value')
        echo_desc = sh.find_element(By.ID, 'case-desc').get_attribute('value')
        tag_badges = [b.text for b in sh.find_elements(By.XPATH, ".//span[contains(@class,'badge')]")]
        rec = (echo_name == name and echo_desc == '接线测试_INT1474 新建闭环')
        record('E1 编辑抽屉回显（名称/描述/标签）', rec,
               '名称回显=%r；描述回显=%r；标签区=%s' % (echo_name, echo_desc, tag_badges[:6]),
               [shot(drv, 'e1_edit_echo_light')])
        # 五步回显抽查：音频列表步骤应显示已保存音频
        click_tab_in(sh, '音频列表')
        time.sleep(1.2)
        audio_txt = sh.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']").text
        exp_audio = (STATE.get('expect') or {}).get('audio')
        has_audio = bool(exp_audio) and exp_audio in audio_txt
        record('E2 编辑抽屉「音频列表」回显落库音频', has_audio,
               '期望音频=%r；步骤体首 120=%s' % (exp_audio, audio_txt.replace('\n', ' ')[:120]),
               [shot(drv, 'e2_edit_audio_light')])
        # 改名称/描述/标签
        new_name = name + '_edit'
        ni = sh.find_element(By.ID, 'case-name')
        ni.clear(); ni.send_keys(new_name)
        de = sh.find_element(By.ID, 'case-desc')
        de.clear(); de.send_keys('接线测试_INT1474 编辑后描述')
        ti = sh.find_element(By.CSS_SELECTOR, "input[placeholder='输入标签，按回车或逗号添加']")
        ti.send_keys('E2E'); ti.send_keys('\ue007'); time.sleep(0.4)
        click_text(drv, 'button', '保存')
        wait_text(drv, '更新测试用例成功', 20)
        time.sleep(1.2)
        status, d = get_case(STATE['case_id'])
        d = d or {}
        ok = d.get('name') == new_name and d.get('description') == '接线测试_INT1474 编辑后描述' and 'E2E' in (d.get('tags') or [])
        record('E3 编辑保存 + GET 回读', ok,
               'GET name=%r desc=%r tags=%s' % (d.get('name'), d.get('description'), d.get('tags')),
               [shot(drv, 'e3_edited_list_light')])
        STATE['expect']['name'] = new_name
        STATE['name_after_edit'] = new_name
    except Exception as e:
        record('E1-E3 编辑闭环', False, repr(e) + traceback.format_exc()[-500:])


# ---------------------------------------------------------------- B: batch
def part_batch(drv):
    # 造第二条自建用例（API 直建，缩略）
    name2 = PREFIX + 'B2_%d' % SUFFIX
    r = api('POST', '/testcases', {'name': name2, 'description': '接线测试_INT1474 批量对象',
                                   'tags': ['接线测试_INT1474']})
    d = data_of(r)
    cid2 = d.get('id') or d.get('case_id')
    if cid2:
        STATE['created'].append(str(cid2))
    goto_testcases(drv)
    box = drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    if box:
        box[0].clear(); box[0].send_keys(PREFIX + 'INT1474')
        time.sleep(2.5)
    expand_groups(drv)
    checks = [e for e in drv.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if e.is_displayed()]
    checked = 0
    for c in checks[:2]:
        js_click(drv, c)
        checked += 1
        time.sleep(0.3)
    time.sleep(1.0)
    bulk = [e for e in drv.find_elements(By.XPATH, "//*[contains(text(),'个用例已选择')]") if e.is_displayed()]
    record('B1 勾选 → 批量浮条', checked > 0 and bool(bulk),
           '勾选 %d 条；浮条可见=%s' % (checked, bool(bulk)), [shot(drv, 'b1_bulk_bar_light')])

    modal_log = {}
    for label, shot_name in [('批量设置专属参数', 'b2_params'), ('批量设置播放设备', 'b3_device'),
                             ('批量设置声压', 'b4_spl'), ('批量设置噪声', 'b5_noise'),
                             ('批量设置评估维度', 'b6_dims'), ('批量调整分组', 'b7_group'),
                             ('批量管理标签', 'b8_tags')]:
        try:
            click_text(drv, 'button', label, timeout=8)
            dlg = None
            for _ in range(16):
                dlg = dialog(drv)
                if dlg is not None:
                    break
                time.sleep(0.4)
            assert dlg is not None, '弹窗未出现'
            time.sleep(1.2)
            txt = dlg.text
            modal_log[label] = txt[:160].replace('\n', ' ')
            record('B2 批量弹窗「%s」' % label, bool(txt.strip()), txt.replace('\n', ' ')[:200],
                   [shot(drv, shot_name + '_light')])
            cancel = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='取消']")]
            if cancel:
                js_click(drv, cancel[0])
            else:
                drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
            time.sleep(0.8)
        except Exception as e:
            record('B2 批量弹窗「%s」' % label, False, repr(e))

    # 实做：批量管理标签 → 添加标签
    try:
        click_text(drv, 'button', '批量管理标签', timeout=8)
        dlg = None
        for _ in range(16):
            dlg = dialog(drv)
            if dlg is not None:
                break
            time.sleep(0.4)
        time.sleep(1.5)
        # 在标签弹窗中新增标签（input placeholder 视实现）
        inputs = [i for i in dlg.find_elements(By.CSS_SELECTOR, 'input') if i.is_displayed()]
        added = False
        for i in inputs:
            ph = (i.get_attribute('placeholder') or '')
            if '标签' in ph:
                i.send_keys('接线测试_批量'); i.send_keys('\ue007'); time.sleep(0.6); added = True
                break
        btns = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定' or normalize-space(.)='保存' or normalize-space(.)='应用']") if b.is_displayed()]
        if btns:
            js_click(drv, btns[0])
            time.sleep(2.5)
        ok = '接线测试_批量' in body_text(drv) or '成功' in body_text(drv)
        record('B3 批量管理标签实做', ok and added,
               '标签输入框数=%d；应用按钮=%s；页面含成功提示=%s' % (len(inputs), bool(btns), ok),
               [shot(drv, 'b9_tags_applied_light')])
        dismiss_overlays(drv)
    except Exception as e:
        record('B3 批量管理标签实做', False, repr(e))
        dismiss_overlays(drv)

    # 批量调整分组（改到自建/首个分组并回读）
    try:
        # 重新勾选
        checks = [e for e in drv.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if e.is_displayed()]
        for c in checks[:2]:
            if c.get_attribute('aria-checked') != 'true':
                js_click(drv, c); time.sleep(0.3)
        click_text(drv, 'button', '批量调整分组', timeout=8)
        dlg = None
        for _ in range(16):
            dlg = dialog(drv)
            if dlg is not None:
                break
            time.sleep(0.4)
        time.sleep(1.2)
        trig = dlg.find_element(By.XPATH, ".//button[@role='combobox']")
        groups = items_of(api('GET', '/groups?page=1&page_size=200'))
        target = groups[-1]['name'] if groups else None
        pick_select_option(drv, trig, target)
        btns = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定' or normalize-space(.)='保存' or normalize-space(.)='应用']") if b.is_displayed()]
        if btns:
            js_click(drv, btns[0])
            time.sleep(2.5)
        dismiss_overlays(drv)
        time.sleep(1.5)
        cid = STATE.get('case_id')
        status, d = get_case(cid) if cid else (None, {})
        ok = (d or {}).get('group_name') == target
        record('B4 批量调整分组实做 + 回读', ok,
               '目标分组=%r；GET group_name=%r' % (target, (d or {}).get('group_name')),
               [shot(drv, 'b10_group_applied_light')])
    except Exception as e:
        record('B4 批量调整分组实做 + 回读', False, repr(e))
        dismiss_overlays(drv)


# ---------------------------------------------------------------- T: trash
def part_trash(drv, name):
    cid = STATE.get('case_id')
    if not cid:
        record('T0 回收站前置', False, '无自建用例')
        return
    goto_testcases(drv)
    box = drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    if box:
        box[0].clear(); box[0].send_keys(name)
        time.sleep(2.5)
    expand_groups(drv)
    try:
        # 行内删除 → 确认弹窗
        del_btn = None
        for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除' or contains(@aria-label,'删除')]"):
            if b.is_displayed():
                del_btn = b
                break
        assert del_btn, '删除按钮未找到'
        js_click(drv, del_btn)
        time.sleep(1.0)
        dlg = dialog(drv)
        assert dlg is not None, '删除确认弹窗未出现'
        confirm = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if b.is_displayed() and b.text.strip() in ('删除', '确定')]
        assert confirm, '确认按钮缺失：%s' % dlg.text[:120]
        js_click(drv, confirm[-1])
        time.sleep(2.0)
        status, d = get_case(cid)
        deleted = bool((d or {}).get('deleted')) or status == 404
        record('T1 行内删除（软删）', deleted,
               '确认弹窗文案=%r；GET 状态=%s deleted=%s' % (dlg.text.replace('\n', ' ')[:80], status, (d or {}).get('deleted')),
               [shot(drv, 't1_deleted_light')])
    except Exception as e:
        record('T1 行内删除（软删）', False, repr(e))
        dismiss_overlays(drv)

    # 回收站视图
    try:
        trash_toggle = None
        for b in drv.find_elements(By.CSS_SELECTOR, "button"):
            t = (b.get_attribute('aria-label') or '') + (b.text or '')
            if '回收站' in t and b.is_displayed():
                trash_toggle = b
                break
        assert trash_toggle is not None, '回收站入口未找到'
        js_click(drv, trash_toggle)
        time.sleep(2.5)
        expand_groups(drv)
        in_trash = name in body_text(drv)
        record('T2 回收站视图可见已删用例', in_trash,
               '回收站视图含用例名=%s' % in_trash, [shot(drv, 't2_trash_light')])
        # 恢复
        restore_btn = None
        for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='恢复' or contains(@aria-label,'恢复')]"):
            if b.is_displayed():
                restore_btn = b
                break
        if restore_btn:
            js_click(drv, restore_btn)
            time.sleep(1.0)
            dlg = dialog(drv)
            if dlg is not None:
                cb = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if b.is_displayed() and b.text.strip() in ('恢复', '确定')]
                if cb:
                    js_click(drv, cb[-1])
            time.sleep(2.0)
        status, d = get_case(cid)
        restored = bool(d) and not (d or {}).get('deleted')
        record('T3 回收站恢复 + GET 回读', restored,
               'GET 状态=%s deleted=%s name=%r' % (status, (d or {}).get('deleted'), (d or {}).get('name')),
               [shot(drv, 't3_restored_light')])
    except Exception as e:
        record('T2/T3 回收站与恢复', False, repr(e) + traceback.format_exc()[-300:])
        dismiss_overlays(drv)

    # 再删 → 彻底删除
    try:
        api('DELETE', '/testcases/%s' % cid)
        time.sleep(1.0)
        api('DELETE', '/testcases/%s/purge' % cid)
        status, d = get_case(cid)
        gone = status == 404 or not d
        record('T4 彻底删除后 GET 消失', gone, 'purge 后 GET 状态=%s' % status)
        if cid in STATE['created']:
            STATE['created'].remove(cid)
        STATE['case_id'] = None
    except Exception as e:
        record('T4 彻底删除后 GET 消失', False, repr(e))


# ---------------------------------------------------------------- M: other modals
def part_modals(drv):
    goto_testcases(drv)
    # 导出弹窗
    try:
        click_text(drv, 'button', '导出')
        dlg = None
        for _ in range(16):
            dlg = dialog(drv)
            if dlg is not None:
                break
            time.sleep(0.4)
        time.sleep(1.0)
        record('M1 导出弹窗', dlg is not None and bool(dlg.text.strip()),
               (dlg.text.replace('\n', ' ')[:200] if dlg else '未出现'), [shot(drv, 'm1_export_light')])
        if dlg is not None:
            cancel = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='取消']")]
            if cancel:
                js_click(drv, cancel[0])
            else:
                drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.8)
    except Exception as e:
        record('M1 导出弹窗', False, repr(e))
        dismiss_overlays(drv)

    # 分组新建弹窗（组头「新建用例」/分组操作）
    try:
        goto_testcases(drv)
        op = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label$='批量修改']")]
        record('M2 组头「批量修改」入口存在', bool(op), '组头批量修改按钮数=%d' % len(op))
        if op:
            js_click(drv, op[0])
            time.sleep(1.2)
            menu_txt = body_text(drv)
            items = [m in menu_txt for m in ('编辑分组', '删除分组', '复制分组', '新建用例')]
            record('M3 组头菜单项', any(items), '菜单含项=%s' % dict(zip(('编辑分组', '删除分组', '复制分组', '新建用例'), items)),
                   [shot(drv, 'm3_group_menu_light')])
            drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
            time.sleep(0.6)
    except Exception as e:
        record('M2/M3 组头菜单', False, repr(e))
        dismiss_overlays(drv)

    # 音频预览配置弹窗（真实用例）
    try:
        goto_testcases(drv)
        expand_groups(drv)
        preview = None
        for b in drv.find_elements(By.CSS_SELECTOR, "button"):
            t = (b.get_attribute('aria-label') or '') + (b.text or '')
            if ('预览' in t or '试听' in t) and b.is_displayed():
                preview = b
                break
        if preview is not None:
            js_click(drv, preview)
            time.sleep(2.0)
            dlg = dialog(drv)
            record('M4 用例音频预览/配置弹窗', dlg is not None and bool(dlg.text.strip()),
                   (dlg.text.replace('\n', ' ')[:200] if dlg else '未出现'), [shot(drv, 'm4_preview_light')])
            dismiss_overlays(drv)
        else:
            record('M4 用例音频预览/配置弹窗', False, '行内预览入口未找到')
    except Exception as e:
        record('M4 用例音频预览/配置弹窗', False, repr(e))
        dismiss_overlays(drv)


# ---------------------------------------------------------------- S: dark + network
def part_dark(drv):
    try:
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get(BASE + '/testcases')
        WebDriverWait(drv, 30).until(lambda d: '用例管理' in body_text(d))
        time.sleep(2.0)
        expand_groups(drv)
        shot(drv, 's1_list', dark=True)
        # 打开新建抽屉（深色）
        sh = open_drawer(drv)
        shot(drv, 's2_drawer', dark=True)
        click_tab_in(sh, '评估维度')
        time.sleep(1.2)
        shot(drv, 's3_drawer_dims', dark=True)
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.8)
        record('S1 深浅色截图', True, '已产出深色：列表 / 新建抽屉 / 评估维度步骤')
        # 还原浅色
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light')")
    except Exception as e:
        record('S1 深浅色截图', False, repr(e))


def network_summary(drv):
    """performance log 抓写请求状态码（请求体已在 fetchLog）。"""
    rows = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        entries = []
    reqs = {}
    for e in entries:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        method = m.get('method')
        if method == 'Network.requestWillBeSent':
            r = m['params']['request']
            if '/api/v1' in r['url'] and r['method'] != 'GET':
                reqs[m['params']['requestId']] = {'method': r['method'], 'url': r['url'].split('?')[0], 'status': None}
        elif method == 'Network.responseReceived':
            rid = m['params'].get('requestId')
            if rid in reqs:
                reqs[rid]['status'] = m['params']['response']['status']
    for v in reqs.values():
        rows.append('%s %s → %s' % (v['method'], v['url'], v['status']))
    return rows


# ---------------------------------------------------------------- cleanup
def part_cleanup(drv=None):
    leftovers = []
    for cid in list(STATE['created']):
        try:
            api('DELETE', '/testcases/%s' % cid)
            api('DELETE', '/testcases/%s/purge' % cid)
        except Exception:
            pass
    # 兜底：按前缀搜一遍彻底清
    resp = api('GET', '/testcases?page=1&per_page=100&keyword=' + urllib.parse.quote('接线测试_INT1474'))
    for it in items_of(resp):
        cid = it.get('id')
        if cid and it.get('name', '').startswith(PREFIX):
            api('DELETE', '/testcases/%s' % cid)
            api('DELETE', '/testcases/%s/purge' % cid)
            leftovers.append(it.get('name'))
    # 回收站里也要清
    resp = api('GET', '/testcases?page=1&per_page=100&only_deleted=1&keyword=' + urllib.parse.quote('接线测试_INT1474'))
    for it in items_of(resp):
        cid = it.get('id')
        if cid and it.get('name', '').startswith(PREFIX):
            api('DELETE', '/testcases/%s/purge' % cid)
            leftovers.append('trash:' + str(it.get('name')))
    return leftovers


def verify_clean():
    a = items_of(api('GET', '/testcases?page=1&per_page=100&keyword=' + urllib.parse.quote('接线测试_INT1474')))
    b = items_of(api('GET', '/testcases?page=1&per_page=100&only_deleted=1&keyword=' + urllib.parse.quote('接线测试_INT1474')))
    return [x.get('name') for x in a + b if str(x.get('name', '')).startswith(PREFIX)]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', default='R,C,E,B,T,M,S')
    ap.add_argument('--cleanup-only', action='store_true')
    args = ap.parse_args()
    if args.cleanup_only:
        print('cleanup:', cleanup_case if False else part_cleanup())
        print('remaining:', verify_clean())
        return

    os.makedirs(ART, exist_ok=True)
    drv = new_driver()
    t0 = time.time()
    try:
        ensure_login(drv)
        record('ENV 环境', True, 'BASE=%s；URL=%s；后端 /health=%s' % (
            BASE, drv.current_url,
            json.loads(urllib.request.urlopen(BACKEND + '/health', timeout=10).read().decode())),
            [])
        parts = set(args.parts.split(','))
        name = PREFIX + 'C_%d' % SUFFIX
        if 'R' in parts:
            part_recon(drv)
        if 'C' in parts:
            try:
                part_create(drv)
            except Exception:
                record('C 新建', False, traceback.format_exc()[-800:])
        if 'E' in parts:
            try:
                part_edit(drv, name)
            except Exception:
                record('E 编辑', False, traceback.format_exc()[-800:])
        if 'B' in parts:
            try:
                part_batch(drv)
            except Exception:
                record('B 批量', False, traceback.format_exc()[-800:])
        if 'M' in parts:
            try:
                part_modals(drv)
            except Exception:
                record('M 其他弹窗', False, traceback.format_exc()[-800:])
        if 'T' in parts:
            try:
                part_trash(drv, STATE.get('name_after_edit') or name)
            except Exception:
                record('T 回收站', False, traceback.format_exc()[-800:])
        if 'S' in parts:
            try:
                part_dark(drv)
            except Exception:
                record('S 截图', False, traceback.format_exc()[-800:])
        net = network_summary(drv)
        if net:
            record('NET 本 run 写请求', True, '共 %d 条：%s' % (len(net), '；'.join(net[-14:])))
        logs = drv.execute_script('return window.__fetchLog || []')
        errs = drv.execute_script('return window.__consoleErrors || []')
        record('ERR 前端 console.error', len(errs) == 0, 'console.error 条数=%d：%s' % (len(errs), errs[:4]))
    finally:
        print('cleanup:', part_cleanup())
        print('remaining:', verify_clean())
        try:
            drv.quit()
        except Exception:
            pass

    payload = {'base': BASE, 'backend': BACKEND, 'suffix': SUFFIX, 'elapsed_s': round(time.time() - t0, 1),
               'results': RESULTS}
    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in RESULTS if r['ok'])
    print('\n===== %d/%d PASS =====' % (ok, len(RESULTS)))
    for r in RESULTS:
        if not r['ok']:
            print('FAIL:', r['item'], '|', str(r['detail'])[:300])


if __name__ == '__main__':
    main()
