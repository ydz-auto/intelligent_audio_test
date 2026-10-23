# -*- coding: utf-8 -*-
"""INT-1424 终审返工核验（P2-1 整体评估维度回显 / P2-2 实验室试听播放设备 / P3-1 文件夹视图翻页 / P3-2 标签限高 / P3-3 弹窗横向溢出）。

环境：docker 后端 http://localhost:15000（库 intelligent_audio_test）+ 本 worktree dev :5373（临时代理）。
断言：
1. 刷新页面后首次编辑带 config.dimensions 的用例 →「启用整体评估」开关为开、维度参数卡完整回显；
2. 音频卡「试听」→ 实验室播放 → Network POST /audios/{id}/preview 的 device_unique_ids / playback_device_ids 非空；
3. 音频库弹窗文件夹视图翻页不再重打 per_page=10000 请求；
4. 标签搜索命中 >12 枚时标签区限高滚动；
5. 弹窗无横向溢出（scrollWidth <= clientWidth）。
"""
import io
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5373')
API = 'http://127.0.0.1:15000'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_fix2_shots')
CASE_ID = '929e5dbb-2279-4b66-8cb4-23da895db367'
CASE_KEY = 'JG0081'

DIALOG_XP = "//div[@role='dialog'][.//input[@aria-label='搜索音频文件名或描述']]"
ROW_XP = DIALOG_XP + "//button[@aria-pressed][.//span[contains(@class,'tabular-nums')]]"


def health():
    with urllib.request.urlopen(API + '/health', timeout=20) as r:
        return json.loads(r.read().decode()).get('database')


def api_case(case_id):
    with urllib.request.urlopen(f'{API}/api/v1/testcases/{case_id}', timeout=60) as r:
        body = json.loads(r.read().decode())
    return body.get('data') or {}


def _driver(headless=True):
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    vv = tuple(int(x) for x in ver.split('.') if x.isdigit())
                    if vv and vv[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(180)
    return drv


def jsclick(drv, el):
    drv.execute_script('arguments[0].click()', el)


def xpaths(drv, xp):
    return drv.find_elements(By.XPATH, xp)


def drain_logs(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def net_entries(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            out.append(json.loads(entry['message'])['message'])
    except Exception:
        pass
    return out


def open_case_drawer(drv, keyword=CASE_KEY):
    """刷新用例页（抽屉 state 归零）→ 按标签视图 + 关键词 → 展开分组 → 点「编辑用例」。

    按分组视图的搜索不收敛分组卡（既有分页/分组口径），按标签视图搜索能直接命中。
    """
    drv.get(BASE + '/testcases/by-tag')
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.XPATH, "//input[@placeholder='搜索用例名称或描述']")) > 0)
    time.sleep(2)
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或描述']")
    box.send_keys(keyword)
    time.sleep(4)
    hdr = "//div[contains(@class,'cursor-pointer')][.//span[contains(@class,'font-medium')]]"
    for _ in range(3):
        edits = xpaths(drv, "//button[@aria-label='编辑用例']")
        if edits:
            break
        for h in xpaths(drv, hdr)[:8]:
            try:
                jsclick(drv, h)
            except Exception:
                pass
        time.sleep(2)
    edits = xpaths(drv, "//button[@aria-label='编辑用例']")
    assert edits, '未找到「编辑用例」按钮（分组未展开或搜索无结果）'
    jsclick(drv, edits[0])
    WebDriverWait(drv, 40).until(lambda d: len(d.find_elements(By.XPATH, "//*[normalize-space(.)='整体评估维度']")) > 0)
    time.sleep(2)


def section_node(drv):
    return drv.execute_script('''
      const heads = [...document.querySelectorAll('h4')].filter(h => h.textContent.trim() === '整体评估维度');
      if (!heads.length) return null;
      let n = heads[0];
      for (let i = 0; i < 4; i++) if (n.parentElement) n = n.parentElement;
      return n;
    ''')


def section_text(drv):
    return drv.execute_script('''
      const heads = [...document.querySelectorAll('h4')].filter(h => h.textContent.trim() === '整体评估维度');
      if (!heads.length) return '';
      let n = heads[0];
      for (let i = 0; i < 4; i++) if (n.parentElement) n = n.parentElement;
      return n.innerText || '';
    ''')


