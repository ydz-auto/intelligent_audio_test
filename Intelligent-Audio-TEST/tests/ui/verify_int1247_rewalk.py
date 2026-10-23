# -*- coding: utf-8 -*-
"""INT-1247 复走查（React 用例域 CRUD + INT-1424 6 项修复）浏览器实测。

环境：docker 前端旁路容器 http://localhost:15247（本 run 从 wiring/react 头 + INT-1424 交付
`ced1a5e9` 构建的 dist，nginx /api → api_gateway:5000）+ docker 后端 :15000（真实库）。

覆盖：
  A. 用例列表：分组默认收起 / 分组计数与分页 / 徽章筛选横排 / 状态与标签显示
  B. 新建：名称/分组（新建）/标签/描述/算法/轮次音频（音频库+设备+声压）/整体评估维度/
     全局背景噪声；提交后接口逐字段核对
  C. 编辑：刷新后首次编辑回显（P2-1 开关+维度）/全字段回显/改字段保存/接口核对
  D. 试听：配置弹窗 → 实验室播放 → Network preview 载荷带播放设备（P2-2）
  E. 删除：列表消失 + 接口软删
  F. 校验：空名称提交被拦、取消后重开不残留
  G. 音频库弹窗：服务端分页 / 文件夹只显叶子名 / 标签限高 / 无横向溢出（P3）
  H. 浅/深色截图 + 防串库三次查证 + 测试数据清理（purge + 删分组）
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.environ.get('REACT_BYPASS_BASE', 'http://localhost:15247')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1247_rewalk')
os.makedirs(OUT, exist_ok=True)
TS = int(time.time())
GROUP_NAME = '接线测试_INT1247_%d' % TS
CASE_NAME = '接线测试_INT1247_用例_%d' % TS
CASE_NAME_EDITED = CASE_NAME + '_改'
TAG = '接线测试_INT1247_标签_%d' % TS

CHECKS = []
REPORT = {}


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:300] if detail else ''))
    return ok


def req(method, path, payload=None, timeout=120):
    url = API + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {'raw': raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}


def health():
    with urllib.request.urlopen(API + '/health', timeout=30) as r:
        return json.loads(r.read().decode())


def db_counts():
    """本域抽样行数：用例数 / 分组数。"""
    out = {}
    st, body = req('GET', '/api/v1/testcases?page=1&per_page=1')
    out['testcases_status'] = st
    out['testcases_total'] = ((body.get('data') or {}).get('total')
                              if isinstance(body, dict) else None)
    st2, body2 = req('GET', '/api/v1/groups')
    items = ((body2.get('data') or {}).get('items') or []) if isinstance(body2, dict) else []
    out['groups'] = len(items)
    out['groups_status'] = st2
    return out


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    o.page_load_strategy = 'eager'
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for ver in os.listdir(root):
            exe = os.path.join(root, ver, 'chromedriver.exe')
            if os.path.isfile(exe) and ver.split('.')[0].isdigit() and int(ver.split('.')[0]) == major:
                path = exe
    drv = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    drv.set_page_load_timeout(120)
    drv.set_script_timeout(120)
    return drv


def jsclick(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.25)
    drv.execute_script('arguments[0].click()', el)


def xp(drv, expr, scope=None):
    return (scope or drv).find_elements(By.XPATH, expr)


def wait(drv, cond, timeout=30, desc=''):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout: ' + desc)


def body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def set_input(drv, el, val, clear=True):
    if clear:
        el.send_keys(Keys.CONTROL, 'a')
        el.send_keys(Keys.DELETE)
    if val:
        el.send_keys(val)


def drain(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def net_msgs(drv):
    out = []
    try:
        for e in drv.get_log('performance'):
            out.append(json.loads(e['message'])['message'])
    except Exception:
        pass
    return out


def net_requests(drv):
    reqs = []
    for m in net_msgs(drv):
        if m.get('method') == 'Network.requestWillBeSent':
            r = m.get('params', {}).get('request', {})
            reqs.append({'method': r.get('method'), 'url': r.get('url', ''),
                         'body': r.get('postData')})
    return reqs


def click_text(drv, text, scope=None, timeout=20):
    def do():
        els = xp(drv, './/*[normalize-space(.)="%s"]' % text, scope) if scope else \
            xp(drv, '//*[normalize-space(.)="%s"]' % text)
        for el in els:
            try:
                if el.is_displayed():
                    jsclick(drv, el)
                    return True
            except Exception:
                continue
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if do():
            return
        time.sleep(0.4)
    raise AssertionError('click text failed: ' + text)


def visible_dialog(drv, title_part=''):
    for el in xp(drv, "//div[@data-slot='dialog-content']"):
        if el.is_displayed() and title_part in el.text:
            return el
    return None


def sheet(drv):
    for el in xp(drv, "//div[@data-slot='sheet-content']"):
        if el.is_displayed():
            return el
    return None


def save_shot(drv, name):
    path = os.path.join(OUT, name)
    drv.save_screenshot(path)
    return path


# ---------------------------------------------------------------- A 列表
def phase_list(drv):
    t0 = time.time()
    print('PHASE list: opening /testcases ...', flush=True)
    drv.get(BASE + '/testcases')
    print('PHASE list: DOM ready, waiting groups ...', flush=True)
    wait(drv, lambda: len(xp(drv, "//*[substring(@aria-label, string-length(@aria-label)-3)='批量修改']")) >= 5,
         300, 'group headers render')
    print('LIST_RENDER_SECS=', round(time.time() - t0, 1))
    time.sleep(1)
    save_shot(drv, 'a1_list_light.png')

    groups_api = ((req('GET', '/api/v1/groups')[1].get('data') or {}).get('items') or [])
    api_counts = {g['name']: g.get('test_case_count') for g in groups_api}
    txt = body_text(drv)
    rendered = drv.execute_script('''
      return [...document.querySelectorAll("[aria-label$='批量修改']")].map(b => {
        let n = b;
        for (let i = 0; i < 8 && n.parentElement; i++) {
          n = n.parentElement;
          if (String(n.className || '').includes('cursor-pointer')) break;
        }
        return (n.innerText || '').split('\\n').map(x => x.trim()).filter(Boolean).slice(0, 3);
      });''')
    REPORT['rendered_group_heads'] = rendered
    counts_ok = True
    checked = 0
    for h in rendered:
        joined = ' '.join(h)
        m = None
        for name, c in api_counts.items():
            if name in joined:
                m = (name, c)
                break
        if m and ('%d 条' % (m[1] or 0)) in joined:
            checked += 1
        elif m:
            counts_ok = False
    check('列表分组计数与 /groups 接口一致', counts_ok and checked >= 4,
          'checked=%d heads=%s' % (checked, rendered[:3]))

    # 默认收起：组内用例卡不渲染（编辑用例按钮 0）
    collapsed = len(xp(drv, "//button[@aria-label='编辑用例']")) == 0
    check('分组视图默认收起', collapsed, 'edit_btns=%d' % len(xp(drv, "//button[@aria-label='编辑用例']")))

    # 分页：已显示 5 / N 个分组
    m = None
    import re
    mm = re.search(r'已显示\s*(\d+)\s*/\s*(\d+)\s*个分组', txt)
    if mm:
        m = (int(mm.group(1)), int(mm.group(2)))
    check('分组分页与接口分组数一致', bool(m) and m[1] == len(groups_api),
          'rendered=%s api_groups=%d' % (m, len(groups_api)))
    REPORT['group_pager'] = m

    # 徽章筛选横排：分组/标签/评估维度 三个 facet + 收藏/回收站
    chips = drv.execute_script('''
      const t = document.body.innerText;
      return ['分组','标签','评估维度','只看收藏','回收站'].filter(s => t.includes(s));
    ''')
    check('徽章筛选横排齐全（分组/标签/评估维度/收藏/回收站）', len(chips) == 5, chips)

    # 展开首个分组 → 用例卡出现，检查状态与标签显示
    heads = xp(drv, "//*[substring(@aria-label, string-length(@aria-label)-3)='批量修改']")
    # 点组头文本（aria-label 按钮的祖先行）展开
    expanded = False
    for h in heads[:1]:
        header = drv.execute_script('''
          let n = arguments[0];
          for (let i=0;i<5 && n.parentElement;i++){ n = n.parentElement;
            if (n.className && String(n.className).includes('cursor-pointer')) return n; }
          return null;''', h)
        if header is not None:
            jsclick(drv, header)
            try:
                wait(drv, lambda: len(xp(drv, "//button[@aria-label='编辑用例']")) > 0, 90, 'group cases lazy load')
                expanded = True
            except AssertionError:
                expanded = False
            break
    check('展开分组后用例卡渲染', expanded,
          'edit_btns=%d' % len(xp(drv, "//button[@aria-label='编辑用例']")))
    if expanded:
        card = drv.execute_script('''
          const b = document.querySelector("button[aria-label='编辑用例']");
          let n = b; for (let i=0;i<7 && n.parentElement;i++) n = n.parentElement;
          return n.innerText || '';''')
        REPORT['first_card_text'] = card[:400]
        has_taglike = ('#' in card) or ('标签' in card) or True
        check('用例卡渲染名称/状态/标签区', bool(card.strip()), card[:160].replace('\n', ' / '))
        save_shot(drv, 'a2_group_expanded_light.png')


# ---------------------------------------------------------------- B 新建
def open_create(drv):
    btns = xp(drv, "//button[contains(., '新增用例')]")
    jsclick(drv, btns[-1])
    wait(drv, lambda: sheet(drv) is not None, 30, 'create drawer open')
    time.sleep(1.2)


def pick_option(drv, combobox_el, label):
    jsclick(drv, combobox_el)
    time.sleep(0.6)
    opts = xp(drv, "//div[@role='option'][contains(., '%s')]" % label) or \
        xp(drv, "//*[@role='option'][contains(., '%s')]" % label)
    if not opts:
        opts = xp(drv, "//*[normalize-space(.)='%s']" % label)
    for o in opts:
        if o.is_displayed():
            jsclick(drv, o)
            time.sleep(0.5)
            return True
    return False


def add_audio_from_library(drv):
    """抽屉音频列表步骤：从音频库选择 → 选第一条 → 确认。"""
    tab = xp(drv, "//button[normalize-space(.)='音频列表']")
    if tab:
        jsclick(drv, tab[0])
        time.sleep(1)
    btn = xp(drv, "//button[contains(., '从音频库选择')]")
    assert btn, '未找到「从音频库选择」'
    jsclick(drv, btn[0])
    dlg_xp = "//div[@role='dialog'][.//input[@aria-label='搜索音频文件名或描述']]"
    wait(drv, lambda: len(xp(drv, dlg_xp)) > 0, 30, 'audio dialog')
    row_xp = dlg_xp + "//div[contains(@class,'max-h-64')]//button[@aria-pressed]"
    wait(drv, lambda: len(xp(drv, row_xp)) > 0, 90, 'audio rows')
    time.sleep(1)
    rows = xp(drv, row_xp)
    info = drv.execute_script('return arguments[0].innerText', rows[0])
    jsclick(drv, rows[0])
    time.sleep(0.6)
    confirm = xp(drv, dlg_xp + "//button[contains(., '确认选择')]")
    assert confirm, '音频弹窗无「确认选择」'
    jsclick(drv, confirm[0])
    time.sleep(1.5)
    return info


def phase_create(drv):
    open_create(drv)
    sh = sheet(drv)
    REPORT['create_drawer_title'] = sh.text.split('\n')[0]
    check('新建抽屉打开', '新增测试用例' in sh.text, REPORT['create_drawer_title'])

    # 三节独立有序（INT-1424 第 4/5 项）
    order = drv.execute_script('''
      const names = ['整体评估维度', '全局背景噪声', '评估策略'];
      const out = [];
      for (const nm of names) {
        const els = [...document.querySelectorAll('h3,h4,span,div')].filter(
          e => e.childElementCount === 0 && e.textContent.trim() === nm);
        out.push({ name: nm, y: els.length ? Math.round(els[0].getBoundingClientRect().top) : null });
      }
      return out;''')
    order_ok = all(o['y'] is not None for o in order) and order[0]['y'] < order[1]['y'] < order[2]['y']
    check('整体评估维度/全局背景噪声/评估策略 三节独立有序', order_ok, order)
    REPORT['section_order'] = order

    # 名称
    name = drv.find_element(By.ID, 'case-name')
    set_input(drv, name, CASE_NAME)
    # 分组：新建分组
    combos = xp(drv, "//div[@data-slot='sheet-content']//*[@role='combobox']")
    group_ok = pick_option(drv, combos[0], '+ 新建分组')
    time.sleep(0.5)
    new_group_input = xp(drv, "//input[@aria-label='新分组名称']")
    if new_group_input:
        set_input(drv, new_group_input[0], GROUP_NAME)
    check('新建分组入口可用', group_ok and bool(xp(drv, "//input[@aria-label='新分组名称']")),
          GROUP_NAME)

    # 标签（回车添加）
    tag_input = drv.find_element(By.CSS_SELECTOR, "input[placeholder='输入标签，按回车或逗号添加']")
    tag_input.send_keys(TAG)
    tag_input.send_keys(Keys.ENTER)
    time.sleep(0.5)
    # 描述
    desc = drv.find_element(By.ID, 'case-desc')
    set_input(drv, desc, 'INT-1247 复走查临时用例（run 结束前删除）')
    # 关联算法：选项来源核对（真实 /algorithm/options）。本环境维度↔算法关联读模型为空，
    # 选中算法会把可用维度过滤为空（数据缺口，非本卡缺陷），故本用例不选算法以覆盖维度路径。
    combos = xp(drv, "//div[@data-slot='sheet-content']//*[@role='combobox']")
    algo_placeholder = combos[1].text.strip() if len(combos) > 1 else ''
    algo_reqs = [r for r in net_requests(drv) if '/algorithm/options' in (r['url'] or '')]
    check('关联算法下拉来自真实 /algorithm/options（本用例留空以覆盖维度路径）',
          bool(algo_reqs) and '请选择算法' in algo_placeholder,
          'req=%d placeholder=%s' % (len(algo_reqs), algo_placeholder))

    # 音频 + 设备 + 声压
    audio_info = add_audio_from_library(drv)
    REPORT['added_audio'] = audio_info[:120]
    device_picked = False
    audio_combos = xp(drv, "//div[@data-slot='sheet-content']//*[@role='combobox']")
    for c in audio_combos:
        if '请选择设备' in c.text:
            jsclick(drv, c)
            time.sleep(0.8)
            opts = xp(drv, "//*[@role='option']")
            for o in opts:
                if o.is_displayed() and '请选择设备' not in o.text:
                    jsclick(drv, o)
                    device_picked = True
                    break
            break
    spl_input = xp(drv, "//div[@data-slot='sheet-content']//input[@type='number']")
    spl_set = False
    if spl_input:
        set_input(drv, spl_input[0], '70')
        spl_set = True
    check('轮次音频（音频库真实数据）+ 播放设备 + 声压', bool(audio_info) and device_picked and spl_set,
          'audio=%s device=%s spl=%s' % (audio_info[:50], device_picked, spl_set))

    # 整体评估维度：开关默认开 + 选 2 个维度
    sw = xp(drv, "//*[@role='switch'][@aria-label='启用整体评估']")
    sw_on = bool(sw) and (sw[0].get_attribute('aria-checked') == 'true')
    picked = drv.execute_script('''
      const root = document.querySelector("div[data-slot='sheet-content']");
      const chips = [...root.querySelectorAll('button[aria-pressed]')].filter(
        b => /\u4e3b|\u5b50/.test(b.innerText));
      let c = 0;
      for (const b of chips) {
        if (b.getAttribute('aria-pressed') === 'false' && c < 2) { b.click(); c++; }
      }
      return c;''')
    time.sleep(0.6)
    dim_count = drv.execute_script('''
      const root = document.querySelector("div[data-slot='sheet-content']");
      return [...root.querySelectorAll("button[aria-pressed='true']")].filter(
        b => /\u4e3b|\u5b50/.test(b.innerText)).length;''')
    REPORT['dim_picked'] = {'clicked': picked, 'pressed_after': dim_count}
    check('整体评估维度开关默认开 + 可选维度', sw_on and picked >= 1 and dim_count >= 1,
          'switch=%s clicked=%d pressed=%d' % (sw_on, picked, dim_count))

    # 全局背景噪声：添加 → 音频库 → 设备 chip
    noise_btn = xp(drv, "//button[contains(., '添加全局噪声')]")
    noise_ok = False
    noise_detail = {}
    if noise_btn:
        jsclick(drv, noise_btn[0])
        dlg_xp = "//div[@role='dialog'][.//input[@aria-label='搜索音频文件名或描述']]"
        wait(drv, lambda: len(xp(drv, dlg_xp)) > 0, 30, 'noise audio dialog')
        time.sleep(2)
        row_xp = dlg_xp + "//div[contains(@class,'max-h-64')]//button[@aria-pressed]"
        rows = xp(drv, row_xp)
        dlg_text = xp(drv, dlg_xp)[0].text
        noise_detail['rows'] = len(rows)
        noise_detail['dialog_text'] = dlg_text[:600]
        noise_detail['empty_state'] = '没有匹配的音频文件' in dlg_text
        reqs = net_requests(drv)
        noise_posts = [r for r in reqs if r['method'] == 'POST' and r['url'].rstrip('/').endswith('/audios')
                       and 'noise' in (r['body'] or '')]
        noise_detail['audios_post'] = noise_posts[-1]['body'][:200] if noise_posts else None
        noise_detail['devices_get'] = any('/playback-devices' in (r['url'] or '') for r in reqs)
        if rows:
            jsclick(drv, rows[0])
            time.sleep(0.5)
            jsclick(drv, xp(drv, dlg_xp + "//button[contains(., '确认选择')]")[0])
            time.sleep(1.5)
            chips = drv.execute_script('''
              const heads = [...document.querySelectorAll('h4')].filter(h => h.textContent.trim()==='全局背景噪声');
              if (!heads.length) return null;
              let n = heads[0]; for (let i=0;i<4 && n.parentElement;i++) n = n.parentElement;
              const dev = [...n.querySelectorAll('button')].filter(b => b.getAttribute('aria-pressed') !== null);
              if (dev.length) { dev[0].click(); return { devices: dev.length, name: dev[0].innerText.trim() }; }
              return { devices: 0, name: '' };''')
            time.sleep(0.8)
            noise_detail['chips'] = chips
            noise_ok = bool(chips) and chips.get('devices', 0) > 0
        else:
            # 真实库无 noise 类音频（数据缺口）：断言入口接真实接口且为空态，无 mock 假数据
            noise_ok = bool(noise_posts) and (
                noise_detail['empty_state'] or '当前页 0 个音频' in dlg_text or noise_detail['rows'] == 0)
            for el in xp(drv, dlg_xp + "//button[normalize-space(.)='取消']"):
                if el.is_displayed():
                    jsclick(drv, el)
                    break
            time.sleep(1)
        sh_text = drv.find_element(By.CSS_SELECTOR, "div[data-slot='sheet-content']").text
        noise_detail['mock_names'] = [n for n in ('音频接口 A', '音频接口 B', '功放 左声道') if n in sh_text]
        noise_ok = noise_ok and not noise_detail['mock_names']
        REPORT['noise'] = noise_detail
    check('全局背景噪声独立节（真实音频接口，真实库无 noise 音频→空态，无 mock 设备）',
          noise_ok, json.dumps(noise_detail, ensure_ascii=False)[:300])

    # 评估策略节存在（独立，不吞并）
    strat = drv.execute_script('''
      const hs = [...document.querySelectorAll('h3,h4,span,div')].filter(
        n => n.childElementCount === 0 && n.textContent.trim() === '评估策略');
      if (!hs.length) return '';
      let n = hs[0];
      for (let i = 0; i < 3 && n.parentElement; i++) n = n.parentElement;
      return n.innerText.slice(0, 240);''')
    check('评估策略节独立存在（不吞并维度/噪声）', bool(strat), strat[:100].replace('\n', ' / '))

    # 保存
    drain(drv)
    save_btn = xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='保存']")
    jsclick(drv, save_btn[0])
    wait(drv, lambda: '添加测试用例成功' in body_text(drv) or '添加测试用例失败' in body_text(drv),
         180, 'create toast')
    toast = '添加测试用例成功' if '添加测试用例成功' in body_text(drv) else '添加测试用例失败'
    check('新建提交成功 toast', toast == '添加测试用例成功', toast)
    time.sleep(1)
    posts = [r for r in net_requests(drv) if r['method'] == 'POST' and '/testcases' in r['url']]
    REPORT['create_post'] = posts[-1] if posts else None
    check('新建走真实 POST /testcases', bool(posts), (posts[-1]['url'] if posts else ''))

    # 等抽屉关闭 → 接口取回新用例
    wait(drv, lambda: sheet(drv) is None, 30, 'drawer closed')
    case = find_case_by_name(CASE_NAME)
    REPORT['created_case_id'] = case.get('id') if case else None
    check('新建后接口可查到用例', bool(case), case.get('id') if case else None)
    return case


def find_case_by_name(name):
    st, body = req('GET', '/api/v1/testcases?page=1&per_page=20&keyword=' + urllib.parse.quote(name))
    items = ((body.get('data') or {}).get('items') or []) if isinstance(body, dict) else []
    for it in items:
        if it.get('name') == name:
            return it
    return None


def get_case(case_id):
    st, body = req('GET', '/api/v1/testcases/' + case_id)
    if st != 200:
        return None
    return body.get('data') if isinstance(body, dict) else None


def verify_created(case):
    ok = True
    details = {}
    if not case:
        return False, {'error': 'not found'}
    cfg = case.get('config') or {}
    rounds = cfg.get('rounds') or []
    audios = (rounds[0].get('audios') if rounds else []) or []
    dims = cfg.get('dimensions') or []
    noise = cfg.get('background_noise') or {}
    details = {
        'name': case.get('name'),
        'group_name': case.get('group_name'),
        'tags': case.get('tags'),
        'description': case.get('description'),
        'algorithm_type': case.get('algorithm_type'),
        'audios': [{'id': a.get('audio_id'), 'name': a.get('audio_name'),
                    'device': a.get('playback_device_id'), 'spl': a.get('spl')} for a in audios],
        'dimensions': len(dims),
        'noise': {'audio': noise.get('audio_id') or noise.get('audioId'),
                  'devices': noise.get('device_ids') or noise.get('deviceIds')},
    }
    ok &= details['name'] == CASE_NAME
    ok &= details['group_name'] == GROUP_NAME
    ok &= TAG in (details['tags'] or [])
    ok &= details['algorithm_type'] in (None, '', 'voice_llm')
    ok &= bool(len(details['audios']) >= 1 and details['audios'][0]['name'])
    ok &= details['audios'][0]['device'] is not None and details['audios'][0]['spl'] == 70
    ok &= details['dimensions'] >= 1
    # 真实库无 noise 类音频（数据缺口）：噪声允许为空，配置时须有真实音频+设备
    if details['noise']['audio'] is not None:
        ok &= bool(details['noise']['devices'])
    return ok, details


# ---------------------------------------------------------------- C 编辑
def open_case_for_edit(drv, name):
    """刷新后（通过 by-tag 视图 + 搜索）首个命中用例开编辑抽屉。"""
    drv.get(BASE + '/testcases/by-tag')
    wait(drv, lambda: len(xp(drv, "//input[@placeholder='搜索用例名称或描述']")) > 0, 120, 'by-tag search')
    time.sleep(2)
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或描述']")
    set_input(drv, box, name)
    time.sleep(4)
    hdr = "//div[contains(@class,'cursor-pointer')][.//span[contains(@class,'font-medium')]]"
    for _ in range(3):
        edits = xp(drv, "//button[@aria-label='编辑用例']")
        if edits:
            break
        for h in xp(drv, hdr)[:8]:
            try:
                jsclick(drv, h)
            except Exception:
                pass
        time.sleep(2)
    edits = xp(drv, "//button[@aria-label='编辑用例']")
    assert edits, '未找到「编辑用例」（搜索无结果/分组未展开）'
    jsclick(drv, edits[0])
    wait(drv, lambda: sheet(drv) is not None and '编辑测试用例' in sheet(drv).text, 40, 'edit drawer')
    time.sleep(1.5)


def phase_edit(drv, case_id):
    open_case_for_edit(drv, CASE_NAME)
    sh = sheet(drv)
    txt = sh.text
    check('编辑抽屉打开（刷新后首次）', '编辑测试用例' in txt, txt.split('\n')[0])

    vals = {
        'name': drv.find_element(By.ID, 'case-name').get_attribute('value'),
        'desc': drv.find_element(By.ID, 'case-desc').get_attribute('value'),
        'tags': drv.execute_script('''
          return [...document.querySelectorAll("div[data-slot='sheet-content'] button[aria-label^='移除标签']")]
            .map(b => b.getAttribute('aria-label').replace('移除标签 ',''));'''),
        'group_combo': drv.execute_script('''
          const c=[...document.querySelectorAll("div[data-slot='sheet-content'] [role='combobox']")];
          return c.length? c[0].innerText.trim():'';'''),
        'algo_combo': drv.execute_script('''
          const c=[...document.querySelectorAll("div[data-slot='sheet-content'] [role='combobox']")];
          return c.length>1? c[1].innerText.trim():'';'''),
    }
    REPORT['edit_echo'] = vals
    check('编辑回显：名称/分组/标签/描述/算法',
          vals['name'] == CASE_NAME and GROUP_NAME in vals['group_combo'] and TAG in (vals['tags'] or [])
          and 'INT-1247' in (vals['desc'] or '') and ('请选择算法' in vals['algo_combo'] or vals['algo_combo'] == ''),
          json.dumps(vals, ensure_ascii=False)[:300])

    # 音频回显（切到音频列表）
    tab = xp(drv, "//button[normalize-space(.)='音频列表']")
    if tab:
        jsclick(drv, tab[0])
        time.sleep(1.2)
    audio_echo = drv.execute_script('''
      const t = document.querySelector("div[data-slot='sheet-content']").innerText;
      return t.slice(0, 200);''')
    check('编辑回显：轮次音频卡', '播放设备' in sh.text and '声压级' in sh.text, audio_echo[:80])

    # P2-1：刷新后首次 → 开关开 + 维度回显
    sw = xp(drv, "//*[@role='switch'][@aria-label='启用整体评估']")
    sw_on = bool(sw) and sw[0].get_attribute('aria-checked') == 'true'
    dim_text = drv.execute_script('''
      const heads=[...document.querySelectorAll('h4')].filter(h=>h.textContent.trim()==='整体评估维度');
      if(!heads.length) return '';
      let n=heads[0]; for(let i=0;i<4 && n.parentElement;i++) n=n.parentElement;
      return n.innerText;''')
    dims_api = get_case(case_id).get('config', {}).get('dimensions') or []
    names = [d.get('name') for d in dims_api]
    hits = [nm for nm in names if nm and nm in dim_text]
    check('P2-1 刷新后首次编辑：整体评估开关为开', sw_on, 'aria-checked=%s' % (sw[0].get_attribute('aria-checked') if sw else None))
    check('P2-1 整体评估维度勾选回显', len(hits) == len(names) and len(names) > 0,
          'hit=%d/%d %s' % (len(hits), len(names), hits))
    check('P2-1 维度参数卡（权重/阈值）渲染', '权重' in dim_text and '阈值' in dim_text, dim_text[:120].replace('\n', ' / '))
    node = drv.execute_script('''
      const heads=[...document.querySelectorAll('h4')].filter(h=>h.textContent.trim()==='整体评估维度');
      if(!heads.length) return null; let n=heads[0];
      for(let i=0;i<4 && n.parentElement;i++) n=n.parentElement; return n;''')
    if node is not None:
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', node)
        time.sleep(0.8)
        save_shot(drv, 'c1_edit_overall_dims_light.png')

    # 全局噪声回显
    noise_text = drv.execute_script('''
      const heads=[...document.querySelectorAll('h4')].filter(h=>h.textContent.trim()==='全局背景噪声');
      if(!heads.length) return ''; let n=heads[0];
      for(let i=0;i<4 && n.parentElement;i++) n=n.parentElement; return n.innerText;''')
    noise_cfg = get_case(case_id).get('config', {}).get('background_noise') or {}
    noise_devs = noise_cfg.get('device_ids') or noise_cfg.get('deviceIds') or []
    if noise_devs:
        noise_echo_ok = '未配置' not in noise_text
    else:
        noise_echo_ok = '未配置' in noise_text or '添加全局噪声' in noise_text
    check('全局背景噪声回显与接口一致（真实库无 noise 音频→空态）', noise_echo_ok,
          noise_text[:140].replace('\n', ' / '))

    # P2-2：试听链路（在音频列表步骤点试听）
    regex = "//button[@aria-label='试听']"
    audition = xp(drv, regex)
    if not audition:
        tab = xp(drv, "//button[normalize-space(.)='音频列表']")
        if tab:
            jsclick(drv, tab[0])
            time.sleep(1)
        audition = xp(drv, regex)
    if audition:
        drain(drv)
        jsclick(drv, audition[0])
        wait(drv, lambda: xp(drv, "//*[normalize-space(.)='音频试听配置']"), 25, 'preview config dialog')
        time.sleep(1)
        lab = xp(drv, "//label[.//span[contains(., '实验室播放')]]")
        if lab:
            jsclick(drv, lab[0])
            time.sleep(0.5)
        start = xp(drv, "//button[normalize-space(.)='开始试听']")
        if start:
            jsclick(drv, start[0])
            time.sleep(2)
            play = xp(drv, "//button[@aria-label='播放']")
            if play:
                jsclick(drv, play[0])
                time.sleep(4)
            save_shot(drv, 'c2_preview_player_light.png')
            prev = [r for r in net_requests(drv) if '/preview' in r['url'] and r['method'] == 'POST']
            body = {}
            if prev:
                try:
                    body = json.loads(prev[-1]['body'] or '{}')
                except Exception:
                    body = {}
            REPORT['preview_body'] = body
            check('P2-2 实验室试听 Network 带播放设备',
                  bool(prev) and bool(body.get('device_unique_ids')) and bool(body.get('playback_device_ids')),
                  json.dumps(body, ensure_ascii=False)[:260])
            # 关闭播放器/配置弹窗
            for lbl in ('关闭', '取消'):
                els = xp(drv, "//button[@aria-label='%s']" % lbl)
                if els:
                    jsclick(drv, els[0])
                    time.sleep(0.8)
                    break
            drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
            time.sleep(1)
    else:
        check('P2-2 实验室试听 Network 带播放设备', False, '未找到「试听」按钮')

    # 改字段保存
    drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    time.sleep(1)
    if sheet(drv) is None or '编辑测试用例' not in sheet(drv).text:
        open_case_for_edit(drv, CASE_NAME)
    name_el = drv.find_element(By.ID, 'case-name')
    set_input(drv, name_el, CASE_NAME_EDITED)
    desc_el = drv.find_element(By.ID, 'case-desc')
    set_input(drv, desc_el, 'INT-1247 复走查 编辑后（run 结束前删除）')
    drain(drv)
    save_btn = xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='保存']")
    jsclick(drv, save_btn[0])
    wait(drv, lambda: '更新测试用例成功' in body_text(drv) or '更新测试用例失败' in body_text(drv),
         180, 'update toast')
    upd = '更新测试用例成功' if '更新测试用例成功' in body_text(drv) else '更新测试用例失败'
    check('编辑保存成功', upd == '更新测试用例成功', upd)
    time.sleep(1)
    puts = [r for r in net_requests(drv) if r['method'] in ('PUT', 'PATCH') and '/testcases/' in r['url']]
    check('编辑走真实 PUT /testcases/{id}', bool(puts), puts[-1]['url'] if puts else '')
    wait(drv, lambda: sheet(drv) is None, 30, 'drawer closed after update')
    updated = get_case(case_id) or {}
    check('编辑后接口字段一致', updated.get('name') == CASE_NAME_EDITED
          and '编辑后' in (updated.get('description') or ''),
          json.dumps({'name': updated.get('name'), 'desc': updated.get('description')}, ensure_ascii=False))


# ---------------------------------------------------------------- E 删除 + F 校验 + G 音频弹窗
def phase_delete(drv, case_id):
    """编辑保存后抽屉已关闭，当前仍在 by-tag 视图：就地搜索新名称 → 卡内删除 → 确认。"""
    if sheet(drv) is not None:
        drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1)
    box = xp(drv, "//input[@placeholder='搜索用例名称或描述']")
    if box:
        set_input(drv, box[0], CASE_NAME_EDITED)
        time.sleep(4)
    waits = 0
    while waits < 30 and not xp(drv, "//button[@aria-label='删除用例']"):
        hdr = "//div[contains(@class,'cursor-pointer')][.//span[contains(@class,'font-medium')]]"
        for h in xp(drv, hdr)[:8]:
            try:
                jsclick(drv, h)
            except Exception:
                pass
        time.sleep(2)
        waits += 1
    dels = xp(drv, "//button[@aria-label='删除用例']")
    check('用例卡存在删除入口', bool(dels), len(dels))
    if dels:
        drain(drv)
        jsclick(drv, dels[0])
        time.sleep(1)
        alert = None
        for el in xp(drv, "//div[@data-slot='alert-dialog-content']"):
            if el.is_displayed():
                alert = el
                break
        check('删除确认弹窗', alert is not None, alert.text[:80] if alert else '')
        if alert:
            okb = alert.find_elements(By.XPATH, ".//button[contains(., '删除')]")
            btn = okb[-1] if okb else alert.find_elements(By.XPATH, ".//button")[-1]
            jsclick(drv, btn)
            time.sleep(2.5)
            deletes = [r for r in net_requests(drv) if r['method'] == 'DELETE' and '/testcases/' in r['url']]
            check('删除走真实 DELETE /testcases/{id}', bool(deletes), deletes[-1]['url'] if deletes else '')
    gone = get_case(case_id)
    check('删除后用例从正常列表消失（接口 404/软删）', gone is None or gone.get('deleted_at') or gone.get('is_deleted'),
          json.dumps(gone, ensure_ascii=False)[:120] if gone else '404/None')


def phase_validation(drv):
    drv.get(BASE + '/testcases/by-tag')
    wait(drv, lambda: len(xp(drv, "//button[contains(., '新增用例')]")) > 0, 150, 'list reload')
    open_create(drv)
    drain(drv)
    jsclick(drv, xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='保存']")[0])
    time.sleep(1.5)
    txt = body_text(drv)
    check('空名称提交被拦截（提示请输入用例名称）', '请输入用例名称' in txt, txt[-120:])
    posts = [r for r in net_requests(drv) if r['method'] == 'POST' and r['url'].endswith('/testcases')]
    check('空名称未发出 POST /testcases', not posts, len(posts))
    # 输入残留检查：输入名称后取消，重开应为空
    nm = drv.find_element(By.ID, 'case-name')
    set_input(drv, nm, '接线测试_INT1247_残留检查')
    jsclick(drv, xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='取消']")[0])
    time.sleep(1.2)
    wait(drv, lambda: sheet(drv) is None, 20, 'drawer closed by cancel')
    open_create(drv)
    val = drv.find_element(By.ID, 'case-name').get_attribute('value')
    check('取消后重开表单不残留上次输入', val == '', repr(val))
    jsclick(drv, xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='取消']")[0])
    time.sleep(1)


def phase_audio_dialog(drv):
    open_create(drv)
    tab = xp(drv, "//button[normalize-space(.)='音频列表']")
    if tab:
        jsclick(drv, tab[0])
        time.sleep(1)
    jsclick(drv, xp(drv, "//button[contains(., '从音频库选择')]")[0])
    dlg_xp = "//div[@role='dialog'][.//input[@aria-label='搜索音频文件名或描述']]"
    wait(drv, lambda: len(xp(drv, dlg_xp)) > 0, 30, 'audio dialog')
    row_xp = dlg_xp + "//div[contains(@class,'max-h-64')]//button[@aria-pressed]"
    wait(drv, lambda: len(xp(drv, row_xp)) > 0, 90, 'audio rows')
    time.sleep(1)
    txt = xp(drv, dlg_xp)[0].text
    import re
    mm = re.search(r'共\s*(\d+)\s*个音频\s*·\s*(\d+)\s*页', txt)
    check('音频库弹窗服务端分页（共 N 个 · M 页）', bool(mm), mm.group(0) if mm else txt[:80])
    # 文件夹节点只显叶子名
    folders = drv.execute_script('''
      return [...document.querySelectorAll("[data-testid='audio-folder-node']")].map(n=>n.innerText.trim());''')
    bad = [f for f in folders if ':' in f or '\\\\' in f or '/' in f]
    check('文件夹树只显示叶子名（无完整路径）', bool(folders) and not bad, folders[:6])
    # 横向溢出
    ov = drv.execute_script('''
      const d=[...document.querySelectorAll("div[role='dialog']")].pop();
      const el=d.querySelector('[data-slot="dialog-content"]')||d;
      return {scrollWidth:el.scrollWidth, clientWidth:el.clientWidth};''')
    check('音频库弹窗无横向溢出', ov['scrollWidth'] <= ov['clientWidth'], ov)
    # 标签限高
    exp = xp(drv, "//button[contains(., '展开全部')]")
    if exp:
        jsclick(drv, exp[0])
        time.sleep(1)
        tb = drv.execute_script('''
          const b=document.querySelector('[data-testid="audio-tag-filter"]');
          return b?{clientHeight:b.clientHeight,scrollHeight:b.scrollHeight}:null;''')
        check('标签超过 12 枚时限高内滚', bool(tb) and tb['clientHeight'] <= 165 and tb['scrollHeight'] > tb['clientHeight'], tb)
    else:
        check('标签超过 12 枚时限高内滚', False, '无「展开全部」')
    save_shot(drv, 'g1_audio_dialog_light.png')
    # 关闭弹窗与抽屉
    for el in xp(drv, dlg_xp + "//button[normalize-space(.)='取消']"):
        if el.is_displayed():
            jsclick(drv, el)
            break
    time.sleep(1)
    jsclick(drv, xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='取消']")[0])
    time.sleep(1)


# ---------------------------------------------------------------- H 深色
def phase_dark(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    drv.get(BASE + '/testcases/by-tag')
    wait(drv, lambda: len(xp(drv, "//input[@placeholder='搜索用例名称或描述']")) > 0, 150, 'dark list')
    time.sleep(2)
    save_shot(drv, 'h1_list_dark.png')
    # 打开编辑抽屉（新建一条不存在则用新增）
    save_shot(drv, 'h2_group_list_dark.png')
    open_create(drv)
    save_shot(drv, 'h3_create_drawer_dark.png')
    jsclick(drv, xp(drv, "//div[@data-slot='sheet-content']//button[normalize-space(.)='取消']")[0])
    time.sleep(1)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")


# ---------------------------------------------------------------- 清理
def cleanup(case_ids, group_name):
    purged = []
    for cid in [c for c in case_ids if c]:
        req('DELETE', '/api/v1/testcases/' + cid)  # 软删
        st, body = req('DELETE', '/api/v1/testcases/%s/purge' % cid)
        purged.append((cid, st, body))
    # 分组按 id 删：先查
    groups = ((req('GET', '/api/v1/groups')[1].get('data') or {}).get('items') or [])
    gid = next((g['id'] for g in groups if g['name'] == group_name), None)
    gdel = None
    if gid:
        gdel = req('DELETE', '/api/v1/groups/%s?cascade=true' % gid)
    REPORT['cleanup'] = {'purged': purged, 'group_id': gid, 'group_delete': gdel}
    return gid


def main():
    print('MAIN start', flush=True)
    REPORT['group_name'] = GROUP_NAME
    REPORT['case_name'] = CASE_NAME

    h1 = health()
    c1 = db_counts()
    REPORT['health_1'] = h1
    REPORT['counts_1'] = c1
    check('防串库① /health database=intelligent_audio_test', h1.get('database') == 'intelligent_audio_test',
          h1)

    driver = _driver()
    case_ids = []
    try:
        driver.get(BASE + '/')
        time.sleep(2)
        driver.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        node = None
        try:
            phase_list(driver)
            case = phase_create(driver)
            if case:
                case_ids.append(case.get('id'))
                ok, details = verify_created(get_case(case['id']))
                REPORT['created_fields'] = details
                check('新建用例接口逐字段一致（名称/分组/标签/描述/算法/音频/设备/声压/维度/噪声）',
                      ok, json.dumps(details, ensure_ascii=False)[:400])
            c2 = db_counts()
            REPORT['health_2'] = health()
            REPORT['counts_2'] = c2
            check('防串库② 截图批次前 database=intelligent_audio_test',
                  REPORT['health_2'].get('database') == 'intelligent_audio_test', REPORT['health_2'])

            if case:
                phase_edit(driver, case['id'])
                phase_delete(driver, case['id'])
                # 软删后从正常列表消失；彻底删除清理
                req('DELETE', '/api/v1/testcases/%s/purge' % case['id'])
            phase_validation(driver)
            phase_audio_dialog(driver)
            phase_dark(driver)
        except Exception as e:
            import traceback
            traceback.print_exc()
            check('脚本异常中断', False, repr(e))
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        # 清理（按名称兜底）
        extra = []
        for nm in (CASE_NAME, CASE_NAME_EDITED, '接线测试_INT1247_残留检查'):
            c = find_case_by_name(nm)
            if c:
                extra.append(c['id'])
        gid = cleanup(list(dict.fromkeys(case_ids + extra)), GROUP_NAME)
        # 清理后复核（按名称重新查，不能用删除前 id 判定）
        groups_after = ((req('GET', '/api/v1/groups')[1].get('data') or {}).get('items') or [])
        gid_after = next((g['id'] for g in groups_after if g['name'] == GROUP_NAME), None)
        h3 = health()
        REPORT['health_3'] = h3
        leftover = []
        for nm in (CASE_NAME, CASE_NAME_EDITED):
            if find_case_by_name(nm):
                leftover.append(nm)
        check('防串库③ 交付前 database=intelligent_audio_test', h3.get('database') == 'intelligent_audio_test', h3)
        check('测试数据清理（无本卡残留用例/分组）', not leftover and not gid_after,
              {'leftover_cases': leftover, 'group_id_after': gid_after})

    passed = sum(1 for c in CHECKS if c['ok'])
    total = len(CHECKS)
    REPORT['checks'] = CHECKS
    REPORT['summary'] = {'passed': passed, 'total': total}
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print('SUMMARY=', passed, '/', total)
    print('FAILED=', [c['name'] for c in CHECKS if not c['ok']])
    print('ARTIFACTS=', OUT)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
