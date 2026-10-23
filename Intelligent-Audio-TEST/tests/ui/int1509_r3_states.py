# -*- coding: utf-8 -*-
"""INT-1509 复测配套：定高容器内错误态 / 空态是否仍完整可见（修复相关部分）。

- 15295：pickable-tasks 返 502 → 错误态「可挑选任务加载失败」+ 重试
- 15296：pickable-tasks 返回空集 → 空态

判据：阶段 1 标题、「全选当前筛选 / 下一步：选择结果」操作栏、状态文案 / 重试按钮
rect 均在视口内，页面文档不整体滚动。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ART = os.environ.get('INT1509_ART', r'D:\00_user_data\.cache\int1509_r3\shots')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
os.makedirs(ART, exist_ok=True)

PROBE_JS = r"""
const out = {innerHeight: window.innerHeight};
const se = document.scrollingElement;
out.docScrollable = se.scrollHeight - se.clientHeight > 4;
const rect = e => { if (!e) return null; const r = e.getBoundingClientRect();
  return {top: Math.round(r.top), bottom: Math.round(r.bottom),
          visible: r.bottom <= window.innerHeight + 0.5 && r.top >= 0, text: (e.textContent||'').trim().slice(0,60)}; };
const btn = t => [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === t);
out.next = rect([...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('下一步：选择结果')));
out.selectAll = rect(btn('全选当前筛选'));
out.clear = rect(btn('清空'));
out.retry = rect([...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '重试'));
const h3 = [...document.querySelectorAll('h3')].find(h => (h.textContent||'').includes('阶段 1'));
out.header = h3 ? Math.round(h3.getBoundingClientRect().top) : null;
out.texts = [...new Set([...document.querySelectorAll('div,p,span')]
  .filter(e => e.children.length === 0)
  .map(e => (e.textContent||'').trim())
  .filter(t => /可挑选|加载失败|暂无|重试/.test(t)))].slice(0, 8);
return out;
"""


def make_driver(w=1440, h=900):
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=%d,%d' % (w, h))
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    return d


def probe(base, tag, wait_text):
    d = make_driver()
    res = {'base': base}
    try:
        d.get(base + '/tasks?tab=cherry-picks')
        WebDriverWait(d, 90).until(
            lambda x: any(b.is_displayed() and '开始挑选' in (b.text or '') for b in x.find_elements(By.TAG_NAME, 'button'))
        )
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and (b.text or '').strip() == '开始挑选':
                d.execute_script('arguments[0].click();', b)
                break
        WebDriverWait(d, 40).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))
        WebDriverWait(d, 60).until(lambda x: wait_text in (x.page_source or ''))
        time.sleep(2)
        res['probe'] = d.execute_script(PROBE_JS)
        time.sleep(0.5)
        p = os.path.join(ART, 'r3_state_%s.png' % tag)
        d.save_screenshot(p)
        res['shot'] = p
    finally:
        d.quit()
    return res


def main():
    out = {
        'error': probe('http://127.0.0.1:15295', 'error', '可挑选任务加载失败'),
        'empty': probe('http://127.0.0.1:15296', 'empty', '暂无可挑选的终态任务'),
    }
    for k, v in out.items():
        print('==', k, json.dumps(v['probe'], ensure_ascii=False))
    p = os.path.join(ART, 'r3_states.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('saved', p)


if __name__ == '__main__':
    main()
