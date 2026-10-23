# -*- coding: utf-8 -*-
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By
from verify_int1480_device_modals import (_driver,_goto,_body,_wait_text,_jsclick,_menu_item,_api,_payload,_check,_row_action,_close_dialog,_save_evidence,_PASS,_FAILURES,TEST)

drv=_driver(); did=None
try:
    dname=TEST+'编辑核对'
    _api('/test-devices','POST',{'name':dname,'model':'INT1480-M','type':'physical','system':'Android','system_version':'12','app_name':'A','app_version':'1.0','connection_type':'usb','serial_number':'INT1480SNX'})
    items=(_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items',[])
    hit=[d for d in items if d['name']==dname]; did=hit[0]['id'] if hit else None
    _goto(drv,'/devices/test'); _wait_text(drv,dname,20)
    _jsclick(drv,_row_action(drv,dname)); _jsclick(drv,_menu_item(drv,'编辑'))
    _wait_text(drv,'测试设备信息',10); time.sleep(1.5)
    print('TEXTAREAS:', [(t.get_attribute('placeholder'), t.is_displayed()) for t in drv.find_elements(By.XPATH,'//textarea')], flush=True)
    m=[e for e in drv.find_elements(By.XPATH,"//input[@name='model']") if e.is_displayed()]
    print('MODEL VALUE:', m[0].get_attribute('value') if m else None, flush=True)
    m[0].clear(); m[0].send_keys('INT1480-M2')
    ta=[t for t in drv.find_elements(By.XPATH,"//textarea[@placeholder='设备用途或工位说明']")]
    if ta:
        ta[0].clear(); ta[0].send_keys(TEST+'描述A')
    for b in drv.find_elements(By.XPATH,"//button[@type='submit'][contains(., '保存')]"):
        if b.is_displayed(): _jsclick(drv,b); break
    time.sleep(3.0)
    got=[d for d in (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items',[]) if d['id']==did]
    _check('③ 编辑保存 → GET 回读 model 更新', bool(got) and got[0].get('model')=='INT1480-M2', detail=f'model={got[0].get("model") if got else None}')
    _check('③ 编辑保存 → GET 回读 description 更新', bool(got) and got[0].get('description')==TEST+'描述A', detail=f'desc={got[0].get("description") if got else None}')
    _save_evidence('03f_edit_saved_light',drv)
finally:
    if did:
        print('cleanup', _api(f'/test-devices/{did}','DELETE')[0], flush=True)
    for d in (_payload(_api('/test-devices?page=1&per_page=100')[1]) or {}).get('items',[]):
        if str(d.get('name','')).startswith(TEST): _api(f"/test-devices/{d['id']}",'DELETE')
    drv.quit()
print('PASS',len(_PASS),'FAIL',len(_FAILURES),flush=True)
for f in _FAILURES: print(' FAIL:',f,flush=True)
