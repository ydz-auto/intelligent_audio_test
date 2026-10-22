# -*- coding: utf-8 -*-
"""INT-1277 挑选合并容器行操作接线浏览器实测（真实库栈 5700，admin）。

覆盖（对照 18_挑选合并交互重设计.md §7.5 行操作清单）：
  P1 行操作菜单完整：查看详情/查看报告/生成报告（手动）/发布/收藏/重命名/删除
  P2 收藏 → POST /tasks/{id}/favorite（真实请求 + 星标回显）→ 取消收藏 DELETE /tasks/{id}/favorite
  P3 重命名 → Dialog → PUT /tasks/{id}（列表刷新回显新名）
  P4 查看报告（有报告容器）→ 跳 /report/:id
  P5 生成报告（手动）→ POST /reports/generate-task 真实请求（SSE 等待后跳报告页，环境允许）
  P6 发布 → PublishTaskDialog 打开（任务域既有入口）
  P7 删除 → ConfirmDialog 确认 → DELETE /tasks/{id}（软删→回收站，容器消失）
证据：tests/ui/artifacts/int1277_cherrypick/*.png（浅/深 + Network 文本图）

用法：python tests/ui/verify_int1277.py --base http://127.0.0.1:5322
前置：dev server /api 代理 → 5700；容器「接线测试_INT1277_容器」(task 502) 与
      「接线测试_INT1277_重新生成」(task 497, report 494) 已由 setup 脚本建好。
"""
import argparse
import json
import os
import sys
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1277_cherrypick')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

ADMIN = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
CONTAINER_NO_REPORT = '接线测试_INT1277_容器'       # task 502，无报告
CONTAINER_WITH_REPORT = '接线测试_INT1277_容器测试'  # task 497，report 494


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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


def wait_for(cond, timeout=30, desc='condition'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout waiting for %s' % desc)


def collect_requests(drv):
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                inner = msg.get('message') or {}
                method = inner.get('method') or ''
                params = inner.get('params') or {}
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                reqs[params.get('requestId')] = {'method': req.get('method', 'GET'), 'url': url, 'status': None}
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return [v for k, v in reqs.items()]


def count_api_calls(reqs, path, methods=None):
    matches = []
    for r in reqs:
        if path in r.get('url', ''):
            if methods and r.get('method') not in methods:
                continue
            matches.append(r)
    return matches


def render_text_png(title, lines, filename):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    text = '\n'.join([title] + lines)
    W, H = 1200, max(140, 36 * (len(text.split('\n')) + 1) + 40)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 12
    for ln in text.split('\n'):
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 34
    out = os.path.join(ARTIFACTS, filename)
    img.save(out)
    return out


def _row_containing(drv, text, timeout=25):
    wait_for(lambda: text in (drv.page_source or ''), timeout, 'row %s' % text)
    script = """
    const rows = document.querySelectorAll('tbody tr');
    for (const r of rows) {
      if (r.textContent && r.textContent.indexOf(arguments[0]) !== -1) return r;
    }
    return null;
    """
    row = drv.execute_script(script, text)
    if not row:
        raise AssertionError('row not found: ' + text)
    return row


def _click_text(drv, text, timeout=12):
    def do():
        els = drv.find_elements(By.XPATH, '//*[normalize-space(text())="%s"]' % text)
        for el in els:
            try:
                if el.is_displayed():
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    time.sleep(0.4)
                    drv.execute_script('arguments[0].click();', el)
                    return True
            except Exception:
                continue
        return False

    if not wait_for(do, timeout, 'click ' + text):
        raise AssertionError('click failed: ' + text)


def _click_row_menu(drv, row, label):
    """点行末「⋯」下拉菜单，再点目标项（base-ui menuitem；normalize 兼容拆分文本）。"""
    btn = row.find_element(By.CSS_SELECTOR, '[aria-label="挑选合并任务操作"]')
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', btn)
    time.sleep(1.0)  # 等 base-ui 开合动画就绪，避免点击被吞

    def do():
        items = drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]')
        for it in items:
            try:
                if (it.text or '').strip() == label and it.is_displayed():
                    drv.execute_script('arguments[0].click();', it)
                    return True
            except Exception:
                continue
        return False

    if not wait_for(do, 10, 'menu item ' + label):
        raise AssertionError('menu item click failed: ' + label)


