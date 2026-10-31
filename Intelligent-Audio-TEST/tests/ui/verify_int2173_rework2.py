# -*- coding: utf-8 -*-
"""INT-2173 返工 2：补 A11 任务列表深色图 + B05 失败原因 toast 图（只读真实数据 + 自建数据）。

- A11：/tasks/daily 深色，含三页签 / 筛选条 / 分页（上、下两屏各一张）。
- B05：/tasks/764（真失败任务，只读）进入详情后 10s 内的「测试任务执行失败」toast，
  检测到立即截图（先图后断言），并与 GET /tasks/764 首条 failed 用例 error_message 比对。
"""
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

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2173_rework2')
os.makedirs(ART, exist_ok=True)
TS = time.strftime('%m%d%H%M%S')
RESULTS = []
CTX = {}


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1500]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))
    return ok


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p, os.path.getsize(p))
    return p


def body(drv):
    return drv.execute_script('return document.body ? (document.body.textContent || "") : ""')


def main():
    token, user = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    st, health = B.api('/health', None)
    print('HEALTH', st, health)
    check('开工核对 /health database=intelligent_audio_test',
          health.get('database') == 'intelligent_audio_test', health)
    st, d = B.api('/api/v1/tasks?page=1&per_page=10', token)
    CTX['tasks_total_start'] = (d.get('data') or {}).get('total')

    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, user)
        CTX['bundle'] = drv.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src).filter(s=>/index\\.|lib-react/.test(s))")

        # ---------------- A11：任务列表深色（三页签 / 筛选条 / 分页） ----------------
        B.set_theme(drv, 'dark')
        B.goto(drv, '/tasks/daily', timeout=90)
        B.wait_text(drv, '任务名称', 60)
        time.sleep(2)
        dark = B.is_dark(drv)
        tabs = drv.execute_script("return [...document.querySelectorAll('[role=tab]')].map(t=>t.textContent.trim().split('\\n')[0])")
        txt = body(drv)
        pag = drv.execute_script(r"""
          const t = document.body.textContent || '';
          return (t.match(/共\s*[\d,]+\s*条/) || [''])[0] || (t.match(/\d+\s*[–-]\s*\d+\s*\/\s*[\d,]+/) || [''])[0];
        """)
        row_total = drv.execute_script("""
          const el = document.querySelector('[role=row]');
          return el ? el.textContent.trim().slice(0, 80) : null;
        """)
        has_rows = bool(re.search(r'(测试任务_|接线测试_|matrix_)', txt))
        tab_names = [re.sub(r'\s*\d+$', '', t).strip() for t in tabs]
        drv.execute_script('window.scrollTo(0,0)')
        time.sleep(1)
        p1 = shot(drv, 'A11_dark_tasks_list_top')
        CTX['a11'] = {'dark': dark, 'tabs': tabs, 'pagination': pag, 'row': row_total,
                      'has_rows': has_rows, 'url': drv.current_url}
        check('A11 任务列表深色：/tasks/daily 三页签齐全且列表有数据',
              dark and tab_names == ['日常', '已发布', '挑选合并'] and '只看收藏' in txt and has_rows,
              CTX['a11'])
        drv.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1.2)
        p2 = shot(drv, 'A11_dark_tasks_list_pagination')
        check('A11 任务列表深色：分页「共 N 条 / 页码」可见',
              bool(pag) and ('共' in pag or '/' in pag), {'pagination': pag, 'shots': [os.path.basename(p1), os.path.basename(p2)]})

        # ---------------- B05：失败任务详情 toast（与接口失败原因一致） ----------------
        B.set_theme(drv, 'light')
        st, td = B.api('/api/v1/tasks/764', token)
        t764 = td.get('data') or {}
        first_err = None
        for c in (t764.get('cases') or []):
            if c.get('execution_status') == 'failed' and c.get('error_message'):
                first_err = c['error_message']
                break
        CTX['first_fail'] = first_err
        B.goto(drv, '/tasks/764', timeout=120)
        toast_text = None
        t0 = time.time()
        for _ in range(40):
            t = drv.execute_script(
                "return [...document.querySelectorAll('[data-sonner-toast]')].map(e=>(e.textContent||'').trim())")
            if t:
                toast_text = t
                break
            time.sleep(0.25)
        dt = round(time.time() - t0, 2)
        p3 = shot(drv, 'B05_failed_toast')
        # toast 元素单独裁一张（sonner 容器），便于核对文案
        p3b = None
        try:
            el = drv.find_element(By.CSS_SELECTOR, '[data-sonner-toast]')
            p3b = os.path.join(ART, 'B05_failed_toast_element.png')
            el.screenshot(p3b)
            print('SHOT', p3b, os.path.getsize(p3b))
        except Exception as exc:
            print('toast element shot skip', exc)
        CTX['b05'] = {'toasts': toast_text, 'detect_s': dt, 'first_err': first_err,
                      'shots': [os.path.basename(p3), os.path.basename(p3b or '')]}
        check('B05 失败任务详情：进入页面即弹「测试任务执行失败」toast（截图时仍在 DOM）',
              bool(toast_text) and any('测试任务执行失败' in x for x in toast_text), CTX['b05'])
        check('B05 toast 描述 = 接口首条 failed 用例 error_message（失败原因一致）',
              bool(first_err) and any(first_err in x for x in (toast_text or [])), CTX['b05'])

        B.set_theme(drv, 'light')
        st, d2 = B.api('/api/v1/tasks?page=1&per_page=10', token)
        CTX['tasks_total_end'] = (d2.get('data') or {}).get('total')
        CTX['bundle_end'] = drv.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src).filter(s=>/index\\.|lib-react/.test(s))")
        check('基线未漂移：index/lib-react 构建哈希开工=收工', CTX['bundle'] == CTX['bundle_end'],
              {'start': CTX['bundle'], 'end': CTX['bundle_end']})
    finally:
        drv.quit()

    failed = [r for r in RESULTS if not r['ok']]
    print('\n==== REWORK2: %d checks, %d failed ====' % (len(RESULTS), len(failed)))
    print('TASKS total start/end:', CTX.get('tasks_total_start'), CTX.get('tasks_total_end'))
    with open(os.path.join(ART, 'evidence_rework2.json'), 'w', encoding='utf-8') as f:
        json.dump({'checks': RESULTS, 'ctx': CTX, 'ts': TS}, f, ensure_ascii=False, indent=1)
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:200])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
