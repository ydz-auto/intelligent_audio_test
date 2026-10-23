# -*- coding: utf-8 -*-
"""INT-1482 批次B：报告详情模态窗（分享 / 用例结果详情 / 音频播放 / 日志文件选择 / 日志下载进度 / 人工复核 / 复核历史）+ 浅深截图。"""
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
REPORT = int(os.environ.get('REPORT_ID', '481'))


def save():
    try:
        with open(os.path.join(L.ART, 'batchB_result.json'), 'w', encoding='utf-8') as f:
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
    return [x['text'][:500] for x in L.dialogs(d)]


def req_log(d, contains=None, since=0):
    out = []
    for e in L.fetch_log(d, since):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody', 'error')})
    return out


def open_report(d, rid):
    L.reset_fetch_log(d)
    d.get(L.BASE + '/report/%s' % rid)
    WebDriverWait(d, 60).until(lambda x: 'report-specific-cases' in (x.page_source or '') or len(L.find_by_text(x, '详细日志', 'h3')) > 0)
    time.sleep(3)


def case_buttons(d, label):
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    btns = []
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == label and b.is_displayed():
                btns.append(b)
        except Exception:
            pass
    return btns


def ensure_cases(d):
    d.execute_script("document.querySelector('#report-specific-cases').scrollIntoView({block:'start'})")
    time.sleep(1.5)
    if case_buttons(d, '详情'):
        return
    # 顺序展开任何折叠分组
    root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
    for h in root.find_elements(By.CSS_SELECTOR, "button[aria-expanded='false'], [data-state='closed']"):
        try:
            L.js_click(d, h)
            time.sleep(0.7)
        except Exception:
            pass
    time.sleep(1)


def click_case_btn(d, label, idx=0):
    ensure_cases(d)
    btns = case_buttons(d, label)
    if not btns:
        raise AssertionError('用例行按钮缺失: %s' % label)
    L.js_click(d, btns[idx])
    time.sleep(1.5)


