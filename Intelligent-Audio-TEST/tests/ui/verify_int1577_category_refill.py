# -*- coding: utf-8 -*-
"""INT-1577 实测取证：评估维度页「编辑分类」弹窗取消后重开同一分类回填。

两条腿：
- BASE = 本 run worktree dev server（应用交付 diff，修后）→ 期望回填；
- BASE = http://localhost:15173（wiring/react 基线镜像，修前）→ 期望复现「三项全空」。
用同一脚本跑两遍，证明脚本有区分力、修复确实生效。

真实库栈（docker）：后端 http://127.0.0.1:15000（database=intelligent_audio_test，只读）。
断言：同一分类连开两次，名称/描述/图标与 GET /evaluation/categories 一致；切到别的分类再回来也一致。
证据：浅/深色各 open1/open2 截图 + performance log 中 /evaluation/* 状态码。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5388')
TAG = os.environ.get('SHOT_TAG', 'fixed')
EXPECT = os.environ.get('EXPECT', 'refill')  # refill | empty
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1577')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API_BASE = 'http://127.0.0.1:15000'
CATEGORY_NAME = '拒识'
OTHER_CATEGORY = '打断'


def log(m):
    print(m, flush=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1400')
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
    return webdriver.Chrome(options=options, service=service)


def api_get(path):
    import urllib.request
    with urllib.request.urlopen(API_BASE + path, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    drv.execute_script('arguments[0].click();', el)


def open_page(drv):
    drv.get(BASE + '/Evaluation')
    time.sleep(3)
    if '/login' in drv.current_url:
        try:
            drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
            drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        except Exception:
            pass
        WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
        drv.get(BASE + '/Evaluation')
        time.sleep(2)
    # 切到分组视图（分组卡才有「编辑分类」）
    tab = WebDriverWait(drv, 60).until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@role='tab' and normalize-space(.)='分组视图']")))
    js_click(drv, tab)
    WebDriverWait(drv, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[@aria-label='编辑分类 %s']" % CATEGORY_NAME)))


def edit_btn(drv, name):
    return WebDriverWait(drv, 30).until(EC.presence_of_element_located(
        (By.XPATH, "//button[@aria-label='编辑分类 %s']" % name)))


def read_form(drv):
    name = drv.find_element(By.ID, 'category-name').get_attribute('value')
    desc = drv.find_element(By.ID, 'category-description').get_attribute('value')
    icon = drv.find_element(By.ID, 'category-icon').get_attribute('value')
    title = drv.find_element(By.XPATH, "//*[@role='dialog']//h2").text
    return {'title': title, 'name': name, 'description': desc, 'icon': icon}


def open_edit(drv, name):
    js_click(drv, edit_btn(drv, name))
    WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.ID, 'category-name')))
    time.sleep(1.0)


def cancel_dialog(drv):
    btn = WebDriverWait(drv, 20).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='取消']")))
    js_click(drv, btn)
    WebDriverWait(drv, 20).until(EC.invisibility_of_element_located((By.ID, 'category-name')))
    time.sleep(1.0)


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('screenshot: %s' % path)
    return path


def network_evidence(drv, tag):
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            method = (msg.get('message') or {}).get('method') or ''
            params = (msg.get('message') or {}).get('params') or {}
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            if '/evaluation/categories' in url or '/evaluation/dimensions' in url:
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'), 'url': url, 'status': None}
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                reqs[rid]['status'] = (params.get('response') or {}).get('status')
    lines = ['%s %s -> %s' % (v['method'], v['url'].split('/api/v1')[-1], v['status'])
             for v in reqs.values()]
    log('network(%s): %s' % (tag, lines))
    return lines


def theme(drv, mode):
    # localStorage 需要在目标源下写（约:blank / data: URL 不可用）
    if not drv.current_url.startswith(BASE):
        drv.get(BASE + '/')
        time.sleep(1.5)
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode","%s")' % mode)
    drv.get('about:blank')
    time.sleep(0.5)
    open_page(drv)


def sequence(drv, mode, expected):
    """同一分类连开两次 + 切到别的分类再回来。返回各项读数与结论。"""
    theme(drv, mode)
    cat = CAT[CATEGORY_NAME]
    res = {}

    open_edit(drv, CATEGORY_NAME)
    first = read_form(drv)
    res['first'] = first
    shot(drv, 'int1577_%s_%s_open1.png' % (TAG, mode))
    cancel_dialog(drv)

    open_edit(drv, CATEGORY_NAME)
    second = read_form(drv)
    res['second'] = second
    shot(drv, 'int1577_%s_%s_open2.png' % (TAG, mode))
    cancel_dialog(drv)

    # 对照：先开别的分类（正常回填），再回来
    open_edit(drv, OTHER_CATEGORY)
    other = read_form(drv)
    res['other'] = other
    cancel_dialog(drv)
    open_edit(drv, CATEGORY_NAME)
    third = read_form(drv)
    res['third'] = third
    cancel_dialog(drv)

    log('[%s/%s] first =%s' % (TAG, mode, json.dumps(first, ensure_ascii=False)))
    log('[%s/%s] second=%s' % (TAG, mode, json.dumps(second, ensure_ascii=False)))
    log('[%s/%s] other =%s' % (TAG, mode, json.dumps(other, ensure_ascii=False)))
    log('[%s/%s] third =%s' % (TAG, mode, json.dumps(third, ensure_ascii=False)))

    want = {'name': cat['name'], 'description': cat.get('description') or '',
            'icon': cat.get('icon') or ''}
    # 第一次必须回填（两版都成立，证明脚本本身能读到值）
    assert first['title'] == '编辑分类', 'title %r' % first['title']
    assert first['name'] == want['name'], 'first open name %r != %r' % (first['name'], want['name'])
    assert first['description'] == want['description'], 'first desc mismatch'
    assert first['icon'] == want['icon'], 'first icon mismatch'

    def check(label, snap, mode=expected):
        vals = {k: snap[k] for k in ('name', 'description', 'icon')}
        if mode == 'refill':
            assert vals == want, '%s 未回填: %s vs %s' % (label, vals, want)
        else:
            # 修前缺陷形态：名称/描述为空，图标退回默认 fas fa-folder（不是该分类的图标）
            assert vals['name'] == '' and vals['description'] == '', \
                '%s 期望名称为空（修前缺陷），实际 %s' % (label, vals)
            assert vals['icon'] != want['icon'], \
                '%s 期望图标未回填（修前缺陷），实际 %s' % (label, vals)

    check('重开同一分类', second)
    # 切到别的分类再回来：修前也正常回填（卡内对照组），两版都必须通过
    check('切别的分类再回来', third, mode='refill')
    assert other['name'] == CAT[OTHER_CATEGORY]['name'], 'other category refill broken: %r' % other
    res['want'] = want
    return res


def main():
    global CAT
    os.makedirs(ART, exist_ok=True)
    health = api_get('/health')
    log('health: %s' % json.dumps(health, ensure_ascii=False))
    assert health.get('database') == 'intelligent_audio_test', 'wrong db %r' % health
    cats = api_get('/api/v1/evaluation/categories')
    items = (cats.get('data') or {}).get('items') or []
    CAT = {c['name']: c for c in items}
    log('categories: %s' % json.dumps([(c['id'], c['name']) for c in items], ensure_ascii=False))
    for n in (CATEGORY_NAME, OTHER_CATEGORY):
        assert n in CAT, 'category %r missing' % n

    drv = _driver()
    try:
        drv.set_page_load_timeout(90)
        light = sequence(drv, 'light', EXPECT)
        net_light = network_evidence(drv, 'light')
        dark = sequence(drv, 'dark', EXPECT)
        net_dark = network_evidence(drv, 'dark')

        lines = ['INT-1577 Evaluation category edit dialog refill',
                 'frontend: %s (%s)' % (BASE, TAG),
                 'backend : %s database=%s' % (API_BASE, health.get('database')),
                 'expect  : %s' % EXPECT,
                 '',
                 'category: id=%s name=%s desc=%s icon=%s' % (
                     CAT[CATEGORY_NAME]['id'], CAT[CATEGORY_NAME]['name'],
                     CAT[CATEGORY_NAME].get('description'), CAT[CATEGORY_NAME].get('icon')),
                 'light open1=%s' % json.dumps(light['first'], ensure_ascii=False),
                 'light open2=%s' % json.dumps(light['second'], ensure_ascii=False),
                 'light back =%s' % json.dumps(light['third'], ensure_ascii=False),
                 'dark  open1=%s' % json.dumps(dark['first'], ensure_ascii=False),
                 'dark  open2=%s' % json.dumps(dark['second'], ensure_ascii=False),
                 'dark  back =%s' % json.dumps(dark['third'], ensure_ascii=False),
                 '',
                 'Network (light):'] + net_light + ['', 'Network (dark):'] + net_dark + [
                 '', 'verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S')]
        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
        except Exception:
            font = ImageFont.load_default()
        W, H = 1300, max(160, 38 * len(lines) + 40)
        img = Image.new('RGB', (W, H), (245, 245, 245))
        draw = ImageDraw.Draw(img)
        y = 12
        for ln in lines:
            draw.text((16, y), ln[:150], fill=(20, 20, 20), font=font)
            y += 34
        out = os.path.join(ART, 'int1577_%s_network_evidence.png' % TAG)
        img.save(out)
        log('network evidence: %s' % out)
        log('PASS expect=%s' % EXPECT)
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
