# -*- coding: utf-8 -*-
"""INT-1538 recon：登录后抓用例域基础数据与页面结构。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}


def j(path, method='GET', body=None):
    st, payload, raw = L.api_json(d, path, method, body)
    return {'status': st, 'len_raw': len(raw), 'json': payload}


d = L.driver()
try:
    url = L.login(d)
    OUT['login_url'] = url
    time.sleep(1)

    # 基础数据
    OUT['groups'] = j('/testcases/groups?page=1&page_size=200')
    OUT['testcases'] = j('/testcases?page=1&page_size=5')
    OUT['audios'] = j('/audios?page=1&page_size=5')
    OUT['dimensions'] = j('/dimensions?page=1&page_size=5')
    OUT['case_tags'] = j('/testcases/tags')

    # 页面结构
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    OUT['page_url'] = d.current_url
    OUT['page_text_head'] = L.body_text(d)[:3000]
    OUT['buttons'] = [b.text.strip() for b in d.find_elements(By.TAG_NAME, 'button') if b.text.strip()][:80]
    OUT['shots'] = [L.shot(d, 'recon_testcases')]
finally:
    L.save_evidence('recon', OUT)
    try:
        d.quit()
    except Exception:
        pass
