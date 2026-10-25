# -*- coding: utf-8 -*-
"""INT-1778 返工 R1 自测（回应前端UX审计 P2-1 / P2-2 / P3）。

环境：docker 后端 15000（intelligent_audio_test）+ 本 run 旁路前端容器（交付 dist +
15173 同款 nginx conf，反代 api_gateway），端口由 REACT_BASE 指定。

覆盖：
- P2-1 编辑 API「关联算法」Select 收起态显示算法名（新增态刚选中 / 编辑态回填），不出现类型码；
- P2-2 被测 API 卡片「算法」徽章显示算法名（本卡之后落库的 algorithm_type=voice_llm）；
- P3 403 降级时只读页签横幅尾句为「当前账号不可查看」，不再指向算法配置页。

夹具：一条「接线测试_INT1778R1_」前缀的 API，run 结束 DELETE 掉。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import int1777_accept as A  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15299')
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1778_r1')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1778R1_' + RUN_TAG
ALGO_CODE = 'voice_llm'

RESULTS = []
SHOTS = []

# 403 注入：/algorithm/params 与 /algorithm/mappings 直接在 fetch 层返回 403（真实网络层之外，
# 与被审计轮同法；页面重新导航会丢失，所以注入后只用弹窗内操作）
INJECT_403 = r"""
if (!window.__origFetch403) { window.__origFetch403 = window.fetch; }
window.fetch = function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  if (url.indexOf('/algorithm/params') !== -1 || url.indexOf('/algorithm/mappings') !== -1) {
    (window.__fetchLog = window.__fetchLog || []).push(
      {url: url, method: 'GET', status: 403, injected: true, t: Date.now()});
    return Promise.resolve(new Response(JSON.stringify({detail: 'forbidden'}), {
      status: 403, headers: {'Content-Type': 'application/json'}
    }));
  }
  return window.__origFetch403.apply(this, arguments);
};
"""


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def shot(d, name):
    p = L.shot(d, name)
    SHOTS.append(p)
    return p


def goto_resources_step(d):
    d.get(L.BASE + '/start-test')
    time.sleep(6)
    steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if steps:
        L.js_click(d, steps[0])
        time.sleep(4)


def card_of(d, name):
    """find_card 返回的是含名字的最小节点，往上找到带「算法 / 最大并发」规格行的卡片容器"""
    node = A.find_card(d, name)
    if node is None:
        return None
    cur = node
    for _ in range(6):
        try:
            txt = cur.text or ''
        except Exception:
            break
        if '算法' in txt and '最大并发' in txt:
            return cur
        try:
            cur = cur.find_element(By.XPATH, '..')
        except Exception:
            break
    return node


def algorithm_label(d):
    st, payload, raw = L.api_json(d, '/algorithm/options')
    algs = ((payload or {}).get('data') or {}).get('algorithms') or []
    for a in algs:
        if a.get('value') == ALGO_CODE:
            return a.get('name'), algs
    return None, algs


def main():
    d = L.driver()
    api_id = None
    try:
        print('LOGIN ->', L.login(d))
        label, algs = algorithm_label(d)
        check('R0 /algorithm/options 给出 voice_llm 的显示名', bool(label) and label != ALGO_CODE,
              '%s | %s' % (label, str(algs)[:200]))

        goto_resources_step(d)

        # ---------- P2-1 新增态：刚选中就显示算法名 ----------
        A.open_new(d)
        A.fill(A.by_id(d, 'api-name'), NAME)
        A.pick(d, 0, label or ALGO_CODE)
        new_text = A.combo_text(d, 0)
        check('R1 新增态关联算法收起态 = 算法名', new_text == label, new_text)
        check('R2 新增态收起态不含类型码', ALGO_CODE not in new_text, new_text)
        shot(d, '01_new_dialog_select_light')
        L.apply_theme(d, 'dark')
        shot(d, '02_new_dialog_select_dark')
        L.apply_theme(d, 'light')

        A.fill(A.by_id(d, 'max-process'), '3')
        A.fill(A.by_id(d, 'api-desc'), 'INT-1778 返工自测 API')
        A.click_btn(d, '添加端点')
        time.sleep(0.6)
        A.fill(A.by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')
        A.save(d)
        for it in A.api_list(d):
            if it.get('name') == NAME:
                api_id = it.get('id')
        check('R3 自建 API 落库 algorithm_type = voice_llm',
              (A.get_api(d, api_id).get('algorithm_type') == ALGO_CODE) if api_id else False,
              str(A.get_api(d, api_id).get('algorithm_type')) if api_id else 'api not found')
        time.sleep(2)

        # ---------- P2-2 卡片徽章 = 算法名 ----------
        goto_resources_step(d)
        card = card_of(d, NAME)
        check('R4 找到自建 API 卡片', card is not None, '')
        card_text = (card.text or '') if card is not None else ''
        check('R5 卡片算法徽章显示算法名', (label or '') and label in card_text, card_text[:300])
        check('R6 卡片文案不含类型码', ALGO_CODE not in card_text, card_text[:300])
        if card is not None:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
            time.sleep(0.5)
        shot(d, '03_api_card_badge_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, '04_api_card_badge_dark')
        L.apply_theme(d, 'light')

        # ---------- P2-1 编辑态回填 ----------
        A.open_edit(d, NAME)
        edit_text = A.combo_text(d, 0)
        check('R7 编辑态关联算法收起态 = 算法名', edit_text == label, edit_text)
        check('R8 编辑态收起态不含类型码', ALGO_CODE not in edit_text, edit_text)
        shot(d, '05_edit_dialog_select_light')
        L.apply_theme(d, 'dark')
        shot(d, '06_edit_dialog_select_dark')
        L.apply_theme(d, 'light')

        # 正常态横幅（对照）：有权限时尾句仍指算法配置页
        A.tab_click(d, '输出字段')
        time.sleep(2.5)
        normal_txt = A.dialog_text(d)
        check('R9 正常态横幅尾句指向算法配置页', '维护入口在算法配置页' in normal_txt, normal_txt[-260:])
        A.click_btn(d, '取消', exact=False) if A.btn(d, '取消', exact=False) else None
        time.sleep(1.2)

        # ---------- P3 403 降级横幅 ----------
        d.execute_script(INJECT_403)
        L.clear_fetch_log(d)
        A.open_edit(d, NAME)
        A.tab_click(d, '输出字段')
        time.sleep(3)
        forbidden_txt = A.dialog_text(d)
        check('R10 403 → 只读页签降级提示', '无权查看算法配置' in forbidden_txt, forbidden_txt[-260:])
        check('R11 403 横幅尾句 = 当前账号不可查看', '当前账号不可查看' in forbidden_txt, forbidden_txt[-260:])
        check('R12 403 横幅不再指向算法配置页', '维护入口在算法配置页' not in forbidden_txt, '')
        check('R13 403 → 隐藏「去算法配置」', A.btn(d, '去算法配置', exact=False) is None, '')
        params_403 = [e for e in L.fetch_log(d, '/algorithm/params') if e.get('status') == 403]
        check('R14 403 注入生效（/algorithm/params → 403）', bool(params_403), str(params_403)[:200])
        shot(d, '07_forbidden_banner_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, '08_forbidden_banner_dark')
        L.apply_theme(d, 'light')

        if A.btn(d, '取消', exact=False):
            A.click_btn(d, '取消', exact=False)
    finally:
        try:
            if api_id:
                st, _, raw = L.api_json(d, '/apis/%d' % api_id, 'DELETE')
                print('CLEANUP api %s -> %s %s' % (api_id, st, raw[:120]))
        except Exception as e:
            print('CLEANUP api failed', e)
        try:
            left = [it.get('name') for it in A.api_list(d) if (it.get('name') or '').startswith('接线测试_INT1778R1_')]
            print('LEFTOVER apis:', left)
        except Exception as e:
            print('LEFTOVER check failed', e)
        try:
            d.quit()
        except Exception:
            pass

    fails = [r for r in RESULTS if not r['pass']]
    print('SUMMARY %d/%d pass' % (len(RESULTS) - len(fails), len(RESULTS)))
    with open(os.path.join(L.ART, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump({'results': RESULTS, 'shots': SHOTS}, f, ensure_ascii=False, indent=2)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
