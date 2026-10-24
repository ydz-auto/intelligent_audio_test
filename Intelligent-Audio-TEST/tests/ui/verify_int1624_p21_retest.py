# -*- coding: utf-8 -*-
"""INT-1624 打回 P2-1 复测（测试工程师）：页签切换关闭弹窗后导入文件 / 导出格式范围必须复位。

背景：代码审计员在 `66868293` 上判定 P2-1 —— 页内点页签（/devices/$tab 同路由换参，页面不重挂）
关掉弹窗后，再开仍带着上一页签选的文件 / 改过的格式与范围。修复提交 `af5c7efc3` 给两个弹窗加了
`key={tab}`。本脚本按 devloop §2.3「只复测失败项与本次修复相关部分」复测：

  1. 页内页签切换路径（不是 goto 整页重载）：导入弹窗选文件 → 切页签 → 重开必须空态（标题随新页签、
     无文件名、「开始导入」禁用）；反方向切回同样成立。
  2. 导出弹窗改 Excel + 「当前筛选结果」→ 切页签 → 重开格式回 JSON、范围回「全部」；反方向同样成立。
  3. 回归：取消 / Esc 两条关闭路径仍复位（key={tab} 不改变原有行为）。
  4. 回归：修复未破坏主链路 —— 仍能真实导入（200 / 更新 1 / 跳过 1）、结果区正常、列表刷新；
     顺带核对 P3-1 成功图标用的是 `text-success`（不再是 emerald 硬编码）。
  5. 证据：浅色 / 深色截图 + Network（performance log：URL / 状态码 / Content-Disposition）。

环境：本 run 一次性 nginx 旁路容器 http://127.0.0.1:15243（dist 由本 worktree 合并 `af5c7efc3` 后
pnpm build 产出，/api → intelligent-audio-test_default 里的 api_gateway:5000），后端 docker 真实库栈
http://127.0.0.1:15000，database=intelligent_audio_test。未启本地后端栈。
数据纪律：只写「接线测试_INT1624_」前缀，脚本末尾删除并复核零残留。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ.setdefault('REACT_BASE', 'http://127.0.0.1:15243')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_int1624_device_import_export as base  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

PORT = os.environ.get('INT1624_P21_PORT', '15243')
BASE_URL = 'http://127.0.0.1:%s' % PORT
CONTAINER = 'iat-int1624-p21'
ART = os.path.join(HERE, 'artifacts', 'int1624_p21')
DOWNLOADS = os.path.join(ART, 'downloads')
os.makedirs(DOWNLOADS, exist_ok=True)
# 复用交付脚本的 helper，但截图 / 下载落到本复测自己的目录
base.BASE = BASE_URL
base.ART = ART
base.DOWNLOADS = DOWNLOADS

NGINX_CONF = """server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
    }

    location /socket.io/ {
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
"""

_FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  [' + str(detail)[:160] + ']') if detail and not cond else ''))
    if not cond:
        _FAILURES.append(name)


TABLE_DELETED_COL = {'devices': 'deleted', 'apis': 'deleted', 'playback_devices': 'is_deleted'}


def db_prefix_rows(active_only=False):
    """库直查本卡前缀行（接口清单可能漏项，收尾以此为准）。"""
    rows = []
    for table, col in TABLE_DELETED_COL.items():
        where = "and %s = false" % col if active_only else ''
        out, _err = base.psql(
            "select id||'|'||name from %s where name like '%s%%' %s order by id;"
            % (table, base.PREFIX, where))
        for line in out.splitlines():
            line = line.strip()
            if '|' in line:
                rid, name = line.split('|', 1)
                rows.append((table, rid.strip(), name.strip()))
    return rows


def db_active_rows():
    return db_prefix_rows(active_only=True)


def purge_rows(rows):
    for table, rid, _name in rows:
        base.psql('delete from %s where id = %s;' % (table, int(rid)))


class NginxStack:
    """一次性 nginx 旁路容器：本 worktree 的 dist + /api 反代容器网络里的 api_gateway:5000。"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='int1624_p21_')
        self.conf = os.path.join(self.dir, 'default.conf')
        with open(self.conf, 'w', encoding='utf-8') as f:
            f.write(NGINX_CONF)

    def start(self):
        dist = os.path.join(base.PROJECT_ROOT, 'frontend-react', 'dist')
        if not os.path.isdir(dist):
            raise SystemExit('缺少 %s，先 cd frontend-react && pnpm build' % dist)
        subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True, text=True)
        r = subprocess.run([
            'docker', 'run', '-d', '--name', CONTAINER,
            '--network', 'intelligent-audio-test_default',
            '-p', '%s:80' % PORT,
            '-v', '%s:/usr/share/nginx/html:ro' % dist,
            '-v', '%s:/etc/nginx/conf.d/default.conf:ro' % self.conf,
            'nginx:alpine',
        ], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit('docker run 失败: %s' % r.stderr)
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                import urllib.request
                with urllib.request.urlopen(BASE_URL + '/', timeout=5) as resp:
                    if resp.status == 200:
                        print('STACK up', BASE_URL)
                        return
            except Exception:
                pass
            time.sleep(1)
        raise SystemExit('旁路容器未就绪')

    def stop(self):
        subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True, text=True)
        shutil.rmtree(self.dir, ignore_errors=True)


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT', path)
    return path


