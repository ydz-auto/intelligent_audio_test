# -*- coding: utf-8 -*-
"""INT-1506 第三轮返修实测（docker 旁路容器 15282 → api_gateway 15000，真实库）。

只复测本轮失败项（代码审计 P1-1）与相关修复：
  A. 分组未展开 → 组头「全选分组」→ 浮条「批量设置评估维度」：轮次一条都没加载时，
     点维度 chip 必须真的勾上（已选 N 项 / 参数卡出现），提交载荷 dimensions 非空。
  B. 分组部分加载（展开后只加载首页 20 条）→ 全选分组：同样可勾选、可提交。
  C. 未选任何维度点确定：先弹二次确认（后端空数组=清空），确认前不发请求。
另外核对批量弹窗共享轮次片段：轮次未知时「指定轮次/逐轮设置」禁用。

写库纪律：批量提交请求在页内被拦截（记录请求体后返回成功信封），不向真实库写入。

用法：REACT_BASE=http://127.0.0.1:15282 python verify_int1506_p1_round3.py
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15282')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = os.path.join(
    os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1506_round3')
os.makedirs(ART, exist_ok=True)

GROUP = '打断与恢复'   # 组内 175 条，每秒展开只加载 20 条（真实库口径）
RESULTS = []


def log(*args):
    print(' '.join(str(a) for a in args), flush=True)


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
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
    exe = chromedriver_path()
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_script_timeout(120)
    return d


def wait(d, sec=60):
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


# 页内拦截批量提交：记录请求体，回成功信封（不写真实库）
STUB_JS = r"""
(() => {
  if (window.__IAT_BATCH_HOOK) return 'already';
  window.__IAT_BATCH = [];
  const orig = window.fetch;
  window.__IAT_BATCH_HOOK = true;
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/testcases/batch') >= 0) {
      window.__IAT_BATCH.push({ url: url, body: (init && init.body) || '' });
      return new Response(
        JSON.stringify({ success: true, code: 0, message: 'ok', data: { updated_count: 0 } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return orig.apply(this, arguments);
  };
  return 'installed';
})()
"""


def set_theme(d, mode):
    d.get(BASE + '/testcases/by-group')
    wait(d, 90).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def enter_cases(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 120).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(2.0)
    d.execute_script(STUB_JS)


def expand_group(d, name):
    wait(d, 90).until(lambda x: name in body_text(x))
    has_cards = lambda x: x.execute_script(
        "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0")
    for attempt in range(3):
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
        log('expand group', name, state, 'attempt', attempt + 1)
        if state != 'ok':
            raise AssertionError('分组未找到：%s' % name)
        try:
            wait(d, 25).until(has_cards)
            time.sleep(1.5)
            return
        except Exception:
            log('expand retry（未出现用例卡）')
            time.sleep(2.0)
    raise AssertionError('分组展开后未加载用例卡：%s' % name)


def select_whole_group(d):
    el = wait(d, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "[role='checkbox'][aria-label='全选分组 %s']" % GROUP)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(4.0)  # /testcases/ids 往返


def open_dimensions(d):
    btn = wait(d, 40).until(EC.presence_of_element_located(
        (By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', btn)
    wait(d, 40).until(lambda x: bool(dialog_el(x)))
    time.sleep(1.2)


def radio_disabled(d, label):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const lab = [...dlg.querySelectorAll('label')]
          .find(l => (l.textContent || '').trim().indexOf(arguments[0]) >= 0);
        if (!lab) return 'label-missing';
        const input = lab.querySelector("input[type='radio']");
        return input ? !!input.disabled : 'input-missing';
        """, label)


def ok_button_enabled(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '确定');
        return btn ? !btn.disabled : null;
        """)


def click_first_dimension(d):
    """在「维度选择」云里点第一个维度 chip；返回点击后的已选文案。"""
    info = d.execute_script(
        """
        const root = document.querySelector("[data-testid='batch-dim-round-cloud']");
        if (!root) return {clicked: false, text: 'cloud-missing'};
        const btns = [...root.querySelectorAll('button')];
        const chip = btns.find(b => {
          const t = (b.textContent || '').trim();
          return t && !/^已选/.test(t) && !/^\\d+$/.test(t) && t.length > 1;
        });
        if (!chip) return {clicked: false, text: 'chip-missing'};
        chip.scrollIntoView({block: 'center'});
        chip.click();
        return {clicked: true, text: (chip.textContent || '').trim()};
        """)
    time.sleep(1.0)
    selected_text = d.execute_script(
        """
        const root = document.querySelector("[data-testid='batch-dim-round-cloud']");
        if (!root) return '';
        const m = (root.textContent || '').match(/已选\\s*(\\d+)\\s*项/);
        return m ? m[1] : '';
        """)
    return info, selected_text


def param_card_visible(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        return !!(dlg && (dlg.textContent || '').indexOf('维度权重和阈值配置') >= 0);
        """)


