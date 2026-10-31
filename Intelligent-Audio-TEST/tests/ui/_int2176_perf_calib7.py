# -*- coding: utf-8 -*-
"""INT-2176 补证校准 7：大表编辑 Sheet 分组全展开 vs 平铺视图（10 行/页）静置对比。"""
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
const lt = window.__cal.lt.slice().sort((a,b)=>b-a);
return {lt_count: lt.length, lt_top: lt.slice(0,8), lt_sum: lt.reduce((a,b)=>a+b,0)};
"""


def sample(d, secs=6.0):
    d.execute_script(JS)
    time.sleep(secs)
    return d.execute_script(STOP)


def main():
    d = sa.make_driver(log_perf=False)
    out = {}
    try:
        sa.ALGO = '接线测试_走查R4_性能R4'
        sa.login(d, 'http://localhost:15173')
        sa.open_edit_sheet(d, 'http://localhost:15173')
        time.sleep(5)
        out['grouped'] = d.execute_script(sa.TABLE_STATS_JS)
        out['grouped_idle'] = sample(d, 6)
        out['to_flat'] = d.execute_script("""
          const root = window.__evalRoot;
          const b = [...root.querySelectorAll('button')].find(x => (x.innerText || '').trim() === '平铺视图');
          if (!b) return {ok:false};
          b.click(); return {ok:true};
        """)
        time.sleep(3)
        out['flat'] = d.execute_script(sa.TABLE_STATS_JS)
        out['flat_idle'] = sample(d, 6)
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'flat_idle.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
