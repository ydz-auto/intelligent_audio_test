# -*- coding: utf-8 -*-
"""INT-1481 附加取证：测试音按钮无真实请求（mock 残留）+ 物理域搜索不含关联设备名。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1481_spl_device as h
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def main():
    d = h.new_driver()
    ev = {'checks': h.EVID['checks'], 'net': []}
    try:
        d.get(h.BASE + '/SPLMapping')
        time.sleep(6)
        # --- 测试音按钮：点第 1 行播放，观察 2.5s 内是否发出 /spl/test-tone ---
        h.js_click(d, h.find(d, "//button[normalize-space(.)='添加增益映射']"))
        time.sleep(1.2)
        before = h.log_len(d)
        play = h.find(d, "//button[@aria-label='第 1 行播放测试音']")
        h.js_click(d, play)
        time.sleep(0.6)
        playing = h.find(d, "//button[@aria-label='第 1 行播放测试音']")
        h.shot(d, '50_test_tone_playing_light')
        time.sleep(2.2)
        after = h.reqlog(d, before)
        reqs = [e for e in after if 'test-tone' in e['url']]
        ev['net'].append({'step': 'test_tone', 'reqs': after})
        h.check('测试音播放发出真实 POST /spl/test-tone', len(reqs) > 0,
                [(e['method'], e['status'], e['url']) for e in after])
        # 停止按钮
        before2 = h.log_len(d)
        h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
        time.sleep(0.8)
        stop_reqs = [e for e in h.reqlog(d, before2) if 'test-tone/stop' in e['url']]
        h.check('再次点击停止发出 POST /spl/test-tone/stop', len(stop_reqs) > 0, [(e['method'], e['status'], e['url']) for e in h.reqlog(d, before2)])
        h.click_text(d, '取消')
        time.sleep(0.8)

        # --- 搜索关联设备名（V9.7.10 支持；React 仅名称/描述） ---
        data = h.api_get('/spl?page=1&per_page=1000')['data']['items']
        target = None
        for r in data:
            dn = r.get('device_name') or ''
            if dn and dn not in (r.get('name') or ''):
                target = r
                break
        h.check('真实库存在「设备名不在映射名内」的记录', target is not None, target and (target['name'], target.get('device_name')))
        if target:
            h.search(d, target['device_name'])
            time.sleep(1)
            names = h.row_names(d)
            empty = '未找到匹配的映射' in d.find_element(By.TAG_NAME, 'body').text
            h.check('按关联设备名搜索可命中（V9.7.10 行为）', target['name'] in names or not empty,
                    {'device_name': target['device_name'], 'rows': names, 'empty_state': empty})
            h.shot(d, '51_search_device_name_light')
            h.clear_search(d)

        # --- 导入映射数据 禁用态 + tooltip ---
        btn = h.find(d, "//button[normalize-space(.)='导入映射数据']")
        h.check('导入映射数据按钮禁用（后端无 import 路由）', btn.get_attribute('disabled') is not None, '')
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(d).move_to_element(btn).pause(1.0).perform()
        time.sleep(1)
        body = d.find_element(By.TAG_NAME, 'body').text
        h.shot(d, '52_import_disabled_light')
        h.check('导入禁用提示「映射导入后端建设中」', '映射导入后端建设中' in body, '')
    finally:
        d.quit()
        with open(os.path.join(h.ART, 'evidence_extra.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        h.log('EVIDENCE checks:', sum(1 for c in ev['checks'] if c['ok']), '/', len(ev['checks']))
        for c in ev['checks']:
            if not c['ok']:
                h.log('FAILED:', c['name'], c['detail'][:500])


if __name__ == '__main__':
    main()
