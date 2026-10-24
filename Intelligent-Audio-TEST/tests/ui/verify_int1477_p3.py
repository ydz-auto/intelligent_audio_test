# -*- coding: utf-8 -*-
"""INT-1477 P3 复现：组头「批量修改」(组未展开) 提交 ids:[] / 删除筛选中的分组后 filters.groupId 未清。

docker 真实栈：前端 15173 / 网关 15000 / 主库 intelligent_audio_test。
自建「接线测试_INT1477P3」前缀夹具，脚本末尾清理。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)

TAG = time.strftime('%m%d%H%M')
GROUP = '接线测试_INT1477P3组' + TAG
GROUP2 = '接线测试_INT1477P3目标组' + TAG
NAMES = ['接线测试_INT1477P3_' + TAG + '_A', '接线测试_INT1477P3_' + TAG + '_B']
STAGES = [s for s in (os.environ.get('STAGES') or 'p32,p31').split(',') if s]
OUT = {'env': {}, 'p3_2': {}, 'p3_1': {}, 'cleanup': {}}


def log(*a):
    print(*a, flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(90)
    return d


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def find(d, t, tag='*', exact=True, timeout=0):
    end = time.time() + timeout
    while True:
        cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
        for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
            if e.is_displayed():
                return e
        if time.time() > end:
            return None
        time.sleep(0.4)


def click_text(d, t, tag='*', exact=True, timeout=20):
    e = find(d, t, tag, exact, timeout)
    if not e:
        raise AssertionError('未找到: ' + t)
    jsclick(d, e)
    return e


def shot(d, name):
    d.save_screenshot(os.path.join(ART, 'p3_' + name + '.png'))
    log('  shot: p3_' + name)


def clear_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def calls(d):
    reqs = {}
    try:
        logs = d.get_log('performance')
    except Exception:
        return []
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        p = m.get('params', {})
        if m.get('method') == 'Network.requestWillBeSent':
            r = p['request']
            if '/api/' not in r['url']:
                continue
            reqs[p['requestId']] = {'method': r['method'],
                                    'url': r['url'].split(BASE)[-1],
                                    'status': None,
                                    'post': (r.get('postData') or '')[:800]}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def api(d, method, path, body=None):
    js = """
    var cb = arguments[arguments.length-1];
    var m = arguments[0], u = arguments[1], b = arguments[2];
    var opt = {method: m, headers: {'Accept':'application/json'}};
    if (b !== null) { opt.headers['Content-Type']='application/json'; opt.body = b; }
    fetch(u, opt).then(r => r.text().then(t => cb({status:r.status, body:t})))
      .catch(e => cb({status:-1, body:String(e)}));
    """
    d.set_script_timeout(60)
    r = d.execute_async_script(js, method, BASE + path,
                               None if body is None else json.dumps(body))
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


def wait_page(d, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if '用例管理' in d.find_element(By.TAG_NAME, 'body').text:
                time.sleep(1.5)
                return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError('用例页未就绪')


def ensure_group_visible(d, gname, timeout=60):
    """滚动加载更多直到找到分组名（分组卡默认收起）。"""
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']"):
            if e.is_displayed():
                return e
        more = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if more:
            jsclick(d, more[0])
            time.sleep(1.5)
            continue
        time.sleep(0.8)
    return None


def group_card(d, gname):
    """分组卡容器：包含分组名 span 与 `<name> 批量修改` 按钮的最近祖先。"""
    els = d.find_elements(
        By.XPATH,
        f"//span[normalize-space(.)='{gname}']/ancestor::div[.//button[@aria-label='{gname} 批量修改']][1]")
    for e in els:
        if e.is_displayed():
            return e
    return None


def pick_select(d, trigger_text, option_text, timeout=20):
    end = time.time() + timeout
    trig = None
    while time.time() < end:
        for b in d.find_elements(By.XPATH, f"//button[@role='combobox'][contains(normalize-space(.),'{trigger_text}')]"):
            if b.is_displayed():
                trig = b
                break
        if trig:
            break
        time.sleep(0.4)
    if not trig:
        raise AssertionError('未找到下拉: ' + trigger_text)
    jsclick(d, trig)
    time.sleep(1.0)
    end = time.time() + 10
    while time.time() < end:
        for o in d.find_elements(By.XPATH, f"//*[@role='option'][normalize-space(.)='{option_text}']"):
            if o.is_displayed():
                jsclick(d, o)
                time.sleep(0.8)
                return
        time.sleep(0.4)
    raise AssertionError('未找到选项: ' + option_text)


def list_cases(d, name):
    import urllib.parse
    r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&keyword=' + urllib.parse.quote(name))
    data = (r.get('json') or {}).get('data') or {}
    items = data.get('items') if isinstance(data, dict) else data
    return [x for x in (items or []) if x.get('name') == name], r


def get_case(d, cid):
    r = api(d, 'GET', '/api/v1/testcases/' + str(cid))
    return (r.get('json') or {}).get('data'), r


def create_case(d, name, new_group=None, group=None):
    click_text(d, '新增用例', 'button')
    end = time.time() + 25
    while time.time() < end:
        dl = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
              if e.is_displayed() and '用例名称' in (e.text or '')]
        if dl:
            break
        time.sleep(0.4)
    time.sleep(1.2)
    el = d.find_element(By.ID, 'case-name')
    jsclick(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(name)
    time.sleep(0.4)
    if new_group:
        pick_select(d, '请选择分组', '+ 新建分组')
        inp = d.find_element(By.CSS_SELECTOR, "input[aria-label='新分组名称']")
        jsclick(d, inp)
        inp.send_keys(new_group)
        time.sleep(0.5)
    elif group:
        pick_select(d, '请选择分组', group)
    clear_log(d)
    click_text(d, '保存', 'button')
    time.sleep(3.5)
    cs = calls(d)
    log('  create', name, '->', ' ; '.join(f"{c['method']} {c['url'].split('?')[0]} {c['status']}" for c in cs))
    return cs


def list_cases_deleted(d, name):
    import urllib.parse
    r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&only_deleted=true&keyword=' +
            urllib.parse.quote(name))
    data = (r.get('json') or {}).get('data') or {}
    items = data.get('items') if isinstance(data, dict) else data
    return [x for x in (items or []) if x.get('name') == name]


def cleanup(d):
    out = {}
    for n in NAMES + ['接线测试_INT1477P3_C']:
        try:
            found = list_cases(d, n)[0] + list_cases_deleted(d, n)
        except Exception as e:
            out['list:' + n] = {'error': repr(e)}
            continue
        for it in found:
            cid = it.get('id')
            try:
                r1 = api(d, 'DELETE', '/api/v1/testcases/' + str(cid))
                r2 = api(d, 'DELETE', '/api/v1/testcases/' + str(cid) + '/purge')
                out[n + ':' + str(cid)] = {'delete': r1['status'], 'purge': r2['status']}
            except Exception as e:
                out[n + ':' + str(cid)] = {'error': repr(e)}
    for gname in (GROUP, GROUP2):
        r = api(d, 'GET', '/api/v1/groups?page=1&per_page=200')
        data = (r.get('json') or {}).get('data') or {}
        items = data.get('items') if isinstance(data, dict) else data
        for g in items or []:
            if g.get('name') == gname:
                dg = api(d, 'DELETE', '/api/v1/groups/%s?cascade=true' % g.get('id'))
                out['group:' + gname] = {'id': g.get('id'), 'delete': dg['status'],
                                         'body': (dg.get('body') or '')[:200]}
    return out


def p3_2(d):
    """组未展开时组头「批量修改」→ 调整分组：ids: [] 仍提交成功。"""
    rec = {}
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    wait_page(d)
    ensure_group_visible(d, GROUP)
    d.execute_script("window.scrollTo(0,0);")
    time.sleep(0.5)
    card = group_card(d, GROUP)
    if not card:
        raise AssertionError('未找到分组卡 ' + GROUP)
    # 确认当前为收起态：组内用例卡不可见
    rec['collapsed'] = not any(e.is_displayed() for e in d.find_elements(
        By.XPATH, f"//*[normalize-space(.)='{NAMES[0]}']"))
    rec['group_header_text'] = (card.text or '')[:300]
    shot(d, 'group_collapsed')

    trig = [b for b in card.find_elements(By.XPATH, ".//button[@aria-label='%s 批量修改']" % GROUP) if b.is_displayed()]
    if not trig:
        raise AssertionError('未找到批量修改按钮')
    jsclick(d, trig[0])
    time.sleep(1.2)
    shot(d, 'group_batch_menu')
    # 点「调整分组」
    item = None
    for e in d.find_elements(By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.),'调整分组')]"):
        if e.is_displayed():
            item = e
            break
    if not item:
        item = click_text(d, '调整分组', '*', True, 10)
    else:
        jsclick(d, item)
    time.sleep(1.5)
    dlg = None
    end = time.time() + 15
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog']"):
            if e.is_displayed() and '批量调整分组' in (e.text or ''):
                dlg = e
                break
        if dlg:
            break
        time.sleep(0.4)
    if not dlg:
        raise AssertionError('批量调整分组弹窗未出现')
    rec['dialog_text'] = (dlg.text or '')[:400]
    shot(d, 'batch_adjust_group_open')
    pick_select(d, '请选择分组', GROUP2)
    clear_log(d)
    btn = [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='确定']") if b.is_displayed()]
    if not btn:
        raise AssertionError('未找到确定')
    jsclick(d, btn[0])
    t0 = time.time()
    closed_at = None
    while time.time() - t0 < 130:
        time.sleep(2.0)
        still = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']")
                 if e.is_displayed() and '批量调整分组' in (e.text or '')]
        if not still:
            closed_at = round(time.time() - t0, 1)
            break
    cs = calls(d)
    rec['submit_elapsed_s'] = closed_at if closed_at is not None else 'timeout>130s'
    rec['calls'] = cs
    shot(d, 'batch_adjust_group_submitted')
    batch = [c for c in cs if '/testcases/batch' in c['url']]
    rec['batch_calls'] = batch
    rec['toast'] = [e.text for e in d.find_elements(By.XPATH, "//*[@data-sonner-toast]")
                    if e.is_displayed()]
    return rec


def p3_1(d):
    """按分组筛选后删除该分组：facet 回落「全部」，列表仍按已删分组过滤 → 空态。"""
    rec = {}
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    wait_page(d)
    # 等分组列表真正落地（刷新瞬时空态：分组 facet 选项与分组卡同时来自 /groups）
    if not ensure_group_visible(d, GROUP, timeout=90):
        raise AssertionError('分组卡未加载: ' + GROUP)
    d.execute_script("window.scrollTo(0,0);")
    time.sleep(0.8)
    # 找到「分组」facet 触发器（按钮内含 span 分组）
    trig = None
    for b in d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='分组']]"):
        if b.is_displayed():
            trig = b
            break
    if not trig:
        raise AssertionError('未找到分组 facet')
    rec['facet_before'] = (trig.text or '').replace('\n', ' ')
    jsclick(d, trig)
    time.sleep(1.2)
    from selenium.webdriver.common.action_chains import ActionChains
    picked = False
    cands = []
    for attempt in range(3):
        cands = [e for e in d.find_elements(By.XPATH, f"//button[normalize-space(.)='{GROUP}']")
                 if e.is_displayed()]
        if not cands:
            time.sleep(1.0)
            continue
        opt = cands[-1]
        rec['opt_rect'] = {k: opt.rect.get(k) for k in ('x', 'y', 'width', 'height')}
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", opt)
        time.sleep(0.6)
        try:
            ActionChains(d).move_to_element(opt).click().perform()
        except Exception:
            jsclick(d, opt)
        time.sleep(2.0)
        now = ''
        for b in d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='分组']]"):
            if b.is_displayed():
                now = (b.text or '').replace('\n', ' ')
                break
        rec.setdefault('facet_text_after_clicks', []).append(now)
        if GROUP in now:
            picked = True
            rec['facet_pick_attempts'] = attempt + 1
            break
        time.sleep(0.5)
        try:
            jsclick(d, trig)
        except Exception:
            pass
        time.sleep(1.0)
    rec['facet_picked'] = picked
    rec['facet_candidates'] = len(cands)
    if not picked:
        raise AssertionError('分组 facet 选中未生效: ' + GROUP)
    # 等筛选后的列表落地（应只剩本分组一张卡）
    end = time.time() + 40
    while time.time() < end:
        time.sleep(2.0)
        cards = [e for e in d.find_elements(By.XPATH, "//button[contains(@aria-label,' 批量修改')]")
                 if e.is_displayed()]
        if len(cards) == 1 and group_card(d, GROUP):
            break
    rec['facet_after_pick'] = (trig.text or '').replace('\n', ' ')
    rec['group_card_after_pick'] = bool(group_card(d, GROUP))
    rec['card_count_after_pick'] = len([e for e in d.find_elements(
        By.XPATH, "//button[contains(@aria-label,' 批量修改')]") if e.is_displayed()])
    shot(d, 'filtered_by_group')

    card = group_card(d, GROUP)
    if not card:
        raise AssertionError('筛选后未找到分组卡')
    delbtn = [b for b in card.find_elements(By.XPATH, ".//button[normalize-space(.)='删除']") if b.is_displayed()]
    if not delbtn:
        raise AssertionError('未找到组头删除')
    jsclick(d, delbtn[0])
    time.sleep(2.0)
    # ConfirmDialog 动画就绪后再点 destructive「删除」
    clicked = False
    end = time.time() + 15
    while time.time() < end and not clicked:
        for e in d.find_elements(By.XPATH, "//*[@role='alertdialog' or @role='dialog']"):
            if not e.is_displayed():
                continue
            if '删除分组' not in (e.text or ''):
                continue
            btns = [b for b in e.find_elements(By.XPATH, ".//button[normalize-space(.)='删除']")
                    if b.is_displayed() and b.is_enabled()]
            if btns:
                rec['confirm_text'] = (e.text or '')[:300]
                jsclick(d, btns[0])
                clicked = True
                break
        if not clicked:
            time.sleep(0.5)
    if not clicked:
        raise AssertionError('删除分组确认框未就绪')
    clear_log(d)
    t0 = time.time()
    closed_at = None
    while time.time() - t0 < 130:
        time.sleep(2.0)
        still = [e for e in d.find_elements(By.XPATH, "//*[@role='alertdialog' or @role='dialog']")
                 if e.is_displayed() and '删除分组' in (e.text or '')]
        if not still:
            closed_at = round(time.time() - t0, 1)
            break
    rec['delete_elapsed_s'] = closed_at if closed_at is not None else 'timeout>130s'
    time.sleep(3.0)
    cs = calls(d)
    rec['calls_after_delete'] = cs
    trig2 = None
    for b in d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='分组']]"):
        if b.is_displayed():
            trig2 = b
            break
    rec['facet_after_delete'] = ((trig2 or trig).text or '').replace('\n', ' ')
    body_txt = d.find_element(By.TAG_NAME, 'body').text
    rec['body_after_delete'] = body_txt[:1500]
    rec['cases_visible_after_delete'] = [n for n in NAMES if n in body_txt]
    shot(d, 'after_group_delete_filtered')
    rec['list_calls_after_delete'] = [c for c in cs
                                      if '/testcases?' in c['url'] and c['method'] == 'GET']
    return rec


def main():
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group')
        wait_page(d)
        r = api(d, 'GET', '/api/v1/auth/mode')
        OUT['env'] = {'base': BASE, 'auth_mode': r.get('json')}
        OUT['cleanup_before'] = cleanup(d)
        log('cleanup_before', OUT['cleanup_before'])

        # 目标分组（批量调整分组的目标）
        g2 = api(d, 'POST', '/api/v1/groups',
                 {'name': GROUP2, 'description': '', 'algorithm_type': ''})
        OUT['group2_create'] = {'status': g2['status'], 'body': (g2.get('body') or '')[:300]}

        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_page(d)
        OUT['create_a'] = create_case(d, NAMES[0], new_group=GROUP)
        # 重建页面，确保抽屉里分组下拉拿到刚建的分组（新建后不重载时下拉选项可能仍为旧快照）
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_page(d)
        time.sleep(3)
        OUT['create_b'] = create_case(d, NAMES[1], group=GROUP)
        got = {}
        for n in NAMES:
            items, _ = list_cases(d, n)
            got[n] = items[0] if items else None
        OUT['created'] = got
        log('created', json.dumps(got, ensure_ascii=False)[:600])
        if any(v is None for v in got.values()):
            raise AssertionError('夹具创建失败')

        if 'p32' in STAGES:
            try:
                OUT['p3_2'] = p3_2(d)
            except Exception as e:
                OUT['p3_2'] = {'error': repr(e)}
                log('P3-2 ERROR', repr(e))
                try:
                    shot(d, 'p3_2_error')
                except Exception:
                    pass

            # P3-2 回读：用例分组未被改动（ids:[] 不应生效）
            rb = {}
            for n in NAMES:
                cid = got[n].get('id')
                data, _ = get_case(d, cid)
                d0 = data.get('data') if isinstance(data, dict) and 'data' in data else data
                if isinstance(d0, dict):
                    rb[n] = {k: d0.get(k) for k in ('id', 'name', 'group_id', 'groupId')}
            OUT['p3_2_readback'] = rb

        if 'p31' in STAGES:
            try:
                OUT['p3_1'] = p3_1(d)
            except Exception as e:
                OUT['p3_1'] = {'error': repr(e)}
                log('P3-1 ERROR', repr(e))
                try:
                    shot(d, 'p3_1_error')
                except Exception:
                    pass
    finally:
        try:
            OUT['cleanup_after'] = cleanup(d)
            log('cleanup_after', OUT['cleanup_after'])
        except Exception as e:
            OUT['cleanup_after'] = {'error': repr(e)}
        json.dump(OUT, open(os.path.join(ART, 'p3_evidence.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    log('DONE')


if __name__ == '__main__':
    main()
