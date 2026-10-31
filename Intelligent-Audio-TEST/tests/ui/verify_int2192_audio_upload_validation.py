# -*- coding: utf-8 -*-
"""INT-2192 自测：上传音频弹窗内容预检 + 逐条提示。

环境：dev 5377（本卡工作树构建，API_PROXY_TARGET → docker 网关 15000，真实库
intelligent_audio_test）。被测改动：audio-upload-dialog.tsx（lib/audio-file-validation.ts、
lib/annotation.ts findUnmatchedAnnotationFiles）。

核对：
  S1 0 字节 .wav + 文本改名 .wav：逐条报错、无「上传完成」成功提示、不发任何
     /audios/upload/* 请求、弹窗不关（症状 1：原先提示成功并入库 duration=0）；
  S2 有效 wav + 游离 .txt + 0 字节 wav 混合：游离 txt 与空文件逐条提示，只上传 1 个有效
     文件，汇总「成功 1 个音频文件，跳过 2 个文件」；merge 只 1 次（症状 2：原先 stray
     文件静默忽略）；入库音频 duration>0；
  S3 深色：S1 同款再跑一遍，浅色 / 深色各一帧。
运行：python tests/ui/verify_int2192_audio_upload_validation.py
"""
import json
import os
import re
import sys
import time
import urllib.request
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:5377')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.action_chains import ActionChains  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2192')
FILES = os.path.join(ART, 'files')
os.makedirs(FILES, exist_ok=True)

DIALOG = "[data-slot='dialog-content']"
PREFIX = '接线测试_INT2192_'
RESULTS = []

EMPTY_WAV = os.path.join(FILES, PREFIX + '空.wav')
FAKE_WAV = os.path.join(FILES, PREFIX + '文本.wav')
STRAY_TXT = os.path.join(FILES, PREFIX + '游离.txt')
VALID_LIGHT = os.path.join(FILES, PREFIX + '正常浅色.wav')
VALID_DARK = os.path.join(FILES, PREFIX + '正常深色.wav')

TOAST_JS = r'''
window.__toasts = window.__toasts || [];
if (!window.__toastObs) {
  window.__toastObs = true;
  window.__grabToasts = function(){
    var nodes = document.querySelectorAll('[data-sonner-toast]');
    for (var i = 0; i < nodes.length; i++) {
      var t = (nodes[i].innerText || '').replace(/\s+/g, ' ').trim();
      if (t && window.__toasts.indexOf(t) < 0) window.__toasts.push(t);
    }
  };
  var mo = new MutationObserver(function(){ window.__grabToasts(); });
  mo.observe(document.body, {childList: true, subtree: true, characterData: true});
}
'''


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:900], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT ' + path)
    return path


def build_fixtures():
    # 0 字节 .wav（症状 1 实测触发的文件）
    open(EMPTY_WAV, 'wb').close()
    # 纯文本改名 .wav（1240 字节，同 INT-2175 实测文件量级）
    with open(FAKE_WAV, 'wb') as f:
        f.write(('this is not an audio file, just text. ' * 35).encode('utf-8')[:1240])
    # 不与任何音频同名的游离标注/txt
    with open(STRAY_TXT, 'w', encoding='utf-8') as f:
        f.write('孤立文本，不匹配任何同批音频文件名\n')
    # 真实可解码的 PCM WAV（浅色 / 深色各一份，内容时长不同避免互撞）
    for path, seconds in ((VALID_LIGHT, 0.4), (VALID_DARK, 0.6)):
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            frames = int(16000 * seconds)
            w.writeframes(b'\x00\x00' * frames)


def bootstrap(drv):
    drv.get(B.BASE + '/login')
    B.wait_ready(drv)
    token, user = B.rsa_login_token(*B.ACCOUNT)
    drv.execute_script(
        'try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
        B.TOKEN_KEY, token)
    drv.execute_script('try { localStorage.removeItem("iatp:auth:v1"); } catch(e) {}')
    B.goto(drv, '/audio-import', '音频管理', timeout=90)
    return token, user


def install_toast_observer(drv):
    drv.execute_script(TOAST_JS)


def reset_toasts(drv):
    drv.execute_script('window.__toasts = []; if (window.__grabToasts) window.__grabToasts();')


def toasts(drv):
    try:
        drv.execute_script('if (window.__grabToasts) window.__grabToasts();')
    except Exception:
        pass
    return drv.execute_script('return window.__toasts || [];')


def wait_toast(drv, needle, timeout=30):
    def probe(d):
        for t in toasts(d):
            if needle in t:
                return True
        return False
    WebDriverWait(drv, timeout).until(probe)