def click_ok(d):
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '确定');
        if (btn) btn.click();
        """)
    time.sleep(1.5)


def captured_batch(d):
    raw = d.execute_script('return JSON.stringify(window.__IAT_BATCH || []);')
    try:
        return json.loads(raw)
    except Exception:
        return []


def close_dialog(d):
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '取消');
        if (btn) btn.click();
        """)
    time.sleep(0.8)


def scenario_unknown(d, theme='light'):
    """A：分组未展开 → 全选分组（组内一条都没加载）→ 弹窗可勾选、可提交非空维度。"""
    enter_cases(d)
    select_whole_group(d)
    open_dimensions(d)

    text = dialog_text(d)
    check('[%s] A 弹窗打开（全选分组）' % theme, '批量设置评估维度' in text, text[:120])
    check('[%s] A 显式提示「轮次信息尚未加载」' % theme, '轮次信息尚未加载' in text, '')
    check('[%s] A 不出现「暂无可配置的轮次信息」' % theme, '暂无可配置的轮次信息' not in text, '')
    check('[%s] A 指定轮次档禁用' % theme, radio_disabled(d, '指定轮次（统一设置）') is True,
          radio_disabled(d, '指定轮次（统一设置）'))
    check('[%s] A 逐轮设置档禁用' % theme, radio_disabled(d, '逐轮设置（每轮可不同）') is True,
          radio_disabled(d, '逐轮设置（每轮可不同）'))
    check('[%s] A 确定可点（所有轮次档）' % theme, ok_button_enabled(d) is True)

    info, selected = click_first_dimension(d)
    check('[%s] A 点维度 chip 真的勾上（已选 %s 项）' % (theme, selected),
          info.get('clicked') and selected not in ('', '0'),
          json.dumps(info, ensure_ascii=False))
    check('[%s] A 已选维度参数卡出现' % theme, param_card_visible(d) is True)

    light_shot = shot(d, 'unknown_rounds_%s.png' % theme)

    click_ok(d)
    reqs = captured_batch(d)
    body = {}
    if reqs:
        try:
            body = json.loads(reqs[-1]['body'])
        except Exception:
            body = {}
    dims = body.get('dimensions') or []
    check('[%s] A 提交载荷 dimensions 非空（%d 项）' % (theme, len(dims)), len(dims) > 0,
          json.dumps(body, ensure_ascii=False)[:600])
    check('[%s] A 载荷 round_mode=all' % theme, body.get('round_mode') == 'all', body.get('round_mode'))
    close_dialog(d)
    return light_shot


def scenario_partial(d):
    """B：展开分组（只加载 20/175）→ 全选分组 → 仍可勾选、可提交。"""
    enter_cases(d)
    expand_group(d, GROUP)
    select_whole_group(d)
    open_dimensions(d)

    text = dialog_text(d)
    check('B 弹窗打开（部分加载）', '批量设置评估维度' in text, text[:120])
    check('B 提示未加载条数', '轮次信息尚未加载' in text, '')
    info, selected = click_first_dimension(d)
    check('B 点维度 chip 真的勾上（已选 %s 项）' % selected,
          info.get('clicked') and selected not in ('', '0'), json.dumps(info, ensure_ascii=False))
    path = shot(d, 'partial_rounds_light.png')
    click_ok(d)
    reqs = captured_batch(d)
    body = {}
    if reqs:
        try:
            body = json.loads(reqs[-1]['body'])
        except Exception:
            body = {}
    check('B 提交载荷 dimensions 非空（%d 项）' % len(body.get('dimensions') or []),
          len(body.get('dimensions') or []) > 0, json.dumps(body, ensure_ascii=False)[:600])
    close_dialog(d)
    return path


def scenario_clear_guard(d):
    """C：未选任何维度点确定 → 二次确认（AlertDialog），确认前不发请求。"""
    enter_cases(d)
    select_whole_group(d)
    open_dimensions(d)
    d.execute_script('window.__IAT_BATCH = [];')
    click_ok(d)
    text = body_text(d)
    check('C 未选维度提交先二次确认', '确定清空所选用例的评估维度' in text,
          [ln for ln in text.splitlines() if '清空所选用例' in ln][:2])
    check('C 确认前不发送清空请求', captured_batch(d) == [], captured_batch(d))
    shot(d, 'clear_guard_light.png')
    # 取消确认（不真的清空）
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='alertdialog']")].pop();
        if (!dlg) return;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '取消');
        if (btn) btn.click();
        """)
    time.sleep(0.8)
    close_dialog(d)


def main():
    only = [s.strip().upper() for s in os.environ.get('SCENARIOS', 'A,B,C').split(',') if s.strip()]
    d = driver()
    shots = []
    try:
        if 'A' in only:
            light = scenario_unknown(d, 'light')
            shots.append(light)

            set_theme(d, 'dark')
            dark = scenario_unknown(d, 'dark')
            shots.append(dark)

        if 'B' in only:
            set_theme(d, 'light')
            shots.append(scenario_partial(d))
        if 'C' in only:
            scenario_clear_guard(d)

        summary = {
            'base': BASE,
            'checks': RESULTS,
            'screenshots': shots,
        }
        out = os.path.join(ART, 'result_%s.json' % ''.join(only))
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
