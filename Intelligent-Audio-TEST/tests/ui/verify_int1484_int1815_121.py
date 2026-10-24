"""INT-1484 交付前补验（INT-1815 重建后）：真实维度 121 抽屉空规则 + 原样保存回读。

只做唤醒指定的这一段，其余 4 窗沿用 2026-10-24 16:48~17:00（image 916bc83ed4d9）那轮证据。
  - 真实维度 121「拒识成功数量」：打开编辑 → 结果配置 0 条规则行 /「该维度未配置评分规则」/「未设置」
  - 浅色 + 深色截图
  - 不改字段保存 → 抓 PUT 请求体 → GET 回读 rule / result_type / name 不变
  - 控制台 SEVERE 0
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import audit_int1484_int1732 as A  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

REAL_ID = 121
REAL_NAME = '拒识成功数量'
OUT = {}


def env_probe():
    with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=30) as r:
        health = json.loads(r.read().decode('utf-8'))
    with urllib.request.urlopen(A.BASE + '/', timeout=30) as r:
        html = r.read().decode('utf-8', 'replace')
    import re
    lib = re.findall(r'lib-react\.[0-9a-z]+\.js', html)
    OUT['health'] = health
    OUT['lib_react'] = sorted(set(lib))
    A.log('env /health database=%s；15173 lib-react=%s' % (health.get('database'), OUT['lib_react']))
    assert health.get('database') == 'intelligent_audio_test', health
    assert OUT['lib_react'], '15173 不是 React 构建'


def snapshot(d):
    return {k: d.get(k) for k in ('id', 'name', 'rule', 'result_type', 'required_inputs', 'output_fields')}


def main():
    os.makedirs(A.ART, exist_ok=True)
    env_probe()
    before = A.get_dim(REAL_ID)
    A.log('121 before rule=%s rt=%s name=%s' % (
        json.dumps(before['rule'], ensure_ascii=False), before['result_type'], before['name']))
    OUT['before'] = snapshot(before)

    drv = A._driver()
    severe = []
    try:
        A.login_and_open(drv)
        A.search(drv, REAL_NAME)
        A.open_edit(drv, REAL_NAME)
        A.open_tab(drv, '结果配置')

        txt = A.sheet(drv).text
        rows = A.rule_rows(drv)
        save_btn = drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")
        info = {
            'rule_rows': rows,
            'hint_no_rule': '该维度未配置评分规则' in txt,
            'result_unset': '未设置' in txt,
            'prompt_choose_type': '请选择结果类型' in txt,
            'save_enabled': save_btn.get_attribute('disabled') is None,
            'sheet_text_head': txt.replace('\n', ' | ')[:400],
        }
        OUT['drawer'] = info
        A.log('121 抽屉 结果配置：%s' % json.dumps(
            {k: v for k, v in info.items() if k != 'sheet_text_head'}, ensure_ascii=False))

        A.set_theme(drv, 'light')
        shot_light = A.shot(drv, '121_drawer_result_light.png')
        A.set_theme(drv, 'dark')
        shot_dark = A.shot(drv, '121_drawer_result_dark.png')
        A.set_theme(drv, 'light')
        OUT['shots'] = [os.path.basename(shot_light), os.path.basename(shot_dark)]

        assert rows == 0, '真实维度 121 冒出 %d 条规则行' % rows
        assert info['hint_no_rule'], '缺「该维度未配置评分规则」'
        assert info['result_unset'], '缺「未设置」'
        assert not info['prompt_choose_type'], '出现「请选择结果类型」'
        assert info['save_enabled'], '保存按钮被禁用'

        A.drain_perf(drv)
        dt = A.save(drv)
        reqs = A.collect_perf(drv)
        put = A.last_request(reqs, 'PUT', '/evaluation/dimensions/%d' % REAL_ID)
        assert put is not None, '没有抓到 PUT 请求'
        body = json.loads(put.get('postData') or '{}')
        OUT['put'] = {'status': put.get('status'), 'url': put.get('url'),
                      'rule': body.get('rule'), 'result_type': body.get('result_type'),
                      'seconds': round(dt, 2)}
        A.log('PUT 121 status=%s %.2fs 载荷 rule=%s rt=%s' % (
            put.get('status'), dt, json.dumps(body.get('rule'), ensure_ascii=False),
            body.get('result_type')))
        assert put.get('status') in (200, 201), put

        after = A.get_dim(REAL_ID)
        OUT['after'] = snapshot(after)
        A.log('GET 121 after rule=%s rt=%s name=%s' % (
            json.dumps(after['rule'], ensure_ascii=False), after['result_type'], after['name']))
        assert after['rule'] == before['rule'], '真实维度 rule 被改：%r → %r' % (
            before['rule'], after['rule'])
        assert after['result_type'] == before['result_type'], 'result_type 被改'
        assert after['name'] == before['name'], 'name 被改'

        # 刷新列表 + 重开抽屉，确认界面也是 0 条规则（回读不只信接口）
        A.reload_eval(drv)
        A.search(drv, REAL_NAME)
        A.open_edit(drv, REAL_NAME)
        A.open_tab(drv, '结果配置')
        txt2 = A.sheet(drv).text
        OUT['reopen'] = {'rule_rows': A.rule_rows(drv),
                         'hint_no_rule': '该维度未配置评分规则' in txt2,
                         'result_unset': '未设置' in txt2,
                         'prompt_choose_type': '请选择结果类型' in txt2}
        A.log('重开抽屉：%s' % json.dumps(OUT['reopen'], ensure_ascii=False))
        assert OUT['reopen']['rule_rows'] == 0
        assert OUT['reopen']['hint_no_rule'] and OUT['reopen']['result_unset']
        assert not OUT['reopen']['prompt_choose_type']
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        A.wait_for(lambda: A.sheet(drv) is None, timeout=20, desc='关闭抽屉')

        severe = A.dump_console(drv)
        OUT['console_severe'] = severe
        A.log('控制台 SEVERE=%d %s' % (len(severe), [e.get('message', '')[:160] for e in severe]))
    finally:
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass

    with open(os.path.join(A.ART, 'report_int1815_121.json'), 'w', encoding='utf-8') as fh:
        json.dump(OUT, fh, ensure_ascii=False, indent=1)
    A.log('DONE')


if __name__ == '__main__':
    main()
