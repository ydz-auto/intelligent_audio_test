# -*- coding: utf-8 -*-
"""INT-1481 SPL 映射域复走（driver 1：物理域全弹窗 + 数字域 /apis 故障取证）。

环境：docker 真实栈 前端 15173 / 后端 15000 / 真实库 intelligent_audio_test（AUTH_MODE=off）。
证据：每个弹窗 浅/深 截图 + 真实请求/响应（页内 fetch 打点）+ GET 回读。
写数据纪律：只写「接线测试_INT1481_」前缀记录，本 run 末尾删除。
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1481')
os.makedirs(ART, exist_ok=True)

PREFIX = '接线测试_INT1481_'
NAME_A = PREFIX + '增益A'
NAME_B = PREFIX + '增益B'
EVID = {'api_readbacks': [], 'checks': [], 'net': []}


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    EVID['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    log(('PASS ' if ok else 'FAIL ') + name + ((' | ' + str(detail)[:800]) if detail else ''))


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def api_delete(path):
    req = urllib.request.Request(API + path, method='DELETE')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


HOOK_JS = r"""
(function(){
  if (window.__int1481_installed) return;
  window.__int1481_installed = true;
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
          window.__reqLog.push({url:url, method:method, status:res.status, reqBody:body, respBody:(t||'').slice(0,8000)});
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
    drv_path = os.path.join(cache_root, sorted(os.listdir(cache_root))[-1], 'chromedriver.exe')
    d = webdriver.Chrome(options=o, service=Service(executable_path=drv_path))
    d.set_page_load_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK_JS})
    return d


