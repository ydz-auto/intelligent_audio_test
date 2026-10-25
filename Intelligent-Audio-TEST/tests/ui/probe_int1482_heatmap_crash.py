# -*- coding: utf-8 -*-
"""INT-1482 E 轮：统计页「热力图」切换崩溃取证（console/error 捕获 + 截图）。

现象：统计结果 → 图表（散点图正常）→ 点「热力图」→ 整页 500「糟糕！出错了」。
本探针只读，抓运行时异常栈与页面文案，并在「趋势分析 → 趋势图表」复现同一组件。
"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}

ERR_HOOK = r"""
window.__errs = [];
window.__cerrs = [];
window.addEventListener('error', function(e){
  window.__errs.push(String((e.error && (e.error.stack || e.error.message)) || e.message));
});
window.addEventListener('unhandledrejection', function(e){
  window.__errs.push('unhandledrejection: ' + String((e.reason && (e.reason.stack || e.reason.message)) || e.reason));
});
(function(){
  var o = console.error;
  console.error = function(){
    try { window.__cerrs.push(Array.prototype.map.call(arguments, function(a){
      return typeof a === 'string' ? a : (a && (a.stack || a.message)) || String(a);
    }).join(' ').slice(0, 3000)); } catch(e) {}
    return o.apply(console, arguments);
  };
})();
"""


def click_text(d, label):
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == label and b.is_displayed():
            L.js_click(d, b)
            time.sleep(1.5)
            return True
    return False


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-statistics')
        WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
        time.sleep(8)
        # 评估维度
        combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
        if combos:
            L.js_click(d, combos[0])
            time.sleep(1.5)
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (o.text or '').strip() == '评估维度' and o.is_displayed():
                    L.js_click(d, o)
                    break
            time.sleep(3)
        OUT['before'] = L.body(d)[-260:]
        d.execute_script(ERR_HOOK)
        OUT['click_result_tab'] = click_text(d, '统计结果')
        OUT['click_chart_tab'] = click_text(d, '图表')
        time.sleep(3)
        OUT['scatter_canvas'] = len([c for c in d.find_elements(By.CSS_SELECTOR, 'canvas') if c.is_displayed()])
        OUT['before_heatmap_text'] = L.body(d)[-200:]
        t0 = L.now_ms()
        OUT['click_heatmap'] = click_text(d, '热力图')
        time.sleep(5)
        OUT['after_heatmap_text'] = L.body(d)[-400:]
        OUT['crashed'] = '糟糕！出错了' in L.body(d)
        OUT['errs'] = d.execute_script('return window.__errs || []')[:6]
        OUT['console_errs'] = d.execute_script('return window.__cerrs || []')[:8]
        OUT['url_after'] = d.current_url
        L.shot(d, 'e30_heatmap_crash')
        OUT['shot'] = os.path.join(L.ART, 'e30_heatmap_crash.png')
        # 复现：趋势分析 → 趋势图表（同一 StatisticsCharts 组件）
        d.get(L.BASE + '/report-statistics')
        time.sleep(8)
        d.execute_script(ERR_HOOK)
        OUT['trend_tab'] = click_text(d, '趋势分析')
        OUT['trend_chart_sub'] = click_text(d, '趋势图表')
        time.sleep(3)
        OUT['trend_scatter_canvas'] = len([c for c in d.find_elements(By.CSS_SELECTOR, 'canvas')
                                          if c.is_displayed()])
        OUT['trend_click_heatmap'] = click_text(d, '热力图')
        time.sleep(5)
        OUT['trend_crashed'] = '糟糕！出错了' in L.body(d)
        OUT['trend_errs'] = d.execute_script('return window.__errs || []')[:6]
        L.shot(d, 'e31_heatmap_crash_trend')
        print(json.dumps({'crashed': OUT['crashed'], 'trend_crashed': OUT['trend_crashed'],
                          'errs': OUT['errs'][:2], 'console_errs': OUT['console_errs'][:3]},
                         ensure_ascii=False, indent=1)[:3000])
    finally:
        os.makedirs(L.ART, exist_ok=True)
        with open(os.path.join(L.ART, 'heatmap_crash.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()
