# -*- coding: utf-8 -*-
"""INT-1484 复验段 (2)：真实维度 121「拒识成功数量」编辑 → 不改字段 → 保存 → GET 回读。

INT-1732（P2：编辑抽屉默认 5 条规则顶替真实 rule、原样保存覆盖 rule 并丢 defaultScore）
修复后，必须在**真实维度**上做一次原样保存，证明保存不会写坏真实配置。

做法：
  ① GET /evaluation/dimensions/121 全量快照（before）
  ② 浏览器打开 /Evaluation → 搜「拒识成功数量」→ 编辑 → 结果配置 tab
     记录规则行数 / 未配置提示 / 结果类型文案，浅深截图
  ③ 不改任何字段，点保存；抓 PUT 请求体与状态
  ④ GET 回读（after）：rule / defaultScore / result_type 必须与 before 完全一致
  ⑤ 若 after.rule 与 before 不同（万一失败）→ 用 before 全量 PUT 还原，并在报告里标 restored=True

真实记录只做本卡要求的一次原样保存，不做任何字段修改。
输出：tests/ui/artifacts/int1484_real121/run.log + 截图。
"""
import argparse
import json
import os
import sys

from verify_int1484_retest_int1732 import (
    EMPTY_HINT,
    PROJECT_ROOT,
    _api,
    _driver,
    api_base,
    close_sheet,
    collect_requests,
    get_dimension,
    open_edit,
    open_result_tab,
    rule_row_count,
    save_and_wait,
    search,
    set_theme,
    sheet_text,
    shot,
    wait_for,
)

REAL_DIM_ID = 121
REAL_DIM_NAME = '拒识成功数量'


def restore(base, before):
    payload = dict(before)
    for key in ('id', 'created_at', 'updated_at', 'created_by_user_id'):
        payload.pop(key, None)
    status, body = _api('%s/evaluation/dimensions/%s' % (api_base(base), REAL_DIM_ID),
                        method='PUT', payload=payload)
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    artifacts = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1484_real121')
    os.makedirs(artifacts, exist_ok=True)
    report = {'base': base, 'steps': [], 'requests': []}
    before = get_dimension(base, REAL_DIM_ID)
    report['before'] = {'name': before.get('name'), 'rule': before.get('rule'),
                        'result_type': before.get('result_type'),
                        'updated_at': before.get('updated_at')}
    assert before.get('rule') == {'rules': [], 'defaultScore': 0}, '121 前置 rule 不符: %r' % before.get('rule')
    drv = _driver()
    try:
        drv.get(base + '/Evaluation')
        wait_for(lambda: drv.find_elements('css selector', 'input[placeholder="搜索评估维度..."]'),
                 timeout=90, desc='/Evaluation 渲染')
        collect_requests(drv)
        search(drv, REAL_DIM_NAME)
        open_edit(drv, REAL_DIM_NAME)
        open_result_tab(drv)
        rows = rule_row_count(drv)
        text = sheet_text(drv)
        report['drawer'] = {'rule_rows': rows, 'empty_hint': EMPTY_HINT in text,
                            'result_type_text_未设置': '未设置' in text,
                            'shows_请选择结果类型': '请选择结果类型' in text}
        assert rows == 0, '真实维度 121 打开编辑出现 %d 条规则行' % rows
        assert EMPTY_HINT in text, '真实维度 121 缺少「%s」' % EMPTY_HINT
        set_theme(drv, 'light')
        shot(drv, artifacts, '01_real121_light.png')
        set_theme(drv, 'dark')
        shot(drv, artifacts, '02_real121_dark.png')
        set_theme(drv, 'light')
        collect_requests(drv)
        save_and_wait(drv, timeout=480)
        reqs = collect_requests(drv)
        puts = [r for r in reqs if '/evaluation/dimensions/121' in r['url'] and r['method'] == 'PUT']
        assert puts, '未捕获 PUT /evaluation/dimensions/121'
        put = puts[-1]
        body = json.loads(put['postData'] or '{}')
        report['requests'].append(put)
        report['put_payload'] = {'rule': body.get('rule'), 'result_type': body.get('result_type'),
                                 'name': body.get('name')}
        after = get_dimension(base, REAL_DIM_ID)
        report['after'] = {'rule': after.get('rule'), 'result_type': after.get('result_type'),
                           'updated_at': after.get('updated_at')}
        assert put['status'] == 200, 'PUT 状态 %r' % put['status']
        assert body.get('rule') == before.get('rule'), 'PUT 载荷 rule 被改: %r' % body.get('rule')
        assert after.get('rule') == before.get('rule'), 'GET 回读 rule 变了: %r → %r' % (
            before.get('rule'), after.get('rule'))
        assert after.get('result_type') == before.get('result_type'), 'GET 回读 result_type 变了'
        report['steps'].append('真实维度 121 原样保存 → PUT 200 / 载荷 rule=%s / 回读 rule=%s ✅'
                               % (json.dumps(body.get('rule'), ensure_ascii=False),
                                  json.dumps(after.get('rule'), ensure_ascii=False)))
        report['ok'] = True
    except Exception as exc:  # noqa: BLE001
        report['ok'] = False
        report['error'] = repr(exc)
        try:
            report['visible_text'] = drv.find_element('tag name', 'body').text[:3000]
        except Exception:
            pass
        # 真实记录被写坏时立刻用快照还原
        try:
            now = get_dimension(base, REAL_DIM_ID)
            if now.get('rule') != before.get('rule'):
                report['restored_status'] = restore(base, before)
                report['restored'] = True
        except Exception as restore_exc:  # noqa: BLE001
            report['restore_error'] = repr(restore_exc)
        raise
    finally:
        try:
            close_sheet(drv)
        except Exception:
            pass
        with open(os.path.join(artifacts, 'run.log'), 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
