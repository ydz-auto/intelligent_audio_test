# -*- coding: utf-8 -*-
"""INT-1933 补证：
1) 保存失败 toast 文案（后端信封形状 {success:false, code, message}）；
2) 设备管理页 /devices API 页签「编辑」打开的弹窗形态（是否五页签 api-edit 弹窗）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

import int1643_lib as L  # noqa: E402

L.BASE = 'http://127.0.0.1:15173'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1933')
os.makedirs(L.ART, exist_ok=True)

OUT = {}


def shot(drv, name):
    L.shot(drv, name)


def goto_step2(drv):
    drv.get(L.BASE + '/start-test')
    time.sleep(5)
    steps = [b for b in drv.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    L.js_click(drv, steps[0])
    time.sleep(3.5)


def open_edit(drv, api_name):
    anchor = None
    for _ in range(10):
        for e in drv.find_elements(By.CSS_SELECTOR, "[aria-label='选择 API %s']" % api_name):
            if e.is_displayed():
                anchor = e
                break
        if anchor:
            break
        time.sleep(0.6)
    if anchor is None:
        raise RuntimeError('api card not found: %s' % api_name)
    node = anchor
    more = None
    for _ in range(8):
        node = node.find_element(By.XPATH, '..')
        ms = node.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']")
        if ms:
            more = ms[0]
            break
    L.js_click(drv, more)
    time.sleep(0.9)
    for i in [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if e.is_displayed()]:
        if (i.text or '').strip() == '编辑':
            L.js_click(drv, i)
            break
    time.sleep(2.5)


def inject(drv, mode):
    drv.execute_script("""
      if (!window.__p3_prevFetch) window.__p3_prevFetch = window.fetch;
      const mode = arguments[0];
      window.fetch = async function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const method = ((init && init.method) || 'GET').toUpperCase();
        if (mode === 'fail-put' && method === 'PUT' && /\\/apis\\/\\d+$/.test(url.split('?')[0])) {
          return new Response(JSON.stringify({success: false, code: 203, message: 'INT-1933 注入保存失败（500）', detail: '注入详情'}),
            {status: 500, headers: {'content-type': 'application/json'}});
        }
        return window.__p3_prevFetch.apply(this, arguments);
      };
    """, mode)


def restore(drv):
    drv.execute_script("if (window.__p3_prevFetch) { window.fetch = window.__p3_prevFetch; window.__p3_prevFetch = null; }")


def read_toasts(drv):
    return [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def main():
    d = L.driver()
    try:
        L.login(d)
        goto_step2(d)

        # 用自建临时记录做保存失败注入，避免碰真实记录
        tmp_name = '接线测试_INT1933_P3_' + time.strftime('%H%M%S')
        st, payload, raw = L.api_json(d, '/apis', 'POST', {
            'name': tmp_name, 'algorithm_type': 'voice_llm', 'default_max_process': 5,
            'description': 'p3', 'device_type': 'http_api',
            'endpoints': [{'endpoint': 'https://api.example.com/v1/asr', 'name': 'p3',
                           'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                           'status': 'online', 'priority': 1, 'description': None}],
            'meta': {'apiKey': 'p3-keep'},
        })
        tmp_id = ((payload or {}).get('data') or {}).get('id')
        OUT['tmp_id'] = tmp_id
        goto_step2(d)

        # ---- 1) 保存失败 toast 文案 ----
        inject(d, 'fail-put')
        open_edit(d, tmp_name)
        name_el = d.find_element(By.ID, 'api-name')
        name_el.click()
        name_el.send_keys(Keys.CONTROL, 'a')
        name_el.send_keys('SHOULD_NOT_SAVE_P3')
        time.sleep(0.4)
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '保存' and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(1.2)
        OUT['toasts_envelope'] = read_toasts(d)
        OUT['dialog_open_after_fail'] = bool(d.execute_script("""
            return Array.from(document.querySelectorAll("[role='dialog']")).some(dd => {
              const r=dd.getBoundingClientRect(); const s=getComputedStyle(dd);
              return r.width>0 && r.height>0 && s.display!=='none' && (dd.innerText||'').includes('请求模板');});
        """))
        shot(d, 'P3_save_fail_envelope')
        restore(d)
        # 关闭弹窗（若还开）
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '取消' and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(1.0)

        # ---- 2) 设备管理 API 页签编辑件形态 ----
        d.get(L.BASE + '/devices')
        time.sleep(5)
        # 切到 API 页签
        tabs = [(t.text or '').strip() for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.is_displayed()]
        OUT['device_tabs'] = tabs
        clicked = False
        for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if t.is_displayed() and (t.text or '').strip() in ('API', '测试 API', 'API 配置'):
                L.js_click(d, t)
                clicked = True
                break
        time.sleep(3.0)
        OUT['device_api_tab_clicked'] = clicked
        body = L.body_text(d)
        OUT['devices_body_head'] = body[:400]
        # 找行菜单/编辑
        edit_btns = []
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if not b.is_displayed():
                continue
            t = (b.text or '').strip()
            al = (b.get_attribute('aria-label') or '').strip()
            if t == '编辑' or '更多操作' in al or t == '编辑 API':
                edit_btns.append({'text': t, 'aria': al})
        OUT['device_edit_buttons'] = edit_btns[:20]
        shot(d, 'P3_devices_api_tab')

        # 若行内有「编辑」直接点
        opened = False
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and (b.text or '').strip() == '编辑':
                L.js_click(d, b)
                opened = True
                break
        if not opened:
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if b.is_displayed() and '更多操作' in (b.get_attribute('aria-label') or ''):
                    L.js_click(d, b)
                    time.sleep(0.8)
                    for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                        if i.is_displayed() and (i.text or '').strip() == '编辑':
                            L.js_click(d, i)
                            opened = True
                            break
                    break
        time.sleep(2.5)
        OUT['device_edit_opened'] = opened
        dlg_txt = d.execute_script("""
            const ds = Array.from(document.querySelectorAll("[role='dialog'],[role='alertdialog']"))
              .filter(dd => { const r=dd.getBoundingClientRect(); return r.width>0 && r.height>0; });
            const d = ds[ds.length-1];
            if (!d) return '';
            const tabs = Array.from(d.querySelectorAll("[role='tab']")).map(t=>(t.innerText||'').trim());
            return JSON.stringify({tabs: tabs, head: (d.innerText||'').slice(0,600),
                                   kind: d.getAttribute('data-slot') || '', role: d.getAttribute('role')});
        """)
        OUT['device_edit_dialog'] = dlg_txt
        shot(d, 'P3_device_edit_dialog')
        if tmp_id:
            st, _, raw = L.api_json(d, '/apis/%s' % tmp_id, 'DELETE')
            OUT['tmp_deleted'] = {'st': st, 'raw': raw[:80]}
        L.save_evidence('probe3', OUT)
        print(json.dumps(OUT, ensure_ascii=False, indent=1))
    finally:
        d.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
