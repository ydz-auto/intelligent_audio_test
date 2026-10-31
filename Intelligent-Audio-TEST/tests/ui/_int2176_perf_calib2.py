# -*- coding: utf-8 -*-
"""INT-2176 补证校准 2：大表编辑 Sheet 静置 vs 短滚 vs 长滚；并测非表格区滚动。"""
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
if (window.__cal.po) window.__cal.po.disconnect();
window.__cal.po = new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cal.lt.push(e.duration); });
window.__cal.po.observe({entryTypes:['longtask']});
window.__last = performance.now(); window.__on = true;
window.__tick = t => { if(!window.__on) return; window.__cal.frames.push(t - window.__last); window.__last = t; window.__raf = requestAnimationFrame(window.__tick); };
window.__raf = requestAnimationFrame(window.__tick);
return 'ok';
"""

IDLE_STOP_JS = r"""
window.__on = false; if(window.__raf) cancelAnimationFrame(window.__raf); if(window.__cal.po) window.__cal.po.disconnect();
const f = window.__cal.frames.slice(2).sort((a,b)=>a-b);
const pct = p => f.length ? +f[Math.min(f.length-1, Math.floor(f.length*p))].toFixed(2) : null;
return {n: f.length, median: f.length ? +f[Math.floor(f.length/2)].toFixed(2) : null,
        p95: pct(0.95), max: f.length ? +f[f.length-1].toFixed(2) : null,
        longtasks: window.__cal.lt.length, lt_max: window.__cal.lt.length ? Math.max(...window.__cal.lt) : 0};
"""


def idle(d, secs=3.0):
    d.execute_script(IDLE_JS)
    time.sleep(secs)
    return d.execute_script(IDLE_STOP_JS)


def wheel(d, geo, n, delta, interval=0.1):
    for _ in range(n):
        d.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': 'mouseWheel', 'x': geo['x'], 'y': geo['y'],
            'deltaX': 0, 'deltaY': delta, 'pointerType': 'mouse',
        })
        time.sleep(interval)


def main():
    sa.ALGO = sys.argv[1] if len(sys.argv) > 1 else '接线测试_走查R4_性能R4'
    d = sa.make_driver(log_perf=False)
    out = {'algo': sa.ALGO}
    try:
        sa.login(d, 'http://localhost:15173')
        d.get('http://localhost:15173/AlgorithmConfig')
        time.sleep(4)
        sa.open_edit_sheet(d, 'http://localhost:15173')
        out['geo'] = d.execute_script(sa.SCROLL_TO_TABLE_JS)
        out['stats'] = d.execute_script(sa.TABLE_STATS_JS)
        # 静置 8s 后采样（排除首次渲染尾流）
        time.sleep(8)
        out['idle_after_8s'] = idle(d, 3.0)
        # 短滚 10 步
        d.execute_script("document.querySelector('#algorithm-mutate-form').scrollTop = 0;")
        time.sleep(1)
        out['idle_top'] = idle(d, 2.0)
        d.execute_script(sa.START_JS)
        time.sleep(0.3)
        wheel(d, out['geo'], 10, 120)
        d.execute_script('window.__rec.scrollEnd = performance.now();')
        time.sleep(0.8)
        data = d.execute_script(sa.STOP_JS)
        out['short_scroll_10'] = sa.stats(data['frames'], data['longtasks'], data.get('t0'), data.get('scrollEnd'))
        # 长滚 40 步
        d.execute_script("document.querySelector('#algorithm-mutate-form').scrollTop = 0;")
        time.sleep(1)
        out['long_scroll_40'] = sa.measure_round(d, 40, 120, 1, 0.1)[0]
        # 非表格区：滚到顶部参数区再滚
        d.execute_script("document.querySelector('#algorithm-mutate-form').scrollTop = 0;")
        time.sleep(1)
        geo_top = dict(out['geo'])
        geo_top['y'] = 200
        out['non_table_idle'] = idle(d, 2.0)
        d.execute_script(sa.START_JS)
        time.sleep(0.3)
        wheel(d, geo_top, 10, 120)
        d.execute_script('window.__rec.scrollEnd = performance.now();')
        time.sleep(0.8)
        data = d.execute_script(sa.STOP_JS)
        out['non_table_scroll_10'] = sa.stats(data['frames'], data['longtasks'], data.get('t0'), data.get('scrollEnd'))
    finally:
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'calib_big_steps.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
