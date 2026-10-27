# -*- coding: utf-8 -*-
"""INT-2090 browser verification — deterministic long audio-name rendering.

Uses a narrowly-scoped window.fetch override (in-page, real backend responses) that
rewrites only the audio-name fields of the two wired endpoints to a ~150-char name:
  - POST/GET /api/v1/reports/{id}/cases/search        (report side: audios[].audio_name)
  - GET /api/v1/tasks/{id}/cases/{cid}/detail          (task side: audio_list[].filename,
                                                       result_audios[*].filename,
                                                       algorithm_results[].label for audio_file)
All other requests pass through untouched. This is a rendering fixture only — no DB writes.

Verifies: player modal title truncation (light+dark), result-audio Badge truncation,
case-detail reference/result audio row truncation, no horizontal overflow, console no SEVERE.
"""
import json
import os
import sys
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://localhost:5388'
ART = r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-2090-93d04ec988e4\worktree\_int2090\artifacts'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

LONG_NAME = '超长音频名称渲染验证_' + '这是一段非常长的音频文件名用于验证超长音频名不破坏播放器布局_2026验证超长音频.wav'.ljust(120, 'x')


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="username"]')))
    drv.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys('admin')
    drv.find_element(By.CSS_SELECTOR, 'input[name="password"]').send_keys('admin123')
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if '登录' in (b.text or '').replace(' ', ''):
            b.click()
            break
    time.sleep(3)
    assert drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')||''"), 'login failed'


def install_override(drv):
    """Install narrow fetch override rewriting audio-name fields in the two endpoints."""
    script = r'''
    if (window.__int2090OverrideInstalled) return true;
    window.__int2090OverrideInstalled = true;
    const LONG = arguments[0];
    const orig = window.fetch.bind(window);
    function rewriteCaseAudio(o) {
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o.audios)) {
        o.audios.forEach(a => { if (a && typeof a === 'object') a.audio_name = LONG; });
      }
      if (Array.isArray(o.algorithmResults) || (o.algorithm_results && Array.isArray(o.algorithm_results))) {
        const arr = o.algorithmResults || o.algorithm_results;
        arr.forEach(a => {
          if (a && (a.param_type === 'audio_file' || a.paramType === 'audio_file')) a.label = LONG;
        });
      }
    }
    function rewriteDetail(o) {
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o.audio_list)) o.audio_list.forEach(a => { if (a) a.filename = LONG; });
      if (o.result_audios && typeof o.result_audios === 'object') {
        Object.values(o.result_audios).forEach(arr => (arr||[]).forEach(a => { if (a) a.filename = LONG; }));
      }
      if (Array.isArray(o.algorithm_results)) {
        o.algorithm_results.forEach(a => { if (a && a.param_type === 'audio_file') a.label = LONG; });
      }
    }
    window.fetch = function(input, init) {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      return orig(input, init).then(resp => {
        try {
          if (!resp.ok) return resp;
          const ct = (resp.headers.get('content-type') || '');
          if (!ct.includes('application/json')) return resp;
          if (url.includes('/cases/search') || (url.includes('/cases/') && url.endsWith('/detail'))) {
            return resp.clone().json().then(j => {
              if (url.includes('/cases/search')) {
                const data = j.data || j;
                if (Array.isArray(data.items)) data.items.forEach(rewriteCaseAudio);
                if (Array.isArray(data)) data.forEach(rewriteCaseAudio);
              } else {
                rewriteDetail(j.data || j);
              }
              return new Response(JSON.stringify(j), { status: resp.status, headers: { 'Content-Type': 'application/json' } });
            });
          }
          return resp;
        } catch (e) { return resp; }
      });
    };
    return true;
    '''
    drv.execute_script(script, LONG_NAME)


def set_theme(drv, mode):
    drv.execute_script(f"localStorage.setItem('iatp:theme:v1:mode','{mode}')")


