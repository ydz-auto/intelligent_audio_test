# -*- coding: utf-8 -*-
"""INT-1843 验收：用例编辑抽屉「评估维度」音乐图标改数据驱动（requiresAudio）。

验法：旁路 nginx 站（wiring/react 头 0e694411a 树 + 交付 3d77f70aa diff 构建的 dist）连 docker 网关 15000，
浏览器进 /testcases/by-group → 展开分组 → 编辑用例 → 「评估维度」步 → 统计带
title「该维度需要音频文件，将随多轮音频一起上传」的 chip，并与 /evaluation/dimensions/options
的 requires_audio=true 集合做对照；浅/深色各截一张；同时读页内 fetch 日志取证。

A/B：同一脚本对 REACT_BASE=http://127.0.0.1:15173（不含本卡的 shared 镜像）复跑，确认修复前为 0。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15243')
API = 'http://127.0.0.1:15000'
TAG = os.environ.get('RUN_TAG', 'fix')
ART = os.path.join(L.ART, 'int1843_' + TAG)
os.makedirs(ART, exist_ok=True)
ICON_TITLE = '该维度需要音频文件，将随多轮音频一起上传'
SEARCH_TERM = os.environ.get('SEARCH_TERM', '接线测试_INT1681')

RESULT = {'base': BASE, 'tag': TAG, 'shots': [], 'icons': [], 'net': [], 'chips': {}}


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    RESULT['shots'].append(os.path.basename(p))
    return p


def wait(d, how, sel, timeout=60):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            els = [e for e in d.find_elements(how, sel) if e.is_displayed()]
            if els:
                return els
        except Exception as e:  # StaleElement 等
            last = e
        time.sleep(0.35)
    raise RuntimeError('wait timeout: %s %s (%s)' % (how, sel, last))


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    try:
        el.click()
    except Exception:
        d.execute_script('arguments[0].click();', el)


def wait_any(d, how, sel, timeout=60):
    """等元素出现（不要求 is_displayed——卡内动作按钮默认 hover 显现）。"""
    end = time.time() + timeout
    while time.time() < end:
        els = d.find_elements(how, sel)
        if els:
            return els
        time.sleep(0.35)
    raise RuntimeError('wait_any timeout: %s %s' % (how, sel))


def open_audio_step(d):
    """从列表进抽屉「评估维度」步。"""
    d.get(BASE + '/testcases/by-group')
    box = wait(d, By.CSS_SELECTOR, "input[aria-label='搜索用例']", 90)[0]
    box.clear()
    box.send_keys(SEARCH_TERM)
    time.sleep(1.6)  # debounce 500ms + 请求

    # 搜索后逐个展开分组卡（组头容器含「N 条」计数徽章），使目标用例所在组渲染用例卡
    heads = d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer') and .//span[contains(normalize-space(.),'条')]]")
    for h in heads:
        try:
            if h.is_displayed():
                js_click(d, h)
                time.sleep(0.5)
        except Exception:
            pass
    time.sleep(1.5)

    edit_btns = wait_any(d, By.CSS_SELECTOR, "button[aria-label='编辑用例']", 90)
    js_click(d, edit_btns[0])
    time.sleep(1.5)

    wait(d, By.XPATH, "//*[@role='tab' and contains(normalize-space(.),'评估维度')]", 60)
    tabs = d.find_elements(By.XPATH, "//*[@role='tab' and contains(normalize-space(.),'评估维度')]")
    js_click(d, tabs[0])
    time.sleep(1.5)
    return True


def collect(d):
    """统计抽屉内音乐图标 chip 与全部 chip 名称。"""
    dialogs = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']") if e.is_displayed()]
    root = dialogs[-1] if dialogs else d
    icons = root.find_elements(By.XPATH, ".//*[@title='%s']" % ICON_TITLE)
    icon_chips = []
    for ic in icons:
        try:
            btn = ic.find_element(By.XPATH, "./ancestor::button[1]")
            icon_chips.append({'chip': btn.text.strip()[:40], 'displayed': ic.is_displayed()})
        except Exception:
            icon_chips.append({'chip': '?', 'displayed': ic.is_displayed()})
    # 全部 chip（评估维度云内 button，含「主」/「子」徽章）
    chips = []
    for b in root.find_elements(By.XPATH, ".//button[contains(normalize-space(.),'主') or contains(normalize-space(.),'子')]"):
        t = b.text.strip()
        if t and len(t) < 60:
            chips.append(t[:40])
    # 抽屉上下文：关联算法选中值 + 维度云空态文案（区分「无关联维度」与真渲染）
    meta = {'algo': '', 'empty': ''}
    try:
        combo = d.find_elements(By.XPATH, "//button[@role='combobox']")
        meta['algo'] = ' | '.join(c.text.strip() for c in combo if c.is_displayed())[:120]
    except Exception:
        pass
    try:
        html = root.text
        for key in ('暂无可用维度（当前算法类型无关联维度）', '暂无可用维度', '没有匹配的评估维度'):
            if key in html:
                meta['empty'] = key
                break
    except Exception:
        pass
    return icon_chips, chips, meta


def fetch_net(d):
    try:
        log = d.execute_script('return (window.__fetchLog||[]).map(function(e){return {url:e.url,status:e.status,resBody:(e.resBody||"").slice(0,200000)}})')
    except Exception:
        return []
    out = []
    for e in log:
        if 'dimensions/options' in e['url'] or ('/evaluation/dimensions' in e['url'] and 'options' not in e['url']):
            try:
                body = json.loads(e['resBody']) if e['resBody'] else {}
            except Exception:
                body = {}
            dims = ((body.get('data') or {}).get('dimensions') or [])
            items = ((body.get('data') or {}).get('items') or [])
            out.append({
                'url': e['url'], 'status': e['status'],
                'dims': len(dims), 'items': len(items),
                'audio_true': len([x for x in dims if x.get('requires_audio')]),
            })
    return out


def run_theme(d, theme):
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    open_audio_step(d)
    # 等图标或空态稳定
    time.sleep(2.5)
    icon_chips, chips, meta = collect(d)
    shot(d, 'drawer-eval-%s' % theme)
    return icon_chips, chips, meta


def main():
    d = L.driver()
    try:
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': L.FETCH_PATCH})
        d.get(BASE + '/')
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")
        icon_chips, chips, meta = run_theme(d, 'light')
        RESULT['icons'] = icon_chips
        RESULT['chips'] = {'count': len(chips), 'sample': chips[:12], 'meta': meta}
        RESULT['net'] = fetch_net(d)

        # 深色（同源整页重载）
        icon_chips2, chips2, meta2 = run_theme(d, 'dark')
        RESULT['icons_dark'] = icon_chips2
        RESULT['chips_dark'] = {'count': len(chips2), 'sample': chips2[:12], 'meta': meta2}
        shot(d, 'after-dark')
        RESULT['ok'] = True
    except Exception:
        RESULT['ok'] = False
        RESULT['error'] = traceback.format_exc()[-2000:]
        try:
            shot(d, 'error')
        except Exception:
            pass
    finally:
        try:
            d.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'result.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(RESULT, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: v for k, v in RESULT.items() if k in ('base', 'tag', 'ok', 'error', 'shots', 'net', 'chips', 'chips_dark')}, ensure_ascii=False, indent=2))
        print('ICON_COUNT_LIGHT=%d ICON_COUNT_DARK=%d' % (len(RESULT.get('icons') or []), len(RESULT.get('icons_dark') or [])))
        print('result ->', out)


if __name__ == '__main__':
    main()
