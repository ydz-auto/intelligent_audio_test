# -*- coding: utf-8 -*-
"""INT-2358 补充实测：详情计数缓存（staleTime 30s）——关闭后立即重开弹窗不重复打详情接口。

用法：python verify_int2358_reopen_cache.py --base http://localhost:15258
只读，输出 tests/ui/artifacts/int2358_cache/run.log。
"""
import argparse
import json
import os
import sys
import time

from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify_int2358_param_profile_counts import (  # noqa: E402
    _driver,
    collect_requests,
    login,
    open_manager,
    read_rows,
    top_dialog,
    wait_for,
)

ART = os.path.join(HERE, 'artifacts', 'int2358_cache')
os.makedirs(ART, exist_ok=True)


def log(msg):
    print(msg)
    with open(os.path.join(ART, 'run.log'), 'a', encoding='utf-8') as fh:
        fh.write(msg + '\n')


def detail_count(drv):
    reqs = collect_requests(drv)
    det = [r for r in reqs if '/param-profiles/' in r['url']]
    return len(det), [(r['status'], r['url'].split('/api/v1')[-1]) for r in det]


def reopen_dialog(drv):
    """不刷新页面，仅再点「参数策略」打开弹窗（保持 react-query 缓存）。"""
    btn = wait_for(
        lambda: drv.find_elements(By.XPATH, "//button[normalize-space(.)='参数策略']"),
        timeout=30, desc='「参数策略」按钮',
    )
    drv.execute_script('arguments[0].click()', btn[0])
    dlg = wait_for(lambda: top_dialog(drv), timeout=30, desc='弹窗重开')
    wait_for(lambda: read_rows(dlg), timeout=30, desc='列表行')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15258')
    args = ap.parse_args()
    errors = []
    drv = _driver()
    try:
        login(drv, args.base)
        open_manager(drv, args.base, log)
        wait_for(lambda: all(r['paramCount'].isdigit() for r in read_rows(top_dialog(drv))),
                 timeout=45, desc='首次计数')
        n1, urls1 = detail_count(drv)
        log('OPEN#1 detail_requests=%d %s' % (n1, json.dumps(urls1, ensure_ascii=False)))
        dlg = top_dialog(drv)
        drv.execute_script(
            'arguments[0].click()',
            dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"),
        )
        wait_for(lambda: top_dialog(drv) is None, timeout=20, desc='关闭弹窗')
        time.sleep(1.0)
        reopen_dialog(drv)
        rows = wait_for(lambda: (lambda r: r if r and all(x['paramCount'].isdigit() for x in r) else None)(
            read_rows(top_dialog(drv))), timeout=30, desc='重开计数')
        n2, urls2 = detail_count(drv)
        log('OPEN#2 detail_requests=%d %s' % (n2, json.dumps(urls2, ensure_ascii=False)))
        if n1 != 6:
            errors.append('首次打开详情请求数 %d != 6' % n1)
        if n2 != 0:
            errors.append('30s 内重开仍重复请求详情 %d 次' % n2)
        log('rows after reopen: %s' % json.dumps(
            [(r['algorithm'], r['scope'], r['paramCount'], r['mappingCount']) for r in rows],
            ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        errors.append('异常：%r' % exc)
    finally:
        log('RESULT %s errors=%s' % ('PASS' if not errors else 'FAIL',
                                     json.dumps(errors, ensure_ascii=False)))
        try:
            drv.quit()
        except Exception:
            pass
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
