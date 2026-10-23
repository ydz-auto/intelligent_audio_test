# -*- coding: utf-8 -*-
"""INT-1481 复走复测（第二轮）：只复测修复卡 INT-1501 / 1502 / 1503 / 1504 对应的失败项。

环境：docker 真实栈 前端 15173（iat-react-frontend:latest，含 wiring/react 修复）/ 后端 15000 /
真实库 intelligent_audio_test（AUTH_MODE=off）。
证据：每项 浅/深 截图 + 真实请求/响应（页内 fetch 打点）+ GET / DB 回读。
写数据纪律：只写「接线测试_INT1481R2_」前缀记录，脚本末尾删除 + 硬删清理。
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1481_spl_device as h
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PREFIX = '接线测试_INT1481R2_'
TS = str(int(time.time()))[-6:]
NAME_P = PREFIX + '校准' + TS      # 物理域：用于 INT-1503 校准点
NAME_D = PREFIX + 'RMS' + TS       # 数字域：用于 INT-1504 时间字段 + 设默认
API = h.API
BASE = h.BASE

EV = {'checks': h.EVID['checks'], 'net': [], 'readbacks': [], 'env': {}}


# ---------------------------------------------------------------- helpers

def tap_theme(d, dark=False):
    h.set_theme(d, 'dark' if dark else 'light', BASE + '/SPLMapping')
    h.wait_rows(d)


def open_create(d):
    h.js_click(d, h.find(d, "//button[normalize-space(.)='添加增益映射']"))
    time.sleep(1.2)


def open_digital(d):
    h.js_click(d, h.find(d, "//button[normalize-space(.)='API/Realtime RMS-SPL']"))
    time.sleep(2.5)


def hover(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(d).move_to_element(el).perform()
    time.sleep(1.2)


def clear_search(d):
    el = h.find(d, "//input[@aria-label='搜索映射']")
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    time.sleep(1.2)


def tooltip_texts(d):
    return [e.text.strip() for e in h.find_all(d, "//*[@data-slot='tooltip-content']") if e.text.strip()]


def digital_rows():
    return h.api_get('/digital-spl?page=1&per_page=100')['data']['items']


def digital_by_name(name):
    for r in digital_rows():
        if r.get('name') == name:
            return r
    return None


def psql(sql):
    out = subprocess.run(
        ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
         '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test', '-A', '-t', '-c', sql],
        capture_output=True, text=True)
    return (out.stdout or '').strip()


def table_cells(d, scope="//div[@role='dialog']//table//tbody/tr"):
    rows = []
    for tr in h.find_all(d, scope):
        rows.append([td.text.strip() for td in tr.find_elements(By.TAG_NAME, 'td')])
    return rows


def stub_test_tone_success(d):
    """仅桩掉 POST /spl/test-tone（播放）成功返回，用于验证播放态与 /stop 真实请求；
    停止请求不桩，走真实后端。"""
    d.execute_script(r"""
      if (!window.__int1481r2_stub) {
        window.__int1481r2_stub = true;
        var orig = window.fetch.bind(window);
        window.fetch = function(input, init){
          var url = (typeof input === 'string') ? input : (input && input.url) || '';
          var method = ((init && init.method) || 'GET').toUpperCase();
          if (method === 'POST' && /\/api\/v1\/spl\/test-tone$/.test(url)) {
            var body = (init && typeof init.body === 'string') ? init.body : null;
            return new Promise(function(resolve){
              setTimeout(function(){
                window.__reqLog.push({url:url, method:method, status:200, reqBody:body,
                                      respBody:'{"success":true,"code":0,"message":"stub ok"}', injected:true});
                resolve(new Response('{"success":true,"code":0,"message":"stub ok"}',
                          {status:200, headers:{'Content-Type':'application/json'}}));
              }, 200);
            });
          }
          return orig(input, init);
        };
      }
    """)


# ---------------------------------------------------------------- INT-1501

def part_1501(d):
    h.log('\n=== INT-1501：Select 标签 / 设备名搜索 / 导入 tooltip ===')
    tap_theme(d, False)
    open_create(d)

    # 1) 设备类型默认显示中文标签（非裸值 dry）
    dt = h.selected_text(d, '设备类型')
    h.check('1501 设备类型闭合态显示中文「干声」', dt == '干声', '实际=' + dt)

    # 2) 关联播放设备选中后显示设备名（非 device_id=6）
    h.open_select(d, '关联播放设备', '设备正右侧（1m+90°）')
    dv = h.selected_text(d, '关联播放设备')
    h.check('1501 关联播放设备闭合态显示设备名', ('设备正右侧' in dv) and dv not in ('6', ''),
            '实际=' + dv)
    h.shot(d, '50_int1501_form_select_light')
    # 切换设备类型，确认非裸值 noise
    h.open_select(d, '设备类型', '噪声')
    dt2 = h.selected_text(d, '设备类型')
    h.check('1501 设备类型改选后显示「噪声」', dt2 == '噪声', '实际=' + dt2)
    h.click_text(d, '取消')
    time.sleep(0.8)

    # 3) 搜索含关联设备名（「设备正右侧」只存在于设备名，映射名无此词）
    h.wait_rows(d)
    base_rows = h.row_names(d)
    h.search(d, '设备正右侧')
    time.sleep(1)
    hits = h.row_names(d)
    h.check('1501 按设备名搜索命中关联该设备的映射',
            len(hits) == 1 and '设备正左斜侧' in hits[0] and len(base_rows) == 3,
            'hits=%s base=%s' % (hits, base_rows))
    h.shot(d, '51_int1501_search_by_device_light')
    clear_search(d)
    time.sleep(1)
    h.check('1501 清空搜索恢复 3 行', len(h.row_names(d)) == 3, h.row_names(d))

    # 4) 导入禁用按钮 tooltip 可达（触发器是可悬停 span）
    span = h.find(d, "//span[contains(@class,'cursor-not-allowed')]")
    hover(d, span)
    tips = tooltip_texts(d)
    h.check('1501 导入按钮 tooltip 可见', any('映射导入后端建设中' in t for t in tips), tips)
    h.shot(d, '52_int1501_import_tooltip_light')

    # 5) 深色
    tap_theme(d, True)
    open_create(d)
    h.open_select(d, '关联播放设备', '设备正右侧（1m+90°）')
    h.shot(d, '53_int1501_form_select_dark')
    dv = h.selected_text(d, '关联播放设备')
    h.check('1501 深色下播放设备仍显示设备名', '设备正右侧' in dv, dv)
    h.click_text(d, '取消')
    time.sleep(0.8)
    h.wait_rows(d)
    h.search(d, '设备正右侧')
    time.sleep(1)
    h.shot(d, '54_int1501_search_by_device_dark')
    clear_search(d)
    span = h.find(d, "//span[contains(@class,'cursor-not-allowed')]")
    hover(d, span)
    h.shot(d, '55_int1501_import_tooltip_dark')
    h.check('1501 深色 tooltip 可见', any('映射导入后端建设中' in t for t in tooltip_texts(d)),
            tooltip_texts(d))


# ---------------------------------------------------------------- INT-1502

def part_1502(d):
    h.log('\n=== INT-1502：测试音真实 POST /spl/test-tone（+ /stop） ===')
    tap_theme(d, False)
    open_create(d)
    h.set_input(d, '映射名称', PREFIX + '测试音')
    h.open_select(d, '关联播放设备', '设备正面（0.5m+0°）')
    h.set_input(d, '第 1 行增益偏移', '-12')
    h.set_input(d, '第 1 行实测 SPL', '57')
    time.sleep(0.5)

    # 真实请求：后端当前缺 test.wav → 400，重点是「确实发出了真实请求」而非 2s 假动作
    before = h.log_len(d)
    h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
    time.sleep(2.5)
    reqs = [e for e in h.reqlog(d, before) if '/spl/test-tone' in e['url']]
    EV['net'].append({'step': '1502_test_tone_real', 'reqs': reqs})
    play = [e for e in reqs if e['method'] == 'POST' and e['url'].rstrip('/').endswith('/spl/test-tone')]
    h.check('1502 点播放真实下发 POST /spl/test-tone', len(play) == 1,
            [(e['method'], e['url'], e['status'], e['reqBody']) for e in reqs])
    if play:
        body = json.loads(play[0]['reqBody'] or '{}')
        h.check('1502 请求体含 gain_offset/gain_value/target_spl/unique_id',
                body.get('gain_offset') == -12 and body.get('gain_value') is not None
                and body.get('target_spl') is not None and bool(body.get('unique_id')),
                body)
        h.check('1502 请求前先 GET 播放设备解析 device_unique_id',
                any('/playback-devices/5' in e['url'] for e in h.reqlog(d, before)),
                [e['url'] for e in h.reqlog(d, before) if '/playback-devices' in e['url']])
        # 环境缺口：后端缺 test.wav → 400，前端如实报错
        tt = h.toast_texts(d, 1)
        h.check('1502 播放失败（环境缺 test.wav）前端如实提示错误',
                str(play[0]['status']) == '400' and any('测试音' in t or '音频' in t or '失败' in t for t in tt),
                {'status': play[0]['status'], 'toast': tt})
    h.shot(d, '56_int1502_tone_request_light')

    # 成功态旁路：仅桩播放 200，验证进入播放态 + 停止下发真实 POST /spl/test-tone/stop
    stub_test_tone_success(d)
    before = h.log_len(d)
    h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
    time.sleep(2)
    pressed = h.find(d, "//button[@aria-label='第 1 行播放测试音']").get_attribute('aria-pressed')
    h.check('1502 播放成功后按钮进入播放态（aria-pressed=true）', pressed == 'true', pressed)
    h.shot(d, '57_int1502_playing_stub_light')
    before_stop = h.log_len(d)
    h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
    time.sleep(2)
    stops = [e for e in h.reqlog(d, before_stop) if '/spl/test-tone/stop' in e['url']]
    EV['net'].append({'step': '1502_test_tone_stop', 'reqs': stops})
    h.check('1502 停止真实下发 POST /spl/test-tone/stop',
            len(stops) == 1 and stops[0]['method'] == 'POST', stops)
    h.check('1502 停止请求成功（200）', bool(stops) and str(stops[0]['status']) == '200',
            stops and stops[0]['status'])
    pressed = h.find(d, "//button[@aria-label='第 1 行播放测试音']").get_attribute('aria-pressed')
    h.check('1502 停止后退出播放态', pressed == 'false', pressed)
    h.shot(d, '58_int1502_stopped_light')
    h.click_text(d, '取消')
    time.sleep(0.8)


# ---------------------------------------------------------------- INT-1503

def part_1503(d):
    h.log('\n=== INT-1503：校准后详情/历史增益列与曲线 ===')
    tap_theme(d, False)
    h.wait_rows(d)
    open_create(d)
    h.set_input(d, '映射名称', NAME_P)
    h.open_select(d, '关联播放设备', '设备正面（0.5m+0°）')
    h.set_input(d, '测量距离', '1.2')
    h.set_input(d, '目标声压级', '70')
    h.set_input(d, '测试频率', '2000')
    h.click_text(d, '保存')
    tt = h.toast_texts(d, 2)
    h.check('1503 新建物理映射', any('创建成功' in t for t in tt), tt)
    h.wait_rows(d)
    p = h.spl_by_name(NAME_P)
    h.check('1503 新建后 GET 回读', p is not None, '')
    # 执行校准（后端写入 calibration_data.points，键为 gain）
    h.row_action(d, NAME_P, '执行校准')
    tt = h.toast_texts(d, 2.5)
    h.check('1503 执行校准 toast', any('校准完成' in t for t in tt), tt)
    p = h.spl_by_name(NAME_P)
    pts = ((p or {}).get('calibration_data') or {}).get('points') or []
    h.check('1503 后端点集键为 gain（复现根因数据）',
            bool(pts) and all('gain' in pt for pt in pts) and not any('gainOffset' in pt for pt in pts),
            pts[:3])
    gains = [pt.get('gain') for pt in pts]
    EV['readbacks'].append({'step': '1503_points', 'id': (p or {}).get('id'), 'points': pts})

    # 详情：增益偏移/数字增益列逐点有值 = 后端 gain
    h.row_action(d, NAME_P, '详情')
    dlg = h.dialog(d)
    cells = table_cells(d)
    h.check('1503 详情点表行数 = 后端点数', len(cells) == len(pts), (len(cells), len(pts)))
    col0 = [r[0] for r in cells if r]

    def nums(texts):
        out = []
        for c in texts:
            try:
                out.append(float(c.replace(' dB', '').strip()))
            except Exception:
                out.append(None)
        return out
    h.check('1503 详情「增益偏移」列无 — 且逐值等于后端 gain',
            all(c not in ('', '—') for c in col0) and nums(col0) == [float(g) for g in gains],
            {'ui': col0, 'api': gains})
    svg = [e for e in h.find_all(d, "//div[@role='dialog']//*[local-name()='svg']")]
    h.check('1503 详情校准曲线已渲染（svg 存在且含路径）',
            bool(svg) and any(e.find_elements(By.CSS_SELECTOR, 'path,circle') for e in svg),
            len(svg))
    h.shot(d, '59_int1503_detail_calibrated_light')

    # 历史
    h.click_text(d, '查看校准历史')
    time.sleep(2)
    h.check('1503 校准历史有记录', '个校准点' in h.dialog(d).text, h.dialog(d).text[:200])
    exp = h.find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
    if exp:
        h.js_click(d, exp[0])
        time.sleep(1)
    hcells = table_cells(d)
    hcol0 = [r[0] for r in hcells if r]
    h.check('1503 历史「增益偏移」列无 — 且逐值等于后端 gain',
            bool(hcol0) and all(c not in ('', '—') for c in hcol0)
            and nums(hcol0) == [float(g) for g in gains],
            {'ui': hcol0, 'api': gains})
    h.shot(d, '60_int1503_history_expanded_light')
    h.click_text(d, 'Close')
    time.sleep(0.8)

    # 深色
    tap_theme(d, True)
    h.wait_rows(d)
    h.row_action(d, NAME_P, '详情')
    h.shot(d, '61_int1503_detail_calibrated_dark')
    h.click_text(d, '查看校准历史')
    time.sleep(1.5)
    exp = h.find_all(d, "//div[@role='dialog']//button[@aria-expanded='false']")
    if exp:
        h.js_click(d, exp[0])
        time.sleep(0.8)
    h.shot(d, '62_int1503_history_expanded_dark')
    h.check('1503 深色历史增益列有值',
            all(c not in ('', '—') for c in [r[0] for r in table_cells(d) if r]), table_cells(d)[:2])
    h.click_text(d, 'Close')
    time.sleep(0.8)


# ---------------------------------------------------------------- INT-1504

def part_1504(d):
    h.log('\n=== INT-1504：GET /apis 200 / digital-spl 时间字段 / 设默认 ===')
    apis = h.api_get('/apis?page=1&per_page=100')
    EV['readbacks'].append({'step': '1504_apis', 'total': apis['data'].get('total'),
                            'first': apis['data']['items'][0] if apis['data']['items'] else None})
    h.check('1504 GET /apis 200 且有数据',
            isinstance(apis.get('data'), dict) and len(apis['data'].get('items') or []) >= 1,
            {'total': apis['data'].get('total')})

    tap_theme(d, False)
    open_digital(d)
    h.shot(d, '63_int1504_digital_page_light')
    h.js_click(d, h.find(d, "//button[normalize-space(.)='添加 RMS-SPL 映射']"))
    time.sleep(1.2)
    # 关联被测 API 下拉来自真实 /apis
    trig = h.find(d, "//button[@role='combobox' and @aria-label='关联被测 API']")
    h.js_click(d, trig)
    time.sleep(0.8)
    opts = [e.text.strip() for e in h.find_all(d, "//*[@role='option']")]
    h.check('1504 关联被测 API 下拉来自真实接口（≥1 项）', len(opts) >= 1, opts)
    h.shot(d, '64_int1504_digital_api_select_light')
    h.open_select(d, '关联被测 API', '1（1）')
    api_label = h.selected_text(d, '关联被测 API')
    h.check('1504 关联被测 API 闭合态显示名称（非裸 id）', api_label not in ('1', ''), api_label)
    h.set_input(d, '映射名称', NAME_D)
    h.set_input(d, '参考声压级', '70')
    h.set_input(d, '参考线性增益', '1.2')
    h.set_input(d, '增益下限', '0.01')
    h.set_input(d, '增益上限', '8')
    before = h.log_len(d)
    h.click_text(d, '保存')
    time.sleep(2)
    tt = h.toast_texts(d)
    h.check('1504 数字域新建成功', any('创建成功' in t for t in tt), tt)
    reqs = [e for e in h.reqlog(d, before) if '/digital-spl' in e['url']]
    EV['net'].append({'step': '1504_create_digital', 'reqs': reqs})
    dd = digital_by_name(NAME_D)
    h.check('1504 数字域 GET 回读', dd is not None, '')
    h.check('1504 读模型返回 created_at/updated_at',
            bool(dd) and bool(dd.get('created_at')) and bool(dd.get('updated_at')),
            dd and (dd.get('created_at'), dd.get('updated_at')))
    EV['readbacks'].append({'step': '1504_digital', 'id': (dd or {}).get('id'),
                            'created_at': (dd or {}).get('created_at'),
                            'updated_at': (dd or {}).get('updated_at')})
    time.sleep(1)
    h.row_action(d, NAME_D, '详情')
    dt = h.dialog(d).text
    import re as _re
    mt = _re.search(r'创建时间\s*(\S+)', dt)
    mu = _re.search(r'更新时间\s*(\S+)', dt)
    date_ok = bool(mt and mu and _re.search(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', mt.group(1))
                   and _re.search(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', mu.group(1)))
    h.check('1504 详情显示创建/更新时间（非 —）', date_ok,
            {'created': mt.group(1) if mt else None, 'updated': mu.group(1) if mu else None})
    h.shot(d, '65_int1504_digital_detail_light')
    h.click_text(d, 'Close')
    time.sleep(0.8)

    # 设默认 → 真实 200 + DB 指针
    before = h.log_len(d)
    h.row_action(d, NAME_D, '设默认')
    tt = h.toast_texts(d, 2.5)
    reqs = [e for e in h.reqlog(d, before) if 'set-default' in e['url']]
    EV['net'].append({'step': '1504_set_default', 'reqs': reqs})
    h.check('1504 设默认请求 200', bool(reqs) and str(reqs[0]['status']) == '200',
            reqs and (reqs[0]['method'], reqs[0]['status'], reqs[0]['url']))
    ptr = psql('select coalesce(rms_spl_mapping_id::text,\'\') from apis where id=1;')
    h.check('1504 DB apis.rms_spl_mapping_id 指向新映射',
            bool(dd) and ptr == str(dd['id']), {'db': ptr, 'mapping': (dd or {}).get('id')})
    h.shot(d, '66_int1504_set_default_light')

    # 深色
    tap_theme(d, True)
    open_digital(d)
    h.shot(d, '67_int1504_digital_page_dark')
    h.row_action(d, NAME_D, '详情')
    h.shot(d, '68_int1504_digital_detail_dark')
    h.click_text(d, 'Close')
    time.sleep(0.8)
    tap_theme(d, False)


# ---------------------------------------------------------------- cleanup

def cleanup(d):
    h.log('\n=== 清理 ===')
    info = {'spl': [], 'digital': [], 'api_pointer': ''}
    p = h.spl_by_name(NAME_P)
    if p:
        try:
            h.api_delete('/spl/%d' % p['id'])
            info['spl'].append(p['id'])
        except Exception as e:
            h.log('delete spl fail', e)
    dd = digital_by_name(NAME_D)
    if dd:
        # 先清默认指针再删
        try:
            import urllib.request
            req = urllib.request.Request(
                API + '/digital-spl/by-api/%s/set-default' % dd.get('api_id', 1),
                data=json.dumps({'mapping_id': None}).encode(),
                headers={'Content-Type': 'application/json'}, method='POST')
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:
            h.log('clear default fail', e)
        try:
            h.api_delete('/digital-spl/%d' % dd['id'])
            info['digital'].append(dd['id'])
        except Exception as e:
            h.log('delete digital fail', e)
    # 硬删（后端 DELETE 为软删）
    ids = info['spl']
    if ids:
        psql('delete from spl_mappings where id in (%s);' % ','.join(str(i) for i in ids))
        psql('delete from calibration_history where spl_mapping_id in (%s);' % ','.join(str(i) for i in ids))
    d_ids = info['digital']
    if d_ids:
        psql('delete from api_rms_spl_mappings where id in (%s);' % ','.join(str(i) for i in d_ids))
    info['api_pointer'] = psql('select coalesce(rms_spl_mapping_id::text,\'\') from apis where id=1;')
    left = psql("select count(*) from spl_mappings where name like '接线测试_INT1481R2_%';")
    dleft = psql("select count(*) from api_rms_spl_mappings where name like '接线测试_INT1481R2_%';")
    h.check('清理：本卡物理/数字映射残留均为 0', left == '0' and dleft == '0',
            {'spl_left': left, 'digital_left': dleft, 'pointers_cleared': info['api_pointer']})
    EV['cleanup'] = info


def main():
    d = h.new_driver()
    try:
        d.get(BASE + '/SPLMapping')
        time.sleep(6)
        part_1501(d)
        part_1502(d)
        part_1503(d)
        part_1504(d)
    finally:
        try:
            cleanup(d)
        except Exception as e:
            h.log('cleanup error', e)
        try:
            d.quit()
        except Exception:
            pass
        os.makedirs(h.ART, exist_ok=True)
        with open(os.path.join(h.ART, 'evidence_retest.json'), 'w', encoding='utf-8') as f:
            json.dump(EV, f, ensure_ascii=False, indent=2)
        h.log('\nEVIDENCE checks: %d / %d' % (
            sum(1 for c in EV['checks'] if c['ok']), len(EV['checks'])))
        for c in EV['checks']:
            if not c['ok']:
                h.log('FAILED:', c['name'], str(c['detail'])[:500])


if __name__ == '__main__':
    main()
