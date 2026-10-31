# -*- coding: utf-8 -*-
"""INT-2252 验收：评估维度页「关联算法」筛选 + 列（真实库栈 docker 15000 + 本卡构建容器）。

用法：python _int2252_ui.py <BASE_URL> <TAG>
  BASE_URL 如 http://localhost:15252（本卡构建）/ http://localhost:15173（基线旧构建）
结果 JSON 打到 stdout，截图落 tests/ui/artifacts/int2252/<TAG>_*.png。
"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2252')
os.makedirs(ART, exist_ok=True)


def shot(drv, tag, name):
    p = os.path.join(ART, '%s_%s.png' % (tag, name))
    drv.save_screenshot(p)
    return p


def login(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    if '/login' not in drv.current_url:
        return drv.current_url
    u = WebDriverWait(drv, 20).until(lambda d: d.find_element(By.ID, 'username'))
    u.clear()
    u.send_keys('dev_user')
    p = drv.find_element(By.ID, 'password')
    p.clear()
    p.send_keys('dev_password')
    btn = drv.find_element(By.CSS_SELECTOR, "button[type='submit']")
    L.js_click(drv, btn)
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    return drv.current_url


def page_state(drv):
    """页面可见状态：共 N 条 / 列表行 / 关联算法列徽章 / 空态。"""
    body = L.body_text(drv)
    total = None
    for seg in body.split():
        pass
    import re
    m = re.search(r'共\s*(\d+)\s*条', body)
    if m:
        total = int(m.group(1))
    rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    headers = [h.text.strip() for h in drv.find_elements(By.CSS_SELECTOR, 'table thead th')]
    assoc_col = None
    for i, h in enumerate(headers):
        if h == '关联算法':
            assoc_col = i
    badges, dashes, names = [], 0, []
    for r in rows:
        tds = r.find_elements(By.TAG_NAME, 'td')
        if not tds:
            continue
        try:
            names.append(tds[1].text.strip().split('\n')[0])
        except Exception:
            names.append('')
        if assoc_col is not None and assoc_col < len(tds):
            cell = tds[assoc_col]
            txt = (cell.text or '').strip()
            if txt == '—' or txt == '':
                dashes += 1
            else:
                badges.append(txt)
    empty_title = ''
    for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='empty-title'], h3"):
        t = (e.text or '').strip()
        if '暂无' in t or '加载失败' in t:
            empty_title = t
            break
    return {
        'total': total,
        'rows': len(rows),
        'headers': headers,
        'assoc_col_index': assoc_col,
        'badge_cells': len(badges),
        'dash_cells': dashes,
        'badge_texts_sample': badges[:3],
        'badge_texts_unique': sorted(set(badges)),
        'row_names_sample': names[:3],
        'empty_title': empty_title,
    }


def open_global_switcher(drv):
    """顶部全局算法切换器（aria-label=切换全局算法）。"""
    for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='切换全局算法']"):
        if b.is_displayed():
            L.js_click(drv, b)
            time.sleep(0.8)
            return (b.text or '').strip()
    return None


def choose_global_algorithm(drv, name):
    """切换器弹出层里点算法行（弹层内 button 文本 = 算法名）。"""
    for b in drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content'] button, [role='dialog'] button"):
        try:
            if b.is_displayed() and (b.text or '').strip() == name:
                L.js_click(drv, b)
                time.sleep(1.5)
                return True
        except Exception:
            pass
    # 兜底：全文匹配可见按钮
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip() == name:
                L.js_click(drv, b)
                time.sleep(1.5)
                return True
        except Exception:
            pass
    return False


def open_facet(drv, title):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip().startswith(title):
                L.js_click(drv, b)
                time.sleep(0.6)
                return b.text.strip()
        except Exception:
            pass
    return None


def choose_facet_option(drv, label):
    # Popover 内容里的选项按钮
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip() == label:
                L.js_click(drv, b)
                time.sleep(1.2)
                return True
        except Exception:
            pass
    return False


def facet_buttons(drv):
    out = []
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed():
                t = (b.text or '').strip()
                if t.startswith('关联算法'):
                    out.append(t)
        except Exception:
            pass
    return out


def wait_index(drv, timeout=25):
    """等关联算法索引请求落地（GET /algorithm/dimensions/*）。"""
    end = time.time() + timeout
    while time.time() < end:
        log = L.fetch_log(drv, '/algorithm/dimensions/')
        if log:
            return log
        time.sleep(0.4)
    return []


def set_theme(drv, base, mode):
    """切主题：写原始字符串 + 同源重载 + 断言 html class（memory: react-theme-storage-key）。"""
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.get(base + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(3)
    end = time.time() + 20
    while time.time() < end:
        cls = drv.execute_script("return document.documentElement.className") or ''
        bg = drv.execute_script('return getComputedStyle(document.body).backgroundColor')
        if mode == 'dark' and 'dark' in cls and bg not in ('rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)'):
            return cls, bg
        if mode == 'light' and 'dark' not in cls:
            return cls, bg
        time.sleep(0.5)
    return drv.execute_script("return document.documentElement.className"), \
        drv.execute_script('return getComputedStyle(document.body).backgroundColor')


def main():
    base = sys.argv[1]
    tag = sys.argv[2]
    os.environ['REACT_BASE'] = base
    drv = L.driver()
    res = {'base': base, 'tag': tag}
    try:
        res['login_url'] = login(drv, base)
        drv.get(base + '/Evaluation')
        WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        log = wait_index(drv)
        time.sleep(2)
        res['index_requests'] = [
            {'url': e.get('url'), 'status': e.get('status'), 'res_len': len(e.get('resBody') or '')}
            for e in log
        ]
        try:
            body = log[0].get('resBody') if log else ''
            if body:
                d = json.loads(body)
                dd = d.get('data', d) if isinstance(d, dict) else d
                res['index_api_count'] = len((dd or {}).get('dimensions') or [])
        except Exception as e:  # noqa: BLE001
            res['index_api_parse_error'] = str(e)

        res['initial'] = page_state(drv)
        res['shot_initial_light'] = shot(drv, tag, 'initial_light')

        # 顶部全局算法切换器（本页「算法筛选」的实际入口，aria-label=切换全局算法）
        st, opt, _ = L.api_json(drv, '/algorithm/options')
        opt = opt or {}
        dd = opt.get('data', opt) if isinstance(opt, dict) else opt
        algos = (dd or {}).get('algorithms') or []
        res['algorithms'] = [(a.get('value') or a.get('algorithm_type'), a.get('label') or a.get('name')) for a in algos]
        label = (algos[0].get('label') or algos[0].get('name')) if algos else None

        res['switcher_trigger_text'] = open_global_switcher(drv)
        visible_menu = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button')
                        if b.is_displayed() and (b.text or '').strip()]
        res['switcher_menu_texts'] = visible_menu
        option_name = label
        picked = choose_global_algorithm(drv, option_name) if option_name else False
        res['switcher_option_name'] = option_name
        res['picked_option'] = picked
        time.sleep(2.5)
        res['after_select'] = page_state(drv)
        res['switcher_after_text'] = drv.execute_script(
            "var b=document.querySelector(\"button[aria-label='切换全局算法']\");return b?b.innerText:null")
        res['shot_after_select_light'] = shot(drv, tag, 'after_select_light')

        # 深色：重载后重选算法，再截图（保证深色图是「选中算法」态）
        cls_d, bg_d = set_theme(drv, base, 'dark')
        res['dark_html_class'] = cls_d
        res['dark_body_bg'] = bg_d
        wait_index(drv)
        open_global_switcher(drv)
        res['dark_repick'] = choose_global_algorithm(drv, option_name) if option_name else False
        time.sleep(2.0)
        res['after_select_dark'] = page_state(drv)
        res['shot_after_select_dark'] = shot(drv, tag, 'after_select_dark')

        # 回浅色（避免后续误用深色截图）
        cls_l, bg_l = set_theme(drv, base, 'light')
        res['light_html_class'] = cls_l
        res['light_body_bg'] = bg_l
        time.sleep(1.0)

        # 页面 API 侧数据（页面同源 fetch）
        st_a, listd, _ = L.api_json(drv, '/evaluation/dimensions?per_page=1000')
        ld = (listd or {}).get('data', listd) if isinstance(listd, dict) else listd
        items = (ld or {}).get('items') or []
        st_c, optd, _ = L.api_json(drv, '/evaluation/dimensions/options?algorithm_type=voice_llm')
        od = (optd or {}).get('data', optd) if isinstance(optd, dict) else optd
        res['api'] = {
            'list_status': st_a, 'list_total': (ld or {}).get('total'), 'list_items': len(items),
            'list_rows_with_associated': sum(1 for i in items if i.get('associated_algorithms')),
            'options_status': st_c, 'options_count': len((od or {}).get('dimensions') or []),
        }

        # console 严重错误
        try:
            sev = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
            res['console_severe'] = sev[:5]
        except Exception as e:  # noqa: BLE001
            res['console_severe'] = 'n/a: %s' % e
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    print('JSON_RESULT ' + json.dumps(res, ensure_ascii=True))


if __name__ == '__main__':
    main()
