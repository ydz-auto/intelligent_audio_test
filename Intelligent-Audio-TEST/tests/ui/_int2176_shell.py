# -*- coding: utf-8 -*-
"""INT-2176 覆盖 3(开始测试参数读取)/5(网络证据)/10(壳层)：引导卡、toast 关闭、
排行榜算法选择器、通知中心、开始测试算法参数（docker 15173 真实栈）。"""
import json
import os
import time
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('r', os.path.join(HERE, '_int2176_report.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

ART = os.path.join(HERE, 'artifacts', 'int2176', 'shell')
RES = {}


def driver_dg():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    for a in ['--headless=new', '--window-size=1680,1050', '--no-sandbox', '--disable-gpu',
              '--disable-extensions', '--lang=zh-CN', '--disable-dev-shm-usage',
              '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    d = webdriver.Chrome(options=o, service=Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    return d


def net_since(d):
    """取 performance log 中的 API 响应（不截图，保证日志未被 drain）。"""
    out = []
    try:
        for e in d.get_log('performance'):
            m = json.loads(e['message'])['message']
            if m.get('method') == 'Network.responseReceived':
                u = m['params']['response']['url']
                if '/api/' in u:
                    out.append({'status': m['params']['response']['status'], 'url': u})
    except Exception as ex:
        return {'err': str(ex)}
    return out


def find_button(d, text=None, aria=None):
    return d.execute_script(r.JS_VIS + """
      const els=[...document.querySelectorAll('button, [role=button]')].filter(vis)
        .filter(e => (!arguments[0] || (e.innerText||'').trim().includes(arguments[0])) &&
                     (!arguments[1] || (e.getAttribute('aria-label')||'')===arguments[1]));
      return els.length ? {ok:true, n:els.length, txt:(els[0].innerText||'').slice(0,40), aria:els[0].getAttribute('aria-label')} : {ok:false};
    """, text, aria)


def click_button(d, text=None, aria=None, wait=1.5):
    res = d.execute_script(r.JS_VIS + """
      const els=[...document.querySelectorAll('button, [role=button]')].filter(vis)
        .filter(e => (!arguments[0] || (e.innerText||'').trim().includes(arguments[0])) &&
                     (!arguments[1] || (e.getAttribute('aria-label')||'')===arguments[1]));
      if(!els.length) return {ok:false};
      els[0].scrollIntoView({block:'center'}); els[0].click();
      return {ok:true, n:els.length, txt:(els[0].innerText||'').slice(0,40)};
    """, text, aria)
    time.sleep(wait)
    return res


def toast_info(d):
    return d.execute_script("""
      const t=document.querySelector('[data-sonner-toast]');
      if(!t) return {present:false};
      const close=t.querySelector('[data-close-button], button[aria-label*="Close"], button[aria-label*="关闭"]');
      return {present:true, text:(t.innerText||'').trim().slice(0,120),
              close: close ? {found:true, aria:close.getAttribute('aria-label'), cls:close.className.slice(0,80)} : {found:false},
              close_btn_count: t.querySelectorAll('button').length,
              html: t.outerHTML.slice(0,400)};
    """)


def close_toast(d):
    return d.execute_script("""
      const t=document.querySelector('[data-sonner-toast]');
      if(!t) return {ok:false, why:'no toast'};
      const c=t.querySelector('[data-close-button]') || [...t.querySelectorAll('button')].pop();
      if(!c) return {ok:false, why:'no close btn'};
      c.click(); return {ok:true};
    """)


def main():
    os.makedirs(ART, exist_ok=True)
    d = driver_dg()
    try:
        r.login(d)

        # ---------- 10. 工作台引导卡（Skill/MCP 文案 + 复制 curl toast 关闭钮） ----------
        d.get(r.BASE + '/dashboard')
        r.ready(d, 5)
        RES['guide_collapsed'] = {'has_show_btn': '显示引导' in r.body_text(d)}
        # 展开
        exp = click_button(d, '显示引导', wait=3)
        RES['guide_expand_click'] = exp
        gtxt = r.body_text(d)
        RES['guide'] = {
            'has_skill_mcp_sentence': '平台能力以 Skill / MCP 形式开放' in gtxt,
            'has_old_rest_sse_sentence': '平台全部能力开放为 REST 与 SSE' in gtxt,
            'has_hide_btn': '隐藏引导' in gtxt,
            'has_example_section': '开发者 API 示例' in gtxt,
            'has_poll_progress': '查询任务执行进度' in gtxt,
        }
        r.shot(d, '01-dashboard-guide-light')
        # 展开开发者 API 示例
        click_button(d, '开发者 API 示例', wait=1.5)
        t2 = r.body_text(d)
        RES['guide']['after_example_expand_has_copy'] = '复制 curl' in t2
        r.shot(d, '02-dashboard-guide-example-light')
        # 点复制 curl → toast
        click_button(d, '复制 curl', wait=2.0)
        RES['toast_after_copy'] = toast_info(d)
        r.shot(d, '03-toast-close-button-light')
        RES['toast_close_click'] = close_toast(d)
        time.sleep(1.2)
        RES['toast_after_close'] = toast_info(d)
        # 隐藏引导
        RES['guide_collapse_click'] = click_button(d, '隐藏引导', wait=2.5)
        RES['guide_collapsed_state'] = {
            'text_tail': [x for x in r.body_text(d).splitlines() if x.strip()][-12:],
        }
        # 深色
        RES['theme_dark'] = r.set_theme(d, 'dark', r.BASE + '/dashboard')
        click_button(d, '显示引导', wait=3)
        r.shot(d, '04-dashboard-guide-dark')

        # ---------- 5. 网络证据：算法列表/详情走 /algorithm/definitions ----------
        r.set_theme(d, 'light', r.BASE + '/AlgorithmConfig')
        d.get_log('performance')  # drain
        d.get(r.BASE + '/AlgorithmConfig')
        r.ready(d, 5)
        calls = net_since(d)
        RES['net_algorithm_config'] = calls

        # ---------- 3. 开始测试的算法参数读取 ----------
        d.get(r.BASE + '/start-test')
        r.ready(d, 6)
        stxt = r.body_text(d)
        RES['start_test'] = {
            'len': len(stxt),
            'has_algorithm': '小艺语音大模型' in stxt or '算法' in stxt,
            'snippet': [x for x in stxt.splitlines() if x.strip()][-25:],
        }
        RES['net_start_test'] = net_since(d)
        r.shot(d, '05-start-test-light')

        # ---------- 10. 排行榜算法选择器 ----------
        d.get(r.BASE + '/rankings')
        r.ready(d, 8)
        info = d.execute_script(r.JS_VIS + """
          const sec=document.querySelector(\"section[aria-label='算法切换']\");
          if(!sec) return {ok:false};
          const cards=[...sec.querySelectorAll('button')].filter(vis).map(b=>({txt:(b.innerText||'').trim().slice(0,50), pressed:b.getAttribute('aria-pressed')}));
          return {ok:true, texts:(sec.innerText||'').slice(0,400), cards:cards, vis:vis(sec)};
        """)
        RES['rankings'] = info
        # 选小艺语音大模型
        click = d.execute_script(r.JS_VIS + """
          const sec=document.querySelector(\"section[aria-label='算法切换']\");
          if(!sec) return {ok:false};
          const b=[...sec.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').includes('小艺语音大模型'));
          if(!b) return {ok:false, why:'no card'};
          b.scrollIntoView({block:'center'}); b.click(); return {ok:true};
        """)
        time.sleep(2)
        RES['rankings_select'] = {'click': click, 'toast': toast_info(d)}
        RES['rankings_after_select'] = d.execute_script(r.JS_VIS + """
          const sec=document.querySelector(\"section[aria-label='算法切换']\");
          const cards=[...sec.querySelectorAll('button')].filter(vis).map(b=>({txt:(b.innerText||'').trim().slice(0,30), pressed:b.getAttribute('aria-pressed')}));
          return {cards:cards, store: localStorage.getItem('iatp:rankings:v1:algorithm')};
        """)
        r.shot(d, '06-rankings-algorithm-light')
        # 刷新持久化
        d.refresh(); r.ready(d, 7)
        RES['rankings_after_reload'] = d.execute_script(r.JS_VIS + """
          const sec=document.querySelector(\"section[aria-label='算法切换']\");
          if(!sec) return {ok:false};
          const cards=[...sec.querySelectorAll('button')].filter(vis).map(b=>({txt:(b.innerText||'').trim().slice(0,30), pressed:b.getAttribute('aria-pressed')}));
          return {cards:cards, store: localStorage.getItem('iatp:rankings:v1:algorithm')};
        """)
        # 恢复全部算法
        click2 = d.execute_script(r.JS_VIS + """
          const sec=document.querySelector(\"section[aria-label='算法切换']\");
          const b=[...sec.querySelectorAll('button')].filter(vis).find(x=>(x.innerText||'').includes('全部算法'));
          if(!b) return {ok:false};
          b.click(); return {ok:true};
        """)
        time.sleep(2)
        RES['rankings_restore'] = {'click': click2, 'toast': toast_info(d),
                                   'store': d.execute_script("return localStorage.getItem('iatp:rankings:v1:algorithm')")}

        # ---------- 10. 通知中心（公共壳） ----------
        d.get(r.BASE + '/')
        r.ready(d, 5)
        RES['notif_badge_before'] = d.execute_script(r.JS_VIS + """
          const b=[...document.querySelectorAll('button')].filter(vis).find(x=>(x.getAttribute('aria-label')||'')==='通知');
          if(!b) return {found:false};
          const badge=b.querySelector('[class*=rounded-full]');
          return {found:true, badge: badge ? badge.innerText.trim() : null, aria:b.getAttribute('aria-label')};
        """)
        click_button(d, aria='通知', wait=2)
        RES['notif_popover'] = d.execute_script(r.JS_VIS + """
          const vis2=vis;
          const pop=[...document.querySelectorAll('[role=dialog]')].filter(vis2).pop();
          const txt=pop?(pop.innerText||''):document.body.innerText;
          return {has_title: txt.includes('通知中心'), has_tabs: txt.includes('通知') && txt.includes('公告'),
                  has_empty_notice: txt.includes('暂无通知'), has_mark_all: txt.includes('全部已读'),
                  snippet: txt.slice(0,300)};
        """)
        r.shot(d, '07-notifications-light')
        # 切公告页签
        click_button(d, '公告', wait=1.5)
        RES['notif_announcement'] = d.execute_script(r.JS_VIS + """
          const pop=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
          const txt=pop?(pop.innerText||''):'';
          return {has_empty: txt.includes('暂无公告'), snippet: txt.slice(0,200)};
        """)
        # 全部已读
        click_button(d, '全部已读', wait=1.5)
        RES['notif_after_mark_all'] = d.execute_script(r.JS_VIS + """
          const pop=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
          return {popover_open: !!pop && (pop.innerText||'').includes('通知中心'), store: localStorage.getItem('iatp:notification:read:v1')};
        """)
        # 深色通知弹窗
        r.set_theme(d, 'dark', r.BASE + '/')
        click_button(d, aria='通知', wait=2)
        r.shot(d, '08-notifications-dark')
        RES['bundle_end'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src.split('/').pop())")
        RES['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    finally:
        try:
            d.quit()
        except Exception:
            pass
    open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8').write(
        json.dumps(RES, ensure_ascii=False, indent=2))
    print('done')


if __name__ == '__main__':
    main()
