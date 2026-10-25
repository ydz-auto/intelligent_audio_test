# -*- coding: utf-8 -*-
"""INT-1486 补验 M2：抢在执行态内截步骤三用例行 → case-detail-dialog（任务 3 条用例，提交后立即轮询）。"""
import json, os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

ART = F.ART
TASK_NAME = '接线测试_INT1486_M2执行页_' + str(int(time.time()))[-6:]
report = {'checks': [], 'env': {}}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:300] if detail else ''))
    return ok


def case_rows(d):
    """collect 用例行按钮；页面在轮询中会重渲染，逐元素 try/except 防 stale。"""
    rows = []
    for e in d.find_elements(F.By.TAG_NAME, 'button'):
        try:
            t = e.text or ''
        except Exception:
            continue
        if '测试用例_' in t or 'JG008' in t:
            rows.append(e)
    return rows


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health'] = h
    d = F.make_driver(token)
    task_id = None
    try:
        F.wait_step1(d)
        picked = F.select_manual_cases(d, 3)
        chk('M2-1 勾选 3 条用例', len(picked) == 3, picked)
        F.next_step(d)
        chk('M2-2 步骤二选中设备', F.pick_device(d))
        F.click_start(d)
        ti = F.taskname_input(d)
        chk('M2-2b 任务命名弹窗打开', ti is not None)
        F.set_input(d, ti, TASK_NAME)
        mark = F.log_mark(d)
        F.js_click(d, d.find_elements(F.By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        # 提交后立即轮询：步骤三用例行 / 弹窗
        found = False
        deadline = time.time() + 90
        seen_states = []
        while time.time() < deadline:
            rows = case_rows(d)
            try:
                url = d.current_url
                txt = F.text(d)[:200]
            except Exception:
                url, txt = '', ''
            if rows:
                found = True
                break
            seen_states.append((url, [ln for ln in txt.splitlines() if '执行' in ln or '报告' in ln][:3]))
            time.sleep(1.5)
        entries = F.log_entries(d, mark, keys=('/tasks',))
        for e in entries:
            if e['method'] == 'POST' and '/tasks' in e['url'] and e.get('resBody'):
                try:
                    task_id = (json.loads(e['resBody']).get('data') or {}).get('id')
                except Exception:
                    pass
        report['task_id'] = task_id
        report['states'] = seen_states[-6:]
        chk('M2-3 进入步骤三并出现用例行', found, {'url': d.current_url, 'rows': len(case_rows(d)), 'seen': seen_states[-3:]})
        if found:
            F.shot(d, 'M2_step3_executing_light.png')
            rows = case_rows(d)
            F.js_click(d, rows[0]); time.sleep(5)
            ct = F.dialog_text(d)
            chk('M2-4 步骤三 case-detail 弹窗渲染',
                ('执行日志' in ct) or ('评估中' in ct) or ('执行结果' in ct), ct[:300])
            F.shot(d, 'M2_step3_case_detail_light.png')
            F.close_dialog(d)
            # 深色：同一会话内切主题后重新点开（不刷新，避免丢 taskId）
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
            time.sleep(1.5)
            if d.execute_script("return document.documentElement.classList.contains('dark')") is True:
                rows = case_rows(d)
                if rows:
                    F.js_click(d, rows[0]); time.sleep(5)
                    chk('M2-5 步骤三 case-detail 深色渲染',
                        ('执行日志' in F.dialog_text(d)) or ('评估中' in F.dialog_text(d)), F.dialog_text(d)[:200])
                    F.shot(d, 'M2_step3_case_detail_dark.png')
                    F.close_dialog(d)
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        else:
            F.shot(d, 'M2_step3_not_reached.png')
    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'M2_error.png')
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
        with open(os.path.join(ART, 'rewalk_m2_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'checks': len(report['checks']), 'task_id': task_id},
                                    ensure_ascii=False)[:1000])


if __name__ == '__main__':
    main()
