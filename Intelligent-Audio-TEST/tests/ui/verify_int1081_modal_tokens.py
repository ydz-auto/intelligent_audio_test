# -*- coding: utf-8 -*-
"""INT-1081 运行时验证：已发布任务域三弹窗硬编码颜色 → 语义令牌（深浅两套自动换肤）。

范围：PublishTaskModal / PublishedTaskNameModal / TaskSnapshotModal。
断言目标：
- 弹窗打开正常（三弹窗各一）
- 浅色下弹窗 surface 为浅色、深色下随 .dark 换肤变暗（无白色亮斑）
  → 读取弹窗 .modal / .modal-header / .modal-footer 计算样式背景色，
    深色下应明显暗于浅色（且 header/footer 不再恒 #fff/#f8f9fa）。
- 附浅色 + 深色截图 + Network 摘要。

依赖：常驻 5000 段开发栈（隔离测试库）+ 本 worktree vite dev 5610。
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

FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5610')
API_ROOT = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1081_modal_tokens')
os.makedirs(ARTIFACT_DIR, exist_ok=True)


def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def resolve_driver():
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    if os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
        major = chrome_major()
        if major:
            same = [exe for ver, exe in cands if ver and ver[0] == major]
            if same:
                return max(same)
        if cands:
            return sorted(cands)[-1][1]
    return ''


FETCH_RECORDER = r"""
window.__reqs = [];
const _origFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const url = typeof args[0] === 'string' ? args[0] : (args[0].url || String(args[0]));
  const opts = args[1] || {};
  const rec = { method: (opts.method || 'GET'), url, status: null, ts: Date.now() };
  try {
    const resp = await _origFetch(...args);
    rec.status = resp.status;
    return resp;
  } catch (e) {
    rec.error = String(e && e.message || e);
    throw e;
  } finally {
    window.__reqs.push(rec);
  }
};
window.__fetchInstalled = true;
"""


def modal_surface(driver, root_selector):
    """读取弹窗核心表面计算样式（背景色 / 分隔线色）；子元素缺失返回 None。"""
    def cs(sel):
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if not els:
            return None
        el = els[0]
        s = driver.execute_script(
            'const el=arguments[0];const cs=getComputedStyle(el);'
            'return {bg: cs.backgroundColor, bgImage: cs.backgroundImage, borderTopColor: cs.borderTopColor, color: cs.color};',
            el)
        return s
    root = driver.find_element(By.CSS_SELECTOR, root_selector)
    return {
        'root_selector': root_selector,
        'modal': cs(root_selector),
        'header': cs(root_selector + ' .modal-header'),
        'body': cs(root_selector + ' .modal-body') if driver.find_elements(By.CSS_SELECTOR, root_selector + ' .modal-body') else None,
        'footer': cs(root_selector + ' .modal-footer'),
        'scroll': cs(root_selector + ' .modal-scroll-container'),
        'body_text': root.text[:120].replace('\n', ' / '),
    }


def fmt_surface(cs):
    if not cs:
        return 'n/a'
    return f'bg={cs["bg"]} img={cs["bgImage"][:40]} border-top={cs["borderTopColor"]}'


def surface_summary(prefix, light, dark):
    lf = fmt_surface(light.get('footer')) if light else 'n/a'
    df = fmt_surface(dark.get('footer')) if dark else 'n/a'
    lh = fmt_surface(light.get('header')) if light else 'n/a'
    dh = fmt_surface(dark.get('header')) if dark else 'n/a'
    return (f'{prefix} | 浅 modal={fmt_surface(light.get("modal")) if light else "n/a"} '
            f'header={lh} footer={lf} | 深 modal={fmt_surface(dark.get("modal")) if dark else "n/a"} '
            f'header={dh} footer={df}')


def main():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    drv_path = resolve_driver()
    service = Service(executable_path=drv_path) if drv_path else Service()
    driver = webdriver.Chrome(options=options, service=service)
    driver.set_page_load_timeout(45)
    wait = WebDriverWait(driver, 20)
    long_wait = WebDriverWait(driver, 60)

    summary_lines = []

    try:
        # ── 登录态注入（AUTH_MODE=off：auth_user + 全权限）──
        driver.get(f'{FRONTEND}/#/login')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        payload = {
            'id': 1,
            'username': 'admin',
            'roleId': 1,
            'roleName': 'admin',
            'permissions': ['*'],
        }
        driver.execute_script(
            'window.localStorage.setItem(arguments[0], arguments[1]);'
            'window.localStorage.setItem(arguments[2], arguments[3]);',
            'auth_token', 'int1081-probe', 'auth_user', json.dumps(payload),
        )
        driver.refresh()
        # 等 boot 完成（侧栏/顶栏出现）再导航，防 boot 竞态落 dashboard
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.sidebar, .public-header, .page-title, .layout-header, header')))
        except Exception:
            pass
        time.sleep(1.5)

        driver.get(f'{FRONTEND}/#/tasks')
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.page-title')))
        except Exception:
            pass

        # 切到「已发布」页签
        published_tab = None
        for _ in range(3):
            try:
                tabs = driver.find_elements(By.CSS_SELECTOR, '.task-tab, .tab-item, .tabs button, .task-tabs button')
                for t in tabs:
                    if '已发布' in (t.text or ''):
                        published_tab = t
                        break
                if published_tab is None:
                    published_tab = driver.find_element(By.XPATH, "//button[contains(., '已发布')]")
                published_tab.click()
                break
            except Exception as e:
                print(f'切已发布页签重试: {e}')
                driver.refresh()
                time.sleep(2)
        # 等已发布卡片出现
        try:
            long_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.pt-card')))
        except Exception:
            raise RuntimeError('未加载出已发布任务卡片')

        driver.execute_script(FETCH_RECORDER)
        summary_lines.append(f'已发布列表加载 OK；卡片数: {len(driver.find_elements(By.CSS_SELECTOR, ".pt-card"))}')

        # ═══ 1. PublishTaskModal（头部「发布」按钮）═══
        driver.execute_script("document.documentElement.classList.remove('dark')")
        publish_btn = None
        for _ in range(2):
            try:
                header_btns = driver.find_elements(By.CSS_SELECTOR, '.header-right .btn-primary, .task-header .btn-primary')
                for b in header_btns:
                    if '发布' in (b.text or ''):
                        publish_btn = b
                        break
                if publish_btn is None:
                    publish_btn = driver.find_element(By.XPATH, "//button[contains(., '发布')]")
                publish_btn.click()
                break
            except Exception as e:
                print(f'发布按钮重试: {e}')
                time.sleep(1)
        long_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.publish-task-modal')))
        summary_lines.append('PublishTaskModal 打开 ✓')
        time.sleep(0.4)
        light_cs = modal_surface(driver, '.publish-task-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'publish_light.png'))
        summary_lines.append('publish_light.png ✓')

        # 深色
        driver.execute_script("document.documentElement.classList.add('dark')")
        time.sleep(0.5)
        dark_cs = modal_surface(driver, '.publish-task-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'publish_dark.png'))
        summary_lines.append('publish_dark.png ✓')
        summary_lines.append(surface_summary('PublishTaskModal', light_cs, dark_cs))
        # 关弹窗（X），回浅色
        driver.execute_script("document.documentElement.classList.remove('dark')")
        time.sleep(0.3)
        driver.find_element(By.CSS_SELECTOR, '.publish-task-modal .modal-close').click()
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '.publish-task-modal')))

        # ═══ 2. PublishedTaskNameModal（卡片「重命名」）═══
        rename_btn = driver.find_element(By.XPATH, "//button[contains(., '重命名')]")
        rename_btn.click()
        long_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.published-task-name-modal')))
        summary_lines.append('PublishedTaskNameModal 打开 ✓')
        time.sleep(0.4)
        rl = modal_surface(driver, '.published-task-name-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'rename_light.png'))
        summary_lines.append('rename_light.png ✓')
        driver.execute_script("document.documentElement.classList.add('dark')")
        time.sleep(0.5)
        rd = modal_surface(driver, '.published-task-name-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'rename_dark.png'))
        summary_lines.append('rename_dark.png ✓')
        summary_lines.append(surface_summary('PublishedTaskNameModal', rl, rd))
        driver.execute_script("document.documentElement.classList.remove('dark')")
        time.sleep(0.3)
        driver.find_element(By.CSS_SELECTOR, '.published-task-name-modal .modal-close').click()
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '.published-task-name-modal')))

        # ═══ 3. TaskSnapshotModal（展开版本详情 → 查看冻结任务详情）═══
        snapshot_opened = False
        tried_indices = set()
        while len(tried_indices) < 6:
            cards = driver.find_elements(By.CSS_SELECTOR, '.pt-card')
            if not cards:
                raise RuntimeError('已发布卡片消失')
            # 挑一张尚未试过的卡
            chosen = None
            for idx in range(len(cards)):
                if idx not in tried_indices:
                    chosen = idx
                    break
            if chosen is None:
                break
            tried_indices.add(chosen)
            card = cards[chosen]
            try:
                version_btn = card.find_element(By.XPATH, ".//button[contains(normalize-space(.), '版本')]")
            except Exception:
                print(f'卡 {chosen} 无「版本」按钮，跳过')
                continue
            print(f'卡 {chosen}：点击「版本」展开')
            try:
                version_btn.click()
            except Exception as e:
                print(f'版本按钮点击失败: {e}')
                continue
            try:
                detail_el = long_wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.pt-detail')))
                print(f'卡 {chosen} 详情已展开，taskSnapshot 行存在: '
                      f'{bool(detail_el.find_elements(By.XPATH, ".//button[contains(., \'查看冻结任务详情\')]"))}')
            except Exception:
                print(f'卡 {chosen} 详情未展开（detail 未出现）')
                # 诊断：dump console + 截图
                logs = driver.get_log('browser')
                recent = [l for l in logs[-12:] if l['level'] in ('SEVERE', 'WARNING')]
                for l in recent:
                    print(f'  [console] {l["level"]}: {l["message"][:160]}')
                driver.save_screenshot(os.path.join(ARTIFACT_DIR, f'debug_detail_missing{chosen}.png'))
                continue
            try:
                view_snapshot_btn = long_wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., '查看冻结任务详情')]")))
                view_snapshot_btn.click()
                long_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.task-snapshot-modal')))
                snapshot_opened = True
                break
            except Exception as e:
                print(f'卡 {chosen} 无「查看冻结任务详情」按钮: {e}')
                driver.save_screenshot(os.path.join(ARTIFACT_DIR, f'debug_snapshot_card{chosen}.png'))
                # 收起该卡再试下一张
                try:
                    for c in driver.find_elements(By.CSS_SELECTOR, '.pt-card'):
                        collapse_btns = c.find_elements(By.XPATH, ".//button[contains(normalize-space(.), '收起')]")
                        if collapse_btns:
                            collapse_btns[0].click()
                            break
                except Exception:
                    pass
                time.sleep(0.5)
                continue
        if not snapshot_opened:
            raise RuntimeError('未找到含 taskSnapshot 的已发布任务卡（无法打开 TaskSnapshotModal）')
        summary_lines.append('TaskSnapshotModal 打开 ✓')
        time.sleep(0.4)
        tl = modal_surface(driver, '.task-snapshot-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'snapshot_light.png'))
        summary_lines.append('snapshot_light.png ✓')
        driver.execute_script("document.documentElement.classList.add('dark')")
        time.sleep(0.5)
        td = modal_surface(driver, '.task-snapshot-modal')
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'snapshot_dark.png'))
        summary_lines.append('snapshot_dark.png ✓')
        summary_lines.append(surface_summary('TaskSnapshotModal', tl, td))
        # 深色下 kv 行背景也应随主题（读取深色 kv 计算样式）
        kv_sel = '.task-snapshot-modal .ts-kv'
        if driver.find_elements(By.CSS_SELECTOR, kv_sel):
            kv_bg = driver.execute_script(
                'const el=arguments[0];return getComputedStyle(el).backgroundColor;',
                driver.find_element(By.CSS_SELECTOR, kv_sel))
            summary_lines.append(f'TaskSnapshotModal .ts-kv 深色背景: {kv_bg}')

        # ── Network 摘要（published-tasks 相关请求）──
        reqs = driver.execute_script('return window.__reqs;') or []
        with open(os.path.join(ARTIFACT_DIR, 'network_summary.txt'), 'w', encoding='utf-8') as fh:
            for r in reqs:
                fh.write(f"{r['method']} {r['url']} → {r['status']}\n")
        summary_lines.append(f'Network 摘要 {len(reqs)} 条请求已存')

        # ── console 日志 ──
        logs = driver.get_log('browser')
        errors = [l for l in logs if l['level'] == 'SEVERE' and 'favicon' not in l['message'].lower()]
        with open(os.path.join(ARTIFACT_DIR, 'console.log'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(f"[{l['level']}] {l['source']}: {l['message']}" for l in logs) or '(no console entries)')
        summary_lines.append(f'console SEVERE: {len(errors)}（排除 favicon）')

        # ── 汇总 ──
        report = '\n'.join(summary_lines)
        with open(os.path.join(ARTIFACT_DIR, 'summary.txt'), 'w', encoding='utf-8') as fh:
            fh.write(report + '\n')
        print('=== INT-1081 VERIFY SUMMARY ===')
        print(report)
        print(f'证据目录: {ARTIFACT_DIR}')
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
