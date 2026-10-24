# -*- coding: utf-8 -*-
"""INT-1489 第五轮：Access Token 编辑/启停/删除（DOM 取准确名称）。"""
import json, os, re, time, traceback
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
  if(url.indexOf('/access-tokens')!==-1){try{e.resBody=await r.clone().text();}catch(x){}}
  window.__fetchLog.push(e);return r;}
 catch(err){e.status='ERR';window.__fetchLog.push(e);throw err;}
};
"""


def drv():
    o = Options(); o.binary_location = CHROME
    for a in ('--headless=new','--window-size=1600,1400','--disable-gpu','--no-sandbox','--lang=zh-CN','--no-first-run'):
        o.add_argument(a)
    import winreg
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64'); path=''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k,'version')[0].split('.')[0])
        for v in os.listdir(cache):
            exe=os.path.join(cache,v,'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0]==str(major): path=exe
    except Exception: pass
    d=webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


def t(d): return d.execute_script('return document.body.textContent || ""') or ''
def shot(d,n): d.save_screenshot(f'{ART}/{n}.png'); print('SHOT',n)
def goto(d,p,s=4):
    d.get(BASE+p); WebDriverWait(d,30).until(lambda x: x.execute_script('return document.readyState')=='complete'); time.sleep(s)
def jsclick(d,el): d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();',el)
def xp(d,e,t_=15): return WebDriverWait(d,t_).until(EC.presence_of_element_located((By.XPATH,e)))
def lg(d):
    try: return d.execute_script('return window.__fetchLog||[]') or []
    except Exception: return []
def clr(d): d.execute_script('window.__fetchLog=[];')
def reqs(d):
    out=[]
    for e in lg(d):
        if '/access-tokens' not in e.get('url',''): continue
        i={'m':e.get('method'),'u':e.get('url','').split(BASE)[-1],'s':e.get('status')}
        if e.get('reqBody'):
            try: i['req']=json.loads(e['reqBody'])
            except Exception: i['req']=e['reqBody'][:150]
        if e.get('resBody'):
            try: i['res']=json.loads(e['resBody']).get('data')
            except Exception: pass
        out.append(i)
    return out
def row(name, inner):
    return f"//p[normalize-space(.)='{name}']/ancestor::div[contains(@class,'py-3')][1]{inner}"
def names(d):
    vals=[]
    for p in d.find_elements(By.XPATH, "//div[contains(@class,'py-3')]//p[contains(@class,'font-medium')]"):
        v=(p.text or '').strip()
        if v: vals.append(v)
    return vals
def login(d):
    goto(d,'/login',2)
    d.execute_script("localStorage.removeItem('iatp:auth:v1');localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.4); goto(d,'/login',2.5)
    if len(d.find_elements(By.ID,'username'))==0: return d.current_url
    d.find_element(By.ID,'username').send_keys('接线测试_admin')
    d.find_element(By.ID,'password').send_keys('JieXianTest@2026')
    d.find_element(By.XPATH,"//form//button[@type='submit']").click(); time.sleep(5)
    return d.current_url


d = drv()
out = {}
try:
    out['login'] = login(d)
    goto(d,'/profile',5)
    out['names_before'] = names(d)
    targets = [n for n in out['names_before'] if n.startswith('接线测试_token_')]
    out['targets'] = targets
    shot(d,'profile_before5')
    target = targets[0] if targets else None
    if target:
        # 编辑
        try:
            r={}
            jsclick(d, xp(d, row(target, "//button[@aria-label='编辑 Access Token']")))
            time.sleep(1.5)
            edit=d.find_element(By.XPATH,"//*[@role='dialog']")
            r['title']=edit.find_element(By.XPATH,'.//h2').text
            en=edit.find_element(By.ID,'access-token-edit-name')
            r['prefill']=en.get_attribute('value')
            r['expiry']=edit.find_element(By.ID,'access-token-edit-expiry').text
            r['scope']=[e.text for e in edit.find_elements(By.XPATH,".//span[contains(., '已选') and contains(., '项')]")]
            shot(d,'token_edit_dialog')
            en.send_keys(Keys.CONTROL,'a'); en.send_keys(Keys.DELETE)
            jsclick(d, edit.find_element(By.XPATH,".//button[@type='submit']")); time.sleep(1.2)
            r['empty_error']=[e.text for e in edit.find_elements(By.XPATH,".//p[contains(@class,'text-destructive')]")]
            shot(d,'token_edit_validation')
            new=target+'_改名'
            en.send_keys(new)
            clr(d); jsclick(d, edit.find_element(By.XPATH,".//button[@type='submit']")); time.sleep(4)
            r['reqs']=reqs(d)
            r['closed']=len(d.find_elements(By.XPATH,"//*[@role='dialog']"))==0
            goto(d,'/profile',4)
            r['list_has_new']= new in names(d)
            r['names_after_edit']=names(d)
            g=[x for x in reqs(d) if x['m']=='GET']
            r['get']=g[-1] if g else None
            out['edit']=r; target=new
            shot(d,'token_after_edit')
        except Exception:
            out['edit']={'FAIL':traceback.format_exc()[-500:]}
        # 启停
        try:
            r={}
            clr(d)
            sw=xp(d, row(target, "//*[@data-slot='switch' or @role='switch']"))
            r['aria_before']=sw.get_attribute('aria-label')
            jsclick(d,sw); time.sleep(4)
            r['disable']=reqs(d)
            goto(d,'/profile',4)
            r['disabled_badge']='已停用' in t(d)
            clr(d)
            sw2=xp(d, row(target, "//*[@data-slot='switch' or @role='switch']"))
            r['aria_after']=sw2.get_attribute('aria-label')
            jsclick(d,sw2); time.sleep(4)
            r['enable']=reqs(d)
            goto(d,'/profile',4)
            r['enabled_badge']='已启用' in t(d)
            g=[x for x in reqs(d) if x['m']=='GET']
            r['get']=g[-1] if g else None
            out['toggle']=r
            shot(d,'token_after_toggle')
        except Exception:
            out['toggle']={'FAIL':traceback.format_exc()[-500:]}
        # 删除全部本卡 token
        try:
            r={'to_delete':[n for n in names(d) if n.startswith('接线测试_token_')]}
            for n in list(r['to_delete']):
                clr(d)
                jsclick(d, xp(d, row(n, "//button[@aria-label='删除 Access Token']"),8))
                time.sleep(1.2)
                if 'confirm' not in r:
                    r['confirm']=' '.join(x.text[:200].replace('\n',' ') for x in d.find_elements(By.XPATH,"//*[@role='alertdialog' or @role='dialog']"))
                jsclick(d, xp(d, "(//*[@role='alertdialog']//button[normalize-space(.)='删除'])[last()] | (//*[@role='dialog']//button[normalize-space(.)='删除'])[last()]"))
                time.sleep(3)
                if 'delete_req' not in r: r['delete_req']=reqs(d)
            goto(d,'/profile',4)
            r['remaining']=[n for n in names(d) if n.startswith('接线测试_token_')]
            g=[x for x in reqs(d) if x['m']=='GET']
            r['get_after_delete']=g[-1] if g else None
            out['delete']=r
            shot(d,'token_list_final5')
        except Exception:
            out['delete']={'FAIL':traceback.format_exc()[-500:]}
    R['round5']=out
    print('RESULT', json.dumps(out, ensure_ascii=False)[:2500])
finally:
    d.quit()
    with open(f'{ART}/round5_result.json','w',encoding='utf-8') as f:
        json.dump(R,f,ensure_ascii=False,indent=2)
    print('DONE')