def _close_menu(drv):
    """Escape 关闭打开的 dropdown（base-ui 对 document click 无感知，须 Escape）。"""
    from selenium.webdriver.common.keys import Keys
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.6)


def _click_in_dialog(drv, text):
    def do():
        dialogs = drv.find_elements(By.CSS_SELECTOR, '[data-slot="alert-dialog-content"]')
        for d in dialogs:
            if not d.is_displayed():
                continue
            els = d.find_elements(By.XPATH, './/*[normalize-space(text())="%s"]' % text)
            for el in els:
                try:
                    if el.is_displayed():
                        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                        time.sleep(0.4)
                        drv.execute_script('arguments[0].click();', el)
                        return True
                except Exception:
                    continue
        return False

    if not wait_for(do, 12, 'click in dialog ' + text):
        raise AssertionError('click in dialog failed: ' + text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5322')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)

        # ---- 登录（真实库栈 AUTH_MODE=dev，表单登录）----
        drv.get(base + '/login')
        wait_for(lambda: '登 录' in (drv.page_source or '') or '登录' in (drv.page_source or ''), 20, 'login page')
        time.sleep(1)
        drv.find_element(By.ID, 'username').send_keys(ADMIN)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.execute_script("""
        const btns = [...document.querySelectorAll('button')];
        const b = btns.find(x => x.textContent && x.textContent.replace(/\\s+/g, '').indexOf('登录') !== -1);
        if (b) b.click();
        """)
        wait_for(lambda: '/dashboard' in (drv.current_url or '') or '工作台' in (drv.page_source or ''), 25, 'login ok')
        print('LOGIN OK ->', drv.current_url)

        # 浅色主题
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')

        # ---- 挑选合并页 ----
        drv.get(base + '/tasks/cherry-picks')
        wait_for(lambda: CONTAINER_NO_REPORT in (drv.page_source or ''), 30, 'container list render')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p0_list_light.png'))

        # ---- P1 行操作菜单完整性 ----
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_NO_REPORT)
        btn = row.find_element(By.CSS_SELECTOR, '[aria-label="挑选合并任务操作"]')
        drv.execute_script('arguments[0].click();', btn)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_row_menu_light.png'))
        for item in ('查看详情', '查看报告', '生成报告（手动）', '发布', '收藏', '重命名', '删除'):
            assert item in (drv.page_source or ''), 'menu item missing: %s' % item
        print('P1 menu items all present')
        # 关闭菜单（base-ui 须 Escape，body.click 无效）
        _close_menu(drv)

        # ---- P2 收藏 → POST /tasks/502/favorite ----
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_NO_REPORT)
        _click_row_menu(drv, row, '收藏')
        wait_for(lambda: '已加入收藏' in (drv.page_source or ''), 12, 'favorite toast')
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p2_favorited.png'))
        reqs = collect_requests(drv)
        fav_reqs = count_api_calls(reqs, '/api/v1/tasks/502/favorite', methods=['POST'])
        print('P2 favorite POST:', [(r['method'], r['url'], r['status']) for r in fav_reqs])
        assert fav_reqs, 'no POST /tasks/502/favorite captured'
        # 星标回显
        wait_for(lambda: '★' in (drv.page_source or '') or '取消收藏' in (drv.page_source or ''), 15, 'star shown')

        # ---- 取消收藏 → DELETE /tasks/502/favorite ----
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_NO_REPORT)
        _click_row_menu(drv, row, '取消收藏')
        wait_for(lambda: '已取消收藏' in (drv.page_source or ''), 12, 'unfavorite toast')
        time.sleep(2)
        reqs = collect_requests(drv)
        unfav_reqs = count_api_calls(reqs, '/api/v1/tasks/502/favorite', methods=['DELETE'])
        print('P2 unfavorite DELETE:', [(r['method'], r['url'], r['status']) for r in unfav_reqs])
        assert unfav_reqs, 'no DELETE /tasks/502/favorite captured'

        # ---- P4 查看报告（容器 497 有报告 494）----
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_WITH_REPORT)
        _click_row_menu(drv, row, '查看报告')
        wait_for(lambda: '/report/494' in (drv.current_url or ''), 20, 'navigate /report/494')
        wait_for(lambda: '报告' in (drv.page_source or ''), 15, 'report page render')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p4_report_nav.png'))
        reqs = collect_requests(drv)
        rep_nav = count_api_calls(reqs, '/api/v1/reports/494')
        print('P4 view report:', drv.current_url, [(r['method'], r['url'], r['status']) for r in rep_nav])
        assert rep_nav, 'no GET /reports/494 captured'

        # 回到挑选合并
        drv.get(base + '/tasks/cherry-picks')
        wait_for(lambda: CONTAINER_NO_REPORT in (drv.page_source or ''), 30, 'back to containers')

        # ---- P5 生成报告（手动）容器 502（当前有旧报告 495 → 覆盖确认分支）----
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_NO_REPORT)
        _click_row_menu(drv, row, '生成报告（手动）')
        # 定位请求 POST /reports/generate-task（真实请求，非 toast 假成功）。
        # 注意：get_log 是 drain 语义——循环内累积而非覆盖，最终 collect 不再二次读。
        captured = []
        deadline = time.time() + 25
        while time.time() < deadline:
            captured += collect_requests(drv)
            if count_api_calls(captured, '/api/v1/reports/generate-task', methods=['POST']):
                break
            time.sleep(0.8)
        gen_reqs = count_api_calls(captured, '/api/v1/reports/generate-task', methods=['POST'])
        print('P5 generate-task POST:', [(r['method'], r['url'], r['status']) for r in gen_reqs])
        assert gen_reqs, 'no POST /reports/generate-task captured'
        # 等分支落定：覆盖确认弹窗（有旧报告）或生成中 toast（无旧报告）
        deadline = time.time() + 15
        while time.time() < deadline:
            src = drv.page_source or ''
            if '将删除当前报告并重新生成' in src or '正在生成报告' in src:
                break
            time.sleep(0.5)
        if '将删除当前报告并重新生成' in (drv.page_source or ''):
            drv.save_screenshot(os.path.join(ARTIFACTS, 'p5_regen_confirm.png'))
            # 点「查看旧报告」→ 跳旧报告（cancel 语义）
            _click_in_dialog(drv, '查看旧报告')
            wait_for(lambda: '/report/495' in (drv.current_url or ''), 20, 'view old report after regen confirm')
            print('P5 regen-confirm → 查看旧报告:', drv.current_url)
            gen_nav = True
        else:
            try:
                wait_for(lambda: '/report/' in (drv.current_url or '') and '/report/494' not in drv.current_url, 90, 'report page after generate')
                time.sleep(1.5)
                drv.save_screenshot(os.path.join(ARTIFACTS, 'p5_report_generated.png'))
                print('P5 generated report URL:', drv.current_url)
                gen_nav = True
            except AssertionError:
                gen_nav = False
                print('P5 SSE nav timeout (POST proven)')

        # 回到挑选合并
        drv.get(base + '/tasks/cherry-picks')
        wait_for(lambda: CONTAINER_NO_REPORT in (drv.page_source or ''), 30, 'back to containers after gen')

        # ---- P3 重命名 → PUT /tasks/502 ----
        new_name = '接线测试_INT1277_容器_已重命名'
        drv.get_log('performance')
        row = _row_containing(drv, CONTAINER_NO_REPORT)
        _click_row_menu(drv, row, '重命名')
        wait_for(lambda: '重命名容器' in (drv.page_source or ''), 12, 'rename dialog')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p3_rename_dialog.png'))
        name_input = drv.find_element(By.ID, 'container-rename-name')
        # React 受控 input：用原生 value setter + input 事件（直接赋 .value 不触发 onChange）
        drv.execute_script("""
        const el = arguments[0];
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        """, name_input, new_name)
        time.sleep(0.3)
        drv.execute_script("""
        const btns = [...document.querySelectorAll('button')];
        const b = btns.find(x => x.textContent && x.textContent.trim() === '保存');
        if (b) b.click();
        """)
        wait_for(lambda: '任务名称已更新' in (drv.page_source or ''), 12, 'rename toast')
        wait_for(lambda: new_name in (drv.page_source or ''), 20, 'renamed in list')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p3_renamed_list.png'))
        reqs = collect_requests(drv)
        ren_reqs = count_api_calls(reqs, '/api/v1/tasks/502', methods=['PUT'])
        print('P3 rename PUT:', [(r['method'], r['url'], r['status']) for r in ren_reqs])
        assert ren_reqs, 'no PUT /tasks/502 captured'

        # ---- P6 发布 → PublishTaskDialog ----
        drv.get_log('performance')
        row = _row_containing(drv, new_name)
        _click_row_menu(drv, row, '发布')
        wait_for(lambda: '发布任务' in (drv.page_source or '') and '发布为可复用' in (drv.page_source or ''), 15, 'publish dialog')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p6_publish_dialog.png'))
        # 关闭（取消，不创建已发布任务）
        drv.execute_script("""
        const btns = [...document.querySelectorAll('[data-slot="dialog-content"] button, button')];
        const b = btns.find(x => x.textContent && x.textContent.trim() === '取消');
        if (b) b.click();
        """)
        time.sleep(1)

        # ---- P7 删除 → ConfirmDialog → DELETE /tasks/502 ----
        drv.get_log('performance')
        row = _row_containing(drv, new_name)
        _click_row_menu(drv, row, '删除')
        wait_for(lambda: '将把 1 个任务移入回收站' in (drv.page_source or ''), 12, 'delete confirm dialog')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p7_delete_confirm.png'))
        _click_in_dialog(drv, '删除')
        wait_for(lambda: '已移入回收站' in (drv.page_source or ''), 15, 'delete toast')
        wait_for(lambda: new_name not in (drv.page_source or ''), 25, 'container removed from list')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p7_deleted_list.png'))
        reqs = collect_requests(drv)
        del_reqs = count_api_calls(reqs, '/api/v1/tasks/502', methods=['DELETE'])
        print('P7 delete DELETE:', [(r['method'], r['url'], r['status']) for r in del_reqs])
        assert del_reqs, 'no DELETE /tasks/502 captured'

        # ---- 深色截图（剩余容器 497 行菜单）----
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get(base + '/tasks/cherry-picks')
        wait_for(lambda: CONTAINER_WITH_REPORT in (drv.page_source or ''), 30, 'dark list')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p8_list_dark.png'))
        row = _row_containing(drv, CONTAINER_WITH_REPORT)
        btn = row.find_element(By.CSS_SELECTOR, '[aria-label="挑选合并任务操作"]')
        drv.execute_script('arguments[0].click();', btn)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p8_row_menu_dark.png'))

        # ---- Network 证据文本图 ----
        lines = []
        lines.append('P2 favorite: %d POST /tasks/502/favorite' % len(fav_reqs))
        for r in fav_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P2 unfavorite: %d DELETE /tasks/502/favorite' % len(unfav_reqs))
        for r in unfav_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P4 view report: %d GET /reports/494' % len(rep_nav))
        for r in rep_nav:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P5 generate: %d POST /reports/generate-task' % len(gen_reqs))
        for r in gen_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P5 SSE nav complete: %s' % gen_nav)
        lines.append('P3 rename: %d PUT /tasks/502' % len(ren_reqs))
        for r in ren_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P7 delete: %d DELETE /tasks/502' % len(del_reqs))
        for r in del_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        net_png = render_text_png('INT-1277 Container Row Ops Network Evidence', lines, 'network_evidence.png')
        print('network evidence:', net_png)
        print('\n'.join(lines))
        print('ALL PASS')
        return 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
