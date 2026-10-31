# -*- coding: utf-8 -*-
"""INT-2176 补证校准：区分「宿主资源饥饿」与「大表滚动本身掉帧」。
同机同时段采样：空白页 / 小表编辑 Sheet / 大表编辑 Sheet 静置 / 大表滚动 1 轮。
"""
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176', 'calib')
os.makedirs(ART, exist_ok=True)

spec = importlib.util.spec_from_file_location('sa', os.path.join(HERE, '_int2121_scroll_audit.py'))
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

IDLE_JS = r"""
window.__cal = {frames: [], lt: []};
try { window.__cal.po && window.__cal.po.disconnect(); window.__cal.po = new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cal.lt.push(e.duration); }); window.__cal.po.observe({entryTypes:['longtask']}); } catch(e) {}
window.__last = performance.now(); window.__on = true;
window.__tick = t => { if(!window.__on) return; window.__cal.frames.push(t - window.__last); window.__last = t; window.__raf = requestAnimationFrame(window.__tick); };
window.__raf = requestAnimationFrame(window.__tick);
return 'ok';
"""

IDLE_STOP_JS = r"""
window.__on = false; if(window.__raf) cancelAnimationFrame(window.__raf); if(window.__cal.po) window.__cal.po.disconnect();
const f = window.__cal.frames.slice(2);
f.sort((a,b)=>a-b);
const pct = p => f.length ? +f[Math.min(f.length-1, Math.floor(f.length*p))].toFixed(2) : null;
return {n: f.length, median: f.length ? +f[Math.floor(f.length/2)].toFixed(2) : null,
        p95: pct(0.95), max: f.length ? +f[f.length-1].toFixed(2) : null,
        longtasks: window.__cal.lt.length, lt_max: window.__cal.lt.length ? Math.max(...window.__cal.lt) : 0};
"""


def main():
    sa.ALGO = sys.argv[1] if len(sys.argv) > 1 else '接线测试_走查R4_编辑映射4'
    d = sa.make_driver(log_perf=False)
    out = {'algo': sa.ALGO}
    try:
        sa.login(d, 'http://localhost:15173')
        # 空白页
        d.get('about:blank')
        time.sleep(0.5)
        d.execute_script(IDLE_JS)
        time.sleep(3.0)
        out['blank_page'] = d.execute_script(IDLE_STOP_JS)
        # 小表编辑 Sheet
        sa.open_edit_sheet(d, 'http://localhost:15173')
        time.sleep(2)
        out['small_geo'] = d.execute_script(sa.SCROLL_TO_TABLE_JS)
        d.execute_script(IDLE_JS)
        time.sleep(3.0)
        out['small_idle'] = d.execute_script(IDLE_STOP_JS)
        r, geo, _ = sa.measure_round(d, 40, 120, 1, 0.1)
        out['small_scroll_1x'] = r
        out['small_scroll_geo'] = geo
        out['small_rows'] = d.execute_script(sa.TABLE_STATS_JS)
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'calib_small.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
