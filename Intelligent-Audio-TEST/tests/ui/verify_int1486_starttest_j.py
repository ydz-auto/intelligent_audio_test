# -*- coding: utf-8 -*-
"""INT-1486 补验（合入后复走）：F 脚本两处脚本侧缺口的正确走法。

C8 空筛选入口拦截：必须先进第 2/3 步（F 脚本漏 next_step，停在第 1 步）。
D4~D7 api-edit / api-health：API 卡片异步加载，需轮询等待（F 脚本立即查询，命中竞态）。

环境：前端 docker 15173（React，镜像 2026-10-23 15:26Z 含 INT-1528 f8a0bd61），后端 15000 真实库。
数据：只建「接线测试_INT1486_」前缀临时 API，run 末按 id 删除。
"""
import json, os, sys, time, traceback, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402  复用驱动/请求/断言辅助

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
API_NAME = '接线测试_INT1486_JAPI_' + SUFFIX
EMPTY_KEYWORD = 'ZZZ_NO_MATCH_INT1486'
report = {'checks': [], 'env': {}, 'apis': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def wait_api_card(d, name, timeout=40):
    """API 卡片异步加载，轮询 aria-label。"""
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
        return None
    card = card_of(d, cb)
    more = card.find_elements(F.By.CSS_SELECTOR, '[aria-label="更多操作"]')
    if not more:
        return None
    F.js_click(d, more[0]); time.sleep(1.2)
    mi = d.find_elements(F.By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
    if not mi:
        return None
    F.js_click(d, mi[0]); time.sleep(2.5)
    return card


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h1 = F.api_req('GET', '/health', token, timeout=20)
    report['env']['health_start'] = h1
    chk('env /health database=intelligent_audio_test',
        isinstance(h1, dict) and h1.get('database') == 'intelligent_audio_test', h1)

    d = F.make_driver(token)
    api_id = None
    try:
        # ============ C8 空筛选入口拦截（走到第 3 步再点开始测试） ============
        F.wait_step1(d)
        F.search_cases(d, EMPTY_KEYWORD)
        lines = F.summary_lines(d)
        print('C8 summary', lines)
        chk('C8a 空筛选汇总显示全部 0 条', any('全部 0 条' in ln for ln in lines), lines)
        F.next_step(d)
        dev = F.pick_device(d)
        chk('C8b 第 2 步选中设备 ' + F.DEVICE_NAME, dev)
        F.shot(d, 'J_filter_empty_step2_light.png')
        mark = F.log_mark(d)
        clicked = F.click_start(d)
        time.sleep(2)
        t = F.text(d)
        posts = [e for e in F.log_entries(d, mark, keys=('/tasks',)) if e['method'] == 'POST']
        msg = [ln for ln in t.splitlines() if '没有可用' in ln or '请调整筛选' in ln]
        chk('C8 空筛选入口拦截（无 POST /tasks + 提示调整筛选）',
            clicked and not posts and bool(msg), {'clicked': clicked, 'posts': len(posts), 'msg': msg})
        F.shot(d, 'J_filter_empty_blocked_light.png')

        # ============ api-edit / api-health 正走（含浅/深） ============
        st, hc = F.api_req('POST', '/api/v1/apis', token, {
            'name': API_NAME, 'description': 'INT-1486 复走临时', 'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'endpoints': [{'endpoint': 'https://example.test/int1486-j', 'name': None, 'max_process': 1,
                           'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                           'description': None}]})
        if isinstance(hc, dict):
            api_id = (hc.get('data') or {}).get('id') or hc.get('id')
        chk('D3 临时 API 创建', st < 300 and api_id is not None, {'status': st, 'id': api_id})
        report['apis'].append({'id': api_id, 'name': API_NAME})

        F.wait_step1(d)
        card = open_edit(d, API_NAME)
        chk('D4 API 卡片出现且可打开编辑', card is not None)
        if card is not None:
            back = d.find_element(F.By.ID, 'api-name').get_attribute('value')
            urls = d.find_elements(F.By.CSS_SELECTOR, "input[aria-label='端点 URL']")
            back_url = urls[0].get_attribute('value') if urls else None
            chk('D5 api-edit 回填名称', back == API_NAME, repr(back))
            chk('D6 api-edit 回填端点 URL', back_url == 'https://example.test/int1486-j', repr(back_url))
            F.shot(d, 'J_api_edit_light.png')
            F.close_dialog(d)

        hb = [e for e in d.find_elements(F.By.CSS_SELECTOR, f'[aria-label="连接测试 {API_NAME}"]') if e.is_displayed()]
        chk('D4b 健康检查入口出现', bool(hb))
        if hb:
            mark = F.log_mark(d)
            F.js_click(d, hb[0]); time.sleep(0.8)
            print('HEALTH testing', F.dialog_text(d)[:200].replace('\n', ' | '))
            try:
                F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
            except Exception:
                pass
            ht = F.dialog_text(d)
            chk('D7 api-health 结果态渲染（重新测试钮）', '重新测试' in ht, ht[:300])
            F.shot(d, 'J_api_health_light.png')
            F.log_show(d, mark, keys=('/apis/', 'health'))
            F.close_dialog(d)

        # ---- 深色：api-edit + api-health ----
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        F.wait_step1(d)
        time.sleep(2)
        chk('D8 深色主题生效',
            d.execute_script("return document.documentElement.classList.contains('dark')") is True,
            d.execute_script("return document.documentElement.className"))
        card = open_edit(d, API_NAME)
        chk('D9 api-edit 深色打开', card is not None)
        if card is not None:
            F.shot(d, 'J_api_edit_dark.png')
            F.close_dialog(d)
        hb = [e for e in d.find_elements(F.By.CSS_SELECTOR, f'[aria-label="连接测试 {API_NAME}"]') if e.is_displayed()]
        if hb:
            F.js_click(d, hb[0])
            try:
                F.WebDriverWait(d, 90).until(lambda x: '重新测试' in F.dialog_text(x) or not F.dialogs(x))
            except Exception:
                pass
            time.sleep(1)
            F.shot(d, 'J_api_health_dark.png')
            chk('D10 api-health 深色结果态', '重新测试' in F.dialog_text(d), F.dialog_text(d)[:200])
            F.close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'J_error.png')
        except Exception:
            pass
    finally:
        d.quit()
        if api_id:
            print('CLEAN api', api_id, F.api_req('DELETE', f'/api/v1/apis/{api_id}', token))
        st, apis = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items = (apis.get('data', apis) or {}).get('items', []) if isinstance(apis, dict) else []
        residue = [x for x in items if '接线测试_INT1486' in (x.get('name') or '')]
        report['residue'] = residue
        chk('数据卫生：无 INT1486 残留 API', not residue, [x.get('name') for x in residue])
        st, h2 = F.api_req('GET', '/health', token, timeout=20)
        report['env']['health_end'] = h2
        with open(os.path.join(ART, 'rewalk_j_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'checks': len(report['checks']), 'residue': report.get('residue')},
                                    ensure_ascii=False)[:1500])


if __name__ == '__main__':
    main()
