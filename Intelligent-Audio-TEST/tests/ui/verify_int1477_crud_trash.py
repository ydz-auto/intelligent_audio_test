# -*- coding: utf-8 -*-
"""INT-1477：批量删除 → 回收站恢复 → 彻底删除 → 清理自建数据。"""
import os, sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1477_crud_batch as M

d = M.driver()
try:
    M.reload_page(d)
    M.expand_group(d, M.current_group(d))
    picked = M.select_cases(d, M.NAMES)
    M.log('picked', picked)
    M.clear_log(d)
    # 批量删除（工具栏）
    M.click_text(d, '批量删除', 'button', timeout=10)
    time.sleep(1.5)
    M.shot(d, 'crud_trash_confirm')
    # ConfirmDialog 确认钮文案是「删除」
    M.click_text(d, '删除', 'button', timeout=10)
    time.sleep(3.5)
    cs = M.calls(d)
    M.shot(d, 'crud_trash_done')
    M.rec('case-bulk-delete', f'批量删除 {picked}', cs)
    # 回收站
    M.clear_log(d)
    M.click_text(d, '回收站', 'button', timeout=10)
    time.sleep(3.5)
    M.shot(d, 'crud_trash_view')
    cs2 = M.calls(d)
    body = d.find_element(By.TAG_NAME, 'body').text
    M.rec('case-trash-view', '回收站视图（删除后）', cs2,
          {'has_A': M.NAMES[0] in body, 'has_B': M.NAMES[1] in body})
    # 恢复 A
    M.clear_log(d)
    try:
        M.click_text(d, '恢复', 'button', timeout=8)
        time.sleep(3.5)
        cs3 = M.calls(d)
        M.shot(d, 'crud_trash_restore')
        M.rec('case-trash-restore', '回收站恢复第一个用例', cs3)
    except Exception as e:
        M.log('  restore fail', e); M.rec('case-trash-restore', '恢复失败 ' + str(e), [])
    # 回列表确认恢复
    M.log('  readback after restore:', json.dumps(
        {n: bool(M.list_cases(d, n)) for n in M.NAMES}, ensure_ascii=False))
finally:
    d.quit()

# 兜底清理：API 软删 + purge 本 run 全部自建用例
d = M.driver()
try:
    d.get(M.BASE + '/'); time.sleep(2)
    for n in M.NAMES:
        hits = M.list_cases(d, n)
        if not hits:
            M.log('  gone', n); continue
        cid = hits[0]['id']
        if not hits[0].get('is_deleted'):
            r = M.api(d, 'DELETE', f'/api/v1/testcases/{cid}')
            M.log('  soft-del', n, r['status'])
        r = M.api(d, 'POST', '/api/v1/testcases/purge', {'ids': [cid]})
        M.log('  purge', n, r['status'], str(r['json'])[:120])
    # 最终核对
    left = [n for n in M.NAMES if M.list_cases(d, n)]
    M.log('  LEFT', left)
finally:
    d.quit()
