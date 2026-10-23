# -*- coding: utf-8 -*-
"""INT-1627 追加缺陷实测：复核历史抽屉长用例名溢出裁切（真实库栈 docker :15000）。

页面：/tasks/417（库内 5 条复核历史）→ 工具行「查看复核历史」→ 抽屉。
断言（缺陷期望「max-w-full truncate + Tooltip 全文 / break-all 换行」）：
  1. 用例名 Badge 的右边界不超出抽屉内容区（不出现「Badge 比抽屉还宽被父级 overflow:hidden 切掉」）；
  2. 长名可见地被省略号截断或换行（text-overflow:ellipsis 且 scrollWidth>clientWidth，或 white-space 可换行）；
  3. 全文可达（title 或 Tooltip 内容）。

dist ← frontend-react/dist（先 pnpm build）；旁路 nginx 连 api_gateway（复用
verify_int1627_publish_dialog.Stack，normal 模式，无失败注入）。
用法：python tests/ui/verify_int1627_review_drawer.py
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1627_publish_dialog import (  # noqa: E402
    ART, BASE, DRIVER, Stack, _opts, http_json, js_click, login, log, set_theme, shot,
    theme_is,
)

TASK_ID = 417
CASE_NAME_PREFIX = '测试用例_'

MEASURE_JS = """
const drawer = arguments[0];
const prefix = arguments[1];
const dr = drawer.getBoundingClientRect();
const cs = getComputedStyle(drawer);
const inner = {
  left: dr.left + parseFloat(cs.paddingLeft || 0),
  right: dr.right - parseFloat(cs.paddingRight || 0),
  width: dr.width,
};
const out = [];
for (const el of drawer.querySelectorAll('span')) {
  const t = (el.textContent || '').trim();
  if (!t.startsWith(prefix)) continue;
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  out.push({
    text: t,
    textLen: t.length,
    left: Math.round(r.left * 10) / 10,
    right: Math.round(r.right * 10) / 10,
    width: Math.round(r.width * 10) / 10,
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    overflowX: s.overflowX,
    textOverflow: s.textOverflow,
    whiteSpace: s.whiteSpace,
    title: el.getAttribute('title'),
    cls: el.className,
  });
}
return {drawer: {left: dr.left, right: dr.right, width: dr.width,
                 scrollWidth: drawer.scrollWidth, clientWidth: drawer.clientWidth},
        inner, badges: out};
"""


def open_history_drawer(drv):
    btn = WebDriverWait(drv, 60).until(lambda d: d.find_elements(
        By.XPATH, "//button[normalize-space(.)='查看复核历史']"))
    js_click(drv, btn[0])
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(
        By.XPATH, "//*[contains(normalize-space(.), '复核历史 —')]"))
    time.sleep(1.5)
    # 抽屉容器：包含「复核历史 —」标题的最近 role=dialog / sheet 容器
    drawers = drv.find_elements(By.XPATH, "//*[@role='dialog']")
    for el in drawers:
        if '复核历史' in (el.text or ''):
            return el
    raise AssertionError('未找到复核历史抽屉容器，role=dialog 数=%d' % len(drawers))


def main():
    ev = {'card': 'INT-1627', 'phase': 'review-history-drawer', 'task_id': TASK_ID}
    st, health = http_json('http://127.0.0.1:15000/health')
    log('[0] /health %s database=%s' % (st, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', health

    st, h = http_json('http://127.0.0.1:15000/api/v1/tasks/results/%d/review-history' % TASK_ID)
    items = h['data']['items']
    log('  复核历史 %d 条；result_ids=%s' % (len(items), sorted({i['result_id'] for i in items})))
    ev['history_rows'] = len(items)

    stack = Stack()
    drv = None
    ok = True
    try:
        stack.start()
        drv = webdriver.Chrome(service=Service(DRIVER), options=_opts())
        drv.set_script_timeout(60)
        login(drv)

        for mode in ('light', 'dark'):
            log('[1] 抽屉长用例名测量（%s）' % mode)
            set_theme(drv, mode)
            drv.get(BASE + '/tasks/%d' % TASK_ID)
            WebDriverWait(drv, 120).until(
                lambda d: d.find_elements(By.XPATH, "//button[normalize-space(.)='查看复核历史']"))
            assert theme_is(drv, mode), '%s 主题未生效' % mode
            time.sleep(1.0)
            drawer = open_history_drawer(drv)
            shot(drv, 'int1627_75_review_history_drawer_%s.png' % mode)
            m = drv.execute_script(MEASURE_JS, drawer, CASE_NAME_PREFIX)
            log('  抽屉宽 %.0fpx，Badge %d 个' % (m['drawer']['width'], len(m['badges'])))
            for b in m['badges']:
                log('   - %d 字，宽 %.0fpx，right=%.0f，overflow=%s ellipsis=%s ws=%s title=%r'
                    % (b['textLen'], b['width'], b['right'], b['overflowX'],
                       b['textOverflow'], b['whiteSpace'], b['title']))
            ev['measure_%s' % mode] = m
            assert len(m['badges']) > 0, '抽屉内未渲染用例名 Badge（检查 caseNameMap）'

            over = [b for b in m['badges'] if b['right'] > m['inner']['right'] + 0.5]
            clipped_no_ellipsis = [
                b for b in m['badges']
                if b['scrollWidth'] > b['clientWidth'] + 1
                and b['textOverflow'] != 'ellipsis'
                and b['whiteSpace'] in ('nowrap', 'pre')
            ]
            no_full_text = [b for b in m['badges']
                            if b['scrollWidth'] > b['clientWidth'] + 1 and not b['title']]
            if over:
                ok = False
                log('  ❌ 超出抽屉内容区：%d 个（最大 right=%.0f > %.0f）'
                    % (len(over), max(b['right'] for b in over), m['inner']['right']))
            if clipped_no_ellipsis:
                ok = False
                log('  ❌ 文本被裁切且无省略号：%d 个' % len(clipped_no_ellipsis))
            if no_full_text:
                ok = False
                log('  ❌ 长名被裁切且无 title/Tooltip 全文：%d 个' % len(no_full_text))

            # 长名可见态明细（供结论引用）
            ev['measure_%s' % mode]['overflow_count'] = len(over)
            ev['measure_%s' % mode]['clipped_no_ellipsis'] = len(clipped_no_ellipsis)
            ev['measure_%s' % mode]['clipped_no_fulltext'] = len(no_full_text)

            # 关闭抽屉（Esc 会连 Sheet 一起关，属预期）
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.0)

        ev['result'] = 'PASS' if ok else 'FAIL'
        log('[2] 结论：%s' % ev['result'])
    finally:
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass
        stack.stop()
        with open(os.path.join(ART, 'evidence_int1627_drawer.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        log('证据 JSON → %s' % os.path.join(ART, 'evidence_int1627_drawer.json'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
