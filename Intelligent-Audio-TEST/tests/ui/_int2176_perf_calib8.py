# -*- coding: utf-8 -*-
"""INT-2176 补证校准 8：大表编辑 Sheet 静置 16s，记录长任务起点以判断是否周期性（草稿自动保存）。"""
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


def main():
    d = sa.make_driver(log_perf=False)
    out = {}
    try:
        sa.ALGO = '接线测试_走查R4_性能R4'
        sa.login(d, 'http://localhost:15173')
        sa.open_edit_sheet(d, 'http://localhost:15173')
        time.sleep(5)
        d.execute_script(r"""
          window.__lt = [];
          if (window.__ltp) window.__ltp.disconnect();
          window.__ltp = new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push({start: Math.round(e.startTime), dur: Math.round(e.duration)}); });
          window.__ltp.observe({entryTypes:['longtask']});
        """)
        time.sleep(16)
        out['idle_16s'] = d.execute_script("window.__ltp.disconnect(); return window.__lt;")
    finally:
        d.quit()
    lt = out['idle_16s']
    starts = [x['start'] for x in lt]
    out['durations'] = [x['dur'] for x in lt]
    out['gaps'] = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'idle_periodicity.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
