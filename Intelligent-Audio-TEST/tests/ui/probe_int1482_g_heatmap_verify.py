# -*- coding: utf-8 -*-
"""INT-1482 G 轮：热力图 500 修复后补充取证——整卡可见（含坐标轴标签）的浅/深截图。

E 轮起热力图整页 500，F 轮确认修复未合入；本轮 INT-1890 集成后复走。
本脚本只补「热力图卡片完整可见」的取证：
  1) 打开 /report-statistics，选「评估维度」，统计结果 → 图表 → 热力图；
  2) 把画布滚入视口、加高窗口，截卡片整卡 + 读 canvas 几何；
  3) 顺带记录 case-averages 返回与图表是否报错。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
ERR_HOOK = r"""
window.__errs = [];
(function(){
  var o = console.error;
  console.error = function(){
    try { window.__errs.push(Array.prototype.map.call(arguments, function(a){
      return typeof a === 'string' ? a : (a && (a.stack || a.message)) || String(a);
    }).join(' ').slice(0, 2000)); } catch(e) {}
    return o.apply(console, arguments);
  };
})();
window.addEventListener('error', function(e){
  window.__errs.push(String((e.error && (e.error.stack || e.error.message)) || e.message));
});
"""


def js_click_text(d, texts):
    ok = d.execute_script("""
      var want = arguments[0];
      var els = document.querySelectorAll('button,[role="tab"],[role="option"],[role="combobox"]');
      for (var i = 0; i < els.length; i++) {
        var t = (els[i].textContent || '').trim();
        if (want.indexOf(t) !== -1 && els[i].offsetParent !== null) { els[i].click(); return t; }
      }
      return null;
    """, texts)
    time.sleep(2)
    return ok


def card_shot(d, name):
    """滚动到热力图卡片并截整卡。"""
    box = d.execute_script("""
      var t = null;
      var all = document.querySelectorAll('div');
      for (var i = 0; i < all.length; i++) {
        var h = all[i].querySelector('canvas');
        if (h && (all[i].textContent || '').indexOf('设备 × 评估维度 值矩阵') !== -1
            && all[i].getBoundingClientRect().height > 200
            && all[i].getBoundingClientRect().height < 900) { t = all[i]; }
      }
      if (!t) return null;
      t.scrollIntoView({block: 'center'});
      var r = t.getBoundingClientRect();
      return {x: r.x, y: r.y, w: r.width, h: r.height, text: (t.textContent || '').slice(0, 400)};
    """)
    time.sleep(1.2)
    path = os.path.join(L.ART, name + '.png')
    d.save_screenshot(path)
    return {'path': path, 'box': box}


def canvas_info(d):
    return d.execute_script("""
      var out = [];
      var cs = document.querySelectorAll('canvas');
      for (var i = 0; i < cs.length; i++) {
        var c = cs[i];
        var r = c.getBoundingClientRect();
        if (r.width === 0) continue;
        var ctx = c.getContext('2d');
        var img = ctx.getImageData(0, 0, c.width, c.height).data;
        var colored = 0;
        for (var p = 0; p < img.length; p += 4) {
          if (img[p + 3] > 0 && !(img[p] > 240 && img[p + 1] > 240 && img[p + 2] > 240)) colored++;
        }
        out.push({w: Math.round(r.width), h: Math.round(r.height),
                  nonWhitePixels: colored});
      }
      return out;
    """)


def run(d, tag):
    L.reset_fetch_log(d)
    t0 = L.now_ms()
    d.get(L.BASE + '/report-statistics')
    WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
    d.execute_script(ERR_HOOK)
    time.sleep(8)
    res = {'theme': d.execute_script(
        "return {dark: document.documentElement.classList.contains('dark'),"
        "bg: getComputedStyle(document.body).backgroundColor};")}
    # 选评估维度（第一个 combobox）
    combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
    L.js_click(d, combos[0])
    time.sleep(1.5)
    for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if (o.text or '').strip() == '评估维度' and o.is_displayed():
            L.js_click(d, o)
            time.sleep(2)
            break
    js_click_text(d, ['统计结果'])
    js_click_text(d, ['图表'])
    time.sleep(2)
    before = canvas_info(d)
    js_click_text(d, ['热力图'])
    time.sleep(5)
    txt = L.body(d)
    res['crashed'] = '糟糕！出错了' in txt
    res['has_title'] = '设备 × 评估维度 值矩阵' in txt
    res['has_subtitle'] = '密度分布：颜色越深值越高' in txt
    res['has_empty'] = '暂无数据' in txt
    res['canvas_before_heatmap'] = before
    res['canvas_after_heatmap'] = canvas_info(d)
    res['errors'] = [e[:400] for e in (d.execute_script('return window.__errs || []') or [])][:5]
    res['case_avg'] = [
        {k: e.get(k) for k in ('method', 'url', 'status')}
        for e in L.fetch_log(d) if '/reports/case-averages' in (e.get('url') or '')
    ][-2:]
    res['shot'] = card_shot(d, 'g_%s_heatmap_card' % tag)
    res['text_tail'] = txt[-350:]
    return res


def main():
    d = L.driver()
    try:
        d.set_window_size(1600, 1400)
        L.login(d)
        OUT['light'] = run(d, 'light')
        L.apply_theme(d, 'dark')
        OUT['dark'] = run(d, 'dark')
        L.apply_theme(d, 'light')
    except Exception:
        OUT['error'] = traceback.format_exc()[-2000:]
    finally:
        with open(os.path.join(L.ART, 'resumeG_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()
    print(json.dumps({k: (v if k != 'error' else v[:300]) for k, v in OUT.items()},
                     ensure_ascii=False)[:2500])


if __name__ == '__main__':
    main()
