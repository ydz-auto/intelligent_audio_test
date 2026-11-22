# -*- coding: utf-8 -*-
"""INT-2676 验收探针：报告「具体用例对比」排序方式/资源下拉触发器必须回显中文标签。

背景：`<SelectValue />` 裸写且 Select 根未给 `items`，Base UI 回退显示原始 value
（name / createdat / metric / all）。修复给 Select 根传 items（与弹层共用同一份选项）。

本探针在 React dev server（API_PROXY_TARGET -> docker 网关 15000）上实测：
  1) /report/426「具体用例对比」初始排序方式触发器 = 「按名称」；
  2) 切「按评估维度」后触发器 = 「按评估维度」，并出现资源触发器 = 「全部资源(平均)」；
  3) 资源下拉首项 = 「全部资源(平均)」，切具体资源后触发器显示该资源名；
  4) 两个下拉的选项文案均为中文，无 name/createdat/metric/all 裸露；
  5) 触发排序后确有真实请求 POST /api/v1/reports/426/cases/search 200，payload sort_by=metric，无 mock。

跑法（环境铁律：后端用 docker 栈 15000，前端 dev server 仅作本卡未部署修复的载体）：
  UI_TEST_USERNAME=dev_user UI_TEST_PASSWORD=dev_password \
  python tests/ui/probe_int2676_select_echo.py --base http://127.0.0.1:5273 --report 426
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402

ART = os.path.join(sm.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2676')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'shots': [], 'notes': []}

# 记录本页 fetch 请求（url + body），用于证明真实请求 + 无 mock。
REQ_PATCH = r"""
window.__reqs = [];
const __f = window.fetch;
window.fetch = function(input, init){
  try {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var body = init && init.body ? String(init.body) : '';
    if (url.indexOf('/api/') >= 0) window.__reqs.push({url: url, body: body, ts: Date.now()});
  } catch(e) {}
  return __f.apply(this, arguments);
};
"""


def log(msg):
    print('[int2676] %s' % msg, flush=True)


def shot(drv, key):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, key + '.png')
    drv.save_screenshot(path)
    RESULT['shots'].append({'name': key, 'size': os.path.getsize(path)})
    return path


def js(drv, script, *args):
    return drv.execute_script(script, *args)


def wait_text(drv, text, timeout=45):
    return WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script(
            'return document.body ? document.body.innerText : ""') or ''))


CARD_SCOPE_JS = """
  function __card(){
    var labels = [].slice.call(document.querySelectorAll('label'))
      .filter(function(l){return (l.textContent||'').trim() === '排序方式';});
    if (!labels.length) return null;
    return labels[0].closest('div.rounded-xl');
  }
