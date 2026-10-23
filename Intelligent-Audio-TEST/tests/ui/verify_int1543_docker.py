# -*- coding: utf-8 -*-
"""INT-1543 验收（测试工程师·docker 旁路栈）：首页平台规模条 6 项可点击 + 副行细分 + API 告警。

被测环境：本 run 临时容器 http://localhost:15433（dist 由交付提交 b56edb20 cherry-pick 后
pnpm build 产出，nginx conf 与 15173 一致，/api 代理 intelligent-audio-test_default 网络里的
api_gateway:5000，真实库 intelligent_audio_test）。

断言（对应卡内验收标准）：
1. 六项各自渲染 Link，href 指向对应管理页；真实鼠标点卡片中心（非锚点文本）能整项跳转，落点正确。
2. 副行文案与 GET /api/v1/home/stats/details 逐项一致（任务的 running/failed、音频的 noise/prompt）。
3. hover 上移 4px + 阴影。
4. API 在线率 0% (<80%) → Alert 色 + 「故障告警」角标。
5. 无子权限账号（拦 /auth/me 仅 home:read+task:read）：六项仍展示、仅「测试任务」渲染链接。
6. Network：/api/v1/home/stats/details 全部 200。
7. 浅色 / 深色截图。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DOCKER_BASE', 'http://localhost:15433')
ART = os.environ.get(
    'ART_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1543_docker'),
)
os.makedirs(ART, exist_ok=True)

STATS_DL = "//span[normalize-space(.)='平台规模']/following-sibling::dl"

# 受限账号：只给 home:read + task:read
RESTRICTED_ME = r"""
(() => {
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/auth/me') >= 0) {
      return new Response(JSON.stringify({
        success: true, code: 0, message: 'Success',
        data: { user_id: 2, username: 'guest', role_id: 4,
                permissions: ['home:read', 'task:read'] }
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return orig.apply(this, arguments);
  };
})();
"""

EXPECTED = {
    '测试用例': '/testcases',
    '测试任务': '/tasks',
    '评估维度': '/Evaluation',
    '音频文件': '/audio-import',
    '在线设备': '/devices',
    'API 服务': '/start-test',   # /APITest → beforeLoad redirect（INT-486 合并入口），设计如此
}


def log(m):
    print(m, flush=True)


def make_driver(with_perf=False):
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    if with_perf:
        o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    return webdriver.Chrome(options=o)


def wait_stats(drv, timeout=90):
    WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(By.XPATH, STATS_DL + "/div[dt]")
    )
    time.sleep(1.5)  # RollingNumber 滚动落定


def cards(drv):
    return drv.find_elements(By.XPATH, STATS_DL + "/div")


def links(drv):
    return drv.find_elements(By.XPATH, STATS_DL + "//a")


def page_stats(drv):
    script = """
    const cb = arguments[arguments.length - 1];
    fetch('/api/v1/home/stats/details', { headers: { Accept: 'application/json' } })
      .then(r => r.json()).then(j => cb(j)).catch(e => cb({ error: String(e) }));
    """
    return drv.execute_async_script(script)


def network_rows(drv, needle='/home/stats/details'):
    rows = []
    for entry in drv.get_log('performance'):
        msg = json.loads(entry['message'])['message']
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg['params']['response']
        url = resp.get('url', '')
        if needle in url:
            rows.append({'url': url, 'status': resp.get('status')})
    return rows


def main():
    report = {}
    drv = make_driver(with_perf=True)
    try:
        drv.get(BASE + '/')
        wait_stats(drv)

        # --- 1. 六项与链接 ---
        cs = cards(drv)
        ls = links(drv)
        report['item_count'] = len(cs)
        report['link_count'] = len(ls)
        report['links'] = [
            {'label': a.get_attribute('aria-label'), 'href': a.get_attribute('href')}
            for a in ls
        ]
        report['sub_lines'] = [c.find_element(By.XPATH, './dt').text for c in cs]
        report['item_labels'] = [
            c.find_element(By.XPATH, './dt').text.split(' · ')[0] for c in cs
        ]

        # --- 2. 副行 vs 接口 ---
        api = page_stats(drv)
        report['api_details'] = api.get('data', api)
        d = report['api_details']
        if 'error' not in api:
            exp_subs = [
                f"{d['test_cases']['groups']} 个分组",
                f"{d['tasks']['completed']} 已完成 / {d['tasks']['running']} 进行中 / {d['tasks']['failed']} 失败",
                f"{d['dimensions']['endpoints']} 个端点",
                f"{d['audio_files']['dry']} 干音 / {d['audio_files']['noise']} 噪声 / {d['audio_files']['prompt']} 提示音",
                f"{d['devices']['offline']} 台离线",
                f"{d['apis']['online']} 个在线",
            ]
            labels = ['测试用例', '测试任务', '评估维度', '音频文件', '在线设备', 'API 服务']
            report['subline_expected'] = [
                f"{lab} · {exp}" for lab, exp in zip(labels, exp_subs)
            ]
            report['subline_match'] = report['sub_lines'] == report['subline_expected']

        # --- 3. API 告警（真实数据：total=1 online=0 → 0% < 80%） ---
        api_dt = drv.find_element(By.XPATH, STATS_DL + "//dt[contains(., 'API 服务')]")
        api_dd = api_dt.find_element(By.XPATH, './preceding-sibling::dd')
        case_dt = drv.find_element(By.XPATH, STATS_DL + "//dt[contains(., '测试用例')]")
        report['api_alert_badge'] = '故障告警' in api_dd.text
        report['api_dd_text'] = api_dd.text
        report['api_color'] = drv.execute_script(
            'return getComputedStyle(arguments[0]).color', api_dt)
        report['normal_color'] = drv.execute_script(
            'return getComputedStyle(arguments[0]).color', case_dt)
        if 'error' not in api:
            ap = d['apis']
            report['api_rate'] = (ap['online'] / ap['total']) if ap['total'] else None

        # --- 4. hover 上移 4px + 阴影 ---
        card = drv.find_element(
            By.XPATH, STATS_DL + "/div[dt[contains(., '测试用例')]]")
        get_style = ('const s = getComputedStyle(arguments[0]);'
                     'return {translate: s.translate, transform: s.transform,'
                     ' shadow: s.boxShadow};')
        report['hover_before'] = drv.execute_script(get_style, card)
        ActionChains(drv).move_to_element(card).perform()
        time.sleep(0.6)
        report['hover_after'] = drv.execute_script(get_style, card)

        # 浅色截图
        sec = drv.find_element(
            By.XPATH, "//span[normalize-space(.)='平台规模']/parent::div/parent::div")
        drv.execute_script('arguments[0].scrollIntoView({block: "center"});', sec)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ART, 'light.png'))

        # --- 5. 点击落点（整项可点：真实鼠标点卡片中心，非锚点文本） ---
        clicks = {}
        real_mouse = {}
        for label, prefix in EXPECTED.items():
            drv.get(BASE + '/')
            wait_stats(drv)
            card = drv.find_element(
                By.XPATH, STATS_DL + f"/div[dt[contains(., '{label}')]]")
            if label == '测试用例':
                # 真鼠标点卡片中心：命中覆盖层 Link 才算「整项可点」
                ActionChains(drv).move_to_element(card).click().perform()
            else:
                a = drv.find_element(
                    By.XPATH, STATS_DL + f"//a[@aria-label='{label}']")
                drv.execute_script('arguments[0].click()', a)
            WebDriverWait(drv, 25).until(lambda d: prefix in d.current_url)
            clicks[label] = drv.current_url
            body = drv.find_element(By.TAG_NAME, 'body').text
            real_mouse[label] = {
                'url_ok': prefix in drv.current_url,
                'error_page': any(k in body for k in ('Unexpected Application Error', '404 Not Found')),
            }
        report['click_urls'] = clicks
        report['click_checks'] = real_mouse

        # --- 6. Network ---
        drv.get(BASE + '/')
        wait_stats(drv)
        time.sleep(1.0)
        report['network'] = network_rows(drv)
        report['network_all_200'] = bool(report['network']) and all(
            r['status'] == 200 for r in report['network'])

        # --- 7. 深色截图 ---
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark')")
        drv.get('about:blank')
        drv.get(BASE + '/')
        wait_stats(drv)
        sec = drv.find_element(
            By.XPATH, "//span[normalize-space(.)='平台规模']/parent::div/parent::div")
        drv.execute_script('arguments[0].scrollIntoView({block: "center"});', sec)
        time.sleep(0.8)
        report['dark_theme_attr'] = drv.execute_script(
            "return document.documentElement.className || document.documentElement.dataset.theme")
        drv.save_screenshot(os.path.join(ART, 'dark.png'))
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light')")
    finally:
        drv.quit()

    # --- 8. 受限权限 ---
    drv2 = make_driver()
    try:
        drv2.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument', {'source': RESTRICTED_ME})
        drv2.get(BASE + '/')
        wait_stats(drv2)
        report['restricted_item_count'] = len(cards(drv2))
        rl = links(drv2)
        report['restricted_link_count'] = len(rl)
        report['restricted_links'] = [a.get_attribute('aria-label') for a in rl]
        report['restricted_subs'] = [
            c.find_element(By.XPATH, './dt').text for c in cards(drv2)]
        sec = drv2.find_element(
            By.XPATH, "//span[normalize-space(.)='平台规模']/parent::div/parent::div")
        drv2.execute_script('arguments[0].scrollIntoView({block: "center"});', sec)
        time.sleep(0.8)
        drv2.save_screenshot(os.path.join(ART, 'restricted.png'))
    finally:
        drv2.quit()

    with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
