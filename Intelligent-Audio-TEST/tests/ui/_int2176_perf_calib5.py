# -*- coding: utf-8 -*-
"""INT-2176 补证校准 5：大表编辑 Sheet 静置期间的网络请求（是否 refetch 循环）
+ 同一算法详情弹窗静置对照。"""
import importlib.util
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176', 'calib')
os.makedirs(ART, exist_ok=True)
spec = importlib.util.spec_from_file_location('sa', os.path.join(HERE, '_int2121_scroll_audit.py'))
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

JS = r"""
window.__cal = {frames: [], lt: []};
if (window.__cal.po) window.__cal.po.disconnect();
window.__cal.po = new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cal.lt.push(Math.round(e.duration)); });
window.__cal.po.observe({entryTypes:['longtask']});
return 'ok';
"""
STOP = r"""
if(window.__cal.po) window.__cal.po.disconnect();
return {lt: window.__cal.lt.slice().sort((a,b)=>b-a).slice(0,10), lt_count: window.__cal.lt.length};
"""


def net_urls(d):
    urls = []
    for e in d.get_log('performance'):
        m = json.loads(e['message'])['message']
        if m.get('method') == 'Network.requestWillBeSent':
            u = m['params']['request']['url']
            if '/api/' in u:
                urls.append(u.split('?')[0])
    return urls


def main():
    d = sa.make_driver(log_perf=True)
    out = {}
    try:
        sa.ALGO = '接线测试_走查R4_性能R4'
        sa.login(d, 'http://localhost:15173')
        sa.open_edit_sheet(d, 'http://localhost:15173')
        time.sleep(4)
        d.get_log('performance')
        d.execute_script(JS)
        time.sleep(8)
        out['edit_idle'] = d.execute_script(STOP)
        out['edit_net'] = net_urls(d)
        # 详情弹窗
        d.get('http://localhost:15173/AlgorithmConfig')
        time.sleep(4)
        d.execute_script("""
          const vis = e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; };
          const tr = [...document.querySelectorAll('tr')].filter(vis).find(x => (x.innerText||'').includes(arguments[0]));
          if (tr) tr.click();
        """, sa.ALGO)
        time.sleep(5)
        d.get_log('performance')
        d.execute_script(JS)
        time.sleep(8)
        out['detail_idle'] = d.execute_script(STOP)
        out['detail_net'] = net_urls(d)
        out['detail_geo'] = d.execute_script("""
          const dl=[...document.querySelectorAll('[role=dialog]')].pop();
          if(!dl) return null;
          const rows=dl.querySelectorAll('tbody tr').length;
          return {dialog: (dl.innerText||'').slice(0,60), rows};
        """)
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'idle_net.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
