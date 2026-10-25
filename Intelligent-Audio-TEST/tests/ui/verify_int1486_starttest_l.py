# -*- coding: utf-8 -*-
"""INT-1486 补验 L：步骤二 API 卡片 → api-edit（回填/改名保存回读）+ api-health（浅/深）。

锚点用卡片内唯一的「连接测试 {API名}」按钮（实测该卡必渲染），再回到同卡片的「更多操作 → 编辑」，
避免直接按勾选框 aria-label 命中竞态；同时记录勾选框存在性。
"""
import json, os, sys, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
API_NAME = '接线测试_INT1486_LAPI_' + SUFFIX
NEW_NAME = API_NAME + '_改'
report = {'checks': [], 'env': {}, 'apis': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def card_of(d, el):
    return d.execute_script('''
      let n = arguments[0];
      while (n && n !== document.body) {
        if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
        n = n.parentElement;
      }
      return arguments[0].parentElement;
    ''', el)


def goto_step2(d):
    F.wait_step1(d)
    F.next_step(d)


def find_health_btn(d, name, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {name}"]') if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(2)
    return None


def find_checkbox(d, name, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements('css selector', f'[aria-label="选择 API {name}"]') if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(1)
    return None


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h1 = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health_start'] = h1
    chk('env /health database=intelligent_audio_test',
        isinstance(h1, dict) and h1.get('database') == 'intelligent_audio_test', h1)

    st, hc = F.api_req('POST', '/api/v1/apis', token, {
        'name': API_NAME, 'description': 'INT-1486 补验 L', 'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://example.test/int1486-l', 'name': None, 'max_process': 1,
                       'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                       'description': None}]})
    api_id = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
    chk('D3 临时 API 创建', st < 300 and api_id is not None, {'status': st, 'id': api_id})
    report['apis'].append({'id': api_id, 'name': API_NAME})

    d = F.make_driver(token)
    name_now = API_NAME
    try:
        # ================= 浅色：api-edit =================
        goto_step2(d)
        hb = find_health_btn(d, API_NAME)
        chk('D4 步骤二 API 卡片渲染（连接测试入口）', hb is not None)
        cb = find_checkbox(d, API_NAME)
        chk('D4c 卡片勾选框存在（选择 API）', cb is not None, cb.get_attribute('aria-label') if cb else None)
        if hb is not None:
            F.shot(d, 'L_step2_api_card_light.png')
            card = card_of(d, hb)
            more = card.find_elements(F.By.CSS_SELECTOR, '[aria-label="更多操作"]')
            chk('D4d 卡片「更多操作」入口', bool(more))
            if more:
                F.js_click(d, more[0]); time.sleep(1.2)
                mi = d.find_elements(F.By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
                chk('D4e 菜单「编辑」项', bool(mi))
                if mi:
                    F.js_click(d, mi[0]); time.sleep(3)
                    back = d.find_element(F.By.ID, 'api-name').get_attribute('value')
                    urls = d.find_elements(F.By.CSS_SELECTOR, "input[aria-label='端点 URL']")
                    back_url = urls[0].get_attribute('value') if urls else None
                    chk('D5 api-edit 回填名称', back == API_NAME, repr(back))
                    chk('D6 api-edit 回填端点 URL', back_url == 'https://example.test/int1486-l', repr(back_url))
                    F.shot(d, 'L_api_edit_light.png')
                    # 改名保存 → GET 回读
                    F.set_input(d, d.find_element(F.By.ID, 'api-name'), NEW_NAME)
                    save = d.find_elements(F.By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']")
                    mark = F.log_mark(d)
                    if save:
                        F.js_click(d, save[-1]); time.sleep(7)
                    F.log_show(d, mark, keys=('/apis',))
                    st, one = F.api_req('GET', f'/api/v1/apis/{api_id}', token)
                    body = one.get('data', one) if isinstance(one, dict) else {}
                    chk('D6b api-edit 改名保存后 GET 回读一致', body.get('name') == NEW_NAME,
                        {'status': st, 'name': body.get('name')})
                    if body.get('name') == NEW_NAME:
                        name_now = NEW_NAME
                    F.close_dialog(d)

        # ================= 浅色：api-health =================
        goto_step2(d)
        hb = find_health_btn(d, name_now)
        chk('D4b 健康检查入口（改名后仍在）', hb is not None)
        if hb is not None:
            mark = F.log_mark(d)
            F.js_click(d, hb); time.sleep(1)
            try:
                F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
            except Exception:
                pass
            ht = F.dialog_text(d)
            chk('D7 api-health 结果态渲染（重新测试钮）', '重新测试' in ht, ht[:300])
            F.shot(d, 'L_api_health_light.png')
            F.log_show(d, mark, keys=('/apis/', 'health'))
            F.close_dialog(d)

        # ================= 深色：四窗中的 api-edit / api-health =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        goto_step2(d)
        time.sleep(2)
        chk('D8 深色主题生效',
            d.execute_script("return document.documentElement.classList.contains('dark')") is True,
            d.execute_script("return document.documentElement.className"))
        hb = find_health_btn(d, name_now)
        if hb is not None:
            card = card_of(d, hb)
            more = card.find_elements(F.By.CSS_SELECTOR, '[aria-label="更多操作"]')
            if more:
                F.js_click(d, more[0]); time.sleep(1.2)
                mi = d.find_elements(F.By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
                if mi:
                    F.js_click(d, mi[0]); time.sleep(2.5)
                    chk('D9 api-edit 深色打开', F.dialogs(d) != [])
                    F.shot(d, 'L_api_edit_dark.png')
                    F.close_dialog(d)
            hb = find_health_btn(d, name_now)
            if hb is not None:
                F.js_click(d, hb)
                try:
                    F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
                except Exception:
                    pass
                time.sleep(1)
                F.shot(d, 'L_api_health_dark.png')
                chk('D10 api-health 深色结果态', '重新测试' in F.dialog_text(d), F.dialog_text(d)[:200])
                F.close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'L_error.png')
        except Exception:
            pass
    finally:
        d.quit()
        st, apis = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items = (apis.get('data', apis) or {}).get('items', []) if isinstance(apis, dict) else []
        for x in [y for y in items if '接线测试_INT1486' in (y.get('name') or '')]:
            print('CLEAN api', x['id'], x['name'], F.api_req('DELETE', f"/api/v1/apis/{x['id']}", token))
        st, apis2 = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items2 = (apis2.get('data', apis2) or {}).get('items', []) if isinstance(apis2, dict) else []
        residue = [x['name'] for x in items2 if '接线测试_INT1486' in (x.get('name') or '')]
        report['residue'] = residue
        chk('数据卫生：无 INT1486 残留 API', not residue, residue)
        st, h2 = F.api_req('GET', '/health', token, timeout=20)
        report['env']['health_end'] = h2
        with open(os.path.join(ART, 'rewalk_l_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'checks': len(report['checks']), 'residue': residue},
                                    ensure_ascii=False)[:1500])


if __name__ == '__main__':
    main()
