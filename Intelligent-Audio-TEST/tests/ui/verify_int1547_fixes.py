# -*- coding: utf-8 -*-
"""INT-1547 五项修复复走（INT-1482 报告域六窗复测）+ A/B 对照。

用法：
  set REACT_BASE=http://localhost:15319 & set VARIANT=fix   → 修复构建（旁路容器）
  set REACT_BASE=http://localhost:15173 & set VARIANT=old   → 共享旧镜像（对照）
输出：tests/ui/artifacts/int1482/verify_1547_<variant>.json

覆盖：P2-1 编辑报告回填 / P2-2 音频播放真实 url / P2-3 统计页首屏不被 case-averages 阻塞 /
      P2-4 导出历史去 mock + 真实导出 / P2-5 统计报表走真实 POST /reports/export。
"""
import atexit
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

VARIANT = os.environ.get('VARIANT', 'fix')
REPORT = int(os.environ.get('REPORT_ID', '481'))
OUT = {'variant': VARIANT, 'base': L.BASE, 'report_id': REPORT}
OUT_PATH = os.path.join(L.ART, 'verify_1547_%s.json' % VARIANT)


def save():
    try:
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    t0 = time.time()
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1500:]
    OUT[name + '_dur_s'] = round(time.time() - t0, 1)
    save()


def shot(name):
    return L.shot(shot.d, '%s_%s' % (name, VARIANT))


shot.d = None


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def rtext(el):
    return (el.get_attribute('textContent') or '').strip()


def wait_rows(d, timeout=60):
    WebDriverWait(d, timeout).until(lambda x: len(rows(x)) > 0)
    return rows(d)


def row_action(d, idx, item_text, wait=1.2):
    r = rows(d)[idx]
    btn = r.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作') or contains(@aria-label,'更多操作')]")
    L.js_click(d, btn)
    time.sleep(0.8)
    menu = [m for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if m.is_displayed()]
    for m in menu:
        if item_text in (m.text or '').strip():
            L.js_click(d, m)
            time.sleep(wait)
            return True
    raise AssertionError('菜单项缺失 %s，现有 %s' % (item_text, [m.text for m in menu]))


def find_row_by_id(d, rid):
    for i, tr in enumerate(rows(d)):
        if ('#%s' % rid) in rtext(tr):
            return i
    return None


def req_log(d, contains=None, since=0):
    out = []
    for e in L.fetch_log(d, since):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody', 'error')})
    return out


def open_center(d):
    d.get(L.BASE + '/report-center')
    wait_rows(d, 90)
    time.sleep(1.5)