def main():
    os.makedirs(OUT, exist_ok=True)
    report = {}
    print('HEALTH_1=', health())

    case = api_case(CASE_ID)
    cfg = case.get('config') or {}
    dims = cfg.get('dimensions') or []
    rounds = cfg.get('rounds') or []
    audios = (rounds[0].get('audios') if rounds else []) or []
    print('CASE_DIMS=', len(dims), [d.get('name') for d in dims][:4])
    print('CASE_AUDIO=', {k: audios[0].get(k) for k in ('audio_id', 'audio_name', 'playback_device_id')} if audios else None)
    report['case_dims'] = [d.get('name') for d in dims]
    report['case_audio'] = {k: audios[0].get(k) for k in ('audio_id', 'playback_device_id')} if audios else None

    drv = _driver()
    try:
        drv.get(BASE + '/testcases')
        time.sleep(2)
        drv.execute_script("try { window.localStorage.setItem('iatp:theme:v1:mode','light') } catch (e) {}")
        drain_logs(drv)

        # ---------- P2-1 整体评估维度回显 ----------
        open_case_drawer(drv)
        sw = xpaths(drv, "//*[@role='switch'][@aria-label='启用整体评估']")
        assert sw, '未找到「启用整体评估」开关'
        checked = sw[0].get_attribute('aria-checked')
        has_checked_attr = drv.execute_script("return arguments[0].hasAttribute('data-checked')", sw[0])
        print('SWITCH_ARIA_CHECKED=', checked, 'DATA_CHECKED=', has_checked_attr)
        report['switch_aria_checked'] = checked
        assert checked == 'true' or has_checked_attr, '整体评估开关未按 config.dimensions 回显为开'
        sec_text = section_text(drv)
        report['section_has_weight'] = '权重' in sec_text
        report['section_has_threshold'] = '阈值' in sec_text
        report['section_dim_names'] = [n for n in report['case_dims'] if n in sec_text]
        print('SECTION_DIMS_HIT=', len(report['section_dim_names']), report['section_dim_names'][:3])
        assert report['section_has_weight'] and report['section_has_threshold'], '已选维度参数卡未回显'
        assert report['section_dim_names'], '维度勾选未回显'
        node = section_node(drv)
        assert node is not None, '未定位到「整体评估维度」节'
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', node)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(OUT, 'f1_overall_dims_light.png'))

        # ---------- P2-2 实验室试听播放设备 ----------
        tabs = xpaths(drv, "//button[normalize-space(.)='音频列表']")
        assert tabs, '未找到「音频列表」步骤'
        jsclick(drv, tabs[0])
        time.sleep(1.5)
        audition = xpaths(drv, "//button[@aria-label='试听']")
        assert audition, '音频卡无「试听」按钮'
        drain_logs(drv)
        jsclick(drv, audition[0])
        WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.XPATH, "//*[normalize-space(.)='音频试听配置']")) > 0)
        time.sleep(1)
        lab = xpaths(drv, "//label[.//span[contains(., '实验室播放')]]")
        assert lab, '未找到「实验室播放」选项'
        jsclick(drv, lab[0])
        time.sleep(0.5)
        jsclick(drv, xpaths(drv, "//button[normalize-space(.)='开始试听']")[0])
        time.sleep(1.5)
        play = xpaths(drv, "//button[@aria-label='播放']")
        assert play, '播放器未出现播放钮'
        jsclick(drv, play[0])
        time.sleep(3)

        preview_reqs = []
        for msg in net_entries(drv):
            if msg.get('method') == 'Network.requestWillBeSent':
                req = msg.get('params', {}).get('request', {})
                url = req.get('url', '')
                if '/preview' in url and req.get('method') == 'POST':
                    preview_reqs.append({'url': url, 'body': req.get('postData')})
        report['preview_requests'] = preview_reqs
        print('PREVIEW_REQS=', json.dumps(preview_reqs, ensure_ascii=False)[:600])
        assert preview_reqs, '未捕获 POST /audios/{id}/preview 请求'
        body = json.loads(preview_reqs[-1]['body'] or '{}')
        assert body.get('device_unique_ids'), 'device_unique_ids 为空：播放设备未按用例配置发送'
        assert body.get('playback_device_ids'), 'playback_device_ids 为空'
        report['preview_body'] = body
        drv.save_screenshot(os.path.join(OUT, 'f2_preview_lab_light.png'))

        # ---------- 深色截图 ----------
        drv.execute_script("try { window.localStorage.setItem('iatp:theme:v1:mode','dark') } catch (e) {}")
        drv.get('about:blank')
        open_case_drawer(drv)
        sw = xpaths(drv, "//*[@role='switch'][@aria-label='启用整体评估']")
        report['dark_switch_checked'] = sw[0].get_attribute('aria-checked') if sw else None
        node = section_node(drv)
        assert node is not None, '未定位到「整体评估维度」节'
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', node)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(OUT, 'f1_overall_dims_dark.png'))
        assert report['dark_switch_checked'] == 'true' or (
            sw and drv.execute_script("return arguments[0].hasAttribute('data-checked')", sw[0])
        ), '深色下整体评估开关未回显为开'

        # ---------- P3-1 / P3-2 / P3-3 音频库弹窗 ----------
        drv.execute_script("try { window.localStorage.setItem('iatp:theme:v1:mode','light') } catch (e) {}")
        drv.get('about:blank')
        drv.get(BASE + '/testcases')
        time.sleep(3)
        newb = xpaths(drv, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        assert newb, '未找到「新增用例」'
        jsclick(drv, newb[0])
        time.sleep(2)
        lib = xpaths(drv, "//button[contains(., '从音频库选择')]")
        if not lib:
            tabs = xpaths(drv, "//button[normalize-space(.)='音频列表']")
            assert tabs, '抽屉内没有音频列表步骤'
            jsclick(drv, tabs[0])
            time.sleep(1.5)
            lib = xpaths(drv, "//button[contains(., '从音频库选择')]")
        assert lib, '未找到「从音频库选择」入口'
        jsclick(drv, lib[0])
        WebDriverWait(drv, 30).until(lambda d: len(d.find_elements(By.XPATH, DIALOG_XP)) > 0)
        WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.XPATH, ROW_XP)) > 0)
        time.sleep(1)

        # 弹窗横向溢出
        overflow = drv.execute_script('''
          const d = [...document.querySelectorAll("div[role='dialog']")].pop();
          const el = d.querySelector('[data-slot="dialog-content"]') || d;
          const r = { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
          // 逐个子元素找溢出源
          r.wide = [...el.querySelectorAll('*')].filter(n => n.getBoundingClientRect().right > el.getBoundingClientRect().right + 1)
              .slice(0, 4).map(n => (n.tagName + '.' + (n.className || '')).slice(0, 120));
          return r;
        ''')
        report['dialog_overflow'] = overflow
        print('DIALOG_OVERFLOW=', json.dumps(overflow, ensure_ascii=False)[:500])
        assert overflow['scrollWidth'] <= overflow['clientWidth'], '弹窗横向溢出（scrollWidth > clientWidth）'

        # 标签：展开全部后限高滚动
        exp = xpaths(drv, "//button[contains(., '展开全部')]")
        assert exp, '未找到「展开全部」标签按钮'
        jsclick(drv, exp[0])
        time.sleep(1)
        tag_box = drv.execute_script('''
          const b = document.querySelector('[data-testid="audio-tag-filter"]');
          return b ? { clientHeight: b.clientHeight, scrollHeight: b.scrollHeight, chips: b.querySelectorAll('[data-testid="audio-tag-chip"]').length } : null;
        ''')
        report['tag_filter'] = tag_box
        print('TAG_FILTER=', tag_box)
        assert tag_box and tag_box['chips'] > 12, '标签未展开'
        assert tag_box['clientHeight'] <= 165, '展开全部后标签区未限高'
        assert tag_box['scrollHeight'] > tag_box['clientHeight'], '展开全部后标签区未内层滚动'
        drv.save_screenshot(os.path.join(OUT, 'f3_tag_expanded.png'))

        # 文件夹视图翻页：不再重打 per_page=10000
        folders = xpaths(drv, DIALOG_XP + "//button[@data-testid='audio-folder-node']")
        assert folders, '文件夹树为空'
        big = [f for f in folders if '多次打断' in f.text]
        target_folder = big[0] if big else folders[0]
        jsclick(drv, target_folder)
        time.sleep(5)
        nxt = xpaths(drv, "//button[normalize-space(.)='下一页']")
        assert nxt, '文件夹视图未出现「下一页」（该文件夹不足一页）'
        drain_logs(drv)
        jsclick(drv, nxt[-1])
        time.sleep(4)
        reqs = []
        for msg in net_entries(drv):
            if msg.get('method') == 'Network.requestWillBeSent':
                req = msg.get('params', {}).get('request', {})
                if '/audios' in req.get('url', '') and req.get('method') == 'POST':
                    reqs.append(req.get('postData'))
        report['folder_page_requests'] = reqs
        print('FOLDER_PAGE_REQS=', reqs)
        assert not any('10000' in (b or '') for b in reqs), '文件夹视图翻页仍重拉全量 1 万行'
        drv.save_screenshot(os.path.join(OUT, 'f4_folder_view.png'))

        print('HEALTH_2=', health())
        print('HEALTH_3=', health())
        print('REPORT=', json.dumps(report, ensure_ascii=False)[:4000])
        with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('ALL_ASSERTIONS_PASSED')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
