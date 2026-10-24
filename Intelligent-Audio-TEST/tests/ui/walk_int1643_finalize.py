# -*- coding: utf-8 -*-
"""INT-1643 续测：彻底删除 UI + 抽屉五步 + INT-1642 五项复测 + 加载/错误态。

基线：INT-1642 交付（492fe09b4）打在 frontend-react 上的临时副本 dev 5333 → 网关 15000（docker 真实库栈）。
不修改业务代码、不保存真实用例（真实用例只读）。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

os.environ.setdefault('REACT_BASE', 'http://127.0.0.1:5333')
L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5333')
L.API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')

GROUP = '接线测试_INT1643_目标组'
B_ID = '38a3fa72-1561-425d-b467-9b46ca209e23'
B_NAME = '接线测试_INT1643_批量_B'
A_NAME = '接线测试_INT1643_批量_A'
C_NAME = '接线测试_INT1643_批量_C'
REAL_ID = '016dd854-a6a0-4a57-b88f-ce986b1d9bcd'
REAL_KW = '测试用例_DD100'

OUT = {}
D = None


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


def toasts(d, timeout=25):
    try:
        end = time.time() + timeout
        while time.time() < end:
            els = [e for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]') if vis(e)]
            if els:
                time.sleep(0.4)
                return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            time.sleep(0.4)
    except Exception:
        pass
    return []


def closedialogs(d):
    for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
        if not vis(x):
            continue
        for c in x.find_elements(By.TAG_NAME, 'button'):
            t = (c.text or '').strip()
            if vis(c) and t in ('取消', '关闭', '返回'):
                L.js_click(d, c)
                time.sleep(0.8)
                return t
    return None


def click_text(text, tag='button', exact=True, timeout=25):
    def f():
        for b in d.find_elements(By.TAG_NAME, tag):
            if not vis(b):
                continue
            t = (b.text or '').strip()
            if (t == text) if exact else (text in t):
                return b
        return None
    return retry(f, timeout)


def api_get(path):
    st, p, body = L.api_json(d, path)
    return st, p


def open_group():
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 40)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(6)


def search(kw):
    inp = retry(lambda: next((i for i in d.find_elements(By.TAG_NAME, 'input')
                              if vis(i) and '搜索' in (i.get_attribute('placeholder') or '')), None), 30)
    L.js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(kw)
    time.sleep(6)


def reset_filters():
    r = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '重置'), None)
    if r is not None:
        L.js_click(d, r)
        time.sleep(4)


def edit_case(name, timeout=40):
    btn = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
                              if vis(x) and name in (x.get_attribute('aria-label') or '')), None), timeout)
    L.js_click(d, btn)
    drawer = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                 if vis(x) and any((t.text or '').strip() == '参考参数'
                                                   for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 40)
    time.sleep(1.5)
    return drawer


def tab(drawer, label):
    t = next((x for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.text or '').strip() == label), None)
    if t is None:
        return False
    L.js_click(d, t)
    time.sleep(1.2)
    return True


def step_text(drawer, label):
    # 步骤体不在 role=tabpanel 里（StepBody 直接渲染），取抽屉尾部文本
    return (drawer.text or '')[-900:]


# ---------------------------------------------------------------- main
d = L.driver()
D = d
DL = os.path.join(L.ART, 'downloads')
os.makedirs(DL, exist_ok=True)
try:
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DL})
except Exception:
    pass
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(8)
    OUT['url_after_login'] = d.current_url

    # ============ 1) 彻底删除 UI（B 已软删） ============
    phase = {}
    try:
        open_group()
        assert not retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                       if vis(b) and (b.text or '').strip() == '回收站'), None), 20) is None
        L.js_click(d, click_text('回收站'))
        time.sleep(6)
        if not any(vis(x) for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='彻底删除']")):
            hdr = next((e for e in d.find_elements(
                By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
                if vis(e)), None)
            if hdr is not None:
                L.js_click(d, hdr)
                time.sleep(6)
        btns = [x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label]") if vis(x)]
        phase['trash_buttons'] = [(x.get_attribute('aria-label'), (x.text or '')[:12]) for x in btns][:12]
        L.shot(d, 'p1_trash_B')
        pb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='彻底删除']") if vis(x)), None), 25)
        phase['purge_button_aria'] = pb.get_attribute('aria-label')
        L.js_click(d, pb)
        time.sleep(1.5)
        L.shot(d, 'p2_purge_confirm')
        ad = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if vis(x)), None), 20)
        phase['confirm_text'] = (ad.text or '')[:300] if ad is not None else None
        done = None
        if ad is not None:
            for c in ad.find_elements(By.TAG_NAME, 'button'):
                if vis(c) and (c.text or '').strip() in ('彻底删除', '删除', '确定', '确认'):
                    done = (c.text or '').strip()
                    L.js_click(d, c)
                    break
        phase['confirm_clicked'] = done
        time.sleep(3)
        phase['toasts'] = toasts(d, 25)
        L.shot(d, 'p3_after_purge')
        phase['api_trash_list'] = api_get('/testcases?page=1&per_page=50&keyword=' + B_NAME + '&only_deleted=1')[0]
        st, p = api_get('/testcases?page=1&per_page=50&keyword=' + B_NAME + '&only_deleted=1')
        phase['api_trash_total'] = ((p or {}).get('data') or {}).get('total')
        phase['api_detail_status'] = api_get('/testcases/' + B_ID)[0]
        L.shot(d, 'p4_after_purge_list')
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['purge'] = phase

    # ============ 2) 抽屉五步（C，2 轮，有音频） ============
    phase = {}
    try:
        # 退出回收站
        t = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                  if vis(b) and (b.text or '').strip() == '回收站'), None)
        if t is not None:
            L.js_click(d, t)
            time.sleep(5)
        reset_filters()
        open_group()
        drawer = edit_case(C_NAME)
        phase['tabs'] = [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
        shots = {}
        for label, key in [('算法参数', 'step1'), ('音频列表', 'step2'), ('噪声与干扰', 'step3'),
                           ('评估维度', 'step4'), ('参考参数', 'step5')]:
            if not tab(drawer, label):
                shots[key] = 'tab missing'
                continue
            time.sleep(1.2)
            L.shot(d, 'f_%s_%s' % (key, label))
            shots[key] = step_text(drawer, label)
            if label == '音频列表':
                combos = [e for e in drawer.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)]
                phase['device_select_closed'] = [(e.text or '').strip()[:80] for e in combos][:8]
                # 每个音频卡的播放设备 Select 文案
                phase['audio_step_has_device_name'] = any('通道' in (e.text or '') for e in combos)
            if label == '噪声与干扰':
                phase['noise_demo_hint_present'] = '演示提示条' in (drawer.text or '')
                phase['noise_step_tail'] = step_text(drawer, label)
            if label == '参考参数':
                phase['ref_step_tail'] = step_text(drawer, label)
                phase['ref_has_fake_path'] = '/data/ref_params/' in (drawer.text or '')
        phase['steps'] = shots
        L.apply_theme(d, 'dark')
        L.shot(d, 'f_drawer_dark')
        L.apply_theme(d, 'light')
        closedialogs(d)
        time.sleep(1)
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['drawer_C'] = phase

    # ============ 3) 参考参数真实错误态（真实 2 轮用例，只读） ============
    phase = {}
    try:
        d.get(L.BASE + '/testcases')
        time.sleep(7)
        search(REAL_KW)
        L.clear_fetch_log(d)
        drawer = edit_case(REAL_KW.split('_')[-1][:0] or 'DD100')
        phase['tabs'] = [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
        tab(drawer, '参考参数')
        L.shot(d, 'g1_ref_loading_or_error')
        time.sleep(4)
        phase['ref_step_tail'] = step_text(drawer, '参考参数')
        phase['ref_fetch'] = [(e.get('method'), (e.get('url') or '')[:100], e.get('status'))
                              for e in L.fetch_log(d, 'ref-params')]
        L.shot(d, 'g2_ref_error_state')
        phase['has_error_text'] = '参考参数内容读取失败' in (drawer.text or '')
        phase['has_retry'] = any((b.text or '').strip() == '重试' for b in drawer.find_elements(By.TAG_NAME, 'button'))
        closedialogs(d)
        reset_filters()
        time.sleep(3)
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['ref_error_state'] = phase

    # ============ 4) 批量评估维度指定轮次（选 A+C，均 2 轮） ============
    phase = {}
    try:
        d.get(L.BASE + '/testcases')
        time.sleep(7)
        open_group()
        for nm in (A_NAME, C_NAME):
            cb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                                     if vis(x) and nm in (x.get_attribute('aria-label') or '')), None), 30)
            L.js_click(d, cb)
            time.sleep(1.5)
        phase['selected'] = [nm for nm in (A_NAME, C_NAME)
                             if any(nm in (x.get_attribute('aria-label') or '')
                                    for x in d.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"))]
        L.clear_fetch_log(d)
        L.js_click(d, click_text('批量设置评估维度'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '批量设置评估维度' in (x.text or '')), None), 30)
        time.sleep(2)
        phase['dialog_text'] = (dlg.text or '')[:1200]
        phase['round_labels'] = [t for t in ['第1轮', '第2轮', '第3轮', '第4轮'] if t in (dlg.text or '')]
        # 切「指定轮次」
        rb = next((x for x in dlg.find_elements(By.TAG_NAME, 'button')
                   if '指定轮次' in (x.text or '')), None)
        if rb is not None:
            L.js_click(d, rb)
            time.sleep(1.5)
            phase['after_specific_text'] = (dlg.text or '')[:800]
            phase['after_specific_rounds'] = [t for t in ['第1轮', '第2轮', '第3轮', '第4轮'] if t in (dlg.text or '')]
        L.shot(d, 'h1_batch_dims_rounds')
        L.apply_theme(d, 'dark')
        L.shot(d, 'h2_batch_dims_dark')
        L.apply_theme(d, 'light')
        closedialogs(d)
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['batch_dims'] = phase

    # ============ 5) 导出弹窗真实下载（P2-2）+ 加载态 ============
    phase = {}
    try:
        d.get(L.BASE + '/testcases')
        time.sleep(7)
        open_group()
        L.clear_fetch_log(d)
        L.js_click(d, click_text('导出'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '导出' in (x.text or '')), None), 30)
        time.sleep(1)
        phase['dialog_text'] = (dlg.text or '')[:600]
        L.shot(d, 'i1_export_dialog')
        L.js_click(d, click_text('开始导出'))
        time.sleep(0.25)
        phase['loading_text_seen'] = '导出中' in (L.body_text(d) or '')
        L.shot(d, 'i2_export_loading')
        phase['toasts'] = toasts(d, 60)
        phase['fetch'] = [(e.get('method'), (e.get('url') or '')[:100], e.get('status'), len(e.get('resBody') or ''))
                          for e in L.fetch_log(d, 'export')]
        time.sleep(3)
        files = []
        for fn in os.listdir(DL):
            p = os.path.join(DL, fn)
            files.append((fn, os.path.getsize(p)))
        phase['downloads'] = files
        L.apply_theme(d, 'dark')
        L.shot(d, 'i3_export_dark')
        L.apply_theme(d, 'light')
        closedialogs(d)
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['export'] = phase

    # ============ 6) 注入式错误态（网关层 502，502 由页内 fetch 打点合成） ============
    phase = {}
    try:
        d.get(L.BASE + '/testcases')
        time.sleep(7)
        # 注入：/testcases/export 返回 502（真实请求不发出）
        d.execute_script("""
        window.__failExport = true;
        if (!window.__origFetchFail) { window.__origFetchFail = window.fetch; }
        window.fetch = function(input, init) {
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          if (window.__failExport && url.indexOf('/testcases/export') !== -1) {
            return Promise.resolve(new Response(JSON.stringify({success:false,code:502,message:'audit injected failure'}), {status:502, headers:{'content-type':'application/json'}}));
          }
          return window.__origFetchFail.apply(this, arguments);
        };
        """)
        open_group()
        L.js_click(d, click_text('导出'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '导出' in (x.text or '')), None), 30)
        time.sleep(1)
        L.js_click(d, click_text('开始导出'))
        time.sleep(1)
        phase['toasts'] = toasts(d, 30)
        L.shot(d, 'j1_export_error_state')
        closedialogs(d)
    except Exception:
        phase['error'] = traceback.format_exc()
    OUT['error_injection'] = phase

finally:
    L.save_evidence('finalize_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: (str(vv)[:180]) for kk, vv in v.items()})
                      for k, v in OUT.items()}, ensure_ascii=False, indent=1)[:6000])
