# -*- coding: utf-8 -*-
"""INT-1072 走查：TestFlow 步骤2 混选设备+API + 执行模式控件 + 创建请求证据。

用真实后端（5000 段共享栈）走 E2E 测试向导：
  1. 步骤0 选算法 voice_llm → 步骤1 勾选分组用例 → 步骤2。
  2. 步骤2 截图：未混选（执行模式置灰）→ 混选（默认并行）→ 串行 + API先。
  3. 阻断 start 请求后提交创建，从后端 GET /tasks/{id} 核对
     device_ids/api_ids/config.execution_mode/serial_first（创建请求落库证据）。
  4. 删除测试任务收尾。

共享栈上其它并发 run 的设备健康检查会把假设备打回 offline，故脚本开头直接
把测试设备/API 的 DB status 置 online，并在页面加载前完成，选完即走（30s 窗口内）。

旧 Vue 未启用 .dark 主题（tokens.css 结构预留）；浅色为主，另用 JS 加 .dark class
试截一张深色，若未生效在交付评论注明。
"""
import json
import os
import time
import urllib.parse
import urllib.request

import psycopg2
from selenium import webdriver

BASE = 'http://127.0.0.1:5405'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
os.makedirs(OUT, exist_ok=True)
DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
GATEWAY = 'http://localhost:5000/api/v1'
DB = dict(host='localhost', port=5432, dbname='intelligent_audio_test_test',
          user='intelligent_audio_test', password='intelligent_audio_test666')
DEVICE_ID = 147
API_ID = 314


def seed_online():
    """把测试设备/API 的 DB status 置 online（共享栈其它 run 健康检查会打回 offline）。"""
    conn = psycopg2.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE devices SET status='online', deleted=FALSE, deleted_at=NULL WHERE id=%s", (DEVICE_ID,))
        cur.execute("UPDATE apis SET status='online', deleted=FALSE, deleted_at=NULL WHERE id=%s", (API_ID,))
        conn.commit()
        print(f'seeded online: device={DEVICE_ID} api={API_ID}')
    finally:
        conn.close()


def wait_for(driver, fn, timeout=30):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
            last = v
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.4)
    raise RuntimeError(f'wait_for timeout; last={last!r}')


def shot(driver, name):
    driver.save_screenshot(os.path.join(OUT, name))
    print('saved', name)


def js_click(driver, selector, index=0):
    """用 JS 点击（绕过滚动/可见性问题）。"""
    driver.execute_script(
        f"const els = document.querySelectorAll({json.dumps(selector)});"
        f"if (els.length > {index}) {{ els[{index}].click(); return true; }} return false;"
    )


def find_card_btn(driver, name_sub):
    """在 ResourceSelectionGrid 卡片中按名称子串找复选框并勾选（触发 @change → toggle-selection）。
    只勾选未禁用（在线）的复选框，并确认勾选生效。"""
    def _click():
        return driver.execute_script(
            "const cards = [...document.querySelectorAll('.resource-card')];"
            "const hits = cards.filter(c => {"
            "  const nm = c.querySelector('.card-name');"
            "  return nm && nm.textContent.includes(arguments[0]);"
            "});"
            "const hit = hits.find(c => {"
            "  const cb = c.querySelector('.resource-checkbox');"
            "  return cb && !cb.disabled;"
            "}) || hits[0];"
            "if (!hit) return false;"
            "const cb = hit.querySelector('.resource-checkbox');"
            "if (cb && !cb.checked && !cb.disabled) { cb.click(); return 'clicked'; }"
            "if (cb && cb.checked) return 'already';"
            "return 'found-but-disabled';",
            name_sub,
        )
    return wait_for(driver, lambda: _click() not in (False, 'found-but-disabled'))