def open_upload_dialog(drv):
    B.click_button_text(drv, '上传音频')
    B.wait_dialog(drv, '上传音频')
    time.sleep(0.8)


def select_files(drv, paths):
    inp = drv.find_element(By.CSS_SELECTOR, DIALOG + " input[type='file']")
    drv.execute_script("arguments[0].style.display='block';", inp)
    inp.send_keys('\n'.join(paths))
    drv.execute_script("arguments[0].style.display='none';", inp)
    B.wait_text(drv, '已选择 %d 个文件' % len(paths), timeout=30)
    time.sleep(0.5)


def click_upload(drv):
    btn = drv.find_element(
        By.XPATH, "//*[@data-slot='dialog-content']//button[normalize-space(.)='开始上传']")
    B.js_click(drv, btn)


def expand_toasts(drv):
    """sonner 默认折叠堆叠，hover 展开后逐条 toast 同屏可见（截图用）。"""
    try:
        # 悬停「最前一层」toast 才会把堆叠展开（toaster 容器本身高度为 0，hover 不触发）
        for el in drv.find_elements(By.CSS_SELECTOR, "[data-sonner-toast][data-front='true']"):
            if B.visible(el):
                ActionChains(drv).move_to_element(el).perform()
                time.sleep(0.8)
                break
    except Exception:
        pass


def reqs(drv):
    return drv.execute_script('return window.__reqs || [];')


def upload_reqs(drv):
    return [r for r in reqs(drv) if '/audios/upload/' in (r.get('url') or '')]


def api_list_audios(token, keyword):
    status, body = B.api('/api/v1/audios', token, method='POST',
                         body={'page': 1, 'per_page': 20, 'keyword': keyword})
    data = body.get('data', body) if isinstance(body, dict) else {}
    return status, (data.get('items') or []) if isinstance(data, dict) else []


def cleanup(token):
    try:
        _, items = api_list_audios(token, PREFIX)
        for item in items:
            name = str(item.get('name') or '')
            if not name.startswith(PREFIX):
                continue
            status, body = B.api('/api/v1/audios/%s' % item.get('id'), token, method='DELETE')
            print('CLEAN id=%s name=%s status=%s msg=%s' % (
                item.get('id'), name, status, str(body)[:120]))
    except Exception as exc:  # 清理失败不掩埋主结论
        print('CLEAN-FAIL ' + repr(exc)[:300])


def scenario_invalid(drv, tag):
    """S1：0 字节 + 文本改名 .wav → 逐条错误、无成功、无上传请求、弹窗不关。"""
    open_upload_dialog(drv)
    select_files(drv, [EMPTY_WAV, FAKE_WAV])
    B.reset_reqs(drv)
    reset_toasts(drv)
    click_upload(drv)
    wait_toast(drv, '文件为空（0 字节）')
    wait_toast(drv, '文件内容不是可解析的音频文件')
    wait_toast(drv, '没有可上传的音频文件')
    time.sleep(0.4)
    expand_toasts(drv)
    texts = toasts(drv)
    joined = ' || '.join(texts)
    png = shot(drv, 'int2192_%s_invalid_files' % tag)
    ok_empty = any('文件为空（0 字节）' in t for t in texts)
    ok_fake = any('文件内容不是可解析的音频文件' in t for t in texts)
    ok_none = any('没有可上传的音频文件' in t for t in texts)
    ok_no_success = not any('上传完成' in t for t in texts)
    calls = upload_reqs(drv)
    ok_no_call = len(calls) == 0
    dialog_open = B.dialog_present(drv, '上传音频') is not None
    record('[%s] 0 字节 .wav 逐条报错' % tag, ok_empty, joined)
    record('[%s] 文本改名 .wav 逐条报错' % tag, ok_fake, joined)
    record('[%s] 全无效时提示无可上传文件' % tag, ok_none, joined)
    record('[%s] 不再提示「上传完成」' % tag, ok_no_success, joined)
    record('[%s] 未发出任何 /audios/upload/* 请求' % tag, ok_no_call,
           [c.get('url') for c in calls])
    record('[%s] 弹窗保持打开可重选' % tag, dialog_open, '')
    return {'toasts': texts, 'png': png}


