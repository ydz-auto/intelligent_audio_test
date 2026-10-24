# -*- coding: utf-8 -*-
"""INT-1506 审返 P2 复测：批量设置评估维度的轮次按「所选用例自身」解析。

只复测代码审计打回的 P2（用户例轮次只从列表首页 items 推导 → 分组内用例被当成
「无轮次」并给出假空态、禁用「确定」）。两条路径：

  A. 分组视图「打断与恢复」→ 展开 → 勾组内 2 条（与 GET /testcases?page=1&per_page=100
     首页交集 0）→ 弹窗轮次按组内用例实际 rounds 渲染（本库 2 轮），无「暂无可配置的
     轮次信息」假空态，确定可点，逐轮页签不出第 3/4 轮。
  B. 组头「全选分组」（POST /testcases/ids 圈全组 175 条，组内只加载 20 条）→ 弹窗
     显式提示「其中 N 个用例的轮次信息尚未加载」（N = 全组 - 已加载），不出现假空态，
     确定可点（按「所有轮次」提交）。

同一脚本可用于 A/B：对修复前构建（e201ca59）运行时 A 的断言应全部 FAIL（假空态 +
确定禁用），证明断言有区分力。

用法：
  REACT_UI_BASE=http://127.0.0.1:15280 python verify_int1506_rounds_retest.py
环境：docker 真实库栈（前端旁路容器 → api_gateway 15000，主库 intelligent_audio_test）。
本脚本对真实库零写入（只读列表接口 + 浏览器点击，不提交任何批量操作）。
"""
import json
import os
import re
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_UI_BASE', 'http://127.0.0.1:15280')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.environ.get('INT1506_ART') or os.path.join(HERE, 'artifacts', 'int1506_rounds_retest')
os.makedirs(ART, exist_ok=True)

GROUP = os.environ.get('INT1506_GROUP', '打断与恢复')
RESULTS = []


def log(*args):
    print(' '.join(str(a) for a in args), flush=True)


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    log(('PASS' if ok else 'FAIL'), name, detail)
    return bool(ok)


# ── 只读接口（AUTH_MODE=off）────────────────────────────────────────────
def api_get(path, timeout=180):
    with urllib.request.urlopen(API + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def api_context():
    """首页 100 条 id、目标分组 id/总数/已加载前 20 条、轮次分布。"""
    page1 = api_get('/testcases?page=1&per_page=100')
    home_ids = [it['id'] for it in page1['data']['items']]

    groups = api_get('/groups?per_page=200')['data']['items']
    grp = next(g for g in groups if g['name'] == GROUP)
    gid = grp['id']

    gpage = api_get('/testcases?page=1&per_page=20&group_id=%s' % gid)
    loaded = gpage['data']['items']
    rounds = [len((it.get('config') or {}).get('rounds') or []) for it in loaded]
    ctx = {
        'home_count': page1['data']['total'],
        'home_ids': home_ids,
        'group_id': gid,
        'group_total': gpage['data']['total'],
        'group_loaded': len(loaded),
        'group_rounds': sorted(set(rounds)),
        'group_first_names': [it['name'] for it in loaded[:3]],
        'intersection': len(set(home_ids) & {it['id'] for it in loaded}),
    }
    log('api context', json.dumps({k: v for k, v in ctx.items() if k != 'home_ids'},
                                  ensure_ascii=False))
    return ctx


# ── 浏览器 ────────────────────────────────────────────────────────────
def chromedriver_path():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    pass
    return sorted(cands, key=lambda c: c[0])[-1][1] if cands else ''


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    exe = chromedriver_path()
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_script_timeout(120)
    return d


def wait(d, sec=60):
    return WebDriverWait(d, sec)


def body_text(d):
    return d.execute_script('return document.body.textContent') or ''


def dialog(d):
    els = d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    return els[-1] if els else None


def dialog_text(d):
    el = dialog(d)
    return (el.text if el else '') or ''


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    log('shot', path)
    return path


def goto_group_view(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 120).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(1.5)


def expand_group(d, name):
    wait(d, 120).until(lambda x: name in body_text(x))
    state = d.execute_script(
        """
        const name = arguments[0];
        const leaves = [...document.querySelectorAll('span,div')]
          .filter(e => e.children.length === 0 && (e.textContent || '').trim() === name);
        for (const leaf of leaves) {
          let p = leaf;
          for (let i = 0; i < 6 && p; i++) {
            const cls = String(p.className || '');
            if (cls.includes('cursor-pointer')) {
              p.scrollIntoView({block: 'center'});
              p.click();
              return 'ok';
            }
            p = p.parentElement;
          }
        }
        return 'not-found';
        """, name)
    log('expand group', name, state)
    if state != 'ok':
        raise AssertionError('分组未找到：%s' % name)
    wait(d, 120).until(
        lambda x: x.execute_script(
            "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0"))
    time.sleep(1.5)


def case_checkboxes(d):
    return d.execute_script(
        """
        return [...document.querySelectorAll('[role="checkbox"][aria-label^="选择 "]')]
          .map(e => e.getAttribute('aria-label'));
        """)


def select_two_cases(d):
    info = d.execute_script(
        """
        const boxes = [...document.querySelectorAll('[role="checkbox"][aria-label^="选择 "]')];
        if (boxes.length < 2) return 'few:' + boxes.length;
        boxes[0].click();
        boxes[1].click();
        return boxes[0].getAttribute('aria-label') + '||' + boxes[1].getAttribute('aria-label');
        """)
    log('select cases', info)
    return info


def select_whole_group(d, name):
    el = wait(d, 60).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "[role='checkbox'][aria-label='全选分组 %s']" % name)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(4.0)  # POST /testcases/ids 往返
    return 'clicked'