def main():
    d = L.driver()
    try:
        L.login(d)
        open_report(d, REPORT)
        OUT['report_url'] = d.current_url
        OUT['detail_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in req_log(d, '/reports/%s' % REPORT)]
        OUT['case_search_req'] = [{k: e.get(k) for k in ('method', 'url', 'status', 'reqBody')} for e in req_log(d, '/cases/search')]
        ensure_cases(d)
        OUT['case_detail_buttons'] = len(case_buttons(d, '详情'))
        L.shot(d, '20_report_detail_light')

        # ---------- 分享弹窗 ----------
        def share():
            L.reset_fetch_log(d)
            L.click_text(d, '分享')
            dl = L.wait_dialog(d, '分享报告')
            time.sleep(1.5)
            OUT['share_text'] = dl.text[:500]
            L.shot(d, '21_share_light')
            OUT['share_reqs'] = req_log(d, '/share')
            # 分享方式两个按钮
            grp = dl.find_element(By.CSS_SELECTOR, "[role='group'][aria-label='分享方式']")
            OUT['share_method_btns'] = [b.text for b in grp.find_elements(By.TAG_NAME, 'button')]
            # 访问权限下拉选项
            combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            OUT['share_combo_n'] = len(combos)
            if combos:
                L.js_click(d, combos[0]); time.sleep(0.7)
                OUT['share_access_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(0.4)
                L.js_click(d, combos[1]); time.sleep(0.7)
                OUT['share_expiry_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
                # 选「自定义」→ 日期输入
                for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (i.text or '').strip() == '自定义':
                        L.js_click(d, i); break
                time.sleep(0.8)
                dl = L.wait_dialog(d, '分享报告')
                dts = dl.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']")
                OUT['share_custom_dt'] = len(dts)
                OUT['share_after_custom'] = dl.text[:400]
                L.shot(d, '21b_share_custom_light')
                # 选「指定人」→ 收件人输入
                combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
                L.js_click(d, combos[0]); time.sleep(0.7)
                for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (i.text or '').strip() == '指定人':
                        L.js_click(d, i); break
                time.sleep(0.8)
                dl = L.wait_dialog(d, '分享报告')
                OUT['share_recipients_placeholder'] = [i.get_attribute('placeholder') for i in dl.find_elements(By.TAG_NAME, 'input')]
            # 「生成分享链接」按钮计数（tab + 实际生成）
            OUT['share_generate_btns'] = len([b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成分享链接'])
            # 取消（真实分享只验取消路径）
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '取消':
                    L.js_click(d, b); break
            time.sleep(0.8)
            OUT['share_closed'] = len(L.dialogs(d)) == 0
            # 重开是否残留
            L.click_text(d, '分享')
            dl = L.wait_dialog(d, '分享报告')
            time.sleep(1)
            OUT['share_reopen_text'] = dl.text[:300]
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('share', share)

        # ---------- 用例结果详情 ----------
        def case_detail():
            click_case_btn(d, '详情')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(2)
            OUT['case_detail_text'] = dlg_texts(d)
            L.shot(d, '22_case_detail_light')
            dl = L.dialogs(d)[-1]['el']
            OUT['case_detail_len'] = len(dl.text)
            OUT['case_detail_has_rounds'] = ('第 1 轮' in dl.text) or ('轮次' in dl.text)
            OUT['case_detail_has_dimension'] = ('维度' in dl.text) or ('评估' in dl.text)
            OUT['case_detail_audio_items'] = len(dl.find_elements(By.XPATH, ".//*[normalize-space(.)='播放']"))
            # 打开音频播放（若有播放按钮，在详情内）
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('case_detail', case_detail)

        # ---------- 音频播放 Modal（结果音频区） ----------
        def audio():
            ensure_cases(d)
            # 展开首条用例（展开详情按钮）
            for b in case_buttons(d, '展开详情')[:1] or []:
                L.js_click(d, b)
                time.sleep(2)
            root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
            plays = [b for b in root.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']") if b.is_displayed()]
            OUT['audio_play_btns'] = len(plays)
            if not plays:
                raise AssertionError('无可播放音频条目（无 url）')
            L.reset_fetch_log(d)
            L.js_click(d, plays[0])
            time.sleep(2)
            OUT['audio_dialog_text'] = dlg_texts(d)
            L.shot(d, '23_audio_player_light')
            dl = L.dialogs(d)[-1]['el']
            audio_els = dl.find_elements(By.TAG_NAME, 'audio')
            OUT['audio_tag'] = len(audio_els)
            if audio_els:
                OUT['audio_src'] = audio_els[0].get_attribute('src')
            OUT['audio_reqs'] = req_log(d, '/audios/play')
            # 播放 → 进度推进
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if '播放' in (b.text or '') and '暂停' not in (b.text or ''):
                    L.js_click(d, b)
                    break
            time.sleep(2.5)
            L.shot(d, '23b_audio_playing_light')
            OUT['audio_after_play'] = dlg_texts(d)
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('audio', audio)

        # ---------- 日志文件选择 ----------
        def log_select():
            click_case_btn(d, '下载日志')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(2)
            OUT['log_select_text'] = dlg_texts(d)
            L.shot(d, '24_log_select_light')
            OUT['log_select_reqs'] = req_log(d, '/logs')
            dl = L.dialogs(d)[-1]['el']
            OUT['log_file_rows'] = len(dl.find_elements(By.CSS_SELECTOR, "[role='checkbox']"))
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('log_select', log_select)

        # ---------- 人工复核 ----------
        def review():
            click_case_btn(d, '人工复核')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(2)
            OUT['review_text'] = dlg_texts(d)
            L.shot(d, '25_manual_review_light')
            dl = L.dialogs(d)[-1]['el']
            OUT['review_combos'] = len(dl.find_elements(By.CSS_SELECTOR, "[role='combobox']"))
            OUT['review_inputs'] = [(i.get_attribute('placeholder'), i.get_attribute('type')) for i in dl.find_elements(By.TAG_NAME, 'input')]
            OUT['review_textareas'] = len(dl.find_elements(By.TAG_NAME, 'textarea'))
            OUT['review_buttons'] = [b.text for b in dl.find_elements(By.TAG_NAME, 'button')]
            # 校验：不填直接提交
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() in ('提交复核', '提交'):
                    OUT['review_submit_disabled_empty'] = b.get_attribute('disabled')
                    break
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('review', review)

        # ---------- 复核历史抽屉 ----------
        def history():
            click_case_btn(d, '人工复核')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(1.5)
            dl = L.dialogs(d)[-1]['el']
            opened = False
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if '查看复核历史' in (b.text or ''):
                    L.js_click(d, b)
                    opened = True
                    break
            if not opened:
                L.close_dialog(d, 'esc')
                time.sleep(0.8)
                # 卡片徽标入口
                ensure_cases(d)
                badges = [b for b in d.find_elements(By.XPATH, "//button[@aria-label='查看复核明细']") if b.is_displayed()]
                OUT['history_badges'] = len(badges)
                if badges:
                    L.js_click(d, badges[0])
                else:
                    raise AssertionError('无复核历史入口（无复核记录徽标）')
            time.sleep(2.5)
            sheets = d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
            OUT['history_dialog_text'] = [s.text[:500] for s in sheets]
            L.shot(d, '26_review_history_light')
            # 两个 Tab
            tabs = d.find_elements(By.CSS_SELECTOR, "[role='tab']")
            OUT['history_tabs'] = [t.text for t in tabs]
            for t in tabs:
                if 'AI' in (t.text or ''):
                    L.js_click(d, t); time.sleep(1.5)
                    L.shot(d, '26b_review_history_ai_light')
                    OUT['history_ai_text'] = [s.text[:400] for s in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")]
                    break
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('history', history)

        # ---------- 深色 ----------
        def dark():
            L.apply_theme(d, 'dark')
            open_report(d, REPORT)
            ensure_cases(d)
            L.shot(d, '27_report_detail_dark')
            L.click_text(d, '分享')
            L.wait_dialog(d, '分享报告'); time.sleep(1.5)
            L.shot(d, '28_share_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            click_case_btn(d, '详情')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(1.5)
            L.shot(d, '29_case_detail_dark')
            L.close_dialog(d, 'esc'); time.sleep(1)
            click_case_btn(d, '下载日志')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(1.2)
            L.shot(d, '30_log_select_dark')
            L.close_dialog(d, 'esc'); time.sleep(1)
            click_case_btn(d, '人工复核')
            WebDriverWait(d, 20).until(lambda x: len(L.dialogs(x)) > 0)
            time.sleep(1.5)
            L.shot(d, '31_manual_review_dark')
            L.close_dialog(d, 'esc'); time.sleep(1)
            L.apply_theme(d, 'light')
        section('dark', dark)

        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.endswith('.png')])
        print('DONE')
    finally:
        save()
        d.quit()


if __name__ == '__main__':
    main()
