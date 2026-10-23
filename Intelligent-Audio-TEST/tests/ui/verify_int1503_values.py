# -*- coding: utf-8 -*-
"""INT-1503 独立复核：页面逐值与 GET /spl/{id} 原始点集一一对应 + 曲线画布差分证据。

复用同目录 verify_int1503_spl_calibration.py 的浏览器骨架（登录/建映射/校准/详情读取），
但断言全部改为「接口原值 vs 页面渲染值」逐行比对，并对曲线画布做校准前/后的像素差分
（空态只有「暂无数据」文字，有数据时折线+散点会显著增加非透明像素）。

环境：本 run dev server（REACT_DEV_BASE，5383）→ 真实库栈 5700（主库 intelligent_audio_test）。
写数据纪律：只建「接线测试_INT1503_」前缀映射，脚本末尾删除。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1503_spl_calibration as H  # noqa: E402

NAME = '接线测试_INT1503_复核' + time.strftime('%H%M%S')
PREFIX = '接线测试_INT1503_'
EVID = {'checks': [], 'api': {}, 'page': {}}


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    EVID['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:3000]})
    log(('PASS ' if ok else 'FAIL ') + name + ((' | ' + str(detail)[:800]) if detail else ''))
    return ok


CANVAS_ALPHA_PX = r"""
  var sec = document.querySelector("section[aria-labelledby='spl-curve-title']");
  if (!sec) return -1;
  var total = 0;
  var canvases = sec.querySelectorAll('canvas');
  for (var i = 0; i < canvases.length; i++) {
    var c = canvases[i];
    try {
      var ctx = c.getContext('2d', {willReadFrequently: true});
      var d = ctx.getImageData(0, 0, c.width, c.height).data;
      for (var p = 3; p < d.length; p += 4) { if (d[p] > 8) total++; }
    } catch (e) { return -2; }
  }
  return total;
