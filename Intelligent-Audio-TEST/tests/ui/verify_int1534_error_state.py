# -*- coding: utf-8 -*-
"""INT-1534 错误态实测：preview 接口失败时弹窗留在配置态 + 错误条 + 错误 toast。
用 fetch 打点合成 500（不依赖后端，仅验证前端错误分支）。"""
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15234')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_试听_浏览器播放')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
ART = os.environ.get('ART_DIR', 'tests/ui/artifacts/int1534-verify')
os.makedirs(ART, exist_ok=True)

PATCH = r"""
window.__failPreview = true;
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  if (window.__failPreview && /\/preview$/.test(url)) {
    window.__previewHit = url;
    return new Response(JSON.stringify({success: false, code: 203,
      message: '音频服务不可用（合成故障）'}), {status: 500,
      headers: {'Content-Type': 'application/json'}});
  }
  return __origFetch.apply(this, arguments);
};
"""


def main():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    drv = webdriver.Chrome(options=o)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    out = {}
    try:
        drv.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
        WebDriverWait(drv, 240).until(
            lambda d: d.find_elements(By.XPATH, "//span[contains(., '%s')]" % GROUP_NAME))
        time.sleep(1.0)
        drv.execute_script('arguments[0].click()', drv.find_element(
            By.XPATH, "//span[contains(@class, 'truncate') and normalize-space(.)='%s']" % GROUP_NAME))
        btn = WebDriverWait(drv, 240).until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
            % CASE_NAME)))
        time.sleep(0.5)
        drv.execute_script('arguments[0].click()', btn)
        WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
        time.sleep(0.8)
        drv.execute_script('arguments[0].click()', drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        time.sleep(2.0)
        out['hit'] = drv.execute_script('return window.__previewHit || null')
        out['dialog'] = drv.find_element(By.XPATH, "//div[@role='dialog']").text
        out['toasts'] = [e.text for e in drv.find_elements(By.XPATH, "//*[@data-sonner-toast]")]
        out['still_config'] = '音频试听配置' in out['dialog']
        drv.save_screenshot(os.path.join(ART, 'E_01_error_state.png'))
        with open(os.path.join(ART, 'result_error.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
