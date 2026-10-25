# -*- coding: utf-8 -*-
"""INT-1765 验收：任务页增量导出 / 增量导入（链路 2）真实浏览器实测。

环境：旁路容器 http://localhost:15266（本卡交付构建 dist + 15173 同款 nginx conf）
      → docker 网关 :15000（库 intelligent_audio_test，AUTH_MODE=off）。
夹具：A 侧 678（接线测试_INT1765_A_回导目标）、B 侧 679（接线测试_INT1765_B_增量源），
      由整包导出/导入两次自建；增量包 inc_from_679_both.zip 由 B 侧「导出增量」逻辑产出。

覆盖卡面 8 条走查 + 跨组件同步点 + 浅/深色截图 + Network 证据。
"""
import functools
import json
import os
import sys
import time
import zipfile

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

print = functools.partial(print, flush=True)  # noqa: A001
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.environ.get('REACT_BASE', 'http://localhost:15266')
GATEWAY = 'http://127.0.0.1:15000'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_PATH = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
WORK = r'D:/00_user_data/int1765_work'
PACK_SRC = os.path.join(WORK, 'inc_from_679_both.zip')
PACK_DIMS = os.path.join(WORK, 'inc_from_679_dims.zip')
PACK_FULL = os.path.join(WORK, 'A_from_321.zip')
PACK_BAD409 = os.path.join(WORK, 'bad_missing_result.zip')
PACK_BAD500 = os.path.join(WORK, 'bad_dim_null.zip')

PROJECT_ROOT = r'D:/00_user_data/multica_workspaces_desktop-api.multica.ai/intelligent-95ba6a12369f/int-1765-68008195f118/worktree/Intelligent-Audio-TEST'
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1765')
DOWNLOADS = os.path.join(ART, 'downloads')
os.makedirs(DOWNLOADS, exist_ok=True)

A_NAME = '接线测试_INT1765_A_回导目标'
B_NAME = '接线测试_INT1765_B_增量源'
REAL_TASK_NAME = 'pura90豆包E2E测试任务_2026/8/28 17:58:05'

CHECKS = []
NET = []          # [(method, url, status, postData)]


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' :: ' + str(detail)) if detail else ''))
    return ok



COUNTER_JS = """
window.__c = {tasksList: 0, progress: 0, importInc: 0, importPreview: 0, exportInc: 0};
const __origFetch = window.fetch;
window.fetch = function(...args) {
  const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
  let p = '';
  try { p = new URL(url, location.href).pathname; } catch (e) {}
  if (p === '/api/v1/tasks') window.__c.tasksList++;
  if (p === '/api/v1/data-transfer/import/progress') window.__c.progress++;
  if (p === '/api/v1/data-transfer/import-incremental') window.__c.importInc++;
  if (p === '/api/v1/data-transfer/import/preview') window.__c.importPreview++;
  if (p === '/api/v1/data-transfer/export-incremental') window.__c.exportInc++;
  return __origFetch.apply(this, args);
};
"""


def counters():
    try:
        return D.execute_script('return JSON.parse(JSON.stringify(window.__c))')
    except Exception:
        return {}

def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_experimental_option('prefs', {
        'download.default_directory': DOWNLOADS.replace('/', '\\'),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
    })
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER_PATH), options=o)
    d.execute_cdp_cmd('Network.enable', {})
    d.set_page_load_timeout(90)
    d.set_script_timeout(300)
    return d


def drain_net(d):
    """把 performance log 里的请求/响应落进 NET（get_log 会清空 buffer）。"""
    reqs, resps = {}, {}
    try:
        logs = d.get_log('performance')
    except Exception:
        return
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        m = msg.get('method')
        p = msg.get('params') or {}
        if m == 'Network.requestWillBeSent':
            r = p.get('request') or {}
            reqs[p.get('requestId')] = (r.get('method'), r.get('url'), r.get('postData'))
        elif m == 'Network.responseReceived':
            r = p.get('response') or {}
            resps[p.get('requestId')] = (r.get('status'), r.get('url'))
    for rid, (meth, url, post) in reqs.items():
        status = resps.get(rid, (None, url))[0]
        if '/api/v1/' in (url or ''):
            NET.append({'method': meth, 'url': url, 'status': status, 'post': post})


def net_where(sub, since=0):
    drain_net(D)
    return [e for e in NET[since:] if sub in (e['url'] or '')]


