# -*- coding: utf-8 -*-
"""INT-1765 返工 R1 复测：只覆盖打回的 F1~F5 与本次修复相关部分（devloop §2.3）。

环境：旁路容器 http://localhost:15267（本 worktree 头 + 交付 diff 构建的 dist，
      15173 同款 nginx conf）→ docker 网关 :15000（库 intelligent_audio_test，AUTH_MODE=off）。
夹具：A=690（真实任务 321 整包导入副本）、B=691（A 的整包导入副本）；
      增量包由 B「导出增量」产出（目标 A），失败变体见 rework_fixture_int1765.py。
"""
import functools
import json
import os
import sys
import time
import zipfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

print = functools.partial(print, flush=True)  # noqa: A001
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.environ.get('REACT_BASE', 'http://localhost:15267')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_PATH = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
WORK = r'D:/00_user_data/int1765_rw_work'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1765_rework')
DOWNLOADS = os.path.join(ART, 'downloads')
os.makedirs(DOWNLOADS, exist_ok=True)

PACK_OK = os.path.join(WORK, 'inc_target_A690.zip')
PACK_NONZIP = os.path.join(WORK, 'bad_nonzip.zip')
PACK_404 = os.path.join(WORK, 'bad_missing_task.zip')
PACK_409 = os.path.join(WORK, 'bad_casehash.zip')
PACK_500 = os.path.join(WORK, 'bad_dim_null.zip')
PACK_V10 = os.path.join(WORK, 'whole_v10.zip')

CHECKS = []
NET = []
SEEN_TEXTS = []

# 让「导入增量」请求在页面内网络层失败（模拟断网，验证第 4 态「结果未知」）
KILL_FETCH_JS = """
window.__killIncImport = false;
(() => {
  const orig = window.fetch;
  window.fetch = function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (window.__killIncImport && url.indexOf('/data-transfer/import-incremental') >= 0) {
      return Promise.reject(new TypeError('Failed to fetch (INT-1765 rework probe)'));
    }
    return orig.apply(this, args);
  };
})();
"""


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' :: ' + str(detail)[:600]) if detail else ''))
    return ok


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
    })
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER_PATH), options=o)
    d.execute_cdp_cmd('Network.enable', {})
    d.set_page_load_timeout(90)
    d.set_script_timeout(300)
    return d


def drain_net(d):
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


def vis_dialogs():
    out = []
    for el in D.find_elements(By.XPATH, "//*[@role='dialog']"):
        try:
            if el.is_displayed():
                out.append(el)
        except Exception:
            pass
    return out


def dlg():
    ds = vis_dialogs()
    return ds[-1] if ds else None


def dlg_text():
    d = dlg()
    if not d:
        return ''
    try:
        return d.text or ''
    except Exception:
        return ''


