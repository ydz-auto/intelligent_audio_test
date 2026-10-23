# -*- coding: utf-8 -*-
"""INT-1477：回收站链路 UI 取证（软删 → 回收站可见 → 恢复 → 彻底删除）。"""
import os, sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1477_crud_batch as M

NAME = '接线测试_INT1477_回收站'
d = M.driver()
try:
    d.get(M.BASE + '/'); time.sleep(2)
    # 建一条（API，前置创建路径已由 UI 验证）
    hits = M.list_cases(d, NAME)
    if not hits:
        r = M.api(d, 'POST', '/api/v1/testcases', {
            'name': NAME, 'description': '回收站链路取证',
            'group': M.GROUP, 'tags': [M.TAG], 'algorithm_type': None,
            'config': {'rounds': [{'round_number': 1, 'audios': [], 'evaluation': {'enabled': True, 'dimensions': []}}]},
            'algorithm_params': []})
        M.log('  create', r['status'], str(r['json'])[:100])
    hits = M.list_cases(d, NAME)
    cid = hits[0]['id']
    M.log('  id', cid)
    # 软删
    r = M.api(d, 'DELETE', f'/api/v1/testcases/{cid}')
    M.log('  soft-delete', r['status'])
    # 回收站 UI
    M.reload_page(d)
    M.clear_log(d)
    M.click_text(d, '回收站', 'button', timeout=10); time.sleep(3)
    M.shot(d, 'crud_trash_view')
    body = d.find_element(By.TAG_NAME, 'body').text
    M.log('  trash has name:', NAME in body)
    M.rec('case-trash-view', '回收站视图含软删用例', M.calls(d), {'has_target': NAME in body})
    # 尝试展开并恢复
    try:
        hdrs = [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{M.GROUP}']") if e.is_displayed()]
        if hdrs:
            M.jsclick(d, hdrs[0]); time.sleep(2)
        M.clear_log(d)
        btn = d.find_element(By.XPATH, "//button[aria-label='恢复' or normalize-space(.)='恢复']")
        M.jsclick(d, btn); time.sleep(3)
        M.shot(d, 'crud_trash_restore')
        M.rec('case-trash-restore', '回收站恢复', M.calls(d))
        M.log('  after restore exists:', bool(M.list_cases(d, NAME)))
    except Exception as e:
        M.log('  restore UI fail:', e)
        M.rec('case-trash-restore', '恢复入口未命中 ' + str(e), [])
finally:
    d.quit()
# 清理
d = M.driver()
try:
    d.get(M.BASE + '/'); time.sleep(2)
    hits = M.list_cases(d, NAME)
    if hits:
        cid = hits[0]['id']
        if not hits[0].get('is_deleted'):
            M.api(d, 'DELETE', f'/api/v1/testcases/{cid}')
        r = M.api(d, 'POST', '/api/v1/testcases/purge', {'ids': [cid]})
        M.log('  purge', r['status'], str(r['json'])[:120])
    M.log('  LEFT', bool(M.list_cases(d, NAME)))
finally:
    d.quit()
