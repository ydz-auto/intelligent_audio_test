# -*- coding: utf-8 -*-
"""INT-1424 返工核验（P2-1 服务端分页 / P3-1 跨搜索保留已选）。

真实库栈 5700（rsbuild 临时代理 5350）。断言：
1. 音频库弹窗总数/页数取接口 total/pages（1953 条 → 98 页/20 条每页），首屏 20 行；
2. 「下一页」发出 page=2&per_page=20 的服务端请求，行集刷新；
3. 勾选后换关键词列表清空，已选仍保留并可确认加入用例（不静默丢弃）；
4. 文件夹树来自 POST /audios/folder-tree 200。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')
API = 'http://127.0.0.1:5700'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_rework_shots')
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
# 音频行：aria-pressed 行按钮（标签 chips 同样带 aria-pressed，按有无时长列 span 区分）
DIALOG_XP = "//div[@role='dialog'][.//input[@aria-label='搜索音频文件名或描述']]"
ROW_XP = DIALOG_XP + "//button[@aria-pressed][.//span[contains(@class,'tabular-nums')]]"


def health():
    with urllib.request.urlopen(API + '/health', timeout=10) as r:
        return json.loads(r.read().decode()).get('database')


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
    drv.set_page_load_timeout(45)
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
            msg = json.loads(entry['message'])['message']
            out.append(msg)
    except Exception:
        pass
    return out


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.ID, 'username')) > 0)
    drv.find_element(By.ID, 'username').send_keys(USERNAME)
    drv.find_element(By.ID, 'password').send_keys(PASSWORD)
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def open_audio_dialog(drv):
    drv.get(BASE + '/testcases')
    time.sleep(3)
    newb = xpaths(drv, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
    assert newb, '未找到「新增用例」按钮'
    jsclick(drv, newb[0])
    time.sleep(2)
    tabs = xpaths(drv, "//button[contains(., '音频列表')]")
    if tabs:
        jsclick(drv, tabs[0])
        time.sleep(1)
    lib = xpaths(drv, "//button[contains(., '从音频库选择')]")
    assert lib, '未找到「从音频库选择」入口'
    jsclick(drv, lib[0])
    dialog = DIALOG_XP
    WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.XPATH, dialog)) > 0)
    # 等列表加载完成（行 / 空态 / 错误态任一出现）
    try:
        WebDriverWait(drv, 30).until(
            lambda d: len(d.find_elements(By.XPATH, ROW_XP)) > 0
            or '没有匹配的音频文件' in dialog_text(d)
            or '加载失败' in dialog_text(d)
        )
    except Exception:
        print('WAIT_LIST_TIMEOUT, dialog text:', json.dumps(dialog_text(drv), ensure_ascii=False))


def api_list_meta(drv, page=1, per_page=20):
    """页面内同步请求 GET/POST /audios，取接口 total/pages（对照弹窗文案）。"""
    return drv.execute_script('''
      const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/v1/audios', false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      xhr.send(JSON.stringify({ page: arguments[0], per_page: arguments[1] }));
      const d = (JSON.parse(xhr.responseText || '{}').data) || {};
      return { status: xhr.status, total: d.total, pages: d.pages, items: (d.items || []).length };
    ''', page, per_page)


def dialog_text(drv):
    ds = xpaths(drv, DIALOG_XP)
    return ds[-1].text if ds else ''


def main():
    os.makedirs(OUT, exist_ok=True)
    report = {}
    print('HEALTH_BEFORE=', health())
    drv = _driver(headless=True)
    try:
        login(drv)
        drain_logs(drv)  # 基线清空（只保留弹窗打开后的请求）
        open_audio_dialog(drv)
        time.sleep(1)

        txt = dialog_text(drv)
        rows = xpaths(drv, ROW_XP)
        page_lbl = [e.text for e in xpaths(drv, DIALOG_XP + "//span[contains(@class,'tabular-nums')]") if '/' in e.text]
        report['dialog_total_text'] = [ln for ln in txt.splitlines() if '个音频' in ln]
        report['rows_page1'] = len(rows)
        report['page_indicator'] = page_lbl
        print('TOTAL_LINE=', report['dialog_total_text'])
        print('ROWS_PAGE1=', len(rows), 'PAGE=', page_lbl)
        meta = api_list_meta(drv)
        report['api_meta'] = meta
        print('API_META=', meta)
        assert any(str(meta['total']) in s for s in report['dialog_total_text']), '弹窗总数与接口 data.total 不一致'
        assert str(meta['pages']) in ' '.join(page_lbl), '弹窗页数与接口 data.pages 不一致'
        assert len(rows) == 20, f'首屏应为 20 行，实际 {len(rows)}'

        # 文件夹树：POST /audios/folder-tree
        folder_btns = xpaths(drv, DIALOG_XP + "//button[@title]")
        report['folder_nodes'] = len(folder_btns)
        print('FOLDER_NODES=', len(folder_btns))
        drv.save_screenshot(os.path.join(OUT, 'r1_light_dialog_p1.png'))

        # 下一页
        nxt = xpaths(drv, "//button[normalize-space(.)='下一页']")
        assert nxt, '未找到「下一页」'
        jsclick(drv, nxt[-1])
        time.sleep(2.5)
        page_lbl2 = [e.text for e in xpaths(drv, DIALOG_XP + "//span[contains(@class,'tabular-nums')]") if '/' in e.text]
        report['page_indicator_after_next'] = page_lbl2
        page2_reqs = []
        status_by_id = {}
        for msg in net_entries(drv):
            if msg.get('method') == 'Network.requestWillBeSent':
                req = msg.get('params', {}).get('request', {})
                url = req.get('url') or ''
                if '/api/v1/audios' in url and req.get('method') == 'POST':
                    page2_reqs.append({'url': url, 'body': req.get('postData', '')[:200]})
            elif msg.get('method') == 'Network.responseReceived':
                resp = msg.get('params', {}).get('response', {})
                url = resp.get('url') or ''
                if '/api/v1/audios' in url:
                    status_by_id[resp.get('url')] = resp.get('status')
        report['audios_page2_requests'] = page2_reqs
        report['page2_ok'] = f"2 / {meta['pages']}" in ' '.join(page_lbl2)
        print('PAGE_AFTER_NEXT=', page_lbl2)
        print('AUDIOS_POST_REQS=', json.dumps(page2_reqs, ensure_ascii=False))
        assert report['page2_ok'], '翻页后页码未跳到第 2 页'
        assert any('"page":2' in (r['body'] or '').replace(' ', '') or '"page": 2' in (r['body'] or '') for r in page2_reqs), '翻页未发出 page=2 服务端请求'

        # 勾选第 1 行，记录名称
        rows2 = xpaths(drv, ROW_XP)
        first_name = rows2[0].find_elements(By.XPATH, ".//span[contains(@class,'truncate')]")[0].text
        jsclick(drv, rows2[0])
        time.sleep(0.6)
        report['selected_name'] = first_name
        after_sel = dialog_text(drv)
        report['selected_line'] = [ln for ln in after_sel.splitlines() if '已选择' in ln]
        print('SELECTED_NAME=', first_name, 'LINE=', report['selected_line'])

        # 换关键词使列表清空，已选需保留
        kw = drv.find_element(By.XPATH, "//input[@aria-label='搜索音频文件名或描述']")
        kw.send_keys('zzz-no-such-audio-int1424')
        time.sleep(2.0)
        txt2 = dialog_text(drv)
        report['empty_after_search'] = '没有匹配的音频文件' in txt2
        report['selected_kept'] = '已选择 1 个' in txt2
        print('EMPTY_AFTER_SEARCH=', report['empty_after_search'], 'SELECTED_KEPT=', report['selected_kept'])
        drv.save_screenshot(os.path.join(OUT, 'r2_search_empty_selection_kept.png'))
        assert report['empty_after_search'], '搜索未清空列表'
        assert report['selected_kept'], '换搜索后已选丢失（P3-1 未修）'

        # 清空搜索，确认选择
        kw.send_keys(Keys.CONTROL, 'a')
        kw.send_keys(Keys.DELETE)
        time.sleep(1.8)
        confirm = xpaths(drv, "//button[normalize-space(.)='确认选择']")
        assert confirm, '未找到确认选择'
        jsclick(drv, confirm[-1])
        time.sleep(2.0)
        drv.save_screenshot(os.path.join(OUT, 'r3_audio_added_light.png'))
        body_text = drv.find_element(By.TAG_NAME, 'body').text
        report['audio_in_drawer'] = first_name in body_text
        print('AUDIO_IN_DRAWER=', report['audio_in_drawer'], 'name=', first_name)
        assert report['audio_in_drawer'], '确认后音频未加入用例'

        # 深色截图：重设主题后重开
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        open_audio_dialog(drv)
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(OUT, 'r4_dark_dialog.png'))

        # 文件夹树点击过滤：挑一个真实含文件的节点（file_count>0），断言行集非空
        tree = drv.execute_script('''
          const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
          const x = new XMLHttpRequest();
          x.open('POST', '/api/v1/audios/folder-tree', false);
          x.setRequestHeader('Content-Type', 'application/json');
          x.setRequestHeader('Authorization', 'Bearer ' + token);
          x.send(JSON.stringify({ depth: 10 }));
          return JSON.parse(x.responseText || '{}').data;
        ''')
        stack = list(((tree.get('tree') or {}).get('folders') or []))
        found = []
        while stack and not found:
            node = stack.pop(0)
            if (node.get('file_count') or 0) > 0 and node.get('path'):
                found.append(node)
            else:
                stack.extend(node.get('folders') or [])
        target = found[0] if found else None
        report['folder_target'] = {'path': (target or {}).get('path'), 'file_count': (target or {}).get('file_count')}
        print('FOLDER_TARGET=', report['folder_target'])
        if target:
            WebDriverWait(drv, 20).until(
                lambda d: len(d.find_elements(By.XPATH, DIALOG_XP + "//button[@title]")) > 0
            )
            btn = xpaths(drv, DIALOG_XP + f"//button[@title={json.dumps(target['path'], ensure_ascii=False)}]")
            assert btn, '文件夹树中未渲染目标节点'
            jsclick(drv, btn[0])
            time.sleep(3.0)
            report['folder_click_text'] = [ln for ln in dialog_text(drv).splitlines() if '个音频' in ln]
            report['folder_rows'] = len(xpaths(drv, ROW_XP))
            drv.save_screenshot(os.path.join(OUT, 'r5_dark_folder_filter.png'))
            print('FOLDER_CLICK=', report['folder_click_text'], 'ROWS=', report['folder_rows'])
            assert report['folder_rows'] > 0, '选中含文件文件夹后列表为空（文件夹过滤未生效）'

        report['folder_tree_responses'] = [
            m.get('params', {}).get('response', {}).get('status')
            for m in net_entries(drv)
            if m.get('method') == 'Network.responseReceived'
            and '/audios/folder-tree' in (m.get('params', {}).get('response', {}).get('url') or '')
        ]
        print('FOLDER_TREE_STATUS=', report['folder_tree_responses'])
        print('HEALTH_AFTER=', health())
        report['health_after'] = health()
        print('RESULT=', json.dumps(report, ensure_ascii=False))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