def open_dimensions(d):
    btn = wait(d, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', btn)
    wait(d, 60).until(lambda x: dialog(x) is not None)
    time.sleep(1.2)


def switch_round_mode(d, text):
    d.execute_script(
        """
        const t = arguments[0];
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        const label = [...dlg.querySelectorAll('label')]
          .find(l => (l.textContent || '').includes(t));
        if (label) label.click();
        """, text)
    time.sleep(1.2)


def round_tabs(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return [];
        return [...dlg.querySelectorAll('button')]
          .map(b => (b.textContent || '').trim())
          .filter(t => /^第\\s*\\d+\\s*轮$/.test(t));
        """)


def button_enabled(d, label):
    return d.execute_script(
        """
        const label = arguments[0];
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === label);
        return btn ? !btn.disabled : null;
        """, label)


def radion_checked(d, text):
    return d.execute_script(
        """
        const t = arguments[0];
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const label = [...dlg.querySelectorAll('label')].find(l => (l.textContent || '').includes(t));
        if (!label) return null;
        const input = label.querySelector('input[type=radio]');
        return input ? !!input.checked : null;
        """, text)


def close_dialog(d):
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '取消');
        if (btn) btn.click();
        """)
    time.sleep(1.0)


def scroll_dialog(d, where='bottom'):
    """弹窗内容高于视口：滚到最底部让「确定」按钮进入截图，或复位到顶部。"""
    d.execute_script(
        """
        const where = arguments[0];
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return;
        const nodes = [dlg, ...dlg.querySelectorAll('*')].filter(
          e => e.scrollHeight > e.clientHeight + 20 && /auto|scroll/.test(getComputedStyle(e).overflowY));
        nodes.forEach(e => { e.scrollTop = where === 'bottom' ? e.scrollHeight : 0; });
        """, where)
    time.sleep(0.8)


def set_dark(d):
    d.get(BASE + '/')
    wait(d, 120).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
    time.sleep(0.5)
    html_class = None
    d.get(BASE + '/testcases/by-group')
    wait(d, 120).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(1.5)
    html_class = d.execute_script("return document.documentElement.className")
    log('html class after dark reload', html_class)
    return html_class


def network_testcases(d):
    hits = []
    for entry in d.get_log('performance'):
        try:
            msg = json.loads(entry['message']).get('message') or {}
            if msg.get('method') != 'Network.responseReceived':
                continue
            resp = msg.get('params', {}).get('response', {})
            url = resp.get('url', '')
            if '/api/v1/testcases' in url:
                hits.append({'url': url.split('/api/v1')[-1], 'status': resp.get('status')})
        except Exception:
            continue
    return hits


def scenario_a(d, ctx, theme):
    goto_group_view(d)
    expand_group(d, GROUP)
    names = select_two_cases(d)
    selected_names = [n.replace('选择 ', '') for n in names.split('||')] if '||' in names else []
    open_dimensions(d)

    text = dialog_text(d)
    loaded_names = [n.replace('选择 ', '') for n in case_checkboxes(d)]
    default_all_checked = radion_checked(d, '所有轮次')

    check('[%s] A1 弹窗识别到勾选 2 条组内用例' % theme, '您勾选了 2 个用例' in text,
          [ln for ln in text.splitlines() if '勾选' in ln][:1])
    check('[%s] A2 无「所选用例暂无可配置的轮次信息」假空态' % theme,
          '暂无可配置的轮次信息' not in text)
    check('[%s] A3 无「尚未加载」提示（两条均已在组内加载）' % theme,
          '轮次信息尚未加载' not in text)
    check('[%s] A4 确定可点' % theme, button_enabled(d, '确定') is True,
          'enabled=%s' % button_enabled(d, '确定'))

    # 所选用例来自组内懒加载：与首页 100 条交集 0（取数口径复现审计现场）
    check('[%s] A5 组内用例与列表首页交集 0（复现审计口径）' % theme,
          ctx['intersection'] == 0, 'intersection=%s/%s' % (ctx['intersection'], ctx['group_loaded']))
    check('[%s] A6 勾选的用例名均属该组已加载页' % theme,
          all(n in loaded_names for n in selected_names) if selected_names else False,
          '%s ⊂ %s' % (selected_names, len(loaded_names)))

    switch_round_mode(d, '逐轮设置')
    tabs = round_tabs(d)
    expected = ['第 %d 轮' % r for r in range(1, max(ctx['group_rounds'] or [1]) + 1)]
    check('[%s] A7 逐轮页签 == 组内实际轮次 %s（修复前恒第 1~4 轮）' % (theme, expected),
          tabs == expected, 'tabs=%s' % tabs)
    check('[%s] A8 逐轮无第 3 / 4 轮（写死 4 轮时会出现）' % theme,
          not any(t in ('第 3 轮', '第 4 轮') for t in tabs), 'tabs=%s' % tabs)
    check('[%s] A9 「添加轮次」在当前轮次已全开时禁用' % theme,
          button_enabled(d, '添加轮次') is False, 'enabled=%s' % button_enabled(d, '添加轮次'))
    check('[%s] A10 默认档位为「所有轮次（统一设置）」' % theme,
          default_all_checked is True, 'checked=%s' % default_all_checked)

    path = shot(d, 'batch_dimensions_group_%s.png' % theme)
    scroll_dialog(d, 'bottom')
    footer = shot(d, 'batch_dimensions_group_footer_%s.png' % theme)
    close_dialog(d)
    return [path, footer]


