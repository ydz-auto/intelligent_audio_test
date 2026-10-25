# -*- coding: utf-8 -*-
"""INT-1780 验收：分组未展开时组头「批量修改」空 ids 入口拦截（不再按 0 条提交/假成功）。

双跑对照：
  旧镜像（无修复） REACT_BASE=http://localhost:15173 TAG=old python verify_int1780_empty_ids.py
  交付旁路容器   REACT_BASE=http://localhost:15280 TAG=fix python verify_int1780_empty_ids.py

覆盖：
  1) 收起态组头「调整分组」：旧=弹窗 0 条 + POST ids:[] + 成功 toast；新=不弹窗/不请求/提示
  2) 收起态组头九项逐个：新全部拦截（无弹窗、无 POST /testcases/batch、同一提示）
  3) 收起态「删除用例」：旧=仅 toast 假成功无请求；新=同一提示拦截
  4) 展开组内 2 条 → 调整分组到 B：弹窗计数 2 → POST ids 2 条 → 200 → GET 回读 group_id 生效
  5) 展开组 B →「删除用例」：新=确认弹窗 → POST batch(delete) 真实软删 → GET 404/删除态
截图：guard 浅/深、dialog 计数、成功 toast、菜单项。数据：接线测试_INT1780_ 前缀，run 后清理。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import winreg

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15280').rstrip('/')
API = os.environ.get('API_BASE', 'http://localhost:15000').rstrip('/')
TAG = os.environ.get('TAG', 'fix')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1780'),
)
os.makedirs(ART, exist_ok=True)

GRP_A = '接线测试_INT1780_A'
GRP_B = '接线测试_INT1780_B'
CASE_1 = '接线测试_INT1780_用例1'
CASE_2 = '接线测试_INT1780_用例2'
ITEMS = ['用例专属参数', '播放设备', '声压', '调整分组', '评价维度', '噪声', '标签生成名称', '管理标签', '用例参考更新']
HINT = '请先展开分组或勾选用例'
DARK_KEY = 'iatp:theme:v1:mode'

RESULT = []


def check(name, ok, detail=None):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | ' + json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)
    return ok


def api(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


FETCH_PATCH = r"""
window.__fetchLog = [];
window.__toasts = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    const reqBody = (init && init.body && typeof init.body === 'string') ? init.body : null;
    let res;
    try { res = await orig.apply(this, arguments); }
    catch (e) { window.__fetchLog.push({url:url, method:method, status:'ERR', error:String(e), reqBody:reqBody}); throw e; }
    let text = null;
    try { text = await res.clone().text(); } catch(e) {}
    window.__fetchLog.push({url:url, method:method, status:res.status, reqBody:reqBody, resBody:(text||'').slice(0,4000)});
    return res;
  };
  const record = function(node) {
    if (!node || node.nodeType !== 1) return;
    const t = (node.textContent || '').trim();
    if (t) window.__toasts.push(t);
  };
  const obs = new MutationObserver(function(muts){
    for (const m of muts) for (const n of m.addedNodes) {
      if (n.nodeType === 1) {
        if (n.matches && n.matches('[data-sonner-toast]')) { record(n); continue; }
        const toasts = n.querySelectorAll ? n.querySelectorAll('[data-sonner-toast]') : [];
        toasts.forEach(record);
      }
    }
  });
  document.addEventListener('DOMContentLoaded', function(){ obs.observe(document.body, {childList:true, subtree:true}); });
  if (document.body) obs.observe(document.body, {childList:true, subtree:true});
})();
"""


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--disable-extensions', '--no-proxy-server'):
        o.add_argument(a)
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for v in os.listdir(cache):
            e = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(e):
                try:
                    cands.append((tuple(int(x) for x in v.split('.') if x.isdigit()), e))
                except ValueError:
                    pass
        same = [e for vv, e in cands if vv and vv[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(120)
    d.implicitly_wait(0)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def wait_text(d, text, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if text in d.execute_script('return document.body.innerText'):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def els(d, xp):
    return d.find_elements(By.XPATH, xp)


def click_el(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)


def click_xpath(d, xp, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        found = els(d, xp)
        if found:
            click_el(d, found[0])
            return True
        time.sleep(0.25)
    return False


def open_menu(d, group_name):
    d.execute_script("window.__toasts=[]")
    ok = click_xpath(d, f"//button[@aria-label='{group_name} 批量修改']")
    if not ok:
        return False
    return wait_text(d, '批量修改 · ' + group_name, 10)


def click_menu_item(d, label, exact=False):
    if exact:
        xp = f"//*[@role='menuitem' or self::*[@data-slot='dropdown-menu-item']][normalize-space(.)='{label}']"
    else:
        xp = f"//*[@role='menuitem'][contains(normalize-space(.), '{label}')]"
    ok = click_xpath(d, xp, 10)
    time.sleep(0.6)
    return ok


def toasts(d):
    try:
        return list(d.execute_script('return window.__toasts || []'))
    except Exception:
        return []


def fetch_rows(d, needle='/testcases/batch', writes_only=True):
    try:
        log = d.execute_script('return window.__fetchLog || []')
    except Exception:
        log = []
    out = []
    for e in log:
        if needle not in (e.get('url') or ''):
            continue
        if writes_only and e.get('method') not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            continue
        out.append(e)
    return out


def clear_fetch(d):
    d.execute_script('window.__fetchLog = []')


def dialog_text(d):
    """base-ui Dialog 是 fixed 定位（offsetParent 为 null），可见性按 getClientRects 判。"""
    try:
        return d.execute_script(
            "return [...document.querySelectorAll('[role=dialog],[role=alertdialog]')]"
            ".filter(x=>x.getClientRects().length>0)"
            ".map(x=>x.innerText).join('\\n---\\n')"
        ) or ''
    except Exception:
        return ''


def close_dialog(d):
    """关闭弹层（取消）并等它从可见集消失。"""
    click_xpath(d, "//*[@role='dialog' or @role='alertdialog']//button[normalize-space(.)='取消']", 5)
    time.sleep(0.5)
    return dialog_text(d) == ''


def shot(d, name):
    p = os.path.join(ART, f'{TAG}_{name}.png')
    d.save_screenshot(p)
    return p


def set_theme(d, mode):
    d.execute_script("localStorage.setItem(arguments[0], arguments[1])", DARK_KEY, mode)
    d.refresh()
    time.sleep(2)


def page_ready(d, need=GRP_A):
    """等首屏分组卡，并按需点「加载更多」拉到目标分组（分组列表每页 5 个、按用例数排序）。"""
    end = time.time() + 45
    while time.time() < end:
        try:
            body = d.execute_script('return document.body.innerText')
        except Exception:
            body = ''
        if need in body:
            time.sleep(1.2)
            return True
        if '加载更多' in body:
            click_xpath(d, "//button[contains(normalize-space(.), '加载更多')]", 5)
            time.sleep(1.2)
            continue
        time.sleep(0.8)
    return False


def group_header_click(d, name):
    # 点组头名称所在行展开（按钮区 stopPropagation，不会误触）
    return click_xpath(d, f"//span[normalize-space(.)='{name}']", 10)


def main():
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group')
        if not page_ready(d):
            check('页面加载分组卡', False, {'body': d.execute_script('return document.body.innerText')[:500]})
            return
        check('页面加载分组卡', True, {'url': d.current_url})
        check('组 A 计数徽章 2 条', '2 条' in d.execute_script('return document.body.innerText'), None)

        # ---- 1) 收起态「调整分组」 ----
        d.execute_script("window.__toasts=[]")
        clear_fetch(d)
        open_menu(d, GRP_A)
        click_menu_item(d, '调整分组')
        time.sleep(1.2)
        dlg = dialog_text(d)
        warn = [t for t in toasts(d) if HINT in t]
        posts = fetch_rows(d)
        shot(d, 'guard_' + TAG)
        if TAG == 'old':
            check('旧镜像：收起态弹出「批量调整分组」且计数 0', '批量调整分组' in dlg and '您勾选了 0 个用例' in dlg, {'dialog': dlg[:300]})
            # 选目标分组 B 后确定（控件作用域限定在当前弹窗内）
            click_xpath(d, "//*[@role='dialog' or @role='alertdialog']//button[@role='combobox']", 8)
            time.sleep(0.5)
            click_xpath(d, f"//*[@role='option'][contains(normalize-space(.), '{GRP_B}')]", 8)
            time.sleep(0.5)
            clear_fetch(d)
            click_xpath(d, "//*[@role='dialog' or @role='alertdialog']//button[normalize-space(.)='确定']", 8)
            time.sleep(1.5)
            posts = fetch_rows(d)
            bodies = []
            for p in posts:
                try:
                    bodies.append(json.loads(p.get('reqBody') or '{}'))
                except Exception:
                    bodies.append(p.get('reqBody'))
            check('旧镜像：确定后 POST /testcases/batch 且 ids 为空', bool(posts) and any(
                isinstance(b, dict) and b.get('ids') == [] for b in bodies), {'bodies': bodies, 'status': [p.get('status') for p in posts]})
            check('旧镜像：仍按成功提示', any(('成功' in t or '移动 0' in t) for t in toasts(d)), {'toasts': toasts(d)[-3:]})
        else:
            check('修复：收起态不弹「批量调整分组」', '批量调整分组' not in dlg, {'dialog': dlg[:200]})
            check('修复：提示「请先展开分组或勾选用例」', bool(warn), {'toasts': toasts(d)[-3:]})
            check('修复：无 POST /testcases/batch', len(posts) == 0, {'posts': [(p.get('method'), p.get('url')) for p in posts]})
            check('修复：无成功 toast', not any(('成功' in t and '请先展开' not in t) for t in toasts(d)), {'toasts': toasts(d)[-3:]})

        # 关闭可能残留的下拉/弹窗
        close_dialog(d)
        d.execute_script("document.body.click()")
        time.sleep(0.4)

        # ---- 2) 收起态九项逐个（仅修复侧） ----
        if TAG != 'old':
            results = {}
            for label in ITEMS:
                if not open_menu(d, GRP_A):
                    results[label] = 'menu-open-fail'
                    continue
                clicked = click_menu_item(d, label)
                time.sleep(0.6)
                dlg = dialog_text(d)
                tst = toasts(d)
                posts = fetch_rows(d)
                hit = any(HINT in t for t in tst)
                results[label] = {'clicked': clicked, 'hint': hit, 'dialog': dlg[:60],
                                  'posts': len(posts)}
                d.execute_script("document.body.click()")
                time.sleep(0.3)
            ok_all = all(isinstance(v, dict) and v.get('clicked') and v.get('hint') and v.get('posts') == 0 and not v.get('dialog') for v in results.values())
            check('修复：九项组头批量空 ids 全部拦截（提示/无弹窗/无请求）', ok_all, results)
            # 深色截图
            set_theme(d, 'dark')
            page_ready(d)
            open_menu(d, GRP_A)
            click_menu_item(d, '调整分组')
            time.sleep(1.0)
            shot(d, 'guard_dark_' + TAG)
            check('深色：提示可见', HINT in d.execute_script('return document.body.innerText'), None)
            set_theme(d, 'light')
            page_ready(d)

            # ---- 2b) 「删除用例」收起态 ----
            d.execute_script("window.__toasts=[]")
            clear_fetch(d)
            open_menu(d, GRP_A)
            click_menu_item(d, '删除用例', exact=True)
            time.sleep(0.8)
            tst = toasts(d)
            check('修复：收起态「删除用例」不假成功（有提示、无成功 toast、无请求）',
                  any(HINT in t for t in tst) and not any('已移入回收站' in t for t in tst) and len(fetch_rows(d)) == 0,
                  {'toasts': tst[-3:], 'posts': len(fetch_rows(d))})
            d.execute_script("document.body.click()")
            time.sleep(0.4)

        # ---- 3) 展开组 A：调整分组计数 2 ----
        group_header_click(d, GRP_A)
        ok_cases = wait_text(d, CASE_1, 20) and wait_text(d, CASE_2, 5)
        check('展开组 A 懒加载 2 条用例', ok_cases, None)
        d.execute_script("window.__toasts=[]")
        clear_fetch(d)
        open_menu(d, GRP_A)
        click_menu_item(d, '调整分组')
        time.sleep(1.0)
        dlg = dialog_text(d)
        check('展开态弹窗计数 2', '批量调整分组' in dlg and '您勾选了 2 个用例' in dlg, {'dialog': dlg[:300]})
        shot(d, 'dialog_expanded_' + TAG)
        click_xpath(d, "//*[@role='dialog' or @role='alertdialog']//button[@role='combobox']", 8)
        time.sleep(0.5)
        ok_opt = click_xpath(d, f"//*[@role='option'][contains(normalize-space(.), '{GRP_B}')]", 8)
        time.sleep(0.5)
        clear_fetch(d)
        click_xpath(d, "//*[@role='dialog' or @role='alertdialog']//button[normalize-space(.)='确定']", 8)
        time.sleep(2.0)
        posts = fetch_rows(d)
        bodies = []
        for p in posts:
            try:
                bodies.append(json.loads(p.get('reqBody') or '{}'))
            except Exception:
                bodies.append(p.get('reqBody'))
        ok_req = any(isinstance(b, dict) and b.get('action') == 'move_to_group' and len(b.get('ids') or []) == 2 for b in bodies)
        check('展开态提交 POST ids=2 且 action=move_to_group', ok_req,
              {'bodies': bodies, 'status': [p.get('status') for p in posts], 'target_clicked': ok_opt})
        toast_ok = any('移动 2 个用例' in t for t in toasts(d))
        shot(d, 'submit_success_' + TAG)
        check('成功 toast「移动 2 个用例」', toast_ok, {'toasts': toasts(d)[-3:]})

        # 回读 group_id
        st, data = api('GET', '/testcases')
        grp_b_id = os.environ.get('GRP_B_ID')
        if grp_b_id:
            detail_ok = []
            for cid in [os.environ.get('CASE_1_ID'), os.environ.get('CASE_2_ID')]:
                if not cid:
                    continue
                s2, one = api('GET', f'/testcases/{cid}')
                gid = ((one or {}).get('data') or {}).get('group_id') if isinstance(one, dict) else None
                detail_ok.append(gid == grp_b_id)
            check('回读两条用例 group_id = 目标分组 B', all(detail_ok) and len(detail_ok) == 2, detail_ok)

        # ---- 4) 组 B 展开态「删除用例」真实批量删除 ----
        if TAG != 'old':
            page_ready(d)
            group_header_click(d, GRP_B)
            ok_cases_b = wait_text(d, CASE_1, 20)
            check('组 B 展开可见 2 条用例', ok_cases_b, None)
            open_menu(d, GRP_B)
            d.execute_script("window.__toasts=[]")
            clear_fetch(d)
            click_menu_item(d, '删除用例', exact=True)
            time.sleep(0.8)
            dlg = dialog_text(d)
            check('组头「删除用例」弹出批量删除确认（非纯 toast）',
                  '批量删除用例' in dlg and '2 个用例' in dlg, {'dialog': dlg[:300]})
            click_xpath(d, "//button[normalize-space(.)='批量删除']", 8)
            time.sleep(2.0)
            posts = fetch_rows(d)
            bodies = []
            for p in posts:
                try:
                    bodies.append(json.loads(p.get('reqBody') or '{}'))
                except Exception:
                    bodies.append(p.get('reqBody'))
            check('确认真实发 POST /testcases/batch(delete, ids=2)',
                  any(isinstance(b, dict) and b.get('action') == 'delete' and len(b.get('ids') or []) == 2 for b in bodies)
                  and any(p.get('status') == 200 for p in posts),
                  {'bodies': bodies, 'status': [p.get('status') for p in posts]})
            check('删除后成功提示', any('批量移入回收站' in t or '回收站' in t for t in toasts(d)), {'toasts': toasts(d)[-3:]})
    finally:
        try:
            d.quit()
        except Exception:
            pass
        print('\n=== RESULT ' + TAG + ' ===')
        print(json.dumps(RESULT, ensure_ascii=False, indent=1))
        with open(os.path.join(ART, f'result_{TAG}.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULT, f, ensure_ascii=False, indent=1)
        failed = [r for r in RESULT if not r['ok']]
        print(f'FAILED {len(failed)} / {len(RESULT)}')


if __name__ == '__main__':
    main()
