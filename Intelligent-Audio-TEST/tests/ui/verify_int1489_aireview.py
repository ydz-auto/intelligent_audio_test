# -*- coding: utf-8 -*-
"""INT-1489 AI 复核两个弹窗：会话弹窗 + 快速复核（真实发起，不采纳）。"""
import json, os, time, traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1489'
R = {}

PATCH = r"""
window.__fetchLog=[];
const f=window.fetch;
window.fetch=async function(input,init){
 const url=typeof input==='string'?input:(input&&input.url)||'';
 const e={url:url,method:(init&&init.method)||'GET'};
 try{const r=await f.apply(this,arguments);e.status=r.status;
  if(init&&typeof init.body==='string')e.reqBody=init.body;
  if(url.indexOf('ai-review')!==-1||url.indexOf('/results')!==-1){try{e.resBody=await r.clone().text();}catch(x){}}
  window.__fetchLog.push(e);return r;}
 catch(err){e.status='ERR';window.__fetchLog.push(e);throw err;}
};
"""


def drv():
    o = Options(); o.binary_location = CHROME
    for a in ('--headless=new','--window-size=1600,1200','--disable-gpu','--no-sandbox','--lang=zh-CN','--no-first-run'):
        o.add_argument(a)
    import winreg
    cache = os.path.join(os.path.expanduser('~'),'.cache','selenium','chromedriver','win64'); path=''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major=int(winreg.QueryValueEx(k,'version')[0].split('.')[0])
        for v in os.listdir(cache):
            exe=os.path.join(cache,v,'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0]==str(major): path=exe
    except Exception: pass
    d=webdriver.Chrome(options=o,service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


def t(d): return d.execute_script('return document.body.textContent || ""') or ''
def shot(d,n): d.save_screenshot(f'{ART}/{n}.png'); print('SHOT',n)
def goto(d,p,s=4):
    d.get(BASE+p); WebDriverWait(d,40).until(lambda x: x.execute_script('return document.readyState')=='complete'); time.sleep(s)
def jsclick(d,el): d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();',el)
def xp(d,e,t_=20): return WebDriverWait(d,t_).until(EC.presence_of_element_located((By.XPATH,e)))
def lg(d):
    try: return d.execute_script('return window.__fetchLog||[]') or []
    except Exception: return []
def clr(d): d.execute_script('window.__fetchLog=[];')
def ai_reqs(d):
    out=[]
    for e in lg(d):
        u=e.get('url','')
        if 'ai-review' not in u and '/cases/' not in u and '/results' not in u: continue
        i={'m':e.get('method'),'u':u.split(BASE)[-1],'s':e.get('status')}
        if e.get('reqBody'):
            try: i['req']=json.loads(e['reqBody'])
            except Exception: i['req']=e['reqBody'][:200]
        if e.get('resBody'):
            try:
                j=json.loads(e['resBody']); i['res']=(j.get('data') if isinstance(j,dict) else j)
            except Exception: i['res']=e['resBody'][:300]
        out.append(i)
    return out


def login(d):
    goto(d,'/login',2)
    d.execute_script("localStorage.removeItem('iatp:auth:v1');localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.4); goto(d,'/login',2.5)
    if len(d.find_elements(By.ID,'username'))==0: return d.current_url
    d.find_element(By.ID,'username').send_keys('接线测试_admin')
    d.find_element(By.ID,'password').send_keys('JieXianTest@2026')
    d.find_element(By.XPATH,"//form//button[@type='submit']").click(); time.sleep(5)
    return d.current_url


d=drv(); out={}
try:
    out['login']=login(d)
    goto(d,'/tasks/527',8)
    out['url']=d.current_url
    body=t(d)
    out['has_ai_review_btn']='AI 复核' in body
    out['has_quick_btn']='快速复核' in body
    # 找 AI 复核按钮
    btns=[b for b in d.find_elements(By.XPATH,"//button[contains(normalize-space(.),'AI 复核')]")]
    out['ai_btn_count']=len(btns)
    out['btn_titles']=[b.get_attribute('title') for b in btns[:5]]
    shot(d,'task527_detail')
    if btns:
        clr(d)
        jsclick(d,btns[0]); time.sleep(4)
        dlg=d.find_elements(By.XPATH,"//*[@data-slot='ai-review-session-dialog']")
        out['session_dialog_open']=len(dlg)>0
        if dlg:
            txt=dlg[0].text
            out['session_text']=txt[:700].replace('\n',' | ')
            out['session_btn_save_disabled']=d.execute_script(
                "const b=[...document.querySelectorAll(\"[data-slot='ai-review-session-dialog'] button\")].find(x=>x.textContent.includes('保存复核结论'));return b?b.disabled:null")
            out['session_reqs']=ai_reqs(d)
            shot(d,'aireview_session_light')
            d.execute_script("document.documentElement.classList.add('dark');"); time.sleep(1)
            shot(d,'aireview_session_dark')
            d.execute_script("document.documentElement.classList.remove('dark');")
            # 关闭
            try:
                jsclick(d, xp(d,"//*[@data-slot='ai-review-session-dialog']//button[contains(normalize-space(.),'稍后处理')]"))
            except Exception:
                d.find_element(By.TAG_NAME,'body').send_keys(Keys.ESCAPE)
            time.sleep(1.5)
        out['session_closed']=len(d.find_elements(By.XPATH,"//*[@data-slot='ai-review-session-dialog']"))==0
    # 快速复核
    qbtns=[b for b in d.find_elements(By.XPATH,"//button[contains(normalize-space(.),'快速复核')]")]
    out['quick_btn_count']=len(qbtns)
    if qbtns:
        clr(d)
        jsclick(d,qbtns[0]); time.sleep(3)
        dlg=d.find_elements(By.XPATH,"//*[@data-slot='quick-ai-review-dialog']")
        out['quick_dialog_open']=len(dlg)>0
        if dlg:
            out['quick_text']=dlg[0].text[:500].replace('\n',' | ')
            shot(d,'aireview_quick_idle')
            launch=[b for b in d.find_elements(By.XPATH,"//*[@data-slot='quick-ai-review-dialog']//button[contains(normalize-space(.),'发起快速复核')]")]
            if launch:
                clr(d)
                jsclick(d,launch[0])
                time.sleep(2)
                shot(d,'aireview_quick_running')
                # 轮询 12s 观察状态
                states=[]
                for _ in range(6):
                    time.sleep(3)
                    txt=' '.join(x.text[:300].replace('\n',' ') for x in d.find_elements(By.XPATH,"//*[@data-slot='quick-ai-review-dialog']"))
                    states.append(txt[:200])
                    if 'AI 复核结论' in txt or '失败' in txt or '已驳回' in txt:
                        break
                out['quick_states']=states
                out['quick_reqs']=ai_reqs(d)
                shot(d,'aireview_quick_result')
                d.execute_script("document.documentElement.classList.add('dark');"); time.sleep(1)
                shot(d,'aireview_quick_dark')
                d.execute_script("document.documentElement.classList.remove('dark');")
                out['quick_final_text']=' '.join(x.text[:600].replace('\n',' ') for x in d.find_elements(By.XPATH,"//*[@data-slot='quick-ai-review-dialog']"))
                # 关闭（不采纳）
                for label in ('取消','关闭'):
                    bs=[b for b in d.find_elements(By.XPATH,f"//*[@data-slot='quick-ai-review-dialog']//button[normalize-space(.)='{label}']")]
                    if bs:
                        jsclick(d,bs[0]); break
                else:
                    d.find_element(By.TAG_NAME,'body').send_keys(Keys.ESCAPE)
                time.sleep(1.5)
        out['quick_closed']=len(d.find_elements(By.XPATH,"//*[@data-slot='quick-ai-review-dialog']"))==0
    R['aireview']=out
    print('RESULT', json.dumps(out,ensure_ascii=False)[:3000])
except Exception:
    R['aireview_fatal']=traceback.format_exc()[-800:]
    print(R['aireview_fatal'])
finally:
    d.quit()
    with open(f'{ART}/aireview_result.json','w',encoding='utf-8') as f:
        json.dump(R,f,ensure_ascii=False,indent=2)
    print('DONE')
