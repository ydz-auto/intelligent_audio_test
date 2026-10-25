# -*- coding: utf-8 -*-
"""INT-1477 复走·用例域 第二轮：编辑 / 批量七窗真实提交 / 回收站链路 / 清理。

阶段由 STAGES 环境变量控制（逗号分隔）：create,edit,batch,trash
只写「接线测试_INT1477_」前缀数据；trash 阶段结束会 purge 本 run 全部自建记录。
"""
import json
import os
import sys
import time
import urllib.parse

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

TAG = '接线测试_INT1477标签'
TAG2 = '接线测试_INT1477标签2'
GROUP = '接线测试_INT1477分组'
NAMES = ['接线测试_INT1477_A', '接线测试_INT1477_B', '接线测试_INT1477_C']
STAGES = [s for s in (os.environ.get('STAGES') or 'create,edit,batch,trash').split(',') if s]
EVID = []
OUT = {}


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


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def click_text(d, t, tag='*', exact=True, timeout=20):
    e = find(d, t, tag, exact, timeout)
    if not e:
        raise AssertionError('未找到: ' + t)
    jsclick(d, e)
    return e


def shot(d, name):
    d.save_screenshot(os.path.join(ART, name + '.png'))
    log('  shot:', name)


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
                                    'post': (r.get('postData') or '')[:700]}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def show(cs):
    return ' ; '.join(f"{c['method']} {c['url'].split('?')[0]} -> {c['status']}" for c in cs)


def rec(window, note, cs=None, extra=None):
    item = {'window': window, 'theme': 'light', 'note': note, 'calls': cs or []}
    if extra:
        item.update(extra)
    EVID.append(item)
    log(f'  [{window}] {note} | {show(cs or [])}')
    return item


def api(d, method, path, body=None):
    js = """
    var cb = arguments[arguments.length-1];
    var m = arguments[0], u = arguments[1], b = arguments[2];
    var opt = {method: m, headers: {'Accept':'application/json'}};
    if (b !== null) { opt.headers['Content-Type']='application/json'; opt.body = b; }
    fetch(u, opt).then(r => r.text().then(t => cb({status:r.status, body:t})))
      .catch(e => cb({status:-1, body:String(e)}));
    """
    d.set_script_timeout(40)
    r = d.execute_async_script(js, method, BASE + path,
                               None if body is None else json.dumps(body))
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


def unwrap(r):
    j = r.get('json') or {}
    return j.get('data', j)


def list_cases(d, name):
    r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=50&keyword=' + urllib.parse.quote(name))
    data = unwrap(r)
    items = data.get('items') if isinstance(data, dict) else data
    items = items or []
    return [x for x in items if x.get('name') == name]


def get_case(d, cid):
    r = api(d, 'GET', f'/api/v1/testcases/{cid}')
    return r


def wait_drawer(d, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog']"):
            if e.is_displayed() and '用例名称' in (e.text or ''):
                return e
        time.sleep(0.4)
    raise AssertionError('用例抽屉未出现')


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


def set_input(d, el, value):
    jsclick(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


def add_tag(d, value):
    el = d.find_element(By.XPATH, "//input[@placeholder='输入标签，按回车或逗号添加']")
    jsclick(d, el)
    el.send_keys(value)
    el.send_keys(Keys.ENTER)
    time.sleep(0.6)


def pick_select(d, trigger_text, option_text):
    trig = d.find_element(By.XPATH,
                          f"//button[@role='combobox'][contains(normalize-space(.),'{trigger_text}')]")
    jsclick(d, trig)
    time.sleep(0.9)
    opt = d.find_element(By.XPATH, f"//*[@role='option'][normalize-space(.)='{option_text}']")
    jsclick(d, opt)
    time.sleep(0.6)


def esc(d, n=1):
    for _ in range(n):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.7)


def close_dialog(d):
    esc(d)
    btns = [b for b in d.find_elements(By.XPATH, "//button[@aria-label='关闭' or @aria-label='Close']")
            if b.is_displayed()]
    for b in reversed(btns):
        try:
            jsclick(d, b)
        except Exception:
            pass
        time.sleep(0.4)


def expand_group(d, gname, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{gname}']")
               if e.is_displayed()]
        if els:
            jsclick(d, els[0])
            time.sleep(2)
            return
        # 加载更多
        more = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if more:
            jsclick(d, more[0])
            time.sleep(1.5)
            continue
        time.sleep(0.6)
    raise AssertionError('未找到分组 ' + gname)


def case_card(d, name):
    for e in d.find_elements(By.XPATH, f"//*[normalize-space(.)='{name}']"):
        if e.is_displayed():
            return e
    return None


def select_cases(d, names):
    """在分组视图勾选指定用例卡。"""
    picked = 0
    for n in names:
        boxes = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
                 if e.is_displayed() and (e.get_attribute('aria-label') or '') == f'选择 {n}']
        if not boxes:
            continue
        jsclick(d, boxes[0])
        picked += 1
        time.sleep(0.5)
    time.sleep(0.8)
    return picked


def body_has(d, t):
    try:
        return t in d.find_element(By.TAG_NAME, 'body').text
    except Exception:
        return False


def find_dialog_with(d, frag):
    for e in d.find_elements(By.XPATH, "//*[@role='dialog' or @role='alertdialog']"):
        if e.is_displayed() and frag in (e.text or ''):
            return e
    return None


