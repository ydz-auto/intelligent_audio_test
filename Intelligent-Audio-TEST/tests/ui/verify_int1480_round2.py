# -*- coding: utf-8 -*-
"""INT-1480 第二轮：补齐 ③ 新增/编辑、② 分组删除、⑦ 告警规则、⑤ 操作弹窗可达性。

修复点：RHF name 属性选择器、switch 为 span[role=switch]、确认弹窗动画后 JS 点击重试。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from verify_int1480_device_modals import (
    _driver, _goto, _body, _wait_text, _wait_gone, _jsclick, _menu_item, _open_more,
    _press_esc, _close_dialog, _set_theme, _save_evidence, _net, _drain_perf, _api, _payload,
    _check, _row_action, _PASS, _FAILURES, TEST, ARTIFACTS,
)

SWITCH_ALARM = "//*[@role='switch' and @aria-label='监控告警面板']"


def _confirm_click(drv, label='删除', wait_gone_selector=None, timeout=10):
    """确认弹窗：等动画 → JS 点击 → 未关闭则重试一次。"""
    time.sleep(1.2)
    for attempt in range(3):
        btns = drv.find_elements(By.XPATH, f"//*[@role='alertdialog']//button[contains(., '{label}')]")
        if not btns:
            btns = [b for b in drv.find_elements(By.XPATH, f"//button[contains(., '{label}')]")
                    if b.is_displayed()]
        clicked = False
        for b in btns:
            if b.is_displayed():
                try:
                    _jsclick(drv, b)
                    clicked = True
                    break
                except Exception:
                    continue
        if not clicked:
            break
        if wait_gone_selector is None:
            time.sleep(1.5)
            return True
        try:
            WebDriverWait(drv, 4).until(
                lambda d: not d.find_elements(By.XPATH, wait_gone_selector))
            return True
        except Exception:
            time.sleep(1.0)
    return False


def main():
    drv = _driver()
    try:
        # ---- 0. 清理上一轮残留（分组） ----
        st, g = _api('/test-devices/device-groups')
        for grp in (_payload(g) or {}).get('items', []):
            if str(grp.get('name', '')).startswith(TEST):
                _api(f"/test-devices/device-groups/{grp['id']}?cascade=true", 'DELETE')
                print(f'  cleanup group {grp["name"]}', flush=True)
        for d in (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items', []):
            if str(d.get('name', '')).startswith(TEST):
                _api(f"/test-devices/{d['id']}", 'DELETE')
                print(f'  cleanup device {d["name"]}', flush=True)

        dname = TEST + '设备'
        created_id = None
        drill = None

        # ---- ① 新增抽屉：填全部必填 ----
        _goto(drv, '/devices/test')
        _wait_text(drv, '设备管理', 20)
        for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
            if b.is_displayed():
                _jsclick(drv, b)
                break
        _wait_text(drv, '测试设备信息', 10)
        time.sleep(1)

        def fill(name_attr, value):
            els = drv.find_elements(By.XPATH, f"//input[@name='{name_attr}']")
            for el in els:
                if el.is_displayed():
                    el.clear()
                    el.send_keys(value)
                    return True
            return False

        ok = all([
            fill('name', dname),
            fill('model', 'INT1480-MODEL'),
            fill('systemVersion', '12'),
            fill('appName', 'INT1480App'),
            fill('appVersion', '1.2.3'),
            fill('serialNumber', 'INT1480SN001'),
        ])
        _check('③ 新增抽屉必填字段全部可填（name/model/systemVersion/appName/appVersion/serialNumber）', ok)
        _drain_perf(drv)
        for b in drv.find_elements(By.XPATH, "//button[@type='submit'][contains(., '保存')]"):
            if b.is_displayed():
                _jsclick(drv, b)
                break
        time.sleep(3.0)
        st, lst = _api('/test-devices?page=1&per_page=100')
        items = (_payload(lst) or {}).get('items', [])
        created = [d for d in items if d['name'] == dname]
        _check('③ 新建后 GET 回读命中', len(created) == 1, detail=f'{len(created)}')
        net_post = [n for n in _net(drv, '/test-devices') if n.get('method') == 'POST']
        _check('③ Network: POST /test-devices <300', any((n.get('status') or 0) < 300 for n in net_post),
               detail=f'{net_post[:2]}')
        if created:
            c = created[0]
            created_id = c['id']
            _check('③ GET 回读字段一致（model/serial/appName/systemVersion）',
                   c.get('model') == 'INT1480-MODEL' and c.get('serial_number') == 'INT1480SN001'
                   and str(c.get('app_name')) == 'INT1480App' and str(c.get('system_version')) == '12',
                   detail=json.dumps({k: c.get(k) for k in ('model', 'serial_number', 'app_name', 'system_version')},
                                     ensure_ascii=False))
        _goto(drv, '/devices/test')
        _wait_text(drv, dname, 15)
        _save_evidence('03b_mutate_created_light', drv)

        # ---- ② 编辑回显 + 保存 ----
        if created_id:
            _drain_perf(drv)
            _jsclick(drv, _row_action(drv, dname))
            _jsclick(drv, _menu_item(drv, '编辑'))
            _wait_text(drv, '测试设备信息', 10)
            time.sleep(1.2)
            vals = {}
            for nm in ('name', 'model', 'appName'):
                els = [e for e in drv.find_elements(By.XPATH, f"//input[@name='{nm}']") if e.is_displayed()]
                vals[nm] = els[0].get_attribute('value') if els else None
            _check('③ 编辑抽屉回显（name/model/appName）',
                   vals.get('name') == dname and vals.get('model') == 'INT1480-MODEL'
                   and vals.get('appName') == 'INT1480App', detail=str(vals))
            _save_evidence('03c_mutate_edit_light', drv)
            ta = [e for e in drv.find_elements(By.XPATH, "//textarea") if e.is_displayed()]
            if ta:
                ta[0].clear()
                ta[0].send_keys(TEST + '改后描述')
            for b in drv.find_elements(By.XPATH, "//button[@type='submit'][contains(., '保存')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(3.0)
            st, one = _api('/test-devices?page=1&per_page=100')
            got = [d for d in (_payload(one) or {}).get('items', []) if d['id'] == created_id]
            _check('③ 编辑保存 → GET 回读描述更新',
                   bool(got) and got[0].get('description') == TEST + '改后描述',
                   detail=f'desc={got[0].get("description") if got else None}')
            net_put = [n for n in _net(drv, '/test-devices/') if n.get('method') == 'PUT']
            _check('③ Network: PUT /test-devices/{id} <300',
                   any((n.get('status') or 0) < 300 for n in net_put), detail=f'{net_put[:2]}')

            # ---- ④ 详情（自建设备）浅色 ----
            _goto(drv, '/devices/test')
            _wait_text(drv, dname, 15)
            _jsclick(drv, _row_action(drv, dname))
            _jsclick(drv, _menu_item(drv, '详情'))
            _wait_text(drv, '测试设备详情', 10)
            time.sleep(1.2)
            dt = _body(drv)
            _check('④ 详情字段与 GET 一致（名称/型号/序列号）',
                   dname in dt and 'INT1480-MODEL' in dt and 'INT1480SN001' in dt)
            _save_evidence('04c_detail_created_light', drv)
            _close_dialog(drv)

            # ---- ⑤ 行菜单：安装/卸载在离线设备禁用；删除同样禁用 ----
            _goto(drv, '/devices/test')
            _wait_text(drv, dname, 15)
            _jsclick(drv, _row_action(drv, dname))
            time.sleep(0.8)
            menu = {}
            for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
                if it.is_displayed():
                    menu[it.text.strip()] = it.get_attribute('data-disabled') or it.get_attribute('aria-disabled')
            _check('⑤ 离线设备「安装应用/卸载应用」菜单项禁用',
                   bool(menu.get('安装应用')) and bool(menu.get('卸载应用')), detail=str(menu))
            _check('⑤ 离线设备「删除」菜单项禁用（新建离线设备 UI 无删除路径）', bool(menu.get('删除')),
                   detail=f'删除 disabled={menu.get("删除")}')
            _save_evidence('05c_row_menu_offline_disabled', drv)
            _press_esc(drv)
            # 删除走 API 清理（UI 不可达）
            st, _ = _api(f'/test-devices/{created_id}', 'DELETE')
            _check('③ 删除（API，UI 按钮禁用）→ <300', 0 < st < 300, detail=f'HTTP {st}')
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 15)
            _check('③ 删除后列表不再出现', dname not in _body(drv))
            created_id = None

        # ---- ② 分组删除（重试点击） ----
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            _open_more(drv)
            _jsclick(drv, _menu_item(drv, '分组管理'))
            _wait_text(drv, '设备分组管理', 10)
            time.sleep(1)
            gname = TEST + '组'
            inp = drv.find_element(By.ID, 'group-name')
            inp.clear()
            inp.send_keys(gname)
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '创建')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            WebDriverWait(drv, 10).until(
                lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {gname}']"))
            _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {gname}']"))
            _jsclick(drv, _menu_item(drv, '删除'))
            _wait_text(drv, '删除分组', 8)
            ok_del = _confirm_click(
                drv, '删除', f"//button[@aria-label='分组操作 {gname}']", timeout=12)
            _check('② 删除分组确认后条目消失（动画后点击重试生效）', ok_del)
            st, g2 = _api('/test-devices/device-groups')
            names = [x['name'] for x in (_payload(g2) or {}).get('items', [])]
            _check('② 删除 → GET 回读无残留', gname not in names, detail=f'{names}')
            _save_evidence('02b_group_after_delete_light', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('② 分组删除复测', False, repr(e))
            _save_evidence('02_group_delete_error', drv)
            _press_esc(drv)

        # ---- ⑦ 告警规则（正确 switch 选择器） ----
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            _jsclick(drv, drv.find_element(By.XPATH, SWITCH_ALARM))
            time.sleep(2.0)
            _check('⑦ 监控告警面板展开（switch 开启）',
                   drv.find_element(By.XPATH, SWITCH_ALARM).get_attribute('aria-checked') == 'true')
            _drain_perf(drv)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '告警规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '监控告警规则', 10)
            time.sleep(1.2)
            _check('⑦ 告警规则弹窗打开', '监控告警规则' in _body(drv))
            st, rules = _api('/test-devices/alarm-rules?page=1&per_page=100')
            ritems = (_payload(rules) or {}).get('items', [])
            net_r = _net(drv, '/test-devices/alarm-rules')
            _check('⑦ Network: GET /test-devices/alarm-rules 200（真实列表）',
                   any((n.get('status') or 0) == 200 for n in net_r),
                   detail=f'后端规则 {len(ritems)} 条')
            rule_name = TEST + '规则'
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '新建规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '创建规则', 8)
            time.sleep(0.8)
            ni = drv.find_element(By.ID, 'rule-name')
            ni.clear()
            ni.send_keys(rule_name)
            nums = [i for i in drv.find_elements(By.XPATH, "//*[@role='dialog']//input[@type='number']")
                    if i.is_displayed()]
            if nums:
                nums[0].clear()
                nums[0].send_keys('80')
            _drain_perf(drv)
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '创建规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(3.0)
            st, r2 = _api('/test-devices/alarm-rules?page=1&per_page=100')
            r2items = (_payload(r2) or {}).get('items', [])
            r2names = [r.get('name') for r in r2items]
            _check('⑦ 新建规则 → GET 回读命中', rule_name in r2names, detail=f'{r2names}')
            net_rp = [n for n in _net(drv, '/test-devices/alarm-rules') if n.get('method') == 'POST']
            _check('⑦ Network: POST /test-devices/alarm-rules <300',
                   any((n.get('status') or 0) < 300 for n in net_rp), detail=f'{net_rp[:2]}')
            _save_evidence('07c_alarm_rule_created_light', drv)
            if rule_name in r2names:
                _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除规则 {rule_name}']"))
                _wait_text(drv, '删除告警规则', 8)
                ok = _confirm_click(drv, '删除', None, timeout=8)
                time.sleep(2.0)
                st, r3 = _api('/test-devices/alarm-rules?page=1&per_page=100')
                r3names = [r.get('name') for r in (_payload(r3) or {}).get('items', [])]
                _check('⑦ 删除规则 → GET 回读已消失', rule_name not in r3names, detail=f'{r3names}')
            _close_dialog(drv)
        except Exception as e:
            _check('⑦ 告警规则复测', False, repr(e))
            _save_evidence('07_alarm_rule_error2', drv)
            _press_esc(drv)

        # ---- ⑦ 深色 ----
        try:
            _set_theme(drv, 'dark')
            _wait_text(drv, '设备管理', 20)
            _jsclick(drv, drv.find_element(By.XPATH, SWITCH_ALARM))
            time.sleep(2.0)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '告警规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '监控告警规则', 10)
            time.sleep(1.2)
            _check('⑦b 深色告警规则弹窗无崩溃', '监控告警规则' in _body(drv))
            _save_evidence('07b_alarm_rule_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('⑦b 告警规则深色', False, repr(e))
            _press_esc(drv)
        _set_theme(drv, 'light')

        # ---- ⑤ 深色抽屉（新建态） ----
        try:
            _set_theme(drv, 'dark')
            _wait_text(drv, '设备管理', 20)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '测试设备信息', 10)
            time.sleep(1)
            _check('⑤b 深色新增抽屉无崩溃', all(m not in _body(drv) for m in ['糟糕！出错了', '页面加载失败']))
            _save_evidence('03e_mutate_drawer_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('⑤b 深色抽屉', False, repr(e))
            _press_esc(drv)
        _set_theme(drv, 'light')

    finally:
        # 清理
        for d in (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items', []):
            if str(d.get('name', '')).startswith(TEST):
                _api(f"/test-devices/{d['id']}", 'DELETE')
                print(f'  final cleanup device {d["name"]}', flush=True)
        for grp in (_payload(_api('/test-devices/device-groups')[1]) or {}).get('items', []):
            if str(grp.get('name', '')).startswith(TEST):
                _api(f"/test-devices/device-groups/{grp['id']}?cascade=true", 'DELETE')
                print(f'  final cleanup group {grp["name"]}', flush=True)
        for r in (_payload(_api('/test-devices/alarm-rules?page=1&per_page=100')[1]) or {}).get('items', []):
            if str(r.get('name', '')).startswith(TEST):
                _api(f"/test-devices/alarm-rules/{r['id']}", 'DELETE')
                print(f'  final cleanup rule {r["name"]}', flush=True)
        drv.quit()

    print(f'\nROUND2 PASS {len(_PASS)} FAIL {len(_FAILURES)}', flush=True)
    for f in _FAILURES:
        print(f'  FAIL: {f}', flush=True)


if __name__ == '__main__':
    os.makedirs(ARTIFACTS, exist_ok=True)
    main()
