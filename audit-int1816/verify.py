"""INT-1816 实测：评估维度新建默认输出字段/默认规则档位/健康测试无端点态（临时脚本，不提交）。

- 浅色 + 深色两轮截图
- 真实 POST /api/v1/evaluation/dimensions 载荷取证（output_fields 应空、rule 6 档）
- 真实 DELETE 清理自建维度
- 真实维度 121（无端点）健康探测：弹窗应显示空态文案而非「总状态 在线」
"""
import json
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5388'
API = 'http://localhost:15000/api/v1'
DIM_NAME = 'INT1816_自测_默认值'

CAPTURE_JS = """
window.__caps = [];
const __origFetch = window.fetch;
window.fetch = async (...args) => {
  let rec = null;
  try {
    const input = args[0];
    const init = args[1] || {};
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    if (method !== 'GET') {
      rec = { url: String(url), method, body: typeof init.body === 'string' ? init.body : null };
      window.__caps.push(rec);
    }
  } catch (e) {}
  const resp = await __origFetch.apply(window, args);
  try {
    if (rec) {
      const clone = resp.clone();
      clone.text().then((t) => { rec.response = t.slice(0, 4000); rec.status = resp.status; }).catch(() => {});
    }
  } catch (e) {}
  return resp;
};
"""


def js(drv, script, *args):
    return drv.execute_script(script, *args)


def wait_body(drv, text, timeout=60):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.find_element(By.TAG_NAME, 'body').text
    )


def click_js(drv, el):
    drv.execute_script('arguments[0].click()', el)


def by_text(drv, tag, text):
    return drv.find_element(
        By.XPATH, f"//{tag}[contains(normalize-space(.), '{text}')]"
    )


def open_drawer(drv):
    click_js(drv, by_text(drv, 'button', '新增维度'))
    wait_body(drv, '新增评估维度')
    time.sleep(0.8)


def open_tab(drv, label):
    tabs = drv.find_elements(By.XPATH, f"//button[@role='tab' and contains(normalize-space(.), '{label}')]")
    assert tabs, f'tab not found: {label}'
    click_js(drv, tabs[0])
    time.sleep(0.8)


def rule_rows(drv):
    rows = []
    i = 1
    while True:
        el = drv.find_elements(By.CSS_SELECTOR, f"input[aria-label='规则 {i} 阈值']")
        if not el:
            break
        threshold = el[0].get_attribute('value')
        score = drv.find_element(
            By.CSS_SELECTOR, f"input[aria-label='规则 {i} 得分']"
        ).get_attribute('value')
        # 行容器文本（含条件 Select 的当前值，如 >= / <）
        row_text = drv.execute_script(
            """const el=document.querySelector("input[aria-label='规则 %d 阈值']");
               let p=el; for(let k=0;k<5 && p;k++){p=p.parentElement; if(p && p.innerText && p.innerText.split('\\n').length<=4) break;}
               return p ? p.innerText.replace(/\\n/g,' | ') : '';""" % i
        )
        rows.append({'index': i, 'threshold': threshold, 'score': score, 'row_text': row_text})
        i += 1
    return rows


def api_section_snapshot(drv):
    def count(prefix):
        return len(
            drv.find_elements(
                By.CSS_SELECTOR, f"input[aria-label^='{prefix}']"
            )
        )

    endpoint_urls = [
        el.get_attribute('value')
        for el in drv.find_elements(By.CSS_SELECTOR, "input[aria-label^='端点 URL']")
    ]
    return {
        'required_input_rows': count('输入参数键名'),
        'required_input_keys': [
            el.get_attribute('value')
            for el in drv.find_elements(By.CSS_SELECTOR, "input[aria-label^='输入参数键名']")
        ],
        'output_field_rows': count('输出字段代码'),
        'endpoint_url_values': endpoint_urls,
        'body_tail': drv.find_elements(By.TAG_NAME, 'body')[0].text[-900:],
    }


def fill_name_and_save(drv, name):
    name_input = drv.find_element(By.ID, 'dim-name')
    name_input.clear()
    name_input.send_keys(name)
    time.sleep(0.4)
    save_btn = drv.find_element(
        By.XPATH, "//button[@type='submit' and (contains(normalize-space(.), '保存'))]"
    )
    WebDriverWait(drv, 20).until(lambda d: save_btn.is_enabled())
    click_js(drv, save_btn)


