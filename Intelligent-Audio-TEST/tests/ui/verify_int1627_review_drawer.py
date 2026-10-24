# -*- coding: utf-8 -*-
"""INT-1627 追加缺陷实测：复核历史抽屉长用例名溢出裁切（真实库栈 docker :15000）。

页面：/tasks/417（库内 5 条复核历史）→ 工具行「查看复核历史」→ 抽屉。
断言（缺陷期望「max-w-full truncate + Tooltip 全文 / break-all 换行」）：
  1. 用例名徽章右边界不超出抽屉内容区（不再「徽章比抽屉还宽被父级 overflow:hidden 切掉」）；
  2. 长名可见地被省略号截断或换行（text-overflow:ellipsis 且 scrollWidth>clientWidth，或可换行）；
  3. 全文可达：悬停徽章出现 base-ui Tooltip（[data-slot=tooltip-content]，无 role=tooltip），
     弹层文本 = 用例名全文（与接口 /testcases/{id} 的 name 逐字相等）。

dist ← frontend-react/dist（先 pnpm build）；旁路 nginx 连 api_gateway（复用
verify_int1627_publish_dialog.Stack，normal 模式，无失败注入）。
用法：python tests/ui/verify_int1627_review_drawer.py
环境变量：INT1627_EXPECT=FAIL 表示预期失败（用于基线与修复后对照的区分力证明）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1627_publish_dialog import (  # noqa: E402
    API, ART, BASE, DRIVER, Stack, _opts, http_json, js_click, login, log, set_theme, shot,
    theme_is,
)

TASK_ID = 417
CASE_NAME_PREFIX = '测试用例_'
EXPECT = os.environ.get('INT1627_EXPECT', 'PASS').upper()

MEASURE_JS = """
const drawer = arguments[0];
const dr = drawer.getBoundingClientRect();
const cs = getComputedStyle(drawer);
const inner = {
  left: dr.left + parseFloat(cs.paddingLeft || 0),
  right: dr.right - parseFloat(cs.paddingRight || 0),
  width: dr.width,
};
const out = [];
for (const b of drawer.querySelectorAll("[data-slot='review-history-case-name']")) {
  // 兜底：老版本没有 data-slot，用文本前缀找徽章
  const nameEl = b.querySelector('span') || b;
  const r = b.getBoundingClientRect();
  const s = getComputedStyle(nameEl);
  const text = (b.textContent || '').trim();
  out.push({
    text: text,
    textLen: text.length,
    left: Math.round(r.left * 10) / 10,
    right: Math.round(r.right * 10) / 10,
    badgeWidth: Math.round(r.width * 10) / 10,
    nameWidth: Math.round(nameEl.getBoundingClientRect().width * 10) / 10,
    nameScrollWidth: nameEl.scrollWidth,
    nameClientWidth: nameEl.clientWidth,
    overflowX: s.overflowX,
    textOverflow: s.textOverflow,
    whiteSpace: s.whiteSpace,
    hasEllipsis: s.textOverflow === 'ellipsis' && nameEl.scrollWidth > nameEl.clientWidth + 1,
    wrapAllowed: s.whiteSpace !== 'nowrap' && s.whiteSpace !== 'pre',
    badgeClass: b.className,
    nameClass: nameEl.className,
  });
}
const badgeFallback = [];
const bgs = [];
for (const el of drawer.querySelectorAll('span')) {
  const t = (el.textContent || '').trim();
  if (t.startsWith(arguments[1]) && !el.closest("[data-slot='review-history-case-name']")) {
    const r = el.getBoundingClientRect();
    bgs.push({text: t, textLen: t.length, right: Math.round(r.right * 10) / 10,
              width: Math.round(r.width * 10) / 10});
  }
}
return {drawer: {left: dr.left, right: dr.right, width: dr.width,
                 scrollWidth: drawer.scrollWidth, clientWidth: drawer.clientWidth},
        inner, badges: out, fallback: bgs};
