# -*- coding: utf-8 -*-
"""INT-1482 F 轮取证：热力图点击后的真实异常文本（console.error + window error + 页面文案）。

前置：统计页上下文已是本轮夹具日报（任务 411）。只读，不改数据。
"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HOOK = r"""
window.__cerrs = [];
window.__errs = [];
(function(){
  var o = console.error;
  console.error = function(){
    try { window.__cerrs.push(Array.prototype.map.call(arguments, function(a){
      return typeof a === 'string' ? a : (a && (a.stack || a.message)) || String(a);
    }).join(' ').slice(0, 3000)); } catch(e) {}
    return o.apply(console, arguments);
  };
})();
window.addEventListener('error', function(e){
  window.__errs.push(String((e.error && (e.error.stack || e.error.message)) || e.message));
});
window.addEventListener('unhandledrejection', function(e){
  window.__errs.push('unhandledrejection: ' + String((e.reason && (e.reason.stack || e.reason.message)) || e.reason));
});
"""


def click_text(d, label):
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == label and b.is_displayed():
            L.js_click(d, b)
            time.sleep(1.5)
            return True
    return False


def main():
    out = {}
    d = L.driver()
    try:
        L.login(d)
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK})
        d.get(L.BASE + '/report-statistics')
        WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
        time.sleep(8)
        out['lib_react'] = d.execute_script(
            "return Array.from(document.scripts).map(s=>s.src).filter(s=>s.indexOf('lib-react')!==-1)")
        out['title_before'] = L.body(d)[-300:]
        out['click_result'] = click_text(d, '统计结果')
        out['click_chart'] = click_text(d, '图表')
        time.sleep(3)
        out['scatter_canvas'] = len([c for c in d.find_elements(By.CSS_SELECTOR, 'canvas')
                                     if c.is_displayed()])
        out['click_heatmap'] = click_text(d, '热力图')
        time.sleep(5)
        out['crashed'] = '糟糕！出错了' in L.body(d)
        out['canvas_after'] = len([c for c in d.find_elements(By.CSS_SELECTOR, 'canvas')
                                   if c.is_displayed()])
        out['cerrs'] = d.execute_script('return (window.__cerrs||[]).slice(-6)')
        out['errs'] = d.execute_script('return (window.__errs||[]).slice(-6)')
        try:
            out['browser_logs'] = [x for x in d.get_log('browser')
                                   if x.get('level') == 'SEVERE'][-5:]
        except Exception as e:
            out['browser_logs'] = 'ERR ' + str(e)
        out['text_tail'] = L.body(d)[-400:]
        # 趋势分析入口
        d.get(L.BASE + '/report-statistics')
        time.sleep(8)
        out['trend_tab'] = click_text(d, '趋势分析')
        out['trend_chart'] = click_text(d, '趋势图表')
        time.sleep(3)
        out['trend_heatmap'] = click_text(d, '热力图')
        time.sleep(5)
        out['trend_crashed'] = '糟糕！出错了' in L.body(d)
        out['trend_cerrs'] = d.execute_script('return (window.__cerrs||[]).slice(-6)')
        # 保存截图
        L.shot(d, 'f30_heatmap_still_crash')
    finally:
        path = os.path.join(L.ART, 'f_heatmap_error.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1, default=str)
        print(json.dumps({'crashed': out.get('crashed'),
                          'trend_crashed': out.get('trend_crashed'),
                          'cerrs': [str(x)[:200] for x in (out.get('cerrs') or [])][-2:],
                          'lib_react': out.get('lib_react')},
                         ensure_ascii=False)[:1500])
        d.quit()


if __name__ == '__main__':
    main()
