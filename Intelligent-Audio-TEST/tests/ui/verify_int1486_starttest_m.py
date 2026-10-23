# -*- coding: utf-8 -*-
"""INT-1486 补验 M：步骤三执行页 → 点击用例行打开 case-detail-dialog（补齐唯一剩余未覆盖入口截图）。

流程：步骤一勾选 1 条 → 步骤二选设备 → 任务命名提交 → 落到步骤三 → 点用例行截图 → 立即停止/删除/purge。
"""
import json, os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

ART = F.ART
TASK_NAME = '接线测试_INT1486_M执行页_' + str(int(time.time()))[-6:]
report = {'checks': [], 'env': {}}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health'] = h
    d = F.make_driver(token)
    task_id = None
    try:
        F.wait_step1(d)
        picked = F.select_manual_cases(d, 1)
        chk('M1 勾选 1 条用例', len(picked) == 1, picked)
        F.next_step(d)
        chk('M2 步骤二选中设备', F.pick_device(d))
        F.click_start(d)
        ti = F.taskname_input(d)
        chk('M3 任务命名弹窗打开', ti is not None)
        F.set_input(d, ti, TASK_NAME)
        mark = F.log_mark(d)
        F.js_click(d, d.find_elements(F.By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(12)
        entries = F.log_entries(d, mark, keys=('/tasks',))
        payload, post = F.find_task_payload(entries)
        chk('M4 POST /tasks 201', post is not None and post.get('status') == 201, (post or {}).get('status'))
        # 取任务 id：从 fetch 响应体或任务列表
        for e in entries:
            if e['method'] == 'POST' and '/tasks' in e['url'] and e.get('resBody'):
                try:
                    j = json.loads(e['resBody'])
                    task_id = (j.get('data') or {}).get('id')
                except Exception:
                    pass
        if task_id is None:
            st, tl = F.api_req('GET', '/api/v1/tasks?page=1&per_page=10', token)
            items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
            task_id = next((x['id'] for x in items if x.get('name') == TASK_NAME), None)
        report['task_id'] = task_id
        chk('M5 任务已创建并启动', task_id is not None, task_id)
        time.sleep(6)
        body = F.text(d)
        out = d.current_url
        chk('M6 提交后进入步骤三（执行页）', 'step=3' in out or '执行中' in body or '执行测试' in body, out)
        F.shot(d, 'M_step3_executing_light.png')
        # 用例行 → case-detail
        rows = [e for e in d.find_elements(F.By.TAG_NAME, 'button')
                if ('测试用例_' in (e.text or '') or 'JG0081' in (e.text or '') or 'JG0080' in (e.text or ''))]
        print('STEP3 rows', len(rows))
        chk('M7 步骤三用例行可点', bool(rows))
        if rows:
            F.js_click(d, rows[0]); time.sleep(5)
            ct = F.dialog_text(d)
            chk('M8 步骤三 case-detail 弹窗渲染', ('执行日志' in ct) or ('评估中' in ct) or ('执行结果' in ct), ct[:300])
            F.shot(d, 'M_step3_case_detail_light.png')
            F.close_dialog(d)
        # 深色
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.refresh(); time.sleep(10)
        rows = [e for e in d.find_elements(F.By.TAG_NAME, 'button')
                if ('测试用例_' in (e.text or '') or 'JG0081' in (e.text or '') or 'JG0080' in (e.text or ''))]
        if rows:
            F.js_click(d, rows[0]); time.sleep(5)
            chk('M9 步骤三 case-detail 深色渲染',
                ('执行日志' in F.dialog_text(d)) or ('评估中' in F.dialog_text(d)), F.dialog_text(d)[:200])
            F.shot(d, 'M_step3_case_detail_dark.png')
            F.close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'M_error.png')
        except Exception:
            pass
    finally:
        d.quit()
        if task_id:
            print('STOP', F.api_req('POST', f'/api/v1/tasks/{task_id}/stop', token, {}))
            time.sleep(3)
            print('DEL', F.api_req('DELETE', f'/api/v1/tasks/{task_id}', token))
            print('PURGE', F.api_req('DELETE', f'/api/v1/tasks/{task_id}/purge', token))
        st, one = F.api_req('GET', f'/api/v1/tasks/{task_id}', token) if task_id else (0, {})
        chk('数据卫生：临时任务已清除', st == 404 or not task_id, st)
        with open(os.path.join(ART, 'rewalk_m_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'checks': len(report['checks']), 'task_id': task_id},
                                    ensure_ascii=False)[:1200])


if __name__ == '__main__':
    main()
