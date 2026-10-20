# -*- coding: utf-8 -*-
"""INT-1072 步骤2 执行模式控件 DOM 状态核验（补证：串行/串行优先侧出现与选中）。"""
import json
import os
import time
import psycopg2
from selenium import webdriver

BASE = 'http://127.0.0.1:5405'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
DB = dict(host='localhost', port=5432, dbname='intelligent_audio_test_test',
          user='intelligent_audio_test', password='intelligent_audio_test666')


def seed():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("UPDATE devices SET status='online', deleted=FALSE, deleted_at=NULL WHERE id=147")
    cur.execute("UPDATE apis SET status='online', deleted=FALSE, deleted_at=NULL WHERE id=314")
    conn.commit(); conn.close()


def wait_for(d, fn, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def js(d, script, *args):
    return d.execute_script(script, *args)


def shot(d, name, scroll_to='.execution-params-panel'):
    d.execute_script("const el=document.querySelector(arguments[0]); if(el) el.scrollIntoView({block:'start'});", scroll_to)
    time.sleep(0.6)
    d.save_screenshot(os.path.join(OUT, name))
    print('saved', name)


def main():
    seed()
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new'); opts.add_argument('--window-size=1440,900')
    opts.add_argument('--no-sandbox'); opts.add_argument('--disable-gpu'); opts.add_argument('--disable-dev-shm-usage')
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1440, 900)
    try:
        d.get(BASE + '/#/E2ETest')
        wait_for(d, lambda: js(d, "return !!document.querySelector('#test-step0.active') && document.querySelectorAll('.algorithm-card').length>0"))
        js(d, "const el=document.querySelector('#algo-voice_llm'); if(el) el.click();"); time.sleep(0.5)
        js(d, "document.querySelector('#test-step0 .step-actions .btn-primary').click();")
        wait_for(d, lambda: js(d, "return !!document.querySelector('#test-step1.active') && document.querySelectorAll('.group-checkbox').length>0"))
        js(d, "document.querySelectorAll('.group-checkbox')[0].click();"); time.sleep(0.4)
        js(d, "document.querySelector('#test-step1 .step-actions .btn-primary').click();")
        wait_for(d, lambda: js(d, "return !!document.querySelector('#test-step2.active') && document.querySelectorAll('.resource-section').length>=2"))
        time.sleep(1.2)

        # 未混选：执行模式置灰
        notmixed = js(d, "return [...document.querySelectorAll('.execution-params-panel input[type=radio]')].every(x=>x.disabled)")
        print('not-mixed radios disabled:', notmixed)
        shot(d, 'step2_notmixed_disabled.png')

        # 勾选设备 + API
        def click_card(sub):
            return js(d,
                "const cards=[...document.querySelectorAll('#test-step2 .resource-card')];"
                "const hits=cards.filter(c=>{const nm=c.querySelector('.card-name');return nm&&nm.textContent.includes(arguments[0]);});"
                "const hit=hits.find(c=>{const cb=c.querySelector('.resource-checkbox');return cb&&!cb.disabled;})||hits[0];"
                "if(!hit)return false;const cb=hit.querySelector('.resource-checkbox');"
                "if(cb&&!cb.checked&&!cb.disabled){cb.click();return 'clicked';}return cb&&cb.checked?'already':'blocked';", sub)
        print('device click:', click_card('INT1072_online_device'))
        time.sleep(0.4)
        print('api click:', click_card('INT1072_api'))
        wait_for(d, lambda: js(d, "return document.querySelectorAll('#test-step2 .resource-card.selected').length>=2"))
        time.sleep(0.6)
        print('selected:', js(d, "return document.querySelectorAll('#test-step2 .resource-card.selected').length"))

        # 混选默认并行
        st = js(d, "return [...document.querySelectorAll('.execution-params-panel input[type=radio]')].map(r=>({v:r.value,checked:r.checked,disabled:r.disabled}))")
        print('radios after mixed:', st)
        shot(d, 'step2_mixed_grid_selected.png', scroll_to='.resource-section')
        shot(d, 'step2_mixed_default_parallel.png')

        # 切串行 → 串行优先侧出现
        js(d, "const r=document.querySelector('.execution-params-panel input[type=radio][value=\"serial\"]'); if(r&&!r.disabled) r.click();")
        time.sleep(0.8)
        serial_visible = js(d, "return !!document.querySelector('.param-group') && [...document.querySelectorAll('.param-group .param-label')].some(e=>e.textContent.includes('串行优先侧'))")
        st2 = js(d, "return [...document.querySelectorAll('.execution-params-panel input[type=radio]')].map(r=>({v:r.value,checked:r.checked,disabled:r.disabled}))")
        print('serial clicked, serial-first visible:', serial_visible)
        print('radios after serial:', st2)
        shot(d, 'step2_mixed_serial_device_first.png')

        # 切 API 先
        js(d, "const r=document.querySelector('.execution-params-panel input[type=radio][value=\"api\"]'); if(r&&!r.disabled) r.click();")
        time.sleep(0.8)
        st3 = js(d, "return [...document.querySelectorAll('.execution-params-panel input[type=radio]')].map(r=>({v:r.value,checked:r.checked,disabled:r.disabled}))")
        print('radios after api-first:', st3)
        shot(d, 'step2_mixed_serial_api_first.png')

        # 深色
        js(d, "document.documentElement.classList.add('dark')")
        time.sleep(0.8)
        shot(d, 'step2_mixed_serial_api_first_dark.png')
        js(d, "document.documentElement.classList.remove('dark')")
    finally:
        d.quit()


if __name__ == '__main__':
    main()
