# -*- coding: utf-8 -*-
"""INT-2418 前端UX审计（第二轮）复测：P3-1 空壳控制卡 / P3-2 计数口径 + 回归。

跑法：
  UI_TEST_USERNAME=dev_user UI_TEST_PASSWORD=dev_password \
  python tests/ui/probe_int2418_audit_p3.py --base http://localhost:15302

只测审计打回的两项 P3 与相关回归（导出主链路 / 离线 / 无后端导出 / 页面未受伤）。
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui import probe_int2418_export_rework as base  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2418_audit_p3')
RESULT = {'checks': {}}


def log(msg):
    print('[audit2418] %s' % msg, flush=True)


PAGE_CARD_JS = """return (function(){
  var t = document.body.innerText || '';
  var ph = function(p){ return document.querySelector('.report-view-container [placeholder="' + p + '"]'); };
  var saveBtn = Array.from(document.querySelectorAll('.report-view-container button'))
    .filter(function(b){ return (b.textContent||'').trim() === '保存'; });
  var selector = Array.from(document.querySelectorAll('.report-view-container p'))
    .filter(function(p){ return (p.textContent||'').trim() === '选择要对比的设备和API'; });
  var selectorButtons = selector.length
    ? selector[0].parentElement.querySelectorAll('button').length : -1;
  return {
    save_text: t.indexOf('报告保存') >= 0,
    selector_text: t.indexOf('选择要对比的设备和API') >= 0,
    save_name_input: !!ph('请输入报告名称'),
    save_desc_input: !!ph('请输入报告描述'),
    save_buttons: saveBtn.length,
    selector_rows: selectorButtons,
    both_visible: (function(){
      var p1 = Array.from(document.querySelectorAll('.report-view-container p'))
        .filter(function(p){ return (p.textContent||'').trim() === '报告保存'; })[0];
      return !!(p1 && p1.offsetParent !== null);
    })(),
    export_hide_on_page: document.querySelectorAll('.report-view-container [data-export-hide]').length
  };
})()"""

TOOLBAR_JS = """return (function(){
  var info = document.getElementById('export-case-pageinfo');
  var hdr = document.querySelector('#report-specific-cases');
  var t = hdr ? (hdr.innerText || '') : '';
  return {
    pageinfo: info ? (info.textContent || '') : null,
    header_has_result: t.indexOf('条结果') >= 0,
    header_text: t.slice(0, 160),
    cards: document.querySelectorAll('[data-case-index]').length,
    case_total_attr: (document.querySelector('[data-export-case-total]') || {}).getAttribute
        ? document.querySelector('[data-export-case-total]').getAttribute('data-export-case-total') : null,
    sections: Array.from(document.querySelectorAll('main section[id]')).map(function(s){return s.id;}),
    first_section_after_header: (function(){
      var secs = Array.from(document.querySelectorAll('main section[id]'));
      return secs.length ? secs[0].id : null;
    })(),
    residual_buttons: Array.from(document.querySelectorAll('button')).map(function(b){return (b.textContent||'').trim();})
      .filter(function(t){return ['保存','发布','取消发布','导出','删除','彻底删除','下载日志','人工复核'].indexOf(t)>=0;})
  };
})()"""


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--report', type=int, default=395)
    args = ap.parse_args()
    url_base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)

    sm.env_check('audit_p3_start')
    smoke = sm.Smoke('react', url_base)
    sm.RESULT['art'] = ART
    d = sm.make_driver(os.path.join(ART, 'downloads_driver'))
    rec = {}
    try:
        smoke.drv = d
        base.login_harness(smoke)
        detail = '%s/report/%d' % (url_base, args.report)
        d.get(detail)
        time.sleep(9)
        sm.wait_quiet(d, 40)

        # ---- 页面侧：两张控制卡仍在且可操作（P3-1 不能伤页面）----
        rec['page'] = d.execute_script(PAGE_CARD_JS)
        rec['page_shot_light'] = sm.shot(d, 'audit_p3_page_light')
        log('PAGE %s' % json.dumps(rec['page'], ensure_ascii=False))

        # ---- 导出 HTML ----
        sm.parse_perf(d.get_log('performance'))  # 清空
        z, dl_dir = base.export_zip(d, 'p3')
        assert z, '导出未下载到 zip'
        rec['zip'] = {'name': os.path.basename(z), 'size': os.path.getsize(z)}
        out = os.path.join(ART, 'export')
        rec['entries'] = base.extract(z, out)
        html_path = os.path.join(out, 'report.html')
        html = open(html_path, encoding='utf-8').read()
        rec['html_size'] = len(html)

        rec['static'] = {
            'save_card_title': html.count('报告保存'),
            'selector_title': html.count('选择要对比的设备和API'),
            'data_export_hide_left': html.count('data-export-hide'),
            'empty_grid': len(re.findall(r'sm:grid-cols-2"?>\s*</div>', html)),
            'has_device_names': ('pura90' in html),
            'has_btn_save': bool(re.search(r'>\s*保存\s*</button>', html)),
        }
        # 导出期间无后端导出请求
        perf = sm.parse_perf(d.get_log('performance'))
        rec['export_requests'] = [a.get('url') for a in perf
                                  if '/reports/export' in (a.get('url') or '')
                                  and (a.get('method') or '').upper() == 'POST']
        rec['export_shot'] = sm.shot(d, 'audit_p3_page_after_export')

        # ---- file:// 打开导出物 ----
        fpath = html_path.replace('\\', '/')
        sm.parse_perf(d.get_log('performance'))
        d.get('file:///' + fpath)
        time.sleep(3)
        rec['offline_http'] = [a.get('url') for a in sm.parse_perf(d.get_log('performance'))
                               if (a.get('url') or '').startswith(('http://', 'https://'))]
        rec['offline'] = {
            'images': d.execute_script('return document.images.length'),
            'broken': d.execute_script(
                'return Array.from(document.images).filter(function(i){return i.complete && i.naturalWidth===0;}).length'),
            'body_bg': d.execute_script('return getComputedStyle(document.body).backgroundColor'),
            'has_dark_class': d.execute_script("return document.documentElement.classList.contains('dark')"),
        }
        rec['exported'] = d.execute_script(TOOLBAR_JS)
        rec['export_shot_top'] = sm.shot(d, 'audit_p3_export_top')
        sec = d.find_element(By.ID, 'report-specific-cases')
        d.execute_script("arguments[0].scrollIntoView({block:'start'});", sec)
        time.sleep(1)
        rec['export_shot_cases'] = sm.shot(d, 'audit_p3_export_cases')

        # 导出内分页/搜索回归（工具条文案 + 翻页）
        d.execute_script("document.getElementById('export-case-next') && document.getElementById('export-case-next').click();")
        time.sleep(1)
        rec['page2'] = d.execute_script(
            "var i=document.getElementById('export-case-pageinfo'); return i?i.textContent:null;")

        # ---- 导出后回页面：控制卡仍在、主题保持 ----
        d.get(detail)
        time.sleep(8)
        sm.wait_quiet(d, 40)
        rec['page_after'] = d.execute_script(PAGE_CARD_JS)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(8)
        sm.wait_quiet(d, 40)
        rec['dark'] = {
            'is_dark': d.execute_script("return document.documentElement.classList.contains('dark')"),
            'card_visible': d.execute_script(PAGE_CARD_JS),
        }
        rec['page_shot_dark'] = sm.shot(d, 'audit_p3_page_dark')

        # 结论
        ok_p3_1 = (rec['static']['save_card_title'] == 0
                   and rec['static']['selector_title'] == 0
                   and rec['static']['data_export_hide_left'] == 0
                   and rec['static']['empty_grid'] == 0
                   and rec['page']['save_text'] and rec['page']['selector_text']
                   and rec['page']['save_name_input'] and rec['page']['save_desc_input']
                   and rec['page']['save_buttons'] > 0 and rec['page']['selector_rows'] > 0
                   and rec['page']['both_visible'] and rec['page']['export_hide_on_page'] == 6
                   and rec['page_after']['save_text'] and rec['page_after']['selector_text'])
        info = rec['exported']['pageinfo'] or ''
        m = re.search(r'总计\s*(\d+)\s*个用例', info)
        ok_p3_2 = (bool(m)
                   and '条结果' not in info
                   and rec['exported']['header_has_result']
                   and rec['exported']['cards'] == int(rec['exported']['case_total_attr'] or -1))
        rec['ok_p3_1'] = ok_p3_1
        rec['ok_p3_2'] = ok_p3_2
        rec['toolbar_count'] = int(m.group(1)) if m else None
        rec['ok_regression'] = (not rec['export_requests']
                               and not rec['offline_http']
                               and rec['offline']['broken'] == 0
                               and rec['offline']['has_dark_class'] is False
                               and not rec['exported']['residual_buttons']
                               and len(rec['entries']) >= 2)
        RESULT['checks']['report'] = rec
        RESULT['ok'] = bool(ok_p3_1 and ok_p3_2 and rec['ok_regression'])
        RESULT['console_errors'] = sm.console_errors(d)
        sm.env_check('audit_p3_end')
    finally:
        try:
            d.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('SUMMARY_JSON=%s' % out_path)
    print('OK=%s' % RESULT.get('ok'))


if __name__ == '__main__':
    main()
