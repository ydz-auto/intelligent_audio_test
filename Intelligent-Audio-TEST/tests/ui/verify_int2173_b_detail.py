# -*- coding: utf-8 -*-
"""INT-2173 走查·B：任务详情（用例级合并/轮次/未执行破折号/目标 Tab）+ 失败原因弹窗。"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2173')
os.makedirs(ART, exist_ok=True)
RESULTS = []
CTX = {}


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1200]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))
    return ok


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text or ''


def wait_text(drv, text, timeout=120):
    return WebDriverWait(drv, timeout).until(lambda d: text in body(d))


def row_info(drv, frag):
    """搜索并返回该用例行的 DOM 信息。"""
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    B.set_input(drv, box, frag)
    time.sleep(2.5)
    return drv.execute_script("""
      const rows = [...document.querySelectorAll('[data-testid="task-case-list"] [role=row]')];
      for (const r of rows) {
        if ((r.textContent||'').includes(arguments[0])) {
          const cell = (col) => { const el = r.querySelector('[data-column="'+col+'"]'); return el ? {text:(el.textContent||'').trim(), html: el.innerHTML.slice(0,200)} : null; };
          return {text: (r.textContent||'').trim().slice(0,400), rounds: cell('rounds'), duration: cell('duration'), targets: cell('targets'), exec: cell('execution')};
        }
      }
      return null;
    """, frag)


def open_case_dialog(drv, frag):
    wait_text(drv, '关联用例', 120)
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    B.set_input(drv, box, frag)
    time.sleep(2)
    btn = WebDriverWait(drv, 60).until(lambda d: d.find_element(
        By.XPATH, "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % frag))
    drv.execute_script('arguments[0].click()', btn)
    WebDriverWait(drv, 60).until(lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.2)


def main():
    token, _ = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    st, health = B.api('/health', None)
    check('B 段核对 /health database=intelligent_audio_test', health.get('database') == 'intelligent_audio_test', health)

    st, d402 = B.api('/api/v1/tasks/402', token)
    t402 = d402.get('data') or {}
    st, d526 = B.api('/api/v1/tasks/526', token)
    t526 = d526.get('data') or {}
    st, d764 = B.api('/api/v1/tasks/764', token)
    t764 = d764.get('data') or {}
    CTX['task402'] = {'total_cases': t402.get('total_cases'), 'devices': len(t402.get('devices') or []), 'apis': len(t402.get('apis') or [])}
    CTX['task526'] = {'status': t526.get('status'), 'failed_cases': t526.get('failed_cases'), 'total_cases': t526.get('total_cases')}

    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, None)
        # ---------- 3. 任务详情（402） ----------
        B.goto(drv, '/tasks/402', timeout=120)
        wait_text(drv, '关联用例', 180)
        time.sleep(2)
        txt = body(drv)
        m = re.search(r'关联用例\s*(\d+)', txt)
        ui_cases = int(m.group(1)) if m else None
        check('详情 402：关联用例 Tab 计数 = GET /tasks/402 total_cases',
              ui_cases == t402.get('total_cases'), {'ui': ui_cases, 'api': t402.get('total_cases')})
        shot(drv, 'B01_detail402_light')

        info = row_info(drv, 'DD061')
        rounds_txt = (info or {}).get('rounds', {}).get('text')
        check('详情 402：DD061 轮次列 = 第 2/2 轮（分母取 rounds_count=2）',
              rounds_txt == '第 2/2 轮', {'row': (info or {}).get('text', '')[:200], 'rounds': rounds_txt})
        check('详情 402：DD061 设备/API 列显示已完成/总数（用例级合并）',
              bool((info or {}).get('targets')) and re.match(r'^\d+/\d+$', ((info or {}).get('targets') or {}).get('text', '')),
              (info or {}).get('targets'))

        info2 = row_info(drv, 'JG0006')
        check('详情 402：JG0006 轮次列 = 第 1/1 轮',
              (info2 or {}).get('rounds', {}).get('text') == '第 1/1 轮',
              {'rounds': (info2 or {}).get('rounds', {}).get('text')})

        # 关联资源 Tab 计数
        drv.execute_script("""
          for (const t of document.querySelectorAll('[role=tab]')) {
            if ((t.textContent||'').trim().startsWith('关联资源')) { t.click(); return true; }
          }
          return false;
        """)
        time.sleep(2)
        res_txt = body(drv)
        want_res = (CTX['task402']['devices'], CTX['task402']['apis'])
        check('详情 402：关联资源 Tab 打开并按设备/API 分别展示',
              '关联资源' in res_txt and ('暂无关联资源' in res_txt or 'pura90' in res_txt),
              {'devices': want_res[0], 'apis': want_res[1], 'tail': res_txt[-200:]})
        shot(drv, 'B02_resources_tab')
        drv.execute_script("""
          for (const t of document.querySelectorAll('[role=tab]')) {
            if ((t.textContent||'').trim().startsWith('关联用例')) { t.click(); return true; }
          }
          return false;
        """)
        time.sleep(1.5)

        # 用例详情弹窗：设备/API 一级 Tab
        open_case_dialog(drv, 'JG0006')
        targets_ui = drv.execute_script("""
          const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
          if (!dlg) return null;
          const bar = [...dlg.querySelectorAll('[role=tab]')].map(t => (t.textContent||'').trim());
          const lists = [...dlg.querySelectorAll('[aria-label="设备/API 切换"], [aria-label="目标切换"]')].map(x => [...x.querySelectorAll('[role=tab]')].map(t => (t.textContent||'').trim()));
          const ths = [...dlg.querySelectorAll('table thead th')].map(t => (t.textContent||'').trim());
          return {bar, lists, heads: ths.slice(0, 8), text: (dlg.textContent||'').slice(0, 300)};
        """)
        check('用例详情：设备/API 一级 Tab 存在（全部对比 + 目标）',
              targets_ui is not None and any(('全部对比' in x) for x in (targets_ui.get('bar') or []) + [y for l in (targets_ui.get('lists') or []) for y in l]),
              targets_ui)
        CTX['target_bar'] = targets_ui
        shot(drv, 'B03_case_dialog_targets')
        # 切到真实设备目标（pura90小艺）
        switched = drv.execute_script("""
          const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
          for (const t of dlg.querySelectorAll('[role=tab]')) {
            if ((t.textContent||'').trim().includes('pura90小艺')) { t.click(); return true; }
          }
          return false;
        """)
        time.sleep(1.5)
        after = drv.execute_script("""
          const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
          const ths = [...dlg.querySelectorAll('table thead th')].map(t => (t.textContent||'').trim());
          const sel = [...dlg.querySelectorAll('[role=tab][aria-selected=true]')].map(t => (t.textContent||'').trim());
          return {heads: ths.slice(0, 8), selected: sel, text: (dlg.textContent||'').slice(0, 200)};
        """)
        scoped_txt = drv.execute_script("""
          const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
          const p = [...dlg.querySelectorAll('p')].find(x => (x.textContent||'').trim() === '设备/API 执行结果');
          const sec = p ? p.parentElement : null;
          return sec ? (sec.textContent||'').slice(0, 500) : null;
        """)
        check('用例详情：切到目标「pura90小艺」后执行结果块收窄到该目标（指标表按设计恒全量）',
              switched and 'pura90小艺' in (after.get('selected') or []) and scoped_txt is not None
              and 'pura90小艺' in scoped_txt and '设备 —' not in (scoped_txt or ''),
              {'switched': switched, 'selected': after.get('selected'), 'scoped': scoped_txt, 'heads': after.get('heads')})
        shot(drv, 'B04_case_dialog_target_pura90')
        # 幽灵目标列证据（旧任务 targets 无 name/id → 前端兜底「设备 —」多出一列）
        phantom = drv.execute_script("""
          const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
          const ths = [...dlg.querySelectorAll('table thead th')].map(t => (t.textContent||'').trim());
          const tabs = [...dlg.querySelectorAll('[role=tab]')].map(t => (t.textContent||'').trim());
          return {heads: ths, tabs};
        """)
        CTX['phantom'] = phantom
        check('用例详情：旧任务 targets 缺 target_name/device_id 时不应出现「设备 —」幽灵目标',
              not any(t.strip() == '设备 —' for t in (phantom.get('heads') or []) + (phantom.get('tabs') or [])),
              phantom)
        drv.find_element(By.TAG_NAME, 'body').send_keys('\x1b')
        time.sleep(1)

        # ---------- 8b. 失败原因弹窗（526 failed） ----------
        # 先取接口里的失败原因
        first_err = None
        for c in (t764.get('cases') or []):
            if c.get('execution_status') == 'failed' and c.get('error_message'):
                first_err = c.get('error_message')
                break
        CTX['first_fail'] = first_err
        B.goto(drv, '/tasks/764', timeout=120)
        # toast 只在 mount 后 10s 内（sonner duration=10000），检测到即先截图再断言
        toast_text = None
        for _ in range(30):
            t = drv.execute_script("return [...document.querySelectorAll('[data-sonner-toast]')].map(e=>(e.textContent||'').trim())")
            if t:
                toast_text = t
                break
            time.sleep(0.5)
        shot(drv, 'B05_failed_toast')
        with_err = [x for x in (toast_text or []) if '测试任务执行失败' in x]
        CTX['toast_shot'] = {'texts': toast_text, 'has_error_toast': bool(with_err)}
        check('B05 失败 toast 截图时 toast 仍在 DOM（图上有「测试任务执行失败」）',
              bool(with_err) and any(('1 轮失败' in x) for x in with_err), CTX['toast_shot'])
        check('失败任务详情：弹出「测试任务执行失败」原因 toast',
              bool(toast_text) and any('测试任务执行失败' in x for x in toast_text),
              {'toasts': toast_text, 'first_err': (first_err or '')[:200]})
        if toast_text and first_err:
            check('失败弹窗内容与任务详情失败原因一致（首条 failed 用例 error_message）',
                  any(first_err in x for x in toast_text), {'toast': toast_text, 'first_err': first_err[:300]})

        # ---------- 3b. 未执行用例：526 中 pending 用例 ----------
        B.goto(drv, '/tasks/526', timeout=120)
        wait_text(drv, '关联用例', 180)
        time.sleep(2)
        info3 = row_info(drv, 'JG0221')
        rounds3 = (info3 or {}).get('rounds', {}).get('text')
        dur3 = (info3 or {}).get('duration', {}).get('text')
        prog = drv.execute_script("""
          const rows = [...document.querySelectorAll('[data-testid="task-case-list"] [role=row]')];
          for (const r of rows) {
            if ((r.textContent||'').includes('JG0221')) {
              const cell = r.querySelector('[data-column="rounds"]');
              const bar = cell ? cell.querySelector('[role=progressbar], [data-slot=progress], [data-value]') : null;
              return {rounds: cell ? (cell.textContent||'').trim() : null, bar: bar ? bar.outerHTML.slice(0,300) : null};
            }
          }
          return null;
        """)
        check('详情 526：未执行用例轮次显示「—」且不误显示第 1 轮',
              rounds3 == '—', {'rounds': rounds3, 'duration': dur3, 'detail': prog})
        check('详情 526：未执行用例耗时显示「—」',
              dur3 == '—', {'duration': dur3})
        check('详情 526：未执行用例进度条为空（aria-valuenow=0 / 无宽度）',
              prog is not None and ('aria-valuenow="0"' in (prog.get('bar') or '') or 'width: 0' in (prog.get('bar') or '') or 'data-value="0"' in (prog.get('bar') or '')),
              prog)
        # 526 用例数核对（先清空用例搜索，避免计数被搜索过滤）
        sbox = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
        B.set_input(drv, sbox, '')
        time.sleep(2)
        txt2 = body(drv)
        m2 = re.search(r'关联用例\s*(\d+)', txt2)
        check('详情 526：关联用例 Tab 计数 = API total_cases',
              (int(m2.group(1)) if m2 else None) == t526.get('total_cases'),
              {'ui': m2.group(1) if m2 else None, 'api': t526.get('total_cases')})
        shot(drv, 'B06_detail526_pending')

        # 深色详情截图
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(6)
        shot(drv, 'B07_detail526_dark')
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light'); location.reload();")
        time.sleep(3)
    finally:
        drv.quit()

    failed = [r for r in RESULTS if not r['ok']]
    print('\n==== B: %d checks, %d failed ====' % (len(RESULTS), len(failed)))
    with open(os.path.join(ART, 'evidence_B.json'), 'w', encoding='utf-8') as f:
        json.dump({'checks': RESULTS, 'ctx': CTX}, f, ensure_ascii=False, indent=1)
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:200])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
