# -*- coding: utf-8 -*-
"""诊断：复现 verify_int1499_fullchain.py 里 pickable_backend 的页面内 fetch（light 阶段两条 CHECK 失败）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1499_fullchain as V  # noqa: E402

d = V.driver()
try:
    d.get(V.BASE + '/')
    V.login(d)
    d.get(V.BASE + '/tasks?tab=cherry-picks')
    time.sleep(5)
    for i in range(2):
        t0 = time.time()
        out = d.execute_script('''
          return (async () => {
            var t = localStorage.getItem('iatp:auth:token:v1');
            if(!t) return {error:'no-token'};
            var r = await fetch('/api/v1/tasks/cherry-picks/pickable-tasks?page=1&per_page=200&sort_by=status&sort_order=asc', {headers:{Authorization:'Bearer '+t}});
            var txt = await r.text();
            var j; try { j = JSON.parse(txt); } catch(e) { return {error:'parse', status:r.status, head:txt.slice(0,200)}; }
            var dd = j.data||j;
            var dist = {};
            (dd.items||[]).forEach(function(i){var k=i.execution_status||'?';dist[k]=(dist[k]||0)+1;});
            return {http:r.status, total:dd.total, loaded:(dd.items||[]).length, dist:dist};
          })()''')
        print('TRY%d %.1fs' % (i, time.time() - t0), json.dumps(out, ensure_ascii=False)[:500])
finally:
    d.quit()
