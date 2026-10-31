# -*- coding: utf-8 -*-
"""INT-2176 补证校准 3：空白页 / 列表页 / 抽屉页 静置长任务对比（定位 1s 停顿来源）。"""
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
try {
  window.__cal.po = new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cal.lt.push(Math.round(e.duration)); });
  window.__cal.po.observe({entryTypes:['longtask']});
} catch (e) { window.__cal.err = String(e); }
window.__last = performance.now(); window.__on = true;
window.__tick = t => { if(!window.__on) return; window.__cal.frames.push(t - window.__last); window.__last = t; window.__raf = requestAnimationFrame(window.__tick); };
window.__raf = requestAnimationFrame(window.__tick);
return 'ok';
"""
STOP = r"""
window.__on = false; if(window.__raf) cancelAnimationFrame(window.__raf); if(window.__cal.po) window.__cal.po.disconnect();
const f = window.__cal.frames.slice(2).sort((a,b)=>a-b);
return {n: f.length, median: f.length ? +f[Math.floor(f.length/2)].toFixed(2) : null,
        p95: f.length ? +f[Math.min(f.length-1, Math.floor(f.length*.95))].toFixed(2) : null,
        max: f.length ? +f[f.length-1].toFixed(2) : null,
        lt: window.__cal.lt.slice().sort((a,b)=>b-a).slice(0,8), lt_count: window.__cal.lt.length, err: window.__cal.err || null};
"""


def sample(d, secs=8.0):
    d.execute_script(JS)
    time.sleep(secs)
    return d.execute_script(STOP)


def main():
    d = sa.make_driver(log_perf=False)
    out = {}
    try:
        sa.login(d, 'http://localhost:15173')
        d.get('about:blank')
        time.sleep(1)
        out['blank'] = sample(d, 8)
        d.get('http://localhost:15173/dashboard')
        time.sleep(4)
        out['dashboard'] = sample(d, 8)
        d.get('http://localhost:15173/AlgorithmConfig')
        time.sleep(5)
        out['algo_list'] = sample(d, 8)
        # 打开大表编辑 Sheet 静置
        sa.ALGO = '接线测试_走查R4_性能R4'
        sa.open_edit_sheet(d, 'http://localhost:15173')
        time.sleep(6)
        out['sheet_idle'] = sample(d, 8)
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'stall_source.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
