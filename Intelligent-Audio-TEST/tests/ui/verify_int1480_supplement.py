# -*- coding: utf-8 -*-
"""INT-1480 补测：编辑保存回读（描述/备注区分）+ 告警规则列表在页面加载时真实 GET。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from verify_int1480_device_modals import (
    _driver, _goto, _body, _wait_text, _jsclick, _menu_item, _set_theme,
    _save_evidence, _net, _drain_perf, _api, _payload, _check, _row_action,
    _close_dialog, _press_esc, _PASS, _FAILURES, TEST, ARTIFACTS,
)


def main():
    drv = _driver()
    dev_id = None
    try:
        dname = TEST + '编辑核对'
        # 建
        st, resp = _api('/test-devices', 'POST', {
            'name': dname, 'model': 'INT1480-M', 'type': 'physical', 'system': 'Android',
            'system_version': '12', 'app_name': 'A', 'app_version': '1.0',
            'connection_type': 'usb', 'serial_number': 'INT1480SNX',
        })
        items = (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items', [])
        hit = [d for d in items if d['name'] == dname]
        dev_id = hit[0]['id'] if hit else None
        _check('准备：API 建设备', dev_id is not None, detail=f'id={dev_id}')

        # 页面加载时抓 alarm-rules GET（真实请求）
        _drain_perf(drv)
        _goto(drv, '/devices/test')
        _wait_text(drv, dname, 20)
        time.sleep(2.0)
        rules_net = _net(drv, '/test-devices/alarm-rules')
        _check('⑦ 页面加载即真实 GET /test-devices/alarm-rules 200',
               any((n.get('status') or 0) == 200 for n in rules_net), detail=f'{rules_net[:3]}')

        # 编辑 → 填描述（按 placeholder 精确定位）
        _jsclick(drv, _row_action(drv, dname))
        _jsclick(drv, _menu_item(drv, '编辑'))
        _wait_text(drv, '测试设备信息', 10)
        time.sleep(1.2)
        desc = drv.find_element(By.XPATH, "//textarea[@placeholder='设备用途或工位说明']")
        desc.clear()
        desc.send_keys(TEST + '描述A')
        remark = drv.find_element(By.XPATH, "//input[@placeholder='与基本信息「描述」独立']")
        remark.clear()
        remark.send_keys(TEST + '备注B')
        _drain_perf(drv)
        for b in drv.find_elements(By.XPATH, "//button[@type='submit'][contains(., '保存')]"):
            if b.is_displayed():
                _jsclick(drv, b)
                break
        time.sleep(3.0)
        items = (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items', [])
        got = [d for d in items if d['id'] == dev_id]
        _check('③ 编辑保存 → GET 回读描述更新',
               bool(got) and got[0].get('description') == TEST + '描述A',
               detail=f'desc={got[0].get("description") if got else None}')
        _check('③ 编辑保存 → GET 回读备注更新（描述/备注独立字段）',
               bool(got) and str(got[0].get('remark')) == TEST + '备注B',
               detail=f'remark={got[0].get("remark") if got else None}')
        put_net = [n for n in _net(drv, '/test-devices/') if n.get('method') == 'PUT']
        _check('③ Network: PUT /test-devices/{id} <300', any((n.get('status') or 0) < 300 for n in put_net),
               detail=f'{put_net[:2]}')
        _save_evidence('03f_edit_saved_light', drv)

        # 再回显核对
        _goto(drv, '/devices/test')
        _wait_text(drv, dname, 15)
        _jsclick(drv, _row_action(drv, dname))
        _jsclick(drv, _menu_item(drv, '编辑'))
        _wait_text(drv, '测试设备信息', 10)
        time.sleep(1.0)
        v = drv.find_element(By.XPATH, "//textarea[@placeholder='设备用途或工位说明']").get_attribute('value')
        _check('③ 重开编辑抽屉描述回显一致', v == TEST + '描述A', detail=f'value={v}')
        _save_evidence('03g_edit_reopen_light', drv)
        _close_dialog(drv)
    except Exception as e:
        _check('补测流程', False, repr(e))
        _save_evidence('03h_supplement_error', drv)
        _press_esc(drv)
    finally:
        if dev_id:
            st, _ = _api(f'/test-devices/{dev_id}', 'DELETE')
            print(f'cleanup device {dev_id} HTTP {st}', flush=True)
        for d in (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items', []):
            if str(d.get('name', '')).startswith(TEST):
                _api(f"/test-devices/{d['id']}", 'DELETE')
                print(f'  sweep {d["name"]}', flush=True)
        drv.quit()
    print(f'\nSUPPLEMENT PASS {len(_PASS)} FAIL {len(_FAILURES)}', flush=True)
    for f in _FAILURES:
        print(f'  FAIL: {f}', flush=True)


if __name__ == '__main__':
    main()
