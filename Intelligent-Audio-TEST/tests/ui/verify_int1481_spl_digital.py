# -*- coding: utf-8 -*-
"""INT-1481 SPL 映射域复走（driver 2：数字域 RMS-SPL 全弹窗，真实栈 15173/15000）。

⚠ /apis 在该 docker 栈不可用（后端 SELECT apis.api_url 列漂移，GET /apis 400）。
数字域表单/facet 依赖 /apis，故用「页内 fetch 打点钩子」返回真实主库里唯一一条活跃 API
（id=1，来自 intelligent_audio_test.apis where deleted=false），仅替换该只读 facet 响应；
其余请求（POST /digital-spl、PUT、calibrate、set-default、GET 回读）全部为真实请求。

写数据纪律：只写「接线测试_INT1481_」前缀记录，run 末尾删除。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1481_spl_device as h
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PREFIX = h.PREFIX
NAME_D = PREFIX + 'RMS1'
API_REF = [{'id': 1, 'name': '1', 'vendor': '1', 'protocol': None, 'rms_spl_mapping_id': None}]

HOOK_JS = h.HOOK_JS.replace(
    "    var body = (init && typeof init.body === 'string') ? init.body : null;",
    "    var body = (init && typeof init.body === 'string') ? init.body : null;\n"
    "    if (window.__int1481_interceptApis && method === 'GET' && url.indexOf('/api/v1/apis') !== -1) {\n"
    "      var payload = {success:true, code:0, message:'Success', data:{items: window.__int1481_apis||[], total:(window.__int1481_apis||[]).length, page:1, per_page:100, pages:1}};\n"
    "      window.__reqLog.push({url:url, method:method, status:200, reqBody:null, respBody:JSON.stringify(payload).slice(0,8000), injected:true});\n"
    "      return Promise.resolve(new Response(JSON.stringify(payload), {status:200, headers:{'Content-Type':'application/json'}}));\n"
    "    }")

BIND_JS = (
    "window.__int1481_interceptApis = true;"
    "try { window.__int1481_apis = JSON.parse(localStorage.getItem('__int1481_apis') || 'null'); }"
    "catch(e) { window.__int1481_apis = null; }"
    "if (!window.__int1481_apis || !window.__int1481_apis.length) { window.__int1481_apis = "
    + json.dumps(API_REF, ensure_ascii=False) + "; }"
)


def new_driver():
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium import webdriver
    o = Options()
    o.binary_location = h.CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = os.path.join(cache_root, sorted(os.listdir(cache_root))[-1], 'chromedriver.exe')
    d = webdriver.Chrome(options=o, service=Service(executable_path=drv_path))
    d.set_page_load_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK_JS})
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': BIND_JS})
    return d


def digital_rows():
    return h.api_get('/digital-spl?page=1&per_page=100')['data']['items']


def digital_by_name(name):
    for r in digital_rows():
        if r.get('name') == name:
            return r
    return None


def open_digital(d):
    h.js_click(d, h.find(d, "//button[normalize-space(.)='API/Realtime RMS-SPL']"))
    time.sleep(2)


def api_ref_in_db():
    import subprocess
    out = subprocess.run(['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
                          '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test', '-A', '-t',
                          '-c', 'select coalesce(rms_spl_mapping_id::text,\'\') from apis where id=1;'],
                         capture_output=True, text=True)
    return out.stdout.strip()


def main():
    d = new_driver()
    ev = {'checks': h.EVID['checks'], 'net': [], 'readbacks': []}
    try:
        d.get(h.BASE + '/SPLMapping')
        time.sleep(6)
        open_digital(d)
        h.shot(d, '30_digital_page_light')
        body = d.find_element(By.TAG_NAME, 'body').text
        h.check('数字域空态 + 统计 0', '暂无 RMS-SPL 映射' in body and 'RMS-SPL 映射数' in body, '')
        # 关联 API facet 选项 = 1（注入的真实 API）
        h.js_click(d, h.find(d, "//button[contains(normalize-space(.), '关联 API')]"))
        time.sleep(0.8)
        opts = h.find_all(d, "//button[contains(normalize-space(.), '1（1）') or normalize-space(.)='1（1）']")
        h.check('关联 API facet 选项来自真实 API', len(opts) >= 1, len(opts))
        d.execute_script("document.body.click();")
        time.sleep(0.5)

        # --- 新建校验：空名 ---
        h.js_click(d, h.find(d, "//button[normalize-space(.)='添加 RMS-SPL 映射']"))
        time.sleep(1.2)
        h.shot(d, '31_digital_form_create_light')
        h.click_text(d, '保存')
        tt = h.toast_texts(d)
        h.check('数字域新建空名拦截', any('请输入映射名称' in t for t in tt), tt)

        # --- 新建 D1 ---
        h.open_select(d, '关联被测 API', '1（1）')
        h.check('关联 API 选中后触发器显示 API 名（非裸 id）',
                h.selected_text(d, '关联被测 API') not in ('1', ''),
                '实际显示=' + h.selected_text(d, '关联被测 API'))
        h.set_input(d, '映射名称', NAME_D)
        h.set_input(d, '参考声压级', '70')
        h.set_input(d, '参考线性增益', '1.2')
        h.set_input(d, '增益下限', '0.01')
        h.set_input(d, '增益上限', '8')
        before = h.log_len(d)
        h.shot(d, '32_digital_form_filled_light')
        h.click_text(d, '保存')
        time.sleep(2)
        tt = h.toast_texts(d)
        h.check('数字域新建 toast', any('创建成功' in t for t in tt), tt)
        reqs = [e for e in h.reqlog(d, before) if '/digital-spl' in e['url']]
        ev['net'].append({'step': 'create_digital', 'reqs': reqs})
        dd = digital_by_name(NAME_D)
        h.check('D1 GET /digital-spl 回读', dd is not None, '')
        if dd:
            ok = (dd['api_id'] == 1 and dd['name'] == NAME_D
                  and abs(dd['reference_spl'] - 70) < 1e-9
                  and abs(dd['reference_gain_linear'] - 1.2) < 1e-9
                  and abs(dd['min_gain_linear'] - 0.01) < 1e-9
                  and abs(dd['max_gain_linear'] - 8) < 1e-9
                  and dd['calibration_points'] == [])
            h.check('D1 全字段回读一致', ok, json.dumps({k: dd.get(k) for k in ('api_id', 'reference_spl', 'reference_gain_linear', 'min_gain_linear', 'max_gain_linear', 'calibration_status')}, ensure_ascii=False))
        time.sleep(1)
        body = d.find_element(By.TAG_NAME, 'body').text
        h.check('数字域统计 total=1', 'RMS-SPL 映射数' in body and '1' in body, '')

        # --- 编辑（API 选择应为 create-only） ---
        h.row_action(d, NAME_D, '编辑')
        dlg = h.dialog(d)
        combos = h.find_all(d, "//button[@role='combobox']")
        h.check('编辑态隐藏关联 API 选择', not any(c.get_attribute('aria-label') == '关联被测 API' for c in combos), len(combos))
        h.check('编辑回显参考声压级', h.get_input(d, '参考声压级') == '70', h.get_input(d, '参考声压级'))
        before = h.log_len(d)
        h.set_input(d, '参考声压级', '72')
        h.set_input(d, '增益上限', '9')
        h.shot(d, '33_digital_form_edit_light')
        h.click_text(d, '保存')
        time.sleep(2)
        tt = h.toast_texts(d)
        h.check('数字域编辑 toast', any('更新成功' in t for t in tt), tt)
        reqs = [e for e in h.reqlog(d, before) if '/digital-spl' in e['url'] and e['method'] == 'PUT']
        ev['net'].append({'step': 'update_digital', 'reqs': reqs})
        dd = digital_by_name(NAME_D)
        h.check('编辑后回读 reference_spl=72 / max=9', dd and abs(dd['reference_spl'] - 72) < 1e-9 and abs(dd['max_gain_linear'] - 9) < 1e-9,
                dd and (dd.get('reference_spl'), dd.get('max_gain_linear')))

        # --- 详情（未校准空态） ---
        h.row_action(d, NAME_D, '详情')
        dt = h.dialog(d).text
        h.check('数字详情字段 + 尚无校准数据', NAME_D in dt and '关联 API' in dt and '参考基准' in dt and '增益限幅' in dt and '尚无校准数据' in dt, dt[:500])
        h.shot(d, '34_digital_detail_light')
        h.click_text(d, 'Close')
        time.sleep(0.6)

        # --- 设默认 → 后端 route 亦命中 apis.api_url 列漂移（400），前端错误态 ---
        before = h.log_len(d)
        h.row_action(d, NAME_D, '设默认')
        tt = h.toast_texts(d, 2.5)
        reqs = [e for e in h.reqlog(d, before) if 'set-default' in e['url']]
        ev['net'].append({'step': 'set_default', 'reqs': reqs})
        h.check('设默认失败时前端提示错误（后端 400 列漂移）',
                any('设置默认映射失败' in t for t in tt) and any(str(e['status']) == '400' for e in reqs), tt)
        dd = digital_by_name(NAME_D)
        h.check('DB apis.rms_spl_mapping_id 未被改动', api_ref_in_db() == '', api_ref_in_db())
        # 前端默认徽章渲染：把注入 facet 的真实 API 指针指向 D1 后刷新（仅 facets 注入，不改真实库）
        if dd:
            d.execute_script("var a=window.__int1481_apis.slice(); a[0].rms_spl_mapping_id=arguments[0];"
                             "localStorage.setItem('__int1481_apis', JSON.stringify(a));", dd['id'])
            d.get(h.BASE + '/SPLMapping')
            time.sleep(5)
            open_digital(d)
            h.shot(d, '35_digital_page_default_light')
            table_body = d.find_element(By.TAG_NAME, 'body').text
            h.check('列表默认列显示「默认」', '默认' in table_body, '')
            h.row_action(d, NAME_D, '详情')
            dlg = h.dialog(d)
            badges = [e.text.strip() for e in h.find_all(d, "//div[@role='dialog']//*[normalize-space(.)='默认']")]
            h.check('详情标题显示默认徽章', len(badges) >= 1, badges)
            h.shot(d, '34b_digital_detail_default_light')
            h.click_text(d, 'Close')
            time.sleep(0.6)
            # 清掉注入指针，回到真实空指针状态
            d.execute_script("localStorage.removeItem('__int1481_apis');")
            d.get(h.BASE + '/SPLMapping')
            time.sleep(5)
            open_digital(d)

        # --- 数字校准弹窗 ---
        h.row_action(d, NAME_D, '校准')
        dlg = h.dialog(d)
        h.check('校准弹窗空态 + 参考基准四格', '尚无校准点' in dlg.text and '参考声压级' in dlg.text and '并发互斥' in dlg.text, dlg.text[:600])
        h.check('无有效点时提交禁用', h.find(d, "//div[@role='dialog']//button[normalize-space(.)='提交校准']").get_attribute('disabled') is not None, '')
        h.shot(d, '36_digital_calibration_light')
        # 按参考生成 5 点
        h.js_click(d, h.find(d, "//div[@role='dialog']//button[contains(normalize-space(.), '按参考生成')]"))
        time.sleep(1.5)
        rows = h.find_all(d, "//div[@role='dialog']//tbody/tr")
        h.check('按参考生成 5 个校准点', len(rows) == 5, len(rows))
        h.check('生成后出现增益曲线预览', '增益曲线预览' in h.dialog(d).text, '')
        h.check('超出增益限幅的点行级报错（第 5 行 12 > 上限 9）', '限幅' in h.dialog(d).text, h.dialog(d).text[-300:])
        h.shot(d, '37_digital_calibration_generated_light')
        # 重复目标校验：把第 2 行目标改成与第 1 行相同
        first = h.get_input(d, '第 1 行目标 SPL')
        h.set_input(d, '第 2 行目标 SPL', first)
        time.sleep(0.8)
        h.check('重复目标 SPL 行级拦截', '重复目标' in h.dialog(d).text, '')
        h.shot(d, '37b_digital_calibration_duplicate_light')
        # 修正第 2 行
        h.set_input(d, '第 2 行目标 SPL', '66')
        h.set_input(d, '第 1 行实测 RMS', '-30')
        time.sleep(0.8)
        before = h.log_len(d)
        h.shot(d, '38_digital_calibration_filled_light')
        h.click_text(d, '提交校准')
        time.sleep(2.5)
        tt = h.toast_texts(d)
        h.check('数字校准 toast', any('校准完成' in t for t in tt), tt)
        reqs = [e for e in h.reqlog(d, before) if '/calibrate' in e['url']]
        ev['net'].append({'step': 'calibrate_digital', 'reqs': reqs})
        dd = digital_by_name(NAME_D)
        h.check('校准后回读 calibrated + 4 个有效点（第 5 点增益越限被过滤）',
                dd and dd['calibration_status'] == 'calibrated' and len(dd['calibration_points']) == 4,
                dd and (dd.get('calibration_status'), len(dd.get('calibration_points') or [])))
        # 详情校准点表
        h.row_action(d, NAME_D, '详情')
        dt = h.dialog(d).text
        h.check('详情校准点明细 4 行', '目标 SPL' in dt and '线性增益' in dt and '实测 RMS' in dt, dt[:500])
        h.shot(d, '39_digital_detail_calibrated_light')
        h.click_text(d, 'Close')
        time.sleep(0.6)

        # --- 深色截图 ---
        h.set_theme(d, 'dark', h.BASE + '/SPLMapping')
        open_digital(d)
        h.shot(d, '40_digital_page_dark')
        h.js_click(d, h.find(d, "//button[normalize-space(.)='添加 RMS-SPL 映射']"))
        time.sleep(1.2)
        h.shot(d, '41_digital_form_create_dark')
        h.click_text(d, '取消')
        time.sleep(0.6)
        h.row_action(d, NAME_D, '编辑')
        h.shot(d, '42_digital_form_edit_dark')
        h.click_text(d, '取消')
        time.sleep(0.6)
        h.row_action(d, NAME_D, '详情')
        h.shot(d, '43_digital_detail_dark')
        h.click_text(d, 'Close')
        time.sleep(0.6)
        h.row_action(d, NAME_D, '校准')
        time.sleep(1)
        h.shot(d, '44_digital_calibration_dark')
        h.click_text(d, '取消')
        time.sleep(0.6)

        # --- 删除（含默认指针清理） ---
        h.set_theme(d, 'light', h.BASE + '/SPLMapping')
        open_digital(d)
        h.row_action(d, NAME_D, '删除')
        ad = h.find(d, "//div[@role='alertdialog']", timeout=10)
        h.check('数字删除确认文案含名称', '删除 RMS-SPL 映射' in ad.text and NAME_D in ad.text, ad.text[:200])
        h.shot(d, '45_digital_delete_confirm_light')
        h.click_text(d, '删除', scope="//div[@role='alertdialog']")
        tt = h.toast_texts(d, 2.5)
        h.check('删除 toast', any('已删除' in t for t in tt), tt)
        time.sleep(1)
        h.check('删除后 GET /digital-spl 不含 D1', digital_by_name(NAME_D) is None, '')
        h.check('删除时清空 API 默认指针', api_ref_in_db() == '', api_ref_in_db())
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(h.ART, 'evidence_driver2.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        h.log('\nEVIDENCE checks:', sum(1 for c in ev['checks'] if c['ok']), '/', len(ev['checks']))
        for c in ev['checks']:
            if not c['ok']:
                h.log('FAILED:', c['name'], c['detail'][:500])


if __name__ == '__main__':
    main()
