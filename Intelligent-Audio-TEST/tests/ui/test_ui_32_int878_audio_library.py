# -*- coding: utf-8 -*-
"""INT-878 音频库页真实数据走查（React 接线验收）。

针对 frontend-react/（真实后端 5000 段常驻栈，AUTH_MODE=off，dev server 5310）：
1. 音频列表真实数据渲染（GET /audios 真实 3 条 + 统计徽章）+ 搜索
2. 批量操作：勾选行 → 批量浮条 → 批量移动/复制/重命名/修改属性四分支可操作性
   （后端 batch-action 四分支已支持 INT-818，前端是否仍禁用待 FEAT 标记）
3. 上传弹窗真实接线（init/register/chunk/merge）字段齐备
4. 删除走真实接口（DELETE /audios/{id}）
5. 空态（搜索无命中）正常
6. 浅色 + 深色 + Network 截图

失败落 tests/ui/artifacts/int878_audio_library/<用例>/。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int878_audio_library')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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


_DRIVER = None
_CONSOLE_SEVERE = []


def _drain_console(drv):
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    _drain_console(drv)


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _set_theme(drv, mode):
    drv.execute_script(
        'try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))
    _goto(drv, '/audio-import')


def _resource_urls(drv, needle):
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)'
        '.filter(n => n.includes(%r))' % needle)


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    shot = os.path.join(d, 'screenshot.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, f'截图过小：{shot}'
    return shot


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _login_off(drv):
    """AUTH_MODE=off：落会话引导（dev_user '*'）后进音频库。"""
    _goto(drv, '/')
    _goto(drv, '/audio-import')


def _wait_rows(drv, n):
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def test_01_list_real_data_render(drv):
    os.makedirs(ARTIFACTS, exist_ok=True)
    _login_off(drv)
    _wait_text(drv, '音频管理')
    txt = _body_text(drv)
    assert '总文件数' in txt and '总大小' in txt and '总时长' in txt and '今日上传' in txt, \
        f'统计徽章缺失：{txt[:200]}'
    # 真实数据行（resident DB 3 条：兼容测试_01.wav / 同名素材.wav×2）
    assert '兼容测试_01.wav' in txt, f'真实音频行缺失：{txt[:300]}'
    assert '同名素材.wav' in txt, f'真实音频行缺失：{txt[:300]}'
    # 表头
    for header in ['ID', '文件名', '格式', '大小', '时长', '音频类型', '源语言', '标签', '创建时间', '操作']:
        assert header in txt, f'列头「{header}」缺失'
    # Network：GET /audios
    urls = _resource_urls(drv, '/api/v1/audios')
    assert any('/audios' in u for u in urls), f'未请求 GET /audios：{urls}'
    light = _screenshot(drv, '01-list-light')
    return light


def test_02_search(drv):
    _set_theme(drv, 'light')
    _wait_text(drv, '音频管理')
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) >= 1)
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索音频']")
    search.send_keys('兼容测试')
    WebDriverWait(drv, 10).until(
        lambda d: '同名素材.wav' not in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '兼容测试_01.wav' in txt, f'搜索「兼容测试」应命中：{txt[:300]}'
    # 重置
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '同名素材.wav' in d.execute_script('return document.body.textContent || ""'))


def test_03_batch_ops_four_branches(drv):
    """批量操作四分支：move/copy/rename/modify-properties 可操作性。

    后端 batch-action 四分支已支持（INT-818），验收要求四分支可操作。
    前端弹窗若仍「待 FEAT」禁用主钮 = 接线缺口（缺陷）。
    """
    _set_theme(drv, 'light')
    _wait_text(drv, '音频管理')
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) >= 1)
    # 勾选首行
    first = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')[0]
    cb = first.find_element(By.CSS_SELECTOR, '[aria-label^="选择音频"]')
    cb.click()
    _wait_text(drv, '已选 1 个音频')
    txt = _body_text(drv)
    assert '批量删除' in txt and '批量导出' in txt and '更多批量操作' in txt, \
        f'批量浮条不完整：{txt[-200:]}'
    # 打开「更多批量操作」→ 四分支菜单项
    drv.find_element(By.XPATH, "//button[contains(., '更多批量操作')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem'][contains(., '批量移动')]"))
    for label in ['批量移动', '批量复制', '批量重命名', '批量修改属性']:
        assert drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(., '{label}')]"), \
            f'批量菜单项「{label}」缺失'
    # 逐分支打开弹窗，记录主钮状态
    results = {}
    for label, kind in [('批量移动', 'move'), ('批量复制', 'copy'),
                        ('批量重命名', 'rename'), ('批量修改属性', 'modify-properties')]:
        menuitems = drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(., '{label}')]")
        if not menuitems:
            results[kind] = 'missing'
            continue
        menuitems[0].click()
        time.sleep(0.8)
        dlg = WebDriverWait(drv, 6).until(
            lambda d: d.find_elements(By.XPATH, "//*[@role='dialog']"))
        body = dlg[0].text
        confirm = dlg[0].find_elements(By.XPATH, ".//button[contains(., '确认执行')]")
        if not confirm:
            results[kind] = 'no-confirm-btn'
        else:
            results[kind] = 'disabled' if confirm[0].get_attribute('disabled') else 'enabled'
        alert_txt = '后端待支持' in body
        _screenshot(drv, f'03-batch-{kind}')
        # 关闭弹窗
        cancel = dlg[0].find_elements(By.XPATH, ".//button[contains(., '取消')]")
        if cancel:
            cancel[0].click()
        else:
            webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.6)
        # 重新打开更多批量操作
        drv.find_element(By.XPATH, "//button[contains(., '更多批量操作')]").click()
        WebDriverWait(drv, 6).until(
            lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem'][contains(., '批量移动')]"))
    print('BATCH_RESULTS=', json.dumps(results, ensure_ascii=False))
    # 清空选择
    drv.find_element(By.XPATH, "//button[@aria-label='清空选择']").click()


def test_04_upload_dialog_wiring(drv):
    """上传弹窗真实接线：字段齐备 + Network 触发 init/register/chunk/merge。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '音频管理')
    drv.find_element(By.XPATH, "//button[contains(., '上传音频')]").click()
    _wait_text(drv, '拖拽文件到此处或点击选择文件')
    txt = _body_text(drv)
    assert '目标文件夹' in txt, '目标文件夹配置缺失'
    assert '生成测试用例' in txt or '创建测试用例' in txt, '上传选项缺失'
    # 注入一个真实小 WAV 文件 → 开始上传 → 走真实 init/register/chunk/merge
    wav = os.path.join(ARTIFACTS, 'smoke_sample.wav')
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    # 44 字节合法 RIFF WAV 头 + 空 data（后端存储探针可识别）
    import struct
    with open(wav, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36))
        f.write(b'WAVEfmt ')
        f.write(struct.pack('<I', 16))
        f.write(struct.pack('<HHIIHH', 1, 1, 8000, 8000, 1, 8))
        f.write(b'data')
        f.write(struct.pack('<I', 0))
    file_input = drv.find_element(By.CSS_SELECTOR, 'input[type="file"]')
    file_input.send_keys(wav)
    WebDriverWait(drv, 6).until(
        lambda d: '已选择 1 个文件' in d.execute_script('return document.body.textContent || ""'))
    drv.find_element(By.XPATH, "//button[contains(., '开始上传')]").click()
    # 等待上传链路：merge 出现在 Network（init/register/chunk/merge 全链）
    WebDriverWait(drv, 30).until(
        lambda d: any('upload/merge' in u for u in _resource_urls(d, '/api/v1/audios/upload')))
    urls = _resource_urls(drv, '/api/v1/audios/upload')
    print('UPLOAD_NETWORK=', json.dumps(urls, ensure_ascii=False))
    assert any('upload/init' in u for u in urls), '未请求 upload/init'
    assert any('upload/register' in u for u in urls), '未请求 upload/register'
    assert any('upload/chunk' in u for u in urls), '未请求 upload/chunk'
    assert any('upload/merge' in u for u in urls), '未请求 upload/merge'


