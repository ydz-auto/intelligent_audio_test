# -*- coding: utf-8 -*-
"""INT-2419 补充验收探针（测试工程师）：主探针 probe_int2419_batch_export.py 未覆盖的项。

覆盖卡面可测验收标准的剩余项：
  A. 失败隔离（验收 4）：人为让 1 份报告的详情取数失败 →
     其余报告仍成功打包，结果面板给出「报告名 + 原因」失败清单，zip 只含成功份；
  B. 连续点击（验收 6）：导出中主按钮 disabled，重复点击不产生第二个 zip；
  C. 状态复原（验收 6）：导出结束页面滚动位置不变、主题不变、离屏宿主已卸载、页面可继续操作；
  D. 对比报告（387 用例）逐份对照单份导出（验收 2）：锚点 / 表头 / 用例集合 / 数字集合 / 图表静态图。

跑法：
  python tests/ui/probe_int2419_verify_extras.py --base http://localhost:5336
  （环境变量 UI_TEST_USERNAME / UI_TEST_PASSWORD 可覆盖登录账号）
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui import probe_int2419_batch_export as pb  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2419_extras')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'notes': []}

# 主探针产物目录：批量 zip 解压结果（对比报告 387 用例那份）
MAIN_ART = os.path.join(sm.ART_ROOT, 'int2419')


def log(msg):
    print('[int2419-extra] %s' % msg, flush=True)


def zips_in(dl_dir, since=0):
    files = [
        f for f in glob.glob(os.path.join(dl_dir, '*.zip'))
        if os.path.getmtime(f) >= since
    ]
    return sorted(files, key=os.path.getmtime)


def install_detail_failure(driver, report_id):
    """把指定报告的详情请求打桩成失败（模拟取数失败），其余请求原样放行。"""
    return driver.execute_script(
        """
        var id = String(arguments[0]);
        if (!window.__origFetch) window.__origFetch = window.fetch;
        window.__failReportId = id;
        window.fetch = function(input, init) {
          var url = typeof input === 'string' ? input : (input && input.url) || '';
          var method = ((init && init.method) || 'GET').toUpperCase();
          var re = new RegExp('/api/v1/reports/' + id + '(\\\\?|$)');
          if (method === 'GET' && re.test(url)) {
            return Promise.reject(new TypeError('模拟取数失败'));
          }
          return window.__origFetch.apply(this, arguments);
        };
        return true;
        """,
        report_id,
    )


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    pb.RESULT['base'] = base
    os.makedirs(ART, exist_ok=True)

    sm.env_check('extras_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    dl_dir = os.path.join(ART, 'downloads')
    os.makedirs(dl_dir, exist_ok=True)
    for f in glob.glob(os.path.join(dl_dir, '*')):
        try:
            os.remove(f)
        except OSError:
            pass
    driver = sm.make_driver(dl_dir)
    try:
        smoke.drv = driver
        login = smoke.login()
        RESULT['checks']['login'] = {'ok': login.get('ok'), 'url': login.get('url_after')}
        assert login.get('ok'), '登录失败: %s' % login

        # 主探针已导出的批量产物（对比报告 387 用例）
        with open(os.path.join(MAIN_ART, 'summary.json'), encoding='utf-8') as fh:
            main_summary = json.load(fh)
        picked = main_summary['checks']['picked']
        names = [p['name'] for p in picked]
        failing = next(p for p in picked if p['type'] == 'task')
        succeeding = next(p for p in picked if p['type'] != 'task')
        RESULT['checks']['scenario'] = {
            'fail': {'id': failing['id'], 'name': failing['name']},
            'ok': {'id': succeeding['id'], 'name': succeeding['name'], 'stats': succeeding['stats']},
        }

        # ---- A/B/C: 失败隔离 + 连点 + 状态复原 ----
        pb.open_report_center(driver, base)
        scroll_before = driver.execute_script('return window.scrollY')
        theme_before = driver.execute_script(
            "return document.documentElement.classList.contains('dark')")
        RESULT['checks']['selected'] = pb.select_reports(driver, [failing['name'], succeeding['name']])
        install_detail_failure(driver, failing['id'])
        RESULT['checks']['scroll_before'] = scroll_before
        RESULT['checks']['theme_before'] = bool(theme_before)

        opened = pb.open_export_html(driver)
        RESULT['checks']['dialog'] = {'ok': opened.get('ok'), 'error': opened.get('error')}
        assert opened.get('ok'), '导出弹窗/格式选择失败: %s' % opened

        since = time.time()
        assert pb.click_export_main(driver), '导出主钮点击失败'
        progress_text = pb.wait_progress(driver, timeout=60)
        RESULT['checks']['progress_text'] = progress_text

        # B. 导出中主按钮 disabled + 重复点击
        btn_state = driver.execute_script(
            """
            var btns = document.querySelectorAll('[role=dialog] button');
            for (var i = btns.length - 1; i >= 0; i--) {
              var t = (btns[i].innerText || '').trim();
              if (t === '导出' || t === '导出中...') {
                return {text: t, disabled: btns[i].disabled};
              }
            }
            return null;
            """)
        RESULT['checks']['main_button_mid_export'] = btn_state
        double_click = driver.execute_script(
            """
            var btns = document.querySelectorAll('[role=dialog] button');
            for (var i = btns.length - 1; i >= 0; i--) {
              var t = (btns[i].innerText || '').trim();
              if (t === '导出' || t === '导出中...') { btns[i].click(); btns[i].click(); return true; }
            }
            return false;
            """)
        RESULT['checks']['double_click_attempted'] = bool(double_click)

        zip_path = pb.wait_zip(dl_dir, timeout=420, since=since)
        RESULT['checks']['zip'] = os.path.basename(zip_path) if zip_path else None
        result_text = None
        for _ in range(30):
            result_text = driver.execute_script(
                "var el = document.querySelector('[data-testid=batch-export-result]');"
                "return el ? (el.innerText || '').trim() : null")
            if result_text and ('导出完成' in result_text or '失败' in result_text):
                break
            time.sleep(0.5)
        RESULT['checks']['result_text'] = result_text
        assert zip_path, '未收到 zip（失败隔离场景）'

        # 连点只产生 1 个 zip
        time.sleep(3)
        all_zips = zips_in(dl_dir, since)
        RESULT['checks']['zip_count_after'] = [os.path.basename(z) for z in all_zips]

        entries = pb.unzip_to(zip_path, os.path.join(ART, 'batch_partial'))
        subdirs = sorted({n.split('/')[0] for n in entries if '/' in n})
        RESULT['checks']['partial_zip'] = {
            'entries': entries,
            'subdirs': subdirs,
            'has_index': 'index.html' in entries,
        }
        RESULT['checks']['partial_ok'] = (
            len(subdirs) == 1
            and failing['name'] not in (subdirs[0] if subdirs else '')
        )

        # C. 状态复原
        time.sleep(2)
        RESULT['checks']['after_state'] = {
            'scroll': driver.execute_script('return window.scrollY'),
            'theme_dark': bool(driver.execute_script(
                "return document.documentElement.classList.contains('dark')")),
            'stage_left': driver.execute_script(
                "return document.querySelectorAll('[data-batch-export-stage]').length"),
            'rows': driver.execute_script(
                "return document.querySelectorAll('[role=row]').length"),
        }
        RESULT['checks']['restore_shot'] = sm.shot(driver, 'extras_after_export')

        # ---- D. 对比报告（387 用例）单份 vs 批量逐项对照 ----
        batch_root = os.path.join(MAIN_ART, 'batch')
        target = succeeding
        batch_dir_name = None
        for html_path in glob.glob(os.path.join(batch_root, '*', 'report.html')):
            with open(html_path, encoding='utf-8') as fh:
                head = fh.read(4000)
            if target['name'] in head:
                batch_dir_name = html_path
                break
        single_zip, single_html = pb.single_export_html(smoke.drv, target['id'], dl_dir)
        RESULT['checks']['single_zip'] = os.path.basename(single_zip) if single_zip else None
        if not (batch_dir_name and single_html):
            RESULT['checks']['compare_comparison'] = {
                'error': '批量产物或单份产物缺失',
                'batch_html': bool(batch_dir_name),
                'single_html': bool(single_html),
            }
        else:
            with open(batch_dir_name, encoding='utf-8') as fh:
                batch_html = fh.read()
            b = pb.parse_html(batch_html)
            s = pb.parse_html(single_html)
            compare = {
                'target': target['name'],
                'anchors_equal': b['anchors'] == s['anchors'],
                'ths_equal': b['ths'] == s['ths'],
                'case_ids_equal': b['case_ids'] == s['case_ids'],
                'numbers_equal': b['numbers'] == s['numbers'],
                'chart_imgs': [b['chart_imgs'], s['chart_imgs']],
                'cards': [len(b['case_ids']), len(s['case_ids'])],
                'api_distinct_cases': target['stats']['distinct_cases'],
                'residual_actions': [b['residual_actions'], s['residual_actions']],
                'diff': {
                    'anchors': [a for a in s['anchors'] if a not in b['anchors']],
                    'ths_missing': [t for t in s['ths'] if t not in b['ths']],
                    'numbers_missing_head': [
                        n for n in s['numbers'] if n not in b['numbers']][:20],
                },
            }
            RESULT['checks']['compare_comparison'] = compare

        checks = RESULT['checks']
        partial = checks.get('partial_zip') or {}
        expect_dir = target['name'][:max(len(target['name']), 0)]
        result_text = checks.get('result_text') or ''
        ok = bool(
            len(checks.get('zip_count_after') or []) == 1
            and (checks.get('main_button_mid_export') or {}).get('disabled')
            and len(partial.get('subdirs') or []) == 1
            and partial.get('has_index')
            and '失败 1 份' in result_text
            and failing['name'] in result_text
            and checks['after_state']['stage_left'] == 0
            and checks['after_state']['theme_dark'] == checks.get('theme_before')
            and checks['after_state']['scroll'] == checks.get('scroll_before')
        )
        cmp = checks.get('compare_comparison') or {}
        if cmp and not cmp.get('error'):
            ok = ok and all([
                cmp.get('anchors_equal'), cmp.get('ths_equal'),
                cmp.get('case_ids_equal'), cmp.get('numbers_equal'),
                cmp.get('cards', [0, 0])[0] == target['stats']['distinct_cases'],
            ])
        RESULT['ok'] = ok
        sm.env_check('extras_end')
    except Exception as exc:
        RESULT['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:500])
        try:
            RESULT['checks']['fail_shot'] = sm.shot(driver, 'extras_fail')
        except Exception:
            pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary_extras.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('SUMMARY_JSON=%s' % out_path)
    print('OK=%s' % RESULT.get('ok'))


if __name__ == '__main__':
    main()
