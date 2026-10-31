# -*- coding: utf-8 -*-
"""INT-2176 覆盖 4（功能半，小算法）：编辑 Sheet 评估参数映射 改转换 → 发布 → 回读。"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176')
ALGO = '接线测试_走查R4_编辑映射'
ATYPE = 'wiring_r4_edit_int2176'
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
RES = {}

import importlib.util
spec = importlib.util.spec_from_file_location('sh', os.path.join(HERE, '_int2176_shell.py'))
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)
spec2 = importlib.util.spec_from_file_location('rep', os.path.join(HERE, '_int2176_report.py'))
r = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(r)


def api_get(path):
    req = urllib.request.Request('http://127.0.0.1:15000/api/v1' + path,
                                 headers={'Authorization': 'Bearer ' + TOKEN})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode('utf-8'))


def dump():
    open(os.path.join(ART, 'mapping_edit_small.json'), 'w', encoding='utf-8').write(
        json.dumps(RES, ensure_ascii=False, indent=2))


def main():
    dump()
    d = sh.driver_dg()
    d.set_page_load_timeout(60)
    try:
        r.login(d)
        d.get(r.BASE + '/AlgorithmConfig')
        r.ready(d, 4)
        d.execute_script(r.JS_VIS + """
          const tr=[...document.querySelectorAll('tr')].find(x=>(x.innerText||'').includes(arguments[0]));
          if(tr){const b=[...tr.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').includes('操作'));if(b)b.click();}
        """, ATYPE)
        time.sleep(1.0)
        RES['open_edit'] = d.execute_script(r.JS_VIS + """
          const it=[...document.querySelectorAll('[role=menuitem]')].filter(vis).find(m=>(m.innerText||'').trim()==='编辑');
          if(!it) return {ok:false}; it.click(); return {ok:true};
        """)
        dump()
        time.sleep(3.5)
        d.execute_script(r.JS_VIS + """
          const b=[...document.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').includes('高级配置'));
          if(b){b.scrollIntoView({block:'center'}); b.click();}
        """)
        time.sleep(2)
        d.execute_script(r.JS_VIS + """
          const t=[...document.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').includes('评估参数映射'));
          if(t && t.getAttribute('aria-expanded')!=='true'){t.scrollIntoView({block:'center'}); t.click();}
        """)
        time.sleep(2.5)
        RES['rows'] = d.execute_script("""
          const ts=[...document.querySelectorAll('.alg-table-contain')];
          return ts.map(t=>({rows:t.querySelectorAll('tbody tr').length, boxes:t.querySelectorAll('[role=combobox]').length}));
        """)
        dump()
        before = d.execute_script(r.JS_VIS + """
          const ts=[...document.querySelectorAll('.alg-table-contain')].filter(vis);
          const t=ts.find(x=>(x.innerText||'').includes('目标评估维度'));
          if(!t) return {ok:false, why:'no mapping table'};
          const rows=[...t.querySelectorAll('tbody tr')].filter(x=>x.querySelectorAll('[role=combobox]').length>=5);
          if(!rows.length) return {ok:false, why:'no data row'};
          const boxes=[...rows[0].querySelectorAll('[role=combobox]')].filter(vis);
          window.__bx=boxes;
          return {ok:true, n:boxes.length, transform:boxes[boxes.length-1].innerText.trim(), row:(rows[0].innerText||'').replace(/\\s+/g,' ').slice(0,120)};
        """)
        RES['row_before'] = before
        dump()
        if before and before.get('ok'):
            d.execute_script(r.JS_VIS + """
              const b=window.__bx[window.__bx.length-1];
              b.scrollIntoView({block:'center'}); b.click();
            """)
            time.sleep(1.0)
            RES['pick'] = d.execute_script(r.JS_VIS + """
              const opts=[...document.querySelectorAll('[role=option]')].filter(vis);
              const el=opts.find(o=>(o.innerText||'').trim()==='JSON解析');
              if(!el) return {ok:false, opts:opts.map(o=>(o.innerText||'').trim()).slice(0,10)};
              el.click(); return {ok:true, picked:el.innerText.trim()};
            """)
            time.sleep(1.0)
            RES['row_after'] = d.execute_script(r.JS_VIS + """
              const b=window.__bx[window.__bx.length-1];
              return {transform:b.innerText.trim()};
            """)
            dump()
        r.shot(d, '13-small-mapping-edit-light')
        # 发布
        RES['publish'] = d.execute_script(r.JS_VIS + """
          const b=[...document.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').trim()==='发布');
          if(!b) return {ok:false};
          b.scrollIntoView({block:'center'}); b.click(); return {ok:true};
        """)
        time.sleep(1.5)
        RES['toast_1s5'] = sh.toast_info(d)
        RES['all_toasts'] = d.execute_script("return [...document.querySelectorAll('[data-sonner-toast]')].map(t=>({txt:(t.innerText||'').trim().slice(0,200), type:t.getAttribute('data-type')}))")
        time.sleep(3)
        RES['toast'] = sh.toast_info(d)
        RES['sheet_errors'] = d.execute_script(r.JS_VIS + """
          const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
          if(!dl) return null;
          return [...dl.querySelectorAll('[class*=destructive], [role=alert]')].map(e=>(e.innerText||'').trim()).filter(Boolean).slice(0,5);
        """)
        RES['footer'] = d.execute_script(r.JS_VIS + """
          const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
          return dl ? (dl.innerText||'').slice(-300) : null;
        """)
        dump()
        r.shot(d, '14-small-mapping-published-light')
    finally:
        try:
            d.quit()
        except Exception:
            pass
    try:
        detail = api_get('/algorithm/definitions/' + ATYPE)['data']
        maps = (detail.get('mappings') or {}).get('evaluation') or []
        RES['readback'] = {'status': detail.get('status'), 'eval_total': len(maps),
                           'maps': maps[:3]}
    except Exception as e:
        RES['readback_err'] = str(e)[:300]
    dump()
    print('done')


if __name__ == '__main__':
    main()
