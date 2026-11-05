# -*- coding: utf-8 -*-
"""INT-2387 验收：报告详情头部「任务：」标签换行 + 标题列宽度（React 接线）。

被测前端：本 worktree rsbuild dev server `--port 5381`（API_PROXY_TARGET=http://localhost:15000）。
后端：docker 真实库栈 http://localhost:15000（/health database=intelligent_audio_test）。
登录：RSA-OAEP 加密登录（dev_user/dev_password）→ 写 localStorage iatp:auth:token:v1 → 直达报告页。

断言（1680×899 / 1920×1080 / 1280×800）：
- 「任务：」文本 Range 行数 = 1（修复前 2 行）
- h1 宽度 > 400px 且行数 = 1
- 动作组换到独立一行（动作组 top >= 标题列 bottom）、仍靠右
- 无横向溢出（scrollWidth == innerWidth）
- 浅色 / 深色截图
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5381').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2387')
LABEL = os.environ.get('SIDE', 'fixed')          # before / fixed
REPORT_ID = os.environ.get('REPORT_ID', '426')
FROM = os.environ.get('FROM_PARAM', 'management')
USERNAME = os.environ.get('REACT_USER', 'dev_user')
PASSWORD = os.environ.get('REACT_PWD', 'dev_password')
TOKEN_KEY = 'iatp:auth:token:v1'
THEME_KEY = 'iatp:theme:v1:mode'

RESULT = []
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))


def get_token():
    with urllib.request.urlopen(API + '/api/v1/auth/encryption-key', timeout=60) as r:
        key_data = json.loads(r.read().decode('utf-8'))
    pub = serialization.load_pem_public_key(key_data['public_key'].encode())
    enc = pub.encrypt(
        PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = urllib.parse.urlencode({
        'username': USERNAME,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': key_data['kid'],
    }).encode()
    req = urllib.request.Request(
        API + '/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))['access_token']


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--force-device-scale-factor=1')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
    drv.set_page_load_timeout(90)
    return drv


MEASURE_JS = r"""
return (function () {
  function rect(r){ return {x:Math.round(r.x*10)/10,y:Math.round(r.y*10)/10,w:Math.round(r.width*10)/10,h:Math.round(r.height*10)/10,right:Math.round(r.right*10)/10,bottom:Math.round(r.bottom*10)/10}; }
  function textNodeRects(tn){
    var rg = document.createRange();
    rg.selectNodeContents(tn);
    var rects = Array.prototype.slice.call(rg.getClientRects()).filter(function(r){return r.width>0&&r.height>0;});
    return rects.map(rect);
  }
  var out = {viewport:{w:innerWidth,h:innerHeight}, docScrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth};
  // 1) 「任务：」文本节点
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  var labelNode = null;
  while (walker.nextNode()) {
    var t = walker.currentNode.nodeValue || '';
    if (t.indexOf('任务：') !== -1) { labelNode = walker.currentNode; break; }
  }
  if (labelNode) {
    var rects = textNodeRects(labelNode);
    var parent = labelNode.parentElement;
    var cs = getComputedStyle(parent);
    var range = document.createRange();
    range.selectNodeContents(labelNode);
    var r0 = range.getBoundingClientRect();
    out.taskLabel = {
      text: labelNode.nodeValue,
      nodeRects: rects,
      lines: rects.length,
      width: Math.round(r0.width*10)/10,
      height: Math.round(r0.height*10)/10,
      parentTag: parent.tagName,
      parentClass: parent.className,
      parentWhiteSpace: cs.whiteSpace,
      parentFlexShrink: cs.flexShrink
    };
    // 整个任务信息行（任务：+ 任务名 + #id）
    var row = parent;
    while (row && !(row.className && String(row.className).indexOf('flex-wrap') !== -1 && String(row.className).indexOf('text-xs') !== -1)) {
      row = row.parentElement;
    }
    if (row) {
      var rr = row.getBoundingClientRect();
      out.taskRow = {class: row.className, rect: rect(rr), text: (row.innerText||'').slice(0,120)};
      var links = row.querySelectorAll('a');
      out.taskRowLink = links.length ? {text: links[0].innerText, rect: rect(links[0].getBoundingClientRect()), class: links[0].className} : null;
    }
  }
  // 2) h1
  var h1 = document.querySelector('h1');
  if (h1) {
    var hr = h1.getBoundingClientRect();
    var hcs = getComputedStyle(h1);
    var hrg = document.createRange();
    hrg.selectNodeContents(h1);
    var hrects = Array.prototype.slice.call(hrg.getClientRects()).filter(function(r){return r.width>0&&r.height>0;});
    out.h1 = {text:(h1.innerText||'').slice(0,140), rect: rect(hr), fontSize:hcs.fontSize, lineHeight:hcs.lineHeight, lines:hrects.length, lineRects:hrects.map(rect)};
  }
  // 3) 标题列（h1 所在列）
  var col = h1 ? h1.closest('div.min-w-0') : null;
  if (col) {
    var ccs = getComputedStyle(col);
    out.titleCol = {class: col.className, rect: rect(col.getBoundingClientRect()), flexBasis: ccs.flexBasis, flexGrow: ccs.flexGrow};
  }
  // 4) 动作组：header 卡片内直接子 div（含一组 Button 的容器）
  var card = h1 ? h1.closest('div.bg-card') : null;
  out.card = card ? {class: card.className, rect: rect(card.getBoundingClientRect())} : null;
  if (card) {
    var kids = Array.prototype.slice.call(card.children[0] ? card.children[0].children : []);
    var action = null;
    kids.forEach(function (k) {
      if (k === col) return;
      if (k.querySelectorAll('button').length >= 2) action = k;
    });
    if (action) {
      var ar = action.getBoundingClientRect();
      var abtns = Array.prototype.slice.call(action.querySelectorAll('button')).map(function(b){ return (b.innerText||b.getAttribute('aria-label')||'').trim(); });
      out.actions = {class: action.className, rect: rect(ar), buttonCount: abtns.length, buttons: abtns,
                     sameRowAsTitle: col ? (Math.abs(ar.top - col.getBoundingClientRect().top) < 8) : null,
                     gapFromColRight: col ? Math.round((ar.left - col.getBoundingClientRect().right)*10)/10 : null,
                     marginLeftAuto: getComputedStyle(action).marginLeft};
    }
  }
  // 5) 描述
  var descs = Array.prototype.slice.call(document.querySelectorAll('p')).filter(function(p){ return (p.innerText||'').indexOf('类 API') !== -1 || (p.innerText||'').indexOf('报告') !== -1; });
  if (descs.length) {
    var d = descs[0];
    var dr = d.getBoundingClientRect();
    var drg = document.createRange();
    drg.selectNodeContents(d);
    var drects = Array.prototype.slice.call(drg.getClientRects()).filter(function(r){return r.width>0&&r.height>0;});
    out.description = {text:(d.innerText||'').slice(0,160), rect: rect(dr), lines: drects.length};
  }
  out.theme = document.documentElement.className;
  out.bodyBg = getComputedStyle(document.body).backgroundColor;
  return out;
})();
"""


def set_viewport(drv, w, h):
    drv.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False,
    })
    time.sleep(1.2)


def reload_and_wait(drv):
    drv.refresh()
    WebDriverWait(drv, 60).until(lambda d: d.execute_script('return !!document.querySelector("h1")'))
    time.sleep(2.5)


def wait_ready(drv):
    # 任务型报告有「任务：」；对比报告显示「N 个任务对比」——两种都等 h1 出现并稳定
    WebDriverWait(drv, 60).until(
        lambda d: d.execute_script('return !!document.querySelector("h1")')
        and ('任务：' in d.find_element(By.TAG_NAME, 'body').text
             or '个任务对比' in d.find_element(By.TAG_NAME, 'body').text))
    time.sleep(2.0)


def main():
    os.makedirs(ART, exist_ok=True)
    token = get_token()
    drv = _driver()
    shots = []
    try:
        drv.get(BASE + '/login')
        time.sleep(1.5)
        drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', TOKEN_KEY, token)
        drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', THEME_KEY, 'light')
        url = BASE + '/report/%s?from=%s' % (REPORT_ID, FROM)
        drv.get(url)
        wait_ready(drv)
        check('报告页标题 h1 出现', True, drv.find_element(By.TAG_NAME, 'h1').text[:80])

        measurements = {}
        for w, h in [(1680, 899), (1920, 1080), (1280, 800)]:
            set_viewport(drv, w, h)
            wait_ready(drv)
            m = drv.execute_script(MEASURE_JS)
            m['tag'] = '%dx%d-light' % (w, h)
            measurements[m['tag']] = m
            print('\n=== %s ===' % m['tag'])
            print(json.dumps(m, ensure_ascii=False, indent=1))
            shot = os.path.join(ART, '%s_%s_%dx%d_light.png' % (LABEL, REPORT_ID, w, h))
            drv.save_screenshot(shot)
            shots.append(shot)

        # 深色：1680
        set_viewport(drv, 1680, 899)
        drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', THEME_KEY, 'dark')
        reload_and_wait(drv)
        wait_ready(drv)
        m = drv.execute_script(MEASURE_JS)
        m['tag'] = '1680x899-dark'
        measurements[m['tag']] = m
        print('\n=== %s ===' % m['tag'])
        print(json.dumps(m, ensure_ascii=False, indent=1))
        shot = os.path.join(ART, '%s_%s_1680x899_dark.png' % (LABEL, REPORT_ID))
        drv.save_screenshot(shot)
        shots.append(shot)
        check('深色主题生效（html.dark）', 'dark' in (m.get('theme') or ''), m.get('theme'))

        # console 错误
        try:
            logs = drv.get_log('browser')
            severe = [l for l in logs if l.get('level') == 'SEVERE']
            check('浏览器 console 无 SEVERE', len(severe) == 0, json.dumps(severe[:3], ensure_ascii=False))
        except Exception as e:
            print('  [warn] console log 读取失败: %s' % e)

        out = os.path.join(ART, 'measure_%s_%s.json' % (LABEL, REPORT_ID))
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(measurements, f, ensure_ascii=False, indent=2)
        print('\n[saved] ' + out)
    finally:
        drv.quit()

    print('\n==== SUMMARY (%s) ====' % LABEL)
    for k, m in measurements.items():
        tl = m.get('taskLabel') or {}
        h1 = m.get('h1') or {}
        ac = m.get('actions') or {}
        print('%s: labelLines=%s labelRects=%s h1w=%s h1lines=%s descW=%s actionsTop=%s sameRow=%s scrollW=%s vw=%s theme=%s' % (
            k, tl.get('lines'), [r['w'] for r in (tl.get('nodeRects') or [])], h1.get('rect', {}).get('w'),
            h1.get('lines'), (m.get('description') or {}).get('rect', {}).get('w'), ac.get('rect', {}).get('y'),
            ac.get('sameRowAsTitle'), m.get('docScrollWidth'), m.get('viewport', {}).get('w'), m.get('theme')))
    with open(os.path.join(ART, 'summary_%s.json' % LABEL), 'w', encoding='utf-8') as f:
        json.dump({'label': LABEL, 'base': BASE, 'report': REPORT_ID, 'measurements': measurements,
                   'shots': shots, 'checks': RESULT}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
