# -*- coding: utf-8 -*-
"""INT-1592 任务域 B 段：/tasks/published（版本链/双快照/执行确认）+ /tasks/:id（人工复核/历史/批量浮条/AI 复核）。

被测环境：docker React http://127.0.0.1:15173 + docker 真实库栈 http://127.0.0.1:15000。
复核对象：本卡自建挑选合并容器（接线测试_INT1592_容器B，id 见 state.json），
        人工复核写入后 GET /tasks/results/{id}/review-history 回读；容器收尾统一软删 + purge。
已发布侧：GET /published-tasks 现有 1 条（源任务 417）；只读验证快照与执行确认，不做破坏性写。

用法：python tests/ui/verify_int1592_published_review.py [--only published|review]
输出：tests/ui/artifacts/int1592/*.png + evidence_published_review.json
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1592_cherry_pick import (  # noqa: E402
    ART, BASE, STATE_PATH, api, body_text, click_exact, click_text, confirm_alert,
    data_of, driver, js_click, log, login, set_dark, shot, toast_texts, wait_body,
)


def perf_index(drv):
    """排空 performance 缓冲（Selenium get_log 读后即清），返回 0 作为占位。"""
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass
    return 0


def requests_since(drv, idx):
    """读取自上次排空以来的网络请求（idx 仅为兼容签名）。"""
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for entry in entries:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:  # noqa: BLE001
            continue
        p = msg.get('message') or {}
        if p.get('method') != 'Network.requestWillBeSent':
            continue
        req = (p.get('params') or {}).get('request') or {}
        url = req.get('url') or ''
        if '/api/' in url:
            out.append({'method': req.get('method'), 'url': url, 'postData': req.get('postData')})
    return out


# ---------------------------------------------------------------- published
def phase_published(drv, ev):
    drv.get(BASE + '/tasks/published')
    WebDriverWait(drv, 120).until(lambda d: '已发布' in body_text(d) and (
        '暂无已发布任务' in body_text(d) or d.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']")))
    time.sleep(2)
    shot(drv, '20_published_list_light.png')
    set_dark(drv, True)
    shot(drv, '21_published_list_dark.png')
    set_dark(drv, False)

    expand = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']") if b.is_displayed()]
    if not expand:
        ev['published_error'] = '无已发布任务行'
        return
    js_click(drv, expand[0])
    # 详情 GET /published-tasks/{id}
    WebDriverWait(drv, 180).until(lambda d: '任务详情（发布时冻结' in body_text(d) or '历史版本（发布时未冻结' in body_text(d)
                                  or '冻结报告（发布时快照' in body_text(d))
    time.sleep(2)
    txt = body_text(drv)
    ev['published_sections'] = {
        '版本历史': '版本历史' in txt,
        'Benchmark': 'Benchmark 标记' in txt,
        '任务详情': '任务详情（发布时冻结' in txt,
        '冻结报告': '冻结报告（发布时快照' in txt,
        '执行记录': '执行记录' in txt,
        'has_snapshot_btn': '查看冻结任务详情' in txt,
        'has_report_btn': '查看冻结报告' in txt,
        'legacy_warning': '历史版本（发布时未冻结' in txt,
    }
    shot(drv, '22_published_expanded_light.png')
    set_dark(drv, True)
    shot(drv, '23_published_expanded_dark.png')
    set_dark(drv, False)

    # 冻结任务详情
    if '查看冻结任务详情' in txt:
        click_text(drv, '查看冻结任务详情')
        WebDriverWait(drv, 30).until(lambda d: '任务详情（发布时冻结 · 不可变）' in body_text(d))
        time.sleep(1.5)
        dlg = drv.find_element(By.XPATH, "//*[@role='dialog'][.//*[contains(normalize-space(.), '发布时冻结 · 不可变')]]")
        ev['snapshot_dialog'] = {
            'title': '任务详情（发布时冻结 · 不可变）' in dlg.text,
            'sections': {
                '任务信息': '任务信息' in dlg.text,
                '关联资源': '关联资源' in dlg.text,
                '用例节': '用例（' in dlg.text,
            },
            'empty_cases': '冻结体无用例数据' in dlg.text,
            'head': dlg.text[:600],
        }
        shot(drv, '24_task_snapshot_dialog_light.png')
        set_dark(drv, True)
        shot(drv, '25_task_snapshot_dialog_dark.png')
        set_dark(drv, False)
        # 展开首个用例（Collapsible）
        cases = [b for b in dlg.find_elements(By.XPATH, ".//button[contains(@class,'w-full')]") if b.is_displayed()]
        if cases:
            js_click(drv, cases[0])
            time.sleep(1)
            ev['snapshot_case_expanded'] = '算法参数' in dlg.text or '参考参数' in dlg.text or 'config' in dlg.text
            shot(drv, '26_task_snapshot_case_expanded_light.png')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)

    # 冻结报告
    if '查看冻结报告' in body_text(drv):
        click_text(drv, '查看冻结报告')
        WebDriverWait(drv, 30).until(lambda d: '冻结报告（发布时快照 · 不可变）' in body_text(d))
        time.sleep(1.5)
        dlg = drv.find_element(By.XPATH, "//*[@role='dialog'][.//*[contains(normalize-space(.), '发布时快照 · 不可变')]]")
        ev['report_snapshot_dialog'] = {
            'title': '冻结报告（发布时快照 · 不可变）' in dlg.text,
            'empty': '缺少可渲染的冻结报告数据' in dlg.text,
            'has_source_link': '查看源报告' in dlg.text,
            'stats': [t for t in dlg.text.split('\n') if '用例总数' in t or '通过率' in t][:4],
            'head': dlg.text[:500],
        }
        shot(drv, '27_report_snapshot_dialog_light.png')
        set_dark(drv, True)
        shot(drv, '28_report_snapshot_dialog_dark.png')
        set_dark(drv, False)
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)

    # 执行确认：打开后取消，确认无 POST /execute
    idx = perf_index(drv)
    btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='执行']") if b.is_displayed()]
    if btns:
        js_click(drv, btns[0])
        time.sleep(1)
        dlg = WebDriverWait(drv, 20).until(
            lambda d: [x for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()])
        ev['execute_confirm'] = {
            'title': '执行此版本' in dlg[0].text,
            'text': dlg[0].text[:400],
        }
        shot(drv, '29_execute_confirm_light.png')
        # 取消
        cancel = [b for b in dlg[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']") if b.is_displayed()]
        if cancel:
            js_click(drv, cancel[0])
        time.sleep(1.5)
        ev['execute_confirm_cancelled'] = not drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")
        reqs = requests_since(drv, idx)
        ev['execute_confirm_writes'] = [r for r in reqs if '/execute' in r['url'] and r['method'] != 'OPTIONS']


# ---------------------------------------------------------------- review
def case_result_ids(task_id):
    detail = data_of(api('GET', f'/api/v1/tasks/{task_id}')) or {}
    out = []
    for c in (detail.get('cases') or [])[:2]:
        d = data_of(api('GET', f"/api/v1/tasks/{task_id}/cases/{c['case_id']}/results")) or {}
        for r in d.get('results') or []:
            out.append({'case_id': c['case_id'], 'case_name': c['name'], 'result_id': r.get('result_id') or r.get('id')})
            break
    return out


def phase_review(drv, ev, task_id):
    res = case_result_ids(task_id)
    ev['review_targets'] = res
    if not res:
        raise AssertionError('容器任务无执行结果，无法复核')

    drv.get(f'{BASE}/tasks/{task_id}')
    WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
    time.sleep(3)
    txt = body_text(drv)
    ev['detail_state'] = {
        'has_review_count': '已复核' in txt,
        'has_history_link': '查看复核历史' in txt,
        'manual_btns': len([b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='人工复核']") if b.is_displayed()]),
        'ai_btns': len([b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='AI 复核']") if b.is_displayed()]),
        'quick_btns': len([b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='快速复核']") if b.is_displayed()]),
    }
    shot(drv, '30_task_detail_light.png')
    set_dark(drv, True)
    shot(drv, '31_task_detail_dark.png')
    set_dark(drv, False)

    idx = perf_index(drv)
    manual = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='人工复核']") if b.is_displayed()]
    if not manual:
        ev['manual_review'] = {'error': '未见「人工复核」按钮'}
        return
    js_click(drv, manual[0])
    dlg = WebDriverWait(drv, 30).until(lambda d: [x for x in d.find_elements(By.CSS_SELECTOR, "[data-slot='manual-review-dialog']") if x.is_displayed()])
    d = dlg[0]
    ev['manual_review'] = {
        'title': d.text.split('\n')[0],
        'summary_line': [t for t in d.text.split('\n') if '已完成' in t or '执行失败' in t][:3],
    }
    shot(drv, '32_manual_review_dialog_light.png')
    set_dark(drv, True)
    shot(drv, '33_manual_review_dialog_dark.png')
    set_dark(drv, False)

    # 执行状态改判 → 执行失败
    trig = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='用例执行状态']") if b.is_displayed()][0]
    js_click(drv, trig)
    time.sleep(0.8)
    opts = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    ev['exec_options'] = [o.text for o in opts]
    target = [o for o in opts if o.text.strip() == '执行失败']
    if target:
        js_click(drv, target[0])
    time.sleep(0.6)
    comment = d.find_element(By.CSS_SELECTOR, "[data-slot='review-comment']")
    comment.send_keys('接线测试_INT1592 人工复核备注')
    time.sleep(0.5)
    submit = [b for b in d.find_elements(By.XPATH, ".//button[normalize-space(.)='提交复核']") if b.is_displayed()][0]
    ev['submit_enabled'] = submit.is_enabled()
    js_click(drv, submit)
    time.sleep(4)
    ev['manual_toasts'] = toast_texts(drv)
    ev['manual_requests'] = [r for r in requests_since(drv, idx) if 'results/review' in r['url']]
    ev['review_history_api'] = data_of(api('GET', f'/api/v1/tasks/results/{task_id}/review-history'))
    ev['review_count_api'] = data_of(api('GET', f'/api/v1/tasks/results/{task_id}/review-count'))
    time.sleep(2)

    # 查看复核历史抽屉
    link = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '查看复核历史')]") if b.is_displayed()]
    if link:
        js_click(drv, link[0])
        time.sleep(2.5)
        shot(drv, '34_review_history_drawer_light.png')
        set_dark(drv, True)
        shot(drv, '35_review_history_drawer_dark.png')
        set_dark(drv, False)
        sheet = drv.find_element(By.XPATH, "//*[contains(@data-slot,'sheet-content')]") if drv.find_elements(By.CSS_SELECTOR, "[data-slot*='sheet-content']") else None
        text = sheet.text if sheet else body_text(drv)
        ev['history_drawer'] = {
            'title_has_task': '复核历史' in text,
            'count': [t for t in text.split('\n') if t.startswith('共 ')][:1],
            'has_operator': '操作人' in text,
            'has_arrow': '→' in text,
            'head': text[:800],
        }
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
    # 空态/加载态：另一个无复核任务（源任务 419 已有历史则跳过）
    empty = data_of(api('GET', '/api/v1/tasks/results/419/review-history')) or {}
    ev['other_task_history_items'] = len(empty.get('items') or [])

    # 批量复核浮条
    boxes = [cb for cb in drv.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row'] [role='checkbox']") if cb.is_displayed()]
    ev['case_rows'] = len(boxes)
    for cb in boxes[:2]:
        js_click(drv, cb)
        time.sleep(0.3)
    time.sleep(1)
    bar = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='批量复核']") if b.is_displayed()]
    ev['batch_bar'] = bool(bar)
    if bar:
        shot(drv, '36_batch_bar_light.png')
        js_click(drv, bar[0])
        time.sleep(2.5)
        batch = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='manual-review-dialog']") if x.is_displayed()]
        ev['batch_dialog'] = {'shown': bool(batch), 'title': batch[0].text.split('\n')[0] if batch else None}
        shot(drv, '37_batch_review_dialog_light.png')
        if batch:
            cancel = [b for b in batch[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']") if b.is_displayed()]
            if cancel:
                js_click(drv, cancel[0])
        time.sleep(1)

    # 快速复核（真实 POST /tasks/results/ai-review）
    idx = perf_index(drv)
    quick = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='快速复核']") if b.is_displayed()]
    if quick:
        js_click(drv, quick[0])
        time.sleep(3)
        shot(drv, '38_quick_ai_review_light.png')
        set_dark(drv, True)
        shot(drv, '39_quick_ai_review_dark.png')
        set_dark(drv, False)
        qtext = ''
        for _ in range(45):
            els = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']") if x.is_displayed()]
            if els:
                qtext = els[0].text
            time.sleep(2)
            if qtext and ('失败' in qtext or '错误' in qtext or '结论' in qtext or '完成' in qtext):
                break
        ev['quick_review_dialog'] = {'text': qtext[:900]}
        ev['quick_review_requests'] = [r for r in requests_since(drv, idx) if 'ai-review' in r['url']]
        shot(drv, '40_quick_ai_review_result_light.png')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)

    # 灵犀Agent AI 复核会话
    ai = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='AI 复核']") if b.is_displayed()]
    if ai:
        js_click(drv, ai[0])
        time.sleep(4)
        els = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='ai-review-session-dialog']") if x.is_displayed()]
        ev['ai_session_dialog'] = {'shown': bool(els), 'head': (els[0].text[:500] if els else '')}
        shot(drv, '41_ai_review_session_light.png')
        if els:
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)


def main():
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else 'all'
    ev = {'base': BASE, 'only': only}
    drv = driver()
    try:
        login(drv, ev)
        if only in ('all', 'published'):
            phase_published(drv, ev)
        if only in ('all', 'review'):
            with open(STATE_PATH, encoding='utf-8') as f:
                cid = json.load(f)['container_id']
            ev['container_id'] = cid
            phase_review(drv, ev, cid)
    finally:
        name = f'evidence_published_review_{only}.json'
        with open(os.path.join(ART, name), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