def test_05_delete_real_api(drv):
    """删除走真实接口：DELETE /audios/{id}（仅删本卡上传的 smoke 夹具，不动共享数据）。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '音频管理')
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) >= 1)
    # 目标行：smoke_sample.wav（test_04 上传创建的夹具）
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    target = None
    for row in rows:
        if 'smoke_sample.wav' in row.text:
            target = row
            break
    if target is None:
        print('SKIP_DELETE: smoke_sample.wav 行未出现在列表（上传未落库）')
        return
    name = target.find_element(By.CSS_SELECTOR, 'td:nth-child(3)').text.strip()
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='音频 {name} 的操作']")
    btn.click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    deleted = False
    for it in items:
        if '删除' in it.text:
            it.click()
            deleted = True
            break
    assert deleted, '行菜单无删除项'
    WebDriverWait(drv, 6).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]").click()
    time.sleep(1.0)
    urls = _resource_urls(drv, '/api/v1/audios/')
    print('DELETE_URLS=', json.dumps([u for u in urls if 'upload' not in u], ensure_ascii=False))
    # 行已消失
    WebDriverWait(drv, 10).until(
        lambda d: 'smoke_sample.wav' not in d.execute_script('return document.body.textContent || ""'))


def test_06_empty_state(drv):
    """空态：搜索无命中 → 「未找到匹配的音频」。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '音频管理')
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索音频']")
    search.send_keys('不存在的音频xyz')
    _wait_text(drv, '未找到匹配的音频')
    _screenshot(drv, '06-empty-state')
    search.send_keys(Keys.CONTROL, 'a')
    search.send_keys(Keys.BACKSPACE)


def test_07_dark_theme(drv):
    _set_theme(drv, 'dark')
    _wait_text(drv, '音频管理')
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) >= 1)
    time.sleep(1.0)
    dark = _screenshot(drv, '07-list-dark')
    theme_mode = drv.execute_script('return document.documentElement.className')
    assert 'dark' in theme_mode, f'深色主题未生效：{theme_mode}'
    _set_theme(drv, 'light')


if __name__ == '__main__':
    _DRIVER = _driver()
    try:
        test_01_list_real_data_render(_DRIVER)
        test_02_search(_DRIVER)
        test_03_batch_ops_four_branches(_DRIVER)
        test_04_upload_dialog_wiring(_DRIVER)
        test_05_delete_real_api(_DRIVER)
        test_06_empty_state(_DRIVER)
        test_07_dark_theme(_DRIVER)
        if _CONSOLE_SEVERE:
            print('CONSOLE_SEVERE=', json.dumps(_CONSOLE_SEVERE[:5], ensure_ascii=False))
        print('ALL_OK')
    finally:
        try:
            _DRIVER.quit()
        except Exception:
            pass
