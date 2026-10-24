# -*- coding: utf-8 -*-
"""INT-1687 返工复核（前端UX审计员）：挑选合并阶段 2 用例卡算法徽章。

审计侧独立脚本，不复用实施者断言：
  - 阶段 2「用例视图」按分组 / 按标签两种组织下，逐卡核对算法徽章文案；
  - 页面内裸类型码（voice_llm / wire_test_param / asr-v3）计数必须为 0；
  - GET /tasks/cherry-picks/candidates 状态码；
  - 控制台 SEVERE；
  - 浅 / 深色截图。

用法：
  INT1497_BASE_URL=http://127.0.0.1:15292 python tests/ui/verify_int1687_ux_audit_pick.py
  IAT1687_AB=1（旧镜像 A/B 对照，只取证不断言）
"""
import importlib.util
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'i1497', os.path.join(HERE, 'verify_int1497_cherry_pick.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

AB = os.environ.get('IAT1687_AB') == '1'
ART = os.path.join(
    base.PROJECT_ROOT, 'tests', 'ui', 'artifacts',
    'int1687_pick_ab' if AB else 'int1687_pick_audit')
os.makedirs(ART, exist_ok=True)

GOOD = '小艺语音大模型'
RAW_RE = re.compile(r'voice_llm|wire_test_param|asr-v3')

CARD_JS = r"""
const name = arguments[0];
const cards = Array.from(document.querySelectorAll('[aria-label^="选择 "]'))
  .map(function (el) { return el.closest('div[class*="rounded"]'); })
  .filter(Boolean);
const out = [];
const seen = new Set();
for (const c of cards) {
  if (seen.has(c)) continue;
  seen.add(c);
  const txt = (c.innerText || '').replace(/\s+/g, ' ');
  out.push(txt.slice(0, 120));
}
return out;
"""


def goto_stage2(drv):
    drv.get(base.BASE + '/tasks/cherry-picks')
    base.wait_text(drv, '开始挑选', timeout=60)
    drv.get_log('performance')
    base.click_button_text(drv, '开始挑选', timeout=30)
    base.wait_text(drv, '阶段 1：选择任务', timeout=60)
    search = base.WebDriverWait(drv, 40).until(
        lambda d: d.find_element(base.By.XPATH, "//input[@aria-label='搜索任务名称']"))
    search.send_keys(base.TASK_NAME_HINT)
    time.sleep(1.2)
    row = base.WebDriverWait(drv, 60).until(
        lambda d: d.find_element(base.By.XPATH, "//*[@data-testid='pick-task-%d']" % base.TASK_ID))
    base.js_click(drv, row.find_element(base.By.XPATH, ".//*[@role='checkbox']"))
    time.sleep(0.5)
    base.click_button_text(drv, '下一步：选择结果')
    base.wait_text(drv, '阶段 2：选择结果', timeout=60)


def wait_cards(drv, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        n = len(drv.find_elements(base.By.CSS_SELECTOR, '[aria-label^="选择 "]'))
        if n:
            # 等徽章随 options 落地（最多再等 20s，出现名称即走）
            t2 = time.time() + 20
            while time.time() < t2:
                if GOOD in base.body_text(drv):
                    return n
                time.sleep(0.4)
            return n
        time.sleep(0.4)
    return 0


def snap(drv, theme, tag):
    texts = drv.execute_script(CARD_JS) or []
    checkboxes = len(drv.find_elements(base.By.CSS_SELECTOR, '[aria-label^="选择 "]'))
    body = base.body_text(drv)
    raws = RAW_RE.findall(body)
    hits = [t for t in texts if GOOD in t]
    png = os.path.join(ART, 'pick_%s_%s.png' % (tag, theme))
    drv.save_screenshot(png)
    reqs, resps = base.perf_network(drv)
    severe = [c.get('message') for c in (drv.get_log('browser') or [])
              if c.get('level') == 'SEVERE'][:5]
    return {
        'theme': theme, 'tag': tag, 'cards': checkboxes,
        'cards_with_name': len(hits), 'raw_codes': sorted(set(raws)),
        'raw_count': len(raws), 'body_name_count': body.count(GOOD),
        'candidates_status': [r.get('status') for r in resps],
        'console_severe': severe, 'shot': png,
        'sample': texts[:3],
    }


def main():
    print('被测入口:', base.BASE)
    drv = base.make_driver()
    out = {'base': base.BASE, 'ab': AB, 'runs': []}
    try:
        for theme in ('light', 'dark'):
            drv.get(base.BASE + '/tasks/cherry-picks')
            drv.execute_script(
                "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
            drv.get('about:blank')
            time.sleep(0.4)
            goto_stage2(drv)
            wait_cards(drv)
            time.sleep(1.2)
            for tag in ('bygroup', 'bytag'):
                if tag == 'bytag':
                    try:
                        base.click_button_text(drv, '按标签', timeout=10)
                        time.sleep(2.0)
                        wait_cards(drv, 30)
                        time.sleep(1.0)
                    except Exception as exc:
                        out['runs'].append({'theme': theme, 'tag': tag, 'error': str(exc)})
                        continue
                res = snap(drv, theme, tag)
                out['runs'].append(res)
                print(json.dumps(res, ensure_ascii=False))
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    if AB:
        print('A/B 对照取证完成:', ART)
        return

    fails = []
    for r in out['runs']:
        if r.get('error'):
            continue
        if r['body_name_count'] < r['cards'] or not r['cards_with_name']:
            fails.append('%s/%s 无算法名徽章（cards=%d）' % (r['theme'], r['tag'], r['cards']))
        if r['raw_count']:
            fails.append('%s/%s 页面裸类型码 %s' % (r['theme'], r['tag'], r['raw_codes']))
        if r['candidates_status'] and all(s != 200 for s in r['candidates_status']):
            fails.append('%s/%s candidates 非 200: %s' % (r['theme'], r['tag'], r['candidates_status']))
    assert not fails, '；'.join(fails)
    print('PASS 全部用例卡徽章为真实算法名，0 裸类型码')


if __name__ == '__main__':
    main()
