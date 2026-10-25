# -*- coding: utf-8 -*-
"""INT-1538 播放器夹具清理：软删 → purge → 删分组，并回读确认。

只处理本 run 自建的「接线测试_INT1538_」用例/分组，不碰真实行。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By

GROUP = '接线测试_INT1538_播放器复测组'
OUT = {}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


d = L.driver()
try:
    d.get(L.BASE + '/login')
    time.sleep(4)
    if '/login' in d.current_url:
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '进入' in (b.text or '') or '登录' in (b.text or ''):
                L.js_click(d, b)
                time.sleep(3)
                break
    # 1) 圈定本卡夹具
    st, body, raw = L.api_json(d, '/testcases?keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1538&page=1&page_size=50')
    st_del, body_del, _ = L.api_json(d, '/testcases?keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1538&only_deleted=1&page=1&page_size=50')
    items = (body or {}).get('data', {}).get('items', []) if body else []
    OUT['before_alive'] = [(i['id'], i['name']) for i in items]
    OUT['before_alive_total'] = (body or {}).get('data', {}).get('total') if body else None
    OUT['before_deleted_total'] = (body_del or {}).get('data', {}).get('total') if body_del else None
    ids = [i['id'] for i in items if 'INT1538' in (i.get('name') or '')]
    # 2) 软删 + purge
    OUT['ops'] = []
    for cid in ids:
        OUT['ops'].append(['DELETE', cid, L.api_json(d, '/testcases/' + cid, 'DELETE')[0]])
        time.sleep(0.5)
        OUT['ops'].append(['PURGE', cid, L.api_json(d, '/testcases/' + cid + '/purge', 'DELETE')[0]])
    # 3) 分组
    gs, gb, _ = L.api_json(d, '/groups?page=1&page_size=200')
    gitems = (gb or {}).get('data', {}).get('items', []) if gb else []
    OUT['groups_before'] = [(g.get('id'), g.get('name')) for g in gitems if 'INT1538' in (g.get('name') or '')]
    for g in gitems:
        if 'INT1538' in (g.get('name') or ''):
            OUT['ops'].append(['DELETE_GROUP', g['id'], L.api_json(d, '/groups/' + g['id'], 'DELETE')[0]])
    # 4) 回读
    time.sleep(2)
    st, body2, _ = L.api_json(d, '/testcases?keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1538&page=1&page_size=50')
    st2, body3, _ = L.api_json(d, '/testcases?keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1538&only_deleted=1&page=1&page_size=50')
    OUT['after_alive_total'] = (body2 or {}).get('data', {}).get('total') if body2 else None
    OUT['after_deleted_total'] = (body3 or {}).get('data', {}).get('total') if body3 else None
    gs2, gb2, _ = L.api_json(d, '/groups?page=1&page_size=200')
    OUT['groups_after'] = [g.get('name') for g in ((gb2 or {}).get('data', {}).get('items', []) if gb2 else [])
                           if 'INT1538' in (g.get('name') or '')]
finally:
    L.save_evidence('cleanup_evidence', OUT)
    with open(os.path.join(L.HERE, 'evidence_int1538_cleanup.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    try:
        d.quit()
    except Exception:
        pass
