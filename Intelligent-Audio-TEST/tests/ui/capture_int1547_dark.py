# -*- coding: utf-8 -*-
"""INT-1547 复走深色截图（修复构建旁路容器）：编辑回填 / 导出历史 / 音频播放 / 统计页。"""
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

REPORT = int(os.environ.get('REPORT_ID', '481'))


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        WebDriverWait(d, 90).until(lambda x: len(rows(x)) > 0)
        L.apply_theme(d, 'dark')
        d.get(L.BASE + '/report-center')
        WebDriverWait(d, 90).until(lambda x: len(rows(x)) > 0)
        time.sleep(1.5)
        r = rows(d)[0]
        L.js_click(d, r.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作') or contains(@aria-label,'更多操作')]"))
        time.sleep(0.8)
        for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
            if m.is_displayed() and (m.text or '').strip() == '编辑':
                L.js_click(d, m)
                break
        L.wait_dialog(d, '编辑报告')
        time.sleep(1)
        L.shot(d, 'p2-1_rename_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys('')
        from selenium.webdriver.common.keys import Keys
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        # 导出历史
        L.js_click(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
        time.sleep(0.8)
        for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
            if m.is_displayed() and '导出' in (m.text or ''):
                L.js_click(d, m)
                break
        L.wait_dialog(d, '导出报告')
        time.sleep(1.2)
        for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if t.text.strip() == '导出历史':
                L.js_click(d, t)
                time.sleep(1)
                break
        L.shot(d, 'p2-4_export_history_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        # 音频播放
        d.get(L.BASE + '/report/%s' % REPORT)
        WebDriverWait(d, 90).until(lambda x: 'report-specific-cases' in (x.page_source or ''))
        time.sleep(3)
        root = d.find_element(By.CSS_SELECTOR, '#report-specific-cases')
        d.execute_script("arguments[0].scrollIntoView({block:'start'})", root)
        for h in root.find_elements(By.CSS_SELECTOR, "button[aria-expanded='false'], [data-state='closed']"):
            try:
                L.js_click(d, h)
                time.sleep(0.5)
            except Exception:
                pass
        btns = [b for b in root.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() in ('详情', '展开详情') and b.is_displayed()]
        L.js_click(d, btns[0])
        time.sleep(2.5)
        plays = []
        for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
            plays += [b for b in dl.find_elements(By.XPATH, ".//button[normalize-space(.)='播放']") if b.is_displayed()]
        L.js_click(d, plays[0])
        time.sleep(2.5)
        L.shot(d, 'p2-2_audio_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        # 统计页
        d.get(L.BASE + '/report-statistics')
        WebDriverWait(d, 90).until(lambda x: '报告数量' in (x.page_source or ''))
        time.sleep(4)
        L.shot(d, 'p2-3_stats_dark')
        for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if (t.text or '').strip() == '报表生成':
                L.js_click(d, t)
                time.sleep(1.2)
                break
        L.shot(d, 'p2-5_stats_report_dark')
    finally:
        try:
            d.quit()
        except Exception:
            pass
    print('DONE')


if __name__ == '__main__':
    main()
