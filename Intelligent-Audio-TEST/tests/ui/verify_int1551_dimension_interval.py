# -*- coding: utf-8 -*-
"""INT-1551 评估维度抽屉「结果配置」min≥max 行内提示 + 保存按钮死路 浏览器实测。

缺陷（INT-1484 走查发现）：结果最小值 ≥ 结果最大值时，页面无任何错误文案，
保存按钮直接 disabled（RHF 默认 onSubmit 模式 → formState.errors 不产出 → 无原因禁用）。

本脚本核对（后端 = docker 网关 15000，前端 = 本 run dev server）：
  ① 新建维度抽屉 → 基本信息填名称 → 切「结果配置」
  ② 把结果最小值改到 ≥ 结果最大值（改 min）→ 结果最大值下方出现行内错误
     「结果最大值必须大于最小值」+ 页脚摘要「请先修正：结果配置：…」+ 保存按钮 disabled
  ③ 反方向（改 max 让 max<min）→ 同样出现行内错误（deps 双向）
  ④ 修回合法区间 → 行内错误消失、页脚摘要消失、保存按钮恢复可用
  ⑤ 保存 → POST /api/v1/evaluation/dimensions 真实落库（Network 证据）→ 列表出现
  ⑥ 清理：DELETE 本 run 自建维度
  ⑦ 浅色 / 深色截图

用法：python verify_int1551_dimension_interval.py --base http://localhost:5355
输出：tests/ui/artifacts/int1551/
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
from selenium.webdriver.common.keys import Keys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1551')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ERR_TEXT = '结果最大值必须大于最小值'
TEST_NAME = '接线测试_INT1551_区间校验_%d' % int(time.time())


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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


def collect_requests(drv):
    """performance log（双层嵌套）→ [{method,url,status,postData}]"""
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': req.get('url') or '',
                    'status': None,
                    'postData': req.get('postData') or '',
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return list(reqs.values())


def wait_for(cond, timeout=30, desc='condition', interval=0.3):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(interval)
    raise AssertionError('timeout waiting for %s (last error: %r)' % (desc, last))


def shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    return path


def set_number(drv, el, value):
    """受控 number 输入：clear() 不触发 React onChange（INT-1484 经验），用 Ctrl+A+Delete 再输入。"""
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(str(value))
    time.sleep(0.4)


def has_error(drv):
    return bool(
        drv.find_elements(
            By.XPATH,
            "//p[contains(@class,'text-destructive')][contains(normalize-space(.),'%s')]" % ERR_TEXT,
        )
    )


def summary_text(drv):
    els = drv.find_elements(By.XPATH, "//p[@data-testid='dimension-form-validation-summary']")
    return els[0].text.strip() if els else ''


def save_button(drv):
    return drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.toggle('dark', arguments[0]==='dark');",
        mode,
    )
    time.sleep(0.8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5355')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)
    report = {'base': base, 'steps': [], 'requests': []}

    drv = _driver()
    created_id = None
    try:
        drv.get(base + '/Evaluation')
        wait_for(
            lambda: drv.find_elements(By.XPATH, "//*[contains(normalize-space(.),'评估维度')]"),
            desc='评估维度页渲染',
        )
        time.sleep(1.5)
        _ = collect_requests(drv)  # drain 基线
        report['steps'].append('① /Evaluation 打开成功')

        # 打开「新增维度」抽屉（表头按钮；空态按钮同文案，取第一个可点）
        btns = drv.find_elements(
            By.XPATH, "//button[contains(normalize-space(.),'新增维度')]"
        )
        assert btns, '未找到「新增维度」按钮'
        drv.execute_script('arguments[0].click()', btns[0])
        wait_for(
            lambda: drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']"),
            desc='维度抽屉打开',
        )
        wait_for(
            lambda: drv.find_elements(By.ID, 'dim-name'),
            desc='基本信息字段渲染',
        )
        # ① 填名称（让「修回合法后保存可用」可被验证）
        name_el = drv.find_element(By.ID, 'dim-name')
        name_el.click()
        name_el.send_keys(TEST_NAME)
        report['steps'].append('① 抽屉打开 + 名称填入 %s' % TEST_NAME)

        # ② 切到结果配置
        tab = drv.find_element(
            By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'结果配置')]"
        )
        drv.execute_script('arguments[0].click()', tab)
        wait_for(lambda: drv.find_elements(By.ID, 'dim-result-min'), desc='结果配置渲染')
        time.sleep(0.5)
        report['steps'].append('② 切到结果配置')

        # ③ 改 min ≥ max（默认 0 / 100 → min=100）
        min_el = drv.find_element(By.ID, 'dim-result-min')
        max_el = drv.find_element(By.ID, 'dim-result-max')
        report['before_min_max'] = (min_el.get_attribute('value'), max_el.get_attribute('value'))
        set_number(drv, min_el, 100)
        wait_for(lambda: has_error(drv), desc='行内错误出现（改 min）')
        inline = drv.find_element(
            By.XPATH,
            "//p[contains(@class,'text-destructive')][contains(normalize-space(.),'%s')]" % ERR_TEXT,
        ).text.strip()
        summary = summary_text(drv)
        disabled = save_button(drv).get_attribute('disabled') is not None
        assert inline == ERR_TEXT, '行内文案不符: %r' % inline
        assert ERR_TEXT in summary, '页脚摘要缺少错误: %r' % summary
        assert disabled, '非法区间下保存按钮应禁用'
        report['steps'].append('③ min≥max → 行内「%s」/ 摘要「%s」/ 保存禁用=%s' % (inline, summary, disabled))
        set_theme(drv, 'light')
        shot(drv, '01_min_ge_max_light.png')

        # ④ 反向：max 降到 min 之下（先修回 0/100，再改 max=50 且 min=60）
        set_number(drv, min_el, 60)
        set_number(drv, max_el, 50)
        wait_for(lambda: has_error(drv), desc='行内错误出现（改 max）')
        report['steps'].append('④ 改 max<min → 行内错误同样出现')
        set_theme(drv, 'dark')
        shot(drv, '02_min_ge_max_dark.png')

        # ⑤ 修回合法区间（0 / 100）→ 错误与摘要消失、保存可用
        set_theme(drv, 'light')
        set_number(drv, min_el, 0)
        set_number(drv, max_el, 100)
        wait_for(lambda: not has_error(drv), desc='行内错误消失')
        wait_for(lambda: not summary_text(drv), desc='页脚摘要消失')
        wait_for(
            lambda: save_button(drv).get_attribute('disabled') is None,
            desc='保存按钮恢复可用',
        )
        report['steps'].append('⑤ 修回 0/100 → 错误与摘要消失、保存按钮可用')
        shot(drv, '03_valid_state_light.png')

        # ⑥ 保存 → 真实 POST
        _ = collect_requests(drv)
        drv.execute_script('arguments[0].click()', save_button(drv))
        wait_for(
            lambda: not drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']"),
            desc='抽屉关闭（保存完成）',
            # 该栈维度写操作经 gRPC 慢（实测 20~60s），超时留足
            timeout=180,
        )
        time.sleep(1.5)
        reqs = collect_requests(drv)
        posts = [
            r
            for r in reqs
            if '/evaluation/dimensions' in r['url'] and r['method'] == 'POST'
        ]
        assert posts, '未捕获 POST /evaluation/dimensions'
        post = posts[-1]
        body = json.loads(post['postData'] or '{}')
        assert body.get('result_min') == 0 and body.get('result_max') == 100, '载荷区间不符: %r' % body
        assert body.get('name') == TEST_NAME, '载荷名称不符: %r' % body.get('name')
        report['requests'].append(post)
        report['steps'].append(
            '⑥ POST /api/v1/evaluation/dimensions status=%s result_min=%s result_max=%s'
            % (post['status'], body.get('result_min'), body.get('result_max'))
        )
        shot(drv, '04_after_save_list.png')

        # 列表回读 + 取 id 以便清理
        dims = _fetch_dimensions(base)
        hit = [d for d in dims if d.get('name') == TEST_NAME]
        assert hit, '列表未出现自建维度'
        created_id = hit[-1]['id']
        report['steps'].append('⑥ 列表回读命中 id=%s' % created_id)

        # ⑦ 清理自建维度
        code = _delete_dimension(base, created_id)
        report['steps'].append('⑦ 清理 DELETE /evaluation/dimensions/%s → %s' % (created_id, code))
        created_id = None

        report['ok'] = True
    except Exception as exc:  # noqa: BLE001
        report['ok'] = False
        report['error'] = repr(exc)
        try:
            shot(drv, '99_failure.png')
            report['visible_text'] = drv.find_element(By.TAG_NAME, 'body').text[:2000]
        except Exception:
            pass
        raise
    finally:
        if created_id:
            try:
                _delete_dimension(base, created_id)
            except Exception:
                pass
        report_path = os.path.join(ARTIFACTS, 'run.log')
        with open(report_path, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        drv.quit()


def _api(url, method='GET', payload=None):
    import urllib.request

    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('content-type', 'application/json')
    with urllib.request.urlopen(req, timeout=240) as resp:  # noqa: S310
        return resp.status, json.loads(resp.read().decode('utf-8') or '{}')


def _fetch_dimensions(base):
    _, body = _api(
        base + '/api/v1/evaluation/dimensions?page=1&per_page=200&search=INT1551'
    )
    return (body.get('data') or {}).get('items') or []


def _delete_dimension(base, dim_id):
    try:
        status, _ = _api(base + '/api/v1/evaluation/dimensions/%s' % dim_id, method='DELETE')
        return status
    except Exception as exc:  # noqa: BLE001
        return repr(exc)


if __name__ == '__main__':
    sys.exit(main())