def scenario_mixed(drv, token, valid_path, tag):
    """S2：有效 wav + 游离 txt + 0 字节 wav → 逐条提示，只传 1 个有效文件。"""
    # 关闭上一幕弹窗后重开，避免残留文件
    try:
        B.click_button_text(drv, '取消', exact=True, timeout=8)
    except Exception:
        pass
    time.sleep(0.5)
    open_upload_dialog(drv)
    select_files(drv, [valid_path, STRAY_TXT, EMPTY_WAV])
    shot(drv, 'int2192_%s_mixed_selected' % tag)
    B.reset_reqs(drv)
    reset_toasts(drv)
    click_upload(drv)
    wait_toast(drv, '上传完成')
    time.sleep(0.4)
    expand_toasts(drv)
    texts = toasts(drv)
    joined = ' || '.join(texts)
    png = shot(drv, 'int2192_%s_mixed_files' % tag)
    ok_stray = any('未匹配到同名音频文件，已忽略' in t for t in texts)
    ok_empty = any('文件为空（0 字节）' in t for t in texts)
    ok_summary = any(re.search(r'成功 1 个音频文件，跳过 2 个文件', t) for t in texts)
    calls = upload_reqs(drv)
    merge_calls = [c for c in calls if '/audios/upload/merge' in (c.get('url') or '')]
    init_calls = [c for c in calls if '/audios/upload/init' in (c.get('url') or '')]
    ok_only_one = len(merge_calls) == 1 and len(init_calls) == 1
    record('[%s] 游离 txt 逐条提示已忽略' % tag, ok_stray, joined)
    record('[%s] 空文件逐条报错' % tag, ok_empty, joined)
    record('[%s] 汇总计入「跳过 2 个文件」' % tag, ok_summary, joined)
    record('[%s] 只上传 1 个有效文件（init/merge 各 1 次）' % tag, ok_only_one,
           {'init': len(init_calls), 'merge': len(merge_calls)})
    # 入库音频 duration>0（真实库回读）
    hit = None
    for c in merge_calls:
        m = re.search(r'"audio_id"\s*:\s*(\d+)', c.get('resp') or '')
        if m:
            hit = int(m.group(1))
            break
    time.sleep(1.5)
    _, items = api_list_audios(token, PREFIX)
    row = None
    for item in items:
        if item.get('id') == hit or str(item.get('name') or '').startswith(os.path.basename(valid_path).split('.')[0]):
            row = item
            break
    duration = (row or {}).get('duration')
    record('[%s] 入库音频时可回读且 duration>0' % tag,
           bool(row) and (duration or 0) > 0,
           {'id': hit, 'name': (row or {}).get('name'), 'duration': duration})
    return {'toasts': texts, 'png': png, 'audio_id': hit, 'row': row, 'calls': len(calls)}


def set_theme(drv, mode):
    B.set_theme(drv, mode)
    drv.refresh()
    B.wait_ready(drv)
    B.wait_text(drv, '音频管理', timeout=60)
    time.sleep(1.2)
    # 刷新会重建 body，重装 toast observer
    install_toast_observer(drv)
    return B.is_dark(drv)


def main():
    build_fixtures()
    drv = B.driver_init()
    token = None
    summary = {}
    try:
        token, user = bootstrap(drv)
        record('登录真实账号', True, (user or {}).get('username'))
        # 基线：浅色
        dark = B.is_dark(drv)
        if dark:
            set_theme(drv, 'light')
        install_toast_observer(drv)
        record('浅色主题', not B.is_dark(drv), '')

        summary['s1_light'] = scenario_invalid(drv, 'light')

        # 深色：重载后同款再跑一遍
        set_theme(drv, 'dark')
        record('深色主题', B.is_dark(drv), '')
        summary['s1_dark'] = scenario_invalid(drv, 'dark')

        # 回到浅色跑混合批次（真实上传 1 个有效文件）
        set_theme(drv, 'light')
        summary['s2_light'] = scenario_mixed(drv, token, VALID_LIGHT, 'light')
    except Exception as exc:
        import traceback
        traceback.print_exc()
        record('执行异常', False, repr(exc))
    finally:
        try:
            if token:
                cleanup(token)
        finally:
            try:
                drv.quit()
            except Exception:
                pass
    passed = sum(1 for r in RESULTS if r['ok'])
    print('\n==== INT-2192 %d/%d 项通过 ====' % (passed, len(RESULTS)))
    for r in RESULTS:
        if not r['ok']:
            print('FAILED: ' + r['step'] + ' :: ' + r['detail'][:300])
    with open(os.path.join(ART, 'int2192_result.json'), 'w', encoding='utf-8') as f:
        json.dump({'results': RESULTS, 'summary': summary}, f, ensure_ascii=False, indent=2)
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == '__main__':
    main()
