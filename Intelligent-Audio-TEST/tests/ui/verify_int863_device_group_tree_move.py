# -*- coding: utf-8 -*-
"""INT-863 验收浏览器实测：设备分组嵌套/移动（独立脚本，不挂 pytest 门禁）。

验证点（对齐卡面验收标准）：
1. 分组管理弹窗显示分组树；有子分组的父级 Chevron 展开/折叠（含 3 层嵌套）；
2. 新建/编辑分组可选父分组（根或任一分组），编辑回显 parentId、选项排除自身与后代；
3. 「移动」：选目标父分组提交 → 分组树级联刷新；移到根成功（PUT .../move 真实请求）；
4. 删除含子分组：确认文案含子分组数，确认后父+子树消失、设备保留（API 回查）；
5. 浅色 + 深色截图 + Network 证据。

运行前提：dev server http://127.0.0.1:5420（frontend/，连 :5000 常驻后端，AUTH_MODE=off），
chromedriver 走 selenium 缓存路径。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from tests.ui.utils.api_client import ApiClient

BASE = os.environ.get('INT863_BASE', 'http://127.0.0.1:5420')
API_BASE = os.environ.get('INT863_API_BASE', 'http://127.0.0.1:5000')
CHROME_BIN = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
CHROMEDRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
SHOT_DIR = os.environ.get(
    'INT863_SHOT_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int863'))
NET_EVIDENCE = os.path.join(SHOT_DIR, 'network_move_evidence.json')

RESULTS = []


def record(name: str, ok: bool, detail: str = ''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail})
    print(f'{"PASS" if ok else "FAIL"} | {name} | {detail}')


def new_driver(width=1600, height=1000, perf_log=False):
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--lang=zh-CN')
    if perf_log:
        opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    svc = Service(CHROMEDRIVER)
    return webdriver.Chrome(service=svc, options=opts)


def wait_visible(driver, css, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))


def wait_gone(driver, css, timeout=15):
    WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, css)))


def wait_count(driver, css, expected, timeout=15):
    WebDriverWait(driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, css)) == expected)


def group_rows(driver):
    """返回分组数据行（含 dg-actions 的 tbody tr，排除成员展开行）。"""
    return [r for r in driver.find_elements(By.CSS_SELECTOR, '.dg-table tbody tr')
            if r.find_elements(By.CSS_SELECTOR, 'td.dg-actions')]


def row_texts(driver):
    return [r.find_element(By.CSS_SELECTOR, '.dg-name').text for r in group_rows(driver)]


def find_row(driver, name):
    for r in group_rows(driver):
        if r.find_element(By.CSS_SELECTOR, '.dg-name').text == name:
            return r
    return None


def row_depth(driver, name):
    r = find_row(driver, name)
    if r is None:
        return None
    indent = r.find_elements(By.CSS_SELECTOR, '.dg-tree-indent')
    if not indent:
        return 0
    style = indent[0].get_attribute('style') or ''
    if 'width:' not in style:
        return 0
    px = ''.join(c for c in style.split('width:')[1] if c.isdigit() or c == '.')
    try:
        return int(float(px) / 18 + 0.5)
    except (ValueError, ZeroDivisionError):
        return 0


def click_btn(row, text):
    btns = row.find_elements(By.CSS_SELECTOR, 'button')
    for b in btns:
        if text in b.text:
            b.click()
            return True
    return False


def capture_move_network(driver, out_path):
    """从 Chrome performance log 抽取 move 相关 Network 事件（对齐实施者证据格式）。"""
    entries = []
    try:
        logs = driver.get_log('performance')
    except Exception:
        logs = []
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
            m = msg.get('message', {})
            if m.get('method') != 'Network.requestWillBeSent':
                continue
            url = m.get('params', {}).get('request', {}).get('url', '')
            method = m.get('params', {}).get('request', {}).get('method', '')
            if '/test-devices/device-groups' in url:
                entries.append({'event': 'Network.requestWillBeSent', 'url': url, 'method': method, 'status': None})
        except Exception:
            continue
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump({'ts': int(time.time()), 'events': entries}, fh, ensure_ascii=False, indent=2)
    return entries


def main():
    api = ApiClient(API_BASE)
    api.login('admin', 'admin123')
    suffix = f'863{int(time.time()) % 100000}'
    created_ids = []
    device_id = 21  # 隔离库既有测试设备

    def api_req(method, path, **kw):
        import httpx
        r = httpx.request(method, f'{API_BASE}/api/v1{path}', headers=api._headers(),
                          timeout=15, trust_env=False, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f'{method} {path} -> {r.status_code}: {r.text[:120]}')
        return r.json()

    # ── 准备测试数据 ──────────────────────────────
    grp_a = api_req('POST', '/test-devices/device-groups',
                    json={'name': f'接线测试_{suffix}_A', 'group_type': 'test', 'description': 'INT-863 树/移动实测'})
    a_id = grp_a['data']['id']
    created_ids.append(a_id)
    grp_a1 = api_req('POST', '/test-devices/device-groups',
                     json={'name': f'接线测试_{suffix}_A1', 'group_type': 'test', 'parent_id': a_id})
    a1_id = grp_a1['data']['id']
    created_ids.append(a1_id)
    grp_a1a = api_req('POST', '/test-devices/device-groups',
                      json={'name': f'接线测试_{suffix}_A1a', 'group_type': 'test', 'parent_id': a1_id})
    a1a_id = grp_a1a['data']['id']
    created_ids.append(a1a_id)
    grp_b = api_req('POST', '/test-devices/device-groups',
                    json={'name': f'接线测试_{suffix}_B', 'group_type': 'test'})
    b_id = grp_b['data']['id']
    created_ids.append(b_id)
    # A 挂 1 台设备（deviceCount=1，供删除文案断言）
    api_req('POST', f'/test-devices/device-groups/{a_id}/devices', json={'device_ids': [device_id]})
    names = {a_id: f'接线测试_{suffix}_A', a1_id: f'接线测试_{suffix}_A1',
             a1a_id: f'接线测试_{suffix}_A1a', b_id: f'接线测试_{suffix}_B'}
    print(f'[setup] groups: {[(i, names[i]) for i in (a_id, a1_id, a1a_id, b_id)]}')

    driver = None
    try:
        driver = new_driver(perf_log=True)
        driver.get(BASE + '/#/Device')
        wait_visible(driver, '.device-view', timeout=30)
        time.sleep(1.0)  # 设备列表加载
        # 打开分组管理
        gm_btns = [b for b in driver.find_elements(By.CSS_SELECTOR, 'button')
                   if '分组管理' in b.text]
        assert gm_btns, '未找到「分组管理」入口按钮'
        gm_btns[0].click()
        wait_visible(driver, '.dg-modal', timeout=15)
        # 等待表格行渲染（4 个根/子分组初始仅 2 根行可见）
        wait_count(driver, '.dg-table tbody tr', 2, timeout=15)

        # ── 1. 树形渲染 + Chevron 展开/折叠 ─────────
        texts0 = row_texts(driver)
        record('初始树：只显示根分组（A/B），子分组折叠',
               set(texts0) == {names[a_id], names[b_id]} and names[a1_id] not in texts0,
               f'rows={texts0}')

        # 展开 A → A1 出现
        row_a = find_row(driver, names[a_id])
        chev = row_a.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        assert chev, f'{names[a_id]} 应有 Chevron'
        chev[0].click()
        time.sleep(0.6)
        texts1 = row_texts(driver)
        record('展开 A → 子分组 A1 显示',
               names[a1_id] in texts1 and names[a1a_id] not in texts1,
               f'rows={texts1}')

        # 展开 A1 → A1a 出现（3 层嵌套）
        row_a1 = find_row(driver, names[a1_id])
        chev1 = row_a1.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        assert chev1, f'{names[a1_id]} 应有 Chevron'
        chev1[0].click()
        time.sleep(0.6)
        texts2 = row_texts(driver)
        record('展开 A1 → 孙分组 A1a 显示（3 层嵌套）',
               names[a1a_id] in texts2,
               f'rows={texts2}')
        # 深度断言：A1a 行缩进深于 A1 行
        dep_a1 = row_depth(driver, names[a1_id])
        dep_a1a = row_depth(driver, names[a1a_id])
        record('缩进层级：A1a 深于 A1', dep_a1a is not None and dep_a1 == 1 and dep_a1a == 2,
               f'depth A={row_depth(driver, names[a_id])} A1={dep_a1} A1a={dep_a1a}')

        # 折叠 A1、A
        chev1[0].click()
        time.sleep(0.4)
        chev[0].click()
        time.sleep(0.4)
        texts3 = row_texts(driver)
        record('折叠后子分组隐藏', names[a1_id] not in texts3 and names[a1a_id] not in texts3,
               f'rows={texts3}')

        # 浅色截图：展开树（截图前再展开）
        chev = find_row(driver, names[a_id]).find_elements(By.CSS_SELECTOR, '.dg-chevron')[0]
        chev.click()
        time.sleep(0.5)
        os.makedirs(SHOT_DIR, exist_ok=True)
        light_tree = os.path.join(SHOT_DIR, '01_tree_expanded_light.png')
        driver.save_screenshot(light_tree)
        record('浅色截图（树展开）', os.path.isfile(light_tree), light_tree)

        # 深色截图（.dark 结构预留类注入 <html>）
        driver.execute_script('document.documentElement.classList.add("dark");')
        time.sleep(0.6)
        dark_tree = os.path.join(SHOT_DIR, '02_tree_expanded_dark.png')
        driver.save_screenshot(dark_tree)
        record('深色截图（树展开）', os.path.isfile(dark_tree), dark_tree)
        driver.execute_script('document.documentElement.classList.remove("dark");')
        time.sleep(0.4)

        # ── 2. 新建/编辑表单父分组选项 ──────────────
        # 设备数角标：A 挂 1 台设备，行内应显示 1
        row_a = find_row(driver, names[a_id])
        tds = row_a.find_elements(By.CSS_SELECTOR, 'td')
        record('设备数角标：A 行显示 1（已挂 1 台设备）', tds[2].text.strip() == '1',
               f'device_count_cell={tds[2].text.strip() if len(tds) > 2 else "n/a"}')

        # 搜索过滤：保留祖先链
        search_input = driver.find_element(By.CSS_SELECTOR, '.dg-search')
        search_input.clear()
        search_input.send_keys(names[a1a_id])
        time.sleep(0.6)
        texts_search = row_texts(driver)
        # 搜索命中孙分组 → 祖先链（A/A1）保留、无关分组 B 隐藏；
        # 命中行 A1a 需在父级 A1 展开后才可见（搜索不自动展开）
        record('搜索 A1a：祖先链保留（A/A1 显示）、B 隐藏',
               set(texts_search) == {names[a_id], names[a1_id]} and names[b_id] not in texts_search,
               f'rows={texts_search}')
        # 展开 A1 后搜索命中行 A1a 可见
        row_a1 = find_row(driver, names[a1_id])
        chev1 = row_a1.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        if chev1:
            chev1[0].click()
            time.sleep(0.5)
        texts_search2 = row_texts(driver)
        record('搜索 A1a：展开祖先后命中行可见', names[a1a_id] in texts_search2,
               f'rows={texts_search2}')
        search_input.clear()
        time.sleep(0.5)
        # 用 JS 显式派发 input 事件确保 Vue v-model 同步清空（selenium clear 偶发不触发）
        driver.execute_script(
            'const i=document.querySelector(".dg-search"); i.value="";'
            ' i.dispatchEvent(new Event("input",{bubbles:true}));')
        time.sleep(0.5)
        # 清空搜索后折叠全部，再展开 A（供后续编辑/移动用例）
        driver.execute_script('document.querySelectorAll(".dg-chevron").forEach(el=>el.click());')
        time.sleep(0.4)
        chev_a = find_row(driver, names[a_id]).find_elements(By.CSS_SELECTOR, '.dg-chevron')
        if chev_a:
            chev_a[0].click()
            time.sleep(0.4)

        driver.find_element(By.CSS_SELECTOR, '.dg-toolbar .btn-primary').click()
        time.sleep(0.4)
        edit_select = driver.find_element(By.CSS_SELECTOR, '.dg-form select')
        opts = [o.text for o in edit_select.find_elements(By.CSS_SELECTOR, 'option')]
        record('新建表单父分组选项含根与全部分组',
               '根分组（顶层）' in opts and names[a_id] in opts and names[b_id] in opts
               and names[a1_id] in opts and names[a1a_id] in opts,
               f'opts={opts}')
        # 取消新建
        driver.find_element(By.CSS_SELECTOR, '.dg-form .btn-secondary').click()
        time.sleep(0.3)

        # 编辑 A1 → 父分组回显 A、选项排除自身与后代
        row_a1 = find_row(driver, names[a1_id])
        click_btn(row_a1, '编辑')
        time.sleep(0.4)
        edit_select = driver.find_element(By.CSS_SELECTOR, '.dg-form select')
        val = edit_select.get_attribute('value')
        opts = [o.text for o in edit_select.find_elements(By.CSS_SELECTOR, 'option')]
        record('编辑 A1 回显 parentId=A，选项排除自身与后代',
               val == a_id and names[a1_id] not in opts and names[a1a_id] not in opts
               and names[a_id] in opts,
               f'value={val} opts={opts}')
        driver.find_element(By.CSS_SELECTOR, '.dg-form .btn-secondary').click()
        time.sleep(0.3)

        # 展开 A1（A 已展开）让孙分组 A1a 可见，供移动操作
        row_a1 = find_row(driver, names[a1_id])
        chev1 = row_a1.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        if chev1:
            chev1[0].click()
            time.sleep(0.5)

        # ── 3. 移动：A1a 移到根（顶层） ─────────────
        row_a1a = find_row(driver, names[a1a_id])
        click_btn(row_a1a, '移动')
        time.sleep(0.4)
        move_form = driver.find_element(By.CSS_SELECTOR, '.dg-form select')
        move_opts = [o.text for o in move_form.find_elements(By.CSS_SELECTOR, 'option')]
        record('移动表单目标选项含根 + 候选父分组（排除自身）',
               '根分组（顶层）' in move_opts and names[a_id] in move_opts
               and names[b_id] in move_opts and names[a1a_id] not in move_opts,
               f'opts={move_opts}')
        # 选根分组（顶层）→ 移动
        Select(move_form).select_by_value('')
        driver.execute_script('document.querySelectorAll(".dg-form .btn-primary")[0].click();')
        # 等待：移动后 A1a 变为根行
        time.sleep(1.2)
        texts_after = row_texts(driver)
        dep_after = row_depth(driver, names[a1a_id])
        # 展开态仍保持，需重新核对：A1a 现为根行（depth 0）
        record('移到根：A1a 出现在顶层行',
               names[a1a_id] in texts_after and dep_after == 0,
               f'rows={texts_after} depth={dep_after}')
        # A1 现在无子分组（A1a 移出）→ A1 行不再有 Chevron
        row_a1 = find_row(driver, names[a1_id])
        no_chev = not row_a1.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        record('A1 失去子分组后 Chevron 消失', no_chev, 'A1 no chevron' if no_chev else 'A1 still has chevron')

        # ── 4. 移动：A1a 移到 B 下 ──────────────────
        row_a1a = find_row(driver, names[a1a_id])
        click_btn(row_a1a, '移动')
        time.sleep(0.4)
        move_form = driver.find_element(By.CSS_SELECTOR, '.dg-form select')
        # 选 B
        Select(move_form).select_by_value(b_id)
        driver.execute_script('document.querySelectorAll(".dg-form .btn-primary")[0].click();')
        time.sleep(1.2)
        # 展开 B → A1a 在其下
        row_b = find_row(driver, names[b_id])
        chev_b = row_b.find_elements(By.CSS_SELECTOR, '.dg-chevron')
        assert chev_b, 'B 应有 Chevron（已含 A1a）'
        chev_b[0].click()
        time.sleep(0.5)
        texts_b = row_texts(driver)
        idx_b = texts_b.index(names[b_id])
        dep_b_after = row_depth(driver, names[a1a_id])
        record('移到 B：A1a 出现在 B 行下（depth 1）',
               names[a1a_id] in texts_b[idx_b + 1:idx_b + 3] and dep_b_after == 1,
               f'rows={texts_b} depth={dep_b_after}')
        # 浅色截图：移动后树
        light_move = os.path.join(SHOT_DIR, '03_after_move_light.png')
        driver.save_screenshot(light_move)
        record('浅色截图（移动后）', os.path.isfile(light_move), light_move)

        # Network 证据（performance log 抽取 move PUT）
        net_entries = capture_move_network(driver, NET_EVIDENCE)
        move_puts = [e for e in net_entries if e['method'] == 'PUT' and '/move' in e['url']]
        record('Network 捕获 PUT .../move 真实请求', len(move_puts) >= 2,
               f'PUT move count={len(move_puts)} entries={move_puts}')

        # ── 5. 删除含子分组：B（含 A1a） ────────────
        row_b = find_row(driver, names[b_id])
        click_btn(row_b, '删除')
        time.sleep(0.6)
        confirm_msg = wait_visible(driver, '.modal-confirmMessage', timeout=10)
        msg = confirm_msg.text
        record('删除含子分组确认文案含子分组数',
               '1 个子分组' in msg and names[b_id] in msg,
               f'msg={msg}')
        # 确认删除（danger 按钮）
        driver.find_element(By.CSS_SELECTOR, '.modal-confirmActions .btn-danger').click()
        time.sleep(1.2)
        wait_gone(driver, '.modal-confirm', timeout=10)
        texts_final = row_texts(driver)
        record('确认删除后 B 消失（级联删子树）',
               names[b_id] not in texts_final and names[a1a_id] not in texts_final,
               f'rows={texts_final}')

        # 深色截图：删除后（A 仍在）
        driver.execute_script('document.documentElement.classList.add("dark");')
        time.sleep(0.6)
        dark_final = os.path.join(SHOT_DIR, '04_after_delete_dark.png')
        driver.save_screenshot(dark_final)
        record('深色截图（删除后）', os.path.isfile(dark_final), dark_final)

        # ── 6. 设备保留回查（API） ──────────────────
        try:
            dev = api_req('GET', f'/test-devices/{device_id}')
            dev_ok = dev.get('data', {}).get('id') == device_id
        except Exception as e:
            dev_ok = False
            print('device recheck error:', e)
        record('设备保留：删除级联后设备仍存在（API 回查）', dev_ok, f'device {device_id}')
        try:
            api_req('GET', f'/test-devices/device-groups/{b_id}')
            b_gone = False
        except Exception:
            b_gone = True
        record('B 分组已被级联删除（API 回查 404/400）', b_gone, 'B gone' if b_gone else 'B still exists')

        # ── 关闭弹窗（回归：重复打开仍正常） ────────
        driver.find_element(By.CSS_SELECTOR, '.dg-close').click()
        wait_gone(driver, '.dg-modal', timeout=10)
        gm_btns = [b for b in driver.find_elements(By.CSS_SELECTOR, 'button') if '分组管理' in b.text]
        gm_btns[0].click()
        wait_visible(driver, '.dg-modal', timeout=15)
        wait_count(driver, '.dg-table tbody tr', 1, timeout=15)
        texts_reopen = row_texts(driver)
        record('关闭后重开弹窗正常（剩余 A 渲染，子分组折叠）',
               texts_reopen == [names[a_id]],
               f'rows={texts_reopen}')
        # 重开弹窗后仍可展开 A 看到 A1
        chev_a = find_row(driver, names[a_id]).find_elements(By.CSS_SELECTOR, '.dg-chevron')
        if chev_a:
            chev_a[0].click()
            time.sleep(0.5)
        record('重开后 Chevron 展开仍显示 A1', names[a1_id] in row_texts(driver),
               f'rows={row_texts(driver)}')
    except Exception as e:
        print('EXCEPTION:', e)
        traceback.print_exc()
        if driver is not None:
            os.makedirs(SHOT_DIR, exist_ok=True)
            driver.save_screenshot(os.path.join(SHOT_DIR, 'ERR_fail.png'))
        record('脚本执行无异常', False, str(e)[:200])
    finally:
        # ── 清理测试数据（无残留） ──────────────────
        try:
            # 删除顺序：先子后父（防级联二次报错）
            for gid in reversed(created_ids):
                try:
                    api_req('DELETE', f'/test-devices/device-groups/{gid}', params={'cascade': 'true'})
                except Exception as e:
                    print(f'[cleanup] {gid}: {str(e)[:60]}')
            # 回查残留
            import httpx
            r = httpx.get(f'{API_BASE}/api/v1/test-devices/device-groups', params={'page': 1, 'per_page': 200},
                          headers=api._headers(), timeout=15, trust_env=False)
            remain = [g for g in r.json()['data']['items'] if suffix in g.get('name', '')]
            print(f'[cleanup] residual groups with {suffix}: {len(remain)}')
        except Exception as e:
            print('[cleanup] ERROR:', str(e)[:100])
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    print('\n==== INT-863 验收结果 ====')
    passed = sum(1 for r in RESULTS if r['ok'])
    for r in RESULTS:
        print(f'  {"✅" if r["ok"] else "❌"} {r["name"]} | {r["detail"]}')
    print(f'PASS {passed}/{len(RESULTS)}')
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
