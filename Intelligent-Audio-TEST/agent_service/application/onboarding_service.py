# -*- coding: utf-8 -*-
"""App/API 接入包的组装（INT-2491，方案 §6.6「交付包」）。

把 ``driver_propose`` 的代码提案装配成**固定结构的接入包**：

```text
onboarding/<app_type|vendor>/
├─ driver.py / adapter.py
├─ config.yaml
├─ capabilities.json
├─ test_plan.md
├─ ui_trace.json
├─ tests/
├─ smoke_case.json
├─ manifest.json
└─ onboarding_report.md
```

本模块只做确定性渲染（无网络 / 无设备 / 无落库）；包校验在
``shared.agent_tools.onboarding``，staging 落盘与冒烟在应用服务层。
所有内容由提案输入与 ``capabilities`` 推导，同一输入重复生成字节一致
（报告里的 hash 也是输入 hash，不含时间戳）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Sequence

from shared.agent_tools import driver_tools, onboarding


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _artifact_of(generated: Mapping[str, Any], kind: str
                 ) -> Dict[str, Any]:
    for item in generated.get('artifacts') or ():
        if item.get('artifact_kind') == kind:
            return dict(item)
    return {}


def _package_tests(generated: Mapping[str, Any],
                   renames: Mapping[str, str]) -> Dict[str, str]:
    """把提案 tests/ 原样带入；驱动 / 适配器模块名改为包内的 driver / adapter。"""
    files: Dict[str, str] = {}
    for path, content in (generated.get('files') or {}).items():
        if not path.startswith('tests/'):
            continue
        text = content
        for module, package_module in renames.items():
            text = text.replace(module, package_module)
        files[path] = text
    return files


def _expected_fields(capabilities: Mapping[str, Any],
                     metrics: Sequence[str]) -> List[str]:
    fields = ['success', 'message']
    capture_modes = set(capabilities.get('capture_modes') or ())
    wants_text = bool(set(metrics) & {'WER', 'CER', 'SENTENCE_ACC',
                                      'FIRST_TOKEN_LATENCY', 'REPLY_LATENCY'})
    wants_audio = bool(set(metrics) & {'TTS_QUALITY', 'BARGE_IN'})
    wants_timing = bool(set(metrics) & {'FIRST_TOKEN_LATENCY', 'REPLY_LATENCY',
                                        'BARGE_IN'})
    declared = set(capabilities.get('result_fields') or ())
    if wants_text:
        for key in ('asr', 'text', 'answer'):
            if key in declared:
                fields.append(key)
                break
    if wants_audio:
        for key in ('wav_path', 'ai_wav', 'user_wav', 'record_path'):
            if key in declared:
                fields.append(key)
                break
    if wants_timing:
        for key in ('start_ms', 'end_ms', 'first_frame_ms', 'latency_ms'):
            if key in declared:
                fields.append(key)
    # 采集方式里含 PCM 时，用户 / AI 音频字段一并验证（真实实现要用）
    if 'PCM_CAPTURE' in capture_modes:
        for key in ('user_wav', 'ai_wav'):
            if key in declared and key not in fields:
                fields.append(key)
    return sorted(set(fields))


def _mock_results(fields: Sequence[str]) -> Dict[str, Any]:
    values = {
        'success': True,
        'message': 'staging mock：未在真机执行',
        'asr': '你好，世界',
        'text': '你好，世界',
        'question': '你好',
        'answer': '你好，世界',
        'wav_path': 'staging://mock/ai.wav',
        'user_wav': 'staging://mock/user.wav',
        'ai_wav': 'staging://mock/ai.wav',
        'record_path': 'staging://mock/record.mp4',
        'start_ms': 0,
        'end_ms': 1200,
        'first_frame_ms': 220,
        'latency_ms': 800,
    }
    return {field: values.get(field) for field in fields}


def _config_yaml(target_kind: str, arguments: Mapping[str, Any],
                 driver: Mapping[str, Any], adapter: Mapping[str, Any]
                 ) -> str:
    lines = [
        '# onboarding 交付包配置（staging only）：不写生产注册表、不自动发布。',
        f'target_kind: {target_kind}',
        'capabilities: capabilities.json',
    ]
    if driver:
        key = driver.get('registry_key') or {}
        lines.extend([
            'driver:',
            '  module: driver.py',
            f'  class: {driver.get("class")}',
            f'  app_type: {key.get("app_type")}',
            f'  version: {key.get("version")}',
            f'  platform: {key.get("platform")}',
            '  registry: staging（不写生产注册表）',
        ])
    if adapter:
        key = adapter.get('registry_key') or {}
        lines.extend([
            'vendor_adapter:',
            '  module: adapter.py',
            f'  class: {adapter.get("class")}',
            f'  protocol: {key.get("protocol")}',
            f'  vendor: {key.get("vendor")}',
            f'  api_id: {adapter.get("api_id")}',
            '  credentials: 走现有 key resolver（配置不含凭证）',
        ])
    lines.append('smoke:')
    lines.append('  case: smoke_case.json')
    lines.append('  runner: task_run(mode=SMOKE)')
    return '\n'.join(lines) + '\n'


def _test_plan_md(arguments: Mapping[str, Any], target_kind: str,
                  capabilities: Mapping[str, Any], plan: Mapping[str, Any],
                  package_ref: str) -> str:
    goals = '、'.join(plan.get('test_goals') or []) or '（按能力画像推断）'
    lines = [
        '# 接入测试计划',
        '',
        f'- 交付包：`{package_ref}`',
        f'- target_kind：`{target_kind}`',
        f'- 测试目标：{goals}',
        '',
        '## 测量路径',
        '',
        '| 项 | 取值 |',
        '|---|---|',
        f'| 输入方式 | {", ".join(plan.get("stimulus_modes") or []) or "-"} |',
        f'| 采集方式 | {", ".join(plan.get("capture_modes") or []) or "-"} |',
        f'| 完成判定 | {plan.get("completion")} |',
        f'| 时序点 | {", ".join(plan.get("timing_points") or []) or "-"} |',
        f'| 可计算指标 | {", ".join(plan.get("computable_metrics") or []) or "-"} |',
        f'| 测试资产 | {", ".join(plan.get("assets") or []) or "测试音 / 文本按用例配置"} |',
        '',
        '## 验收',
        '',
        '1. 按上述采集方式跑一轮，返回字段对齐现有驱动契约，不另造 schema；',
        '2. 至少产出一个可计算指标（ASR 文本或 TTS 音频 + 时序）；',
        '3. 指标由 algorithm_service / evaluation_service 计算，驱动不写 WER / MOS；',
        '4. staging 冒烟用 `task_run(mode=SMOKE, driver_ref, case_ref)`，'
        '不写生产注册表。',
        '',
        '## 迭代',
        '',
        f'失败必须带新证据，最多 {onboarding.MAX_ITERATIONS} 轮；第 3 轮仍不'
        '收敛交回诊断，不无限重试。',
        '',
    ]
    limitations = plan.get('limitations') or []
    if limitations:
        lines.extend(['## 已知限制', ''])
        lines.extend(f'- {item}' for item in limitations)
        lines.append('')
    return '\n'.join(lines)


def _report_md(arguments: Mapping[str, Any], target_kind: str,
               capabilities: Mapping[str, Any], plan: Mapping[str, Any],
               package_ref: str, source_trace: Mapping[str, Any],
               static: Mapping[str, Any], t2: Mapping[str, Any],
               rollback: Sequence[str]) -> str:
    trace_sha = source_trace.get('sha256') or '-'
    lines = [
        '# 接入报告',
        '',
        '> 本报告由 `driver_propose` 确定性生成；只产提案与 staging 包，'
        '不写生产注册表、不自动发布。',
        '',
        '## 目标与入口',
        '',
        f'- target_kind：`{target_kind}`',
        f'- 测试目标：{"、".join(plan.get("test_goals") or []) or "-"}',
        f'- 接入包：`{package_ref}`',
        '',
        '## 测量路径',
        '',
        f'- 输入：{", ".join(plan.get("stimulus_modes") or []) or "-"}',
        f'- 采集：{", ".join(plan.get("capture_modes") or []) or "-"}',
        f'- 完成判定：{plan.get("completion")}',
        f'- 时序：{", ".join(plan.get("timing_points") or []) or "-"}',
        f'- 指标：{", ".join(plan.get("computable_metrics") or []) or "-"}',
        '',
        '## 证据',
        '',
    ]
    if target_kind != driver_tools.TARGET_API_ADAPTER:
        lines.append(
            f'- UI 轨迹：`ui_trace.json`（sha256=`{trace_sha}`，'
            f'动作 {source_trace.get("actions", 0)} 个，'
            f'页面 {source_trace.get("pages", 0)} 个）；')
    lines.extend([
        f'- 静态检查：{static.get("outcome")}；',
        f'- T2 沙箱：{t2.get("outcome")}（{t2.get("reason")}）；',
        '- staging 冒烟：见 `task_run(mode=SMOKE)` 的返回证据（mock 或真机）。',
        '',
        '## 已知限制',
        '',
    ])
    limitations = list(plan.get('limitations') or [])
    if target_kind != driver_tools.TARGET_API_ADAPTER:
        limitations.append('生成的驱动是待评审骨架：initialize / pre_process / '
                           'get_results 需补真实实现后才能真机冒烟。')
    if t2.get('outcome') != 'SUCCEEDED':
        limitations.append(f'T2 未通过（{t2.get("reason")}）：包不可发布，'
                           '只用于 staging 评审。')
    lines.extend(f'- {item}' for item in limitations or ['无'])
    lines.extend([
        '',
        '## 回滚',
        '',
    ])
    lines.extend(f'- {item}' for item in rollback or ['删除 staging 目录即可，生产无变化。'])
    lines.extend([
        '',
        '## 审批',
        '',
        '- 生成与 staging 冒烟按 WRITE 审批；写生产注册表是 DESTRUCTIVE，'
        '必须单独的审批单且本期开关默认关闭。',
        '',
    ])
    return '\n'.join(lines)


class OnboardingPackageBuilder:
    """把 ``driver_propose`` 的产物装配成固定结构接入包（纯函数）。"""

    def build(self, arguments: Mapping[str, Any], generated: Mapping[str, Any],
              target_kind: str, capabilities: Mapping[str, Any],
              plan: Mapping[str, Any], static: Mapping[str, Any],
              t2: Mapping[str, Any]) -> Dict[str, Any]:
        args = dict(arguments or {})
        caps = driver_tools.normalize_capabilities(dict(capabilities or {}))
        driver = _artifact_of(generated, driver_tools.TARGET_DEVICE_DRIVER)
        adapter = _artifact_of(generated, driver_tools.TARGET_API_ADAPTER)
        source_trace = driver_tools.trace_summary(args.get('ui_trace'))

        files: Dict[str, str] = {}
        renames: Dict[str, str] = {}
        proposal_files = dict(generated.get('files') or {})
        if driver:
            module = driver.get('module')
            files['driver.py'] = proposal_files.get(module, '')
            renames[str(module)[:-3].replace('/', '.')] = 'driver'
        if adapter:
            module = adapter.get('module')
            files['adapter.py'] = proposal_files.get(module, '')
            renames[str(module)[:-3].replace('/', '.')] = 'adapter'
        files.update(_package_tests(generated, renames))
        files['capabilities.json'] = _json(caps)
        files['config.yaml'] = _config_yaml(target_kind, args, driver, adapter)
        if driver:
            files['ui_trace.json'] = _json(args.get('ui_trace') or {})

        slug = onboarding.package_slug(target_kind, args)
        root = f'{onboarding.PACKAGE_ROOT}/{slug}'
        package_ref = onboarding.package_ref(files)

        metrics = [metric for metric in plan.get('computable_metrics') or []
                   if metric in driver_tools.SUPPORTED_METRICS]
        if not metrics:
            metrics = list(caps.get('supported_metrics') or [])
        expected_fields = _expected_fields(caps, metrics)
        if target_kind == driver_tools.TARGET_API_ADAPTER:
            steps = [
                '按 contract 渲染请求（端点 / 鉴权 / 样例）',
                '按 stimulus_modes 上传测试音频或文本',
                '按 capture_modes 采集响应',
                '校验返回字段与完成判定',
            ]
        else:
            steps = [
                'initialize / pre_process 进入功能页',
                '按 stimulus_modes 播放测试音频',
                '按 capture_modes 采集一轮结果',
                '校验返回字段与完成判定',
            ]
        smoke_case = {
            'case_ref': f'smoke-{slug}',
            'target_kind': target_kind,
            'test_goals': list(plan.get('test_goals') or []),
            'inputs': {
                'assets': list(plan.get('assets') or []),
                'stimulus_modes': list(plan.get('stimulus_modes') or []),
            },
            'steps': steps,
            'expected_fields': expected_fields,
            'metrics': metrics,
            'mock_results': _mock_results(expected_fields),
        }
        files['smoke_case.json'] = _json(smoke_case)

        artifacts = []
        if driver:
            artifacts.append({
                'artifact_kind': driver_tools.TARGET_DEVICE_DRIVER,
                'path': 'driver.py',
                'class': driver.get('class'),
                'registry_key': dict(driver.get('registry_key') or {}),
            })
        if adapter:
            artifacts.append({
                'artifact_kind': driver_tools.TARGET_API_ADAPTER,
                'path': 'adapter.py',
                'class': adapter.get('class'),
                'registry_key': dict(adapter.get('registry_key') or {}),
                'api_id': adapter.get('api_id'),
            })
        if len(artifacts) == 2:
            artifacts[0]['pair_with'] = artifacts[1]['path']
            artifacts[1]['pair_with'] = artifacts[0]['path']

        manifest = {
            'target_kind': target_kind,
            'entry': _entry_for(target_kind),
            'root': root,
            # package_ref 指向「除 manifest 自身之外」的内容 hash，避免自引用。
            'package_ref': onboarding.package_ref(
                {path: content for path, content in files.items()
                 if path != 'manifest.json'}),
            'artifacts': artifacts,
            'capabilities': 'capabilities.json',
            'source_trace': 'ui_trace.json' if driver else None,
            'smoke_case': 'smoke_case.json',
            'files': sorted(files),
            'metrics': metrics,
            'validation': {
                'static_check': static.get('outcome'),
                't2': t2.get('outcome'),
                'publishable': bool(
                    static.get('outcome') == 'OK'
                    and t2.get('outcome') == 'SUCCEEDED'),
            },
        }
        # 先写 test_plan / report（它们不参与 manifest 自引用），再写 manifest。
        files['test_plan.md'] = _test_plan_md(
            args, target_kind, caps, plan, package_ref)
        files['onboarding_report.md'] = _report_md(
            args, target_kind, caps, plan, package_ref, source_trace,
            static, t2, generated.get('rollback') or [])
        files['manifest.json'] = _json(manifest)

        files['manifest.json'] = _json(manifest)
        final_ref = onboarding.package_ref(files)

        entries = [
            {
                'path': f'{root}/{path}',
                'bytes': len(content.encode('utf-8')),
                'sha256': _sha256(content),
            }
            for path, content in sorted(files.items())
        ]
        return {
            'root': root,
            'driver_ref': final_ref,
            'sha256': onboarding.package_sha256(files),
            'target_kind': target_kind,
            'entry': _entry_for(target_kind),
            'files': files,
            'entries': entries,
            'manifest': manifest,
            'smoke_case': smoke_case,
            'measurement_plan': dict(plan),
        }


def _entry_for(target_kind: str) -> str:
    return {
        driver_tools.TARGET_DEVICE_DRIVER: onboarding.ENTRY_APP,
        driver_tools.TARGET_API_ADAPTER: onboarding.ENTRY_API,
        driver_tools.TARGET_PAIR: onboarding.ENTRY_PAIR,
    }.get(target_kind, onboarding.ENTRY_APP)


__all__ = ['OnboardingPackageBuilder']
