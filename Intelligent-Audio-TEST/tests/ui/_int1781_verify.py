# -*- coding: utf-8 -*-
"""INT-1781 验收：删除「正在筛选的分组」后 filters.groupId 是否清空。

靶子：docker 15000 网关（库 intelligent_audio_test）+ 本 run 用交付 diff 构建的 React 产物。
流程：
1. 页面内 fetch 造夹具：分组「接线测试_INT1781组_<ts>」+ 组内 1 条用例「接线测试_INT1781用例_<ts>」；
2. 分组 facet 选中该组 → 断言列表请求带 group_id=<id>、chip 显示组名；
3. 组头「删除」→ 确认框「删除分组」→「删除」→ DELETE /groups/{id}?cascade=true；
4. 断言（修复点）：chip 回落「分组 全部」、删除后**不再**出现带已删 group_id 的列表请求、
   页面不落「没有找到符合条件的测试用例」空态、其余分组卡正常渲染；
5. 浅色删除前 / 删除后 + 深色删除后截图 + Network 证据 JSON；
6. 清理夹具（cascade 已删则核对 404 / facet 无残留）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1781_BASE', 'http://127.0.0.1:15281')
DRIVER = os.environ.get(
    'CHROMEDRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
ART = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'artifacts',
    'int1781',
    os.environ.get('INT1781_TAG', 'run'),
)
TS = time.strftime('%H%M%S')
GROUP = '接线测试_INT1781组_%s' % TS
CASE = '接线测试_INT1781用例_%s' % TS

NET_PATCH = r"""
window.__net = [];
(function(){
  const oFetch = window.fetch;
  window.fetch = function(input, init){
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const method = ((init && init.method) || 'GET').toUpperCase();
    const t0 = Date.now();
    const p = oFetch.apply(this, arguments);
    return p.then(function(r){
      try { window.__net.push({u: url, m: method, s: r.status, t: t0}); } catch(e){}
      return r;
    }, function(e){
      try { window.__net.push({u: url, m: method, s: -1, t: t0}); } catch(e2){}
      throw e;
    });
  };
})();
"""

CLICK_JS = """
(function(sel){
  const el = document.querySelector(sel);
  if (!el) return 'NOT_FOUND';
  el.click();
  return 'CLICKED';
})(arguments[0])
"""


def log(msg):
    print(msg, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def api(drv, path, method='GET', body=None):
    script = """
    const cb = arguments[arguments.length - 1];
    const opts = {method: arguments[1] || 'GET', headers: {'Content-Type': 'application/json'}};
    if (arguments[2]) opts.body = arguments[2];
    fetch(arguments[0], opts)
      .then(async r => cb({status: r.status, body: await r.text()}))
      .catch(e => cb({status: -1, body: String(e)}));
    """
    res = drv.execute_async_script(script, path, method, json.dumps(body) if body else None)
    return res


def net(drv):
    try:
        return drv.execute_script('return window.__net || []')
    except Exception:
        return []


def wait_net(drv, pred, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        for e in net(drv):
            if pred(e):
                return e
        time.sleep(0.5)
    return None


def wait_text(drv, text, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            body = drv.find_element(By.TAG_NAME, 'body').text
        except Exception:
            body = ''
        if text in body:
            return True
        time.sleep(1)
    return False


def body_text(drv):
    try:
        return drv.find_element(By.TAG_NAME, 'body').text
    except Exception:
        return ''


def chip_value(drv):
    """分组 facet chip 的当前值文案（label=分组 / value=全部 或 组名）"""
    return drv.execute_script("""
    const btns = Array.from(document.querySelectorAll('button'));
    const el = btns.find(b => Array.from(b.querySelectorAll('span')).some(s => (s.textContent||'').trim() === '分组'));
    if (!el) return null;
    const spans = Array.from(el.querySelectorAll('span')).map(s => (s.textContent||'').trim()).filter(Boolean);
    return spans.join(' | ');
    """)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    return p


def build_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1600,1100')
    opts.add_argument('--lang=zh-CN')
    caps = {'browserName': 'chrome', 'goog:loggingPrefs': {'performance': 'ALL'}}
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    drv = webdriver.Chrome(service=Service(DRIVER), options=opts)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': NET_PATCH})
    drv.set_page_load_timeout(180)
    del caps
    return drv


def main():
    os.makedirs(ART, exist_ok=True)
    result = {'base': BASE, 'group': GROUP, 'case': CASE, 'checks': {}}
    drv = build_driver()
    try:
        drv.get(BASE + '/testcases')
        assert wait_text(drv, '用例', 180), '用例页未加载'
        time.sleep(3)

        # 1. 夹具
        r = api(drv, '/api/v1/groups', 'POST', {'name': GROUP, 'description': '', 'algorithm_type': ''})
        log('POST /groups -> %s %s' % (r['status'], r['body'][:200]))
        gid = json.loads(r['body'])['data']['id'] if r['status'] in (200, 201) else None
        if gid is None:
            gid = json.loads(r['body']).get('id')
        gid = str(gid)
        result['group_id'] = gid
        r2 = api(drv, '/api/v1/testcases', 'POST', {'name': CASE, 'group_id': gid, 'description': ''})
        log('POST /testcases -> %s %s' % (r2['status'], r2['body'][:200]))
        cid = None
        if r2['status'] in (200, 201):
            cid = str(json.loads(r2['body'])['data']['id'])
        result['case_id'] = cid
        assert cid, '夹具用例创建失败'
        result['checks']['fixture_created'] = {'group': GROUP, 'group_id': gid, 'case_id': cid}

        # 2. 重新加载，走 UI 分组筛选
        drv.get(BASE + '/testcases')
        assert wait_text(drv, '用例', 180), '用例页未加载'
        WebDriverWait(drv, 120).until(
            EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space(.)='分组']]"))
        )
        js_click(drv, drv.find_element(By.XPATH, "//button[.//span[normalize-space(.)='分组']]"))
        time.sleep(1)
        opt = WebDriverWait(drv, 60).until(
            EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='%s']" % GROUP))
        )
        js_click(drv, opt)
        log('已选中分组 facet: %s' % GROUP)

        e = wait_net(drv, lambda x: x['m'] == 'GET' and '/testcases?' in x['u'] and gid in x['u'], 120)
        assert e is not None, '筛选后未见带 group_id 的列表请求'
        result['checks']['filter_request'] = {'url': e['u'], 'status': e['s']}
        time.sleep(6)
        chip_before = chip_value(drv)
        body_before = body_text(drv)
        result['checks']['before_delete'] = {
            'chip': chip_before,
            'has_empty_state': '没有找到符合条件的测试用例' in body_before,
            'saw_group_name': GROUP in body_before,
        }
        shot(drv, 'p1_filtered_light')

        # 3. 组头删除
        btn = WebDriverWait(drv, 60).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='删除']"))
        )
        js_click(drv, btn)
        dlg = WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[role='alertdialog'],[role='dialog']"))
        )
        time.sleep(1.2)
        dlg_text = dlg.text
        log('确认框: %s' % dlg_text.replace('\n', ' / '))
        confirm = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']")
        js_click(drv, confirm)

        de = wait_net(drv, lambda x: x['m'] == 'DELETE' and '/groups/' in x['u'], 120)
        assert de is not None, '未发出 DELETE /groups'
        del_t = de['t']
        result['checks']['delete_request'] = {'url': de['u'], 'status': de['s'], 't': del_t}
        since_delete = None
        end = time.time() + 120
        while time.time() < end:
            since_delete = [x for x in net(drv) if x['t'] > del_t and x['m'] == 'GET' and '/testcases?' in x['u']]
            if since_delete:
                break
            time.sleep(0.5)
        time.sleep(4)

        after = [x for x in net(drv) if x['t'] > del_t]
        list_after = [x for x in after if x['m'] == 'GET' and '/testcases?' in x['u']]
        with_gid_after = [x for x in list_after if gid in x['u']]
        chip_after = chip_value(drv)
        body_after = body_text(drv)
        group_delete_buttons = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
        shot(drv, 'p2_after_delete_light')
        result['checks']['after_delete'] = {
            'chip': chip_after,
            'list_requests_after': [x['u'] for x in list_after],
            'list_requests_with_deleted_group_id': [x['u'] for x in with_gid_after],
            'has_empty_state': '没有找到符合条件的测试用例' in body_after,
            'group_name_visible': GROUP in body_after,
            'group_cards_with_delete_button': len(group_delete_buttons),
            'toast_or_success': '删除分组成功' in body_after,
        }

        # 4. 深色（同页删除后状态；筛选已清，正常列表）
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        drv.get(BASE + '/testcases')
        assert wait_text(drv, '用例', 180), '深色重载未加载'
        time.sleep(8)
        shot(drv, 'p3_after_delete_dark')
        result['checks']['dark_reload'] = {
            'theme': drv.execute_script("return localStorage.getItem('iatp:theme:v1:mode')"),
            'has_empty_state': '没有找到符合条件的测试用例' in body_text(drv),
        }

        # 5. 夹具清理核对
        rg = api(drv, '/api/v1/groups?page=1&per_page=200')
        leaked = GROUP in (rg['body'] or '')
        rc = api(drv, '/api/v1/testcases/%s' % cid)
        if leaked or rc['status'] == 200:
            api(drv, '/api/v1/groups/%s?cascade=true' % gid, 'DELETE')
            api(drv, '/api/v1/testcases/%s/purge' % cid, 'DELETE')
        result['checks']['cleanup'] = {
            'group_in_facet': leaked,
            'case_get_after': {'status': rc['status'], 'body': (rc['body'] or '')[:160]},
        }

        # 判定
        ok = (
            chip_before and GROUP[:8] in (chip_before or '')
            and chip_after == '分组 | 全部'
            and not with_gid_after
            and not result['checks']['after_delete']['has_empty_state']
            and result['checks']['before_delete']['has_empty_state'] is False
        )
        result['pass'] = bool(ok)
        log('RESULT ' + json.dumps(result, ensure_ascii=False, indent=2))
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return 0 if ok else 2
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