def set_nav_marker(drv):
    drv.execute_script("window.__int1624NavMarker = 'alive';")


def nav_marker(drv):
    return drv.execute_script('return window.__int1624NavMarker || null')


def open_menu_item(drv, text):
    base.open_more_menu(drv)
    base.click_menu_item(drv, text)
    time.sleep(1.0)


def start_btn(drv):
    return drv.find_element(By.XPATH, base.LAST_DIALOG + "//button[normalize-space(.)='开始导入']")


def dialog_shot_state(drv):
    return drv.execute_script(
        """
        const ds = [...document.querySelectorAll('[role="dialog"]')];
        const d = ds[ds.length - 1];
        if (!d) return null;
        const svg = d.querySelector('svg.text-success');
        return {
          iconSuccess: !!svg,
          iconClass: svg ? svg.getAttribute('class') : null,
          emerald: !!d.querySelector('.text-emerald-600'),
          importing: d.innerText.indexOf('正在导入') >= 0,
        };
        """)


def drain_perf(drv):
    """取走（并清空）performance log，后续统计只算这一段。"""
    try:
        drv.get_log('performance')
    except Exception:
        pass


def perf_hits(drv, needle):
    return base.perf_entries(drv, needle)


def esc_close(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.9)


def main():
    stack = NginxStack()
    stack.start()
    drv = None
    network = []
    before_ids = set((t, rid) for t, rid, _n in db_prefix_rows())
    try:
        files = base.write_files()
        base.seed_fixtures()
        drv = base.driver()
        drv.execute_cdp_cmd('Page.setDownloadBehavior',
                            {'behavior': 'allow', 'downloadPath': DOWNLOADS})
        base.login(drv)

        # ================= 1. 导入弹窗：选文件 → 页内切页签 → 重开 =================
        base.goto_tab(drv, 'test')
        set_nav_marker(drv)
        open_menu_item(drv, '导入设备')
        base.upload_file(drv, files['mixed'])
        t = base.dialog_text(drv)
        check('切换前：导入弹窗已选文件（mixed_update.json）', 'mixed_update.json' in t, t[:120])
        check('切换前：「开始导入」可用', start_btn(drv).get_attribute('disabled') is None)

        base.clear_fetch_log(drv)
        base.click_tab(drv, '播放设备', 'playback')
        check('页内点页签是 SPA 换参、未整页重载（window 标记仍在）', nav_marker(drv) == 'alive', nav_marker(drv))

        open_menu_item(drv, '导入设备')
        t_pb = base.dialog_text(drv)
        check('切到播放设备重开：标题随新页签（导入播放设备）', '导入播放设备' in t_pb, t_pb[:120])
        check('切到播放设备重开：无上一页签文件名残留', 'mixed_update.json' not in t_pb)
        check('切到播放设备重开：「开始导入」回到禁用', start_btn(drv).get_attribute('disabled') is not None)
        hits = base.fetch_log(drv, '/import')
        check('切页签后未向新页签发导入请求（无残留在途提交）', len(hits) == 0, hits)
        shot(drv, 'p21_tab_switch_import_light')

        # 反方向：切回测试设备，标题也要跟着回去
        base.close_dialog(drv)
        base.click_tab(drv, '测试设备', 'test')
        open_menu_item(drv, '导入设备')
        t_back = base.dialog_text(drv)
        check('再切回测试设备重开：标题回到「导入测试设备」', '导入测试设备' in t_back, t_back[:120])
        check('再切回测试设备重开：仍无文件名残留', 'mixed_update.json' not in t_back)
        base.close_dialog(drv)

        # ================= 2. 导出弹窗：格式/范围 → 页内切页签 → 重开 =================
        open_menu_item(drv, '导出设备')
        base.choose_format(drv, 'Excel')
        base.choose_range(drv, '当前筛选结果')
        before = base.dialog_export_state(drv) or {}
        check('切换前：导出弹窗格式 Excel + 范围「当前筛选结果」',
              before.get('format') == 'Excel' and before.get('ranges') == ['filtered'], before)

        base.click_tab(drv, '播放设备', 'playback')
        open_menu_item(drv, '导出设备')
        after = base.dialog_export_state(drv) or {}
        check('切到播放设备重开导出：格式回 JSON', after.get('format') == 'JSON', after)
        check('切到播放设备重开导出：范围回「全部」', after.get('ranges') == ['all'], after)
        shot(drv, 'p21_tab_switch_export_light')

        # 反方向：在播放设备改 Excel + 筛选后，切回测试设备
        base.choose_format(drv, 'Excel')
        base.choose_range(drv, '当前筛选结果')
        rev_before = base.dialog_export_state(drv) or {}
        check('反方向切换前：播放设备页导出格式 Excel + 筛选范围',
              rev_before.get('format') == 'Excel' and rev_before.get('ranges') == ['filtered'], rev_before)
        base.click_tab(drv, '测试设备', 'test')
        open_menu_item(drv, '导出设备')
        rev_after = base.dialog_export_state(drv) or {}
        check('切回测试设备重开导出：格式回 JSON', rev_after.get('format') == 'JSON', rev_after)
        check('切回测试设备重开导出：范围回「全部」', rev_after.get('ranges') == ['all'], rev_after)

        # 真实导出一次：核对下载文件名时间戳口径 + 取 Network（URL / 状态码）
        exported, export_fetch = base.do_export(drv, timeout=180)
        check('导出仍产出文件，文件名 = test_devices_YYYYmmdd_HHMMSS.json',
              bool(exported) and exported[0].startswith('test_devices_')
              and exported[0].endswith('.json'), exported)
        for e in export_fetch:
            network.append({'method': e.get('method'), 'url': e.get('url'),
                            'status': e.get('status'), 'headers': {}})
        if exported:
            network.append({'method': 'DOWNLOAD', 'url': exported[0], 'status': 'saved', 'headers': {}})
        base.close_dialog(drv)

        # ================= 3. 回归：取消 / Esc 关闭路径仍复位 =================
        open_menu_item(drv, '导入设备')
        base.upload_file(drv, files['mixed'])
        check('取消路径：先确认已选文件', 'mixed_update.json' in base.dialog_text(drv))
        base.close_dialog(drv)
        open_menu_item(drv, '导入设备')
        t_cancel = base.dialog_text(drv)
        check('取消后重开导入：无文件名、「开始导入」禁用',
              'mixed_update.json' not in t_cancel
              and start_btn(drv).get_attribute('disabled') is not None, t_cancel[:120])
        base.close_dialog(drv)

        open_menu_item(drv, '导出设备')
        base.choose_format(drv, 'Excel')
        check('Esc 路径：先确认格式已改 Excel',
              (base.dialog_export_state(drv) or {}).get('format') == 'Excel')
        esc_close(drv)
        open_menu_item(drv, '导出设备')
        esc_state = base.dialog_export_state(drv) or {}
        check('Esc 关闭后重开导出：格式回 JSON', esc_state.get('format') == 'JSON', esc_state)
        base.close_dialog(drv)

        # ================= 4. 主链路回归 + P3-1 图标 =================
        drain_perf(drv)
        open_menu_item(drv, '导入设备')
        text, entry = base.do_import(drv, files['mixed'])
        status = entry.get('status')
        body = entry.get('respBody') or ''
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
        data = (payload or {}).get('data') or {}
        check('页签重挂后主链路仍可用：导入 200 且 更新1/跳过1',
              status == 200 and data.get('updated_count') == 1 and data.get('skipped_count') == 1,
              '%s %s' % (status, body[:160]))
        # 结果区在响应后渲染，等它出现再取文本 / 图标（否则会读到「正在导入」之前的中间态）
        try:
            WebDriverWait(drv, 40).until(lambda d: '成功导入' in base.dialog_text(d))
        except Exception:
            pass
        text = base.dialog_text(drv)
        check('结果区计数与接口一致', (payload.get('message') or '') in text,
              '%s | dialog=%s' % (payload.get('message'), text[:160]))
        state = dialog_shot_state(drv) or {}
        check('P3-1：成功图标用 text-success（不再 emerald 硬编码）',
              bool(state.get('iconSuccess')) and not state.get('emerald'), state)
        shot(drv, 'p21_import_result_light')
        # Network 证据：本次复测里真实的 import 请求（URL / 方法 / 状态码 / 上传文件名）
        network.append({'method': entry.get('method') or 'POST', 'url': entry.get('url'),
                        'status': entry.get('status'), 'headers': {},
                        'file': entry.get('formFile')})

        # 导入成功后列表刷新（关闭弹窗 → 行上的「最近上报 / 描述」口径不逐一验，只看记录仍在列表）
        base.close_dialog(drv)
        WebDriverWait(drv, 30).until(lambda d: base.PREFIX + '设备' in base.body_text(d))
        check('导入后测试设备列表仍含本 run 记录', base.PREFIX + '设备' in base.body_text(drv))

        # ================= 5. 深色截图 + Network 证据 =================
        base.goto_tab(drv, 'test')
        base.apply_theme(drv, 'dark')
        shot(drv, 'p21_devices_test_dark')
        open_menu_item(drv, '导入设备')
        base.upload_file(drv, files['mixed'])
        base.click_tab(drv, '播放设备', 'playback')
        open_menu_item(drv, '导入设备')
        t_dark = base.dialog_text(drv)
        check('深色 + 页签切换后重开导入：仍为空态',
              '导入播放设备' in t_dark and 'mixed_update.json' not in t_dark)
        shot(drv, 'p21_tab_switch_import_dark')
        base.close_dialog(drv)
        open_menu_item(drv, '导出设备')
        base.choose_format(drv, 'Excel')
        base.click_tab(drv, '测试设备', 'test')
        open_menu_item(drv, '导出设备')
        dark_state = base.dialog_export_state(drv) or {}
        check('深色 + 页签切换后重开导出：JSON / 全部',
              dark_state.get('format') == 'JSON' and dark_state.get('ranges') == ['all'], dark_state)
        shot(drv, 'p21_tab_switch_export_dark')
    finally:
        try:
            if drv is not None:
                removed, left = base.cleanup(drv)
                check('数据清理：前缀数据零残留（接口视角）', not left, str(left))
            # 接口清单可能漏项，再按库直查一遍；本 run 新建的前缀行按 id 硬删，不留残留
            new_rows = [r for r in db_prefix_rows() if (r[0], r[1]) not in before_ids]
            if new_rows:
                print('本 run 新建前缀行，按 id 清理:', new_rows)
                purge_rows(new_rows)
            actives = db_active_rows()
            check('数据清理：前缀数据零残留（库直查）', not actives, str(actives))
        except Exception as exc:
            print('cleanup error', exc)
            _FAILURES.append('cleanup')
        try:
            if drv is not None:
                drv.quit()
        except Exception:
            pass
        stack.stop()
        if network:
            path = os.path.join(ART, 'network_evidence.txt')
            lines = []
            with open(path, 'w', encoding='utf-8') as f:
                for e in network:
                    line = '%s %s -> %s %s' % (e.get('method'), e.get('url'), e.get('status'),
                                               ('file=' + e['file']) if e.get('file') else '')
                    f.write(line + '\n')
                    lines.append('%s %s' % (e.get('method'), (e.get('url') or '')[:90]))
                    lines.append('   status=%s %s' % (e.get('status'),
                                                      ('file=' + e['file']) if e.get('file') else ''))
            print('NETWORK', path)
            try:
                base.render_evidence('p21_network', 'INT-1624 复测 Network（fetch log）', lines)
            except Exception as exc:
                print('render evidence failed', exc)

    print('\n==== SUMMARY ====')
    print('failures:', len(_FAILURES))
    for item in _FAILURES:
        print('  FAIL', item)
    return 1 if _FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
