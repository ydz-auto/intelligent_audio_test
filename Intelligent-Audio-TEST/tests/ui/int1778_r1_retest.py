# -*- coding: utf-8 -*-
"""INT-1778 返工 R1 复测（测试工程师独立断言，不用交付自测脚本）。

复测范围（devloop §2.3：打回后只复测失败项与本次修复相关部分）：
- P2-1 关联算法 Select 收起态（新增态 / 编辑态）显示算法名、不出现类型码；
- P2-2 被测 API 卡片「算法」徽章显示算法名（含本卡之前落库的真实 API）；表格视图组件未挂载（api-table 备用），单独说明；
- P3 403 降级横幅尾句改为「当前账号不可查看」、不再指向算法配置页，且不阻断基础页签保存；
- 相关回归：Select 仍落库类型码、输出字段 / 映射页签仍能取到数据、正常态横幅未被改坏。

环境：docker 后端 15000（intelligent_audio_test）+ 本 run 旁路容器（交付 dist + 15173 同款 nginx conf）。
夹具：API「接线测试_INT1778RT_」+ 输出参数 int1778rt_out + source=api 映射，run 结束删除。
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import int1777_accept as A  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15267')
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1778_r1_retest')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1778RT_' + RUN_TAG
ALGO_CODE = 'voice_llm'
PARAM_CODE = 'int1778rt_out'
DIMENSION_ID = 121
TARGET_PARAM = 'is_reject'

RESULTS = []
SHOTS = []

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
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': str(detail)[:500]})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:500] if detail else ''))
    return ok


def shot(d, name):
    p = L.shot(d, name)
    SHOTS.append(p)
    return p


def backend_health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def goto_resources_step(d):
    d.get(L.BASE + '/start-test')
    time.sleep(6)
    steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if steps:
        L.js_click(d, steps[0])
        time.sleep(4)


def card_of(d, name):
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


def badge_texts(d):
    """页面上所有 API 卡「算法」行的 dd 文本（真实 API + 本 run 夹具一起看）"""
    out = []
    try:
        dts = d.find_elements(By.XPATH, "//dt[normalize-space(.)='算法']")
    except Exception:
        return out
    for dt in dts:
        try:
            dd = dt.find_element(By.XPATH, 'following-sibling::dd[1]')
            out.append((dd.text or '').strip())
        except Exception:
            continue
    return out


def fixture_param(d):
    st, payload, raw = L.api_json(d, '/algorithm/params?algorithm_type=%s&param_type=api' % ALGO_CODE)
    for it in ((payload or {}).get('data') or {}).get('items') or []:
        if it.get('param_code') == PARAM_CODE:
            L.api_json(d, '/algorithm/params/%s' % it['id'], 'DELETE')
    body = {
        'param_type_source': 'api', 'algorithm_type': ALGO_CODE, 'param_code': PARAM_CODE,
        'param_name': '接线测试_复测输出', 'label': '接线测试_复测标签', 'param_type': 'text',
        'direction': 'output', 'ui_order': 991,
    }
    return L.api_json(d, '/algorithm/params', 'POST', body)


def fixture_mapping(d):
    st, payload, raw = L.api_json(d, '/algorithm/mappings?algorithm_type=%s&source_type=api' % ALGO_CODE)
    for it in ((payload or {}).get('data') or {}).get('items') or []:
        if it.get('source_param') == PARAM_CODE:
            L.api_json(d, '/algorithm/mappings/%s' % it['id'], 'DELETE')
    body = {
        'algorithm_type': ALGO_CODE, 'source_type': 'api', 'source_param': PARAM_CODE,
        'source_direction': 'output', 'dimension_id': DIMENSION_ID,
        'target_param': TARGET_PARAM, 'transform_type': 'uppercase',
    }
    return L.api_json(d, '/algorithm/mappings', 'POST', body)


def cleanup(d, api_id):
    res = {}
    try:
        st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=%s&source_type=api' % ALGO_CODE)
        for it in ((payload or {}).get('data') or {}).get('items') or []:
            if it.get('source_param') == PARAM_CODE:
                res['mapping'] = L.api_json(d, '/algorithm/mappings/%s' % it['id'], 'DELETE')[0]
        st, payload, _ = L.api_json(d, '/algorithm/params?algorithm_type=%s&param_type=api' % ALGO_CODE)
        for it in ((payload or {}).get('data') or {}).get('items') or []:
            if it.get('param_code') == PARAM_CODE:
                res['param'] = L.api_json(d, '/algorithm/params/%s' % it['id'], 'DELETE')[0]
        if api_id:
            res['api'] = L.api_json(d, '/apis/%d' % api_id, 'DELETE')[0]
    except Exception as e:
        res['error'] = str(e)
    return res


def leftovers(d):
    out = {}
    try:
        out['apis'] = [it.get('name') for it in A.api_list(d)
                       if (it.get('name') or '').startswith('接线测试_INT1778RT_')]
    except Exception as e:
        out['apis_err'] = str(e)
    try:
        st, payload, _ = L.api_json(d, '/algorithm/params?algorithm_type=%s&param_type=api' % ALGO_CODE)
        out['params'] = [it.get('param_code') for it in ((payload or {}).get('data') or {}).get('items') or []
                         if it.get('param_code') == PARAM_CODE]
    except Exception as e:
        out['params_err'] = str(e)
    try:
        st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=%s&source_type=api' % ALGO_CODE)
        out['mappings'] = [it.get('source_param') for it in ((payload or {}).get('data') or {}).get('items') or []
                           if it.get('source_param') == PARAM_CODE]
    except Exception as e:
        out['mappings_err'] = str(e)
    return out


def main():
    meta = {'base': L.BASE, 'health_start': backend_health(), 'run_tag': RUN_TAG, 'name': NAME}
    d = L.driver()
    api_id = None
    try:
        print('LOGIN ->', L.login(d))
        meta['bundle'] = [s for s in d.execute_script(
            "return Array.from(document.querySelectorAll('script[src]')).map(s=>s.src)") if '/static/js/' in s][:5]
        print('BUNDLE', meta['bundle'])

        # ---------- R0 算法选项（徽章 / 下拉文案的数据源） ----------
        st, payload, raw = L.api_json(d, '/algorithm/options')
        algs = ((payload or {}).get('data') or {}).get('algorithms') or []
        label = None
        for a in algs:
            if a.get('value') == ALGO_CODE:
                label = a.get('name')
        check('RT0 /algorithm/options 给出 voice_llm 显示名', bool(label) and label != ALGO_CODE,
              '%s | %s' % (label, str(algs)[:200]))
        opt_reqs = [e for e in L.fetch_log(d, '/algorithm/options')]
        check('RT1 徽章映射走真实 GET /algorithm/options', bool(opt_reqs), str(opt_reqs)[:200])

        goto_resources_step(d)

        # ---------- P2-1 新增态 ----------
        A.open_new(d)
        A.fill(A.by_id(d, 'api-name'), NAME)
        A.pick(d, 0, label or ALGO_CODE)
        new_text = A.combo_text(d, 0)
        check('RT2 新增态：关联算法收起态 = 算法名', new_text == label, new_text)
        check('RT3 新增态：收起态不含类型码', ALGO_CODE not in new_text, new_text)
        shot(d, '01_new_select_light')
        L.apply_theme(d, 'dark')
        shot(d, '02_new_select_dark')
        L.apply_theme(d, 'light')

        A.fill(A.by_id(d, 'max-process'), '3')
        A.fill(A.by_id(d, 'api-desc'), 'INT-1778 返工复测 API')
        A.click_btn(d, '添加端点')
        time.sleep(0.6)
        A.fill(A.by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')
        A.save(d)
        time.sleep(2)
        for it in A.api_list(d):
            if it.get('name') == NAME:
                api_id = it.get('id')
        algo_saved = A.get_api(d, api_id).get('algorithm_type') if api_id else None
        check('RT4 回归：保存后 algorithm_type 仍落类型码 voice_llm', algo_saved == ALGO_CODE, str(algo_saved))
        check('RT5 自建 API 取得 id', bool(api_id), str(api_id))

        # 夹具：输出参数 + source=api 映射（走同一写端点，避免动算法草稿）
        st_p, _, raw_p = fixture_param(d)
        st_m, _, raw_m = fixture_mapping(d)
        check('RT6 夹具输出参数创建成功', st_p in (200, 201), '%s %s' % (st_p, raw_p[:120]))
        check('RT7 夹具 source=api 映射创建成功', st_m in (200, 201), '%s %s' % (st_m, raw_m[:120]))

        # ---------- P2-2 卡片徽章 ----------
        goto_resources_step(d)
        card = card_of(d, NAME)
        check('RT8 找到自建 API 卡片', card is not None, '')
        if card is not None:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
            time.sleep(0.5)
        badges = badge_texts(d)
        all_badge_txt = ' | '.join(badges)
        check('RT9 自建 API 卡片算法徽章 = 算法名', (label or '') in badges, all_badge_txt)
        check('RT10 页面所有卡片算法徽章均不含类型码', all(ALGO_CODE not in b for b in badges), all_badge_txt)
        preexisting = [b for b in badges if b and b != label]
        check('RT11 真实存量 API 徽章不是类型码（本卡之前落库的数据一并修正）',
              all(ALGO_CODE not in b and b != '—' for b in preexisting), all_badge_txt)
        shot(d, '03_card_badge_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, '04_card_badge_dark')
        L.apply_theme(d, 'light')

        # ---------- P2-1 编辑态回填 ----------
        A.open_edit(d, NAME)
        edit_text = A.combo_text(d, 0)
        check('RT12 编辑态：关联算法收起态 = 算法名', edit_text == label, edit_text)
        check('RT13 编辑态：收起态不含类型码', ALGO_CODE not in edit_text, edit_text)
        shot(d, '05_edit_select_light')
        L.apply_theme(d, 'dark')
        shot(d, '06_edit_select_dark')
        L.apply_theme(d, 'light')

        # ---------- 回归：只读页签仍有数据（与 Select 值口径相关） ----------
        L.clear_fetch_log(d)
        A.tab_click(d, '输出字段')
        time.sleep(3)
        out_txt = A.dialog_text(d)
        check('RT14 回归：输出字段页签渲染夹具输出行', PARAM_CODE in out_txt, out_txt[-300:])
        check('RT15 回归：正常态横幅尾句指向算法配置页', '维护入口在算法配置页' in out_txt, out_txt[-200:])
        params_reqs = [e for e in L.fetch_log(d, '/algorithm/params') if e.get('status') == 200]
        check('RT16 输出字段数据来自 GET /algorithm/params?param_type=api',
              any('param_type=api' in (e.get('url') or '') for e in params_reqs), str(params_reqs)[:240])

        A.tab_click(d, '映射')
        time.sleep(3)
        map_txt = A.dialog_text(d)
        check('RT17 回归：映射页签渲染夹具映射行', PARAM_CODE in map_txt, map_txt[-300:])
        map_reqs = [e for e in L.fetch_log(d, '/algorithm/mappings') if e.get('status') == 200]
        check('RT18 映射数据来自 GET /algorithm/mappings?source_type=api',
              any('source_type=api' in (e.get('url') or '') for e in map_reqs), str(map_reqs)[:240])
        check('RT19 映射页签不请求 /algorithm/definitions',
              not [e for e in L.fetch_log(d, '/algorithm/definitions')],
              str([e.get('url') for e in L.fetch_log(d)])[:240])
        shot(d, '07_mapping_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, '08_mapping_dark')
        L.apply_theme(d, 'light')

        # Network 证据叠加（页内 fetch 抓包）
        net_entries = [e for e in L.fetch_log(d)
                       if '/algorithm/params' in (e.get('url') or '')
                       or '/algorithm/mappings' in (e.get('url') or '')]
        A.network_overlay(d, net_entries[:12])
        shot(d, '09_network_readonly_tabs')
        A.remove_overlay(d)

        if A.btn(d, '取消', exact=False):
            A.click_btn(d, '取消', exact=False)
        time.sleep(1.2)

        # ---------- P3 403 降级 ----------
        d.execute_script(INJECT_403)
        L.clear_fetch_log(d)
        A.open_edit(d, NAME)
        A.tab_click(d, '输出字段')
        time.sleep(3)
        forbidden_txt = A.dialog_text(d)
        check('RT20 403：只读页签显示降级提示', '无权查看算法配置' in forbidden_txt, forbidden_txt[-300:])
        check('RT21 403：横幅尾句 = 当前账号不可查看', '当前账号不可查看' in forbidden_txt, forbidden_txt[-300:])
        check('RT22 403：横幅不再指向算法配置页', '维护入口在算法配置页' not in forbidden_txt, '')
        check('RT23 403：隐藏「去算法配置」', A.btn(d, '去算法配置', exact=False) is None, '')
        p403 = [e for e in L.fetch_log(d, '/algorithm/params') if e.get('status') == 403]
        check('RT24 403 注入生效（/algorithm/params → 403）', bool(p403), str(p403)[:200])
        shot(d, '10_forbidden_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, '11_forbidden_dark')
        L.apply_theme(d, 'light')

        # 403 不阻断基础页签保存
        A.tab_click(d, '基础')
        time.sleep(1.5)
        A.fill(A.by_id(d, 'api-desc'), 'INT-1778 返工复测 API（403 下保存）')
        L.clear_fetch_log(d)
        closed = A.save(d)
        puts = [e for e in L.fetch_log(d) if e.get('method') == 'PUT' and '/apis' in (e.get('url') or '')]
        check('RT25 403 下基础页签仍能保存（PUT 200）',
              closed and any(e.get('status') == 200 for e in puts), '%s %s' % (closed, str(puts)[:240]))
        time.sleep(1.5)
        desc_now = A.get_api(d, api_id).get('description') if api_id else None
        check('RT26 保存落库（描述已更新）', desc_now == 'INT-1778 返工复测 API（403 下保存）', str(desc_now))

    finally:
        try:
            meta['cleanup'] = cleanup(d, api_id)
            print('CLEANUP', meta['cleanup'])
        except Exception as e:
            print('CLEANUP failed', e)
        try:
            d.quit()
        except Exception:
            pass

    # 清理后再起一次浏览器核残留（避免与上一步共用会话的缓存）
    try:
        d2 = L.driver()
        try:
            L.login(d2)
            left = leftovers(d2)
        finally:
            d2.quit()
        meta['leftovers'] = left
        check('RT27 夹具清理干净（apis / params / mappings 残留 0）',
              not left.get('apis') and not left.get('params') and not left.get('mappings'), str(left))
    except Exception as e:
        check('RT27 夹具清理检查', False, str(e))

    meta['health_end'] = backend_health()
    check('RT28 收尾后端仍是 intelligent_audio_test',
          (meta['health_end'] or {}).get('database') == 'intelligent_audio_test', str(meta['health_end']))

    fails = [r for r in RESULTS if not r['pass']]
    print('SUMMARY %d/%d pass' % (len(RESULTS) - len(fails), len(RESULTS)))
    with open(os.path.join(L.ART, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump({'meta': meta, 'results': RESULTS, 'shots': SHOTS}, f, ensure_ascii=False, indent=2)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
