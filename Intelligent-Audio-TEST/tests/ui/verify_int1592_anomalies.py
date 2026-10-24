# -*- coding: utf-8 -*-
"""INT-1592 父卡两处遗留异常定性（真鼠标事件 + Network 取证）。

异常 1 发布任务弹窗：来源任务下拉停在「加载中…」/「发布」钮 disabled。
  - 复现两种来源任务：新任务（在 fetchTaskList perPage=100 首页内）与旧任务（不在首页内），
    对照「source 是否能从已加载 100 项中解析」→ 判定是后端慢查询还是前端 disabled 判定。
异常 2 重新执行范围弹窗：确认钮点击无 POST /tasks/{id}/retry。
  - 用 ActionChains 真实鼠标事件点击；对照 review_count=0（556）与 review_count=1（419）
    两种任务，验证是否被「人工复核覆盖硬确认层」截获。

用法：python tests/ui/verify_int1592_anomalies.py
输出：tests/ui/artifacts/int1592/50~58_*.png + evidence_anomalies.json
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium.webdriver import ActionChains  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1592_cherry_pick import (  # noqa: E402
    ART, BASE, STATE_PATH, api, body_text, data_of, driver, js_click, log, login, set_dark, shot, toast_texts,
)

NEW_TASK = None   # 本卡容器（最新，预计在首页 100 条内）
OLD_TASK = 419    # 小艺拒识（较旧，用于对照）


def drain(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def new_requests(drv):
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


def open_row_menu(drv, task_id):
    """在 /tasks 日常表按行 id 打开「任务操作」菜单。

    行内数据无 task id 属性，故按任务名匹配所在 tr。
    """
    detail = data_of(api('GET', f'/api/v1/tasks/{task_id}')) or {}
    name = detail.get('name') or ''
    WebDriverWait(drv, 120).until(
        lambda d: d.find_elements(By.XPATH, f"//tr[.//span[contains(normalize-space(.), '{name}')]]"))
    rows = drv.find_elements(By.XPATH, f"//tr[.//span[contains(normalize-space(.), '{name}')]]")
    rows = [r for r in rows if r.is_displayed()]
    if not rows:
        raise AssertionError(f'日常任务列表未找到任务 {task_id}「{name}」')
    trig = rows[0].find_element(By.CSS_SELECTOR, "button[aria-label='任务操作']")
    js_click(drv, trig)
    time.sleep(0.8)


def menu_item(drv, text):
    els = [e for e in drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(normalize-space(.), '{text}')]") if e.is_displayed()]
    if not els:
        raise AssertionError('菜单项未出现: ' + text)
    js_click(drv, els[0])
    time.sleep(1.2)


def publish_probe(drv, task_id):
    drain(drv)
    open_row_menu(drv, task_id)
    menu_item(drv, '发布')
    t0 = time.time()
    WebDriverWait(drv, 20).until(lambda d: '发布任务' in body_text(d))
    time.sleep(1.5)
    dlg = drv.find_element(By.XPATH, "//*[@role='dialog'][.//*[contains(normalize-space(.), '发布任务')]]")
    # 先记录弹窗初始态（来源卡 / 发布钮 enabled）
    body_before = dlg.text
    trig = [b for b in dlg.find_elements(By.CSS_SELECTOR, "button[aria-label='选择来源任务']") if b.is_displayed()]
    trigger_text = trig[0].text if trig else ''
    publish_btn = None
    for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='发布']"):
        if b.is_displayed():
            publish_btn = b
            break
    info = {
        'task_id': task_id,
        'elapsed_s': round(time.time() - t0, 1),
        'trigger_text': trigger_text,
        'trigger_shows_raw_id': trigger_text.strip() == str(task_id),
        'publish_disabled': (not publish_btn.is_enabled()) if publish_btn else None,
        'source_card_in_dialog': '设备' in body_before,
        'dialog_head': body_before[:500],
    }
    # 打开来源下拉读选项后，再点触发器关闭（ESC 会连带关弹窗）
    if trig:
        js_click(drv, trig[0])
        time.sleep(1.2)
        option_texts = [o.text for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        # 仍在加载 → 等加载完成（最多 40s），再记录最终态
        waited = 0
        while any('加载中' in o for o in option_texts) and waited < 40:
            time.sleep(2)
            waited += 2
            option_texts = [o.text for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        info['option_count'] = len(option_texts)
        info['option_has_loading'] = any('加载中' in o for o in option_texts)
        info['option_first'] = option_texts[:3]
        info['load_wait_s'] = waited
        js_click(drv, trig[0])
        time.sleep(1.0)
    # 加载完成后的最终态（发布钮 / 来源卡）
    body_after = dlg.text
    publish_btn2 = None
    for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='发布']"):
        if b.is_displayed():
            publish_btn2 = b
            break
    info['publish_disabled_after_load'] = (not publish_btn2.is_enabled()) if publish_btn2 else None
    info['source_card_after_load'] = '设备' in body_after
    info['dialog_after_load_head'] = body_after[:500]
    reqs = new_requests(drv)
    info['fetch_task_requests'] = [r['url'] for r in reqs if '/api/v1/tasks?' in r['url']]
    shot(drv, f'50_publish_dialog_task{task_id}_light.png')
    set_dark(drv, True)
    shot(drv, f'51_publish_dialog_task{task_id}_dark.png')
    set_dark(drv, False)
    for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='取消']"):
        if b.is_displayed():
            js_click(drv, b)
            break
    time.sleep(1)
    return info


def reexecute_probe(drv, task_id):
    drain(drv)
    open_row_menu(drv, task_id)
    menu_item(drv, '重新执行')
    WebDriverWait(drv, 30).until(lambda d: '重新执行' in body_text(d) and '全部用例' in body_text(d))
    time.sleep(1)
    # 确认钮（真实鼠标事件）
    confirm = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '确认')]") if b.is_displayed()]
    if not confirm:
        return {'task_id': task_id, 'error': '确认钮未出现'}
    btn = confirm[-1]
    before_url = drv.current_url
    ActionChains(drv).move_to_element(btn).pause(0.2).click().perform()
    time.sleep(3.5)
    reqs = new_requests(drv)
    retry_reqs = [r for r in reqs if '/retry' in r['url'] or '/reevaluate' in r['url']]
    alerts = [a for a in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if a.is_displayed()]
    info = {
        'task_id': task_id,
        'retry_requests': retry_reqs,
        'alert_dialog': alerts[0].text[:400] if alerts else None,
        'url_changed': drv.current_url != before_url,
        'toasts': toast_texts(drv),
        'body_snippet': body_text(drv)[-500:],
    }
    shot(drv, f'52_reexecute_task{task_id}_after_confirm.png')
    # 关掉可能出现的硬确认层 / 弹窗
    for a in alerts:
        for b in a.find_elements(By.XPATH, ".//button[normalize-space(.)='返回' or normalize-space(.)='取消']"):
            if b.is_displayed():
                js_click(drv, b)
                break
        time.sleep(0.8)
    for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消']"):
        if b.is_displayed():
            js_click(drv, b)
            break
    time.sleep(1)
    return info


def main():
    global NEW_TASK
    with open(STATE_PATH, encoding='utf-8') as f:
        NEW_TASK = json.load(f)['container_id']
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else 'all'
    ev = {'base': BASE, 'new_task': NEW_TASK, 'old_task': OLD_TASK, 'only': only}
    drv = driver()
    try:
        login(drv, ev)
        drv.get(BASE + '/tasks')
        WebDriverWait(drv, 180).until(
            lambda d: [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='任务操作']") if b.is_displayed()])
        time.sleep(4)
        shot(drv, '53_daily_list_light.png')
        if only in ('all', 'publish'):
            ev['publish_new'] = publish_probe(drv, NEW_TASK)
            ev['publish_old'] = publish_probe(drv, OLD_TASK)
        if only in ('all', 'reexecute'):
            drv.get(BASE + '/tasks')
            time.sleep(4)
            ev['reexecute_new'] = reexecute_probe(drv, NEW_TASK)
            drv.get(BASE + '/tasks')
            time.sleep(4)
            ev['reexecute_old'] = reexecute_probe(drv, OLD_TASK)
    finally:
        name = 'evidence_anomalies.json' if only == 'all' else f'evidence_anomalies_{only}.json'
        with open(os.path.join(ART, name), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
