# -*- coding: utf-8 -*-
"""INT-1919 前端回归冒烟（React 15173 / 新Vue 16173），docker 真实库栈。

在 INT-1854 脚本（smoke_frontend_int1854.py）基础上按当前两个前端的真实入口校正：
  - INT-1854 版脚本按旧 Vue / 更早 React 的选择器写死，2026-10-26 冒烟时四处误判
    （用例详情入口只在任务域的用例行上、React 导出走弹窗 + POST、Vue 导出是
    「导出 HTML」下拉且纯前端打包、Vue 开始测试无「已显示 X / N 个分组」文案）。
  - 本脚本沿用 INT-1854 的登录 / 环境守卫 / 截图 / Network 取证，只替换误判的四条链路。

五条链路（卡 INT-1919）：
  1 登录 / 会话保持 / 登出
  2 任务列表 → 任务详情（React：报告区计数 vs /reports/by_task；Vue：详情抽屉 + 列表「查看报告」入口）
  3 用例列表（分组展开 / 轮次 / 音频动作）→ 用例详情弹窗（维度 / 轮次 / 音频）
  4 报告中心 → 报告详情 / 导出（React：导出弹窗 + POST /reports/export；Vue：导出 HTML 下载 zip）
  5 开始测试入口 + 分组数与 /api/v1/groups 一致（不提交执行）

跑法：
  <conda python> tests/ui/smoke_frontend_int1919.py --kind react --base http://localhost:15173
  <conda python> tests/ui/smoke_frontend_int1919.py --kind vue   --base http://localhost:16173
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import smoke_frontend_int1854 as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART_ROOT = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1919')


class Smoke1919(B.Smoke):
    # ── 2 任务列表 → 任务详情 ───────────────────────────────
    def chain_tasks(self):
        if not self.vue:
            out = super(Smoke1919, self).chain_tasks()
            return out
        d = self.drv
        out = {'ok': False, 'steps': {}, 'api_errors': []}
        d.get(self.url('/tasks'))
        time.sleep(3)
        B.WebDriverWait(d, 60).until(
            lambda dd: len([b for b in dd.find_elements(By.TAG_NAME, 'button')
                            if b.is_displayed() and b.text.strip() == '查看详情']) > 0)
        B.wait_quiet(d, 30)
        st, tasks = B.http_json('/tasks?page=1&per_page=10')
        api_total = (tasks.get('data') or {}).get('total')
        rows = [b for b in d.find_elements(By.TAG_NAME, 'button')
                if b.is_displayed() and b.text.strip() == '查看详情']
        report_btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
                       if b.is_displayed() and b.text.strip() == '查看报告']
        m = re.search(r'共\s*(\d+)\s*条', B.body_text(d))
        out['steps']['list'] = {'api_total': api_total, 'row_count': len(rows),
                                'total_in_page': m.group(1) if m else None,
                                'report_entries': len(report_btns)}
        list_apis = B.parse_perf(d.get_log('performance'))
        out['list_apis'] = [a for a in list_apis if '/tasks' in (a.get('url') or '')][:6]
        out['shot_list'] = B.shot(d, '03_vue_task_list')
        # 任务详情抽屉（Vue 口径：进度 / 关联用例 / 日志，见 UX设计规范-VUE 对齐总表 D02）
        B.click_js(d, rows[0])
        time.sleep(6)
        B.wait_quiet(d, 30)
        dtxt = B.body_text(d)
        out['steps']['detail'] = {
            'url': d.current_url,
            'has_title': '任务名称' in dtxt,
            'has_cases': ('用例清单' in dtxt) or ('用例视图' in dtxt),
            'has_ai_report_entry': '生成 AI 报告' in dtxt,
            'text_tail': dtxt[-500:],
        }
        out['shot_detail'] = B.shot(d, '04_vue_task_detail')
        out['detail_apis'] = B.parse_perf(d.get_log('performance'))
        self.set_theme(True)
        B.shot(d, '04_vue_task_detail_dark')
        self.set_theme(False)
        out['api_errors'] = B.api_errors(list_apis)
        det = out['steps']['detail']
        out['ok'] = (out['steps']['list']['row_count'] > 0 and det['has_title']
                     and det['has_cases'] and out['steps']['list']['report_entries'] > 0)
        return out

    # ── 3 用例列表 + 用例详情弹窗 ───────────────────────────
    def open_group(self):
        """用例管理/开始测试共用：展开首个分组，摊平用例卡。"""
        d = self.drv
        st, gr = B.http_json('/groups?page=1&per_page=100')
        names = [g.get('name') for g in ((gr.get('data') or {}).get('items') or [])][:6]
        for gname in names:
            if not gname:
                continue
            cands = d.execute_script("""
              const name = arguments[0]; const out = [];
              for (const el of document.querySelectorAll('div,section,article,li')) {
                const t = (el.innerText || '').trim();
                if (!t.startsWith(name) || t.length > 160) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 400 || r.height > 220) continue;
                out.push(el);
              }
              return out.slice(-1);
            """, gname)
            if not cands:
                continue
            B.click_js(d, cands[0])
            time.sleep(4)
            B.wait_quiet(d, 25)
            if re.search(r'\d+\s*轮', B.body_text(d)):
                return True
        return False

    def open_case_detail_from_task(self, task_id):
        """任务域用例行 → 用例详情弹窗（两前端同一语义入口）。"""
        d = self.drv
        rec = {'ok': False}
        if self.vue:
            d.get(self.url('/tasks'))
            time.sleep(5)
            B.wait_quiet(d, 30)
            rows = [b for b in d.find_elements(By.TAG_NAME, 'button')
                    if b.is_displayed() and b.text.strip() == '查看详情']
            if not rows:
                rec['error'] = '任务列表无「查看详情」'
                return rec
            B.click_js(d, rows[0])
            time.sleep(6)
            B.wait_quiet(d, 30)
        else:
            d.get(self.url('/tasks/%s' % task_id))
            time.sleep(6)
            B.wait_quiet(d, 30)
        txt_before = B.body_text(d)
        rec['task_text_has_case'] = '用例' in txt_before
        # 展开「用例清单 / 关联用例」折叠区（两前端默认收起，用例行不渲染）
        rec['expand'] = d.execute_script("""
          const out = [];
          for (const el of document.querySelectorAll('[role=button],button,div[class*=collapse],.tab-btn')) {
            const t = (el.innerText||'').trim();
            if (!t || !/^(用例清单|关联用例)/.test(t)) continue;
            const r = el.getBoundingClientRect();
            if (r.width < 30 || r.height < 10) continue;
            el.click();
            out.push(t.slice(0,24));
          }
          return out;
        """)
        time.sleep(3)
        B.wait_quiet(d, 20)
        hit = d.execute_script("""
          // ① React：任务详情用例行按钮 title=查看用例详情
          for (const el of document.querySelectorAll('[title^="查看用例详情"]')) {
            const r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 6) continue;
            el.click();
            return {sel: 'title=查看用例详情', tag: el.tagName, text: (el.innerText||'').slice(0,50)};
          }
          // ② Vue：任务域用例卡整卡 click（.case-name 上 @click.stop 会吞掉事件）
          for (const el of document.querySelectorAll('.task-case-card')) {
            const r = el.getBoundingClientRect();
            if (r.width < 200 || r.height < 20) continue;
            el.click();
            return {sel: '.task-case-card', tag: el.tagName, text: (el.innerText||'').trim().slice(0,50)};
          }
          return null;
        """)
        rec['clicked'] = hit
        time.sleep(6)
        B.wait_quiet(d, 25)
        dtxt = B.body_text(d)
        rec['dialog_text_head'] = dtxt[:400]
        rec['has_dimension'] = '维度' in dtxt
        rec['has_rounds'] = bool(re.search(r'第\s*\d+\s*/\s*\d+\s*轮|\d+\s*轮', dtxt))
        rec['has_audio'] = any(k in dtxt for k in ('音频', '试听', '播放'))
        rec['overlay'] = d.execute_script("""
          const out = [];
          for (const el of document.querySelectorAll('[role=dialog],[role=alertdialog],[class*=modal],[class*=dialog],[class*=drawer]')) {
            const r = el.getBoundingClientRect();
            if (r.width > 200 && r.height > 100) out.push({cls: (el.className||'').toString().slice(0,60),
              w: Math.round(r.width), h: Math.round(r.height), text: (el.innerText||'').replace(/\\n+/g,' | ').slice(0,300)});
          }
          return out.slice(0, 4);
        """)
        rec['shot'] = B.shot(d, '06_%s_case_detail' % self.kind)
        rec['apis'] = B.parse_perf(d.get_log('performance'))
        rec['ok'] = bool(rec['has_dimension'] and rec['has_rounds'] and rec['has_audio']
                         and rec['overlay'])
        return rec

    def chain_cases(self):
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/testcases'))
        time.sleep(5)
        B.wait_quiet(d, 40)
        out['expanded'] = self.open_group()
        txt = B.body_text(d)
        out['rounds_visible'] = bool(re.search(r'\d+\s*轮', txt))
        out['cases_visible'] = ('测试用例_' in txt) or ('用例' in txt)
        # 音频动作：React 卡片「预览音频」按钮；Vue 卡片试听/播放动作
        audio_actions = []
        for b in d.find_elements(By.TAG_NAME, 'button'):
            try:
                if not b.is_displayed():
                    continue
            except Exception:
                continue
            lab = (b.get_attribute('title') or '') + (b.get_attribute('aria-label') or '')
            if any(k in lab for k in ('预览音频', '试听', '播放')):
                audio_actions.append(lab[:30])
        out['audio_actions'] = audio_actions[:5]
        out['list_apis'] = [a for a in B.parse_perf(d.get_log('performance'))
                            if '/testcases' in (a.get('url') or '') or '/groups' in (a.get('url') or '')][:6]
        out['shot_list'] = B.shot(d, '05_%s_case_list' % self.kind)
        self.set_theme(True)
        d.refresh()
        time.sleep(4)
        out['shot_list_dark'] = B.shot(d, '05_%s_case_list_dark' % self.kind)
        self.set_theme(False)
        # 用例详情弹窗（任务域用例行入口，两前端同一分道）
        # INT-2136：原先写死任务 658，当前库已无该 id（404 任务不存在）→
        # 前端渲染「任务详情加载失败」，链路恒假失败。改为按 API 现查一条有
        # 用例结果的任务（/tasks/{id}/stats 的 total>0）。
        task_id = self._pick_task_with_cases()
        out['detail_task_id'] = task_id
        if task_id:
            out['detail'] = self.open_case_detail_from_task(task_id)
        else:
            out['detail'] = {'ok': False, 'error': '未找到有用例结果的任务'}
        out['ok'] = bool(out['expanded'] and out['rounds_visible'] and out['cases_visible']
                         and out['detail'].get('ok'))
        return out

    def _pick_task_with_cases(self):
        """现查一条有真实用例结果的任务 id（只读；取不到返回 None）。"""
        try:
            st, tj = B.http_json('/tasks?page=1&per_page=20&sort_by=created_at&order=desc')
            items = (tj.get('data') or {}).get('items') or []
            for item in items[:10]:
                tid = item.get('id')
                if not tid:
                    continue
                st2, stj = B.http_json('/tasks/%s/stats' % tid)
                if st2 == 200 and ((stj.get('data') or {}).get('total') or 0) > 0:
                    return tid
        except Exception as exc:
            B.log('pick task failed: %s' % exc)
        return None

    # ── 4 报告中心 → 报告详情 / 导出 ────────────────────────
    def chain_reports(self):
        if not self.vue:
            return super(Smoke1919, self).chain_reports()
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/report-center'))
        time.sleep(5)
        B.wait_quiet(d, 40)
        txt = B.body_text(d)
        m = re.search(r'共\s*(\d+)\s*个报告', txt)
        out['center_total_in_page'] = m.group(1) if m else None
        st, rc = B.http_json('/reports?page=1&per_page=20&sort_by=created_at&order=desc&deleted=false')
        items = (rc.get('data') or {}).get('items') or []
        out['api_total'] = (rc.get('data') or {}).get('total')
        out['api_reports_shown'] = len(items)
        out['shot_center'] = B.shot(d, '07_vue_report_center')
        target = next((i for i in items if i.get('status') == 'published'), items[0] if items else None)
        if target is None:
            out['error'] = '报告列表为空'
            return out
        out['report'] = {'id': target.get('id'), 'name': (target.get('name') or '')[:40],
                         'status': target.get('status')}
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and b.text.strip() == '查看':
                B.click_js(d, b)
                break
        time.sleep(7)
        B.wait_quiet(d, 40)
        dtxt = B.body_text(d)
        m_id = re.search(r'/report/(\d+)', d.current_url)
        rid = m_id.group(1) if m_id else None
        rec_api = None
        if rid:
            st2, rj = B.http_json('/reports/%s' % rid)
            rec_api = ((rj.get('data') or {}).get('name') or '')[:40] if st2 == 200 else None
        out['detail'] = {'url': d.current_url, 'report_id': rid, 'api_name': rec_api,
                         'has_name': bool(rec_api and rec_api[:12] in dtxt),
                         'text_head': dtxt[:300]}
        out['detail_apis'] = B.parse_perf(d.get_log('performance'))
        out['shot_detail'] = B.shot(d, '08_vue_report_detail')
        out['export'] = self.export_vue_html(d)
        self.set_theme(True)
        time.sleep(2)
        out['shot_detail_dark'] = B.shot(d, '08_vue_report_detail_dark')
        self.set_theme(False)
        out['ok'] = (bool(out['detail']['url']) and out['detail']['has_name']
                     and out['export'].get('ok'))
        return out

    def export_vue_html(self, d):
        """Vue：报告详情浮动「导出」下拉 → 导出 HTML → 前端 JSZip 打包下载 zip。"""
        rec = {'ok': False}
        try:
            btn = d.execute_script("""
              for (const el of document.querySelectorAll('.rv-action-btn')) {
                if ((el.getAttribute('title')||'') === '导出') { el.click(); return true; }
              }
              return false;
            """)
            rec['export_btn_clicked'] = btn
            time.sleep(2)
            menu = d.execute_script("""
              const out = [];
              for (const el of document.querySelectorAll('.rv-export-menu-item')) out.push((el.innerText||'').trim());
              return out;
            """)
            rec['menu_items'] = menu
            if not menu:
                rec['error'] = '导出下拉未展开'
                return rec
            before = set(os.listdir(self.download_dir))
            ok_click = d.execute_script("""
              for (const el of document.querySelectorAll('.rv-export-menu-item')) {
                if ((el.innerText||'').includes('HTML')) { el.click(); return true; }
              }
              return false;
            """)
            rec['html_clicked'] = ok_click
            deadline = time.time() + 90
            got = None
            while time.time() < deadline:
                new = [f for f in (set(os.listdir(self.download_dir)) - before)
                       if not f.endswith('.crdownload')]
                if new:
                    got = new[0]
                    break
                time.sleep(1)
            rec['downloaded'] = got
            if got:
                rec['size'] = os.path.getsize(os.path.join(self.download_dir, got))
            rec['toast'] = [ln for ln in B.body_text(d).split('\n') if '导出' in ln][:5]
            rec['ok'] = bool(got and rec.get('size', 0) > 1000)
            B.shot(d, '08_vue_export_done')
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        return rec

    # ── 5 开始测试入口 + 分组数一致 ─────────────────────────
    def chain_start_test(self):
        if not self.vue:
            return super(Smoke1919, self).chain_start_test()
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/start-test'))
        time.sleep(6)
        B.wait_quiet(d, 40)
        txt = B.body_text(d)
        out['url'] = d.current_url
        out['text_head'] = txt[:300]
        out['steps_visible'] = ('选择测试用例' in txt) or ('选择用例' in txt)
        apis = B.parse_perf(d.get_log('performance'))
        out['group_requests'] = [a for a in apis if '/groups' in (a.get('url') or '')]
        out['shot'] = B.shot(d, '09_vue_start_test')
        st, g = B.http_json('/groups?page=1&per_page=1000')
        data = g.get('data') or {}
        names = [x.get('name') for x in (data.get('items') or []) if x.get('name')]
        api_groups = data.get('total') or len(names)
        # 页面上分组筛选 chip：可见名 + 「更多 (N)」折叠数
        page_buttons = [((b.text or '').strip()) for b in d.find_elements(By.TAG_NAME, 'button')
                        if b.is_displayed()]
        present = [n for n in names if any(n == t or n in t for t in page_buttons)]
        more = None
        for t in page_buttons:
            mm = re.search(r'更多\s*\((\d+)\)', t)
            if mm:
                more = int(mm.group(1))
                break
        ui_groups = len(present) + (more or 0)
        out['group_compare'] = {'ui_visible': len(present), 'ui_more': more,
                                'ui_total': ui_groups, 'api': api_groups,
                                'missing': [n for n in names if n not in present][:5]}
        out['group_match'] = (ui_groups == api_groups)
        self.set_theme(True)
        d.refresh()
        time.sleep(5)
        B.wait_quiet(d, 30)
        out['shot_dark'] = B.shot(d, '09_vue_start_test_dark')
        self.set_theme(False)
        out['ok'] = bool(out['steps_visible'] and out['group_match'])
        return out

    # ── 编排 ───────────────────────────────────────────────
    def run(self):
        B.env_check('start')
        self.download_dir = os.path.join(B.RESULT['art'], 'downloads')
        os.makedirs(self.download_dir, exist_ok=True)
        self.drv = B.make_driver(self.download_dir)
        d = self.drv
        try:
            B.RESULT['chains']['1_login'] = self.login()
            if not B.RESULT['chains']['1_login'].get('ok'):
                raise AssertionError('登录失败')
            B.RESULT['chains']['1_logout'] = self.logout()
            try:
                B.RESULT['chains']['1_relogin'] = self.login()
            except Exception as exc:
                B.RESULT['chains']['1_relogin'] = {'ok': False, 'error': str(exc)[:300]}
            for name, fn in (('2_tasks', self.chain_tasks),
                             ('3_cases', self.chain_cases),
                             ('4_reports', self.chain_reports),
                             ('5_start_test', self.chain_start_test)):
                try:
                    B.RESULT['chains'][name] = fn()
                except Exception as exc:
                    B.RESULT['chains'][name] = {'ok': False, 'error': '%s: %s' % (type(exc).__name__, str(exc)[:300])}
                    B.log('CHAIN %s ERROR %s' % (name, exc))
                B.log('CHAIN %s ok=%s' % (name, B.RESULT['chains'][name].get('ok')))
            B.RESULT['console_errors'] = B.console_errors(d)
            B.env_check('end')
        finally:
            try:
                d.quit()
            except Exception:
                pass


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--kind', required=True, choices=['react', 'vue'])
    ap.add_argument('--base', required=True)
    args = ap.parse_args()
    os.makedirs(ART_ROOT, exist_ok=True)
    B.RESULT['kind'] = args.kind
    B.RESULT['base'] = args.base.rstrip('/')
    sm = Smoke1919(args.kind, args.base)
    B.RESULT['art'] = os.path.join(ART_ROOT, args.kind)  # __init__ 会用基类 ART_ROOT 覆盖
    sm.run()
    out_path = os.path.join(B.RESULT['art'], 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(B.RESULT, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % out_path)
    for k, v in B.RESULT['chains'].items():
        if isinstance(v, dict):
            print('CHAIN %-14s ok=%s note=%s' % (k, v.get('ok'), (v.get('error') or '')[:120]))


if __name__ == '__main__':
    main()
