# -*- coding: utf-8 -*-
"""INT-1488 实时日志收新日志截图取证（合成 task_log 插顶可见）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1488_common import *  # noqa: F403
from int1488_common import _driver

import redis
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

REDIS_URL = os.environ.get('INT1488_REDIS_URL', 'redis://localhost:16379')


def main():
    os.makedirs(ART, exist_ok=True)
    env_check('realtime_shot')
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        uname = WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'username')))
        uname.send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url or '欢迎' in body(d))
        time.sleep(2)
        drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, 'light'))
        drv.get(BASE + '/logs')
        WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
        time.sleep(1.5)
        sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
        js_click(drv, sw)
        wait_text(drv, 'WS实时', 30)
        time.sleep(1)

        marker = 'INT1488_WS_EVIDENCE_%d' % int(time.time())
        rc = redis.from_url(REDIS_URL)
        rc.publish('task_events', json.dumps({
            'event_type': 'task_log',
            'payload': {'task_id': None, 'log_payload': {
                'id': 995000000 + int(time.time()) % 1000000,
                'time': '2026-10-23 19:58:00', 'level': 'WARNING', 'module': 'run_all',
                'content': marker, 'mark': '', 'task_id': None,
                'test_case_id': None, 'category': 'test', 'source': 'run_all'}}}, ensure_ascii=False))
        rc.close()
        deadline = time.time() + 40
        top_text = ''
        while time.time() < deadline:
            trs = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
            top_text = trs[0].text if trs else ''
            if marker in body(drv):
                break
            time.sleep(1)
        # 把表格滚到顶部，确保新日志行在可视区
        try:
            drv.execute_script("const el=document.querySelector('tbody'); if(el){el.scrollIntoView({block:'start'})}")
        except Exception:
            pass
        time.sleep(0.6)
        shot(drv, 'light_24_ws_marker_row.png')
        out = {'marker': marker, 'top_row_text': top_text[:200],
               'body_contains_marker': marker in body(drv),
               'monitor_bar': [t for t in ['WS实时', '实时监控中', '条/秒'] if t in body(drv)]}
        log(json.dumps(out, ensure_ascii=False))
        # 关闭实时
        sw = drv.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]')
        js_click(drv, sw)
        time.sleep(0.8)
        env_check('realtime_shot_end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
