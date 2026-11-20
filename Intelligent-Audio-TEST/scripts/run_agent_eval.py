# -*- coding: utf-8 -*-
"""五层 Agent 评测门禁入口（INT-2475）——一条命令跑完全部评测。

用法::

    python scripts/run_agent_eval.py                       # 五层全跑（沙箱 T1）
    python scripts/run_agent_eval.py --out ./agent_eval_out
    python scripts/run_agent_eval.py --layers e2e,skill     # 子集（默认 exit 1）
    python scripts/run_agent_eval.py --layers e2e,skill --allow-skip
    python scripts/run_agent_eval.py --sandbox-tier t2     # 需 docker 已注册 runsc
    python scripts/run_agent_eval.py --changed-skills auto --base-ref V10.11.2
    python scripts/run_agent_eval.py --skills algorithm-config,audio-import

产出一份机器可读报告（``<out>/report.json``）与人读摘要（``<out>/report.md``）。
退出码：0 全通过（**只认五层全跑且全过**）；1 有层未通过（含被改坏的 Skill，
报告按 ``skill:<name>`` 指出具体集合），或层不完整（``--layers`` 子集 /
``--sandbox-tier none`` 跳过的层）；2 基础设施不可用（Docker / 镜像 /
runsc / 评测集缺失）。层不完整默认按 1 退出，只有显式 ``--allow-skip``（本地排障）
才放行；报告顶层恒带 ``layers_expected`` / ``layers_skipped`` / ``full_five`` /
``degraded``，降级可在报告里机器分辨。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_OUT = os.path.join(PROJECT_ROOT, 'tests', 'agent_eval', 'out')
DEFAULT_BASE_REF = 'V10.11.2'


def _parse_layers(raw: str):
    value = (raw or 'all').strip()
    if value in ('', 'all'):
        from tests.agent_eval.gate import LAYER_ORDER
        return list(LAYER_ORDER)
    return [item.strip() for item in value.split(',') if item.strip()]


def _parse_skills(raw: str):
    if not raw or raw.strip() in ('none', 'all'):
        return None
    return [item.strip() for item in raw.split(',') if item.strip()]


def _section(title: str) -> None:
    print(f'\n== {title} ==')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='INT-2475 五层 Agent 评测门禁（端到端 / 单 Skill / 压缩 / '
                    '沙箱 / 恢复）')
    parser.add_argument('--layers', default=os.environ.get(
        'AGENT_EVAL_LAYERS', 'all'),
        help='逗号分隔的层；all=五层全跑（默认）')
    parser.add_argument('--out', default=os.environ.get(
        'AGENT_EVAL_OUT', DEFAULT_OUT), help='报告输出目录')
    parser.add_argument('--sandbox-tier', default=os.environ.get(
        'AGENT_EVAL_SANDBOX_TIER', 't1'),
        choices=('t1', 't2', 'all', 'none'),
        help='沙箱层级：t1（默认）/ t2（需 runsc）/ all / none（跳过）')
    parser.add_argument('--skills', default=os.environ.get(
        'AGENT_EVAL_SKILLS', ''),
        help='只评估指定 Skill（逗号分隔）；缺省评估全部')
    parser.add_argument('--changed-skills', default=os.environ.get(
        'AGENT_EVAL_CHANGED_SKILLS', 'none'),
        help='auto=按 git diff 判定变更 Skill 并只跑对应集合；'
             'none=不限定（默认）')
    parser.add_argument('--base-ref', default=os.environ.get(
        'AGENT_EVAL_GATE_BASE', DEFAULT_BASE_REF),
        help=f'--changed-skills auto 的比较基线（默认 {DEFAULT_BASE_REF}）')
    parser.add_argument('--json', action='store_true',
                        help='stdout 额外打印机器可读 JSON')
    parser.add_argument('--allow-infra-unavailable', action='store_true',
                        help='基础设施不可用时仍以 0 退出（仅本地排障用，CI 禁用）')
    parser.add_argument('--allow-skip', action='store_true',
                        default=(os.environ.get('AGENT_EVAL_ALLOW_SKIP', '')
                                 .strip().lower() in ('1', 'true', 'yes', 'on')),
                        help='层不完整（--layers 子集 / --sandbox-tier none）时仍以 0 '
                             '退出：默认按 1 退出，只有显式放行才返回 0，且报告仍标 '
                             'layers_skipped / full_five=false（仅本地排障用，CI 禁用）')
    args = parser.parse_args(argv)

    try:
        layers = _parse_layers(args.layers)
        skills = _parse_skills(args.skills)
        changed = []
        if args.changed_skills.strip() == 'auto':
            from tests.agent_eval.gate import changed_skills
            changed = changed_skills(args.base_ref)
            print(f'变更 Skill（{args.base_ref}...工作区）：{changed or "无"}')
        elif args.changed_skills.strip() not in ('', 'none'):
            changed = _parse_skills(args.changed_skills) or []
        from tests.agent_eval.gate import run_gate
        report = run_gate(layers, skills=skills,
                          sandbox_tier=args.sandbox_tier, changed=changed,
                          allow_skip=args.allow_skip)
    except Exception as exc:  # noqa: BLE001 - 入口统一成退出码 2
        print(f'[ERROR] 评测门禁无法启动：{exc}', file=sys.stderr)
        if args.json:
            print(json.dumps({'gate': 'INT-2475', 'passed': False,
                              'exit_code': 2, 'error': str(exc)},
                             ensure_ascii=False, indent=2))
        return 2

    paths = report.write(args.out)
    _print_summary(report)
    print(f"\nreport: {paths['json']}")
    print(f"summary: {paths['markdown']}")
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if args.allow_infra_unavailable and report.exit_code == 2:
        print('\n[--allow-infra-unavailable] 基础设施不可用已降级为 exit 0'
              '（报告 exit_code=2，仅供本地排障）')
        return 0
    return report.exit_code


def _print_summary(report) -> None:
    _section('分层结果')
    for name in report.layers:
        layer = report.layers[name]
        status = {'passed': 'PASS', 'failed': 'FAIL',
                  'unavailable': 'UNAVAILABLE', 'skipped': 'SKIP'}.get(
                      layer.status, layer.status)
        print(f'  [{status:>11}] {name:<10} {layer.duration_seconds:6.1f}s')
        for failure in layer.failures:
            print(f'      - {failure["set"]}: {failure["detail"]}')
    cost = report.cost_totals()
    _section('耗时与成本')
    print(f"  墙钟 {cost['wall_seconds']:.1f}s | 模型轮次 "
          f"{cost['llm_calls']} | 工具调用 {cost['tool_calls']} | "
          f"输入 ≈{cost['approx_prompt_tokens']} tokens")
    _section('结论')
    if report.degraded:
        parts = []
        if report.layers_skipped:
            parts.append(f'跳过 {", ".join(report.layers_skipped)}')
        if report.layers_missing:
            parts.append(f'未跑 {", ".join(report.layers_missing)}')
        if report.unavailable_layers:
            parts.append(f'不可用 {", ".join(report.unavailable_layers)}')
        print(f'  层完整性：降级（{"; ".join(parts)}）'
              + ('；已显式 --allow-skip 放行' if report.allow_skip
                 else '；默认按未通过处置（exit 1）'))
    else:
        print('  层完整性：五层全跑')
    if report.passed:
        label = '五层' if report.full_five else '降级放行所选层'
        print(f'  PASS（{label}门槛全部满足）')
    elif report.failed_layers:
        print(f'  FAIL：{", ".join(report.failed_layers)}')
        for failure in report.failures():
            print(f"    * {failure['set']} -> {failure['detail']}")
    elif report.unavailable_layers:
        print(f'  UNAVAILABLE：{", ".join(report.unavailable_layers)}'
              f'（基础设施不可用，非用例失败）')
    else:
        print(f'  INCOMPLETE：层不完整（exit={report.exit_code}），不算全通过；'
              f'本地排障可加 --allow-skip')


if __name__ == '__main__':
    sys.exit(main())
