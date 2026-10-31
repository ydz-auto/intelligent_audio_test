# -*- coding: utf-8 -*-
"""INT-2176 补证校准 6：大表编辑 Sheet「全展开」vs「全折叠」静置长任务，
判定 1s 级停顿是否由 1846 行 DOM 驱动（而非宿主）。"""
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
        out['expanded'] = d.execute_script(sa.TABLE_STATS_JS)
        out['expanded_idle'] = sample(d, 6)
        # 全部折叠
        out['collapse_click'] = d.execute_script(r"""
          const t = window.__evalTable; if (!t) return {ok:false};
          const heads = [...t.querySelectorAll('tbody button[aria-expanded="true"]')]
            .filter(b => /条\s*$/.test((b.innerText || '').replace(/\s+/g, ' ')));
          heads.forEach(h => h.click());
          return {ok:true, collapsed: heads.length};
        """)
        time.sleep(2.5)
        out['collapsed'] = d.execute_script(sa.TABLE_STATS_JS)
        out['collapsed_idle'] = sample(d, 6)
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'collapse_idle.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