def js_click(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    d.execute_script("arguments[0].click();", el)


def find(d, xpath, timeout=15, visible=True):
    from selenium.webdriver.support.ui import WebDriverWait
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


def click_text(d, text, scope='//div[@role="dialog" or @role="alertdialog"]', timeout=15):
    el = find(d, scope + "//button[normalize-space(.)='" + text + "']", timeout)
    js_click(d, el)


def set_input(d, aria, value, scope='//div[@role="dialog"]'):
    el = find(d, scope + "//input[@aria-label='" + aria + "']|" + scope + "//textarea[@aria-label='" + aria + "']")
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(str(value))
    if (el.get_attribute('value') or '') != str(value):
        # number 输入框对逐键输入的中间态处理不一致 → 走 React 原生 setter 兜底
        d.execute_script(
            "var el=arguments[0], v=arguments[1];"
            "var proto = el.tagName==='TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;"
            "var setter = Object.getOwnPropertyDescriptor(proto,'value').set;"
            "setter.call(el, v); el.dispatchEvent(new Event('input',{bubbles:true}));",
            el, str(value))
        time.sleep(0.2)
    return el.get_attribute('value')


def get_input(d, aria, scope='//div[@role="dialog"]'):
    el = find(d, scope + "//input[@aria-label='" + aria + "']|" + scope + "//textarea[@aria-label='" + aria + "']")
    return el.get_attribute('value')


def open_select(d, label, option_text):
    trig = find(d, "//button[@role='combobox' and @aria-label='" + label + "']")
    js_click(d, trig)
    opt = find(d, "//*[@role='option'][contains(normalize-space(.), '" + option_text + "')]", timeout=10)
    js_click(d, opt)
    time.sleep(0.4)


def selected_text(d, label):
    el = find(d, "//button[@role='combobox' and @aria-label='" + label + "']")
    return el.text.strip()


def row_action(d, name, item):
    trig = find(d, "//button[@aria-label='映射 " + name + " 的操作']")
    js_click(d, trig)
    time.sleep(0.5)
    mi = find(d, "//*[@role='menuitem'][normalize-space(.)='" + item + "']", timeout=10)
    js_click(d, mi)
    time.sleep(0.8)


def toast_texts(d, wait=1.2):
    time.sleep(wait)
    return [e.text.strip() for e in find_all(d, "//*[@data-sonner-toast]") if e.text.strip()]


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('SHOT', name)
    return p


def set_theme(d, mode, url):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.get('about:blank')
    d.get(url)
    time.sleep(5)
    return d.execute_script("return document.documentElement.className")


def reqlog(d, since=0):
    return d.execute_script("return (window.__reqLog||[]).slice(arguments[0]);", since)


def log_len(d):
    return d.execute_script("return (window.__reqLog||[]).length;")


def net_entries(d, since, needle):
    out = []
    for e in reqlog(d, since):
        if needle in e['url'] and e['method'] != 'GET' or (needle in e['url'] and 'page=' not in e['url']):
            out.append(e)
    return out


def wait_rows(d, timeout=20):
    find(d, "//table//tbody/tr", timeout)


def row_names(d):
    out = []
    for e in find_all(d, "//table//tbody/tr/td[2]"):
        txt = e.text.strip()
        out.append(txt.split('\n')[0] if txt else '')
    return out


def search(d, text):
    el = find(d, "//input[@aria-label='搜索映射']")
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(text)
    time.sleep(1.2)


def clear_search(d):
    search(d, '')
    time.sleep(0.5)


def spl_by_name(name):
    rows = api_get('/spl?page=1&per_page=1000')['data']['items']
    for r in rows:
        if r.get('name') == name:
            return r
    return None


def run_device(d):
    log('\n=== 物理域 ===')
    d.get(BASE + '/SPLMapping')
    time.sleep(6)
    wait_rows(d)
    shot(d, '01_device_page_light')
    names = row_names(d)
    log('rows', names)
    check('列表真实数据 3 条', len(names) == 3, names)

    # 统计徽章 vs /spl/stats
    stats = api_get('/spl/stats')['data']
    body = d.find_element(By.TAG_NAME, 'body').text
    check('统计徽章 total/calibrated 与 GET /spl/stats 一致',
          ('映射总数' in body and str(stats['total']) in body and str(stats['calibrated']) in body),
          stats)

    # --- 新建校验：空名 ---
    js_click(d, find(d, "//button[normalize-space(.)='添加增益映射']"))
    time.sleep(1.2)
    shot(d, '02_form_create_light')
    click_text(d, '保存')
    tt = toast_texts(d)
    check('新建空名拦截', any('请输入映射名称' in t for t in tt), tt)
    # 关闭后重开表单清空（先填空再取消）
    set_input(d, '映射名称', '临时_不应保存')
    click_text(d, '取消')
    time.sleep(0.8)
    js_click(d, find(d, "//button[normalize-space(.)='添加增益映射']"))
    time.sleep(1.2)
    check('取消后重开表单清空', get_input(d, '映射名称') == '', repr(get_input(d, '映射名称')))
    log('设备类型 select 初始显示:', selected_text(d, '设备类型'))

    # --- 新建 A ---
    before = log_len(d)
    set_input(d, '映射名称', NAME_A)
    set_input(d, '描述', 'INT-1481 复走测试记录，可删')
    open_select(d, '关联播放设备', '设备正面（0.5m+0°）')
    open_select(d, '设备类型', '噪声')
    check('设备类型选择后触发器显示中文标签', selected_text(d, '设备类型') == '噪声',
          '实际显示=' + selected_text(d, '设备类型'))
    check('关联播放设备选中后触发器显示设备名',
          '设备正面' in selected_text(d, '关联播放设备'),
          '实际显示=' + selected_text(d, '关联播放设备'))
    set_input(d, '测量距离', '1.2')
    set_input(d, '目标声压级', '70')
    set_input(d, '数字增益', '3')
    set_input(d, '测试频率', '2000')
    set_input(d, '第 1 行增益偏移', '-12')
    set_input(d, '第 1 行实测 SPL', '57')
    shot(d, '03_form_create_filled_light')
    click_text(d, '保存')
    time.sleep(2)
    tt = toast_texts(d)
    check('新建 A toast', any('创建成功' in t for t in tt), tt)
    reqs = [e for e in reqlog(d, before) if '/api/v1/spl' in e['url'] and e['method'] in ('POST', 'PUT')]
    EVID['net'].append({'step': 'create_spl', 'reqs': reqs})
    a = spl_by_name(NAME_A)
    check('新建 A GET 回读', a is not None, '')
    if a:
        check('A 名称/设备/类型/距离/目标/频率/点数 回读一致',
              a['name'] == NAME_A and a['device_id'] == 5 and a['device_type'] == 'noise'
              and abs(a['distance'] - 1.2) < 1e-9 and abs(a['target_spl'] - 70) < 1e-9
              and a['test_frequency'] == 2000
              and len((a.get('calibration_data') or {}).get('points') or []) == 4,
              json.dumps({k: a.get(k) for k in ('name', 'device_id', 'device_type', 'distance', 'target_spl', 'test_frequency')}, ensure_ascii=False))
        # V9.7.10 基线 spl_controller 创建时显式 digital_gain=None，新建回读为空属基线行为
        check('A 新建 digital_gain 回读与 V9.7.10 基线一致（创建不落数字增益）',
              a['digital_gain'] is None, a.get('digital_gain'))
        check('A 新建带点集即 calibrated（V9.7.10 基线一致）',
              a['calibration_status'] == 'calibrated', a.get('calibration_status'))
    wait_rows(d)
    check('A 出现在列表首行', row_names(d)[0].startswith(NAME_A), row_names(d)[:2])

    # --- 编辑回显 + 改字段 ---
    row_action(d, NAME_A, '编辑')
    check('编辑表单回显名称', get_input(d, '映射名称') == NAME_A, get_input(d, '映射名称'))
    check('编辑表单回显目标声压级/频率', get_input(d, '目标声压级') == '70' and get_input(d, '测试频率') == '2000',
          (get_input(d, '目标声压级'), get_input(d, '测试频率')))
    log('编辑态设备类型 select 显示:', selected_text(d, '设备类型'))
    before = log_len(d)
    set_input(d, '目标声压级', '72')
    shot(d, '04_form_edit_light')
    click_text(d, '保存')
    time.sleep(2)
    tt = toast_texts(d)
    check('编辑保存 toast', any('已保存' in t for t in tt), tt)
    reqs = [e for e in reqlog(d, before) if '/api/v1/spl' in e['url'] and e['method'] in ('POST', 'PUT')]
    EVID['net'].append({'step': 'update_spl', 'reqs': reqs})
    a = spl_by_name(NAME_A)
    check('编辑后 GET 回读 target_spl=72', a and abs(a['target_spl'] - 72) < 1e-9, a and a.get('target_spl'))

    # --- 执行校准 ---
    before = log_len(d)
    row_action(d, NAME_A, '执行校准')
    tt = toast_texts(d, 2)
    check('执行校准 toast', any('校准完成' in t for t in tt), tt)
    reqs = [e for e in reqlog(d, before) if '/calibrate' in e['url']]
    EVID['net'].append({'step': 'calibrate_spl', 'reqs': reqs})
    a = spl_by_name(NAME_A)
    check('校准后 GET 回读 calibrated', a and a['calibration_status'] == 'calibrated', a and a.get('calibration_status'))

    # --- 详情弹窗 ---
    row_action(d, NAME_A, '详情')
    dlg = dialog(d)
    dt = dlg.text
    check('详情弹窗含名称/已校准/校准点数/曲线', NAME_A in dt and '已校准' in dt and '校准点数' in dt and '校准曲线' in dt, dt[:400])
    shot(d, '05_detail_light')
    # 详情 → 校准历史
    click_text(d, '查看校准历史')
    time.sleep(2)
    dlg = dialog(d)
    check('详情跳校准历史', '校准历史' in dlg.text, dlg.text[:300])
    hist = dlg.text
    check('校准历史有 1 条记录', '个校准点' in hist, hist[:300])
    shot(d, '06_history_light')
    # 展开记录
    js_click(d, find(d, "//div[@role='dialog']//button[@aria-expanded='false']"))
    time.sleep(1)
    dlg = dialog(d)
    check('校准历史展开点集表', '实测 SPL' in dlg.text, dlg.text[:400])
    shot(d, '06b_history_expanded_light')
    click_text(d, 'Close')
    time.sleep(0.8)

    # --- 编辑已校准映射改距离：重置确认（先取消再确认） ---
    row_action(d, NAME_A, '编辑')
    before = log_len(d)
    set_input(d, '测量距离', '1.5')
    time.sleep(1)
    ad = find(d, "//div[@role='alertdialog']", timeout=10)
    check('已校准改距离弹校准重置确认', '校准重置确认' in ad.text, ad.text[:200])
    shot(d, '07_reset_confirm_light')
    # 取消 → 距离保持原值
    click_text(d, '取消', scope="//div[@role='alertdialog']")
    time.sleep(0.8)
    check('重置确认取消后距离不变', get_input(d, '测量距离') == '1.2', get_input(d, '测量距离'))
    # 再改 + 确认
    set_input(d, '测量距离', '1.5')
    time.sleep(1)
    ad = find(d, "//div[@role='alertdialog']", timeout=10)
    click_text(d, '继续', scope="//div[@role='alertdialog']")
    time.sleep(0.8)
    check('确认重置后点集清空', '尚无校准点' in dialog(d).text, dialog(d).text[:300])
    shot(d, '07b_form_reset_light')
    click_text(d, '保存')
    time.sleep(2)
    a = spl_by_name(NAME_A)
    check('重置保存后回读 uncalibrated/距离1.5',
          a and a['calibration_status'] == 'uncalibrated' and abs(a['distance'] - 1.5) < 1e-9,
          a and (a.get('calibration_status'), a.get('distance')))

    # 再校准一次（供批量确认路径）
    row_action(d, NAME_A, '执行校准')
    toast_texts(d, 1.5)
    a = spl_by_name(NAME_A)
    check('二次校准后 calibrated', a and a['calibration_status'] == 'calibrated', a and a.get('calibration_status'))

    # --- 新建 B ---
    js_click(d, find(d, "//button[normalize-space(.)='添加增益映射']"))
    time.sleep(1.2)
    set_input(d, '映射名称', NAME_B)
    open_select(d, '关联播放设备', '设备正面（0.5m+0°）')
    set_input(d, '目标声压级', '60')
    click_text(d, '保存')
    toast_texts(d, 1.5)
    b = spl_by_name(NAME_B)
    check('新建 B GET 回读', b is not None, '')
    wait_rows(d)

    # --- 批量配置（先按前缀筛选，只动测试记录） ---
    search(d, PREFIX)
    time.sleep(1)
    names = row_names(d)
    check('筛选后仅 2 条测试记录', len(names) == 2, names)
    before = log_len(d)
    js_click(d, find(d, "//button[contains(normalize-space(.), '批量配置 SPL')]"))
    time.sleep(1.2)
    dt = dialog(d).text
    check('批量弹窗目标数=2 且提示已校准条数', '2' in dt and '已校准' in dt, dt[:400])
    shot(d, '08_batch_light')
    set_input(d, '测量距离', '2')
    set_input(d, '目标声压级', '66')
    set_input(d, '测试频率', '1500')
    set_input(d, '数字增益', '4')
    click_text(d, '确认配置')
    time.sleep(1.2)
    ad = find(d, "//div[@role='alertdialog']", timeout=10)
    check('批量已校准确认弹窗', '将对 2 个已校准映射' in ad.text, ad.text[:200])
    shot(d, '08b_batch_confirm_light')
    click_text(d, '继续', scope="//div[@role='alertdialog']")
    tt = toast_texts(d, 4)
    check('批量配置完成 toast', any('批量配置完成' in t for t in tt), tt)
    reqs = [e for e in reqlog(d, before) if '/api/v1/spl/' in e['url'] and e['method'] == 'PUT']
    EVID['net'].append({'step': 'batch_spl', 'reqs': reqs})
    time.sleep(1)
    a = spl_by_name(NAME_A)
    b = spl_by_name(NAME_B)
    ok = (a and b and abs(a['distance'] - 2) < 1e-9 and abs(b['distance'] - 2) < 1e-9
          and abs(a['target_spl'] - 66) < 1e-9 and b['test_frequency'] == 1500
          and a['calibration_status'] == 'uncalibrated' and b['calibration_status'] == 'uncalibrated')
    check('批量后两条 GET 回读一致且校准被重置', ok,
          [(a or {}).get('distance'), (a or {}).get('calibration_status'), (b or {}).get('test_frequency'), (b or {}).get('calibration_status')])
    clear_search(d)

    # --- 删除确认弹窗（先取消再删） ---
    row_action(d, NAME_B, '删除')
    ad = find(d, "//div[@role='alertdialog']", timeout=10)
    check('删除确认弹窗文案', '删除增益映射' in ad.text, ad.text[:200])
    shot(d, '09_delete_confirm_light')
    click_text(d, '取消', scope="//div[@role='alertdialog']")
    time.sleep(0.6)
    check('取消删除后记录仍在', spl_by_name(NAME_B) is not None, '')

    return


def run_device_dark(d):
    log('\n=== 物理域 深色截图 ===')
    set_theme(d, 'dark', BASE + '/SPLMapping')
    wait_rows(d)
    shot(d, '11_device_page_dark')
    # 新建表单
    js_click(d, find(d, "//button[normalize-space(.)='添加增益映射']"))
    time.sleep(1.2)
    shot(d, '12_form_create_dark')
    click_text(d, '取消')
    time.sleep(0.6)
    # 编辑 A
    search(d, PREFIX)
    time.sleep(1)
    row_action(d, NAME_A, '编辑')
    shot(d, '13_form_edit_dark')
    click_text(d, '取消')
    time.sleep(0.6)
    # 详情
    row_action(d, NAME_A, '详情')
    shot(d, '14_detail_dark')
    click_text(d, '查看校准历史')
    time.sleep(1.5)
    shot(d, '15_history_dark')
    click_text(d, 'Close')
    time.sleep(0.6)
    # 批量
    js_click(d, find(d, "//button[contains(normalize-space(.), '批量配置 SPL')]"))
    time.sleep(1.2)
    shot(d, '16_batch_dark')
    click_text(d, '取消')
    time.sleep(0.6)
    clear_search(d)
    # 删除确认
    row_action(d, NAME_B, '删除')
    time.sleep(0.8)
    shot(d, '17_delete_confirm_dark')
    click_text(d, '取消', scope="//div[@role='alertdialog']")
    time.sleep(0.6)


def cleanup_device():
    ids = []
    for name in (NAME_A, NAME_B):
        r = spl_by_name(name)
        if r:
            ids.append(r['id'])
            api_delete('/spl/%d' % r['id'])
            log('deleted spl', name, r['id'])
    for i in ids:
        try:
            left = api_get('/spl/%d' % i)
            log('WARN spl %s still gettable' % i, str(left)[:120])
        except Exception as e:
            log('spl %s GET after delete -> %s' % (i, e))
    EVID['cleanup'] = {'deleted_spl_ids': ids}


def run_digital_broken(d):
    log('\n=== 数字域 /apis 故障取证 ===')
    set_theme(d, 'light', BASE + '/SPLMapping')
    all_reqs = reqlog(d, 0)
    js_click(d, find(d, "//button[normalize-space(.)='API/Realtime RMS-SPL']"))
    time.sleep(3)
    shot(d, '20_digital_broken_light')
    body = d.find_element(By.TAG_NAME, 'body').text
    check('数字域空态渲染', '暂无 RMS-SPL 映射' in body, '')
    reqs = [e for e in all_reqs if '/apis' in e['url']]
    EVID['net'].append({'step': 'digital_apis_broken', 'reqs': reqs})
    check('GET /apis 返回 400（后端列漂移）', any(str(e['status']) == '400' for e in reqs),
          [(e['method'], e['status'], e['url']) for e in reqs])
    js_click(d, find(d, "//button[normalize-space(.)='添加 RMS-SPL 映射']"))
    time.sleep(1.2)
    shot(d, '21_digital_form_apis_broken_light')
    trig = find(d, "//button[@role='combobox' and @aria-label='关联被测 API']")
    js_click(d, trig)
    time.sleep(1)
    opts = find_all(d, "//*[@role='option']")
    check('关联 API 下拉 0 个选项（/apis 故障）', len(opts) == 0, len(opts))
    shot(d, '21b_digital_form_select_empty_light')
    # 点弹窗标题收起下拉（ESC 会连弹窗一起关掉）
    js_click(d, find(d, "//div[@role='dialog']//*[normalize-space(.)='添加 RMS-SPL 映射']"))
    time.sleep(0.6)
    set_input(d, '映射名称', PREFIX + '无API')
    click_text(d, '保存')
    tt = toast_texts(d)
    check('未选 API 提交拦截', any('请选择关联被测 API' in t for t in tt), tt)
    click_text(d, '取消')
    time.sleep(0.5)


def main():
    d = new_driver()
    try:
        run_device(d)
        run_device_dark(d)
        cleanup_device()
        run_digital_broken(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(HERE, 'artifacts', 'int1481', 'evidence_driver1.json'), 'w', encoding='utf-8') as f:
            json.dump(EVID, f, ensure_ascii=False, indent=2)
        log('\nEVIDENCE checks:', sum(1 for c in EVID['checks'] if c['ok']), '/', len(EVID['checks']))
        for c in EVID['checks']:
            if not c['ok']:
                log('FAILED:', c['name'], c['detail'][:400])


if __name__ == '__main__':
    main()
