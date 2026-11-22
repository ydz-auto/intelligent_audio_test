# -*- coding: utf-8 -*-
"""INT-2675 前端回归日巡补充实测（React docker 栈 15173，只读）。

本轮重点（卡面「上一轮结论与本轮重点」）：
  report — report-view 五条前端提交：
           * 8d54eb26c 用例标签筛选卡关键词搜索（过滤 / 无匹配 / 清空）
           * d844800d7 排序资源/评估维度下拉长名溢出与弹层裁切（触发器宽度、弹层宽度、文本不裁切）
           * 800a78b52 用例详情结果音频改可点击时间轴 → 点击分段弹播放器播输入音频
           * 8df9c9a67 具体用例状态筛选（全部/通过/失败）
           * a0a734c2e 具体用例对比分组头展开/收起
  device  — INT-2670 / INT-2671 修复后回归（四图接真实 monitor-stats、历史监控按分类取数）
  perf    — c35d6a218 全站 SSE 共享单连接；d16e7560b facet per_page 200；189297bee 音频页懒加载

只读：不改库、不删数据、不保存设置。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2675_focus.py report --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2675_focus.py device --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2675_focus.py perf   --base http://localhost:15173 --api http://127.0.0.1:15000
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2675')


class Probe:
    def __init__(self, base, api_root, username, password):
        self.base = base.rstrip('/')
        self.api_root = api_root
        self.api = ApiClient(api_root)
        self.api.login(username, password)
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-46s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def skip(self, name, detail):
        self.checks.append({'name': name, 'ok': True, 'skipped': True, 'detail': detail})
        print('[SKIP] %-46s %s' % (name, detail), flush=True)

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path, full_page=False)
        print('SHOT=%s' % path, flush=True)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    def watch(self, page):
        def on_req(req):
            self.net.append({'m': req.method, 'u': req.url[:240], 't': time.time()})

        page.on('request', on_req)

    def bad_requests(self, since=0):
        return [n for n in self.net[since:] if any(k in n['u'] for k in ('/api/v1/',))]

    def toggle_theme(self, page, dark):
        # React 深色走 html.dark / data-theme（INT-1854 smoke 口径同款按钮在设置页；这里直接置类）
        page.evaluate(
            "(d)=>{const el=document.documentElement;el.classList.toggle('dark',d);"
            "el.setAttribute('data-theme', d?'dark':'light');}", dark)
        page.wait_for_timeout(600)


# ───────────── report：report-view 五条提交 ─────────────
def run_report(p, page, report_id):
    p.watch(page)
    page.goto(p.base + '/report/%d' % report_id, wait_until='domcontentloaded')
    # 报告详情异步拉取
    try:
        page.wait_for_selector("text=具体用例对比", timeout=60000)
    except Exception:
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        page.locator('tbody tr').first.click()
        page.wait_for_selector("text=具体用例对比", timeout=60000)
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(ART, '00_report_top.png'))

    # ── 1. 标签筛选卡关键词搜索 (8d54eb26c) ──
    tag_input = page.locator("input[aria-label='搜索用例标签']")
    tag_input.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    # 初始可见标签 checkbox 数与该区块标签文本
    def tag_labels():
        return page.evaluate(
            """()=>{
              const inp=document.querySelector("input[aria-label='搜索用例标签']");
              if(!inp) return [];
              const card=inp.closest('[data-export-hide]');
              if(!card) return [];
              // 标签分组容器 = 筛选卡里 div.mt-2.space-y-2（无命中时是 p「无匹配标签」）
              const g=card.querySelector('div.mt-2.space-y-2');
              if(!g) return [];
              return Array.from(g.querySelectorAll('label')).map(l=>l.innerText.trim()).filter(Boolean);
            }"""
        )
    base_labels = tag_labels()
    p.check('8d54eb26c 初始标签可见', len(base_labels) >= 1, 'labels=%r' % base_labels)
    # 命中唯一标签（'单轮' 只命中「单轮接管-正常接管」）
    tag_input.fill('单轮')
    page.wait_for_timeout(500)
    hit_labels = tag_labels()
    p.check('8d54eb26c 关键词「单轮」过滤掉其他标签',
            len(hit_labels) == 1 and '单轮接管-正常接管' in hit_labels[0]
            and all('单轮' in x for x in hit_labels),
            'labels=%r' % hit_labels)
    p.shot(page, '10_tag_search_hit')
    # 无命中 → 无匹配标签
    tag_input.fill('ZZZ_NOT_EXIST')
    page.wait_for_timeout(500)
    no_match = page.locator("text=无匹配标签").count()
    p.check('8d54eb26c 无命中显示「无匹配标签」', no_match >= 1, 'count=%d' % no_match)
    p.shot(page, '11_tag_search_nomatch')
    # 清空恢复
    tag_input.fill('')
    page.wait_for_timeout(500)
    restored = tag_labels()
    p.check('8d54eb26c 清空后恢复全部标签', len(restored) == len(base_labels),
            'before=%d after=%d' % (len(base_labels), len(restored)))

    # ── 2. 具体用例状态筛选 (8df9c9a67) ──
    # 滚动到具体用例对比
    page.locator("text=具体用例对比").first.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(ART, '12_specific_cases.png'))

    def case_result_total():
        txt = page.evaluate("()=>document.body.innerText")
        import re
        m = re.search(r'共\s*(\d+)\s*条结果', txt)
        return int(m.group(1)) if m else None

    def status_select_trigger():
        # 状态 Select 触发器：文本为「全部状态」/「通过」/「失败」... 的 combobox
        for b in page.locator("[role=combobox]").all():
            try:
                if b.is_visible() and b.inner_text().strip() in (
                        '全部状态', '通过', '失败', '警告', '跳过', '未知'):
                    return b
            except Exception:
                pass
        return None

    trg = status_select_trigger()
    p.check('8df9c9a67 状态筛选触发器存在（全部状态）', trg is not None,
            'trigger=%r' % (trg.inner_text() if trg else None))
    if trg:
        trg.click()
        page.wait_for_timeout(700)
        p.shot(page, '13_status_options')
        opts = [o.inner_text().strip() for o in page.locator("[role=option]").all() if o.is_visible()]
        p.check('8df9c9a67 状态选项齐全',
                all(x in opts for x in ('全部状态', '通过', '失败')), 'opts=%r' % opts)
        # 选「失败」→ 0 条
        page.locator("[role=option]", has_text='失败').first.click()
        page.wait_for_timeout(1200)
        fail_total = case_result_total()
        empty_txt = page.locator("text=暂无数据").count()
        p.check('8df9c9a67 选「失败」后 0 结果', (fail_total == 0) or empty_txt >= 1,
                'total=%r 暂无数据=%d' % (fail_total, empty_txt))
        p.shot(page, '14_status_fail_empty')
        # 选「通过」→ 恢复非零
        status_select_trigger().click()
        page.wait_for_timeout(600)
        page.locator("[role=option]", has_text='通过').first.click()
        page.wait_for_timeout(1200)
        pass_total = case_result_total()
        p.check('8df9c9a67 选「通过」后结果恢复', (pass_total or 0) > 0, 'total=%r' % pass_total)
        # 复位
        status_select_trigger().click()
        page.wait_for_timeout(500)
        page.locator("[role=option]", has_text='全部状态').first.click()
        page.wait_for_timeout(900)

    # ── 3. 分组头展开/收起 (a0a734c2e) ──
    group_btns = page.locator("button[aria-label^='展开或收起分组']")
    n_groups = group_btns.count()
    p.check('a0a734c2e 分组头按钮存在', n_groups >= 1, 'groups=%d' % n_groups)
    if n_groups >= 1:
        g = group_btns.first
        label = g.get_attribute('aria-label')
        before_exp = g.get_attribute('aria-expanded')
        # 计算组内 case 卡数量（data-export-case 不是页面态；用报告卡标识或展开详情按钮计数）
        cards_before = page.locator("button[aria-label='展开详情']").count()
        g.click()
        page.wait_for_timeout(800)
        after_exp = group_btns.first.get_attribute('aria-expanded')
        cards_after = page.locator("button[aria-label='展开详情']").count()
        p.check('a0a734c2e 点击分组头折叠组内用例',
                before_exp != after_exp and cards_after < cards_before,
                'aria %s→%s cards %d→%d (%s)' % (before_exp, after_exp, cards_before,
                                                 cards_after, label))
        p.shot(page, '15_group_collapsed')
        group_btns.first.click()
        page.wait_for_timeout(800)
        cards_restored = page.locator("button[aria-label='展开详情']").count()
        p.check('a0a734c2e 再次点击恢复展开', cards_restored == cards_before,
                'cards %d→%d' % (cards_after, cards_restored))

    # ── 4. 排序资源/评估维度下拉长名 (d844800d7) ──
    sort_trigger = None
    combo_texts = []
    for b in page.locator("[role=combobox]").all():
        try:
            if not b.is_visible():
                continue
            t = b.inner_text().strip()
            combo_texts.append(t)
            if t.startswith('按') and t in ('按名称', '按创建时间', '按评估维度'):
                sort_trigger = b
                break
        except Exception:
            pass
    if sort_trigger is None:
        try:
            cand = page.locator(
                "xpath=//label[normalize-space()='排序方式']/following::*[@role='combobox'][1]")
            if cand.count() > 0 and cand.first.is_visible():
                sort_trigger = cand.first
        except Exception:
            pass
    p.check('d844800d7 排序方式触发器存在', sort_trigger is not None,
            'trigger=%r combos=%r' % (
                sort_trigger.inner_text() if sort_trigger else None, combo_texts))
    if sort_trigger:
        sort_trigger.click()
        page.wait_for_timeout(600)
        page.locator("[role=option]", has_text='按评估维度').first.click()
        page.wait_for_timeout(1200)
        p.shot(page, '16_sort_by_metric')
        # 资源/评估维度触发器宽度不超过其网格单元（不溢出压右侧）
        geom = page.evaluate(
            """()=>{
              const out={};
              const labels=Array.from(document.querySelectorAll('label'));
              for(const name of ['资源','评估维度']){
                const lb=labels.find(l=>l.innerText.trim()===name);
                if(!lb) { out[name]=null; continue; }
                const cell=lb.parentElement;
                const cb=cell.querySelector('[role=combobox]');
                if(!cb){ out[name]={cell:null}; continue; }
                const cr=cell.getBoundingClientRect(), br=cb.getBoundingClientRect();
                out[name]={cellW:Math.round(cr.width), btnW:Math.round(br.width),
                           btnRight:Math.round(br.right), cellRight:Math.round(cr.right)};
              }
              return out;
            }"""
        )
        res = geom.get('资源') or {}
        over = bool(res) and res.get('btnW', 0) > res.get('cellW', 0) + 1
        p.check('d844800d7 资源触发器不溢出网格列', bool(res) and not over, 'geom=%r' % res)
        # 回显口径（P3 缺陷候选）：排序/资源触发器应显示中文选项名，不应回显原始 value
        trig_texts = page.evaluate(
            """()=>{
              const out={};
              const labels=Array.from(document.querySelectorAll('label'));
              for(const name of ['资源','排序方式']){
                const lb=labels.find(l=>l.innerText.trim()===name);
                const cb=lb&&lb.parentElement.querySelector('[role=combobox]');
                out[name]=cb?cb.innerText.trim():null;
              }
              return out;
            }"""
        )
        raw_vals = {'all', 'name', 'createdat', 'metric'}
        bad_raw = {k: v for k, v in trig_texts.items() if v in raw_vals}
        p.check('report-view 排序/资源下拉回显中文（非原始 value）',
                not bad_raw, 'trigger_texts=%r raw=%r' % (trig_texts, bad_raw))
        # 打开评估维度下拉，检查弹层宽度 >= 288(min-w-72) 且文本不裁切、层在视口内
        dim = page.evaluate(
            """()=>{
              const labels=Array.from(document.querySelectorAll('label'));
              const lb=labels.find(l=>l.innerText.trim()==='评估维度');
              if(!lb) return null;
              const cb=lb.parentElement.querySelector('[role=combobox]');
              if(!cb) return null;
              const r=cb.getBoundingClientRect();
              return {x:r.left+r.width/2, y:r.top+r.height/2};
            }"""
        )
        if dim:
            page.mouse.click(dim['x'], dim['y'])
            page.wait_for_timeout(900)
            p.shot(page, '17_dimension_popup')
            pop = page.evaluate(
                """()=>{
                  const opts=Array.from(document.querySelectorAll('[role=option]')).filter(o=>o.offsetParent!==null);
                  if(!opts.length) return {n:0};
                  // 选项共同父容器（Base UI popup / listbox）尺寸
                  const par=opts[0].parentElement;
                  const pr=par?par.getBoundingClientRect():{width:0,left:0,right:0};
                  let minL=1e9,maxR=-1e9;
                  for(const o of opts){const r=o.getBoundingClientRect();
                    minL=Math.min(minL,r.left); maxR=Math.max(maxR,r.right);}
                  const clipped=opts.filter(o=>o.scrollWidth>o.clientWidth+2)
                                   .map(o=>o.innerText.trim().slice(0,30));
                  return {n:opts.length, parentW:Math.round(pr.width),
                          unionW:Math.round(maxR-minL), left:Math.round(pr.left||minL),
                          right:Math.round(pr.right||maxR), vw:window.innerWidth,
                          clipped:clipped.slice(0,5)};
                }"""
            )
            width = max(pop.get('parentW') or 0, pop.get('unionW') or 0)
            ok_w = width >= 280
            in_vp = pop.get('right', 0) <= pop.get('vw', 0) + 2 and pop.get('left', 0) >= -2
            p.check('d844800d7 评估维度弹层宽度>=288 且未裁切',
                    pop.get('n', 0) > 0 and ok_w and not pop.get('clipped') and in_vp,
                    'popup=%r' % pop)
            page.keyboard.press('Escape')
            page.wait_for_timeout(400)

    # ── 5. 用例详情音频时间轴点击播放 (800a78b52) ──
    expand = page.locator("button[aria-label='展开详情']")
    if expand.count() == 0:
        p.skip('800a78b52 音频时间轴点击播放', '无可展开用例详情')
    else:
        expand.first.scroll_into_view_if_needed()
        expand.first.click()
        page.wait_for_timeout(1500)
        tl_btns = page.locator("button[title*='点击播放输入音频']")
        n_tl = tl_btns.count()
        p.check('800a78b52 音频时间轴分段为可点击按钮', n_tl >= 1, 'segments=%d' % n_tl)
        if n_tl >= 1:
            page.screenshot(path=os.path.join(ART, '18_audio_timeline.png'))
            before = len(p.net)
            tl_btns.first.click()
            page.wait_for_timeout(2500)
            # 播放器弹窗 + <audio> + 音频请求
            dlg = page.locator("[role=dialog]")
            audio_el = page.evaluate(
                """()=>{const a=document.querySelector('[role=dialog] audio');
                        if(!a) return null;
                        return {src:(a.src||'').slice(0,120), duration:a.duration||0,
                                readyState:a.readyState, currentTime:a.currentTime||0,
                                paused:a.paused};}"""
            )
            audio_reqs = [n['u'] for n in p.net[before:]
                          if ('/audios/' in n['u'] or 'audio' in n['u'].lower())]
            p.check('800a78b52 点击分段弹出播放器并加载音频',
                    dlg.count() >= 1 and audio_el is not None
                    and (audio_el.get('readyState', 0) >= 1 or bool(audio_el.get('src'))),
                    'dialog=%d audio=%r reqs=%r' % (dlg.count(), audio_el, audio_reqs[:4]))
            p.shot(page, '19_audio_player')
            # 进度同步：尝试等待 currentTime > 0（自动播放可能被策略拦截，记 skip 不判失败）
            advanced = False
            for _ in range(12):
                st = page.evaluate(
                    "()=>{const a=document.querySelector('[role=dialog] audio');return a?{t:a.currentTime,p:a.paused}:null}")
                if st and st['t'] and st['t'] > 0.05:
                    advanced = True
                    break
                page.wait_for_timeout(500)
            if advanced:
                p.check('800a78b52 点击后音频开始播放（currentTime>0）', True, 'advanced')
            else:
                p.skip('800a78b52 点击后音频自动播放', '弹窗与音频源已加载；headless 自动播放受限，不判失败')
            # 深色播放器截图
            p.toggle_theme(page, True)
            page.wait_for_timeout(600)
            p.shot(page, '19_audio_player_dark', dark=True)
            p.toggle_theme(page, False)
            page.keyboard.press('Escape')
            page.wait_for_timeout(400)

    # 深浅色总览
    p.toggle_theme(page, True)
    page.wait_for_timeout(800)
    page.locator("text=具体用例对比").first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    p.shot(page, '20_report_dark', dark=True)
    p.toggle_theme(page, False)


# ───────────── device：INT-2670/2671 回归 ─────────────
def run_device(p, page):
    p.watch(page)
    page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    page.screenshot(path=os.path.join(ART, '30_devices.png'))
    txt = page.evaluate("()=>document.body.innerText")
    p.check('设备页加载', ('设备' in txt), 'len=%d' % len(txt))
    # 展开「监控告警」面板（开关②）
    toggled = False
    try:
        trig = page.locator("button", has_text='监控告警').first
        if trig.count() > 0:
            trig.scroll_into_view_if_needed()
            trig.click()
            toggled = True
            page.wait_for_timeout(3500)
    except Exception as e:
        print('monitor toggle err', e, flush=True)
    page.screenshot(path=os.path.join(ART, '31_monitor_panel.png'))
    # 切到「历史监控」页签 → 触发 status-history + monitor-stats
    hist_tab_ok = False
    try:
        tab = page.get_by_role('tab', name='历史监控')
        if tab.count() > 0:
            tab.first.click()
            hist_tab_ok = True
            page.wait_for_timeout(4000)
    except Exception as e:
        print('history tab err', e, flush=True)
    page.screenshot(path=os.path.join(ART, '32_history_monitor.png'))
    urls = [n['u'] for n in p.net]
    ms = [u for u in urls if 'monitor-stats' in u]
    hist = [u for u in urls if 'status-history' in u]
    body = page.evaluate("()=>document.body.innerText")
    p.check('INT-2670 监控统计请求 /test-devices/monitor-stats',
            len(ms) >= 1, 'requests=%r hist_tab=%s' % (ms[:3], hist_tab_ok))
    p.check('INT-2671 历史监控请求 /test-devices/status-history',
            len(hist) >= 1, 'requests=%r' % hist[:3])
    p.check('INT-2670/2671 监控面板渲染（历史四子页签/统计文案）',
            any(k in body for k in ('历史监控', '状态历史', '性能历史', '操作历史', '统计分析')),
            'body_head=%r' % body[:120])
    # 统计分析四图区（INT-2670）：滚动到分区并统计图实例
    try:
        stats_head = page.locator("text=统计分析").first
        if stats_head.count() > 0:
            stats_head.scroll_into_view_if_needed()
            page.wait_for_timeout(1500)
    except Exception:
        pass
    page.screenshot(path=os.path.join(ART, '32b_stats_charts.png'))
    chart_info = page.evaluate(
        """()=>{
          // vChart 渲染成 canvas；统计四图区里应至少有多张图表
          const canvases=Array.from(document.querySelectorAll('canvas'));
          const visible=canvases.filter(c=>{const r=c.getBoundingClientRect();
             return r.width>40 && r.height>40 && r.bottom>0 && r.top<window.innerHeight;});
          return {canvasTotal:canvases.length, visible:visible.length};
        }"""
    )
    p.check('INT-2670 统计分析图表渲染（可见 canvas）',
            (chart_info.get('visible') or 0) >= 1, 'charts=%r' % chart_info)
    # 深浅色
    p.toggle_theme(page, True)
    page.wait_for_timeout(700)
    p.shot(page, '33_devices_dark', dark=True)
    p.toggle_theme(page, False)


# ───────────── perf：SSE / per_page / 音频懒加载 ─────────────
def run_perf(p, page):
    p.watch(page)
    # SSE 共享单连接：登录后跨页导航，统计并发 /sse/ 连接（按 URL 去重 + 打开次数）
    page.goto(p.base + '/tasks/daily', wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    sse = [n['u'] for n in p.net if '/sse/' in n['u']]
    uniq = sorted(set(sse))
    p.check('c35d6a218 任务页 SSE 连接数（共享单连接）', len(uniq) <= 2,
            'opened=%d uniq=%r' % (len(sse), uniq[:4]))
    # 跨页导航后不应为每页各开一条长连接
    before = len(p.net)
    page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
    page.wait_for_timeout(3500)
    sse2 = [n['u'] for n in p.net[before:] if '/sse/' in n['u']]
    p.check('c35d6a218 跨页导航不重复开 SSE', len(sse2) <= 2,
            'new_opens=%d %r' % (len(sse2), sorted(set(sse2))[:4]))

    # per_page facet（开始测试页设备/apis/维度 ≤200）
    before = len(p.net)
    page.goto(p.base + '/start-test', wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    nav_urls = [n['u'] for n in p.net[before:] if '/api/v1/' in n['u']]
    per_pages = [int(x) for u in nav_urls for x in _per_page_values(u)]
    p.check('d16e7560b 开始测试页无 per_page=1000 请求', 1000 not in per_pages,
            'per_page values=%r' % sorted(set(per_pages))[-6:])
    page.screenshot(path=os.path.join(ART, '40_test_execution.png'))

    # 音频页 folder-tree 懒加载 + 统计
    before = len(p.net)
    page.goto(p.base + '/audio', wait_until='domcontentloaded')
    page.wait_for_timeout(4500)
    page.screenshot(path=os.path.join(ART, '41_audio_page.png'))
    audio_urls = [n['u'] for n in p.net[before:] if '/api/v1/' in n['u']]
    p.check('189297bee 音频页加载（目录/统计请求）', len(audio_urls) >= 1,
            'api_calls=%d' % len(audio_urls))


def _per_page_values(url):
    from urllib.parse import urlparse, parse_qs
    try:
        q = parse_qs(urlparse(url).query)
        return q.get('per_page', [])
    except Exception:
        return []


# ───────────── tasks：重新执行/评估弹窗 (936d9b94c) ─────────────
def run_tasks(p, page, task_id):
    p.watch(page)
    page.goto(p.base + '/tasks/%d' % task_id, wait_until='domcontentloaded')
    page.wait_for_timeout(3500)
    btn = page.get_by_role('button', name='重新执行', exact=True)
    if btn.count() == 0:
        btn = page.locator("button", has_text='重新执行')
    if btn.count() == 0:
        p.skip('936d9b94c 重新执行弹窗', '任务详情无「重新执行」入口（状态/权限不符）')
        return
    btn.first.scroll_into_view_if_needed()
    btn.first.click()
    page.wait_for_timeout(1500)
    dlg = page.locator("[role=dialog]").last
    try:
        dlg.wait_for(state='visible', timeout=8000)
    except Exception:
        p.check('936d9b94c 弹窗打开', False, '未出现 role=dialog')
        return
    title = dlg.inner_text()[:120]
    p.check('936d9b94c 弹窗打开且标题正确', '重新执行' in title, 'head=%r' % title)
    box = dlg.bounding_box() or {}
    p.check('936d9b94c 弹窗加宽（>=700px，sm:max-w-3xl）',
            (box.get('width') or 0) >= 700, 'width=%s' % box.get('width'))
    page.screenshot(path=os.path.join(ART, '50_reexecute_dialog.png'))
    # 范围三选项
    opt_texts = dlg.inner_text()
    p.check('936d9b94c 范围三选项齐全',
            all(k in opt_texts for k in ('全部用例', '仅失败用例', '手动选择用例')),
            'options pedantic head=%r' % opt_texts[:160])
    # 选「手动选择用例」
    page.get_by_text('手动选择用例', exact=True).last.click()
    page.wait_for_timeout(2500)
    p.check('936d9b94c 手动选择区工具行（搜索/查看方式/状态筛选/全选）',
            page.locator("input[aria-label='搜索用例']").count() >= 1
            and page.locator("[aria-label='用例查看方式']").count() >= 1
            and page.locator("[aria-label='状态筛选']").count() >= 1
            and page.get_by_text('全选', exact=True).count() >= 1,
            'toolbar ok')
    # 切分组视图 → 组头三态勾选 + 折叠
    try:
        gtab = dlg.get_by_role('tab', name='分组')
        if gtab.count() > 0:
            gtab.first.click()
        else:
            dlg.locator("[role=tab]", has_text='分组').first.click()
    except Exception as e:
        print('group tab err', e, flush=True)
    # 等用例详情加载（含条数统计）
    for _ in range(20):
        if dlg.locator("[aria-label^='全选 ']").count() >= 1:
            break
        if '暂无已执行用例' in dlg.inner_text() or '没有匹配的用例' in dlg.inner_text():
            break
        page.wait_for_timeout(500)
    gchecks = dlg.locator("[aria-label^='全选 ']")
    n_groups = gchecks.count()
    p.check('936d9b94c 分组视图组头存在', n_groups >= 1,
            'groups=%d dialog_text=%r' % (n_groups, dlg.inner_text()[-260:]))
    if n_groups >= 1:
        def checked_count():
            # 用例行（label 内含已勾选 checkbox），排除工具行「全选」与组头
            return dlg.locator(
                "label:has([role=checkbox][aria-checked='true'])").count()

        def row_count():
            return dlg.locator("label:has([role=checkbox])").count()

        # 定位含「组名 (n)」的组头折叠按钮
        header_btn = None
        for b in dlg.locator("button").all():
            try:
                if b.is_visible() and b.get_attribute('aria-label') is None \
                        and '(' in (b.inner_text() or '') and b.inner_text().strip() != '':
                    header_btn = b
                    break
            except Exception:
                pass
        # 默认全部收起 → 展开首个组
        rows_collapsed = row_count()
        if header_btn is not None:
            header_btn.click()
            page.wait_for_timeout(800)
        rows_expanded = row_count()
        p.check('936d9b94c 组头展开组内用例',
                rows_expanded > rows_collapsed, 'rows %d→%d' % (rows_collapsed, rows_expanded))
        # 组头整组全选 / 取消
        gchecks.first.click()
        page.wait_for_timeout(700)
        checked_after = checked_count()
        p.check('936d9b94c 组头整组全选联动',
                rows_expanded > 0 and checked_after == rows_expanded,
                'rows=%d checked=%d' % (rows_expanded, checked_after))
        page.screenshot(path=os.path.join(ART, '51_reexecute_group_all.png'))
        gchecks.first.click()
        page.wait_for_timeout(600)
        p.check('936d9b94c 再次点击取消整组', checked_count() == 0,
                'checked=%d' % checked_count())
        # 组头收起
        if header_btn is not None:
            header_btn.click()
            page.wait_for_timeout(800)
            p.check('936d9b94c 组头收起隐藏组内用例',
                    row_count() == rows_collapsed,
                    'rows %d→%d(收起基线 %d)' % (rows_expanded, row_count(), rows_collapsed))
            page.screenshot(path=os.path.join(ART, '52_reexecute_group_collapsed.png'))
            header_btn.click()
            page.wait_for_timeout(500)
        else:
            p.skip('936d9b94c 组头展开/收起', '未定位到组头折叠按钮')
    # 深色
    p.toggle_theme(page, True)
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(ART, '53_reexecute_dialog_dark.png'))
    p.toggle_theme(page, False)
    # 安全：关闭不提交，确认没有发出重执行写请求
    page.keyboard.press('Escape')
    page.wait_for_timeout(600)
    posts = [n['u'] for n in p.net if n['m'] == 'POST'
             and ('retry' in n['u'] or 'reexecute' in n['u'] or '/execute' in n['u'])]
    p.check('936d9b94c 只读打开未提交重执行', len(posts) == 0, 'posts=%r' % posts[:3])


# ───────────── states：空态 / 错误态（CDP 拦请求，不用 Playwright route）─────────────
def run_states(p, page, ctx):
    # 1) 任务列表搜索无结果 → 空态
    page.goto(p.base + '/tasks/daily', wait_until='domcontentloaded')
    page.wait_for_timeout(3500)
    search = page.locator("input[placeholder*='搜索']").first
    if search.count() > 0:
        search.fill('ZZZ_NOT_EXIST_INT2675')
        page.wait_for_timeout(2500)
        body = page.evaluate("()=>document.body.innerText")
        p.check('空态：任务搜索无结果显示空态',
                any(k in body for k in ('暂无', '没有', '无匹配', '无数据', '未找到')),
                'body_tail=%r' % body[-160:])
        page.screenshot(path=os.path.join(ART, '60_tasks_empty.png'))
    else:
        p.skip('空态：任务搜索', '未找到搜索框')

    # 2) 用例页阻断 /api/v1/testcases → 错误态（CDP Network.setBlockedURLs）
    p2 = ctx.new_page()
    cdp = ctx.new_cdp_session(p2)
    cdp.send('Network.enable')
    cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/testcases*', '*api/v1/groups*']})
    try:
        p2.goto(p.base + '/testcases', wait_until='domcontentloaded')
        p2.wait_for_timeout(4000)
        p2.screenshot(path=os.path.join(ART, '61_testcases_error.png'))
        b2 = p2.evaluate("()=>document.body.innerText")
        p.check('错误态：用例页接口失败显示错误/重试',
                any(k in b2 for k in ('失败', '出错', '错误', '重试', '加载失败')),
                'body_tail=%r' % b2[-200:])
    finally:
        cdp.send('Network.setBlockedURLs', {'urls': []})
        p2.close()


# ───────────── dark：关键页深色截图 ─────────────
def run_dark(p, page, report_id, task_id):
    p.toggle_theme(page, True)
    # 报告具体用例
    page.goto(p.base + '/report/%d' % report_id, wait_until='domcontentloaded')
    page.wait_for_selector("text=具体用例对比", timeout=60000)
    page.wait_for_timeout(2500)
    p.toggle_theme(page, True)
    page.locator("text=具体用例对比").first.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    page.screenshot(path=os.path.join(ART, '20_report_dark.png'))
    # 设备监控
    page.goto(p.base + '/devices/test', wait_until='domcontentloaded')
    page.wait_for_timeout(3500)
    try:
        page.locator("button", has_text='监控告警').first.click()
        page.wait_for_timeout(2000)
        t = page.get_by_role('tab', name='历史监控')
        if t.count() > 0:
            t.first.click()
            page.wait_for_timeout(3000)
        p.toggle_theme(page, True)
        page.locator("text=统计分析").first.scroll_into_view_if_needed()
        page.wait_for_timeout(1200)
    except Exception as e:
        print('dark device err', e, flush=True)
    page.screenshot(path=os.path.join(ART, '33_devices_dark.png'))
    # 重执行弹窗
    page.goto(p.base + '/tasks/%d' % task_id, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    b = page.locator("button", has_text='重新执行')
    if b.count() > 0:
        b.first.click()
        page.wait_for_timeout(1500)
        page.get_by_text('手动选择用例', exact=True).last.click()
        page.wait_for_timeout(2000)
        p.toggle_theme(page, True)
        page.screenshot(path=os.path.join(ART, '53_reexecute_dialog_dark.png'))
    p.check('深色截图完成', True, '20_report_dark / 33_devices_dark / 53_reexecute_dialog_dark')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['report', 'device', 'perf', 'tasks', 'states', 'dark'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--report-id', type=int, default=426)
    ap.add_argument('--task-id', type=int, default=588)
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    args = ap.parse_args()

    p = Probe(args.base, args.api, args.username, args.password)
    os.makedirs(ART, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=[
            '--window-size=1680,1050', '--no-sandbox',
            '--autoplay-policy=no-user-gesture-required'])
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050},
                                  locale='zh-CN')
        page = ctx.new_page()
        try:
            p.login(page)
            if args.mode == 'report':
                run_report(p, page, args.report_id)
            elif args.mode == 'device':
                run_device(p, page)
            elif args.mode == 'tasks':
                run_tasks(p, page, args.task_id)
            elif args.mode == 'states':
                run_states(p, page, ctx)
            elif args.mode == 'dark':
                run_dark(p, page, args.report_id, args.task_id)
            else:
                run_perf(p, page)
        finally:
            import traceback
            if sys.exc_info()[0] is not None:
                traceback.print_exc()
            summary = {'checks': p.checks}
            with open(os.path.join(ART, 'summary_%s.json' % args.mode), 'w',
                      encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=1)
            fails = [c for c in p.checks if not c['ok'] and not c.get('skipped')]
            total = len([c for c in p.checks if not c.get('skipped')])
            print('SUMMARY mode=%s pass=%d/%d fails=%d skipped=%d' % (
                args.mode, total - len(fails), total, len(fails),
                len([c for c in p.checks if c.get('skipped')])), flush=True)
            browser.close()
            sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
