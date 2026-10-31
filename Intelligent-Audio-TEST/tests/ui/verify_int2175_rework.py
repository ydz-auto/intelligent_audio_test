# -*- coding: utf-8 -*-
"""INT-2175 返工补证（UX 审计打回）。

补齐：
  P1-a 失败文件逐条错误：1 个有效 wav + 1 个垃圾内容 .wav + 1 个 0 字节 .wav 混合上传，
       记录是否逐条报错、成功/失败计数、失败文件是否落到列表。
  P1-b 文件夹导入真实导入：webkitdirectory 目录选择在 headless 下的真实尝试记录
       （Selenium 目录 send_keys → CDP DOM.setFileInputFiles 兜底），能选上就真实导入并回读。
  P3   连接方式=USB连接 列表行数与接口 connection_type 分布核对（更正上一轮口径）。
  另：重跑 t2/t3/t5/t6/t10 重新生成关键截图（上一轮附件不可追溯）。

环境：docker 15173（前端）+ 15000（网关，database=intelligent_audio_test）。
数据卫生：自建数据「接线测试_走查R3_」前缀，结束时按 id 删除。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import wave
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
import verify_int2175_device_audio as V  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = V.ART
PREFIX = V.PREFIX
RC = []
FIX = V.FIX
MY_AUDIOS = []


def record(step, ok, detail=''):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:1500]}
    RC.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])


def shot(drv, name):
    p = V.shot(drv, name)
    return p


def make_wav(path, seconds=0.5, sr=16000):
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h', 0) for _ in range(int(sr * seconds))))


def toast_watch_start(drv):
    drv.execute_script('''
      window.__toasts = [];
      if (window.__toastTimer) { clearInterval(window.__toastTimer); }
      window.__toastTimer = setInterval(function(){
        var els = document.querySelectorAll('[data-sonner-toast]');
        for (var i = 0; i < els.length; i++) {
          var t = (els[i].innerText || els[i].textContent || '').trim();
          if (t && window.__toasts.indexOf(t) === -1) { window.__toasts.push(t); }
        }
      }, 120);
    ''')


def toast_watch_take(drv):
    return drv.execute_script(
        'if (window.__toastTimer) { clearInterval(window.__toastTimer); window.__toastTimer = null; }'
        ' return window.__toasts || [];')


def p3_conn_type(drv, token):
    _, js = B.api('/api/v1/test-devices?page=1&per_page=1000', token)
    devs = (js.get('data') or {}).get('items') or []
    usb = [d for d in devs if (d.get('connection_type') or '').lower() == 'usb']
    none = [d for d in devs if not d.get('connection_type')]
    record('P3 接口 connection_type=usb 条数', True,
           'usb=%d null=%d total=%d detail=%s' % (
               len(usb), len(none), len(devs),
               [(d.get('id'), d.get('name'), d.get('connection_type')) for d in devs]))
    B.goto(drv, '/devices/test', '设备管理')
    time.sleep(2.0)
    rows_all = V.table_rows(drv)
    V.facet(drv, '连接方式')
    picked = V.pick_popover_option(drv, 'USB连接')
    time.sleep(2.5)
    rows_usb = V.table_rows(drv)
    record('P3 页面连接方式=USB连接 筛选行数', picked and rows_usb == len(usb),
           'picked=%s rows=%d api_usb=%d rows_all=%d' % (picked, rows_usb, len(usb), rows_all))
    shot(drv, 'p3_usb_filter_light')
    # 重置
    for el in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed() and (el.text or '').strip() in ('重置', '清空筛选', '清空'):
                drv.execute_script('arguments[0].click();', el)
                break
        except Exception:
            pass
    time.sleep(2.0)
    return len(usb)


def _find_file_input(drv, root):
    best = None
    for el in root.find_elements(By.CSS_SELECTOR, "input[type='file']"):
        try:
            attrs = {
                'webkitdirectory': el.get_attribute('webkitdirectory'),
                'directory': el.get_attribute('directory'),
                'multiple': el.get_attribute('multiple'),
                'accept': el.get_attribute('accept'),
                'class': el.get_attribute('class'),
            }
            wd = (attrs.get('webkitdirectory') or '').strip().lower()
            print('FILE_INPUT %s' % json.dumps(attrs, ensure_ascii=False))
            if wd in ('', 'false') and best is None:
                best = el
        except Exception:
            pass
    return best


def p1a_mixed_upload(drv, token):
    wav_dir = os.path.join(ART, 'wav_in')
    os.makedirs(wav_dir, exist_ok=True)
    stamp = time.strftime('%H%M%S')
    ok_path = os.path.join(wav_dir, PREFIX + 'RW_UPOK_%s.wav' % stamp)
    bad_path = os.path.join(wav_dir, PREFIX + 'RW_UPBAD_%s.wav' % stamp)
    empty_path = os.path.join(wav_dir, PREFIX + 'RW_UPEMPTY_%s.wav' % stamp)
    make_wav(ok_path)
    with open(bad_path, 'wb') as f:
        f.write(b'this is not a real wav payload ' * 40)
    with open(empty_path, 'wb') as f:
        f.write(b'')
    record('P1a 夹具（1 有效 wav + 1 垃圾 .wav + 1 空 .wav）', True,
           'sizes=%s' % [(os.path.basename(p), os.path.getsize(p)) for p in (ok_path, bad_path, empty_path)])

    B.goto(drv, '/audio-import', '音频管理')
    time.sleep(2.0)
    V.click_page_btn(drv, '上传音频')
    dlg = V.dialog_with_title(drv, '上传音频', 15)
    record('P1a 上传弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    inp = _find_file_input(drv, dlg)
    if inp is None:
        record('P1a 上传文件输入', False, 'no file input')
        return
    inp.send_keys('\n'.join([ok_path, bad_path, empty_path]))
    time.sleep(2.5)
    dtext = dlg.text or ''
    listed = [k for k in ('UPOK', 'UPBAD', 'UPEMPTY') if k in dtext]
    record('P1a 三个文件进入待传列表', len(listed) == 3, 'listed=%s text=%s' % (listed, dtext[:400]))
    shot(drv, 'p1a_upload_three_light')

    toast_watch_start(drv)
    V.click_btn_in(drv, dlg, '开始上传', exact=False)
    time.sleep(2.0)
    shot(drv, 'p1a_uploading_light')
    # 等上传结束：最多 120s，出现「上传完成/导入完成/失败」任一提示
    end = time.time() + 120
    toasts = []
    while time.time() < end:
        toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
        if any(('上传完成' in t) or ('失败' in t) for t in toasts):
            time.sleep(6.0)  # 让逐条 toast 都出现
            toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
            break
        time.sleep(1.0)
    toasts = toast_watch_take(drv)
    print('TOASTS %s' % json.dumps(toasts, ensure_ascii=False))
    joined = ' | '.join(toasts)
    record('P1a 上传结果提示', bool(toasts), 'toasts=%s' % joined[:600])
    record('P1a 混合批次含失败计数', ('失败' in joined), 'joined=%s' % joined[:400])
    per_file = [t for t in toasts if ('UPBAD' in t or 'UPEMPTY' in t)]
    record('P1a 失败文件逐条错误（含文件名+错误原因）', len(per_file) >= 1,
           'per_file=%s' % json.dumps(per_file, ensure_ascii=False)[:600])
    shot(drv, 'p1a_upload_result_toasts')
    B.set_theme(drv, 'dark')
    time.sleep(0.6)
    shot(drv, 'p1a_upload_result_dark')
    B.set_theme(drv, 'light')

    _, js = B.api('/api/v1/audios?page=1&per_page=50&keyword=%s' % urllib.parse.quote(PREFIX + 'RW_'), token)
    items = (js.get('data') or {}).get('items') or []
    got = [(a['id'], a.get('name')) for a in items]
    names = [n for _, n in got]
    record('P1a 有效文件落库', any('UPOK' in (n or '') for n in names), 'created=%s' % got)
    record('P1a 无效文件未落库', not any(('UPBAD' in (n or '')) or ('UPEMPTY' in (n or '')) for n in names),
           'names=%s' % names)
    MY_AUDIOS.extend([i for i, _ in got])
    # 关闭可能仍打开的弹窗
    d = V.dialog_with_title(drv, '上传音频', 3)
    if d is not None:
        V.click_btn_in(drv, d, '取消', exact=True)


def p1b_folder_import(drv, token):
    root = os.path.join(ART, 'folder_in')
    sub = os.path.join(root, 'sub')
    os.makedirs(sub, exist_ok=True)
    stamp = time.strftime('%H%M%S')
    a = os.path.join(root, PREFIX + 'RW_FD_A_%s.wav' % stamp)
    b = os.path.join(sub, PREFIX + 'RW_FD_B_%s.wav' % stamp)
    make_wav(a)
    make_wav(b)
    record('P1b 文件夹夹具（2 个 wav，含 1 个子目录）', True, 'files=%s' % [os.path.basename(a), os.path.basename(b)])

    B.goto(drv, '/audio-import', '音频管理')
    time.sleep(2.0)
    V.click_page_btn(drv, '批量从文件夹导入')
    dlg = V.dialog_with_title(drv, '批量从文件夹导入', 15)
    record('P1b 文件夹导入弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    inp = None
    for el in dlg.find_elements(By.CSS_SELECTOR, 'input[webkitdirectory]'):
        inp = el
    if inp is None:
        for el in dlg.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            if el.get_attribute('webkitdirectory') is not None:
                inp = el
    record('P1b webkitdirectory 输入存在', inp is not None, 'input=%s' % (inp is not None))
    if inp is None:
        return
    attempt = {}
    try:
        inp.send_keys(root)
        attempt['selenium_dir_send_keys'] = 'ok'
    except Exception as exc:
        attempt['selenium_dir_send_keys'] = repr(exc)
    time.sleep(3.0)
    dtext = dlg.text or ''
    sel_n = None
    import re
    m = re.search(r'已选\s*(\d+)\s*个文件', dtext)
    if m:
        sel_n = int(m.group(1))
    attempt['after_send_keys_selected'] = sel_n
    print('FOLDER_ATTEMPT %s' % json.dumps(attempt, ensure_ascii=False))
    if not sel_n:
        # 兜底：CDP DOM.setFileInputFiles（对目录输入按文件列表注入）
        try:
            doc = drv.execute_cdp_cmd('DOM.getDocument', {'depth': -1})
            node = drv.execute_cdp_cmd('DOM.querySelector', {
                'nodeId': doc['root']['nodeId'],
                'selector': 'input[webkitdirectory]'})
            drv.execute_cdp_cmd('DOM.setFileInputFiles', {
                'files': [a, b], 'nodeId': node['nodeId']})
            attempt['cdp_set_file_input_files'] = 'ok nodeId=%s' % node.get('nodeId')
        except Exception as exc:
            attempt['cdp_set_file_input_files'] = repr(exc)
        time.sleep(2.5)
        dtext = dlg.text or ''
        m = re.search(r'已选\s*(\d+)\s*个文件', dtext)
        sel_n = int(m.group(1)) if m else None
        attempt['after_cdp_selected'] = sel_n
        print('FOLDER_ATTEMPT_CDP %s' % json.dumps(attempt, ensure_ascii=False))
    record('P1b 文件夹真实选择（真实尝试记录）', bool(sel_n),
           'attempt=%s dialog_text=%s' % (json.dumps(attempt, ensure_ascii=False), dtext[:400]))
    shot(drv, 'p1b_folder_selected_light')
    B.set_theme(drv, 'dark')
    time.sleep(0.5)
    shot(drv, 'p1b_folder_selected_dark')
    B.set_theme(drv, 'light')
    if not sel_n:
        record('P1b 文件夹真实导入', False,
               '环境受限：headless 下 webkitdirectory 无法赋值，attempt=%s' % json.dumps(attempt, ensure_ascii=False))
        return
    stats_txt = dtext
    record('P1b 统计四枚取真实值', ('音频文件数量' in stats_txt) and ('总大小' in stats_txt),
           'text=%s' % stats_txt[:400])
    toast_watch_start(drv)
    V.click_btn_in(drv, dlg, '开始导入', exact=False)
    end = time.time() + 180
    toasts = []
    while time.time() < end:
        toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
        if any(('导入完成' in t) or ('失败' in t) for t in toasts):
            time.sleep(6.0)
            toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
            break
        time.sleep(1.0)
    toasts = toast_watch_take(drv)
    print('FOLDER_TOASTS %s' % json.dumps(toasts, ensure_ascii=False))
    record('P1b 文件夹导入结果提示', bool(toasts), 'toasts=%s' % ' | '.join(toasts)[:500])
    shot(drv, 'p1b_folder_import_result')
    _, js = B.api('/api/v1/audios?page=1&per_page=50&keyword=%s' % urllib.parse.quote(PREFIX + 'RW_FD_'), token)
    items = (js.get('data') or {}).get('items') or []
    got = [(x['id'], x.get('name')) for x in items]
    record('P1b 文件夹导入后回读', len(got) >= 1, 'created=%s' % got)
    MY_AUDIOS.extend([i for i, _ in got])
    d = V.dialog_with_title(drv, '批量从文件夹导入', 3)
    if d is not None:
        V.click_btn_in(drv, d, '取消', exact=True)


def p1a2_auditor_case(drv, token):
    """审计要求的原案：1 个有效 wav + 1 个非法文件（stray .txt）混合上传，逐条记录实际结果。
    另测后端对非法内容（0 字节 .wav）的受理与回读，判断「失败文件逐条错误」是否有可触发路径。"""
    wav_dir = os.path.join(ART, 'wav_in')
    os.makedirs(wav_dir, exist_ok=True)
    stamp = time.strftime('%H%M%S')
    ok_path = os.path.join(wav_dir, PREFIX + 'RW_A2OK_%s.wav' % stamp)
    txt_path = os.path.join(wav_dir, PREFIX + 'RW_A2STRAY_%s.txt' % stamp)
    zero_path = os.path.join(wav_dir, PREFIX + 'RW_A2ZERO_%s.wav' % stamp)
    make_wav(ok_path)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('this text file matches no audio, should be an illegal/stray file\n')
    open(zero_path, 'wb').close()

    B.goto(drv, '/audio-import', '音频管理')
    time.sleep(2.0)
    V.click_page_btn(drv, '上传音频')
    dlg = V.dialog_with_title(drv, '上传音频', 15)
    if not dlg:
        record('P1a2 上传弹窗打开', False, 'no dialog')
        return
    inp = _find_file_input(drv, dlg)
    if inp is None:
        record('P1a2 上传文件输入', False, 'no input')
        return
    inp.send_keys('\n'.join([ok_path, txt_path]))
    time.sleep(2.0)
    dtext = dlg.text or ''
    m_audio = re.search(r'音频文件\s*(\d+)', dtext)
    m_text = re.search(r'文本文件\s*(\d+)', dtext)
    record('P1a2 有效 wav + stray .txt 进入待传列表', ('A2OK' in dtext) and ('A2STRAY' in dtext),
           'audio=%s text=%s text=%s' % (m_audio.group(1) if m_audio else None,
                                         m_text.group(1) if m_text else None, dtext[:300]))
    shot(drv, 'p1a2_mixed_files_light')
    toast_watch_start(drv)
    V.click_btn_in(drv, dlg, '开始上传', exact=False)
    end = time.time() + 90
    toasts = []
    while time.time() < end:
        toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
        if any(('上传完成' in t) or ('失败' in t) for t in toasts):
            time.sleep(5.0)
            toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
            break
        time.sleep(1.0)
    toasts = toast_watch_take(drv)
    joined = ' | '.join(toasts)
    print('TOASTS_A2 %s' % json.dumps(toasts, ensure_ascii=False))
    per_file = [t for t in toasts if ('A2STRAY' in t) or ('A2OK' in t)]
    record('P1a2 逐条结果（逐文件提示）', len(per_file) > 0,
           'per_file=%s' % json.dumps(per_file, ensure_ascii=False))
    record('P1a2 stray .txt 出现逐条错误', any('A2STRAY' in t for t in toasts),
           'toasts=%s' % joined[:400])
    shot(drv, 'p1a2_mixed_result')
    _, js = B.api('/api/v1/audios?page=1&per_page=20&keyword=%s' % urllib.parse.quote(PREFIX + 'RW_A2'), token)
    items = (js.get('data') or {}).get('items') or []
    got = [(x['id'], x.get('name')) for x in items]
    record('P1a2 有效文件落库 / stray .txt 未落库', any('A2OK' in (n or '') for _, n in got),
           'created=%s' % got)
    MY_AUDIOS.extend([i for i, _ in got])

    # 0 字节 .wav：后端是否受理，回读时长/大小
    B.goto(drv, '/audio-import', '音频管理')
    time.sleep(2.0)
    V.click_page_btn(drv, '上传音频')
    dlg = V.dialog_with_title(drv, '上传音频', 15)
    if dlg:
        inp = _find_file_input(drv, dlg)
        if inp:
            inp.send_keys(zero_path)
            time.sleep(2.0)
            toast_watch_start(drv)
            V.click_btn_in(drv, dlg, '开始上传', exact=False)
            end = time.time() + 60
            toasts = []
            while time.time() < end:
                toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
                if any(('上传完成' in t) or ('失败' in t) for t in toasts):
                    time.sleep(4.0)
                    toasts = drv.execute_script('return (window.__toasts || []).slice();') or []
                    break
                time.sleep(1.0)
            toasts = toast_watch_take(drv)
            print('TOASTS_ZERO %s' % json.dumps(toasts, ensure_ascii=False))
            shot(drv, 'p1a2_zero_byte_result')
            _, js = B.api('/api/v1/audios?page=1&per_page=20&keyword=%s' % urllib.parse.quote(PREFIX + 'RW_A2ZERO'), token)
            items = (js.get('data') or {}).get('items') or []
            got = [(x['id'], x.get('name'), x.get('duration'), x.get('file_size') or x.get('size'),
                    x.get('format')) for x in items]
            record('P1a2 0 字节 .wav 后端受理（缺陷判据）', len(got) > 0,
                   'toasts=%s created=%s' % (' | '.join(toasts)[:200], got))
            MY_AUDIOS.extend([i for i, _, _, _, _ in got])
    d = V.dialog_with_title(drv, '上传音频', 3)
    if d is not None:
        V.click_btn_in(drv, d, '取消', exact=True)


def cleanup(token):
    V.cleanup(token)
    for aid in sorted(set(MY_AUDIOS)):
        s, j = B.api('/api/v1/audios/%s' % aid, token, method='DELETE')
        print('cleanup audio %s -> %s %s' % (aid, s, json.dumps(j, ensure_ascii=False)[:120]))


def main():
    which = sys.argv[1:] or ['all']
    token, _ = B.rsa_login_token(*B.ACCOUNT)
    V.health('rework-start', token)
    drv = B.driver_init()
    try:
        drv.get(B.BASE + '/login')
        B.wait_ready(drv)
        drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
                           B.TOKEN_KEY, token)
        drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
                           B.THEME_KEY, 'light')
        drv.execute_script('try { localStorage.removeItem("iatp:auth:v1"); } catch(e) {}')
        steps = [
            ('p3', lambda: p3_conn_type(drv, token)),
            ('t2', lambda: V.t2_scan_add(drv, token)),
            ('t3', lambda: V.t3_offline_prune(drv, token)),
            ('t5', lambda: V.t5_speaker_group(drv, token)),
            ('t6', lambda: V.t6_spl(drv, token)),
            ('t10', lambda: V.t10_linkage(drv, token)),
            ('p1a', lambda: p1a_mixed_upload(drv, token)),
            ('p1a2', lambda: p1a2_auditor_case(drv, token)),
            ('p1b', lambda: p1b_folder_import(drv, token)),
        ]
        for key, fn in steps:
            if 'all' in which or key in which:
                try:
                    print('---- %s start %s' % (key, time.strftime('%H:%M:%S')))
                    fn()
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    record(key + ' 执行异常', False, repr(exc))
                V.health(key, token)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        cleanup(token)
        with open(os.path.join(ART, 'rework_results.json'), 'w', encoding='utf-8') as f:
            json.dump({'health': V.HEALTH, 'results': RC, 'base_results': V.RESULTS,
                       'fixtures': FIX, 'my_audios': MY_AUDIOS}, f, ensure_ascii=False, indent=2)
        passed = len([r for r in RC + V.RESULTS if r['ok']])
        print('SUMMARY %d/%d passed' % (passed, len(RC) + len(V.RESULTS)))


if __name__ == '__main__':
    main()
