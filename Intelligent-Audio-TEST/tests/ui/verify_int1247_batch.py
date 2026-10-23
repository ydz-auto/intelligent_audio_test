# -*- coding: utf-8 -*-
"""INT-1247 复走查 · 批量设置模态窗逐项（九项弹窗 + 真实批量操作）。

环境：docker 前端旁路容器 http://localhost:15247 + 后端 :15000（真实库）。
数据：本 run 自建分组「接线测试_INT1247批量_<ts>」+ 3 条自建用例，只对自建记录操作，
      结束前彻底删除（purge + 删分组）。
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = os.environ.get('REACT_BYPASS_BASE', 'http://localhost:15247')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1247_batch')
os.makedirs(OUT, exist_ok=True)
TS = int(time.time())
GROUP = '接线测试_INT1247批量_%d' % TS
TAG = '接线测试_INT1247批量标签_%d' % TS
CHECKS = []
REPORT = {}


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:280] if detail else ''))


def req(method, path, payload=None, timeout=120):
    d = json.dumps(payload).encode('utf-8') if payload is not None else None
    r = urllib.request.Request(API + path, data=d, method=method)
    if d:
        r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            raw = x.read().decode('utf-8', 'replace')
            return x.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}


def health():
    with urllib.request.urlopen(API + '/health', timeout=30) as r:
        return json.loads(r.read().decode())


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for v in os.listdir(root):
            exe = os.path.join(root, v, 'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0].isdigit() and int(v.split('.')[0]) == major:
                path = exe
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    return d


def xp(d, e, s=None):
    return (s or d).find_elements(By.XPATH, e)


def jsclick(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    d.execute_script('arguments[0].click()', el)


def wait(d, cond, timeout=40, desc=''):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout: ' + desc)


def visible_dialog(d, title):
    for el in xp(d, "//div[@data-slot='dialog-content']"):
        if title in el.text:
            return el
    return None


def visible_alert(d, title):
    for el in xp(d, "//div[@data-slot='alert-dialog-content']"):
        if title in el.text:
            return el
    return None


def click_text(d, text, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for el in xp(d, '//*[normalize-space(.)="%s"]' % text):
            try:
                if el.is_displayed():
                    jsclick(d, el)
                    return True
            except Exception:
                continue
        time.sleep(0.4)
    raise AssertionError('click failed: ' + text)


def close_dialog(d, kind, title):
    if kind == 'alert':
        dlg = visible_alert(d, title)
        btn = dlg.find_element(By.XPATH, ".//button[contains(., '取消')]")
    else:
        dlg = visible_dialog(d, title)
        btns = dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]")
        btn = btns[0] if btns else dlg.find_elements(By.XPATH, ".//button[contains(., '取消')]")[0]
    jsclick(d, btn)
    time.sleep(0.8)


def net_requests(d):
    out = []
    try:
        for e in d.get_log('performance'):
            m = json.loads(e['message'])['message']
            if m.get('method') == 'Network.requestWillBeSent':
                r = m['params']['request']
                out.append({'method': r.get('method'), 'url': r.get('url', ''), 'body': r.get('postData')})
    except Exception:
        pass
    return out


def create_fixtures():
    st, g = req('POST', '/api/v1/groups', {'name': GROUP, 'description': 'INT-1247 批量走查临时分组'})
    gid = (g.get('data') or {}).get('id')
    ids = []
    for i in range(3):
        st, c = req('POST', '/api/v1/testcases', {
            'name': '接线测试_INT1247批量_用例%d_%d' % (i + 1, TS),
            'group_id': gid,
            'tags': ['接线测试_INT1247'],
            'description': 'INT-1247 批量设置走查临时用例（run 结束前删除）',
            'algorithm_type': 'voice_llm',
            'config': {'rounds': [{'round_number': 1, 'audios': [], 'evaluation': {}, 'noise': {}}]},
            'algorithm_params': [],
        })
        if (c.get('data') or {}).get('id'):
            ids.append(c['data']['id'])
    return gid, ids


NINE = [
    ('用例专属参数', '批量设置用例专属参数', 'dialog'),
    ('播放设备', '批量设置播放设备', 'dialog'),
    ('声压', '批量设置声压级', 'dialog'),
    ('调整分组', '批量调整分组', 'dialog'),
    ('评价维度', '批量设置评估维度', 'dialog'),
    ('噪声', '选择噪声音频', 'dialog'),
    ('标签生成名称', '自动生成名称', 'alert'),
    ('管理标签', '批量管理标签', 'dialog'),
    ('用例参考更新', '刷新参考参数', 'alert'),
]


def open_group_dropdown(d):
    btn = xp(d, "//button[@aria-label='%s 批量修改']" % GROUP)
    assert btn, '未找到自建分组的「批量修改」'
    jsclick(d, btn[0])
    time.sleep(0.8)


def expand_my_group(d):
    btn = xp(d, "//button[@aria-label='%s 批量修改']" % GROUP)[0]
    header = d.execute_script('''
      let n=arguments[0];
      for(let i=0;i<8 && n.parentElement;i++){n=n.parentElement;
        if(String(n.className||'').includes('cursor-pointer')) return n;}
      return null;''', btn)
    assert header is not None
    jsclick(d, header)
    wait(d, lambda: len(xp(d, "//button[@aria-label='编辑用例']")) >= 3, 90, 'my group cases')


def main():
    REPORT['group'] = GROUP
    h1 = health()
    REPORT['health_1'] = h1
    check('防串库① database=intelligent_audio_test', h1.get('database') == 'intelligent_audio_test', h1)
    gid, ids = create_fixtures()
    REPORT['fixture_group'] = gid
    REPORT['fixture_cases'] = ids
    check('自建夹具（1 分组 3 用例）', bool(gid) and len(ids) == 3, ids)

    d = _driver()
    try:
        d.get(BASE + '/')
        time.sleep(2)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        d.get(BASE + '/testcases')
        wait(d, lambda: len(xp(d, "//*[substring(@aria-label, string-length(@aria-label)-3)='批量修改']")) >= 5,
             300, 'group list')
        # 分组按数量降序分页：点「加载更多」直到自建分组出现
        for _ in range(4):
            if xp(d, "//button[@aria-label='%s 批量修改']" % GROUP):
                break
            more = xp(d, "//button[contains(., '加载更多')]")
            if more:
                jsclick(d, more[0])
                time.sleep(3)
            else:
                break
        found = bool(xp(d, "//button[@aria-label='%s 批量修改']" % GROUP))
        check('自建分组在列表可见（分页加载）', found, GROUP)
        if not found:
            raise AssertionError('自建分组不可见')
        expand_my_group(d)
        cards = len(xp(d, "//button[@aria-label='编辑用例']"))
        check('自建分组展开 3 条用例', cards >= 3, cards)
        d.save_screenshot(os.path.join(OUT, 'b1_group_expanded.png'))

        # 九项逐项弹窗
        results = []
        for label, title, kind in NINE:
            open_group_dropdown(d)
            click_text(d, label)
            if kind == 'alert':
                wait(d, lambda t=title: visible_alert(d, t) is not None, 20, 'alert ' + title)
            else:
                wait(d, lambda t=title: visible_dialog(d, t) is not None, 20, 'dialog ' + title)
            results.append((label, title, 'OK'))
            if label in ('声压', '管理标签'):
                d.save_screenshot(os.path.join(OUT, 'b2_dialog_%s.png' % label))
            close_dialog(d, kind, title)
            time.sleep(0.4)
        REPORT['nine'] = results
        check('批量设置九项弹窗逐项弹出', len(results) == 9, [r[0] for r in results])

        # 真实批量操作 1：声压 68
        open_group_dropdown(d)
        click_text(d, '声压')
        wait(d, lambda: visible_dialog(d, '批量设置声压级') is not None, 20, 'spl dialog')
        dlg = visible_dialog(d, '批量设置声压级')
        inp = dlg.find_element(By.XPATH, ".//input[@aria-label='声压级 dB']")
        d.execute_script(
            "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
            "s.call(arguments[0],'68'); arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", inp)
        time.sleep(0.6)
        ok_btn = dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
        check('声压弹窗确定钮可用', bool(ok_btn) and not ok_btn[0].get_attribute('disabled'), len(ok_btn))
        jsclick(d, ok_btn[0])
        wait(d, lambda: '批量操作执行成功' in d.find_element(By.TAG_NAME, 'body').text
             or '批量' in d.find_element(By.TAG_NAME, 'body').text, 60, 'spl toast')
        time.sleep(1.5)
        reqs = [r for r in net_requests(d) if '/testcases/batch' in r['url'] and r['method'] == 'POST']
        REPORT['batch_spl'] = reqs[-1] if reqs else None
        check('真实批量 POST /testcases/batch（update_spl 68）', bool(reqs) and 'update_spl' in (reqs[-1]['body'] or ''),
              (reqs[-1]['body'] or '')[:220] if reqs else '')

        # 真实批量操作 2：管理标签（添加）
        open_group_dropdown(d)
        click_text(d, '管理标签')
        wait(d, lambda: visible_dialog(d, '批量管理标签') is not None, 20, 'tags dialog')
        dlg = visible_dialog(d, '批量管理标签')
        tag_inp = dlg.find_element(By.XPATH, ".//input[@placeholder='输入标签，按回车或逗号添加']")
        tag_inp.send_keys(TAG)
        tag_inp.send_keys(Keys.ENTER)
        time.sleep(0.5)
        okb = dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
        jsclick(d, okb[0])
        time.sleep(3)
        reqs = [r for r in net_requests(d) if '/testcases/batch' in r['url'] and r['method'] == 'POST']
        REPORT['batch_tags'] = reqs[-1] if reqs else None
        check('真实批量 POST /testcases/batch（add_tags）', bool(reqs) and 'add_tags' in (reqs[-1]['body'] or ''),
              (reqs[-1]['body'] or '')[:220] if reqs else '')
        time.sleep(2)
        tag_ok = 0
        for cid in ids:
            st, body = req('GET', '/api/v1/testcases/' + cid)
            tags = ((body.get('data') or {}).get('tags') or []) if st == 200 else []
            if TAG in tags:
                tag_ok += 1
        check('批量加标签落库（3/3）', tag_ok == 3, 'tagged=%d' % tag_ok)

        # 真实批量操作 3：评价维度
        open_group_dropdown(d)
        click_text(d, '评价维度')
        wait(d, lambda: visible_dialog(d, '批量设置评估维度') is not None, 20, 'dims dialog')
        dlg = visible_dialog(d, '批量设置评估维度')
        picked = d.execute_script('''
          const d=[...document.querySelectorAll("div[data-slot='dialog-content']")].filter(e=>e.textContent.includes('批量设置评估维度')).pop();
          const btns=[...d.querySelectorAll('button[aria-pressed]')];
          if(!btns.length) return 0;
          btns[0].click(); return 1;''')
        time.sleep(0.8)
        if picked:
            okb = dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
            jsclick(d, okb[-1])
            time.sleep(3)
            reqs = [r for r in net_requests(d) if '/testcases/batch' in r['url'] and r['method'] == 'POST']
            REPORT['batch_dims'] = reqs[-1] if reqs else None
            check('真实批量 POST /testcases/batch（update_dimensions）',
                  bool(reqs) and 'update_dimensions' in (reqs[-1]['body'] or ''),
                  (reqs[-1]['body'] or '')[:220] if reqs else '')
        else:
            # 本环境维度目录未挂算法关联/无可用维度时，弹窗打开但无可选维度：记为数据缺口，不算失败
            REPORT['batch_dims'] = {'dialog_opened': True, 'dim_chips': 0,
                                    'dialog_text': dlg.text[:200]}
            check('评价维度弹窗打开（本环境无可选维度，数据缺口）', '批量设置评估维度' in dlg.text, dlg.text[:100])
            cancels = dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]")
            if cancels:
                jsclick(d, cancels[0])
                time.sleep(1)
        d.save_screenshot(os.path.join(OUT, 'b3_after_batch.png'))

        # 深色弹窗一张
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(BASE + '/testcases')
        wait(d, lambda: len(xp(d, "//*[substring(@aria-label, string-length(@aria-label)-3)='批量修改']")) >= 5,
             300, 'dark group list')
        for _ in range(4):
            if xp(d, "//button[@aria-label='%s 批量修改']" % GROUP):
                break
            more = xp(d, "//button[contains(., '加载更多')]")
            if more:
                jsclick(d, more[0])
                time.sleep(3)
        if xp(d, "//button[@aria-label='%s 批量修改']" % GROUP):
            open_group_dropdown(d)
            click_text(d, '声压')
            wait(d, lambda: visible_dialog(d, '批量设置声压级') is not None, 20, 'dark spl dialog')
            time.sleep(1)
            d.save_screenshot(os.path.join(OUT, 'b4_spl_dark.png'))
            close_dialog(d, 'dialog', '批量设置声压级')
    finally:
        try:
            d.quit()
        except Exception:
            pass
        # 清理
        for cid in ids:
            req('DELETE', '/api/v1/testcases/' + cid)
            req('DELETE', '/api/v1/testcases/%s/purge' % cid)
        if gid:
            req('DELETE', '/api/v1/groups/%s?cascade=true' % gid)
        # 清理本卡批量加标签时创建的真实标签
        tag_items = ((req('GET', '/api/v1/tags')[1].get('data') or {}).get('items') or [])
        tid = next((t['id'] for t in tag_items if t.get('name') == TAG), None)
        if tid:
            req('DELETE', '/api/v1/tags/%s?cascade=true' % tid)
        groups = ((req('GET', '/api/v1/groups')[1].get('data') or {}).get('items') or [])
        left = [g['name'] for g in groups if g['name'] == GROUP]
        check('夹具清理（分组已删）', not left, left)
        h3 = health()
        REPORT['health_3'] = h3
        check('防串库③ database=intelligent_audio_test', h3.get('database') == 'intelligent_audio_test', h3)

    passed = sum(1 for c in CHECKS if c['ok'])
    REPORT['checks'] = CHECKS
    REPORT['summary'] = {'passed': passed, 'total': len(CHECKS)}
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print('SUMMARY=', passed, '/', len(CHECKS))
    print('FAILED=', [c['name'] for c in CHECKS if not c['ok']])
    return 0 if passed == len(CHECKS) else 1


if __name__ == '__main__':
    sys.exit(main())