def fetch_json(path):
    with urllib.request.urlopen(GATEWAY + path, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    caps = {'goog:loggingPrefs': {'performance': 'ALL', 'browser': 'ALL'}}
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', caps['goog:loggingPrefs'])
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1440, 900)
    d.execute_cdp_cmd('Network.enable', {})

    task_name = '接线测试_INT1072_execmode_serial_api_first'
    created_id = None
    try:
        seed_online()
        d.get(BASE + '/#/E2ETest')
        # ---- 步骤0：选择算法 ----
        wait_for(d, lambda: d.execute_script(
            "return !!document.querySelector('#test-step0.active') && "
            "document.querySelectorAll('.algorithm-card').length > 0;"
        ))
        print('step0 loaded')
        js_click(d, '#algo-voice_llm')
        time.sleep(0.5)
        js_click(d, '#test-step0 .step-actions .btn-primary')
        # ---- 步骤1：勾选用例分组 ----
        wait_for(d, lambda: d.execute_script(
            "return !!document.querySelector('#test-step1.active') && "
            "document.querySelectorAll('.group-checkbox').length > 0;"
        ))
        print('step1 loaded')
        js_click(d, '.group-checkbox', 0)
        time.sleep(0.4)
        js_click(d, '#test-step1 .step-actions .btn-primary')
        # ---- 步骤2：资源混选 + 执行参数 ----
        wait_for(d, lambda: d.execute_script(
            "return !!document.querySelector('#test-step2.active') && "
            "document.querySelectorAll('.resource-section').length >= 2;"
        ))
        time.sleep(1.5)
        print('step2 loaded; sections:', d.execute_script(
            "return [...document.querySelectorAll('.resource-section-header h4')].map(e=>e.textContent);"))
        shot(d, 'step2_notmixed_disabled.png')
        # 执行模式控件初始应置灰
        dis = d.execute_script(
            "const r = document.querySelectorAll('.execution-params-panel input[type=radio]');"
            "return [...r].every(x => x.disabled);")
        print('execution-mode radios all disabled (not mixed):', dis)

        # ---- 混选：设备 + API ----
        print('select device:', find_card_btn(d, 'INT1072_online_device'))
        time.sleep(0.5)
        print('select api:', find_card_btn(d, 'INT1072_api'))
        # 等混选成立（两张在线卡选中）
        wait_for(d, lambda: d.execute_script(
            "return document.querySelectorAll('#test-step2 .resource-card.selected').length >= 2;"
        ))
        time.sleep(0.5)
        mixed = d.execute_script(
            "return document.querySelectorAll('#test-step2 .resource-card.selected').length;")
        print('selected cards:', mixed)
        shot(d, 'step2_mixed_default_parallel.png')

        # 切串行
        js_click(d, '.execution-params-panel input[type=radio][value="serial"]')
        time.sleep(0.4)
        shot(d, 'step2_mixed_serial_device_first.png')
        # 切 API 先
        js_click(d, '.execution-params-panel input[type=radio][value="api"]')
        time.sleep(0.4)
        shot(d, 'step2_mixed_serial_api_first.png')

        # 深色（旧 Vue 未启用 .dark，试强制）
        d.execute_script("document.documentElement.classList.add('dark')")
        time.sleep(0.6)
        shot(d, 'step2_mixed_serial_api_first_dark.png')
        d.execute_script("document.documentElement.classList.remove('dark')")
        time.sleep(0.3)

        # ---- 阻断 start，提交创建（保留 create 证据） ----
        # 提交前确认执行模式单选状态
        checked = d.execute_script(
            "const r = [...document.querySelectorAll('.execution-params-panel input[type=radio]')];"
            "return r.filter(x => x.checked).map(x => x.value);")
        print('checked radios before submit:', checked)
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1/tasks/*/start*']})
        js_click(d, '#test-step2 .step-actions .btn-primary')  # 开始任务 → 弹任务名模态窗
        wait_for(d, lambda: d.execute_script("return !!document.querySelector('#task-name-input');"))
        d.execute_script(
            "const inp = document.querySelector('#task-name-input');"
            "inp.value = arguments[0];"
            "inp.dispatchEvent(new Event('input', { bubbles: true }));", task_name)
        time.sleep(0.3)
        js_click(d, '.modal-footer .btn-primary')  # 确认 → create + start(被阻断)
        # 等待 create 落库
        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(1.5)
            try:
                res = fetch_json('/tasks?search=' + urllib.parse.quote(task_name) + '&per_page=5')
                items = res.get('data', {}).get('items', [])
                if items:
                    created_id = items[0]['id']
                    break
            except Exception as e:  # noqa: BLE001
                print('poll err', e)
        print('created task id:', created_id)

        # 截图（start 被阻断后的状态）
        time.sleep(1)
        shot(d, 'step2_after_create_start_blocked.png')

        # ---- Network 证据（尽力抓 POST /tasks postData；失败则以后端落库为准） ----
        body = None
        try:
            for entry in d.get_log('performance'):
                txt = entry.get('message', '')
                if 'requestWillBeSent' not in txt:
                    continue
                try:
                    evt = json.loads(txt)['message']['params']
                    if evt.get('type') == 'XHR' and '/api/v1/tasks' in evt.get('request', {}).get('url', '') \
                            and evt.get('request', {}).get('method') == 'POST':
                        post = evt.get('request', {}).get('postData')
                        if post:
                            body = post
                            break
                except Exception:  # noqa: BLE001
                    continue
        except Exception as e:  # noqa: BLE001
            print('perf log unavailable (用后端落库证据):', type(e).__name__)
        print('POST /tasks postData:', body)
        if body:
            with open(os.path.join(OUT, 'create_request_postdata.json'), 'w', encoding='utf-8') as f:
                f.write(body)

        # ---- 后端核对（创建请求落库证据：关联设备/API + config.execution_mode/serial_first） ----
        if created_id:
            detail = fetch_json(f'/tasks/{created_id}')
            data = detail.get('data', detail)
            print('TASK detail keys:', {k: data.get(k) for k in
                  ('id', 'name', 'devices', 'apis', 'config', 'device_types') if k in data})
            # config 落库（execution_mode / serial_first）
            cfg = data.get('config') or {}
            print('config:', cfg)
            with open(os.path.join(OUT, 'task_detail.json'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    finally:
        if created_id:
            try:
                req = urllib.request.Request(GATEWAY + f'/tasks/{created_id}', method='DELETE')
                urllib.request.urlopen(req, timeout=15)
                print('deleted task', created_id)
            except Exception as e:  # noqa: BLE001
                print('delete err', e)
        d.quit()


if __name__ == '__main__':
    main()
