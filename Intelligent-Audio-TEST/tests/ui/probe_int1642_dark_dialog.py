# -*- coding: utf-8 -*-
"""INT-1642 返工补充取证：
1) 深色下导出弹窗面板的实际背景色（截图看似浅色，核 computed style，区分真缺陷 vs 截图错觉）；
2) 「仅导出已选」请求体只含所选（上一版脚本取字段名写错导致为空，补一次干净取证）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1642_rework as V  # noqa: E402

ART = V.ART


def main():
    d = V.make_driver()
    out = {}
    added = []
    try:
        out['login_ok'] = V.login(d)
        # --- 深色：导出弹窗面板背景 ---
        V.js(d, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get('about:blank')
        d.get(V.BASE + '/testcases')
        assert V.wait_body(d, '用例管理', 90), 'page not loaded'
        time.sleep(3)
        assert V.open_export(d), 'export dialog not open'
        out['dark_dialog_styles'] = V.js(d, """
          const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'));
          const dl = dlgs[dlgs.length - 1];
          const panel = dl.querySelector('[data-slot="dialog-content"]') || dl;
          const cs = getComputedStyle(panel);
          const body = getComputedStyle(document.body);
          return {count: dlgs.length, panelBg: cs.backgroundColor, panelColor: cs.color,
                  bodyBg: body.backgroundColor,
                  htmlClass: document.documentElement.className,
                  stored: localStorage.getItem('iatp:theme:v1:mode')};
        """)
        out['dark_shot'] = V.shot(d, '09_export_dialog_dark_probe')
        V.click_btn(d, '取消', 15)
        # 对照：同页「新建用例」抽屉/弹窗（非本卡改动）是否同样浅色
        try:
            V.click_btn(d, '新建用例', 20)
            time.sleep(2)
            out['other_dialog_dark'] = V.js(d, """
              const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'));
              const dl = dlgs[dlgs.length - 1];
              if (!dl) return null;
              const panel = dl.querySelector('[data-slot="dialog-content"]') || dl;
              const cs = getComputedStyle(panel);
              return {panelBg: cs.backgroundColor, panelColor: cs.color};
            """)
            V.shot(d, '10_other_dialog_dark')
            V.js(d, "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
            time.sleep(1.2)
        except Exception as e:
            out['other_dialog_error'] = str(e)[:200]
        V.js(d, "localStorage.setItem('iatp:theme:v1:mode','light');")

        # --- 「仅导出已选」请求体 ---
        d.get(V.BASE + '/testcases')
        assert V.wait_body(d, '用例管理', 90), 'page not loaded (light)'
        time.sleep(3)
        base_ids, _ = V.favorite_ids(d)
        r = {}
        for _ in range(4):
            r = V.api(d, 'GET', '/api/v1/testcases?page=1&per_page=20')
            items = ((r.get('body') or {}).get('data') or {}).get('items') or []
            if items:
                break
            time.sleep(6)
        targets = [i for i in items if i.get('id') not in base_ids][:2]
        for t in targets:
            st = V.api(d, 'POST', '/api/v1/testcases/%s/favorite' % t['id'])
            if st.get('status') in (200, 201):
                added.append(t)
        out['fixture'] = [{'id': t['id'], 'name': t['name']} for t in added]
        fav_ids, _ = V.favorite_ids(d)
        out['favorite_ids'] = fav_ids

        d.get(V.BASE + '/testcases')
        assert V.wait_body(d, '用例管理', 90), 'page not loaded (fav)'
        time.sleep(3)
        V.toggle_favorite_filter(d)
        V.expand_all_groups(d)
        time.sleep(1.2)
        cards = V.card_checkboxes(d)
        for c in cards:
            V.js_click(d, c)
        time.sleep(1.2)
        out['selected'] = V.selected_cards(d)
        assert V.open_export(d), 'export dialog not open (selected)'
        radio = V.wait_fn(d, lambda: next((i for i in d.find_elements(
            V.By.CSS_SELECTOR, "input[name='export-range']") if not i.is_selected()), None), 15)
        V.js_click(d, radio)
        time.sleep(0.8)
        out['radio'] = V.radio_state(d)
        V.clear_downloads()
        V.clear_log(d)
        V.click_btn(d, '开始导出', 20)
        V.wait_fn(d, lambda: any(s in V.body_text(d) for s in ('已导出', '导出失败')), 90)
        time.sleep(1.5)
        calls = V.fetch_log(d, '/testcases/export')
        out['export_calls'] = [{'url': c.get('url'), 'status': c.get('status'),
                                'req': c.get('reqBody')} for c in calls]
        f = V.newest_download('testcases_export_')
        if f:
            out['file'] = os.path.basename(f)
            out['size'] = os.path.getsize(f)
            if f.endswith('.json'):
                data = json.load(open(f, encoding='utf-8'))
                out['file_total'] = data.get('total_count')
                out['file_ids'] = [c.get('id') for c in (data.get('test_cases') or [])]
        out['toast_ok'] = '已导出' in V.body_text(d)
        V.shot(d, '11_selected_export_probe')
    finally:
        try:
            for t in added:
                V.api(d, 'DELETE', '/api/v1/testcases/%s/favorite' % t['id'])
            after, _ = V.favorite_ids(d)
            out['favorite_after_cleanup'] = len(after)
        except Exception as e:
            out['cleanup_error'] = str(e)[:200]
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'probe.json'), 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
