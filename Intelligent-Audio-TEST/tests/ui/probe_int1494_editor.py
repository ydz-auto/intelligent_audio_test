# -*- coding: utf-8 -*-
"""INT-1494 探针：消息操作组按钮与编辑态 DOM（定位编辑器不打开的原因）。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from int1494_helpers import BASE, body_text, driver, goto, js_click, set_theme

PROVIDER_ID = 'p-int1494'


def main():
    d = driver()
    out = {}
    try:
        set_theme(d, 'light')
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        d.execute_script("""
            ['iatp:ai-chat:v1:config','iatp:ai-chat:v1:messages','iatp:ai-chat:v1:providers']
              .forEach(function(k){localStorage.removeItem(k);});
            localStorage.setItem('iatp:ai-chat:v1:providers', JSON.stringify({version:1,data:[{
              id:'p-int1494', name:'接线测试_LLM供应商', baseUrl:'http://127.0.0.1:18899/v1',
              apiKey:'sk-int1494-test', models:['stub-model-a'], isDefault:true}]}));
            localStorage.setItem('iatp:ai-chat:v1:config', JSON.stringify({version:1,data:{
              providerId:'p-int1494', modelId:'stub-model-a'}}));
        """)
        goto(d, '/ai-chat', wait_text='开始与灵犀Agent对话')
        time.sleep(2)
        ta = d.find_element(By.CSS_SELECTOR, "textarea[placeholder^='描述你的报告需求']")
        ta.send_keys('接线测试_PROBE_消息')
        ta.send_keys(Keys.ENTER)
        time.sleep(4)
        msgs = d.find_elements(By.CSS_SELECTOR, 'div.group.flex-row-reverse')
        out['containers'] = []
        for m in msgs:
            out['containers'].append({
                'text': (m.text or '')[:80],
                'displayed': m.is_displayed(),
                'aria': [x.get_attribute('aria-label') for x in
                         m.find_elements(By.CSS_SELECTOR, '[aria-label]')],
                'buttons': [(b.text or '').strip() for b in
                            m.find_elements(By.CSS_SELECTOR, 'button')],
            })
        # 点最后一条的编辑（若存在）—— 逐条打印
        target = None
        for m in msgs:
            if 'PROBE_消息' in (m.text or ''):
                target = m
                break
        out['target_text'] = (target.text or '') if target else None
        if target is not None:
            btn = None
            for b in target.find_elements(By.CSS_SELECTOR, '[aria-label]'):
                if b.get_attribute('aria-label') == '编辑':
                    btn = b
                    break
            out['edit_btn_found'] = btn is not None
            if btn is not None:
                out['edit_btn_displayed'] = btn.is_displayed()
                js_click(d, btn)
                time.sleep(1.5)
                out['after_click_textareas'] = [
                    {'placeholder': x.get_attribute('placeholder'),
                     'value': x.get_attribute('value')} for x in
                    d.find_elements(By.CSS_SELECTOR, 'textarea')]
                out['body_snippet'] = body_text(d)[:800]
                out['buttons_after'] = [(b.text or '').strip() for b in
                                        d.find_elements(By.CSS_SELECTOR, 'button') if b.is_displayed()][:20]
    finally:
        try:
            d.execute_script("['iatp:ai-chat:v1:config','iatp:ai-chat:v1:messages','iatp:ai-chat:v1:providers'].forEach(function(k){localStorage.removeItem(k);});")
        except Exception:
            pass
        d.quit()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