"""


def api_json(d, path):
    r = H.page_fetch(d, path)
    try:
        body = json.loads(r['body'])
    except Exception:
        return r['status'], {}
    return r['status'], (body.get('data', body) if isinstance(body, dict) else body)


def fmt(v):
    """页面渲染口径：数字按 JS 数字转字符串（1 → '1'，40.0 → '40'）。"""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def open_detail(d):
    H.open_row_menu(d, NAME)
    H.menu_click(d, '详情')
    H.find(d, "//div[@role='dialog']//*[contains(normalize-space(.),'增益映射详情')]")
    time.sleep(2.0)


def main():
    d = H.new_driver()
    try:
        H.login(d)
        H.open_page(d, dark=False)

        # 预清理本卡残留
        st, lst = api_json(d, '/api/v1/spl?page=1&per_page=1000')
        for item in (lst.get('items') or []):
            if str(item.get('name', '')).startswith(PREFIX):
                d.execute_async_script(
                    "var id=arguments[0],done=arguments[arguments.length-1];"
                    "var t=window.localStorage.getItem('iatp:auth:token:v1');"
                    "fetch('/api/v1/spl/'+id,{method:'DELETE',headers:t?{Authorization:'Bearer '+t}:{}})"
                    ".then(function(r){return r.text().then(function(x){done(r.status);});})"
                    ".catch(function(e){done(String(e));});", item['id'])

        # 建映射（清空表单默认 4 个校准点 → 未校准空点集）
        H.js_click(d, H.find(d, "//button[normalize-space(.)='添加增益映射']"))
        H.dialog(d)
        H.WebDriverWait(d, 20).until(lambda dd: dd.find_elements(H.By.XPATH, "//input[@aria-label='映射名称']"))
        H.find(d, "//input[@aria-label='映射名称']").send_keys(NAME)
        dist = H.find(d, "//input[@aria-label='测量距离']")
        dist.click()
        dist.send_keys(u'' + 'a')
        dist.send_keys(u'')
        dist.send_keys('1.0')
        for _ in range(6):
            dels = [e for e in d.find_elements(H.By.XPATH,
                    "//div[@role='dialog']//button[starts-with(@aria-label,'删除第')]") if e.is_displayed()]
            if not dels:
                break
            H.js_click(d, dels[0])
            time.sleep(0.2)
        H.js_click(d, H.find(d, "//div[@role='dialog']//button[normalize-space(.)='保存']"))
        H.WebDriverWait(d, 30).until(lambda dd: not [e for e in dd.find_elements(
            H.By.XPATH, "//div[@role='dialog']//input[@aria-label='映射名称']") if e.is_displayed()])
        time.sleep(2.0)

        st, lst = api_json(d, '/api/v1/spl?page=1&per_page=1000')
        mine = [i for i in (lst.get('items') or []) if i.get('name') == NAME]
        check('新建映射已入列表', bool(mine), st)
        if not mine:
            return 1
        m_id = mine[0]['id']

        # 校准前：详情空态 + 画布像素基线
        H.search(d, NAME)
        H.row_for(d, NAME)
        open_detail(d)
        pre_rows = H.read_points(d, 'spl-points-title')
        check('校准前无校准点（空态）', len(pre_rows) == 0, len(pre_rows))
        pre_px = d.execute_script(CANVAS_ALPHA_PX)
        check('校准前画布像素基线已取到', isinstance(pre_px, int) and pre_px >= 0, pre_px)
        H.save(d, '10_before_calibration_light')
        H.close_dialog(d)
        time.sleep(0.5)

        # 执行校准（base-ui 菜单点击可能被吞，按网络请求确认，最多重试 3 次）
        cal = None
        for attempt in range(3):
            c0 = H.req_len(d)
            H.open_row_menu(d, NAME)
            H.menu_click(d, '执行校准')
            try:
                H.WebDriverWait(d, 8, poll_frequency=0.25).until(lambda dd: any(
                    r['method'] == 'POST' and '/calibrate' in r['url'] for r in H.reqs_since(dd, c0)))
            except Exception:
                pass
            got = [r for r in H.reqs_since(d, c0) if r['method'] == 'POST' and '/calibrate' in r['url']]
            if got:
                cal = got[0]
                break
            time.sleep(1.0)
        check('校准 POST /spl/{id}/calibrate 发出且 <300',
              bool(cal) and cal['status'] < 300, cal or 'no request')
        EVID['network'] = {'calibrate': {k: cal[k] for k in ('method', 'url', 'status')}} if cal else {}
        time.sleep(2.5)
        H.search(d, NAME)
        check('校准后列表行显示已校准', '已校准' in H.row_for(d, NAME).text,
              H.row_for(d, NAME).text.replace('\n', ' | ')[:200])

        # 详情页渲染值
        open_detail(d)
        rows = H.read_points(d, 'spl-points-title')
        post_px = d.execute_script(CANVAS_ALPHA_PX)
        H.save(d, '11_after_calibration_light')
        EVID['page']['detail_rows'] = rows

        st_detail, raw = api_json(d, '/api/v1/spl/%s' % m_id)
        pts = ((raw.get('calibration_data') or {}).get('points')) or []
        EVID['api']['detail'] = {'status': st_detail, 'calibration_status': raw.get('calibration_status'),
                                 'points': pts}
        check('GET /spl/{id} 200 且已校准', st_detail == 200 and raw.get('calibration_status') == 'calibrated', st_detail)
        check('接口校准点 11 个', len(pts) == 11, len(pts))
        check('页面校准点行数与接口一致', len(rows) == len(pts), '%d vs %d' % (len(rows), len(pts)))

        # 逐行逐值比对（表头顺序：增益偏移/数字增益/基础电平/最终电平/实测 SPL）
        mism = []
        for idx, (row, p) in enumerate(zip(rows, pts)):
            g = p.get('gainOffset', p.get('gain'))
            spl = p.get('spl')
            exp = [
                '%s dB' % fmt(g),
                '%s dB' % fmt(p.get('digitalGain', g)),
                '%s dBFS' % fmt(p.get('baseLevel', -30)),
                '%s dBFS' % fmt(p.get('finalLevel', round(-30 + g, 2))),
                '%s dB' % fmt(spl),
            ]
            if [c.strip() for c in row] != exp:
                mism.append({'row': idx + 1, 'page': row, 'expected': exp})
        check('页面五行逐值与 GET /spl/{id} 一致', not mism, mism[:3])
        check('增益偏移 1~100 dB',
              [r[0] for r in rows] == ['1 dB', '10 dB', '20 dB', '30 dB', '40 dB', '50 dB',
                                       '60 dB', '70 dB', '80 dB', '90 dB', '100 dB'],
              [r[0] for r in rows])
        check('基础电平恒 -30 dBFS', all(r[2] == '-30 dBFS' for r in rows), [r[2] for r in rows][:3])
        check('最终电平 -29 → 70 dBFS', rows[0][3] == '-29 dBFS' and rows[-1][3] == '70 dBFS',
              [rows[0][3], rows[-1][3]] if rows else [])
        check('曲线画布像素较校准前显著增加（有真实数据）',
              isinstance(post_px, int) and isinstance(pre_px, int) and post_px > pre_px * 1.5,
              'pre=%s post=%s' % (pre_px, post_px))
        EVID['page']['canvas_alpha_px'] = {'before': pre_px, 'after': post_px}

        # 历史：接口 vs 页面展开行
        st_h, hist = api_json(d, '/api/v1/spl/%s/history' % m_id)
        items = hist.get('items') or []
        hpts = (((items[0] or {}).get('calibration_data') or {}).get('points')) or [] if items else []
        EVID['api']['history'] = {'status': st_h, 'item_count': len(items), 'first_points': hpts}
        check('GET /spl/{id}/history 200 有记录', st_h == 200 and len(items) > 0, '%s / %d' % (st_h, len(items)))

        H.js_click(d, H.find(d, "//div[@role='dialog']//button[normalize-space(.)='查看校准历史']"))
        time.sleep(2.0)
        heads = H.find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
        if heads:
            H.js_click(d, heads[0])
            time.sleep(0.8)
        hrows = [r for r in H.find_all(d, "//div[@role='dialog']//tbody/tr")]
        hcells = [[c.text.strip() for c in r.find_elements(H.By.XPATH, './td')] for r in hrows]
        EVID['page']['history_rows'] = hcells
        check('历史展开行数与接口点集一致', len(hcells) == len(hpts), '%d vs %d' % (len(hcells), len(hpts)))
        hm = []
        for idx, (row, p) in enumerate(zip(hcells, hpts)):
            g = p.get('gainOffset', p.get('gain'))
            exp = ['%s dB' % fmt(g), '%s dBFS' % fmt(p.get('baseLevel', -30)),
                   '%s dBFS' % fmt(p.get('finalLevel', round(-30 + g, 2))), '%s dB' % fmt(p.get('spl'))]
            if [c.strip() for c in row] != exp:
                hm.append({'row': idx + 1, 'page': row, 'expected': exp})
        check('历史四列逐值与接口一致', not hm if hcells else False, hm[:3])
        H.save(d, '12_history_light')
        H.close_dialog(d)
        H.close_dialog(d)
        time.sleep(0.5)

        # 深色
        H.open_page(d, dark=True)
        H.search(d, NAME)
        H.row_for(d, NAME)
        open_detail(d)
        drows = H.read_points(d, 'spl-points-title')
        check('深色详情逐值与浅色一致', drows == rows, drows[:2])
        H.save(d, '13_detail_dark')
        H.js_click(d, H.find(d, "//div[@role='dialog']//button[normalize-space(.)='查看校准历史']"))
        time.sleep(2.0)
        heads = H.find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
        if heads:
            H.js_click(d, heads[0])
            time.sleep(0.8)
        dh = [[c.text.strip() for c in r.find_elements(H.By.XPATH, './td')]
              for r in H.find_all(d, "//div[@role='dialog']//tbody/tr")]
        check('深色历史与浅色一致', dh == hcells, dh[:2])
        H.save(d, '14_history_dark')

        # 清理
        dele = d.execute_async_script(
            "var id=arguments[0],done=arguments[arguments.length-1];"
            "var t=window.localStorage.getItem('iatp:auth:token:v1');"
            "fetch('/api/v1/spl/'+id,{method:'DELETE',headers:t?{Authorization:'Bearer '+t}:{}})"
            ".then(function(r){return r.text().then(function(x){done({status:r.status});});})"
            ".catch(function(e){done({status:'ERR',body:String(e)});});", m_id)
        check('清理：删除本卡映射', dele.get('status', 999) < 300, dele)
    finally:
        with open(os.path.join(H.ART, 'evidence_values.json'), 'w', encoding='utf-8') as f:
            json.dump(EVID, f, ensure_ascii=False, indent=2)
        d.quit()
    fails = [c for c in EVID['checks'] if not c['ok']]
    log('\n== SUMMARY: %d checks, %d FAIL ==' % (len(EVID['checks']), len(fails)))
    for c in fails:
        log('FAIL: ' + c['name'] + ' | ' + c['detail'][:300])
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
