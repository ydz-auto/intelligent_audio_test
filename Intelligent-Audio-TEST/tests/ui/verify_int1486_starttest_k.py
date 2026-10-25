# -*- coding: utf-8 -*-
"""INT-1486 补验 K：C8 空筛选拦截（含 toast 轮询）+ 步骤二 API 卡片的 api-edit / api-health（浅/深）。

背景：F/J 两处失败均为脚本侧走法问题——
  C8 需在第 2 步（索引 1）点「开始测试」，且校验提示是 sonner toast，需轮询读取；
  api-edit/api-health 入口在**步骤二**（设备/API 同屏），F/J 在步骤一查询，必然找不到卡片。
"""
import json, os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
API_NAME = '接线测试_INT1486_KAPI_' + SUFFIX
EMPTY_KEYWORD = 'ZZZ_NO_MATCH_INT1486'
report = {'checks': [], 'env': {}, 'apis': [], 'notes': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def wait_step2(d, timeout=120):
    """步骤二：等到设备卡与 API 卡都渲染（API 列表异步）。"""
    F.next_step(d)
    end = time.time() + timeout
    dev = None
    while time.time() < end:
        devs = [e for e in d.find_elements('css selector', f'[aria-label="选择设备 {F.DEVICE_NAME}"]') if e.is_displayed()]
        if devs:
            dev = devs[0]
            break
        time.sleep(2)
    return dev


def wait_api_card(d, name, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements('css selector', f'[aria-label="选择 API {name}"]') if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(2)
    return None


def card_of(d, el):
    return d.execute_script('''
      let n = arguments[0];
      while (n && n !== document.body) {
        if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
        n = n.parentElement;
      }
      return arguments[0].parentElement;
    ''', el)


def open_edit(d, name):
    cb = wait_api_card(d, name)
    if not cb:
        return False
    card = card_of(d, cb)
    more = card.find_elements(F.By.CSS_SELECTOR, '[aria-label="更多操作"]')
    if not more:
        return False
    F.js_click(d, more[0]); time.sleep(1.2)
    mi = d.find_elements(F.By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
    if not mi:
        return False
    F.js_click(d, mi[0]); time.sleep(2.5)
    return True


def click_start_poll(d, seconds=8):
    """点开始测试后轮询 toast/弹窗，避免 sonner 自动消失造成漏取。"""
    st = d.find_elements(F.By.XPATH, "//button[normalize-space(.)='开始测试']")
    if not st:
        return {'clicked': False}
    F.js_click(d, st[-1])
    seen = {'clicked': True, 'toasts': [], 'dialogs': 0}
    end = time.time() + seconds
    while time.time() < end:
        t = F.text(d)
        for ln in t.splitlines():
            if ('没有可用' in ln or '请调整筛选' in ln or '请选择用例' in ln) and ln not in seen['toasts']:
                seen['toasts'].append(ln)
        if F.dialogs(d):
            seen['dialogs'] = len(F.dialogs(d))
        time.sleep(0.3)
    return seen


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h1 = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health_start'] = h1
    chk('env /health database=intelligent_audio_test',
        isinstance(h1, dict) and h1.get('database') == 'intelligent_audio_test', h1)

    d = F.make_driver(token)
    api_id = None
    try:
        # ---------- C8 空筛选入口拦截 ----------
        F.wait_step1(d)
        F.search_cases(d, EMPTY_KEYWORD)
        lines = F.summary_lines(d)
        chk('C8a 空筛选汇总显示全部 0 条', any('全部 0 条' in ln for ln in lines), lines)
        dev = wait_step2(d)
        chk('C8b 步骤二设备卡出现', dev is not None)
        if dev is not None:
            F.js_click(d, dev); time.sleep(1.2)
        mark = F.log_mark(d)
        res = click_start_poll(d)
        posts = [e for e in F.log_entries(d, mark, keys=('/tasks',)) if e['method'] == 'POST']
        res['posts'] = len(posts)
        report['notes'].append({'C8': res})
        chk('C8c 空筛选点开始测试：无 POST /tasks', res['clicked'] and res['posts'] == 0, res)
        chk('C8 空筛选入口拦截：toast 提示调整筛选且不开任务弹窗',
            bool(res['toasts']) and res['dialogs'] == 0, res)
        F.shot(d, 'K_filter_empty_blocked_light.png')

        # ---------- 临时 API ----------
        st, hc = F.api_req('POST', '/api/v1/apis', token, {
            'name': API_NAME, 'description': 'INT-1486 补验临时', 'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'endpoints': [{'endpoint': 'https://example.test/int1486-k', 'name': None, 'max_process': 1,
                           'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                           'description': None}]})
        if isinstance(hc, dict):
            api_id = (hc.get('data') or {}).get('id') or hc.get('id')
        chk('D3 临时 API 创建', st < 300 and api_id is not None, {'status': st, 'id': api_id, 'body': str(hc)[:200]})
        report['apis'].append({'id': api_id, 'name': API_NAME})

        # ---------- api-edit 浅色 ----------
        F.wait_step1(d)
        wait_step2(d)
        opened = open_edit(d, API_NAME)
        chk('D4 步骤二 API 卡片出现并可打开编辑', opened)
        if opened:
            back = d.find_element(F.By.ID, 'api-name').get_attribute('value')
            urls = d.find_elements(F.By.CSS_SELECTOR, "input[aria-label='端点 URL']")
            back_url = urls[0].get_attribute('value') if urls else None
            chk('D5 api-edit 回填名称', back == API_NAME, repr(back))
            chk('D6 api-edit 回填端点 URL', back_url == 'https://example.test/int1486-k', repr(back_url))
            F.shot(d, 'K_api_edit_light.png')
            # 保存回读：改名后保存，GET /apis/{id} 核对
            new_name = API_NAME + '_改'
            F.set_input(d, d.find_element(F.By.ID, 'api-name'), new_name)
            save = [b for b in d.find_elements(F.By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']")]
            mark = F.log_mark(d)
            if save:
                F.js_click(d, save[-1]); time.sleep(6)
            F.log_show(d, mark, keys=('/apis',))
            st, one = F.api_req('GET', f'/api/v1/apis/{api_id}', token)
            body = one.get('data', one) if isinstance(one, dict) else {}
            chk('D6b api-edit 改名保存后 GET 回读一致', body.get('name') == new_name,
                {'status': st, 'name': body.get('name')})
            API_NAME_SAVED = new_name
            F.close_dialog(d)
        else:
            API_NAME_SAVED = API_NAME

        # ---------- api-health 浅色 ----------
        F.wait_step1(d)
        wait_step2(d)
        hb = []
        end = time.time() + 60
        while time.time() < end and not hb:
            hb = [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {API_NAME_SAVED}"]') if e.is_displayed()]
            time.sleep(2)
        chk('D4b 健康检查入口出现', bool(hb))
        if hb:
            mark = F.log_mark(d)
            F.js_click(d, hb[0]); time.sleep(1)
            try:
                F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
            except Exception:
                pass
            ht = F.dialog_text(d)
            chk('D7 api-health 结果态渲染（重新测试钮）', '重新测试' in ht, ht[:400])
            F.shot(d, 'K_api_health_light.png')
            F.log_show(d, mark, keys=('/apis/', 'health'))
            F.close_dialog(d)

        # ---------- 深色 ----------
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        F.wait_step1(d)
        wait_step2(d)
        time.sleep(2)
        chk('D8 深色主题生效',
            d.execute_script("return document.documentElement.classList.contains('dark')") is True,
            d.execute_script("return document.documentElement.className"))
        opened = open_edit(d, API_NAME_SAVED)
        chk('D9 api-edit 深色打开', opened)
        if opened:
            F.shot(d, 'K_api_edit_dark.png')
            F.close_dialog(d)
        hb = []
        end = time.time() + 60
        while time.time() < end and not hb:
            hb = [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {API_NAME_SAVED}"]') if e.is_displayed()]
            time.sleep(2)
        if hb:
            F.js_click(d, hb[0])
            try:
                F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
            except Exception:
                pass
            time.sleep(1)
            F.shot(d, 'K_api_health_dark.png')
            chk('D10 api-health 深色结果态', '重新测试' in F.dialog_text(d), F.dialog_text(d)[:200])
            F.close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'K_error.png')
        except Exception:
            pass
    finally:
        d.quit()
        st, apis = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items = (apis.get('data', apis) or {}).get('items', []) if isinstance(apis, dict) else []
        mine = [x for x in items if '接线测试_INT1486' in (x.get('name') or '')]
        for x in mine:
            print('CLEAN api', x['id'], x['name'], F.api_req('DELETE', f"/api/v1/apis/{x['id']}", token))
        st, apis2 = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items2 = (apis2.get('data', apis2) or {}).get('items', []) if isinstance(apis2, dict) else []
        residue = [x['name'] for x in items2 if '接线测试_INT1486' in (x.get('name') or '')]
        report['residue'] = residue
        chk('数据卫生：无 INT1486 残留 API', not residue, residue)
        st, h2 = F.api_req('GET', '/health', token, timeout=20)
        report['env']['health_end'] = h2
        with open(os.path.join(ART, 'rewalk_k_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'checks': len(report['checks']), 'residue': residue},
                                    ensure_ascii=False)[:1500])


if __name__ == '__main__':
    main()