def main():
    d = L.driver()
    shot.d = d
    try:
        L.login(d)
        open_center(d)
        OUT['center_rows'] = len(rows(d))
        rid = None
        try:
            r = L.api(d, '/reports?page=1&per_page=5')
            dd = (r['json'] or {}).get('data') or {}
            items = dd.get('items') or dd.get('list') or []
            if items:
                rid = items[0].get('id')
                OUT['target_report_row'] = {k: items[0].get(k) for k in ('id', 'name', 'status', 'task_id')}
        except Exception:
            pass
        OUT['target_report_id'] = rid

        # ---------- P2-1 编辑报告回填 ----------
        def rename():
            idx = find_row_by_id(d, rid) if rid else None
            if idx is None:
                idx = 0
            OUT['rename_row_text'] = rtext(rows(d)[idx])[:160]
            row_action(d, idx, '编辑')
            dl = L.wait_dialog(d, '编辑报告')
            time.sleep(0.8)
            name = dl.find_element(By.ID, 'rename-name').get_attribute('value')
            desc = dl.find_element(By.ID, 'rename-desc').get_attribute('value')
            OUT['rename_prefill_name'] = name
            OUT['rename_prefill_desc'] = desc
            r = L.api(d, '/reports/%s' % rid)
            dd = (r['json'] or {}).get('data') or {}
            OUT['rename_api_name'] = dd.get('name')
            OUT['rename_match'] = bool(name) and name == dd.get('name')
            shot('p2-1_rename')
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('p2_1_rename_prefill', rename)

        # ---------- P2-4 导出历史去 mock + P2-4 真实导出 ----------
        def export():
            open_center(d)
            L.reset_fetch_log(d)
            idx = find_row_by_id(d, rid) if rid else 0
            # 行菜单无导出项：用页面级「更多操作」→「导出」（INT-1482 批次 A 同路径）
            try:
                L.js_click(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
            except Exception:
                row_action(d, idx, '查看')
            time.sleep(1)
            menu = [m for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if m.is_displayed()]
            OUT['page_more_menu'] = [m.text for m in menu]
            picked = None
            for m in menu:
                if '导出' in (m.text or ''):
                    L.js_click(d, m)
                    picked = m.text
                    break
            OUT['page_more_picked'] = picked
            time.sleep(1.2)
            if picked is None:
                raise AssertionError('页面「更多操作」无导出项：%s' % OUT['page_more_menu'])
            dl = L.wait_dialog(d, '导出报告')
            time.sleep(1.2)
            OUT['export_dialog_text'] = dl.text[:400]
            # 先看历史页签（未导出前）
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '导出历史':
                    L.js_click(d, t)
                    time.sleep(1)
                    break
            dl2 = L.wait_dialog(d, '导出报告')
            OUT['history_before'] = dl2.text[:500]
            OUT['history_mock_rows'] = dl2.text.count('旗舰音箱') + dl2.text.count('API 通道并发稳定性验证报告')
            shot('p2-4_export_history_before')
            # 回到导出页签，真实导出
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() in ('导出', '导出报告'):
                    L.js_click(d, t)
                    time.sleep(0.8)
                    break
            L.reset_fetch_log(d)
            btn = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() in ('导出', '开始导出', '导出报告')]
            if btn:
                L.js_click(d, btn[-1])
            t0 = time.time()
            reqs = []
            for _ in range(60):
                time.sleep(1)
                reqs = req_log(d, '/reports/export')
                if reqs:
                    break
            OUT['export_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in reqs]
            OUT['export_wait_s'] = round(time.time() - t0, 1)
            time.sleep(8)
            dl3 = [x for x in L.dialogs(d)]
            OUT['export_after_text'] = dl3[0]['text'][:500] if dl3 else None
            shot('p2-4_export_progress')
            # 导出历史页签（应有本次真实导出记录）
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '导出历史':
                    L.js_click(d, t)
                    time.sleep(1)
                    break
            dl4 = L.wait_dialog(d, '导出报告')
            OUT['history_after'] = dl4.text[:600]
            OUT['history_after_rows'] = len(dl4.find_elements(By.CSS_SELECTOR, 'tbody tr'))
            shot('p2-4_export_history_after')
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('p2_4_export', export)

        # ---------- P2-2 音频播放真实 url ----------
        def audio():
            L.reset_fetch_log(d)
            d.get(L.BASE + '/report/%s' % REPORT)
            WebDriverWait(d, 90).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
            time.sleep(3)
            root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
            d.execute_script("arguments[0].scrollIntoView({block:'start'})", root)
            # 先展开分组，再点首个用例「详情」打开用例结果抽屉/弹窗
            for h in root.find_elements(By.CSS_SELECTOR, "button[aria-expanded='false'], [data-state='closed']"):
                try:
                    L.js_click(d, h)
                    time.sleep(0.6)
                except Exception:
                    pass
            time.sleep(1)
            detail_btns = [b for b in root.find_elements(By.TAG_NAME, 'button')
                           if (b.text or '').strip() in ('详情', '展开详情') and b.is_displayed()]
            OUT['case_detail_entries'] = len(detail_btns)
            if not detail_btns:
                raise AssertionError('未找到用例详情入口')
            L.js_click(d, detail_btns[0])
            time.sleep(2.5)
            plays = []
            for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
                try:
                    plays += [b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']") if b.is_displayed()]
                except Exception:
                    pass
            OUT['audio_play_buttons'] = len(plays)
            if not plays:
                raise AssertionError('未找到播放按钮')
            L.reset_fetch_log(d)
            L.js_click(d, plays[0])
            time.sleep(2.5)
            shot('p2-2_audio_player')
            audio_els = d.find_elements(By.CSS_SELECTOR, "[role='dialog'] audio")
            OUT['audio_tags_in_dialog'] = len(audio_els)
            OUT['audio_src'] = audio_els[0].get_attribute('src') if audio_els else None
            OUT['audio_dialog_text'] = [x['text'][:300] for x in L.dialogs(d)]
            OUT['audio_play_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in req_log(d, '/audios/play')]
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('p2_2_audio', audio)

        # ---------- P2-3 统计页首屏 + P2-5 统计报表真实导出 ----------
        def stats():
            L.reset_fetch_log(d)
            t0 = time.time()
            d.get(L.BASE + '/report-statistics')
            # 首屏统计卡出现（报告数量/用例总数）
            WebDriverWait(d, 90).until(lambda x: '报告数量' in (x.page_source or ''))
            shot('p2-3_stats_first_paint')
            OUT['stats_first_paint_s'] = round(time.time() - t0, 1)
            # 统计卡数值（记录首次出现时文本，判定是否恒 0）
            body0 = d.execute_script("return document.body.textContent||''")
            OUT['stats_body_first'] = body0[:600]
            # 等 case-averages 落地（最多 90s），观察评估维度区
            got = False
            for _ in range(45):
                time.sleep(2)
                txt = d.execute_script("return document.body.textContent||''")
                if ('评估指标' in txt and '暂无任务执行数据' not in txt) or '统计加载中' not in txt:
                    got = True
                    break
            OUT['stats_avg_settled'] = got
            OUT['stats_avg_wait_s'] = round(time.time() - t0, 1)
            OUT['stats_body_after'] = (d.execute_script("return document.body.textContent||''"))[:900]
            OUT['stats_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in
                                 req_log(d, '/reports/case-averages') + req_log(d, '/reports/tab-counts')]
            shot('p2-3_stats_after')
            # 统计报表页签（界面文案「报表生成」）
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() in ('报表生成', '统计报表'):
                    L.js_click(d, t)
                    time.sleep(1.2)
                    break
            shot('p2-5_stats_report_form')
            L.reset_fetch_log(d)
            btn = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() in ('生成报表', '生成中...')]
            OUT['stats_report_btn_text'] = [b.text for b in btn]
            if btn:
                L.js_click(d, btn[-1])
            reqs = []
            for _ in range(60):
                time.sleep(1)
                reqs = req_log(d, '/reports/export')
                if reqs:
                    break
            OUT['stats_report_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status', 'reqBody')} for e in reqs]
            time.sleep(6)
            shot('p2-5_stats_report_after')
            OUT['stats_report_body'] = (d.execute_script("return document.body.textContent||''"))[:600]
        section('p2_3_p2_5_statistics', stats)

    finally:
        save()
        try:
            d.quit()
        except Exception:
            pass
    print('WROTE', OUT_PATH)


if __name__ == '__main__':
    main()
