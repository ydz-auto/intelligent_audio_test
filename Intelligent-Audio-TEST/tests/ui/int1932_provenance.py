# -*- coding: utf-8 -*-
"""INT-1932 第 4 项：取证出处核对（页面地址与实际栈一致）。

INT-1545 的证据页头写「dev server 5345」，而抓包 URL 全为 15173（出处矛盾）。
本脚本在 docker 15173 栈上重取等价证据：
  - 页面 + 弹窗截图右上角水印写入当前真实 URL（document.location.href）
  - 记录 index/lib-react 指纹、nginx 反代契约、以及 /tasks/527 在本栈的 404 事实
"""
import json, os, subprocess, sys, time, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1932_ai_review_success as M

ART = M.ART
out = {}


def sh(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True)
    return (p.stdout or b'').decode('utf-8', 'replace').strip()


d = M.driver()
try:
    out['page_base'] = M.BASE
    out['api_base_host'] = M.API
    out['login'] = M.login(d)
    out['nginx_api_proxy'] = sh(
        "docker exec iat-react-frontend sh -c \"grep -A1 'location /api/' /etc/nginx/conf.d/default.conf\"")
    out['tailscale'] = None
    out['container_image'] = sh("docker inspect iat-react-frontend --format '{{.Config.Image}}'")
    out['container_created'] = sh("docker inspect iat-react-frontend --format '{{.Created}}'")
    out['image_created'] = sh("docker image inspect iat-react-frontend:latest --format '{{.Created}}'")
    # 1) /tasks/527（INT-1545 目标容器任务）在本栈的实际结果
    d.get(M.BASE + '/tasks/527')
    time.sleep(8)
    out['task527_url'] = d.current_url
    out['task527_text'] = M.body_text(d)[-400:]
    out['shots_527'] = [M.shot(d, '50_task527_404', f'INT-1545 目标任务在本栈 URL={d.current_url}')]
    # 2) 等价证据：任务 419 快速复核弹窗（真实请求同源 15173/api/v1）
    out['task419'] = M.open_task(d)
    M.set_providers(d, M.STUB_BASE)
    row, err = M.open_dialog_via(d, M.T_REJECT['tag'], '快速复核')
    out['quick_open'] = err is None and M.dialog(d, 'quick-ai-review-dialog') is not None
    if out['quick_open']:
        M.clear_log(d)
        M.click_text(d, 'quick-ai-review-dialog', '发起快速复核')
        M.wait_until(lambda: 'AI 复核结论' in M.dlg_text(d, 'quick-ai-review-dialog'), 120, 1.5)
        out['shots_quick'] = M.shot_pair(d, '51_provenance_quick', f'出处核对 URL={d.current_url}')
        out['reqs'] = [
            {'method': e.get('method'), 'url': e.get('url'), 'status': e.get('status')}
            for e in M.relevant(M.fetch_log(d))]
        out['script_hashes'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src)")
        out['location_href'] = d.execute_script('return document.location.href')
        M.click_text(d, 'quick-ai-review-dialog', '驳回')
        time.sleep(1.5)
        if M.dialog(d, 'quick-ai-review-dialog') is not None:
            M.click_text(d, 'quick-ai-review-dialog', '关闭', exact=True)
except Exception:
    out['fatal'] = traceback.format_exc()[-1500:]
finally:
    d.quit()
json.dump(out, open(os.path.join(ART, 'provenance.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1)[:3500])
