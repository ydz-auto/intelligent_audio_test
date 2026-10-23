# -*- coding: utf-8 -*-
"""INT-1486 脚本 D（收尾续验）：target_modes/config 请求体取证 + case-detail-dialog（任务详情共用组件）
+ 四窗深色截图 + 自建数据清理。"""
import json, os, sys, time, traceback
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import (  # noqa: E402
    API, ART, BASE, DEVICE_NAME, TASK_NAME, enter_resources, api_req, make_driver, js_click,
    text, wait_text, shot, dialogs, dialog_text, close_dialog, find_api_card_button, card_of,
    log_mark, WebDriverWait, By, Keys,
)

TOKEN_FILE = os.path.join(ART, 'token.txt')
API_NAME = None  # 运行时按 GET /apis 选最新自建 API


def main():
    token = open(TOKEN_FILE).read().strip()
    st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
    items = (apis.get('data', apis) or {}).get('items', [])
    mine = [x for x in items if str(x.get('name') or '').startswith('接线测试_INT1486_APIXC')]
    mh = [x for x in items if str(x.get('name') or '').startswith('接线测试_INT1486_HC')]
    api_name = mine[-1]['name'] if mine else None
    health_name = mh[-1]['name'] if mh else None
    print('use api', api_name, '| health api', health_name)

    d = make_driver(token)
    task_id = None
    try:
        # ---------- 提交并抓完整请求体（target_modes / config.network） ----------
        enter_resources(d)
        dc = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {DEVICE_NAME}"]')
        if dc:
            js_click(d, dc[0]); time.sleep(1.2)
        ac = find_api_card_button(d, api_name, '选择 API')
        if ac:
            js_click(d, ac); time.sleep(1.2)
        modes = d.find_elements(By.CSS_SELECTOR, f'[aria-label="{DEVICE_NAME} 执行模式"]')
        if modes:
            s = modes[0].find_elements(By.XPATH, ".//*[normalize-space(.)='串行']")
            if s:
                js_click(d, s[0]); time.sleep(1.2)
        print('MODE', modes[0].text.replace('\n', '|') if modes else None)
        net = d.find_elements(By.XPATH, "//h4[normalize-space()='网络配置']/following-sibling::*//*[@data-slot='select-trigger']")
        if net:
            js_click(d, net[0]); time.sleep(1)
            wi = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip() == 'Wi-Fi']
            if wi:
                js_click(d, wi[0]); time.sleep(1)
        # 打开任务命名弹窗并提交
        starts = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        js_click(d, starts[-1]); time.sleep(2)
        ti = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
        print('dialog open', len(ti), 'value', repr(ti[0].get_attribute('value')) if ti else None)
        ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); ti[0].send_keys(TASK_NAME)
        time.sleep(0.6)
        mark = log_mark(d)
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(18)
        entries = d.execute_script('return window.__fetchLog || []')
        captured = []
        for it in entries[mark:]:
            if '/tasks' in it['url']:
                captured.append(it)
        with open(os.path.join(ART, 'task_submit_requests.json'), 'w', encoding='utf-8') as f:
            json.dump(captured, f, ensure_ascii=False, indent=1)
        for it in captured:
            print('REQ', it['method'], it['status'], it['url'])
            if it['method'] == 'POST' and it.get('reqBody'):
                try:
                    body = json.loads(it['reqBody'])
                    print('  name', body.get('name'), '| case_ids', len(body.get('case_ids') or []),
                          '| device_ids', body.get('device_ids'), '| api_ids', body.get('api_ids'))
                    print('  target_modes', json.dumps(body.get('target_modes'), ensure_ascii=False))
                    print('  case_devices head', json.dumps((body.get('case_devices') or [])[:3], ensure_ascii=False))
                    print('  config', json.dumps(body.get('config'), ensure_ascii=False))
                except Exception as e:
                    print('  body parse fail', e)
            if it.get('resBody'):
                print('  RES', it['resBody'][:400])
                try:
                    j = json.loads(it['resBody'])
                    task_id = (j.get('data') or {}).get('id') or task_id
                except Exception:
                    pass
        print('NEW task_id', task_id)

        # ---------- case-detail-dialog（/tasks/{id} 任务详情共用组件） ----------
        target_task = task_id or 528
        d.get(BASE + f'/tasks/{target_task}')
        time.sleep(8)
        print('task detail url', d.current_url, '| has 用例 rows?', '测试用例_' in text(d))
        shot(d, 'D_task_detail_light.png')
        rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
        print('case rows', len(rows))
        if rows:
            mark = log_mark(d)
            js_click(d, rows[0]); time.sleep(4)
            print('CASEDETAIL dialog:', dialog_text(d)[:1400].replace('\n', ' | '))
            shot(d, 'D_case_detail_light.png')
            for it in d.execute_script('return window.__fetchLog || []')[mark:]:
                if '/cases/' in it['url'] or 'detail' in it['url']:
                    print('  REQ', it['method'], it['status'], it['url'], '|', (it.get('resBody') or '')[:300])
            # 遮罩关闭
            d.action = None
            overlay_closed = False
            overlays = d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-overlay"]')
            print('overlays', len(overlays))
            if overlays:
                js_click(d, overlays[0]); time.sleep(1.5)
                overlay_closed = not dialogs(d)
                print('closed by overlay', overlay_closed)
            if not overlay_closed:
                print('closed by Esc', close_dialog(d))

        # ---------- 深色四窗 ----------
        d.get(BASE + '/start-test')
        wait_text(d, '按分组', 90)
        time.sleep(3)
        try:
            js_click(d, d.find_element(By.CSS_SELECTOR, "[aria-label='打开主题设置']")); time.sleep(1.5)
            dark = d.find_elements(By.XPATH, "//*[normalize-space(.)='深色']")
            if dark:
                js_click(d, dark[-1]); time.sleep(2)
            print('theme', d.execute_script("return localStorage.getItem('iatp:theme:v1:mode')"))
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(1.2)
        except Exception as e:
            print('theme switch failed', e)
        enter_resources(d)
        shot(d, 'D_step2_dark.png')
        # api-edit 深色（回读展示）
        ac = find_api_card_button(d, api_name, '选择 API')
        if ac:
            card = card_of(d, ac)
            more = card.find_elements(By.CSS_SELECTOR, '[aria-label="更多操作"]')
            js_click(d, more[0]); time.sleep(1.2)
            mi = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
            if mi:
                js_click(d, mi[0]); time.sleep(2)
                shot(d, 'D_api_edit_dark.png')
                print('DARK api-edit dialog', dialog_text(d)[:150].replace('\n', ' | '))
                close_dialog(d)
        # api-health 深色
        if health_name:
            hb = find_api_card_button(d, health_name, '连接测试')
            if hb:
                js_click(d, hb)
                try:
                    WebDriverWait(d, 60).until(lambda x: '重新测试' in dialog_text(x) or not dialogs(x))
                except Exception:
                    pass
                time.sleep(1)
                shot(d, 'D_api_health_dark.png')
                close_dialog(d)
        # task-name 深色
        starts = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        if starts:
            js_click(d, starts[-1]); time.sleep(2)
            shot(d, 'D_taskname_dark.png')
            print('DARK taskname value', [x.get_attribute('value') for x in d.find_elements(By.CSS_SELECTOR, 'input#task-name')])
            close_dialog(d)
        # case-detail 深色（任务详情页）
        d.get(BASE + f'/tasks/{target_task}')
        time.sleep(8)
        rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
        print('dark case rows', len(rows))
        if rows:
            js_click(d, rows[0]); time.sleep(4)
            shot(d, 'D_case_detail_dark.png')
            print('DARK case-detail', dialog_text(d)[:200].replace('\n', ' | '))
            close_dialog(d)

        # ---------- 清理 ----------
        st, tasks = api_req('GET', '/api/v1/tasks?page=1&per_page=20', token)
        for it in (tasks.get('data', tasks) or {}).get('items', []):
            if str(it.get('name') or '').startswith('接线测试_INT1486'):
                tid = it['id']
                print('CLEAN task', tid, api_req('POST', f'/api/v1/tasks/{tid}/stop', token)[0],
                      api_req('DELETE', f'/api/v1/tasks/{tid}', token)[0],
                      api_req('DELETE', f'/api/v1/tasks/{tid}/purge', token)[0])
        st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
        for it in (apis.get('data', apis) or {}).get('items', []):
            if str(it.get('name') or '').startswith('接线测试_INT1486'):
                print('CLEAN api', it['id'], api_req('DELETE', f"/api/v1/apis/{it['id']}", token)[0])
        st, tasks = api_req('GET', '/api/v1/tasks?page=1&per_page=20', token)
        print('RESIDUE tasks', [x['name'] for x in (tasks.get('data', tasks) or {}).get('items', []) if 'INT1486' in (x.get('name') or '')])
        st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
        print('RESIDUE apis', [x['name'] for x in (apis.get('data', apis) or {}).get('items', []) if 'INT1486' in (x.get('name') or '')])
    except Exception:
        traceback.print_exc()
        shot(d, 'D_error.png')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
