# -*- coding: utf-8 -*-
"""INT-2176 覆盖 7/8：report 381 用例 JG0242 轮次轴切换与评分指标数值一致（真实栈只读）。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('r', os.path.join(HERE, '_int2176_report.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

ART = os.path.join(HERE, 'artifacts', 'int2176', 'report')
RES = {}


JS_OPEN = r"""
const innermost = [...document.querySelectorAll('*')].filter(vis)
  .find(e => (e.textContent||'').includes('JG0242') &&
             [...e.children].every(c => !(c.textContent||'').includes('JG0242')));
if(!innermost) return {ok:false, why:'no text el'};
let el = innermost;
for(let i=0;i<10 && el;i++){
  const b=[...el.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').trim()==='详情');
  if(b){ b.scrollIntoView({block:'center'}); b.click(); return {ok:true, depth:i}; }
  el = el.parentElement;
}
return {ok:false, why:'no detail btn'};
"""


def case_dialog_metrics(d):
    return d.execute_script(r.JS_VIS + """
      const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
      if(!dl) return {ok:false};
      const secs=[...dl.querySelectorAll('section')];
      const sec=secs.find(s=>(s.innerText||'').includes('评分指标'));
      const rows=sec?[...sec.querySelectorAll('table tr')].map(tr=>[...tr.querySelectorAll('th,td')].map(c=>(c.innerText||'').trim())):[];
      const bars=[...dl.querySelectorAll('[role=tablist]')].filter(b=>vis(b));
      const tabs=bars.map(b=>({label:b.getAttribute('aria-label'),items:[...b.querySelectorAll('[role=tab]')].filter(vis).map(t=>({t:(t.innerText||'').trim(),sel:t.getAttribute('aria-selected')}))}));
      const full=dl.innerText||'';
      return {ok:true, rows:rows, tabs:tabs, has_multi_round: full.includes('多轮对话结果'),
              exec_rounds: (full.match(/第\\s*\\d+\\s*轮/g)||[]).slice(0,10),
              has_execution: full.includes('执行结果'), len: full.length};
    """)


def click_tab(d, label):
    out = d.execute_script(r.JS_VIS + """
      const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
      if(!dl) return {ok:false, why:'no dialog'};
      const bars=[...dl.querySelectorAll('[role=tablist]')].filter(b=>(b.getAttribute('aria-label')||'')==='轮次切换' && vis(b));
      if(!bars.length) return {ok:false, why:'no round bar'};
      const t=[...bars[0].querySelectorAll('[role=tab]')].find(x=>(x.innerText||'').trim()===arguments[0]);
      if(!t) return {ok:false, why:'no tab', items:[...bars[0].querySelectorAll('[role=tab]')].map(x=>x.innerText)};
      t.click(); return {ok:true};
    """, label)
    time.sleep(2.2)
    return out


def main():
    d = r.driver()
    try:
        r.login(d)
        d.get(r.BASE + '/report/381')
        r.ready(d, 7)
        RES['page_len'] = len(r.body_text(d))
        opened = d.execute_script(r.JS_VIS + JS_OPEN)
        time.sleep(3)
        RES['open'] = opened
        RES['initial'] = case_dialog_metrics(d)
        r.shot(d, '08-round381-initial-light')
        seq = []
        for lb in ['第 2 轮', '第 4 轮', '整体']:
            clk = click_tab(d, lb)
            st = case_dialog_metrics(d)
            # 提取接管时延平均值行
            lat = None
            for row in (st.get('rows') or []):
                if row and str(row[0]).startswith('接管时延平均值'):
                    lat = row
            seq.append({'tab': lb, 'click': clk, 'latency_row': lat,
                        'tabs': (st.get('tabs') or [{}]),
                        'has_execution': st.get('has_execution'),
                        'has_multi_round': st.get('has_multi_round'),
                        'exec_rounds': st.get('exec_rounds')})
            r.shot(d, '09-round381-' + lb.replace(' ', '') + '-light')
        RES['sequence'] = seq
        # 深色
        RES['dark'] = r.set_theme(d, 'dark', r.BASE + '/report/381')
        d.execute_script(r.JS_VIS + JS_OPEN)
        time.sleep(3)
        click_tab(d, '第 2 轮')
        r.shot(d, '10-round381-round2-dark')
        RES['dark_state'] = case_dialog_metrics(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    open(os.path.join(ART, 'round381.json'), 'w', encoding='utf-8').write(
        json.dumps(RES, ensure_ascii=False, indent=2))
    print('done')


if __name__ == '__main__':
    main()
