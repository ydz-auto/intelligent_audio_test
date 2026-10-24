# -*- coding: utf-8 -*-
"""INT-1592 返工（UX 审计打回）：补冻结报告窗口证据 + 三个缺图态 + 缺陷复核。

被审环境：docker React http://127.0.0.1:15173 + docker 真实库栈 http://127.0.0.1:15000
        （database=intelligent_audio_test）。

覆盖（对应打回清单问题 1/2/3）：
- 冻结报告弹窗：浅/深截图 + 逐行标签文本（复现 tags 渲染成 [object Object]，问题 1）
- 执行确认：打开 → 取消，采集 Network（断言无 POST /execute），渲染 Network 面板图
- 批量复核浮条：勾选 2 行出浮条 → 批量复核弹窗（浅色截图）
- 快速 AI 复核：真实点「发起快速复核」→ 采集 POST /tasks/results/ai-review 请求/响应 + 失败态截图（浅/深）
- 复核历史抽屉：长用例名溢出裁切复现（问题 3，并入 P3 卡）

数据：本 run 用挑选合并自建容器「接线测试_INT1592_容器C」承载复核类窗口（不写真实任务）；
      run 末软删 + purge 容器、清空购物车、按 task_id 删本 run 产生的 ai_reviews / test_result_reviews。
      已发布任务只读。

输出：tests/ui/artifacts/int1592/rework_*.png + evidence_rework.json
用法：python tests/ui/verify_int1592_rework.py
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1592_cherry_pick import (  # noqa: E402
    ART, BASE, TOKEN, add_to_cart, api, body_text, candidates, cart_state, click_text,
    data_of, driver, js_click, log, login, set_dark, shot, toast_texts,
)

CONTAINER_NAME = '接线测试_INT1592_容器C'
PG = 'intelligent-audio-test-postgres-1'


# ------------------------------------------------------------- network
def perf_drain(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def perf_requests(drv):
    """返回 [{method,url,status,requestId}]（Network.requestWillBeSent + responseReceived 合并）。"""
    out = {}
    try:
        entries = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return []
    for entry in entries:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:  # noqa: BLE001
            continue
        payload = msg.get('message') or {}
        method = payload.get('method')
        params = payload.get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            if '/api/' not in url:
                continue
            out[params.get('requestId')] = {
                'method': req.get('method'),
                'url': url,
                'postData': req.get('postData'),
                'status': None,
            }
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in out:
                out[rid]['status'] = (params.get('response') or {}).get('status')
    return list(out.values())


def render_network_panel(drv, reqs, title, conclusion, name):
    """把采集到的真实请求渲染成 Network 面板图（浅色，真数据）。"""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 18)
        bold = ImageFont.truetype(r'C:\Windows\Fonts\msyhbd.ttc', 20)
    except Exception:  # noqa: BLE001
        font = bold = ImageFont.load_default()

    lines = []
    for r in reqs:
        url = r['url'].split('127.0.0.1:15000')[-1].split('localhost:15000')[-1]
        url = url.split('?')[0]
        body = ''
        if r.get('postData'):
            body = '  body=' + str(r['postData'])[:120]
        lines.append('%s  %s   %s%s' % (r.get('method'), r.get('status'), url, body))
    if not lines:
        lines = ['（该时段无 /api 请求）']

    W = 1500
    H = 120 + 34 * (len(lines) + 3)
    img = Image.new('RGB', (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 54], fill=(32, 33, 36))
    d.text((18, 14), 'Network（Chrome DevTools Protocol · 真实采集）', fill=(255, 255, 255), font=bold)
    d.text((18, 66), title, fill=(20, 20, 20), font=bold)
    y = 104
    for ln in lines:
        color = (200, 30, 30) if 'execute' in ln or 'ai-review' in ln else (30, 30, 30)
        d.text((18, y), ln, fill=color, font=font)
        y += 34
    y += 12
    d.rectangle([12, y - 4, W - 12, y + 46], fill=(255, 243, 205), outline=(230, 150, 0), width=2)
    d.text((22, y + 10), conclusion, fill=(122, 65, 0), font=bold)
    path = os.path.join(ART, name)
    img.save(path)
    log('network panel -> ' + name)


# ------------------------------------------------------------- phases
def phase_published(drv, ev):
    drv.get(BASE + '/tasks/published')
    WebDriverWait(drv, 180).until(lambda d: '已发布' in body_text(d) and (
        '暂无已发布任务' in body_text(d) or d.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']")))
    time.sleep(2)
    expand = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='展开版本详情']") if b.is_displayed()]
    if not expand:
        ev['published_error'] = '无已发布任务行'
        return
    js_click(drv, expand[0])
    WebDriverWait(drv, 180).until(lambda d: '冻结报告（发布时快照' in body_text(d)
                                  or '历史版本（发布时未冻结' in body_text(d))
    time.sleep(2)
    shot(drv, '62_published_expanded_light.png')
    ev['published_rows'] = len(expand)

    # ---- 冻结报告（浅/深 + 标签文本）
    if '查看冻结报告' in body_text(drv):
        click_text(drv, '查看冻结报告')
        WebDriverWait(drv, 60).until(lambda d: '冻结报告（发布时快照 · 不可变）' in body_text(d))
        time.sleep(2)
        dlg = [x for x in drv.find_elements(By.XPATH,
               "//*[@role='dialog'][.//*[contains(normalize-space(.), '发布时快照 · 不可变')]]")
               if x.is_displayed()][0]
        txt = dlg.text
        shot(drv, '60_report_snapshot_light.png')
        # 抽取前 3 个用例行的标签区文本
        lines = [ln.strip() for ln in txt.split('\n') if ln.strip()]
        tag_lines = [ln for ln in lines if '、' in ln][:3]
        ev['report_snapshot'] = {
            'title_ok': '冻结报告（发布时快照 · 不可变）' in txt,
            'has_source_link': '查看源报告' in txt,
            'stats': [ln for ln in lines if '用例' in ln or '通过率' in ln][:4],
            'object_object_lines': sum(1 for ln in lines if 'object Object' in ln),
            'tag_lines': tag_lines,
            'head': txt[:1200],
        }
        # 深色（同源页内切主题，断言 html.dark）
        set_dark(drv, True)
        ev['dark_class'] = drv.execute_script("return document.documentElement.className")
        shot(drv, '61_report_snapshot_dark.png')
        set_dark(drv, False)
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
    else:
        ev['report_snapshot'] = {'error': '未见「查看冻结报告」按钮'}

    # ---- 执行确认：打开 → 取消 → Network
    perf_drain(drv)
    btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='执行']") if b.is_displayed()]
    if not btns:
        ev['execute_confirm'] = {'error': '未见「执行」按钮'}
        return
    js_click(drv, btns[0])
    time.sleep(1.5)
    dlgs = [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()]
    if not dlgs:
        ev['execute_confirm'] = {'error': '未弹出确认层'}
        return
    ev['execute_confirm'] = {'title': '执行此版本' in dlgs[0].text, 'text': dlgs[0].text[:400]}
    shot(drv, '63_execute_confirm_light.png')
    cancel = [b for b in dlgs[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']") if b.is_displayed()]
    if cancel:
        js_click(drv, cancel[0])
    time.sleep(2)
    ev['execute_confirm_cancelled'] = not [x for x in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()]
    reqs = perf_requests(drv)
    ev['execute_window_requests'] = reqs
    writes = [r for r in reqs if '/execute' in r['url']]
    ev['execute_writes'] = writes
    if not writes:
        render_network_panel(
            drv, reqs,
            '已发布 v2「执行此版本」确认层：打开 → 点「取消」后整个窗口的 /api 请求',
            '结论：确认层打开与取消期间共 %d 个 /api 请求，其中 POST /tasks/{id}/execute 为 0 —— 取消未发出执行请求' % len(reqs),
            '64_execute_cancel_network.png')


def phase_review(drv, ev, cid):
    drv.get(f'{BASE}/tasks/{cid}')
    WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
    time.sleep(3)
    ev['review_detail'] = {
        'manual_btns': len([b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='人工复核']") if b.is_displayed()]),
        'quick_btns': len([b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='快速复核']") if b.is_displayed()]),
    }
    shot(drv, '65_review_task_detail_light.png')

    # ---- 批量复核浮条
    boxes = [cb for cb in drv.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-row'] [role='checkbox']") if cb.is_displayed()]
    ev['case_rows'] = len(boxes)
    for cb in boxes[:2]:
        js_click(drv, cb)
        time.sleep(0.4)
    time.sleep(1.2)
    bar = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='批量复核']") if b.is_displayed()]
    ev['batch_bar'] = bool(bar)
    if bar:
        shot(drv, '66_batch_bar_light.png')
        set_dark(drv, True)
        shot(drv, '67_batch_bar_dark.png')
        set_dark(drv, False)
        js_click(drv, bar[0])
        time.sleep(2.5)
        batch = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='manual-review-dialog']") if x.is_displayed()]
        ev['batch_dialog'] = {'shown': bool(batch), 'title': batch[0].text.split('\n')[0] if batch else None}
        shot(drv, '68_batch_review_dialog_light.png')
        if batch:
            cancels = [b for b in batch[0].find_elements(By.XPATH, ".//button[normalize-space(.)='取消']") if b.is_displayed()]
            if cancels:
                js_click(drv, cancels[0])
        time.sleep(1.5)

    # ---- 快速 AI 复核：真实发起 → 失败态
    perf_drain(drv)
    quick = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='快速复核']") if b.is_displayed()]
    if not quick:
        ev['quick_review'] = {'error': '未见快速复核按钮'}
        return
    js_click(drv, quick[0])
    time.sleep(3)
    dlg = WebDriverWait(drv, 40).until(
        lambda d: [x for x in d.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']") if x.is_displayed()])
    shot(drv, '69_quick_review_before_submit_light.png')
    ev['quick_before_submit'] = {'head': dlg[0].text[:600]}
    submit = [b for b in dlg[0].find_elements(By.XPATH, ".//button[contains(normalize-space(.), '发起快速复核')]")
              if b.is_displayed() and b.is_enabled()]
    if not submit:
        allb = [b.text for b in dlg[0].find_elements(By.TAG_NAME, 'button') if b.is_displayed()]
        ev['quick_review'] = {'error': '发起快速复核按钮不可用', 'buttons': allb}
        return
    js_click(drv, submit[0])
    # 等失败态（LLM 未配置 → 「AI 复核执行失败，请稍后重试」）
    final_text = ''
    for _ in range(60):
        els = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']") if x.is_displayed()]
        if els:
            final_text = els[0].text
        if final_text and ('失败' in final_text or '错误' in final_text):
            break
        time.sleep(2)
    ev['quick_review'] = {
        'final_text': final_text[:900],
        'toasts': toast_texts(drv),
    }
    ev['quick_requests'] = [r for r in perf_requests(drv) if 'ai-review' in r['url']]
    shot(drv, '70_ai_review_failure_light.png')
    set_dark(drv, True)
    shot(drv, '71_ai_review_failure_dark.png')
    set_dark(drv, False)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.5)


def phase_history_overflow(drv, ev, cid):
    """问题 3：复核历史抽屉长用例名溢出（容器恒空 → 用源任务 419 只读取历史）。"""
    drv.get(f'{BASE}/tasks/{cid}')
    WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
    time.sleep(2)
    link = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '查看复核历史')]") if b.is_displayed()]
    ev['history_link_on_container'] = bool(link)
    if not link:
        ev['history_overflow'] = {'note': '容器无复核历史入口（INT-1626 现象），改用源任务 419 只读取证'}
        drv.get(f'{BASE}/tasks/419')
        WebDriverWait(drv, 240).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']"))
        time.sleep(2)
        link = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '查看复核历史')]") if b.is_displayed()]
    if not link:
        ev['history_overflow'] = {'error': '未见复核历史入口'}
        return
    js_click(drv, link[0])
    time.sleep(3)
    shot(drv, '72_review_history_drawer_light.png')
    sheet = [x for x in drv.find_elements(By.CSS_SELECTOR, "[data-slot*='sheet-content']") if x.is_displayed()]
    if sheet:
        s = sheet[0]
        # 抽屉内的用例名 Badge（长名）是否溢出：比较 scrollWidth 与 clientWidth
        badges = s.find_elements(By.XPATH, ".//span | .//div")
        overflow = []
        for b in badges[:80]:
            try:
                info = drv.execute_script(
                    "const e=arguments[0];return {t:(e.textContent||'').trim().slice(0,80),sw:e.scrollWidth,cw:e.clientWidth,"
                    "cls:e.className,tr:getComputedStyle(e).textOverflow,ws:getComputedStyle(e).whiteSpace};", b)
            except Exception:  # noqa: BLE001
                continue
            if info['t'] and len(info['t']) > 30 and info['sw'] > info['cw'] + 2:
                overflow.append(info)
        ev['history_overflow'] = {'candidates': overflow[:5], 'count': len(overflow)}
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1)


# ------------------------------------------------------------- data / cleanup
def create_container(ev):
    items = (candidates(3, 419).get('items') or [])
    ids = [i['result_id'] for i in items[:2]]
    ev['seeded_result_ids'] = ids
    if not ids:
        raise AssertionError('候选接口未返回结果，无法建容器')
    add = add_to_cart(ids)
    ev['cart_add'] = {'success': add.get('success'), 'message': add.get('message')}
    resp = api('POST', '/api/v1/tasks/cherry-picks/cart/checkout',
               {'action': 'merge', 'name': CONTAINER_NAME, 'description': 'INT-1592 返工证据容器'})
    cid = (data_of(resp) or {}).get('task_id')
    ev['checkout'] = {'success': resp.get('success'), 'message': resp.get('message'), 'task_id': cid}
    return cid


def sql(scalar):
    try:
        out = subprocess.run(
            ['docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test',
             '-tAc', scalar], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return 'ERR ' + str(exc)


def cleanup(ev, cid):
    if not cid:
        return
    before = {'ai_reviews': sql('select count(*) from ai_reviews where task_id=%d;' % cid),
              'result_reviews': sql('select count(*) from test_result_reviews where task_id=%d;' % cid),
              'ai_rows': sql('select coalesce(string_agg(id::text,\',\'),\'\') from ai_reviews where task_id=%d;' % cid),
              'review_rows': sql('select coalesce(string_agg(id::text,\',\'),\'\') from test_result_reviews where task_id=%d;' % cid)}
    ev['db_before_cleanup'] = before
    ev['delete_task'] = api('DELETE', f'/api/v1/tasks/{cid}')
    time.sleep(2)
    ev['purge_task'] = api('DELETE', f'/api/v1/tasks/{cid}/purge')
    cleared = api('DELETE', '/api/v1/tasks/cherry-picks/cart/items')
    ev['cart_clear'] = {'success': cleared.get('success'), 'message': cleared.get('message')}
    # 本 run 在容器上产生的复核/AI 复核行按 task_id 删除（只删自建容器归属）
    ev['sql_delete_ai'] = sql('delete from ai_reviews where task_id=%d;' % cid)
    ev['sql_delete_reviews'] = sql('delete from test_result_reviews where task_id=%d;' % cid)
    ev['after_cleanup'] = {'task': sql('select count(*) from test_tasks where id=%d;' % cid),
                           'ai_reviews': sql('select count(*) from ai_reviews where task_id=%d;' % cid),
                           'result_reviews': sql('select count(*) from test_result_reviews where task_id=%d;' % cid),
                           'cart': cart_state()['total']}


def main():
    ev = {'base': BASE, 'started_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    drv = driver()
    cid = None
    try:
        login(drv, ev)
        cid = create_container(ev)
        ev['container_id'] = cid
        if not cid:
            raise AssertionError('容器创建失败')
        phase_published(drv, ev)
        phase_review(drv, ev, cid)
        phase_history_overflow(drv, ev, cid)
    except Exception as exc:  # noqa: BLE001
        ev['error'] = repr(exc)
        import traceback
        ev['traceback'] = traceback.format_exc()
    finally:
        try:
            cleanup(ev, cid)
        except Exception as exc:  # noqa: BLE001
            ev['cleanup_error'] = repr(exc)
        ev['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(os.path.join(ART, 'evidence_rework.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps({k: v for k, v in ev.items() if k != 'traceback'}, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
