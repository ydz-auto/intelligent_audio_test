# -*- coding: utf-8 -*-
"""INT-1503 验收（React 页面线 B）：SPL 校准后详情/历史增益列与校准曲线。

环境：本 run dev server 5391（临时 rsbuild 配置）→ 真实库栈网关 5700（主库 intelligent_audio_test，
AUTH_MODE=dev，表单登录 接线测试_admin）。docker :15000 的 device 域当前 gRPC 50053 未监听
（容器跑成 api_gateway app），SPL 域无法在 15000 复测，故走常驻真实库栈 5700（同主库）。
写数据纪律：只建「接线测试_INT1503_」前缀映射，run 末删除。
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
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5391')
USER = os.environ.get('REAL_USER', '接线测试_admin')
PASSWORD = os.environ.get('REAL_PASSWORD', 'JieXianTest@2026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1503')
os.makedirs(ART, exist_ok=True)
THEME_KEY = 'iatp:theme:v1:mode'
NAME = '接线测试_INT1503_增益' + time.strftime('%H%M%S')
PREFIX = '接线测试_INT1503_'
EVID = {'checks': [], 'network': [], 'api_readback': {}}


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    EVID['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:4000]})
    log(('PASS ' if ok else 'FAIL ') + name + ((' | ' + str(detail)[:600]) if detail else ''))
    return ok


HOOK_JS = r"""
(function(){
  if (window.__int1503_installed) return;
  window.__int1503_installed = true;
  window.__reqLog = [];
  var origFetch = window.fetch.bind(window);
  window.fetch = function(input, init){
    var url = (typeof input === 'string') ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var body = (init && typeof init.body === 'string') ? init.body : null;
    return origFetch(input, init).then(function(res){
      try {
        var clone = res.clone();
        clone.text().then(function(t){
          window.__reqLog.push({url:url, method:method, status:res.status, reqBody:body, respBody:(t||'').slice(0,20000)});
        }).catch(function(){});
      } catch(e) {}
      return res;
    }).catch(function(e){
      window.__reqLog.push({url:url, method:method, status:'ERR', reqBody:body, respBody:String(e)});
      throw e;
    });
  };
})();
"""


def new_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = [os.path.join(cache_root, v, 'chromedriver.exe') for v in os.listdir(cache_root)]
    cands = [c for c in cands if os.path.isfile(c)]
    d = webdriver.Chrome(options=o, service=Service(executable_path=sorted(cands)[-1]))
    d.set_page_load_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK_JS})
    return d


def js(d, script, *args):
    return d.execute_script(script, *args)


def js_click(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.15)
    d.execute_script("arguments[0].click();", el)


def find(d, xpath, timeout=20, visible=True):
    def cond(dd):
        for e in dd.find_elements(By.XPATH, xpath):
            if (not visible) or e.is_displayed():
                return e
        return False
    return WebDriverWait(d, timeout, poll_frequency=0.25).until(cond)


def find_all(d, xpath, visible=True):
    return [e for e in d.find_elements(By.XPATH, xpath) if (not visible) or e.is_displayed()]


def dialog(d):
    return find(d, "//div[@role='dialog' or @role='alertdialog']")


def auth_mode():
    import urllib.request
    try:
        with urllib.request.urlopen(BASE + '/api/v1/auth/mode', timeout=10) as r:
            return json.loads(r.read().decode()).get('auth_mode') or ''
    except Exception:
        return ''


def login(d):
    if auth_mode() != 'dev':
        return
    d.get(BASE + '/login')
    WebDriverWait(d, 25).until(lambda dd: dd.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PASSWORD)
    js_click(d, d.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    WebDriverWait(d, 40).until(lambda dd: '/login' not in dd.current_url)
    time.sleep(0.5)


def reqs_since(d, start):
    return d.execute_script('return (window.__reqLog||[]).slice(arguments[0]);', start)


def req_len(d):
    return d.execute_script('return (window.__reqLog||[]).length;')


def page_fetch(d, path):
    """页内 fetch（带 token）取原始响应体。"""
    d.set_script_timeout(40)
    return d.execute_async_script(
        """
        var path = arguments[0], done = arguments[arguments.length-1];
        var token = window.localStorage.getItem('iatp:auth:token:v1');
        fetch(path, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
          .then(function(r){ return r.text().then(function(t){ done({status:r.status, body:t}); }); })
          .catch(function(e){ done({status:'ERR', body:String(e)}); });
        """,
        path,
    )


def open_page(d, dark=False):
    js(d, "window.localStorage.setItem(arguments[0], arguments[1]);", THEME_KEY, 'dark' if dark else 'light')
    d.get(BASE + '/SPLMapping')
    WebDriverWait(d, 40).until(lambda dd: dd.find_elements(By.ID, '搜索映射') or dd.find_elements(By.XPATH, "//h1|//*[contains(text(),'声压级映射管理')]"))
    time.sleep(1.5)


def search(d, keyword):
    box = find(d, "//input[@aria-label='搜索映射']")
    box.click()
    box.send_keys(u'\ue009' + 'a')
    box.send_keys(u'\ue003')
    box.send_keys(keyword)
    time.sleep(1.2)


def row_for(d, name):
    return find(d, "//tr[.//span[@title=%s]]" % xpath_lit(name))


def xpath_lit(s):
    if '"' not in s:
        return '"%s"' % s
    return "'%s'" % s


def open_row_menu(d, name):
    trig = find(d, "//button[@aria-label=%s]" % xpath_lit('映射 %s 的操作' % name))
    js_click(d, trig)
    time.sleep(0.4)


def menu_click(d, label):
    item = find(d, "//div[@role='menuitem'][normalize-space(.)=%s]" % xpath_lit(label))
    js_click(d, item)
    time.sleep(0.6)


def save(d, name):
    path = os.path.join(ART, name + '.png')
    d.save_screenshot(path)
    return path


def close_dialog(d):
    btns = find_all(d, "//div[@role='dialog']//button[normalize-space(.)='关闭' or normalize-space(.)='取消']")
    if btns:
        js_click(d, btns[-1])
        time.sleep(0.5)


def read_points(d, section_label):
    rows = find_all(d, "//section[@aria-labelledby=%s]//tbody/tr" % xpath_lit(section_label))
    out = []
    for r in rows:
        cells = r.find_elements(By.XPATH, './td')
        out.append([c.text.strip() for c in cells])
    return out


def create_mapping(d):
    js_click(d, find(d, "//button[normalize-space(.)='添加增益映射']"))
    dlg = dialog(d)
    WebDriverWait(d, 20).until(lambda dd: dd.find_elements(By.XPATH, "//input[@aria-label='映射名称']"))
    name_input = find(d, "//input[@aria-label='映射名称']")
    name_input.send_keys(NAME)
    dist = find(d, "//input[@aria-label='测量距离']")
    dist.click()
    dist.send_keys(u'\ue009' + 'a')
    dist.send_keys(u'\ue003')
    dist.send_keys('1.0')
    js_click(d, find(d, "//div[@role='dialog']//button[normalize-space(.)='保存']"))
    WebDriverWait(d, 30).until(lambda dd: not [e for e in dd.find_elements(By.XPATH, "//div[@role='dialog']//input[@aria-label='映射名称']") if e.is_displayed()])
    time.sleep(2.0)


def main():
    d = new_driver()
    try:
        login(d)
        start = req_len(d)
        open_page(d, dark=False)

        # 预清理：上一轮中断残留的本卡测试映射
        leftovers = json.loads(page_fetch(d, '/api/v1/spl?page=1&per_page=1000')['body']).get('data', {}).get('items') or []
        for item in leftovers:
            if str(item.get('name', '')).startswith(PREFIX):
                d.execute_async_script(
                    """
                    var id=arguments[0], done=arguments[arguments.length-1];
                    var token=window.localStorage.getItem('iatp:auth:token:v1');
                    fetch('/api/v1/spl/'+id,{method:'DELETE',headers:token?{Authorization:'Bearer '+token}:{}})
                      .then(function(r){return r.text().then(function(t){done(r.status);});})
                      .catch(function(e){done(String(e));});
                    """, item['id'])
                log('pre-clean deleted leftover', item['id'], item.get('name'))

        # 列表请求
        lst = [r for r in reqs_since(d, start) if '/api/v1/spl' in r['url'] and r['method'] == 'GET']
        check('列表 GET /spl 200', any(r['status'] == 200 for r in lst), [r['url'] for r in lst][:3])

        # 建映射
        c0 = req_len(d)
        create_mapping(d)
        post = [r for r in reqs_since(d, c0) if r['method'] == 'POST' and r['url'].rstrip('/').endswith('/api/v1/spl')]
        check('新建 POST /spl 返回 <300', bool(post) and post[0]['status'] < 300, post[0] if post else 'no request')

        search(d, NAME)
        row_for(d, NAME)
        time.sleep(0.5)

        # 执行校准
        c1 = req_len(d)
        open_row_menu(d, NAME)
        menu_click(d, '执行校准')
        WebDriverWait(d, 40).until(lambda dd: any(
            r['method'] == 'POST' and '/calibrate' in r['url'] and r['status'] < 300 for r in reqs_since(d, c1)))
        cal = [r for r in reqs_since(d, c1) if '/calibrate' in r['url']][0]
        EVID['network'].append({'method': cal['method'], 'url': cal['url'], 'status': cal['status'], 'resp': cal['respBody'][:500]})
        check('校准 POST /spl/{id}/calibrate 成功', cal['status'] < 300, cal['respBody'][:300])
        # 等列表刷新出「已校准」
        WebDriverWait(d, 40).until(lambda dd: '已校准' in (row_for(dd, NAME).text if dd.find_elements(By.XPATH, "//tr[.//span[@title=%s]]" % xpath_lit(NAME)) else ''))
        check('列表行刷新为已校准', '已校准' in row_for(d, NAME).text, row_for(d, NAME).text.replace('\n', ' | ')[:300])

        # 详情
        open_row_menu(d, NAME)
        menu_click(d, '详情')
        find(d, "//div[@role='dialog']//*[contains(normalize-space(.),'增益映射详情')]")
        time.sleep(2.0)
        points = read_points(d, 'spl-points-title')
        check('详情校准点 11 行', len(points) == 11, len(points))
        gain_ok = [p[0] for p in points][:11] == ['%d dB' % g for g in [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]]
        check('增益偏移 1~100 dB', gain_ok, [p[0] for p in points][:11])
        check('数字增益列非空', all(p[1] not in ('', '—') for p in points), [p[1] for p in points][:3])
        check('基础电平恒 -30 dBFS', all(p[2] == '-30 dBFS' for p in points), [p[2] for p in points][:3])
        check('最终电平 -29~70 dBFS', all(p[3] not in ('', '—') for p in points) and points[0][3] == '-29 dBFS' and points[-1][3] == '70 dBFS',
              [p[3] for p in points])
        canvases = find_all(d, "//section[@aria-labelledby='spl-curve-title']//canvas", visible=False)
        check('校准曲线画布渲染', len(canvases) > 0, len(canvases))
        check('曲线区无「暂无数据」空态', '暂无数据' not in dialog(d).text, '')
        save(d, '01_detail_light')

        # GET /spl/{id} 原始回读
        api_list = page_fetch(d, '/api/v1/spl?page=1&per_page=1000')
        try:
            items = json.loads(api_list['body']).get('data', {}).get('items') or []
        except Exception:
            items = []
        mine = [i for i in items if i.get('name') == NAME]
        m_id = mine[0]['id'] if mine else None
        check('GET /spl 回读含本卡映射', m_id is not None, api_list['status'])
        detail_api = page_fetch(d, '/api/v1/spl/%s' % m_id) if m_id else {'status': 'skip', 'body': ''}
        try:
            raw = json.loads(detail_api['body'])
            raw = raw.get('data', raw)
        except Exception:
            raw = {}
        pts = ((raw.get('calibration_data') or {}).get('points')) or []
        EVID['api_readback'] = {'id': m_id, 'status': detail_api['status'], 'status_field': raw.get('calibration_status'), 'point_count': len(pts), 'first': pts[0] if pts else None, 'last': pts[-1] if pts else None}
        check('GET /spl/{id} 校准点 11 且键为 gain', len(pts) == 11 and all('gain' in p for p in pts), EVID['api_readback'])

        # 历史
        js_click(d, find(d, "//div[@role='dialog']//button[normalize-space(.)='查看校准历史']"))
        time.sleep(2.0)
        heads = find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
        check('校准历史有记录', len(heads) > 0, len(heads))
        if heads:
            js_click(d, heads[0])
            time.sleep(0.8)
        hrows = find_all(d, "//div[@role='dialog']//tbody/tr")
        hcells = [[c.text.strip() for c in r.find_elements(By.XPATH, './td')] for r in hrows]
        check('历史展开 11 行', len(hcells) == 11, len(hcells))
        check('历史四列均有值（增益/基础/最终/SPL）', all(all(v not in ('', '—') for v in row) for row in hcells) if hcells else False,
              hcells[:2])
        check('历史基础电平 -30 dBFS', all(row[1] == '-30 dBFS' for row in hcells) if hcells else False, [r[1] for r in hcells][:3])
        hnet = [r for r in reqs_since(d, c1) if '/history' in r['url']]
        check('历史 GET /spl/{id}/history 200', bool(hnet) and hnet[-1]['status'] == 200, hnet[-1]['url'] if hnet else 'no request')
        save(d, '02_history_light')
        close_dialog(d)
        close_dialog(d)

        # 深色
        open_page(d, dark=True)
        search(d, NAME)
        row_for(d, NAME)
        open_row_menu(d, NAME)
        menu_click(d, '详情')
        find(d, "//div[@role='dialog']//*[contains(normalize-space(.),'增益映射详情')]")
        time.sleep(2.0)
        dpoints = read_points(d, 'spl-points-title')
        check('深色详情 11 行四列非空', len(dpoints) == 11 and all(p[1] not in ('', '—') and p[2] == '-30 dBFS' for p in dpoints), dpoints[:2])
        save(d, '03_detail_dark')
        js_click(d, find(d, "//div[@role='dialog']//button[normalize-space(.)='查看校准历史']"))
        time.sleep(2.0)
        heads = find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
        if heads:
            js_click(d, heads[0])
            time.sleep(0.8)
        save(d, '04_history_dark')

        # 清理
        if m_id:
            dele = d.execute_async_script(
                """
                var id=arguments[0], done=arguments[arguments.length-1];
                var token=window.localStorage.getItem('iatp:auth:token:v1');
                fetch('/api/v1/spl/'+id,{method:'DELETE',headers:token?{Authorization:'Bearer '+token}:{}})
                  .then(function(r){return r.text().then(function(t){done({status:r.status,body:t});});})
                  .catch(function(e){done({status:'ERR',body:String(e)});});
                """, m_id)
            check('清理：删除本卡测试映射', dele['status'] < 300, dele['status'])

        EVID['network'] += [{'method': r['method'], 'url': r['url'], 'status': r['status']} for r in reqs_since(d, start) if '/api/v1/spl' in r['url']][:40]
    finally:
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(EVID, f, ensure_ascii=False, indent=2)
        d.quit()
    fails = [c for c in EVID['checks'] if not c['ok']]
    log('\n== SUMMARY: %d checks, %d FAIL ==' % (len(EVID['checks']), len(fails)))
    for c in fails:
        log('FAIL: ' + c['name'])
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
