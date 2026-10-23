# -*- coding: utf-8 -*-
"""INT-1479 R5 · B2：音频列表接口失败时的错误态取证。

在页面加载前注入 fetch 钩子，把列表请求 POST /api/v1/audios 打成 500，
观察首屏失败时页面呈现（是否与「暂无音频文件」空态混淆、是否有错误提示 / 重试）。
取证后移除钩子并重载恢复。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402

PATCH = r"""
(function(){
  if (window.__int1479_patch) return;
  window.__int1479_patch = true;
  var orig = window.fetch;
  window.fetch = function(input, init){
    try {
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      var method = (((init && init.method) || (input && input.method) || 'GET') + '').toUpperCase();
      var path = url.split('?')[0];
      if (method === 'POST' && /\/api\/v1\/audios$/.test(path)) {
        window.__int1479_failed = (window.__int1479_failed || 0) + 1;
        return Promise.resolve(new Response(
          JSON.stringify({success:false, code:203, message:'INT-1479 模拟接口失败'}),
          {status:500, headers:{'Content-Type':'application/json'}}));
      }
    } catch (e) {}
    return orig.apply(this, arguments);
  };
})();
"""


def main():
    os.makedirs(L.OUT, exist_ok=True)
    c = L.connect()
    L.set_theme(c, 'light')
    sid = c.send('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})['identifier']
    try:
        L.nav(c, '/audio-import', 10)
        time.sleep(20)
        c.pump()
        t = c.eval("(document.body && document.body.innerText) || ''") or ''
        failed = c.eval('window.__int1479_failed || 0')
        has_empty = '暂无音频文件' in t
        has_match_empty = '未找到匹配的音频' in t
        has_retry = any(k in t for k in ('重试', '加载失败', '请求失败', '出错了'))
        toasts = c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(n=>n.innerText)") or []
        resps = [e['params']['response']['status'] for e in c.events
                 if e.get('method') == 'Network.responseReceived'
                 and '/api/v1/audios' in e['params']['response'].get('url', '')
                 and e['params']['response']['url'].split('?')[0].endswith('/audios')]
        shot = L.shot(c, 'r5_b2-audio-list-500')
        out = {
            'failed_interceptions': failed,
            'list_response_statuses': resps[:10],
            'has_empty_state_暂无音频文件': has_empty,
            'has_empty_state_未找到匹配': has_match_empty,
            'has_retry_or_error_hint': has_retry,
            'toasts': toasts,
            'screenshot': shot,
            'page_text_head': t.replace('\n', ' | ')[:900],
        }
        print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
        with open(os.path.join(L.OUT, 'r5_b2_report.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    finally:
        try:
            c.send('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid})
        except Exception:
            pass


if __name__ == '__main__':
    main()