"""


def open_history_drawer(drv):
    btn = WebDriverWait(drv, 60).until(lambda d: d.find_elements(
        By.XPATH, "//button[normalize-space(.)='查看复核历史']"))
    js_click(drv, btn[0])
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(
        By.XPATH, "//*[contains(normalize-space(.), '复核历史 —')]"))
    drawers = drv.find_elements(By.XPATH, "//*[@role='dialog']")
    # 动画期间 Selenium .text 为空（元素尚不可见），轮询到可见且带标题的抽屉；
    # 关闭过的 base-ui 弹层会残留在 DOM，取最后一个匹配项
    target = None
    deadline = time.time() + 30
    while time.time() < deadline:
        for el in drv.find_elements(By.XPATH, "//*[@role='dialog']"):
            try:
                if el.is_displayed() and '复核历史' in (el.text or ''):
                    target = el
            except Exception:
                continue
        if target is not None:
            break
        time.sleep(0.4)
    if target is None:
        raise AssertionError('未找到可见的复核历史抽屉容器，role=dialog 数=%d'
                             % len(drawers))
    # 等 review-history 行渲染完（骨架态没有「操作人」与用例名），真实库可能 >10s
    deadline = time.time() + 60
    while time.time() < deadline:
        names = target.find_elements(By.XPATH, ".//span[starts-with(normalize-space(.), '%s')]"
                                      % CASE_NAME_PREFIX)
        if names:
            break
        time.sleep(0.5)
    time.sleep(0.8)
    return target


def hover_text(drv, el, expect_text, timeout=20):
    """悬停徽章 → 返回可见 Tooltip 文本（base-ui：无 role=tooltip，用 data-slot）"""
    ActionChains(drv).move_to_element(el).perform()
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        tips = drv.find_elements(By.CSS_SELECTOR, "[data-slot='tooltip-content']")
        for t in reversed(tips):
            try:
                if t.is_displayed() and (t.text or '').strip():
                    last = (t.text or '').strip()
                    if last == expect_text:
                        return last
            except Exception:
                continue
        time.sleep(0.3)
    return last


def main():
    ev = {'card': 'INT-1627', 'phase': 'review-history-drawer', 'task_id': TASK_ID,
          'expect': EXPECT}
    st, health = http_json('http://127.0.0.1:15000/health')
    log('[0] /health %s database=%s' % (st, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', health
    ev['health'] = health

    st, h = http_json('http://127.0.0.1:15000/api/v1/tasks/results/%d/review-history' % TASK_ID)
    items = h['data']['items']
    log('  复核历史 %d 条；result_ids=%s' % (len(items), sorted({i['result_id'] for i in items})))
    ev['history_rows'] = len(items)

    # 接口真值：过程中涉及的用例名（逐字比对 Tooltip）
    expected = {}
    for cid in sorted({i['test_case_id'] for i in items}):
        st, c = http_json('%s/testcases/%s' % (API, cid))
        name = c['data']['name']
        expected[name] = len(name)
        log('  用例 %s → %d 字 %r' % (cid[:8], len(name), name[:28] + '…'))
    ev['expected_names'] = expected

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
            log('  抽屉宽 %.0fpx（内容区 %.0f ~ %.0f），徽章 %d 个'
                % (m['drawer']['width'], m['inner']['left'], m['inner']['right'],
                   len(m['badges'])))
            for b in m['badges']:
                log('   - %d 字，徽章宽 %.0fpx，right=%.0f，ellipsis=%s wrap=%s'
                    % (b['textLen'], b['badgeWidth'], b['right'],
                       b['hasEllipsis'], b['wrapAllowed']))
            ev['measure_%s' % mode] = m
            legacy = len(m['badges']) == 0
            if legacy:
                # 基线（未修复）实现：用例名直接以裸 span 渲染，没有截断徽章容器
                if not m['fallback']:
                    raise AssertionError('抽屉内未渲染用例名（检查 caseNameMap）')
                ok = False
                log('  ❌ 基线实现：%d 个用例名以裸 span 渲染，无截断徽章容器'
                    % len(m['fallback']))
                ev['measure_%s' % mode]['legacy_render'] = True
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1.0)
                continue

            over = [b for b in m['badges'] if b['right'] > m['inner']['right'] + 0.5]
            clipped_no_ellipsis = [
                b for b in m['badges']
                if b['nameScrollWidth'] > b['nameClientWidth'] + 1
                and not b['hasEllipsis'] and not b['wrapAllowed']
            ]
            if over:
                ok = False
                log('  ❌ 超出抽屉内容区：%d 个（最大 right=%.0f > %.0f）'
                    % (len(over), max(b['right'] for b in over), m['inner']['right']))
            if clipped_no_ellipsis:
                ok = False
                log('  ❌ 文本被裁切且无省略号/换行：%d 个' % len(clipped_no_ellipsis))
            if m['fallback']:
                ok = False
                log('  ❌ 存在不在徽章内、直接以长文本渲染的 span：%d 个'
                    % len(m['fallback']))
            ev['measure_%s' % mode]['overflow_count'] = len(over)
            ev['measure_%s' % mode]['clipped_no_ellipsis'] = len(clipped_no_ellipsis)

            # 全文可达：逐个悬停（长名优先），Tooltip 文本须与接口名逐字相等
            badges_el = drawer.find_elements(
                By.CSS_SELECTOR, "[data-slot='review-history-case-name']")
            tooltip_checks = []
            long_first = sorted(
                zip(m['badges'], badges_el), key=lambda p: -p[0]['textLen'])
            for b, el in long_first:
                txt = hover_text(drv, el, b['text'])
                match = (txt == b['text'] and b['text'] in expected)
                tooltip_checks.append({'textLen': b['textLen'], 'tooltip': txt,
                                       'match_api_name': b['text'] in expected,
                                       'hit': match})
                log('   - 悬停 %d 字 → tooltip=%d 字，与接口名相等=%s'
                    % (b['textLen'], len(txt or ''), match))
                if not match:
                    ok = False
                    log('  ❌ Tooltip 未提供用例名全文（或与接口名不一致）')
                if b['textLen'] >= 70:
                    shot(drv, 'int1627_75b_review_history_tooltip_%s.png' % mode)
            ev['tooltip_%s' % mode] = tooltip_checks

            # Esc：先收 Tooltip，必要时连抽屉一起关（下一轮循环本来会重新导航）
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.0)

        ev['result'] = 'PASS' if ok else 'FAIL'
        log('[2] 结论：%s（预期 %s）' % (ev['result'], EXPECT))
        if EXPECT == 'FAIL':
            ok = not ok   # 基线对照：缺陷存在即证明脚本有区分力
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
