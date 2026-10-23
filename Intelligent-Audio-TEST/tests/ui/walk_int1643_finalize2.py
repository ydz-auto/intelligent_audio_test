# -*- coding: utf-8 -*-
"""INT-1643 续测第二批（每阶段独立 driver，避免单点崩溃拖垮全部）。

阶段 A：抽屉五步（自建 C，2 轮，有音频）
阶段 B：参考参数真实错误态（真实 2 轮用例 DD100，只读）
阶段 C：批量评估维度「指定轮次」真实轮次（选 A+C）
阶段 D：导出弹窗真实下载（P2-2）
阶段 E：导出失败态（网关层等价 502 注入）
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

L.BASE = 'http://127.0.0.1:5333'
GROUP = '接线测试_INT1643_目标组'
A_NAME = '接线测试_INT1643_批量_A'
C_NAME = '接线测试_INT1643_批量_C'
REAL_KW = 'DD100'
OUT = {}


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


def toasts(d, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]') if vis(e)]
        if els:
            time.sleep(0.3)
            return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        time.sleep(0.3)
    return []


def btn(d, text, exact=True, timeout=25):
    def f():
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if not vis(b):
                continue
            t = (b.text or '').strip()
            if (t == text) if exact else (text in t):
                return b
        return None
    return retry(f, timeout)


def open_group(d):
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 40)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(6)
    hdr = next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None)
    if hdr is not None:
        L.js_click(d, hdr)
        time.sleep(5)


def drawer_tabs(drawer):
    return [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]


def tab_click(drawer, label):
    t = next((x for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.text or '').strip() == label), None)
    if t is None:
        return False
    L.js_click(d, t)
    time.sleep(1.2)
    return True


def open_edit(d, name_kw, timeout=45):
    b = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='编辑用例']")
                            if vis(x) and name_kw in (x.get_attribute('aria-label') or '')), None), timeout)
    L.js_click(d, b)
    return retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                               if vis(x) and '参考参数' in (x.text or '')
                               and any((t.text or '').strip() == '参考参数'
                                       for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 45)


def close_dialogs(d):
    for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
        if not vis(x):
            continue
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if vis(c) and (c.text or '').strip() in ('取消', '关闭', '返回'):
                L.js_click(d, c)
                time.sleep(0.8)
                return


def fresh(url='/testcases'):
    d = L.driver()
    L.login(d)
    d.get(L.BASE + url)
    time.sleep(7)
    return d


# ============================== 阶段 A：抽屉五步
def phase_a():
    ph = {}
    d = fresh()
    try:
        open_group(d)
        drawer = open_edit(d, C_NAME)
        ph['tabs'] = drawer_tabs(drawer)
        step_keys = ['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数']
        texts = {}
        for i, label in enumerate(step_keys, 1):
            if not tab_click(drawer, label):
                texts[label] = 'TAB_MISSING'
                continue
            L.shot(d, 'A%d_%s' % (i, label))
            texts[label] = (drawer.text or '')[-900:]
            if label == '音频列表':
                combos = [e for e in drawer.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)]
                ph['combobox_texts'] = [(e.text or '').strip()[:90] for e in combos][:10]
                ph['device_name_in_closed'] = any('通道' in (e.text or '') for e in combos)
            if label == '噪声与干扰':
                ph['noise_demo_hint'] = '演示提示条' in (drawer.text or '')
            if label == '参考参数':
                L.clear_fetch_log(d)
                tab_click(drawer, '评估维度')
                time.sleep(0.5)
                tab_click(drawer, '参考参数')
                ph['ref_loading_seen'] = '加载参考参数' in (drawer.text or '')
                L.shot(d, 'A5b_ref_loading')
                time.sleep(3)
                ph['ref_step_text'] = (drawer.text or '')[-700:]
                ph['ref_fake_path'] = '/data/ref_params/' in (drawer.text or '')
                ph['ref_fetch'] = [(e.get('method'), (e.get('url') or '')[:90], e.get('status'))
                                   for e in L.fetch_log(d, 'ref-params')]
                L.shot(d, 'A6_ref_after')
        ph['step_texts'] = texts
        L.apply_theme(d, 'dark')
        L.shot(d, 'A7_drawer_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


# ============================== 阶段 B：参考参数真实错误态（真实用例）
def phase_b():
    ph = {}
    d = fresh()
    try:
        inp = retry(lambda: next((i for i in d.find_elements(By.TAG_NAME, 'input')
                                  if vis(i) and '搜索' in (i.get_attribute('placeholder') or '')), None), 30)
        L.js_click(d, inp)
        inp.send_keys(Keys.CONTROL, 'a')
        inp.send_keys(Keys.DELETE)
        inp.send_keys(REAL_KW)
        time.sleep(8)
        L.clear_fetch_log(d)
        drawer = open_edit(d, REAL_KW)
        ph['tabs'] = drawer_tabs(drawer)
        tab_click(drawer, '参考参数')
        L.shot(d, 'B1_ref_initial')
        time.sleep(5)
        ph['ref_text'] = (drawer.text or '')[-800:]
        ph['has_error_text'] = '参考参数内容读取失败' in (drawer.text or '')
        ph['has_retry'] = any((b.text or '').strip() == '重试' for b in drawer.find_elements(By.TAG_NAME, 'button'))
        ph['fetch'] = [(e.get('method'), (e.get('url') or '')[:110], e.get('status'))
                       for e in L.fetch_log(d, 'ref-params')]
        L.shot(d, 'B2_ref_error')
        L.apply_theme(d, 'dark')
        L.shot(d, 'B3_ref_error_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


# ============================== 阶段 C：批量评估维度轮次
def phase_c():
    ph = {}
    d = fresh()
    try:
        open_group(d)
        for nm in (A_NAME, C_NAME):
            cb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                                     if vis(x) and nm in (x.get_attribute('aria-label') or '')), None), 30)
            L.js_click(d, cb)
            time.sleep(1.5)
        L.js_click(d, btn(d, '批量设置评估维度'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '批量设置评估维度' in (x.text or '')), None), 30)
        time.sleep(2)
        ph['dialog_text'] = (dlg.text or '')[:1400]
        ph['rounds_default'] = [t for t in ['第1轮', '第2轮', '第3轮', '第4轮', '最后一轮'] if t in (dlg.text or '')]
        L.shot(d, 'C1_batch_dims_default')
        rb = next((x for x in dlg.find_elements(By.TAG_NAME, 'button') if '指定轮次' in (x.text or '')), None)
        if rb is not None:
            L.js_click(d, rb)
            time.sleep(1.5)
            ph['after_specific'] = (dlg.text or '')[:900]
            ph['rounds_specific'] = [t for t in ['第1轮', '第2轮', '第3轮', '第4轮', '最后一轮'] if t in (dlg.text or '')]
        L.shot(d, 'C2_batch_dims_specific')
        L.apply_theme(d, 'dark')
        L.shot(d, 'C3_batch_dims_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


# ============================== 阶段 D：导出真实下载
def phase_d():
    ph = {}
    d = L.driver()
    DL = os.path.join(L.ART, 'downloads2')
    os.makedirs(DL, exist_ok=True)
    try:
        d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DL})
    except Exception:
        pass
    try:
        L.login(d)
        d.get(L.BASE + '/testcases')
        time.sleep(7)
        open_group(d)
        L.clear_fetch_log(d)
        L.js_click(d, btn(d, '导出'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '导出' in (x.text or '')), None), 30)
        time.sleep(1)
        ph['dialog_text'] = (dlg.text or '')[:600]
        ph['selected_radio'] = next((x.get_attribute('aria-checked') for x in dlg.find_elements(By.CSS_SELECTOR, "[role='radio']")), None)
        L.shot(d, 'D1_export_dialog')
        L.js_click(d, btn(d, '开始导出'))
        time.sleep(0.3)
        ph['loading_seen'] = '导出中' in (L.body_text(d) or '')
        L.shot(d, 'D2_export_loading')
        ph['toasts'] = toasts(d, 90)
        ph['fetch'] = [(e.get('method'), (e.get('url') or '')[:110], e.get('status'), len(e.get('resBody') or ''))
                       for e in L.fetch_log(d, 'export')]
        for _ in range(20):
            if any(fn.endswith(('.json', '.xlsx')) for fn in os.listdir(DL)):
                break
            time.sleep(1)
        ph['downloads'] = [(fn, os.path.getsize(os.path.join(DL, fn))) for fn in os.listdir(DL)]
        L.apply_theme(d, 'dark')
        L.shot(d, 'D3_export_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


# ============================== 阶段 E：导出失败态（注入 502）
def phase_e():
    ph = {}
    d = fresh()
    try:
        d.execute_script("""
        window.__failExport = true;
        if (!window.__origFetchFail) { window.__origFetchFail = window.fetch; }
        window.fetch = function(input, init) {
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          if (window.__failExport && url.indexOf('/testcases/export') !== -1) {
            window.__failHit = (window.__failHit || 0) + 1;
            return Promise.resolve(new Response(JSON.stringify({success:false,code:502,message:'audit injected failure'}), {status:502, headers:{'content-type':'application/json'}}));
          }
          return window.__origFetchFail.apply(this, arguments);
        };
        """)
        open_group(d)
        L.js_click(d, btn(d, '导出'))
        dlg = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                  if vis(x) and '导出' in (x.text or '')), None), 30)
        time.sleep(1)
        L.js_click(d, btn(d, '开始导出'))
        time.sleep(1)
        ph['toasts'] = toasts(d, 30)
        ph['intercepted'] = d.execute_script('return window.__failHit || 0')
        L.shot(d, 'E1_export_error')
        L.apply_theme(d, 'dark')
        L.shot(d, 'E2_export_error_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


for name, fn in [('A_drawer', phase_a), ('B_ref_error', phase_b), ('C_batch_dims', phase_c),
                 ('D_export', phase_d), ('E_export_error', phase_e)]:
    try:
        OUT[name] = fn()
    except Exception:
        OUT[name] = {'fatal': traceback.format_exc()}
    print('PHASE_DONE', name, flush=True)

L.save_evidence('finalize2_evidence', OUT)
print(json.dumps({k: {kk: str(vv)[:200] for kk, vv in (v or {}).items()} for k, v in OUT.items()},
                 ensure_ascii=False, indent=1)[:8000])