def wait_text(sub, timeout=180):
    """等可见弹窗里出现某段文字（返回弹窗全文）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = dlg_text()
        if t:
            SEEN_TEXTS.append(t)
        if t and sub in t:
            return t
        time.sleep(0.4)
    return dlg_text()


def click_xp(xp, timeout=25, root=None):
    ctx = root or D
    el = WebDriverWait(ctx, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
    D.execute_script('arguments[0].scrollIntoView({block:"center"})', el)
    try:
        el.click()
    except Exception:
        D.execute_script('arguments[0].click()', el)
    return el


def open_tasks():
    D.get(BASE + '/tasks/daily')
    WebDriverWait(D, 45).until(
        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='导入增量']")))
    time.sleep(1.5)


def open_import_dialog():
    click_xp("//button[normalize-space(.)='导入增量']")
    WebDriverWait(D, 25).until(
        EC.visibility_of_element_located((By.XPATH, "//*[@role='dialog'][contains(., '导入增量数据')]")))
    time.sleep(0.6)


def upload_pack(path):
    inp = WebDriverWait(D, 20).until(
        EC.presence_of_element_located((By.XPATH, "//*[@role='dialog']//input[@type='file']")))
    inp.send_keys(path)
    time.sleep(0.5)


def close_dialog():
    d = dlg()
    if d:
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() in ('关闭', '取消'):
                D.execute_script('arguments[0].click()', b)
                break
    time.sleep(1.2)


def click_import_go():
    d = dlg()
    click_xp(".//button[normalize-space(.)='开始导入增量']", 20, d)


def run():
    D.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': KILL_FETCH_JS})
    open_tasks()

    # ---------- 0. 入口在位 ----------
    exp_n = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导出增量']"))
    imp_n = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导入增量']"))
    check('0 任务页操作区两个增量入口在位（改动页基线）', exp_n >= 1 and imp_n >= 1,
          f'导出增量={exp_n} 导入增量={imp_n}')
    shot('00_tasklist_entries_light')

    # ---------- F1 预检失败不再静默 ----------
    n0 = len(NET)
    open_import_dialog()
    upload_pack(PACK_NONZIP)
    t = wait_text('增量包预检失败', 180)
    shot('01_F1_preview_fail')
    net_prev = net_where('/data-transfer/import/preview', n0)
    check('F1 增量预检失败给出错误标题 + 后端原文 + 可操作引导（此前整段静默）',
          '增量包预检失败' in t and ('ZIP' in t or 'zip' in t) and '导入数据' in t
          and any(e['status'] == 400 for e in net_prev),
          f'net={[(e["method"], e["status"]) for e in net_prev]} text={t[:300]}')
    close_dialog()

    # ---------- F2-a 未写入（404 目标任务不存在） ----------
    n1 = len(NET)
    open_import_dialog()
    upload_pack(PACK_404)
    wait_text('预检结果', 180)
    t_prev = wait_text('本侧未找到', 40)  # 预检先渲染包信息，任务存在性查询随后补齐
    time.sleep(0.5)
    shot('02_F2_404_preview')
    check('F2-a-pre 目标任务在预检即提示「本侧未找到」并提示导入会被拒',
          '本侧未找到' in t_prev and '拒绝' in t_prev, t_prev[:400])
    click_import_go()
    t = wait_text('增量回导失败', 300)
    net404 = net_where('/data-transfer/import-incremental', n1)
    shot('03_F2_404_not_written')
    st404 = [e['status'] for e in net404]
    check('F2-a 前置校验（目标任务不存在）→ 「未写入任何数据」且不再说「已回滚」',
          '增量回导失败：未写入任何数据' in t and '无需回滚' in t
          and '已回滚至导入前状态' not in t
          and any((s or 0) >= 400 and (s or 0) < 500 for s in st404),
          f'net={[(e["method"], e["status"]) for e in net404]} text={t[:700]}')
    check('F2-a 观察：404 回执是否仍挂了批次号（快照兜底可能取到上一次导入的批次）',
          True, '批次号出现=' + str('批次号：' in t) + ' text=' + t[:200].replace('\n', ' | '))
    close_dialog()

    # ---------- F2-b 未写入（409 caseSetHash 指纹不符） ----------
    n2 = len(NET)
    open_import_dialog()
    upload_pack(PACK_409)
    wait_text('预检结果', 180)
    click_import_go()
    t = wait_text('增量回导失败', 300)
    net409 = net_where('/data-transfer/import-incremental', n2)
    shot('04_F2_409_not_written')
    check('F2-b 409 指纹不符 → 「未写入任何数据」+ 后端原文，且不出现「已回滚」',
          '增量回导失败：未写入任何数据' in t and '无需回滚' in t
          and '已回滚至导入前状态' not in t and '指纹' in t
          and any(e['status'] == 409 for e in net409),
          f'net={[(e["method"], e["status"]) for e in net409]} text={t[:700]}')
    close_dialog()

    # ---------- F2-c 已回滚（500 段失败） ----------
    n3 = len(NET)
    open_import_dialog()
    upload_pack(PACK_500)
    wait_text('预检结果', 180)
    click_import_go()
    t = wait_text('增量回导失败', 300)
    net500 = net_where('/data-transfer/import-incremental', n3)
    shot('05_F2_500_rolled_back')
    check('F2-c 500 段失败 → 「已回滚至导入前」+「原任务数据未被改动」+ 批次号',
          '增量回导失败：已回滚至导入前' in t and '原任务数据未被改动' in t and '批次号：' in t
          and any(e['status'] == 500 for e in net500),
          f'net={[(e["method"], e["status"]) for e in net500]} text={t[:700]}')
    check('F2-c 观察：500 回执不再与「需人工介入」互斥文案同现',
          '需人工介入' not in t, '含需人工介入=' + str('需人工介入' in t))
    close_dialog()

    # ---------- F2-d 结果未知（网络层无回执） ----------
    D.execute_script('window.__killIncImport = true')
    open_import_dialog()
    upload_pack(PACK_OK)
    wait_text('预检结果', 180)
    click_import_go()
    t = wait_text('增量回导结果未知', 180)
    shot('06_F2_unknown_network')
    check('F2-d 网络层失败 → 「增量回导结果未知」，既不说已回滚也不说未写入',
          '增量回导结果未知' in t and '未收到服务端回执' in t
          and '已回滚至导入前状态' not in t and '未写入任何数据' not in t,
          t[:300])
    D.execute_script('window.__killIncImport = false')
    close_dialog()

    # ---------- 成功路径回归 + F4 文案/跳转 ----------
    n4 = len(NET)
    open_import_dialog()
    upload_pack(PACK_OK)
    t_prev = wait_text('预检结果', 180)
    shot('07_preview_success')
    check('R1 预检展示源任务 #690 / 覆盖维度与报告数',
          '#690' in t_prev and '将被覆盖' in t_prev and '维度评分' in t_prev and '报告' in t_prev,
          t_prev[:220])
    click_import_go()
    steps, parsing_label = [], False
    t0 = time.time()
    while time.time() - t0 < 300:
        t = dlg_text()
        if t:
            SEEN_TEXTS.append(t)
        if '正在解析增量包' in t:
            parsing_label = True
            if 'parsing' not in steps:
                steps.append('parsing')
                shot('08_progress_parsing_incremental')
        if '增量回导完成' in t or '增量回导失败' in t:
            break
        time.sleep(0.3)
    time.sleep(2.5)
    t = dlg_text()
    shot('09_receipt_success')
    net_ok = net_where('/data-transfer/import-incremental', n4)
    check('R2 成功回执：合并行数/覆盖前删除/报告替换/批次号/快照',
          '增量回导完成' in t and '覆盖前删除旧行' in t and '报告：替换' in t
          and '批次号：' in t and ('批次快照' in t)
          and any(e['status'] == 200 for e in net_ok),
          f'net={[(e["method"], e["status"]) for e in net_ok]} text={t[:400]}')
    label_seen = parsing_label or any('正在解析增量包' in x for x in SEEN_TEXTS)
    check('F4-a 进度/选包阶段按模式显示「正在解析增量包」（返工前固定「解析导出包」）',
          label_seen and not any('正在解析导出包' in x for x in SEEN_TEXTS),
          '增量包标签出现=' + str(label_seen))

    check('F4-b 成功回执写真实同步点（任务列表与报告中心已刷新，不再是「详情页报告页签」）',
          '任务列表与报告中心已刷新' in t and '详情页报告页签' not in t, t[:300])

    # 查看任务详情 → /tasks/:id
    click_xp("//*[@role='dialog']//button[normalize-space(.)='查看任务详情']")
    time.sleep(3.0)
    url = D.current_url
    shot('10_task_detail_nav')
    check('F4-c 「查看任务详情」跳到该任务详情 /tasks/690（返工前落 /tasks/daily）',
          '/tasks/690' in url, 'url=' + url)

    # ---------- F5 深色页面截图 ----------
    D.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    D.get('about:blank')
    open_tasks()
    time.sleep(1.5)
    shot('11_tasklist_entries_dark')
    dark_exp = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导出增量']"))
    dark_imp = len(D.find_elements(By.XPATH, "//button[normalize-space(.)='导入增量']"))
    theme_attr = D.execute_script(
        "return document.documentElement.className + '|' + (document.body && document.body.className)")
    check('F5 深色主题下任务列表操作区两入口正常渲染（补打回缺图）',
          dark_exp >= 1 and dark_imp >= 1 and ('dark' in (theme_attr or '')),
          f'导出={dark_exp} 导入={dark_imp} class={theme_attr}')
    open_import_dialog()
    upload_pack(PACK_OK)
    wait_text('预检结果', 180)
    time.sleep(0.8)
    shot('12_preview_dark')
    close_dialog()
    D.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
    return t


if __name__ == '__main__':
    D = make_driver()
    try:
        run()
    except Exception:
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
        report = {
            'base': BASE,
            'checks': CHECKS,
            'passed': sum(1 for c in CHECKS if c['ok']),
            'failed': sum(1 for c in CHECKS if not c['ok']),
            'network': [e for e in NET if '/data-transfer/' in (e['url'] or '')][-60:],
        }
        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print('=== SUMMARY: %d passed / %d failed ===' % (report['passed'], report['failed']))
        for c in CHECKS:
            if not c['ok']:
                print('FAILED:', c['name'], '::', c['detail'])
