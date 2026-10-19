# -*- coding: utf-8 -*-
"""INT-891 报告域模态窗验收：报告详情用例卡 / 人工审核 / AI 复核（INT-825 四端点）。

逐窗验证（打开 → 真实数据 → 关键操作 → 关闭）：
  1. 报告详情用例卡（CaseDetailDialog）：详情按钮 → 七块真实数据 → 关闭
  2. 人工审核（ManualReviewDialog）：真实结果加载 → 提交复核（写操作）→ 历史抽屉
  3. AI 复核（AiReviewDialog）：发起 → 结论卡 → 采纳/驳回
  4. Network 证据：reviewApi 四端点（POST ai-review / GET ai-review-history /
     POST adopt / POST reject）+ 人工复核 POST /tasks/results/review
  5. 浅色 + 深色截图
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5388')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int891_review_modals')

REPORT_ID = 65
TASK_ID = 1257
CASE_ID = '5412e6d4-be58-4446-9dc0-d40f739e919f'
RESULT_ID = 3693


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(drv))


def _wait_gone(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text not in _body(drv))


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('saved', p)
    return p


def _drain_perf(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                p = inner.get('params', {})
                req = p.get('request', {})
                url = req.get('url', '')
                if '/api/v1/' in url:
                    out.append({
                        'url': url.replace('http://localhost:5388', ''),
                        'method': req.get('method'),
                        'postData': req.get('postData'),
                    })
    except Exception as e:
        out.append({'error': str(e)})
    return out


def _perf_since(drv, before):
    after = _drain_perf(drv)
    return [e for e in after if e not in before]


def _severe(drv):
    try:
        return [e.get('message') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    except Exception:
        return []


def _set_theme(drv, mode):
    drv.get(BASE + '/report/65')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1)
    drv.execute_script(
        'localStorage.setItem("iatp:theme:v1:mode", "%s"); location.reload();' % mode)
    time.sleep(3)


def _click_button_text(drv, text, container=None):
    xp = f"//button[contains(normalize-space(.), '{text}')]"
    if container:
        xp = f"{container}{xp}"
    el = drv.find_element(By.XPATH, xp)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.3)
    try:
        el.click()
    except Exception:
        drv.execute_script("arguments[0].click();", el)
    time.sleep(0.8)


def _find_dialog(drv, title):
    xp = f"//*[@role='dialog']//*[contains(normalize-space(.), '{title}')]"
    els = drv.find_elements(By.XPATH, xp)
    return len(els) > 0


def _backend(url_path):
    with urllib.request.urlopen('http://127.0.0.1:5000' + url_path, timeout=8) as r:
        return json.loads(r.read().decode('utf-8'))


def _backend_cleanup_review():
    """清理人工审核写操作（留痕行 + 复位 result/case/stats/TRD），恢复验收前状态。"""
    import subprocess
    env = os.environ.copy()
    env['PGPASSWORD'] = 'intelligent_audio_test666'
    env['PGCLIENTENCODING'] = 'UTF8'
    sql_file = os.path.join(ART, '_cleanup_review.sql')
    os.makedirs(ART, exist_ok=True)
    sql = (
        "DELETE FROM test_result_reviews WHERE result_id=3693 "
        "AND comment LIKE '接线测试 INT-891%';\n"
        "UPDATE test_results SET reviewed=0, reviewed_by_user_id=NULL, reviewed_at=NULL, "
        "last_review_comment=NULL, last_review_action=NULL WHERE id=3693;\n"
        "UPDATE task_case_relations SET status='completed', execution_status='completed', "
        "evaluation_status='completed' WHERE task_id=1257 "
        "AND test_case_id='5412e6d4-be58-4446-9dc0-d40f739e919f';\n"
        "UPDATE test_tasks SET total_cases=1, completed_cases=1, failed_cases=0 WHERE id=1257;\n"
        "UPDATE test_result_dimensions SET evaluation_status='completed', status='completed' "
        "WHERE test_result_id=3693;\n"
    )
    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write(sql)
    try:
        r = subprocess.run(
            ['psql', '-h', 'localhost', '-p', '5432', '-U', 'intelligent_audio_test',
             '-d', 'intelligent_audio_test_test', '-f', sql_file],
            env=env, capture_output=True, text=False, timeout=30)
        print('manual review cleanup rc=', r.returncode)
        if r.returncode != 0:
            print('!! cleanup failed:', (r.stderr or b'')[-300:])
    except Exception as e:
        print('!! cleanup exception:', e)


def main():
    # ---------- 数据预检 ----------
    hist = _backend(f'/api/v1/tasks/results/{TASK_ID}/ai-review-history')
    items = hist.get('data', {}).get('items', [])
    print('=== pre-check ai-review-history ===')
    print('count:', len(items))
    for it in items:
        print('  id', it['id'], 'result_id', it['result_id'], 'status', it['status'],
              'adopted', it.get('adopted'), 'rejected', it.get('rejected'))

    drv = _driver()
    try:
        _set_theme(drv, 'light')
        _goto(drv, f'/report/{REPORT_ID}')
        _wait_text(drv, '具体用例对比', 25)
        _shot(drv, '01_report_light')

        # ============ 1. 报告详情用例卡（CaseDetailDialog） ============
        print('=== 1. case detail dialog ===')
        _wait_text(drv, 'INT314SMOKE_70ed974e_API用例', 25)
        # 打开第一个用例行的「详情」按钮
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(1)
        btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '详情')]")
        print('详情 buttons:', len(btns))
        btns[0].click()
        time.sleep(1.5)
        _wait_text(drv, '评分指标', 15)
        _wait_text(drv, '执行结果', 15)
        _shot(drv, '02_case_detail_dialog_light')
        body = _body(drv)
        print('case dialog has 评分指标:', '评分指标' in body)
        print('case dialog has 执行结果:', '执行结果' in body)
        print('case dialog has 详细日志:', '详细日志' in body)
        # 关闭
        close_btn = drv.find_elements(By.XPATH,
            "//*[@role='dialog']//button[contains(normalize-space(.), '关闭')]")
        if not close_btn:
            close_btn = drv.find_elements(By.XPATH,
                "//*[@role='dialog']//button[contains(normalize-space(.), '取消')]")
        if close_btn:
            close_btn[0].click()
            time.sleep(1)
        print('case detail dialog closed')

        # ============ 2. 人工审核（ManualReviewDialog） ============
        print('=== 2. manual review dialog ===')
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        before = _drain_perf(drv)
        _click_button_text(drv, '人工复核')
        _wait_text(drv, '人工复核 —', 15)
        _wait_text(drv, '#3693', 15)
        _shot(drv, '03_manual_review_dialog_light')
        # 打开复核历史抽屉（dialog 内链接）
        hist_link = drv.find_elements(By.XPATH,
            "//*[@role='dialog']//button[contains(normalize-space(.), '查看复核历史')]")
        if hist_link:
            hist_link[0].click()
            time.sleep(1.5)
            _wait_text(drv, '复核历史 —', 15)
            _wait_text(drv, '暂无复核记录', 15)
            _shot(drv, '04_review_history_empty_light')
            # 关闭抽屉
            drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '关闭')]").click()
            time.sleep(1)
        # 填表提交：评估状态改判 failed + 备注必填
        drv.execute_script("arguments[0].click();",
            drv.find_element(By.ID, 'manual-review-eval'))
        time.sleep(0.8)
        opt = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' and normalize-space(.)='评估失败']")
        if not opt:
            opt = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' and normalize-space(.)='failed']")
        if opt:
            opt[0].click()
            time.sleep(0.5)
        else:
            print('!! eval select option 评估失败 not found')
        comment = drv.find_element(By.ID, 'manual-review-comment')
        comment.clear()
        comment.send_keys('接线测试 INT-891 人工审核验收提交（验收后删除）')
        time.sleep(0.3)
        _click_button_text(drv, '提交复核')
        time.sleep(1.5)
        body = _body(drv)
        print('after submit has 复核已提交:', '复核已提交' in body or '计入统计' in body)
        net = _perf_since(drv, before)
        print('=== network (manual review) ===')
        for e in net:
            u = e['url']
            if 'tasks/results/review' in u or 'cases' in u:
                print('  ', e['method'], u, (e.get('postData') or '')[:120])
        _shot(drv, '05_manual_review_submitted_light')
        time.sleep(0.5)
        # 测试数据卫生：立即清理人工审核写操作（删留痕行 + 复位 result/case/stats/TRD）
        _backend_cleanup_review()

        # ============ 3. AI 复核（AiReviewDialog） ============
        print('=== 3. AI review dialog ===')
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        before = _drain_perf(drv)
        _click_button_text(drv, 'AI 复核')
        _wait_text(drv, '发起 AI 复核', 15)
        _wait_text(drv, '复核维度', 15)
        _shot(drv, '06_ai_review_idle_light')
        # 发起
        _click_button_text(drv, '发起 AI 复核')
        _wait_text(drv, 'AI 复核中', 10)
        time.sleep(2.5)
        _wait_text(drv, '采纳为复核结果', 20)
        _shot(drv, '07_ai_review_conclusion_light')
        body = _body(drv)
        print('has 置信度:', '置信度' in body)
        print('has 采纳为复核结果:', '采纳为复核结果' in body)
        print('has 驳回:', '驳回' in body)
        print('has 对比:', '对比' in body)
        net = _perf_since(drv, before)
        print('=== network (AI review initiate) ===')
        for e in net:
            u = e['url']
            if 'ai-review' in u:
                print('  ', e['method'], u, (e.get('postData') or '')[:120])
        _shot(drv, '08_ai_review_conclusion_light2')

        # ---- 采纳（INT-825 contract: adopt requires payload） ----
        print('=== 3b. adopt click ===')
        before = _drain_perf(drv)
        adopt_btn = drv.find_elements(By.XPATH,
            "//*[@role='dialog']//button[contains(normalize-space(.), '采纳为复核结果')]")
        if adopt_btn:
            adopt_btn[0].click()
            time.sleep(2)
            body = _body(drv)
            print('after adopt: dialog still open (采纳为复核结果 present):', '采纳为复核结果' in body)
            print('after adopt: has 已采纳:', '已采纳' in body)
            print('after adopt: has error 载荷:', '载荷' in body or '失败' in body)
            net = _perf_since(drv, before)
            adopt_fired = [e for e in net if '/adopt' in e['url']]
            print('adopt network requests fired:', len(adopt_fired))
            for e in adopt_fired:
                print('  ', e['method'], e['url'], (e.get('postData') or '')[:120])
            _shot(drv, '09_after_adopt_light')
        else:
            print('!! adopt button not found')

        # ---- 驳回 ----
        print('=== 3c. reject click ===')
        before = _drain_perf(drv)
        rej_btn = drv.find_elements(By.XPATH,
            "//*[@role='dialog']//button[contains(normalize-space(.), '驳回')]")
        if rej_btn:
            rej_btn[0].click()
            time.sleep(2)
            body = _body(drv)
            print('after reject has 已驳回:', '已驳回' in body)
            net = _perf_since(drv, before)
            rej_fired = [e for e in net if '/reject' in e['url']]
            print('reject network requests fired:', len(rej_fired))
            for e in rej_fired:
                print('  ', e['method'], e['url'])
            _shot(drv, '10_after_reject_light')
        else:
            print('!! reject button not found')

        # ---- AI 历史抽屉 ----
        print('=== 3d. review history drawer (AI tab) ===')
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        if '人工复核 —' in _body(drv):
            # 若人工复核弹窗仍开着，先关闭
            try:
                drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '取消')]").click()
                time.sleep(1)
            except Exception:
                pass
        hist_btn = drv.find_elements(By.XPATH,
            "//button[contains(normalize-space(.), '查看复核历史')]")
        if not hist_btn:
            # 从用例卡片入口（人工复核 Badge / 详情）打开
            hist_btn = drv.find_elements(By.XPATH,
                "//button[contains(normalize-space(.), '查看复核明细')]")
        if hist_btn:
            before = _drain_perf(drv)
            hist_btn[0].click()
            time.sleep(1.5)
            _wait_text(drv, '复核历史 —', 15)
            # 切 AI Tab
            ai_tab = drv.find_elements(By.XPATH,
                "//*[@role='tab' or @data-slot='tab']//*[contains(normalize-space(.), 'AI 复核')]")
            if not ai_tab:
                ai_tab = drv.find_elements(By.XPATH,
                    "//*[contains(normalize-space(.), 'AI 复核') and @role='tab']")
            if ai_tab:
                ai_tab[0].click()
                time.sleep(1.5)
            net = _perf_since(drv, before)
            print('=== network (AI history) ===')
            for e in net:
                if 'ai-review-history' in e['url']:
                    print('  ', e['method'], e['url'])
            _shot(drv, '11_review_history_ai_light')
            # 关闭抽屉
            try:
                drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '关闭')]").click()
                time.sleep(1)
            except Exception:
                pass
        else:
            print('!! history button not found')

        severe = _severe(drv)
        print('=== console SEVERE count:', len(severe))
        for s in severe[:10]:
            print(s[:250])

        # ============ 深色 ============
        print('=== dark mode ===')
        _set_theme(drv, 'dark')
        _goto(drv, f'/report/{REPORT_ID}')
        _wait_text(drv, '具体用例对比', 25)
        _wait_text(drv, 'INT314SMOKE_70ed974e_API用例', 25)
        _shot(drv, '12_report_dark')
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(1)
        btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '详情')]")
        if btns:
            btns[0].click()
            time.sleep(1.5)
            _wait_text(drv, '评分指标', 15)
            _shot(drv, '13_case_detail_dialog_dark')
            try:
                drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '关闭')]").click()
                time.sleep(1)
            except Exception:
                pass
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        _click_button_text(drv, '人工复核')
        _wait_text(drv, '人工复核 —', 15)
        _wait_text(drv, '#3693', 15)
        _shot(drv, '14_manual_review_dialog_dark')
        # 关闭
        try:
            drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '取消')]").click()
            time.sleep(1)
        except Exception:
            pass
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'start'})")
        time.sleep(0.5)
        _click_button_text(drv, 'AI 复核')
        _wait_text(drv, '发起 AI 复核', 15)
        _shot(drv, '15_ai_review_idle_dark')

        print('=== DONE ===')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
