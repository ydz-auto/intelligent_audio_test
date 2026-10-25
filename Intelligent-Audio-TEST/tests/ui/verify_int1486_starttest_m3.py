# -*- coding: utf-8 -*-
"""INT-1486 回归 M3：新构建（INT-1769 合入后）上重走任务命名弹窗——默认名 / 取消后重开重置(INT-1528)
+ 真实提交 + GET /tasks?keyword= 回读 + task 清理；浅/深截图。

只建本 run「接线测试_INT1486_M3_」任务，finally 里 stop + delete + purge。
"""
import json, os, sys, time, traceback, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
TASK_NAME = '接线测试_INT1486_M3_' + SUFFIX
report = {'checks': [], 'env': {}}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:300] if detail else ''))
    return ok


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h1 = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health_start'] = h1
    chk('env /health database=intelligent_audio_test',
        isinstance(h1, dict) and h1.get('database') == 'intelligent_audio_test', h1)
    task_id = None
    d = F.make_driver(token)
    try:
        F.wait_step1(d)
        picked = F.select_manual_cases(d, 1)
        chk('步骤一 手动勾选用例（INT-1542 入口）', len(picked) == 1, picked)
        F.next_step(d)
        ok_dev = F.pick_device(d)
        chk('步骤二 设备勾选', ok_dev, F.DEVICE_NAME)
        F.close_dialog(d)

        # 打开任务命名弹窗 → 默认名
        chk('打开任务命名弹窗（开始测试）', F.click_start(d))
        inp = F.taskname_input(d)
        chk('任务命名弹窗出现', inp is not None)
        default_name = inp.get_attribute('value') if inp else ''
        chk('默认任务名 = 测试任务_*（INT-1528）', default_name.startswith('测试任务_'), repr(default_name))
        F.shot(d, 'M3_task_name_light.png')

        # 改名 → 取消 → 重开必须恢复默认名
        F.set_input(d, inp, '接线测试_INT1486_残留名')
        F.close_dialog(d)
        time.sleep(1.5)
        F.click_start(d)
        inp2 = F.taskname_input(d)
        reopened = inp2.get_attribute('value') if inp2 else ''
        chk('取消后重开恢复默认名（INT-1528）', reopened.startswith('测试任务_') and '残留名' not in reopened,
            repr(reopened))

        # 深色截图
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        time.sleep(1)
        F.shot(d, 'M3_task_name_dark.png')
        chk('深色主题生效', d.execute_script("return document.documentElement.classList.contains('dark')") is True)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        time.sleep(1)

        # 真实提交 + 回读
        inp3 = F.taskname_input(d)
        F.set_input(d, inp3, TASK_NAME)
        mark = F.log_mark(d)
        st, launch = F.api_req('GET', '/api/v1/tasks?per_page=1', token)  # 基线
        F.click_start(d) if False else None
        # 点弹窗主钮「开始测试」
        btns = d.find_elements(F.By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")
        chk('任务命名弹窗主钮「开始测试」', bool(btns))
        if btns:
            F.js_click(d, btns[-1])
            for _ in range(60):
                time.sleep(1)
                if not [x for x in d.find_elements(F.By.CSS_SELECTOR, 'input#task-name') if x.is_displayed()]:
                    break
            time.sleep(5)
        F.log_show(d, mark, keys=('/tasks',), maxn=12)
        st, body = F.api_req('GET', '/api/v1/tasks?per_page=50&keyword=' + urllib.parse.quote(TASK_NAME), token)
        items = (body.get('data', body) or {}).get('items', []) if isinstance(body, dict) else []
        hit = next((x for x in items if (x.get('name') or '') == TASK_NAME), None)
        chk('POST 后 GET /tasks?keyword 回读命中', hit is not None,
            {'status': st, 'n': len(items), 'names': [x.get('name') for x in items][:5]})
        if hit:
            task_id = hit.get('id')
            chk('回读任务 case 数 = 1', (hit.get('case_count') or hit.get('total_cases')) in (1, None),
                {k: v for k, v in hit.items() if 'case' in k.lower()})
        F.shot(d, 'M3_after_submit_light.png')
        report['task_id'] = task_id
    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'M3_error.png')
        except Exception:
            pass
    finally:
        try:
            d.quit()
        except Exception:
            pass
        if task_id:
            try:
                F.stop_and_cleanup_task(d, token, task_id)
            except Exception:
                traceback.print_exc()
        st, t2 = F.api_req('GET', '/api/v1/tasks?per_page=50&keyword=' + urllib.parse.quote(TASK_NAME), token)
        items2 = (t2.get('data', t2) or {}).get('items', []) if isinstance(t2, dict) else []
        residue = [x.get('name') for x in items2 if (x.get('name') or '') == TASK_NAME]
        report['residue'] = residue
        chk('数据卫生：本 run 任务已清理', not residue, residue)
        st, h2 = F.api_req('GET', '/health', token, timeout=20)
        report['env']['health_end'] = h2
        with open(os.path.join(ART, 'rewalk_m3_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'total': len(report['checks']), 'residue': residue,
                                     'task_id': task_id}, ensure_ascii=False))


if __name__ == '__main__':
    main()