def console_severe(drv):
    return [e.get('message') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']


def modal_evidence(drv, tag):
    data = drv.execute_script(
        "const dlg=document.querySelectorAll('[data-slot=\"dialog-content\"]');"
        "let el=null; for(const d of dlg){const p=d.querySelector('p.truncate'); if(p && p.textContent.trim()){el=d; break;}}"
        "if(!el) return {err:'no player dialog'};"
        "const title=el.querySelector('p.truncate');"
        "return {dialogClientW: el.clientWidth, dialogScrollW: el.scrollWidth,"
        " titleText: title.textContent, titleClientW: title.clientWidth, titleScrollW: title.scrollWidth,"
        " titleTruncated: title.scrollWidth>title.clientWidth+1,"
        " titleHasAttr: !!title.getAttribute('title') && title.getAttribute('title').length>0,"
        " playBtn: !!Array.from(el.querySelectorAll('button')).find(b=>b.textContent.includes('播放')||b.getAttribute('aria-label')==='播放'),"
        " stopBtn: !!Array.from(el.querySelectorAll('button')).find(b=>b.textContent.includes('停止')||b.getAttribute('aria-label')==='停止'),"
        " horizontalOverflow: el.scrollWidth>el.clientWidth+1}"
    )
    print(f'[{tag}] modal evidence:', json.dumps(data, ensure_ascii=False))
    return data


def badge_evidence(drv, tag):
    """evidence for the report result-audio Badge that contains the long name."""
    data = drv.execute_script(
        "const badges=Array.from(document.querySelectorAll('[data-slot=\"dialog-content\"] span, [data-slot=\"dialog-content\"] *'))"
        ".filter(e=>e.textContent.includes('超长音频名称渲染验证'));"
        "if(!badges.length) return {err:'no long badge found'};"
        "const b=badges[0];"
        "const row=b.closest('[class*=flex]');"
        "return {badgeText: b.textContent.slice(0,30), badgeClientW: b.clientWidth, badgeScrollW: b.scrollWidth,"
        " badgeHasTitle: !!b.getAttribute('title'),"
        " badgeTruncated: b.scrollWidth>b.clientWidth+1}"
    )
    print(f'[{tag}] badge evidence:', json.dumps(data, ensure_ascii=False))
    return data


def row_evidence(drv, tag):
    """evidence for a case-detail audio row name span truncation."""
    data = drv.execute_script(
        "const spans=Array.from(document.querySelectorAll('[data-slot=\"case-detail-dialog\"] span[class*=font-mono]'))"
        ".filter(e=>e.textContent.includes('超长音频名称渲染验证'));"
        "if(!spans.length) return {err:'no long row span found'};"
        "const s=spans[0];"
        "return {rowText: s.textContent.slice(0,30), rowClientW: s.clientWidth, rowScrollW: s.scrollWidth,"
        " rowHasTitle: !!s.getAttribute('title'),"
        " rowTruncated: s.scrollWidth>s.clientWidth+1,"
        " dialogHorizontalOverflow: (function(){const d=s.closest('[data-slot=\"case-detail-dialog\"]'); return d? d.scrollWidth>d.clientWidth+1 : null})()}"
    )
    print(f'[{tag}] row evidence:', json.dumps(data, ensure_ascii=False))
    return data


def open_report_case_modal(drv):
    drv.get(BASE + '/report/628')
    time.sleep(6)
    # find a case card's 详情 button
    try:
        btn = WebDriverWait(drv, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'详情')]"))
        )
        # prefer one whose row contains an audio badge; click first 详情
        btn.click()
        time.sleep(4)
        return True
    except Exception as e:
        print('report case 详情 click failed:', e)
        return False


def open_task_case_dialog(drv):
    drv.get(BASE + '/tasks/413')
    time.sleep(5)
    try:
        search = WebDriverWait(drv, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="搜索用例"]'))
        )
        search.clear()
        search.send_keys('HJ033')
        time.sleep(2)
    except Exception as e:
        print('task search failed:', e)
    btns = drv.find_elements(By.CSS_SELECTOR, 'button[title^="查看用例详情"]')
    if not btns:
        return False
    for b in btns:
        t = b.get_attribute('title') or ''
        if 'HJ033' in t:
            b.click()
            return True
    btns[0].click()
    return True


