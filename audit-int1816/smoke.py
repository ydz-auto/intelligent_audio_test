"""INT-1816 实测：评估维度新建默认值 + 健康测试空态（临时脚本，不提交）。"""
import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5388'

CAPTURE_JS = """
window.__caps = [];
const __origFetch = window.fetch;
window.fetch = async (...args) => {
  let rec = null;
  try {
    const input = args[0];
    const init = args[1] || {};
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    if (method !== 'GET') {
      rec = { url: String(url), method, body: typeof init.body === 'string' ? init.body : '(non-string)' };
      window.__caps.push(rec);
    }
  } catch (e) {}
  const resp = await __origFetch.apply(window, args);
  try {
    if (rec) {
      const clone = resp.clone();
      clone.text().then((t) => { rec.response = t.slice(0, 2000); rec.status = resp.status; }).catch(() => {});
    }
  } catch (e) {}
  return resp;
};
"""


def js(drv, script, *args):
    return drv.execute_script(script, *args)


def wait_text(drv, text, timeout=40):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.find_element(By.TAG_NAME, 'body').text
    )


def main():
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1100')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    drv = webdriver.Chrome(options=opts)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': CAPTURE_JS})
    drv.set_window_size(1600, 1100)
    out = {}
    try:
        drv.get(f'{BASE}/Evaluation')
        WebDriverWait(drv, 60).until(
            lambda d: '新增维度' in d.find_element(By.TAG_NAME, 'body').text
            or 'login' in d.current_url.lower()
        )
        time.sleep(1.5)
        out['url'] = drv.current_url
        out['body_head'] = drv.find_element(By.TAG_NAME, 'body').text[:600]
        drv.save_screenshot('audit-int1816/00-page.png')
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
