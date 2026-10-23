# -*- coding: utf-8 -*-
"""INT-1482 批次C：分享配置全量 / 音频播放 Modal / 中心确认弹窗取消路径 / 统计报表页与报表生成。"""
import atexit
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
STAMP = time.strftime('%H%M%S')


def save():
    try:
        with open(os.path.join(L.ART, 'batchC_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1200:]
    save()


def dlg_texts(d):
    return [x['text'][:600] for x in L.dialogs(d)]


def req_log(d, contains=None, since=0):
    out = []
    for e in L.fetch_log(d, since):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody', 'error')})
    return out


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def rtext(el):
    return (el.get_attribute('textContent') or '').strip()


def find_row_by_id(d, rid):
    for i, tr in enumerate(rows(d)):
        if ('#%s' % rid) in rtext(tr):
            return i
    return None


def row_action(d, idx, item_text, wait=1.2):
    btn = rows(d)[idx].find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
    L.js_click(d, btn)
    time.sleep(0.8)
    for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
        if m.is_displayed() and (m.text or '').strip() == item_text:
            L.js_click(d, m)
            time.sleep(wait)
            return True
    raise AssertionError('菜单项缺失 %s' % item_text)


def open_report(d, rid):
    d.get(L.BASE + '/report/%s' % rid)
    WebDriverWait(d, 60).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
    time.sleep(3)


def case_root(d):
    return d.find_element(By.CSS_SELECTOR, '#report-specific-cases')


def case_buttons(d, label):
    out = []
    for b in case_root(d).find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == label and b.is_displayed():
                out.append(b)
        except Exception:
            pass
    return out


def open_case_dialog(d, label):
    btns = case_buttons(d, label)
    if not btns:
        raise AssertionError('用例按钮缺失 %s' % label)
    L.js_click(d, btns[0])
    WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
    time.sleep(1.5)
    return L.dialogs(d)[-1]['el']


def main():
    d = L.driver()
    try:
        L.login(d)

        # ---------- 分享：有效期/自定义/指定人 ----------
        def share_full():
            open_report(d, 481)
            L.click_text(d, '分享')
            dl = L.wait_dialog(d, '分享报告')
            time.sleep(1)
            combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            # 有效期
            L.js_click(d, combos[1]); time.sleep(0.8)
            OUT['share_expiry_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
            for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (i.text or '').strip() == '自定义':
                    L.js_click(d, i); break
            time.sleep(1)
            dl = L.wait_dialog(d, '分享报告')
            OUT['share_custom_dt_n'] = len(dl.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']"))
            OUT['share_custom_text'] = dl.text[:400]
            L.shot(d, '32_share_custom_light')
            # 指定人
            combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            L.js_click(d, combos[0]); time.sleep(0.8)
            for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (i.text or '').strip() == '指定人':
                    L.js_click(d, i); break
            time.sleep(1)
            dl = L.wait_dialog(d, '分享报告')
            OUT['share_specific_placeholders'] = [i.get_attribute('placeholder') for i in dl.find_elements(By.TAG_NAME, 'input')]
            OUT['share_specific_text'] = dl.text[:400]
            L.shot(d, '32b_share_specific_light')
            # 切「导出后分享」
            grp = dl.find_element(By.CSS_SELECTOR, "[role='group'][aria-label='分享方式']")
            for b in grp.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '导出后分享':
                    L.js_click(d, b); break
            time.sleep(0.8)
            dl = L.wait_dialog(d, '分享报告')
            OUT['share_export_method_text'] = dl.text[:400]
            L.shot(d, '32c_share_export_method_light')
            # 生成分享链接按钮计数（tab + 实际操作）
            OUT['share_generate_btns_export_mode'] = len([b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成分享链接'])
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
            # 取消按钮
            L.click_text(d, '分享')
            dl = L.wait_dialog(d, '分享报告')
            time.sleep(0.8)
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '取消':
                    L.js_click(d, b); break
            time.sleep(0.8)
            OUT['share_cancel_closed'] = len(L.dialogs(d)) == 0
        section('share_full', share_full)

        # ---------- 音频播放 Modal（用例详情内） ----------
        def audio():
            open_report(d, 481)
            dl = open_case_dialog(d, '详情')
            plays = [b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']")]
            OUT['case_detail_play_btns'] = len(plays)
            if not plays:
                raise AssertionError('用例详情内无播放按钮')
            L.reset_fetch_log(d)
            L.js_click(d, plays[0])
            time.sleep(2)
            OUT['audio_dialog_text'] = dlg_texts(d)
            L.shot(d, '33_audio_player_light')
            audio_els = d.find_elements(By.TAG_NAME, 'audio')
            OUT['audio_tags'] = len(audio_els)
            OUT['audio_src'] = [a.get_attribute('src') for a in audio_els]
            OUT['audio_reqs'] = req_log(d, '/audios/play')
            # 播放
            cur = L.dialogs(d)[-1]['el']
            for b in cur.find_elements(By.TAG_NAME, 'button'):
                if (b.get_attribute('aria-label') or '') in ('播放', 'play') or (b.text or '').strip() == '播放':
                    L.js_click(d, b); break
            time.sleep(3)
            L.shot(d, '33b_audio_playing_light')
            OUT['audio_after_play'] = dlg_texts(d)
            OUT['audio_play_reqs'] = req_log(d, '/audios/play')
            L.close_dialog(d, 'esc'); time.sleep(1)
            # 深色
            L.apply_theme(d, 'dark')
            open_report(d, 481)
            dl = open_case_dialog(d, '详情')
            plays = [b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']")]
            if plays:
                L.js_click(d, plays[0]); time.sleep(2)
                L.shot(d, '34_audio_player_dark')
            L.apply_theme(d, 'light')
        section('audio', audio)

        # ---------- 中心确认弹窗：重命名预填 / 发布取消 / 删除取消 ----------
        def confirms():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(rows(x)) > 0)
            time.sleep(2)
            idx = find_row_by_id(d, 481)
            OUT['confirm_report_row'] = rtext(rows(d)[idx])[:120] if idx is not None else None
            if idx is None:
                raise AssertionError('列表未找到 #481')
            # 重命名（仅打开/读取/取消，不保存真实报告）
            row_action(d, idx, '编辑')
            dl = L.wait_dialog(d, '编辑报告')
            time.sleep(0.8)
            OUT['rename_prefill'] = dl.find_element(By.ID, 'rename-name').get_attribute('value')
            OUT['rename_desc_prefill'] = dl.find_element(By.ID, 'rename-desc').get_attribute('value')
            L.shot(d, '35_rename_light')
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '取消':
                    L.js_click(d, b); break
            time.sleep(1)
            # 发布确认（取消）
            d.get(L.BASE + '/report-center')
            time.sleep(3)
            idx = find_row_by_id(d, 481)
            row_action(d, idx, '发布')
            dl = L.wait_dialog(d, '发布报告')
            time.sleep(0.8)
            OUT['publish_text'] = dl.text[:300]
            L.shot(d, '36_publish_confirm_light')
            L.close_dialog(d, 'esc'); time.sleep(1)
            r = L.api(d, '/reports/481')
            OUT['publish_cancel_status'] = ((r['json'] or {}).get('data') or {}).get('status')
            # 删除确认（取消）
            d.get(L.BASE + '/report-center')
            time.sleep(3)
            idx = find_row_by_id(d, 481)
            row_action(d, idx, '删除')
            dl = L.wait_dialog(d, '删除报告')
            time.sleep(0.8)
            OUT['delete_text'] = dl.text[:300]
            L.shot(d, '37_delete_confirm_light')
            L.close_dialog(d, 'esc'); time.sleep(1)
            r = L.api(d, '/reports/481')
            OUT['delete_cancel'] = {'status': r['status'], 'deleted': ((r['json'] or {}).get('data') or {}).get('deleted')}
        section('confirms', confirms)

        # ---------- 统计报表页 ----------
        def stats():
            L.reset_fetch_log(d)
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(4)
            OUT['stats_url'] = d.current_url
            OUT['stats_text'] = L.body(d)[:500]
            OUT['stats_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in req_log(d, '/reports')][-6:]
            L.shot(d, '38_statistics_light')
            tabs = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.is_displayed()]
            OUT['stats_tabs'] = tabs
            # 切到 报表生成
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '报表生成':
                    L.js_click(d, t); time.sleep(2); break
            L.shot(d, '39_statistics_report_tab_light')
            OUT['stats_report_tab_text'] = L.body(d)[:800]
            # 报表类型下拉
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['stats_combos'] = len(combos)
            if combos:
                L.js_click(d, combos[0]); time.sleep(0.8)
                OUT['stats_type_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(0.5)
            L.reset_fetch_log(d)
            # 名称 + 生成报表
            named = False
            for i in d.find_elements(By.TAG_NAME, 'input'):
                ph = i.get_attribute('placeholder') or ''
                if '报表名称' in ph or product_hint(i):
                    i.clear(); i.send_keys('接线测试_统计报表_%s' % STAMP)
                    named = True
                    break
            OUT['stats_name_filled'] = named
            btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报表' and b.is_displayed()]
            OUT['stats_generate_btns'] = len(btns)
            if btns:
                L.js_click(d, btns[-1])
                time.sleep(3)
            OUT['stats_after_generate'] = L.body(d)[:300]
            OUT['stats_generate_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status', 'reqBody')} for e in req_log(d)]
            dl_dir = os.path.join(L.ART, 'downloads')
            OUT['stats_downloads'] = sorted(os.listdir(dl_dir)) if os.path.isdir(dl_dir) else []
            L.shot(d, '40_statistics_after_generate_light')
            # 深色
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(5)
            L.shot(d, '41_statistics_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '报表生成':
                    L.js_click(d, t); time.sleep(2); break
            L.shot(d, '42_statistics_report_tab_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.endswith('.png')])
        print('DONE')
    finally:
        save()
        d.quit()


def product_hint(el):
    try:
        return '报表名称' in (el.get_attribute('outerHTML') or '')
    except Exception:
        return False


if __name__ == '__main__':
    main()
