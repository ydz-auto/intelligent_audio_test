# -*- coding: utf-8 -*-
"""INT-1484 复验段 (4)-P3-3 取证：新建维度 → API配置 → 端点 URL/名称 初始为空（截图到端点行）。

复用 verify_int1484_retest_int1732 的浏览器/选择器工具；只打开新建抽屉，不提交、不写库。
输出：tests/ui/artifacts/int1484_create_endpoints/01_light.png + 02_dark.png + run.log
"""
import argparse
import json
import os
import sys
import time

from verify_int1484_retest_int1732 import (
    PROJECT_ROOT,
    _driver,
    close_sheet,
    open_api_tab,
    set_theme,
    shot,
    wait_for,
)
from selenium.webdriver.common.by import By


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    artifacts = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1484_create_endpoints')
    os.makedirs(artifacts, exist_ok=True)
    report = {'base': base}
    drv = _driver()
    try:
        drv.get(base + '/Evaluation')
        wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
                 timeout=90, desc='/Evaluation 渲染')
        time.sleep(1.0)
        btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.),'新增维度')]")
        assert btns, '未找到「新增维度」'
        drv.execute_script('arguments[0].click()', btns[0])
        wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='新增维度抽屉')
        open_api_tab(drv)
        url_el = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="端点 URL 1"]')
        name_el = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="端点名称 1"]')
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', url_el)
        time.sleep(0.6)
        report['endpoint_url'] = url_el.get_attribute('value')
        report['endpoint_name'] = name_el.get_attribute('value')
        master = drv.find_elements(By.CSS_SELECTOR, 'input[placeholder*="Master"]')
        report['master_url'] = master[0].get_attribute('value') if master else None
        set_theme(drv, 'light')
        shot(drv, artifacts, '01_light.png')
        set_theme(drv, 'dark')
        shot(drv, artifacts, '02_dark.png')
        set_theme(drv, 'light')
        assert report['endpoint_url'] == '', '端点 URL 非空: %r' % report['endpoint_url']
        assert report['endpoint_name'] == '', '端点名称非空: %r' % report['endpoint_name']
        report['ok'] = True
    except Exception as exc:  # noqa: BLE001
        report['ok'] = False
        report['error'] = repr(exc)
        raise
    finally:
        try:
            close_sheet(drv)
        except Exception:
            pass
        with open(os.path.join(artifacts, 'run.log'), 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