def wait_capture(drv, url_part, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        caps = js(drv, 'return window.__caps || []')
        hits = [c for c in caps if url_part in c['url'] and c.get('response')]
        if hits:
            return hits[-1]
        time.sleep(0.5)
    return None


def open_health(drv, dim_name):
    btn = drv.find_element(
        By.XPATH, f"//button[@aria-label='测试维度 {dim_name} 的 API']"
    )
    click_js(drv, btn)
    wait_body(drv, 'API健康测试结果', timeout=60)
    time.sleep(1.2)


def dialog_snapshot(drv):
    dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
    text = dlg[-1].text if dlg else drv.find_element(By.TAG_NAME, 'body').text
    return {
        'dialog_text': text,
        'has_total_status': '总状态' in text,
        'has_online': '在线' in text,
        'has_no_endpoint_empty': '该维度未配置 API 端点' in text,
    }


def main():
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1100')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    drv = webdriver.Chrome(options=opts)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': CAPTURE_JS})
    drv.set_window_size(1600, 1100)
    out = {'evidence': {}, 'errors': []}
    try:
        # ---------- 浅色：页面 ----------
        drv.get(f'{BASE}/Evaluation')
        wait_body(drv, '新增维度')
        time.sleep(1.5)
        out['url'] = drv.current_url
        drv.save_screenshot('audit-int1816/01-evaluation-light.png')

        # ---------- P3-2 / P3-1：新增抽屉 ----------
        open_drawer(drv)
        open_tab(drv, '结果配置')
        out['evidence']['rule_rows_new_dimension'] = rule_rows(drv)
        drv.save_screenshot('audit-int1816/02-new-result-tab-light.png')

        open_tab(drv, 'API配置')
        out['evidence']['api_section'] = api_section_snapshot(drv)
        api_pane = drv.find_element(By.CSS_SELECTOR, "[role='tabpanel']")
        api_pane.screenshot('audit-int1816/03-new-api-tab-light.png')
        out['evidence']['drawer_text_api_tab'] = drv.find_elements(By.TAG_NAME, 'body')[0].text[-600:]

        # ---------- P3-1：真实保存载荷 ----------
        open_tab(drv, '基本信息')
        fill_name_and_save(drv, DIM_NAME + '_' + time.strftime('%H%M%S'))
        WebDriverWait(drv, 40).until(
            lambda d: '新增评估维度' not in d.find_element(By.TAG_NAME, 'body').text
        )
        cap = wait_capture(drv, '/evaluation/dimensions')
        if cap:
            body = json.loads(cap['body'] or '{}')
            resp = json.loads(cap.get('response') or '{}')
            out['evidence']['post_payload'] = {
                'status': cap.get('status'),
                'output_fields': body.get('outputFields', body.get('output_fields')),
                'rule': body.get('rule'),
                'api_endpoints': body.get('apiEndpoints', body.get('api_endpoints')),
                'required_input_codes': [
                    ri.get('paramCode') or ri.get('param_code')
                    for ri in (body.get('requiredInputs') or body.get('required_inputs') or [])
                ],
            }
            created = (resp.get('data') or {}) if isinstance(resp, dict) else {}
            out['evidence']['created_dimension'] = {
                'id': created.get('id'),
                'name': created.get('name'),
                'output_fields': created.get('outputFields', created.get('output_fields')),
            }
            new_id = created.get('id')
            if new_id:
                req = urllib.request.Request(
                    f'{API}/evaluation/dimensions/{new_id}', method='DELETE'
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    out['evidence']['cleanup_delete'] = {
                        'id': new_id, 'status': r.status,
                        'body': r.read().decode('utf-8')[:300],
                    }
        else:
            out['errors'].append('未捕获到 POST /evaluation/dimensions 载荷')

        # 抽屉可能已关闭；确认
        time.sleep(1.0)
        drv.save_screenshot('audit-int1816/04-after-save-light.png')

        # ---------- P3-3：健康测试（维度 121 无端点） ----------
        drv.get(f'{BASE}/Evaluation')
        wait_body(drv, '新增维度')
        time.sleep(1.5)
        open_health(drv, '拒识成功数量')
        out['evidence']['health_empty_state_light'] = dialog_snapshot(drv)
        drv.save_screenshot('audit-int1816/05-health-empty-light.png')
        # 关闭
        for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='关闭']"):
            click_js(drv, b)
            break
        time.sleep(0.8)

        # ---------- 深色 ----------
        drv.get(f'{BASE}/Evaluation')
        wait_body(drv, '新增维度')
        js(drv, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        drv.refresh()
        wait_body(drv, '新增维度')
        time.sleep(2.0)
        out['evidence']['dark_theme'] = js(
            drv,
            "return {cls: document.documentElement.className, bg: getComputedStyle(document.body).backgroundColor}",
        )
        open_drawer(drv)
        open_tab(drv, 'API配置')
        out['evidence']['dark_api_section'] = api_section_snapshot(drv)['output_field_rows']
        drv.save_screenshot('audit-int1816/06-new-api-tab-dark.png')
        open_tab(drv, '结果配置')
        out['evidence']['rule_rows_dark'] = rule_rows(drv)
        drv.save_screenshot('audit-int1816/07-new-result-tab-dark.png')
        # 取消关闭
        for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消']"):
            click_js(drv, b)
            break
        time.sleep(1.0)

        open_health(drv, '拒识成功数量')
        out['evidence']['health_empty_state_dark'] = dialog_snapshot(drv)
        drv.save_screenshot('audit-int1816/08-health-empty-dark.png')

        # 构建指纹
        out['evidence']['bundle'] = js(
            drv,
            "return Array.from(document.querySelectorAll('script[src]')).map(s=>s.src).filter(s=>s.includes('index.')||s.includes('static/js'))",
        )
    except Exception as exc:  # noqa: BLE001
        out['errors'].append(f'{type(exc).__name__}: {exc}')
        try:
            drv.save_screenshot('audit-int1816/99-failure.png')
        except Exception:
            pass
    finally:
        drv.quit()
    with open('audit-int1816/evidence.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
