# -*- coding: utf-8 -*-
"""INT-2358 补充实测：详情计数未返回 / 请求失败时，行内应显示「—」而不是误报 0。

用法（修复侧旁路容器）：
  python verify_int2358_pending_states.py --base http://localhost:15258

步骤：
  A. 打开弹窗 → 关闭，CDP 给网络加 3s 延迟后重开 → 行已渲染但详情未回时读「字段 / 映射」，
     断言为「—」（未知不渲染成 0）；解除延迟后等待变为真实数字。
  B. Network.setBlockedURLs 屏蔽 /algorithm/param-profiles/{id} 后刷新页面重开弹窗 →
     断言计数仍为「—」、页面不崩（列表正常）；解除屏蔽后恢复。
只读，不写任何数据。输出 tests/ui/artifacts/int2358_states/。
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
    console_severe,
    login,
    open_manager,
    read_rows,
    shot,
    top_dialog,
    wait_for,
)

ART = os.path.join(HERE, 'artifacts', 'int2358_states')
os.makedirs(ART, exist_ok=True)


def log(msg):
    print(msg)
    with open(os.path.join(ART, 'run.log'), 'a', encoding='utf-8') as fh:
        fh.write(msg + '\n')


def cells(rows):
    return [(r['algorithm'], r['scope'], r['paramCount'], r['mappingCount']) for r in rows]


def close_dialog(drv):
    dlg = top_dialog(drv)
    btn = dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='关闭']")
    if btn:
        drv.execute_script('arguments[0].click()', btn[-1])
    wait_for(lambda: top_dialog(drv) is None, timeout=20, desc='弹窗关闭')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15258')
    args = ap.parse_args()
    errors = []
    drv = _driver()
    try:
        login(drv, args.base)
        open_manager(drv, args.base, log)
        wait_for(lambda: all(c[2].isdigit() for c in cells(read_rows(top_dialog(drv)))),
                 timeout=45, desc='首次计数加载')
        close_dialog(drv)

        # A. 延迟 3s：列表回、详情未回 → 「—」
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 3000,
            'downloadThroughput': 8 * 1024 * 1024, 'uploadThroughput': 4 * 1024 * 1024,
        })
        open_manager(drv, args.base, log)
        pending = wait_for(
            lambda: (lambda rows: rows if rows and any(
                r['paramCount'] == '—' or r['mappingCount'] == '—' for r in rows) else None)(
                read_rows(top_dialog(drv))),
            timeout=30, desc='详情未返回时的「—」状态', interval=0.2,
        )
        shot(drv, ART, 'pending_dash.png')
        log('PENDING rows: %s' % json.dumps(cells(pending), ensure_ascii=False))
        if any(r['paramCount'] == '0' and r['mappingCount'] == '0' for r in pending):
            errors.append('加载中出现了误报的 0/0：%r' % cells(pending))
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 0,
            'downloadThroughput': -1, 'uploadThroughput': -1,
        })
        settled = wait_for(
            lambda: (lambda rows: rows if rows and all(
                r['paramCount'].isdigit() and r['mappingCount'].isdigit() for r in rows) else None)(
                read_rows(top_dialog(drv))),
            timeout=45, desc='解除延迟后计数补齐',
        )
        log('SETTLED rows: %s' % json.dumps(cells(settled), ensure_ascii=False))
        close_dialog(drv)
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/algorithm/param-profiles/*']})

        # B. 详情接口失败 → 「—」，列表仍可用
        drv.get(args.base + '/AlgorithmConfig')
        wait_for(lambda: drv.find_elements(By.XPATH, "//button[normalize-space(.)='参数策略']"),
                 timeout=60, desc='算法配置页')
        drv.execute_script(
            'arguments[0].click()',
            drv.find_element(By.XPATH, "//button[normalize-space(.)='参数策略']"),
        )
        dlg = wait_for(lambda: top_dialog(drv), timeout=30, desc='弹窗')
        wait_for(lambda: read_rows(dlg), timeout=30, desc='列表行')
        time.sleep(4.0)
        rows = read_rows(dlg)
        shot(drv, ART, 'error_dash.png')
        log('ERROR-STATE rows: %s' % json.dumps(cells(rows), ensure_ascii=False))
        if not rows:
            errors.append('详情失败时列表未渲染')
        if any(r['paramCount'] != '—' or r['mappingCount'] != '—' for r in rows):
            errors.append('详情失败时应全部显示 —：%r' % cells(rows))
        severe = console_severe(drv)
        log('ERROR-STATE console: %r' % severe[:4])
        # 屏蔽请求产生的 net::ERR_* 属预期错误注入，不判缺陷；只要不是白屏 / JS 异常
        if any('Uncaught' in s or 'TypeError' in s for s in severe):
            errors.append('错误态出现 JS 异常：%r' % severe[:3])

        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
        drv.refresh()
        time.sleep(1.0)
    except Exception as exc:  # noqa: BLE001
        errors.append('异常：%r' % exc)
        try:
            shot(drv, ART, 'error_state.png')
        except Exception:
            pass
    finally:
        log('RESULT %s errors=%s' % ('PASS' if not errors else 'FAIL',
                                     json.dumps(errors, ensure_ascii=False)))
        with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump({'errors': errors, 'passed': not errors}, fh, ensure_ascii=False, indent=2)
        try:
            drv.quit()
        except Exception:
            pass
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
