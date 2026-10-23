# -*- coding: utf-8 -*-
"""INT-1543 首页「平台规模条」验收：6 项整项可点击 + 副行细分 + API 告警角标。

环境：本 worktree dev server（默认 http://localhost:5311，代理 docker 后端 15000，
真实库 intelligent_audio_test）；a11y/RBAC 用 /auth/me 拦包模拟 home:read + task:read 受限账号。

产出（tests/ui/artifacts/int1543/）：
- light.png / dark.png：规模条浅/深色截图；
- network.json：/home/stats/details 响应状态与首屏请求；
- report.json：逐项 href、副行文案、hover 位移、告警色、受限账号链接数、点击落点。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
ART = 'tests/ui/artifacts/int1543'
os.makedirs(ART, exist_ok=True)

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


def log(m):
    print(m, flush=True)


def make_driver(with_perf=False):
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1200')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    if with_perf:
        o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    return webdriver.Chrome(options=o)


def wait_stats(drv):
    WebDriverWait(drv, 90).until(
        lambda d: d.find_elements(By.XPATH, "//dt[contains(., '测试用例')]")
    )
    # 等数字滚动落定（滚动动画 0.6s + 位数动画 0.5s）
    time.sleep(1.5)


def network_entries(drv):
    rows = []
    for entry in drv.get_log('performance'):
        msg = json.loads(entry['message'])['message']
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg['params']['response']
        url = resp.get('url', '')
        if '/api/v1/' in url:
            rows.append({'url': url, 'status': resp.get('status')})
    return rows


def stats_section(drv):
    return drv.find_element(
        By.XPATH, "//span[normalize-space(.)='平台规模']/parent::div"
    )


STATS_DL = "//span[normalize-space(.)='平台规模']/following-sibling::dl"


def main():
    report = {}
    drv = make_driver(with_perf=True)
    try:
        drv.get(BASE + '/')
        wait_stats(drv)
        time.sleep(1.5)

        links = drv.find_elements(By.XPATH, STATS_DL + "//a")
        report['link_count'] = len(links)
        report['links'] = [
            {'text': a.get_attribute('aria-label'), 'href': a.get_attribute('href')}
            for a in links
        ]
        report['item_count'] = len(drv.find_elements(By.XPATH, STATS_DL + "//div"))
        report['sub_lines'] = [
            el.text for el in drv.find_elements(By.XPATH, STATS_DL + "//dt")
        ]

        # API 项告警角标与 Alert 色
        api_dt = drv.find_element(
            By.XPATH, STATS_DL + "//dt[contains(., 'API 服务')]"
        )
        report['api_alert_badge'] = (
            '故障告警' if '故障告警' in (
                api_dt.find_element(By.XPATH, './preceding-sibling::dd').text
            ) else None
        )
        report['api_color'] = drv.execute_script(
            'return getComputedStyle(arguments[0]).color', api_dt
        )
        case_dt = drv.find_element(
            By.XPATH, STATS_DL + "//dt[contains(., '测试用例')]"
        )
        report['normal_color'] = drv.execute_script(
            'return getComputedStyle(arguments[0]).color', case_dt
        )

        # hover 上移 4px + 阴影
        item = drv.find_element(
            By.XPATH, STATS_DL + "//dt[contains(., '测试用例')]/parent::div"
        )
        report['hover_before'] = drv.execute_script(
            'const s = getComputedStyle(arguments[0]);'
            'return {translate: s.translate, transform: s.transform, shadow: s.boxShadow}',
            item,
        )
        ActionChains(drv).move_to_element(item).perform()
        time.sleep(0.5)
        report['hover_after'] = drv.execute_script(
            'const s = getComputedStyle(arguments[0]);'
            'return {translate: s.translate, transform: s.transform, shadow: s.boxShadow}',
            item,
        )

        section = stats_section(drv)
        drv.execute_script(
            'arguments[0].scrollIntoView({block: "center"});', section
        )
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ART, 'light.png'))

        # 点击落点（整项覆盖 Link）：六项逐项点击并记录最终 URL
        expected = {
            '测试用例': '/testcases',
            '测试任务': '/tasks',
            '评估维度': '/Evaluation',
            '音频文件': '/audio-import',
            '在线设备': '/devices',
            'API 服务': '/start-test',  # /APITest 路由守卫按设计重定向至合并入口
        }
        clicks = {}
        for label, prefix in expected.items():
            link_el = drv.find_element(
                By.XPATH, STATS_DL + f"//a[@aria-label='{label}']"
            )
            drv.execute_script('arguments[0].click()', link_el)
            WebDriverWait(drv, 20).until(
                lambda d: prefix in d.current_url
            )
            clicks[label] = drv.current_url
            drv.get(BASE + '/')
            wait_stats(drv)
        report['click_urls'] = clicks
        report['click_url'] = clicks['测试用例']

        report['network'] = [
            r for r in network_entries(drv)
            if '/home/stats/details' in r['url']
        ]

        # 深色
        drv.execute_script(
            "localStorage.setItem('iatp:theme:v1:mode', 'dark')"
        )
        drv.get('about:blank')
        drv.get(BASE + '/')
        wait_stats(drv)
        time.sleep(1.5)
        section = stats_section(drv)
        drv.execute_script(
            'arguments[0].scrollIntoView({block: "center"});', section
        )
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ART, 'dark.png'))
        drv.execute_script(
            "localStorage.setItem('iatp:theme:v1:mode', 'light')"
        )
    finally:
        drv.quit()

    # 受限账号：只有 home:read + task:read → 六项仍展示，仅任务项渲染链接
    drv2 = make_driver()
    try:
        drv2.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument', {'source': RESTRICTED_ME}
        )
        drv2.get(BASE + '/')
        wait_stats(drv2)
        time.sleep(1.5)
        report['restricted_link_count'] = len(
            drv2.find_elements(By.XPATH, STATS_DL + "//a")
        )
        report['restricted_links'] = [
            a.get_attribute('aria-label')
            for a in drv2.find_elements(By.XPATH, STATS_DL + "//a")
        ]
        report['restricted_item_count'] = len(
            drv2.find_elements(By.XPATH, STATS_DL + "//div")
        )
        drv2.execute_script(
            "arguments[0].scrollIntoView({block:'center'})",
            stats_section(drv2),
        )
        time.sleep(0.8)
        drv2.save_screenshot(os.path.join(ART, 'restricted.png'))
    finally:
        drv2.quit()

    with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
