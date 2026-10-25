# -*- coding: utf-8 -*-
"""INT-1477 / INT-1731 (b) 定点复测：声压窗「指定轮次」清空唯一勾选后点确定。

_process 的差异点：_c 脚本在等待弹窗关闭上耗了 150s，toast 早已自动消失，
读不到提示文案。本脚本点确定后 0.2s 起连续 6s 采样 toast 文案与网络请求，
截图保留提示出现的那一帧。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_int1477_int1731 as base  # noqa: E402
import verify_int1477_int1731_b as b  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402

TAG = os.environ.get('FIXTAG', '10241546')
base.GROUP = '接线测试_INT1477R组' + TAG
base.NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']
NAMES = base.NAMES


OBSERVER_JS = """
window.__toastLog = [];
var grab = function () {
  document.querySelectorAll('[data-sonner-toast]').forEach(function (n) {
    var t = (n.textContent || '').trim();
    if (t && window.__toastLog.indexOf(t) < 0) {
      window.__toastLog.push(t);
    }
  });
};
new MutationObserver(grab).observe(document.body, {childList: true, subtree: true, characterData: true});
grab();
"""

READ_JS = "return window.__toastLog || [];"


def install_toast_observer(d):
    d.execute_script(OBSERVER_JS)


def main():
    d = base.driver()
    out = {}
    try:
        d.get(base.BASE + '/testcases/by-group')
        base.wait_page(d)
        ids = b.find_ids(d)
        out['fixtures'] = ids
        if any(v is None for v in ids.values()):
            raise AssertionError('夹具用例缺失')
        base.open_page(d)
        out['before'] = b.all_states(d, ids)
        base.clear_log(d)
        dlg = base.open_window(d, '批量设置声压', '批量设置声压级')
        base.click_label(d, dlg, '指定轮次（统一设置）')
        # 默认已勾第1轮 → 取消它，成为「一个轮次都没选」
        for e in dlg.find_elements(By.XPATH, ".//label[normalize-space(.)='第1轮']"):
            if e.is_displayed():
                base.jsclick(d, e)
                time.sleep(0.6)
                break
        inp = [x for x in dlg.find_elements(By.XPATH, ".//input[@aria-label='声压级 dB']")
               if x.is_displayed()][0]
        inp.send_keys('66')
        time.sleep(0.5)
        btn = [x for x in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']")
               if x.is_displayed()][0]
        out['confirm_disabled'] = not btn.is_enabled()
        install_toast_observer(d)
        base.jsclick(d, btn)
        # 0.2s 起连续采样（toast 文案由 MutationObserver 落日志，避开 sonner 摘除 DOM 的 stale）
        shots = 0
        t0 = time.time()
        while time.time() - t0 < 6.0:
            time.sleep(0.2)
            cur = d.execute_script(READ_JS)
            if cur and shots == 0:
                base.shot(d, 'r_spl_submit_none_toast')
                shots += 1
        out['toast_log'] = d.execute_script(READ_JS)
        out['dialog_still_open'] = bool([
            e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
            if e.is_displayed() and '批量设置声压级' in (e.text or '')])
        base.shot(d, 'r_spl_submit_none_after')
        cs = base.calls(d)
        out['batch'] = [c for c in cs if '/testcases/batch' in c['url']]
        out['api_calls_after_click'] = [{'method': c['method'], 'url': c['url'], 'status': c['status']}
                                        for c in cs]
        out['after'] = b.all_states(d, ids)
    finally:
        json.dump(out, open(os.path.join(base.ART, 'rounds_evidence_c2.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