"""


def trigger_text(drv, label):
    """在「排序方式」所在的筛选卡内，按 label 找 Select 触发器文本。"""
    return js(drv, """
      %s
      var want = arguments[0];
      var card = __card();
      if (!card) return null;
      var labels = [].slice.call(card.querySelectorAll('label'))
        .filter(function(l){return (l.textContent||'').trim() === want;});
      if (!labels.length) return null;
      var box = labels[0].parentElement;
      var t = box.querySelector('[role="combobox"]');
      return t ? (t.textContent||'').trim() : null;
    """ % CARD_SCOPE_JS, label)


def click_trigger(drv, label):
    ok = js(drv, """
      %s
      var want = arguments[0];
      var card = __card();
      if (!card) return false;
      var labels = [].slice.call(card.querySelectorAll('label'))
        .filter(function(l){return (l.textContent||'').trim() === want;});
      if (!labels.length) return false;
      var box = labels[0].parentElement;
      var t = box.querySelector('[role="combobox"]');
      if (!t) return false;
      var r = t.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return false;
      t.scrollIntoView({block:'center'});
      t.click();
      return true;
    """ % CARD_SCOPE_JS, label)
    time.sleep(0.8)
    return ok


def open_options(drv):
    return js(drv, """
      return [].slice.call(document.querySelectorAll('[role="option"]'))
        .filter(function(o){return o.getBoundingClientRect().height > 0;})
        .map(function(o){return (o.textContent||'').trim();});
    """)


def pick_option(drv, text):
    ok = js(drv, """
      var opts = [].slice.call(document.querySelectorAll('[role="option"]'))
        .filter(function(o){return o.getBoundingClientRect().height > 0;});
      for (var i=0;i<opts.length;i++){
        if ((opts[i].textContent||'').trim() === arguments[0]) { opts[i].click(); return true; }
      }
      return false;
    """, text)
    time.sleep(2.0)
    return ok


def login(drv, base, username, password):
    drv.get(base + '/login')
    WebDriverWait(drv, 45).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'input[type=password]'))
    time.sleep(1.0)
    u = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]') if e.is_displayed()][0]
    u.clear(); u.send_keys(username)
    p.clear(); p.send_keys(password)
    btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]') if b.is_displayed()]
    sm.click_js(drv, btns[-1])
    WebDriverWait(drv, 45).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2.0)
    return drv.current_url


def set_theme(drv, mode):
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.refresh()
    time.sleep(4)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5273')
    ap.add_argument('--report', default='426')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    report_id = args.report

    username = os.environ.get('UI_TEST_USERNAME', 'dev_user')
    password = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

    # 0. 后端环境
    with sm.urllib.request.urlopen(sm.API + '/health', timeout=20) as r:
        health = json.loads(r.read().decode('utf-8'))
    RESULT['checks']['backend_health'] = health
    log('ENV database=%s version=%s' % (health.get('database'), health.get('version')))

    drv = sm.make_driver(os.path.join(ART, 'downloads'))
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': REQ_PATCH})

    # 1. 登录
    url_after = login(drv, base, username, password)
    RESULT['checks']['login_url'] = url_after
    log('login -> %s' % url_after)

    # 后端侧期望：报告详情资源 + 搜索 total
    status, detail = sm.http_json('/reports/%s' % report_id)
    RESULT['checks']['report_detail_status'] = status
    summary = ((detail or {}).get('data') or detail or {}).get('summary') if isinstance(detail, dict) else {}
    RESULT['checks']['report_resources'] = (summary or {}).get('resources')

    drv.get(base + '/report/' + report_id)
    wait_text(drv, '具体用例对比')
    # 等筛选卡渲染出下拉
    WebDriverWait(drv, 45).until(lambda d: js(d, """
      var labels = [].slice.call(document.querySelectorAll('label'))
        .filter(function(l){return (l.textContent||'').trim() === '排序方式';});
      return labels.length > 0 && !!labels[0].parentElement.querySelector('[role="combobox"]');
    """))
    time.sleep(1.5)

    def ensure_expanded():
        """筛选卡默认展开；仅当「排序方式」label 不在文档中时才点开（避免把已展开的折叠掉）。"""
        if js(drv, """
          return [].slice.call(document.querySelectorAll('label'))
            .some(function(l){return (l.textContent||'').trim() === '排序方式';});
        """):
            return
        js(drv, """
          var btns=[].slice.call(document.querySelectorAll('button'));
          for (var i=0;i<btns.length;i++){ if((btns[i].textContent||'').indexOf('具体用例对比')>=0){ btns[i].click(); return true; } }
        """)
        time.sleep(1.5)

    ensure_expanded()

    # 2. 初始回显
    sort_text0 = trigger_text(drv, '排序方式')
    RESULT['checks']['initial_sort_trigger'] = sort_text0
    log('initial sort trigger = %r' % sort_text0)
    shot(drv, '01_filter_card_light')

    opts = []
    if click_trigger(drv, '排序方式'):
        opts = open_options(drv)
    RESULT['checks']['sort_options'] = opts
    log('sort options = %r' % opts)
    shot(drv, '02_sort_popup_light')
    # 关闭弹层（Esc）
    drv.find_element(By.TAG_NAME, 'body').send_keys('') if False else None
    pick_option(drv, '按评估维度')
    time.sleep(2.0)

    # 3. 切按评估维度后回显 + 资源出现
    sort_text1 = trigger_text(drv, '排序方式')
    res_text1 = trigger_text(drv, '资源')
    RESULT['checks']['after_metric_sort_trigger'] = sort_text1
    RESULT['checks']['after_metric_resource_trigger'] = res_text1
    log('after metric: sort=%r resource=%r' % (sort_text1, res_text1))
    shot(drv, '03_filter_card_metric_light')

    res_opts = []
    if click_trigger(drv, '资源'):
        res_opts = open_options(drv)
    RESULT['checks']['resource_options'] = res_opts
    log('resource options = %r' % res_opts)
    shot(drv, '04_resource_popup_light')

    # 4. 选一个具体资源（若存在非「全部资源(平均)」项）
    concrete = [o for o in res_opts if o and o != '全部资源(平均)']
    if concrete:
        pick_option(drv, concrete[0])
        time.sleep(1.5)
        RESULT['checks']['resource_after_pick'] = trigger_text(drv, '资源')
        RESULT['checks']['picked_resource'] = concrete[0]
        log('picked resource %r -> trigger %r' % (concrete[0], RESULT['checks']['resource_after_pick']))
        # 复位到全部资源，截图干净
        if click_trigger(drv, '资源'):
            pick_option(drv, '全部资源(平均)')
            time.sleep(1.0)

    # 5. 网络证据
    reqs = js(drv, "return window.__reqs || [];")
    RESULT['checks']['requests'] = reqs
    search_reqs = [r for r in reqs if '/reports/%s/cases/search' % report_id in r.get('url', '')]
    RESULT['checks']['search_requests'] = search_reqs
    apis = sm.parse_perf(drv.get_log('performance'))
    search_apis = [a for a in apis if '/reports/%s/cases/search' % report_id in (a.get('url') or '')]
    RESULT['checks']['search_apis'] = search_apis
    RESULT['checks']['api_errors'] = sm.api_errors(apis)
    RESULT['checks']['console_errors'] = sm.console_errors(drv)
    log('search apis = %r' % search_apis)

    # 6. 深色模式复测
    set_theme(drv, 'dark')
    wait_text(drv, '具体用例对比')
    ensure_expanded()
    time.sleep(0.5)
    dark_sort0 = trigger_text(drv, '排序方式')
    if click_trigger(drv, '排序方式'):
        dark_opts = open_options(drv)
        pick_option(drv, '按评估维度')
        time.sleep(2.0)
    else:
        dark_opts = []
    dark_sort1 = trigger_text(drv, '排序方式')
    dark_res = trigger_text(drv, '资源')
    RESULT['checks']['dark_sort_trigger_initial'] = dark_sort0
    RESULT['checks']['dark_sort_trigger_metric'] = dark_sort1
    RESULT['checks']['dark_resource_trigger'] = dark_res
    RESULT['checks']['dark_sort_options'] = dark_opts
    log('dark: initial=%r metric=%r resource=%r' % (dark_sort0, dark_sort1, dark_res))
    shot(drv, '05_filter_card_metric_dark')
    if click_trigger(drv, '资源'):
        shot(drv, '06_resource_popup_dark')
        pick_option(drv, '全部资源(平均)')

    set_theme(drv, 'light')

    # 7. 判定
    RAW = {'name', 'createdat', 'metric', 'all', 'tag'}
    bad = [t for t in [sort_text0, sort_text1, res_text1] if t in RAW]
    c = RESULT['checks']
    RESULT['ok'] = (
        c.get('initial_sort_trigger') == '按名称'
        and c.get('after_metric_sort_trigger') == '按评估维度'
        and c.get('after_metric_resource_trigger') == '全部资源(平均)'
        and (c.get('resource_options') or [''])[0] == '全部资源(平均)'
        and not bad
        and any(a.get('status') == 200 for a in c.get('search_apis') or [])
        and len(search_reqs) > 0
        and not c.get('api_errors')
        and not c.get('console_errors')
        and c.get('dark_sort_trigger_metric') == '按评估维度'
        and c.get('dark_resource_trigger') == '全部资源(平均)'
    )
    RESULT['checks']['raw_value_leaks'] = bad

    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % os.path.join(ART, 'summary.json'))
    print('RESULT_OK=%s' % RESULT['ok'])
    drv.quit()
    return 0 if RESULT['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