def scroll_and_find(drv, text):
    for _ in range(4):
        found = drv.execute_script(
            "const els=Array.from(document.querySelectorAll('[data-slot=\"dialog-content\"] *,[data-slot=\"case-detail-dialog\"] *'))"
            ".filter(e=>e.textContent.trim()==='%s');"
            "if(els.length){els[els.length-1].scrollIntoView({block:'center'}); return true;} return false;" % text
        )
        if found:
            return True
        time.sleep(1)
    return False


def main():
    os.makedirs(ART, exist_ok=True)
    results = {}
    drv = _driver()
    try:
        login(drv)
        install_override(drv)
        set_theme(drv, 'light')
        drv.refresh()
        time.sleep(2)
        # re-install after refresh (window reload clears the override)
        install_override(drv)

        # ===== Part A: report side (result-audio Badge + player modal) =====
        if open_report_case_modal(drv):
            scroll_and_find(drv, '结果音频')
            drv.save_screenshot(os.path.join(ART, 'int2090_report_badges_light.png'))
            results['report_badge_light'] = badge_evidence(drv, 'report-badge-light')
            # click 播放 on a result audio badge -> player modal
            try:
                play = WebDriverWait(drv, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'播放')]"))
                )
                play.click()
                time.sleep(3)
                results['report_player_light'] = modal_evidence(drv, 'report-player-light')
                drv.save_screenshot(os.path.join(ART, 'int2090_report_player_light.png'))
            except Exception as e:
                print('report play click failed:', e)
                results['report_player_light'] = {'err': str(e)}

        # ===== Part B: task side (case-detail audio rows + player modal) =====
        drv.get(BASE + '/tasks/413')
        time.sleep(3)
        install_override(drv)  # keep override installed across SPA nav (reinstall to be safe)
        if open_task_case_dialog(drv):
            time.sleep(4)
            if scroll_and_find(drv, '参考音频（用例输入）'):
                drv.save_screenshot(os.path.join(ART, 'int2090_task_rows_light.png'))
                results['task_row_light'] = row_evidence(drv, 'task-row-light')
                try:
                    play = WebDriverWait(drv, 8).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'试听')]"))
                    )
                    play.click()
                    time.sleep(3)
                    results['task_player_light'] = modal_evidence(drv, 'task-player-light')
                    drv.save_screenshot(os.path.join(ART, 'int2090_task_player_light.png'))
                except Exception as e:
                    print('task 试听 click failed:', e)
                    results['task_player_light'] = {'err': str(e)}
            else:
                print('task reference audio section not found')

        # ===== DARK theme repeat (report player + task player) =====
        set_theme(drv, 'dark')
        drv.refresh()
        time.sleep(2)
        install_override(drv)
        if open_report_case_modal(drv):
            try:
                play = WebDriverWait(drv, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'播放')]"))
                )
                play.click()
                time.sleep(3)
                results['report_player_dark'] = modal_evidence(drv, 'report-player-dark')
                drv.save_screenshot(os.path.join(ART, 'int2090_report_player_dark.png'))
            except Exception as e:
                results['report_player_dark'] = {'err': str(e)}
        drv.get(BASE + '/tasks/413')
        time.sleep(3)
        install_override(drv)
        if open_task_case_dialog(drv):
            time.sleep(4)
            if scroll_and_find(drv, '参考音频（用例输入）'):
                try:
                    play = WebDriverWait(drv, 8).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'试听')]"))
                    )
                    play.click()
                    time.sleep(3)
                    results['task_player_dark'] = modal_evidence(drv, 'task-player-dark')
                    drv.save_screenshot(os.path.join(ART, 'int2090_task_player_dark.png'))
                except Exception as e:
                    results['task_player_dark'] = {'err': str(e)}

        results['console_SEVERE'] = {
            'light': console_severe(drv),
        }
        print('SEVERE:', results['console_SEVERE'])
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    with open(os.path.join(ART, 'int2090_evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print('EVIDENCE JSON written to', os.path.join(ART, 'int2090_evidence.json'))
    print('FINAL SUMMARY:', json.dumps({k: v for k, v in results.items()}, ensure_ascii=False)[:1500])


if __name__ == '__main__':
    main()