def scenario_b(d, ctx, theme):
    goto_group_view(d)
    expand_group(d, GROUP)
    loaded = len(case_checkboxes(d))
    select_whole_group(d, GROUP)
    open_dimensions(d)
    text = dialog_text(d)
    expect_unknown = ctx['group_total'] - loaded
    m = re.search(r'其中\s*(\d+)\s*个用例的轮次信息尚未加载', text)
    actual_unknown = int(m.group(1)) if m else None

    check('[%s] B1 弹窗按全组条数识别勾选' % theme,
          ('您勾选了 %d 个用例' % ctx['group_total']) in text,
          [ln for ln in text.splitlines() if '勾选' in ln][:1])
    check('[%s] B2 显式提示未加载条数（预期 %d）' % (theme, expect_unknown),
          actual_unknown == expect_unknown, 'parsed=%s text=%s' % (actual_unknown, [ln for ln in text.splitlines() if '尚未加载' in ln][:2]))
    check('[%s] B3 不复用「暂无可配置的轮次信息」假空态' % theme,
          '暂无可配置的轮次信息' not in text)
    check('[%s] B4 确定可点（未加载 ≠ 无轮次，可按所有轮次提交）' % theme,
          button_enabled(d, '确定') is True, 'enabled=%s' % button_enabled(d, '确定'))
    check('[%s] B5 默认档位「所有轮次」' % theme, radion_checked(d, '所有轮次') is True)
    scroll_dialog(d, 'bottom')
    footer = shot(d, 'batch_dimensions_whole_group_footer_%s.png' % theme)
    scroll_dialog(d, 'top')
    # 有已知轮次时可按轮次设置：未加载条目不产生第 3/4 轮，仍按已加载用例的轮次渲染
    switch_round_mode(d, '逐轮设置')
    tabs = round_tabs(d)
    expected = ['第 %d 轮' % r for r in range(1, max(ctx['group_rounds'] or [1]) + 1)]
    check('[%s] B6 逐轮页签仍按已加载用例轮次 %s（不按 155 条未知编造轮次）' % (theme, expected),
          tabs == expected, 'tabs=%s' % tabs)
    check('[%s] B7 切到逐轮后确定仍可点' % theme, button_enabled(d, '确定') is True)

    path = shot(d, 'batch_dimensions_whole_group_%s.png' % theme)
    close_dialog(d)
    return [path, footer]


def main():
    ctx = api_context()
    d = driver()
    shots = []
    try:
        shots.extend(scenario_a(d, ctx, 'light'))
        shots.extend(scenario_b(d, ctx, 'light'))
        dark_class = set_dark(d)
        check('深色主题已生效（html class 含 dark）', 'dark' in (dark_class or ''),
              'class=%s' % dark_class)
        shots.extend(scenario_a(d, ctx, 'dark'))
        shots.extend(scenario_b(d, ctx, 'dark'))

        hits = network_testcases(d)
        group_hits = [h for h in hits if 'group_id=' in h['url']]
        home_hits = [h for h in hits if 'per_page=100' in h['url']]
        # 网关偶发 504 由前端重试兜住：判定「最终一次成功且会话内成功过」，不要求每一次都 200
        check('Network：组内用例来自按分组懒加载（group_id 请求最终 200）',
              bool(group_hits) and group_hits[-1]['status'] == 200,
              [h['status'] for h in group_hits])
        check('Network：列表首页 per_page=100 请求最终 200',
              bool(home_hits) and home_hits[-1]['status'] == 200,
              [h['status'] for h in home_hits])

        failed = [r for r in RESULTS if not r['ok']]
        out = os.path.join(ART, 'result.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'base': BASE, 'api': ctx, 'checks': RESULTS, 'screenshots': shots,
                       'network_testcases': hits[-8:]}, f, ensure_ascii=False, indent=2)
        log('result', out)
        log('SUMMARY', 'PASS' if not failed else 'FAIL %d' % len(failed))
        return 0 if not failed else 1
    finally:
        d.quit()


if __name__ == '__main__':
    raise SystemExit(main())
