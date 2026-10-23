# -*- coding: utf-8 -*-
"""INT-1642 补充取证：批量设置评估维度「逐轮设置」轮次 Tab（真实轮次，1 轮 / 3 轮）。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1642_usercase_fixes as v

OUT = {}


def per_round_tabs(d, search_text, dark=False):
    d.get(v.BASE + '/testcases')
    v.wait_body(d, '用例管理', 60)
    if dark:
        v.js(d, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get(v.BASE + '/testcases')
        v.wait_body(d, '用例管理', 60)
    time.sleep(2)
    v.set_search(d, search_text)
    v.expand_group(d, '拒识')
    cbs = v.card_checkboxes(d)
    if not cbs:
        return {'error': 'no card'}
    v.js_click(d, cbs[0])
    v.wait_fn(d, lambda: '个用例已选择' in v.body_text(d), 20)
    v.click_btn(d, '批量设置评估维度', 20)
    v.wait_body(d, '批量设置评估维度', 20)
    time.sleep(1.0)
    lab = next((l for l in d.find_elements(By.TAG_NAME, 'label')
                if '逐轮设置' in (v.text_of(d, l) or '')), None)
    if lab is None:
        return {'error': 'per-round label not found'}
    v.js_click(d, lab)
    time.sleep(1.2)
    tabs = v.js(d, """
      const dlg = document.querySelector('[role="dialog"]');
      if (!dlg) return [];
      const out = [];
      Array.from(dlg.querySelectorAll('button')).forEach(function(b){
        const t = (b.innerText||'').trim();
        if (/^(第\\d+轮|最后一轮)$/.test(t)) out.push(t);
      });
      return out;
    """)
    # 指定轮次网格（同一单轮用例）
    return {'tabs': tabs}


d = v.make_driver()
try:
    OUT['per_round_1round_light'] = per_round_tabs(d, '测试用例_JS115_单轮拒识')
    v.shot(d, '15_batch_per_round_1round_light')
    v.click_btn(d, '取消', 20)
    time.sleep(0.8)
    OUT['per_round_3round_light'] = per_round_tabs(d, '测试用例_JS172_多轮拒识')
    v.shot(d, '16_batch_per_round_3round_light')
    v.click_btn(d, '取消', 20)
    time.sleep(0.8)
    OUT['per_round_3round_dark'] = per_round_tabs(d, '测试用例_JS172_多轮拒识', dark=True)
    v.shot(d, '26_batch_per_round_3round_dark')
finally:
    d.quit()

with open(os.path.join(v.ART, 'results_per_round.json'), 'w', encoding='utf-8') as fh:
    json.dump(OUT, fh, ensure_ascii=False, indent=2)
print(json.dumps(OUT, ensure_ascii=True))