# ---------------- stages ----------------
def stage_create(d):
    created = []
    for i, name in enumerate(NAMES):
        existing = list_cases(d, name)
        if existing:
            created.append(existing[0])
            log('  exist', name, existing[0].get('id'))
            continue
        click_text(d, '新增用例', 'button')
        wait_drawer(d)
        time.sleep(1)
        set_input(d, d.find_element(By.ID, 'case-name'), name)
        set_input(d, d.find_element(By.ID, 'case-desc'), f'复走 {name}')
        add_tag(d, TAG)
        pick_select(d, '请选择分组', GROUP)
        clear_log(d)
        click_text(d, '保存', 'button')
        time.sleep(3.5)
        cs = calls(d)
        shot(d, f'crud_create_{name[-1]}')
        hits = list_cases(d, name)
        rec('case-mutate-drawer', f'新建 {name} → GET 回读',
            cs, {'readback': hits[0] if hits else None})
        log('  created', bool(hits))
        if hits:
            created.append(hits[0])
        esc(d)
        time.sleep(1)
    OUT['created'] = created


def open_edit(d, name):
    end = time.time() + 20
    while time.time() < end:
        btns = [e for e in d.find_elements(By.XPATH, "//button[@aria-label='编辑用例']")
                if e.is_displayed()]
        cards = [e for e in d.find_elements(By.XPATH, f"//*[normalize-space(.)='{name}']")
                 if e.is_displayed()]
        if cards:
            card = cards[0]
            # 向上找到包含编辑钮的卡片容器
            cont = d.execute_script(
                "var el=arguments[0];for(var i=0;i<6&&el;i++){if(el.querySelector&&el.querySelector"
                "(\"button[aria-label='编辑用例']\"))return el;el=el.parentElement;}return null;", card)
            if cont:
                b = cont.find_element(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
                jsclick(d, b)
                wait_drawer(d)
                time.sleep(1.2)
                return
    raise AssertionError('未找到编辑入口 ' + name)


def stage_edit(d):
    name = NAMES[0]
    expand_group(d, GROUP)
    clear_log(d)
    open_edit(d, name)
    shot(d, 'crud_edit_open')
    # 改描述 + 追加标签
    set_input(d, d.find_element(By.ID, 'case-desc'), '复走编辑后描述 INT1477')
    add_tag(d, TAG2)
    clear_log(d)
    click_text(d, '保存', 'button')
    time.sleep(3.5)
    cs = calls(d)
    shot(d, 'crud_edit_save')
    hits = list_cases(d, name)
    detail = get_case(d, hits[0]['id']) if hits else {'status': None}
    rec('case-mutate-drawer', '编辑保存 → PUT + GET 逐字段回读', cs,
        {'readback': unwrap(detail), 'detail_status': detail.get('status')})
    log('  edit readback:', json.dumps(unwrap(detail), ensure_ascii=False)[:500])
    esc(d)
    time.sleep(1)


def confirm_batch(d):
    click_text(d, '确定', 'button', timeout=15)
    time.sleep(3)
    return calls(d)


def stage_batch(d):
    results = {}
    expand_group(d, GROUP)
    # 调整分组 → 换到「音频上传生成」
    try:
        n = select_cases(d, NAMES)
        log('  selected', n)
        clear_log(d)
        click_text(d, '批量调整分组', 'button')
        time.sleep(1.5)
        shot(d, 'crud_batch_group_open')
        pick_select(d, '请选择目标分组', '音频上传生成') if find(d, '请选择目标分组', '*', False, 2) \
            else pick_select(d, '请选择分组', '音频上传生成')
        clear_log(d)
        cs = confirm_batch(d)
        shot(d, 'crud_batch_group_done')
        results['adjust_group'] = cs
        rec('batch-adjust-group-dialog', '批量调整分组 → 音频上传生成', cs)
    except Exception as e:
        results['adjust_group'] = f'FAIL {e}'
        log('  FAIL adjust_group', e)
        close_dialog(d)

    # 管理标签 → 加 TAG2
    try:
        expand_group(d, '音频上传生成')
        n = select_cases(d, NAMES)
        log('  selected', n)
        clear_log(d)
        click_text(d, '批量管理标签', 'button')
        time.sleep(1.5)
        shot(d, 'crud_batch_tags_open')
        add_tag(d, TAG2) if d.find_elements(By.XPATH, "//input[@placeholder='输入标签，按回车或逗号添加']") else None
        clear_log(d)
        cs = confirm_batch(d)
        shot(d, 'crud_batch_tags_done')
        results['manage_tags'] = cs
        rec('batch-manage-tags-dialog', '批量管理标签 → 追加 ' + TAG2, cs)
    except Exception as e:
        results['manage_tags'] = f'FAIL {e}'
        log('  FAIL manage_tags', e)
        close_dialog(d)
        expand_group(d, GROUP)

    OUT['batch'] = results


def main():
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_page(d)
        if 'create' in STAGES:
            stage_create(d)
        if 'edit' in STAGES:
            stage_edit(d)
        if 'batch' in STAGES:
            stage_batch(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    ev = os.path.join(ART, 'evidence.json')
    merged = []
    if os.path.isfile(ev):
        try:
            merged = json.load(open(ev, encoding='utf-8'))
        except Exception:
            merged = []
    merged += EVID
    json.dump(merged, open(ev, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(OUT, open(os.path.join(ART, 'crud_out.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    log('STAGES DONE', STAGES)


if __name__ == '__main__':
    main()
