# -*- coding: utf-8 -*-
"""INT-1506 返修 P2 浏览器实测（dev 5386 → docker api_gateway 15000，真实库）。

只复测本轮失败项（代码审计 P2）：批量设置评估维度的轮次取自「所选用例自身」而非列表首页。
覆盖两条路径：
  A. 分组视图组内勾选 2 条（这些用例与 /testcases 首页 100 条交集 0）→ 弹窗轮次按组内用例
     实际轮次渲染（本库「打断与恢复」组 2 轮）、不出现「暂无可配置的轮次信息」、确定可点。
  B. 组头「全选分组」（POST /testcases/ids 圈全组 175 条，只加载了 20 条）→ 弹窗显式提示
     「其中 N 个用例的轮次信息尚未加载」，仍可按「所有轮次」提交（未加载 ≠ 无轮次）。

用法：REACT_BASE=http://127.0.0.1:5386 python verify_int1506_batch_rounds.py
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5386')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = os.path.join(
    os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1506_rework')
os.makedirs(ART, exist_ok=True)

GROUP = '打断与恢复'
ROUNDS = 2           # 该组用例实际轮次（GET /testcases?group_id=… → config.rounds 长度）
GROUP_TOTAL = 175    # 组内总数（组内懒加载每页 20）

RESULTS = []


def log(*args):
    print(' '.join(str(a) for a in args), flush=True)


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    log(('PASS' if ok else 'FAIL'), name, detail)


def chromedriver_path():
    if not os.path.isdir(DRIVER_CACHE):
        return None
    cands = []
    for ver in os.listdir(DRIVER_CACHE):
        exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
        if os.path.isfile(exe):
            cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    return max(cands)[1] if cands else None


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


def wait(d, sec=40):
    return WebDriverWait(d, sec)


def body_text(d):
    return d.execute_script('return document.body.textContent') or ''


def dialog_el(d):
    els = d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    return els[-1] if els else None


def dialog_text(d):
    el = dialog_el(d)
    return (el.text if el else '') or ''


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    log('shot', path)
    return path


def set_theme(d, mode):
    d.get(BASE + '/testcases/by-group')
    wait(d, 60).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def enter_cases(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(1.5)


def expand_group(d, name):
    # 分组卡异步来自 /groups：先等组名出现
    wait(d, 90).until(lambda x: name in body_text(x))
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
    wait(d, 60).until(
        lambda x: x.execute_script(
            "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0"))
    time.sleep(1.0)


def select_two_cases(d):
    """勾选组内前两张用例卡（这些 id 与列表首页 100 条无交集）。"""
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


def select_whole_group(d):
    """组头「全选分组」：POST /testcases/ids 圈定整组（175 条），组内只加载了 20 条。"""
    el = wait(d, 30).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "[role='checkbox'][aria-label='全选分组 %s']" % GROUP)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(3.0)  # /testcases/ids 往返
    return 'clicked'


def open_dimensions(d):
    btn = wait(d, 30).until(EC.presence_of_element_located(
        (By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', btn)
    wait(d, 30).until(lambda x: bool(dialog_el(x)))
    time.sleep(1.0)


def round_tabs(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return [];
        return [...dlg.querySelectorAll('button')]
          .map(b => (b.textContent || '').trim())
          .filter(t => /^第\\s*\\d+\\s*轮$/.test(t));
        """)


def ok_button_enabled(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '确定');
        return btn ? !btn.disabled : null;
        """)


def close_dialog(d):
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (dlg) {
          const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '取消');
          if (btn) btn.click();
        }
        """)
    time.sleep(0.8)


def network(d):
    logs = d.get_log('performance')
    hits = []
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if '/api/v1/testcases' in url and resp.get('status'):
            hits.append({'url': url, 'status': resp.get('status')})
    return hits


def scenario_a(d, theme):
    """组内勾选 2 条（不在列表首页）→ 轮次按组内用例实际轮次。"""
    enter_cases(d)
    expand_group(d, GROUP)
    names = select_two_cases(d)
    open_dimensions(d)

    text = dialog_text(d)
    check('[%s] A 弹窗已打开（勾选 2 条组内用例）' % theme, '您勾选了 2 个用例' in text, names)
    check('[%s] A 不出现「暂无可配置的轮次信息」假空态' % theme,
          '暂无可配置的轮次信息' not in text)
    check('[%s] A 无「尚未加载」提示（两条均已加载）' % theme,
          '轮次信息尚未加载' not in text)
    check('[%s] A 确定可点' % theme, ok_button_enabled(d) is True)

    # 逐轮档位：轮次 Tab 与组内用例实际轮次一致（2 轮，不出现第 3/4 轮）
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        const label = [...dlg.querySelectorAll('label')]
          .find(l => (l.textContent || '').includes('逐轮设置'));
        if (label) label.click();
        """)
    time.sleep(1.2)
    tabs = round_tabs(d)
    check('[%s] A 逐轮页签 = 实际 2 轮（%s）' % (theme, tabs),
          tabs == ['第 1 轮', '第 2 轮'], str(tabs))

    path = shot(d, 'batch_dimensions_%s.png' % theme)
    close_dialog(d)
    return path


def scenario_b(d):
    """组头全选分组（/testcases/ids 圈全组）→ 未加载条数显式提示，仍可提交。"""
    enter_cases(d)
    expand_group(d, GROUP)
    select_whole_group(d)
    open_dimensions(d)
    text = dialog_text(d)

    check('B 弹窗已打开（全选分组）', '批量设置评估维度' in text or '轮次' in text, '')
    check('B 提示未加载条数（不当成无轮次）', '轮次信息尚未加载' in text,
          [ln for ln in text.splitlines() if '尚未加载' in ln][:2])
    check('B 不出现「暂无可配置的轮次信息」', '暂无可配置的轮次信息' not in text)
    check('B 确定可点（按所有轮次提交）', ok_button_enabled(d) is True)
    path = shot(d, 'batch_dimensions_whole_group.png')
    close_dialog(d)
    return path


def main():
    d = driver()
    shots = []
    try:
        light = scenario_a(d, 'light')
        shots.append(light)
        time.sleep(0.5)
        hits_a = network(d)
        log('network /api/v1/testcases:', json.dumps(hits_a[-4:], ensure_ascii=False))

        whole = scenario_b(d)
        shots.append(whole)

        # 深色（同源 reload 后才生效）
        set_theme(d, 'dark')
        dark = scenario_a(d, 'dark')
        shots.append(dark)

        summary = {
            'base': BASE,
            'checks': RESULTS,
            'network_testcases': hits_a[-6:],
            'screenshots': shots,
        }
        out = os.path.join(ART, 'result.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log('result', out)
        failed = [r for r in RESULTS if not r['ok']]
        log('SUMMARY', 'PASS' if not failed else 'FAIL %d' % len(failed))
        return 0 if not failed else 1
    finally:
        d.quit()


if __name__ == '__main__':
    raise SystemExit(main())
