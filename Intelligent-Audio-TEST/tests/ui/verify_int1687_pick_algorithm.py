# -*- coding: utf-8 -*-
"""INT-1687 返工实测：挑选合并阶段 2 用例卡算法徽章取真实 /algorithm/options 名称。

被测入口：本 run 交付 dist 起的旁路容器（--network intelligent-audio-test_default），
nginx /api → api_gateway（真实库 intelligent_audio_test）。
验证点：
  1) 阶段 2 用例视图用例卡徽章显示真实算法中文名（如「小艺语音大模型」），页面无裸类型码 voice_llm；
  2) Network：GET /tasks/cherry-picks/candidates 200 且返回 algorithm_type 为真实类型码；
  3) 浅色 / 深色截图。
"""
import importlib.util
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('INT1497_BASE_URL', 'http://127.0.0.1:15289')
spec = importlib.util.spec_from_file_location(
    'i1497', os.path.join(HERE, 'verify_int1497_cherry_pick.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

BASE = base.BASE
ART = os.path.join(
    base.PROJECT_ROOT, 'tests', 'ui', 'artifacts',
    'int1687_pick_ab' if os.environ.get('IAT1687_AB') == '1' else 'int1687_pick')
os.makedirs(ART, exist_ok=True)
TASK_ID = base.TASK_ID
TASK_NAME_HINT = base.TASK_NAME_HINT


def goto_stage2(drv):
    drv.get(BASE + '/tasks/cherry-picks')
    base.wait_text(drv, '开始挑选', timeout=60)
    drv.get_log('performance')  # 丢首屏噪声
    base.click_button_text(drv, '开始挑选', timeout=30)
    base.wait_text(drv, '阶段 1：选择任务', timeout=60)
    search = base.WebDriverWait(drv, 40).until(
        lambda d: d.find_element(base.By.XPATH, "//input[@aria-label='搜索任务名称']"))
    search.send_keys(TASK_NAME_HINT)
    time.sleep(1.2)
    row = base.WebDriverWait(drv, 60).until(
        lambda d: d.find_element(base.By.XPATH, f"//*[@data-testid='pick-task-{TASK_ID}']"))
    base.js_click(drv, row.find_element(base.By.XPATH, ".//*[@role='checkbox']"))
    time.sleep(0.5)
    base.click_button_text(drv, '下一步：选择结果')
    base.wait_text(drv, '阶段 2：选择结果', timeout=60)
    # 候选列表首查可能较慢（骨架屏 4 行）：等算法徽章任一形态出现，不靠固定 sleep
    end = time.time() + 40
    while time.time() < end:
        txt = base.body_text(drv)
        if any(k in txt for k in ('小艺语音大模型', '通用识别引擎', 'voice_llm', 'wire_test_param')):
            break
        time.sleep(0.5)
    time.sleep(0.8)


def badge_texts(drv):
    """用例卡徽章行文案（Card 内 Badge 多为 span，取所有短文本节点做证据）。"""
    return drv.execute_script(
        "return Array.from(document.querySelectorAll('span')).map(e=>e.textContent.trim())"
        ".filter(t=>t && t.length<=20)")


def candidates(drv):
    reqs, resps = base.perf_network(drv)
    return reqs, resps


def main():
    print('被测入口:', BASE)
    drv = base.make_driver()
    out = {'base': BASE}
    try:
        results = []
        # ---------- 浅色 ----------
        goto_stage2(drv)
        time.sleep(1.5)
        texts = badge_texts(drv)
        body = base.body_text(drv)
        reqs, resps = candidates(drv)
        hits = sorted({t for t in texts if t in ('小艺语音大模型', '通用识别引擎')})
        raw_codes = sorted({t for t in texts if t in ('voice_llm', 'wire_test_param', 'asr-v3')})
        results.append(f'浅色·用例卡算法徽章真实名命中: {hits}')
        results.append(f'浅色·页面内裸类型码: {raw_codes or "无"}')
        results.append(f'candidates 请求/响应: {reqs} / {resps}')
        light_png = os.path.join(ART, 'pick_case_light.png')
        drv.save_screenshot(light_png)
        out['light'] = {'hits': hits, 'raw_codes': raw_codes, 'candidates': resps}
        if os.environ.get('IAT1687_AB') == '1':
            # A/B 对照旧镜像：只取证不断言（旧镜像预期命中裸类型码）
            for line in results:
                print('ℹ️', line)
            out['ab'] = True
            print('artifacts:', ART)
            return
        assert hits, f'未命中真实算法名徽章，badge 文本样本={texts[:40]}'
        assert not raw_codes, f'页面仍出现裸类型码: {raw_codes}'
        assert any(r.get('status') == 200 for r in resps), f'candidates 非 200: {resps}'

        # ---------- 深色 ----------
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
        drv.refresh()
        time.sleep(2.0)
        goto_stage2(drv)
        time.sleep(1.5)
        texts = badge_texts(drv)
        hits_dark = sorted({t for t in texts if t in ('小艺语音大模型', '通用识别引擎')})
        raw_dark = sorted({t for t in texts if t in ('voice_llm', 'wire_test_param', 'asr-v3')})
        results.append(f'深色·用例卡算法徽章真实名命中: {hits_dark}')
        results.append(f'深色·页面内裸类型码: {raw_dark or "无"}')
        assert hits_dark, f'深色未命中真实算法名徽章: {texts[:40]}'
        assert not raw_dark, f'深色页面仍出现裸类型码: {raw_dark}'
        dark_png = os.path.join(ART, 'pick_case_dark.png')
        drv.save_screenshot(dark_png)
        out['dark'] = {'hits': hits_dark, 'raw_codes': raw_dark}

        for line in results:
            print('✅', line)
        out['ok'] = True
    finally:
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        drv.quit()
    print('artifacts:', ART)


if __name__ == '__main__':
    main()
