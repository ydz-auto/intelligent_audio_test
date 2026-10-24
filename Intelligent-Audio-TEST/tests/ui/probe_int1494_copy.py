# -*- coding: utf-8 -*-
import json, os, sys, time
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import ARTIFACTS, body_text, driver, goto, js_click, result, set_theme, shot
R=[]; d=driver()
try:
    set_theme(d,'light'); goto(d,'/user-guide-api',wait_text='API 手册'); time.sleep(2)
    btns=d.find_elements(By.CSS_SELECTOR,"button[aria-label='复制代码']")
    st={'count':len(btns)}
    if btns:
        el=btns[0]
        st['before']=d.execute_script("return arguments[0].outerHTML.slice(0,400)",el)
        js_click(d,el); time.sleep(1.5)
        st['after']=d.execute_script("return arguments[0].outerHTML.slice(0,400)",el)
        st['changed']= st['before']!=st['after']
        st['clip']=d.execute_script("return navigator.clipboard.readText().catch(e=>'ERR:'+e.name)")
        time.sleep(1)
    R.append(result('copy', st.get('changed', False), st, [shot(d,'guide_copy_light')]))
finally:
    d.quit()
json.dump(R,open(os.path.join(ARTIFACTS,'int1494_copy.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps(R,ensure_ascii=False,indent=2)[:2500])