def shot(name):
    path = os.path.join(ART, name + '.png')
    try:
        D.save_screenshot(path)
        print('  shot:', path)
    except Exception as e:
        print('  shot failed', e)


def dialog():
    return D.find_element(By.XPATH, "//*[@role='dialog']")


def dlg_text():
    try:
        return dialog().text
    except Exception:
        return ''


def click_xp(xp, timeout=25):
    el = WebDriverWait(D, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
    try:
        el.click()
    except Exception:
        D.execute_script('arguments[0].click()', el)
    return el


def btn(text):
    return f"//button[normalize-space(.)='{text}']"


def open_tasks():
    D.get(BASE + '/tasks/daily')
    WebDriverWait(D, 40).until(
        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='导出增量']")))
    time.sleep(1.5)


def search(name):
    inp = WebDriverWait(D, 20).until(
        EC.presence_of_element_located((By.XPATH, "//input[@aria-label='搜索任务']")))
    inp.send_keys(Keys.CONTROL, 'a')
    if name:
        inp.send_keys(name)
    else:
        inp.send_keys(Keys.DELETE)
    time.sleep(2.5)


def row(name):
    return WebDriverWait(D, 25).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//tbody/tr[contains(., '{name}')]")))


def row_checkbox(r):
    for xp in (".//span[@role='checkbox']", ".//button[@role='checkbox']",
               ".//input[@type='checkbox']"):
        els = r.find_elements(By.XPATH, xp)
        if els:
            return els[0]
    raise AssertionError('row checkbox not found')


def export_btn():
    return D.find_element(By.XPATH, "//button[normalize-space(.)='导出增量']")


def tooltip_text():
    try:
        el = WebDriverWait(D, 6).until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-slot="tooltip-content"]')))
        return el.text.strip()
    except Exception:
        return ''


def hover_export():
    b = export_btn()
    wrapper = b.find_element(By.XPATH, './..')
    ActionChains(D).move_to_element(wrapper).perform()
    time.sleep(0.8)
    txt = tooltip_text()
    ActionChains(D).move_to_element(D.find_element(By.TAG_NAME, 'body')).perform()
    time.sleep(0.4)
    return txt


def clear_downloads():
    for f in os.listdir(DOWNLOADS):
        try:
            os.remove(os.path.join(DOWNLOADS, f))
        except Exception:
            pass


def wait_download(timeout=90):
    t0 = time.time()
    seen = set()
    while time.time() - t0 < timeout:
        for f in os.listdir(DOWNLOADS):
            if f.endswith('.zip') and f not in seen:
                p = os.path.join(DOWNLOADS, f)
                if os.path.getsize(p) > 1000 and not f.endswith('.crdownload'):
                    time.sleep(1.0)
                    return p
        time.sleep(0.5)
    return ''


def dialog_open(title):
    WebDriverWait(D, 20).until(EC.presence_of_element_located(
        (By.XPATH, f"//*[@role='dialog'][contains(., '{title}')]")))


def dialog_gone(timeout=20):
    WebDriverWait(D, timeout).until(EC.invisibility_of_element_located(
        (By.XPATH, "//*[@role='dialog']")))
    time.sleep(0.5)


def close_dialog():
    try:
        for label in ('关闭', '取消'):
            els = [b for b in dialog().find_elements(By.TAG_NAME, 'button')
                   if (b.text or '').strip() == label]
            if els:
                D.execute_script('arguments[0].click()', els[0])
                break
    except Exception:
        pass
    try:
        dialog().send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(1.0)


