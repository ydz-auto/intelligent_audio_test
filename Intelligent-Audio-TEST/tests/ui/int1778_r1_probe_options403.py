# -*- coding: utf-8 -*-
"""P2-1 边界探针：/algorithm/options 不可用（403 降级 / 无 algorithm:read）时，
编辑弹窗「关联算法」收起态显示什么。只读，不写任何数据。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import int1777_accept as A  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15267')

INJECT = r"""
if (!window.__origFetchOpt) { window.__origFetchOpt = window.fetch; }
window.fetch = function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  if (url.indexOf('/algorithm/options') !== -1) {
    (window.__fetchLog = window.__fetchLog || []).push(
      {url: url, method: 'GET', status: 403, injected: true, t: Date.now()});
    return Promise.resolve(new Response(JSON.stringify({detail: 'forbidden'}), {
      status: 403, headers: {'Content-Type': 'application/json'}
    }));
  }
  return window.__origFetchOpt.apply(this, arguments);
};
"""


def main():
    d = L.driver()
    try:
        # 应用挂载前就拦截（L.driver 已用 addScriptToEvaluateOnNewDocument 装了日志补丁）
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': INJECT})
        L.login(d)
        d.get(L.BASE + '/start-test')
        time.sleep(6)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        if steps:
            L.js_click(d, steps[0])
            time.sleep(4)
        # 取一个真实 API 名字
        st, payload, _ = L.api_json(d, '/apis?page=1&page_size=50')
        items = ((payload or {}).get('data') or {}).get('items') or []
        print('APIS', [(it.get('id'), it.get('name'), it.get('algorithm_type')) for it in items][:5])
        target = None
        for it in items:
            if it.get('algorithm_type') == 'voice_llm':
                target = it.get('name')
                break
        if not target:
            print('no voice_llm api, skip')
            return 2
        # 降级态下卡片徽章（useAlgorithmLabels 受 algorithm:read 门控 → 预期「—」）
        badges = []
        for dt in d.find_elements(By.XPATH, "//dt[normalize-space(.)='算法']"):
            try:
                badges.append((dt.find_element(By.XPATH, 'following-sibling::dd[1]').text or '').strip())
            except Exception:
                pass
        print('BADGES_UNDER_403', badges)
        L.shot(d, 'probe_options_403_cards')
        A.open_edit(d, target)
        txt = A.combo_text(d, 0)
        reqs = [e for e in L.fetch_log(d, '/algorithm/options') if e.get('status') == 403]
        print('OPTIONS_403_HIT', bool(reqs))
        print('COMBO_TEXT', repr(txt))
        L.shot(d, 'probe_options_403_select')
        return 0
    finally:
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
