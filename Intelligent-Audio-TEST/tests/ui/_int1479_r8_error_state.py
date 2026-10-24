# -*- coding: utf-8 -*-
"""INT-1479 R8 · C：音频列表错误态（INT-1583 修复复走）。

页内 fetch 打点把 POST /api/v1/audios 打成 500（窗口内可控失败次数）：
1) 首屏失败 → 必须出现「音频列表加载失败 / 音频列表获取失败，请重试 / 重试」，
   且不得出现「暂无音频文件」空态；浅色 + 深色各一图；
2) 解除失败后点「重试」→ 列表恢复真实行（证明重试可用）；
3) 已有数据后再次失败 → 保留旧行 + 行内提示条「当前显示的是上一次加载的数据」。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402

OUT = L.OUT

PATCH = r"""
(function(){
  if (window.__int1479_patch) return;
  window.__int1479_patch = true;
  window.__failN = 5;
  window.__failCount = 0;
  var orig = window.fetch;
  window.fetch = function(input, init){
    try {
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      var method = (((init && init.method) || (input && input.method) || 'GET') + '').toUpperCase();
      var path = url.split('?')[0];
      if (method === 'POST' && /\/api\/v1\/audios$/.test(path) && window.__failN > 0) {
        window.__failN--;
        window.__failCount++;
        return Promise.resolve(new Response(
          JSON.stringify({success:false, code:203, message:'INT-1479 模拟接口失败'}),
          {status:500, headers:{'Content-Type':'application/json'}}));
      }
    } catch (e) {}
    return orig.apply(this, arguments);
  };
})();
"""


def text(c):
    return L.text(c)


def rows(c):
    return c.eval("document.querySelectorAll('tbody tr').length") or 0


def wait_for(c, cond, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def click_retry(c):
    return c.eval("""(function(){
      const b = Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='重试');
      if(!b) return 'NOT_FOUND'; b.click(); return 'CLICKED';})()""")


def snapshot(c, t):
    return {
        'rows': rows(c),
        'has_error_title': '音频列表加载失败' in t,
        'has_error_desc': '音频列表获取失败，请重试' in t,
        'has_retry_btn': '重试' in t,
        'has_empty_暂无音频文件': '暂无音频文件' in t,
        'has_stale_alert': '当前显示的是上一次加载的数据' in t,
        'hdr': c.eval("""(function(){const m=(document.body.innerText||'').match(/共[^\\n]{0,12}个/);return m?m[0]:'';})()"""),
        'text_head': t.replace('\n', ' | ')[:900],
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    c = L.connect()
    sid = c.send('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})['identifier']
    out = {}
    try:
        # ---------- 1. 浅色首屏失败 ----------
        L.nav(c, '/audio-import', 6)
        L.set_theme(c, 'light')
        L.nav(c, '/audio-import', 8)
        wait_for(c, lambda: '音频列表加载失败' in text(c), 120)
        time.sleep(4)
        t = text(c)
        out['light_error'] = snapshot(c, t)
        out['fail_count_light'] = c.eval('window.__failCount')
        out['light_error']['shot'] = L.shot(c, 'r8-c1-audio-list-error-light')
        print('LIGHT ERROR', json.dumps(out['light_error'], ensure_ascii=False), flush=True)

        # ---------- 2. 解除失败 → 重试恢复 ----------
        c.eval('window.__failN = 0')
        print('RETRY', click_retry(c), flush=True)
        ok = wait_for(c, lambda: rows(c) > 0, 180)
        time.sleep(2)
        t2 = text(c)
        out['retry_recovered'] = ok
        out['retry_rows'] = rows(c)
        out['retry_text_head'] = t2.replace('\n', ' | ')[:600]
        out['retry_shot'] = L.shot(c, 'r8-c2-audio-list-retry-recovered-light')
        print('RETRY RECOVERED', ok, 'rows', rows(c), flush=True)

        # ---------- 3. 已有数据后失败 → 保留旧行 + 行内提示条 ----------
        c.eval('window.__failN = 99')
        L.set_theme(c, 'light')
        # 触发一次重取：改搜索关键字
        c.eval("""(function(){const i=document.querySelector("input[aria-label='搜索音频']");
          const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          setter.call(i,'INT1479'); i.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        wait_for(c, lambda: '当前显示的是上一次加载的数据' in text(c), 120)
        time.sleep(3)
        t3 = text(c)
        out['stale'] = snapshot(c, t3)
        out['stale']['shot'] = L.shot(c, 'r8-c3-audio-list-stale-alert-light')
        print('STALE', json.dumps(out['stale'], ensure_ascii=False), flush=True)

        # ---------- 4. 深色首屏失败 ----------
        L.nav(c, '/audio-import', 5)
        L.set_theme(c, 'dark')
        L.nav(c, '/audio-import', 8)
        wait_for(c, lambda: '音频列表加载失败' in text(c), 120)
        time.sleep(4)
        t4 = text(c)
        out['dark_error'] = snapshot(c, t4)
        out['dark_theme_on'] = c.eval("document.documentElement.classList.contains('dark')")
        out['dark_error']['shot'] = L.shot(c, 'r8-c4-audio-list-error-dark')
        print('DARK ERROR', json.dumps(out['dark_error'], ensure_ascii=False), flush=True)
        out['dark_fail_count'] = c.eval('window.__failCount')
    finally:
        try:
            c.send('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid})
        except Exception:
            pass
    with open(os.path.join(OUT, 'r8_error_state.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
