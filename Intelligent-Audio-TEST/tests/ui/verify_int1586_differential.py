# -*- coding: utf-8 -*-
"""INT-1586 验收对照脚本：同一断言的「已修 / 未修」两态区分力验证。

用法：
  python verify_int1586_differential.py --expect fixed    # 当前交付分支
  python verify_int1586_differential.py --expect broken   # 临时回退 roles-page/use-roles-query 基线

仅覆盖两条最能区分修复的核心断言：
  A. 新建态名称留空点「创建」→ 零请求 + 红字 + aria-invalid + 弹窗仍开（未修时：发 POST 且弹窗关闭）
  B. 后端 400（重名 admin）→ 弹窗保持打开且 toast = 后端 message（未修时：弹窗关闭 + 通用「角色保存失败」）
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5387')
OUT = os.environ.get('DIFF_OUT', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              'reports', 'int1586_differential.json'))
DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
expect = 'fixed'
if '--expect' in sys.argv:
    expect = sys.argv[sys.argv.index('--expect') + 1]

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const res = await __origFetch.apply(this, arguments);
  let text = '';
  try { text = await res.clone().text(); } catch (e) {}
  window.__net.push({url: url, method: method, status: res.status, resp: (text || '').slice(0, 400)});
  return res;
};
"""


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def net(drv):
    return [r for r in drv.execute_script('return window.__net || [];')
            if r['method'] in ('POST', 'PUT', 'DELETE') and '/auth/roles' in r['url']
            and '/permissions' not in r['url']]


def dialog_open(drv):
    return bool(drv.find_elements(By.XPATH, "//div[@role='dialog']"))


def aria_invalid(drv):
    els = drv.find_elements(By.ID, 'role-name')
    return els[0].get_attribute('aria-invalid') if els else None


def errors(drv):
    return [e.text.strip() for e in drv.find_elements(
        By.CSS_SELECTOR, "[role='dialog'] p.text-destructive") if e.text.strip()]


def toasts(drv):
    return [e.text.strip().replace('\n', ' ') for e in drv.find_elements(
        By.CSS_SELECTOR, '[data-sonner-toast]') if e.text.strip()]


def main():
    drv = webdriver.Chrome(service=Service(executable_path=DRIVER), options=opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    result = {'expect': expect, 'base': BASE}
    try:
        drv.get(BASE + '/system-settings/iam/roles')
        WebDriverWait(drv, 90).until(EC.presence_of_element_located(
            (By.XPATH, "//button[contains(normalize-space(.), '新建角色')]")))
        time.sleep(1.5)

        # A. 空名提交
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '新建角色')]"))
        WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
        time.sleep(0.5)
        drv.execute_script('window.__net = [];')
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='创建']"))
        time.sleep(2)
        result['A_empty_name'] = {
            'writes': net(drv), 'errors': errors(drv),
            'aria_invalid': aria_invalid(drv),
            'dialog_open': dialog_open(drv),
        }

        # B. 重名 admin 提交 → 后端 400
        if dialog_open(drv):
            el = drv.find_element(By.ID, 'role-name')
            js_click(drv, el)
            el.send_keys(Keys.CONTROL, 'a')
            el.send_keys(Keys.DELETE)
            el.send_keys('admin')
            drv.execute_script('window.__net = [];')
            js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='创建']"))
            if not dialog_open(drv):
                result['B_backend_400'] = {'skipped': 'dialog was already closed'}
            else:
                WebDriverWait(drv, 30).until(lambda d: net(d))
                time.sleep(1.8)
                result['B_backend_400'] = {
                    'writes': net(drv), 'toasts': toasts(drv),
                    'dialog_open': dialog_open(drv),
                    'name_value': drv.find_element(By.ID, 'role-name').get_attribute('value')
                    if dialog_open(drv) else None,
                }
        else:
            result['B_backend_400'] = {'skipped': 'dialog closed after A (broken behaviour)'}
    finally:
        drv.quit()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    a = result['A_empty_name']
    b = result.get('B_backend_400', {})
    ok = (
        not a['writes'] and '请输入角色名称' in a['errors']
        and a['aria_invalid'] == 'true' and a['dialog_open']
        and b.get('writes') and b['writes'][0]['status'] == 400
        and any('角色名已存在' in t for t in b.get('toasts', []))
        and b.get('dialog_open') and b.get('name_value') == 'admin'
    )
    verdict = 'PASS(fixed-behaviour)' if ok else 'FAIL'
    print(json.dumps({'verdict': verdict, **result}, ensure_ascii=False, indent=2))
    if expect == 'fixed':
        return 0 if ok else 1
    return 0 if not ok else 1


def opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1100')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


if __name__ == '__main__':
    sys.exit(main())