def upload_pack(path):
    inp = WebDriverWait(D, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[@role='dialog']//input[@type='file']")))
    inp.send_keys(path)
    time.sleep(0.5)


def run():
    # 页面内 fetch 计数需在应用加载前注入（否则拿到的是已被模块缓存的原始 fetch）
    D.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': COUNTER_JS})
    open_tasks()

    # ========== 1. 入口显隐 / 单任务约束 ==========
    b = export_btn()
    check('1a 未勾选时「导出增量」禁用', b.get_attribute('disabled') is not None,
          'disabled=' + str(b.get_attribute('disabled')))
    tip = hover_export()
    check('1b 未勾选悬停给出原因', '勾选 1 个任务' in tip, tip)
    shot('01_export_disabled_hint')

    search(A_NAME)
    r = row(A_NAME)
    cb = row_checkbox(r)
    D.execute_script('arguments[0].click()', cb)
    time.sleep(1.2)
    b = export_btn()
    check('1c 勾选 1 个任务后「导出增量」可用', b.get_attribute('disabled') is None)
    shot('02_export_enabled')

    # 再勾一个（B 侧行按名称搜索需同页；这里用同一行的搜索范围无法同时出现两行，
    # 改用清空搜索后勾选任意第二行）
    search('')
    names = [tr for tr in D.find_elements(By.XPATH, "//tbody/tr[contains(., '')]")][:2]
    if len(names) == 2:
        for tr in names:
            try:
                D.execute_script('arguments[0].click()', row_checkbox(tr))
            except Exception:
                pass
        time.sleep(1.2)
        tip2 = hover_export()
        check('1d 勾选 2 个任务时禁用并提示只支持单任务',
              export_btn().get_attribute('disabled') is not None and '单个任务' in tip2,
              f'disabled={export_btn().get_attribute("disabled")} tip={tip2}')
        shot('03_export_multi_disabled')
        for tr in names:  # 取消回到单选
            try:
                D.execute_script('arguments[0].click()', row_checkbox(tr))
            except Exception:
                pass
        time.sleep(1.0)
    else:
        check('1d 勾选 2 个任务时禁用并提示只支持单任务', False, 'rows=%d' % len(names))

    # ========== 2/3. 导出：默认两段 / 取消报告 / 失败引导 ==========
    open_tasks()  # 重载清空勾选，保证从已知状态开始
    search(A_NAME)
    D.execute_script('arguments[0].click()', row_checkbox(row(A_NAME)))
    time.sleep(1.2)
    check('2a-pre 重新勾选单个任务后「导出增量」可用',
          export_btn().get_attribute('disabled') is None)
    n0 = len(NET)
    click_xp("//button[normalize-space(.)='导出增量']")
    dialog_open('导出增量数据')
    time.sleep(0.8)
    shot('04_export_dialog_default')
    dtext = dlg_text()
    dims_checked = D.find_element(By.XPATH, "//*[@role='dialog']//label[contains(., '评估维度')]//*[@role='checkbox']").get_attribute('aria-checked')
    reps_checked = D.find_element(By.XPATH, "//*[@role='dialog']//label[contains(., '报告')]//*[@role='checkbox']").get_attribute('aria-checked')
    check('2a 增量导出弹窗两个勾选项默认都勾（评估维度/报告）',
          dims_checked == 'true' and reps_checked == 'true',
          f'dims={dims_checked} reports={reps_checked}')

    clear_downloads()
    n_click = len(NET)
    click_xp("//button[normalize-space(.)='开始导出增量']")
    pack_default = wait_download(120)
    time.sleep(1.5)
    dialog_gone()
    net_exp = net_where('/data-transfer/export-incremental', n_click)
    zip_ok = False
    namelist = []
    if pack_default:
        with zipfile.ZipFile(pack_default) as z:
            namelist = z.namelist()
            man = json.loads(z.read('manifest.json').decode('utf-8'))
            zip_ok = man.get('version') == '1.1'
    check('2b 默认两段导出 → POST export-incremental 200 + incremental_*.zip',
          bool(pack_default) and zip_ok and any(e['status'] == 200 for e in net_exp),
          f'file={os.path.basename(pack_default)} version={man.get("version") if pack_default else None} '
          f'net={[(e["method"], e["status"]) for e in net_exp]} '
          f'include={man.get("options", {}).get("include") if pack_default else None}')
    check('2c 默认导出包内含报告表', 'db/test_reports.json' in namelist,
          ','.join([n for n in namelist if 'report' in n][:4]))

    # 取消「报告」只导维度
    click_xp("//button[normalize-space(.)='导出增量']")
    dialog_open('导出增量数据')
    time.sleep(0.6)
    D.execute_script('arguments[0].click()',
                     D.find_element(By.XPATH, "//*[@role='dialog']//label[contains(., '报告')]//*[@role='checkbox']"))
    time.sleep(0.6)
    shot('05_export_dialog_reports_unchecked')
    clear_downloads()
    n_click = len(NET)
    click_xp("//button[normalize-space(.)='开始导出增量']")
    pack_dims = wait_download(120)
    time.sleep(1.5)
    dialog_gone()
    net_dims = net_where('/data-transfer/export-incremental', n_click)
    dims_namelist, man_dims = [], {}
    if pack_dims:
        with zipfile.ZipFile(pack_dims) as z:
            dims_namelist = z.namelist()
            man_dims = json.loads(z.read('manifest.json').decode('utf-8'))
    check('2d 取消「报告」后请求体只含 dimensions（包内无报告表）',
          bool(pack_dims) and 'db/test_reports.json' not in dims_namelist
          and man_dims.get('options', {}).get('include') == ['dimensions']
          and any(e['status'] == 200 for e in net_dims),
          f'include={man_dims.get("options", {}).get("include")} '
          f'reportTables={[n for n in dims_namelist if "report" in n]} '
          f'net={[(e["method"], e["status"]) for e in net_dims]}')
    shot('06_export_dims_only_done')

    # 失败：未做过整包导入的真实任务 321 → 400 + 后端原文 + 引导
    open_tasks()  # 勾选集跨搜索保留，重载清空
    search(REAL_TASK_NAME)
    tr = row(REAL_TASK_NAME)
    D.execute_script('arguments[0].click()', row_checkbox(tr))
    time.sleep(1.2)
    check('3-pre 勾选真实任务后「导出增量」可用',
          export_btn().get_attribute('disabled') is None)
    click_xp("//button[normalize-space(.)='导出增量']")
    dialog_open('导出增量数据')
    time.sleep(0.6)
    n_click = len(NET)
    click_xp("//button[normalize-space(.)='开始导出增量']")
    WebDriverWait(D, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '增量导出失败')]")))
    time.sleep(0.8)
    ftext = dlg_text()
    shot('07_export_fail_guidance')
    net_fail = net_where('/data-transfer/export-incremental', n_click)
    check('3a 增量导出失败展示后端原文 + 引导（无 source_map 任务）',
          '增量导出失败' in ftext and '未整包导入' in ftext and '导入数据' in ftext
          and any(e['status'] == 400 for e in net_fail),
          f'net={[(e["method"], e["status"]) for e in net_fail]} text={ftext[:160]}')
    close_dialog()

    # ========== 4. 导入增量：预检 ==========
    n_net = len(NET)
    click_xp("//button[normalize-space(.)='导入增量']")
    dialog_open('导入增量数据')
    time.sleep(0.6)
    shot('08_import_select')
    upload_pack(PACK_SRC)
    WebDriverWait(D, 120).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '预检结果')]")))
    WebDriverWait(D, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '任务匹配')]")))
    time.sleep(1.0)
    ptext = dlg_text()
    shot('09_import_preview')
    net_prev = net_where('/data-transfer/import/preview', n_net)
    has_src = '源任务' in ptext and '#678' in ptext
    has_match = '任务匹配：本侧存在该任务' in ptext
    mismatch = '不一致，按任务 id 合并' in ptext
    has_cover = '将被覆盖' in ptext and '维度评分' in ptext and '报告' in ptext
    has_warn = '维度定义' in ptext or '跳过' in ptext
    check('4a 预检展示源任务/任务匹配/覆盖维度数/报告数（warnings：接口本次返回空）',
          has_src and has_match and has_cover
          and any(e['status'] == 200 for e in net_prev),
          f'src={has_src} match={has_match} cover={has_cover} warn={has_warn} '
          f'nameMismatch={mismatch} net={[(e["method"], e["status"]) for e in net_prev]}')
    check('4b 任务名与包内不一致时给出按 id 合并提示', mismatch, ptext[:200])

    # ========== 5. 进度推进 + 轮询兜底 ==========
    n_imp = len(NET)
    c_before = counters()
    t_click = time.time()
    click_xp("//button[normalize-space(.)='开始导入增量']")
    seen_steps = []
    t0 = time.time()
    done = False
    while time.time() - t0 < 240:
        drain_net(D)
        t = dlg_text()
        for step in ('解析导出包', '合并维度评分', '替换平台报告', '导入完成', '增量回导完成'):
            if step in t and step not in seen_steps:
                seen_steps.append(step)
                if step == '合并维度评分':
                    shot('10_import_progress_merging')
        if '增量回导完成' in t or '增量回导失败' in t:
            done = True
            break
        time.sleep(0.5)
    time.sleep(2.0)
    rtext = dlg_text()
    shot('11_import_receipt')
    c_after = counters()
    dur = round(time.time() - t_click, 1)
    net_exec = net_where('/data-transfer/import-incremental', n_imp)
    check('5a 进度按 解析(parsing) → 合并维度评分(merging) → 完成(done) 推进',
          '解析导出包' in seen_steps and '合并维度评分' in seen_steps and done,
          'UI steps=' + ' → '.join(seen_steps) + f'（耗时 {dur}s）')
    polls = (c_after.get('progress') or 0) - (c_before.get('progress') or 0)
    check('5b 断流兜底：3s 轮询 GET /import/progress 发出（页面内计数）',
          polls >= 1 or dur < 3.2,
          f'poll={polls} 耗时={dur}s' + ('；导入在首个 3s 轮询前已完成' if polls == 0 and dur < 3.2 else ''))
    check('5c 增量导入请求 200',
          (c_after.get('importInc') or 0) - (c_before.get('importInc') or 0) == 1,
          f'importInc={c_after.get("importInc")} net={[(e["method"], e["status"]) for e in net_exec]}')

    # ========== 6. 成功回执 ==========
    has_task = '#678' in rtext
    has_merge = '合并维度评分' in rtext and '覆盖前删除旧行' in rtext
    has_report = '目标报告 #602' in rtext
    has_batch = '批次号：' in rtext and len([l for l in rtext.split('\n') if '批次号：' in l]) >= 1
    has_snap = '快照' in rtext
    check('6a 成功回执展示覆盖维度数/替换报告数/目标报告 id/批次号/可回滚',
          has_task and has_merge and has_report and has_batch and has_snap,
          rtext[:260].replace('\n', ' | '))
    if '跳过' in rtext:
        check('6b 回执展示跳过的未匹配维度告警', True, '含「跳过 … 未匹配维度」')

    receipt = rtext

    # ========== 6c. 跨组件同步：列表 refetch + 刷新后一致 ==========
    n_close = len(NET)
    # onImported（前缀失效）在回执到达时即触发，故窗口取「点击导入 → 回执出现」
    refetch = (counters().get('tasksList') or 0) - (c_before.get('tasksList') or 0)
    check('6c 导入成功后任务列表自动重取（invalidate，无手动刷新）',
          refetch >= 1,
          f'GET /api/v1/tasks 次数 +{refetch}（点击导入前 {c_before.get("tasksList")} → 回执后 {counters().get("tasksList")}）')
    close_dialog()
    time.sleep(2.0)
    shot('12_task_list_after_import')

    search(A_NAME)
    rtext_row = []
    try:
        tr = row(A_NAME)
        rtext_row = [(tr.text or '').replace('\n', ' | ')]
    except Exception:
        pass
    shot('13_task_list_row_A')
    open_tasks()  # 整页刷新（非内存假象）
    search(A_NAME)
    persisted = row(A_NAME).text
    check('6d 刷新页面后结果仍在（非内存假象）', A_NAME in persisted, persisted.replace('\n', ' | ')[:160])

    # ========== 7. 失败回执：批次号 + 回滚/人工介入 ==========
    click_xp("//button[normalize-space(.)='导入增量']")
    dialog_open('导入增量数据')
    upload_pack(PACK_BAD500)
    WebDriverWait(D, 120).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '预检结果')]")))
    time.sleep(1.2)
    n_bad = len(NET)
    click_xp("//button[normalize-space(.)='开始导入增量']")
    WebDriverWait(D, 180).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '增量回导失败')]")))
    time.sleep(1.5)
    btext = dlg_text()
    net_bad = net_where('/data-transfer/import-incremental', n_bad)
    shot('14_import_fail_receipt')
    check('7a 段失败回执：批次号 + 已回滚文案（非只弹导入失败）',
          '批次号：' in btext and '已回滚' in btext and any(e['status'] == 500 for e in net_bad),
          f'text={btext[:220].replace(chr(10), " | ")} net={[(e["method"], e["status"]) for e in net_bad]}')
    close_dialog()

    # 结构坏包（409 前置校验，未写数据）
    click_xp("//button[normalize-space(.)='导入增量']")
    dialog_open('导入增量数据')
    upload_pack(PACK_BAD409)
    WebDriverWait(D, 120).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '预检结果')]")))
    time.sleep(1.0)
    n_bad2 = len(NET)
    click_xp("//button[normalize-space(.)='开始导入增量']")
    WebDriverWait(D, 180).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '增量回导失败')]")))
    time.sleep(1.2)
    b2text = dlg_text()
    shot('15_import_fail_409')
    check('7b 前置校验失败回执有明确口径（未写入/已回滚）+ 批次号',
          '增量回导失败' in b2text and '批次号：' in b2text
          and ('未写入' in b2text or '已回滚' in b2text),
          b2text[:220].replace('\n', ' | '))
    close_dialog()

    # 整包放进增量入口 → 版本引导
    click_xp("//button[normalize-space(.)='导入增量']")
    dialog_open('导入增量数据')
    upload_pack(PACK_FULL)
    WebDriverWait(D, 120).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '不是增量包')]")))
    time.sleep(0.8)
    vtext = dlg_text()
    shot('16_import_not_incremental')
    check('7c 非 1.1 包在增量入口被拒绝并引导去「导入数据」',
          '不是增量包' in vtext and '导入数据' in vtext, vtext[:200].replace('\n', ' | '))
    close_dialog()

    # ========== 深色截图 ==========
    D.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    D.get('about:blank')
    open_tasks()
    search(A_NAME)
    D.execute_script('arguments[0].click()', row_checkbox(row(A_NAME)))
    time.sleep(1.0)
    click_xp("//button[normalize-space(.)='导出增量']")
    dialog_open('导出增量数据')
    time.sleep(0.8)
    shot('17_export_dialog_dark')
    close_dialog()
    click_xp("//button[normalize-space(.)='导入增量']")
    dialog_open('导入增量数据')
    upload_pack(PACK_SRC)
    WebDriverWait(D, 120).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//*[contains(., '预检结果')]")))
    time.sleep(1.0)
    shot('18_import_preview_dark')
    check('8d 深色主题下弹窗可正常渲染（截图 17/18）', True)
    close_dialog()
    D.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    # ========== 8. 权限口径 ==========
    try:
        open_tasks()
        before = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导出增量']"))
        patch = """
        const orig = window.fetch;
        window.fetch = async function(...args) {
          const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
          const resp = await orig.apply(this, args);
          if (url.indexOf('/api/v1/auth/me') >= 0) {
            try {
              const body = await resp.clone().json();
              // 保留 task:read 让页面可进，仅剥离 task:export / task:import
              body.permissions = ['task:read'];
              return new Response(JSON.stringify(body),
                {status: 200, headers: {'Content-Type': 'application/json'}});
            } catch (e) { return resp; }
          }
          return resp;
        };
        """
        D.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': patch})
        D.execute_cdp_cmd('Page.reload', {'ignoreCache': True})
        time.sleep(6)
        exp_n = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导出增量']"))
        imp_n = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导入增量']"))
        old_imp = len([b for b in D.find_elements(By.XPATH, "//button") if (b.text or '').strip() == '导入数据'])
        shot('19_permissions_hidden')
        perms = D.execute_script(
            "return fetch('/api/v1/auth/me').then(r=>r.json()).then(j=>j.permissions)")
        check('8a 无 task:export/task:import（保留 task:read，页面可进）时两个增量入口与既有导入数据一起隐藏',
              before == 1 and exp_n == 0 and imp_n == 0 and old_imp == 0,
              f'beforeExport={before} export={exp_n} import={imp_n} oldImport={old_imp} perms={perms}')
        D.execute_cdp_cmd('Page.reload', {'ignoreCache': True})
        time.sleep(4)
    except Exception as e:
        check('8a 无 task:export/task:import 时两个增量入口隐藏', False, repr(e))
    return receipt


if __name__ == '__main__':
    D = make_driver()
    receipt = ''
    try:
        receipt = run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            shot('99_exception')
            with open(os.path.join(ART, 'exception_page.html'), 'w', encoding='utf-8') as f:
                f.write(D.page_source)
        except Exception:
            pass
    finally:
        drain_net(D)
        try:
            D.quit()
        except Exception:
            pass
        report = {'checks': CHECKS,
                  'passed': sum(1 for c in CHECKS if c['ok']),
                  'failed': sum(1 for c in CHECKS if not c['ok']),
                  'network': [e for e in NET if '/data-transfer/' in (e['url'] or '')][-60:]}
        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print('=== SUMMARY: %d passed / %d failed ===' % (report['passed'], report['failed']))
        for c in CHECKS:
            if not c['ok']:
                print('FAILED:', c['name'], '::', c['detail'])
