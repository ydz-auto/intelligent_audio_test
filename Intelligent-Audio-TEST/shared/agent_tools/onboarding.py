# -*- coding: utf-8 -*-
"""App/API 接入（onboarding）的材料口径与校验（INT-2491，方案 §6.6）。

本模块是「接入包」的**共享事实源**（纯函数，不碰网络 / 文件 / 设备）：

- 入口与产物结构：``ENTRY_KINDS``（``APP`` / ``API`` / ``PAIR``）映射到
  ``driver_propose.target_kind``；交付包固定 10 项（``PACKAGE_ITEMS``），
  目录根始终是 ``onboarding/<app_type|vendor>/``；
- 测量路径（§6.5.1）：受理阶段先定「怎么喂 / 怎么收 / 怎么对齐 / 算哪个指标」。
  ``resolve_measurement_plan`` 把测试目标（ASR / TTS / 对话 / 翻译 / 降噪 /
  打断）解析成可测的采集方式与时序点；**算不出来的指标必须显式拒绝或降级**，
  不产出假指标（例如只能取 UI 文本却要 TTS 音质、只能录屏且无音轨却要
  TTS 音质、只能录屏却要 ASR 文本却没补识别步骤）；
- 交付包校验：10 项齐全、``capabilities.json`` 六组字段自洽、manifest /
  smoke_case / ui_trace 结构、报告含证据 / 已知限制 / 回滚、生成代码不含
  凭证且不联网；
- 迭代边界：最多 3 轮，失败轮必须带**新证据**（证据 hash 与上一轮不同），
  第 3 轮仍不收敛只能交回诊断，不无限重试。

指标词表 / 结果字段统一来自 ``shared.agent_tools.driver_tools``，不另造
schema；驱动只采集文本 / 音频 / 时序，WER / MOS 等由 algorithm_service /
evaluation_service 计算。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shared.agent_tools import driver_tools

# ---------------------------------------------------------------- 入口

ENTRY_APP = 'APP'
ENTRY_API = 'API'
ENTRY_PAIR = 'PAIR'
ENTRY_KINDS: Tuple[str, ...] = (ENTRY_APP, ENTRY_API, ENTRY_PAIR)

#: 入口 → ``driver_propose.target_kind``（同一个提案工具承担三个入口）
TARGET_KIND_BY_ENTRY: Dict[str, str] = {
    ENTRY_APP: driver_tools.TARGET_DEVICE_DRIVER,
    ENTRY_API: driver_tools.TARGET_API_ADAPTER,
    ENTRY_PAIR: driver_tools.TARGET_PAIR,
}

#: 测试目标（受理阶段必须逐项确认）
TEST_GOALS: Tuple[str, ...] = (
    'ASR', 'TTS', 'DIALOG', 'TRANSLATION', 'NOISE_REDUCTION', 'BARGE_IN')

#: 测试目标 → 该目标至少需要的指标（任一即可；由平台计算）
GOAL_METRICS: Dict[str, Tuple[str, ...]] = {
    'ASR': ('WER', 'CER', 'SENTENCE_ACC'),
    'TTS': ('TTS_QUALITY',),
    'DIALOG': ('SENTENCE_ACC', 'REPLY_LATENCY'),
    'TRANSLATION': ('SENTENCE_ACC',),
    'NOISE_REDUCTION': ('TTS_QUALITY', 'WER', 'CER'),
    'BARGE_IN': ('BARGE_IN',),
}

#: 测试目标 → 可接受的采集方式（§6.5.1 五类模板的归纳）
GOAL_CAPTURES: Dict[str, Tuple[str, ...]] = {
    'ASR': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE', 'SCREEN_RECORD',
            'PCM_CAPTURE'),
    'TTS': ('SCREEN_RECORD', 'PCM_CAPTURE', 'API_RESPONSE'),
    'DIALOG': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE'),
    'TRANSLATION': ('UI_TEXT', 'APP_EXPORT', 'API_RESPONSE'),
    'NOISE_REDUCTION': ('PCM_CAPTURE', 'API_RESPONSE'),
    'BARGE_IN': ('PCM_CAPTURE', 'API_RESPONSE'),
}

#: 测试目标 → 至少需要的一个时序点（延迟 / 打断类）
GOAL_TIMINGS: Dict[str, Tuple[str, ...]] = {
    'DIALOG': ('FINAL_TEXT', 'REPLY_END'),
    'BARGE_IN': ('PLAYBACK_START', 'PLAYBACK_END'),
}

#: 只出文本的采集方式（能直接拿到 ASR / 对话 / 翻译文本）
TEXT_CAPTURES = frozenset({'UI_TEXT', 'APP_EXPORT', 'API_RESPONSE'})

#: 需要额外 ASR 识别步骤的采集方式（录屏 / PCM 本身没有文本）
NEEDS_RECOGNITION = frozenset({'SCREEN_RECORD', 'PCM_CAPTURE'})

MEASUREMENT_PROFILE_KEYS = (
    'test_goals', 'stimulus_modes', 'capture_modes', 'timing_points',
    'capture_details', 'completion', 'assets', 'extra_recognition',
)

# ---------------------------------------------------------------- 交付包

PACKAGE_ROOT = 'onboarding'

#: 交付包固定 10 项（目录项以 ``/`` 结尾）。设备驱动 / 成对交付含
#: ``driver.py`` + ``ui_trace.json``；纯 API 入口含 ``adapter.py``，没有 UI 轨迹。
PACKAGE_ITEMS: Dict[str, Tuple[str, ...]] = {
    driver_tools.TARGET_DEVICE_DRIVER: (
        'driver.py', 'config.yaml', 'capabilities.json', 'test_plan.md',
        'ui_trace.json', 'tests/', 'smoke_case.json', 'manifest.json',
        'onboarding_report.md'),
    driver_tools.TARGET_API_ADAPTER: (
        'adapter.py', 'config.yaml', 'capabilities.json', 'test_plan.md',
        'tests/', 'smoke_case.json', 'manifest.json', 'onboarding_report.md'),
    driver_tools.TARGET_PAIR: (
        'driver.py', 'adapter.py', 'config.yaml', 'capabilities.json',
        'test_plan.md', 'ui_trace.json', 'tests/', 'smoke_case.json',
        'manifest.json', 'onboarding_report.md'),
}

#: 报告必须覆盖的三节（卡面验收 9）
REPORT_SECTIONS: Tuple[str, ...] = ('证据', '已知限制', '回滚')

#: 生成代码禁止联网（T2 禁网；提案里出现网络依赖即视为不可交付）
FORBIDDEN_IMPORTS = frozenset({
    'requests', 'httpx', 'urllib', 'urllib2', 'urllib3', 'socket',
    'websocket', 'websockets', 'aiohttp', 'http', 'grpc', 'paramiko', 'ftplib',
})

#: 生成代码禁止出现凭证形态（Key 走现有 resolver，不写死）
CREDENTIAL_PATTERNS: Tuple[Tuple[str, 're.Pattern[str]'], ...] = (
    ('OpenAI 风格 Key', re.compile(r'\bsk-[A-Za-z0-9_\-]{8,}')),
    ('AWS Access Key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Bearer 令牌', re.compile(r'Bearer\s+[A-Za-z0-9._\-]{12,}')),
    ('明文 api_key 赋值',
     re.compile(r'\bapi[_-]?key\s*=\s*[\'"][^\'"\s]{6,}[\'"]', re.I)),
    ('明文 password 赋值',
     re.compile(r'\bpassword\s*=\s*[\'"][^\'"\s]{4,}[\'"]', re.I)),
)

MAX_ITERATIONS = 3

#: staging 冒烟不可覆盖项（真机不可用时如实列出，不假通过）
STAGING_UNCOVERED = (
    '真机 UI 操作（生成的驱动是待评审骨架，initialize / pre_process / '
    'get_results 需补真实实现）',
    '音频播放与采集链路（声学播放 / 录屏 / PCM）',
    '平台指标计算（WER / CER / TTS_QUALITY 需真实采集结果）',
)

_SLUG_SAFE = re.compile(r'[^a-z0-9._-]+')


def _as_string_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value):
        return None
    return [item.strip() for item in value if item.strip()]


def _unknown(values: Iterable[str], allowed: Iterable[str]) -> List[str]:
    allowed_set = set(allowed)
    return sorted({value for value in values if value not in allowed_set})


def package_slug(target_kind: str, arguments: Mapping[str, Any]) -> str:
    """``onboarding/<app_type|vendor>/`` 的目录名（确定性、路径安全）。"""
    if target_kind in (driver_tools.TARGET_DEVICE_DRIVER,
                       driver_tools.TARGET_PAIR):
        base = str(arguments.get('app_type') or 'app')
        if target_kind == driver_tools.TARGET_PAIR:
            vendor = str(arguments.get('vendor') or '')
            if vendor:
                base = f'{base}_{vendor}'
    else:
        base = str(arguments.get('vendor') or 'vendor')
    slug = _SLUG_SAFE.sub('_', base.strip().lower()).strip('._-')
    return slug or 'onboarding'


def package_sha256(files: Mapping[str, str]) -> str:
    """交付包内容 hash（路径 + 内容，排序后 canonical JSON）。"""
    payload = json.dumps(
        {path: files[path] for path in sorted(files)},
        ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def package_ref(files: Mapping[str, str]) -> str:
    return 'onboarding-' + package_sha256(files)[:16]


# ---------------------------------------------------------------- 测量路径

def _has_audio_capture(captures: set, details: Mapping[str, Any]) -> bool:
    """采集方式是否能拿到**音频**（录屏默认含音轨，显式 audio=false 则不算）。"""
    if 'PCM_CAPTURE' in captures or 'API_RESPONSE' in captures:
        return True
    if 'SCREEN_RECORD' in captures:
        screen = details.get('SCREEN_RECORD') or {}
        return bool(screen.get('audio', True))
    return False


def _supports_recognition(details: Mapping[str, Any],
                          extra_recognition: bool) -> bool:
    if extra_recognition:
        return True
    for mode in ('SCREEN_RECORD', 'PCM_CAPTURE'):
        if bool((details.get(mode) or {}).get('asr')):
            return True
    return False


def _downgrade_hint(goal: str) -> str:
    if goal in ('TTS', 'NOISE_REDUCTION', 'BARGE_IN'):
        return ('降级：仅声明文本类指标（ASR / 对话文本 / 延迟）并按 UI_TEXT 或 '
                'API_RESPONSE 采集；或补充 PCM_CAPTURE / 含音轨的录屏后再评 '
                'TTS_QUALITY / BARGE_IN。')
    if goal == 'ASR':
        return ('降级：只评延迟 / 音频质量，不产出 ASR 文本指标；或改用 '
                'UI_TEXT / APP_EXPORT / API_RESPONSE 采集文本，或补 ASR 识别步骤'
                '（extra_recognition=true）。')
    return ('降级：改用能取到文本的采集方式（UI_TEXT / APP_EXPORT / '
            'API_RESPONSE），或把该目标从本次接入范围移除。')


def resolve_measurement_plan(
        profile: Any,
        capabilities: Any = None,
        target_kind: str = '') -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """解析并校验测量路径，返回 ``(错误文本, 计划)``。

    ``profile`` 为 ``None`` 时按 ``capabilities`` 反推测试目标（只做一致性
    自检，不额外要求材料）；显式给 ``measurement_profile`` 时逐项校验。
    """
    caps = capabilities if isinstance(capabilities, dict) else {}
    cap_stimuli = _as_string_list(caps.get('stimulus_modes')) or []
    cap_captures = _as_string_list(caps.get('capture_modes')) or []
    cap_timings = _as_string_list(caps.get('timing_points')) or []
    cap_metrics = _as_string_list(caps.get('supported_metrics')) or []

    if profile is None:
        goals = _goals_from_metrics(cap_metrics)
        details: Dict[str, Any] = {}
        extra_recognition = True
        completion = ''
        assets: List[str] = []
        stimuli = list(cap_stimuli)
        captures = list(cap_captures)
        timings = list(cap_timings)
    else:
        if not isinstance(profile, dict):
            return '参数 measurement_profile 必须是对象（测量路径口径）', None
        unknown = sorted(set(profile) - set(MEASUREMENT_PROFILE_KEYS))
        if unknown:
            return (f'measurement_profile 不支持字段：{"、".join(unknown)}'
                    f'（只支持 {"、".join(MEASUREMENT_PROFILE_KEYS)}）'), None
        goals = _as_string_list(profile.get('test_goals'))
        if goals is None:
            return 'measurement_profile.test_goals 必须是字符串数组', None
        if not goals:
            return ('measurement_profile.test_goals 不能为空：受理阶段必须确认'
                    '测试目标（ASR / TTS / 对话 / 翻译 / 降噪 / 打断）'), None
        bad_goals = _unknown(goals, TEST_GOALS)
        if bad_goals:
            return (f'measurement_profile.test_goals 含未知目标：'
                    f'{"、".join(bad_goals)}'), None
        details = profile.get('capture_details') or {}
        if not isinstance(details, dict):
            return 'measurement_profile.capture_details 必须是对象', None
        unknown_modes = sorted(set(details) - set(driver_tools.CAPTURE_MODES))
        if unknown_modes:
            return (f'measurement_profile.capture_details 含未知采集方式：'
                    f'{"、".join(unknown_modes)}'), None
        for mode, detail in details.items():
            if not isinstance(detail, dict):
                return (f'measurement_profile.capture_details.{mode} 必须是对象'
                        '（如 {"audio": true}）'), None
            unknown_detail = sorted(set(detail) - {'audio', 'asr'})
            if unknown_detail:
                return (f'measurement_profile.capture_details.{mode} 不支持字段：'
                        f'{"、".join(unknown_detail)}（只支持 audio / asr）'), None
        extra_recognition = bool(profile.get('extra_recognition'))
        completion = str(profile.get('completion') or '').strip()
        assets = _as_string_list(profile.get('assets'))
        if assets is None:
            return 'measurement_profile.assets 必须是字符串数组', None
        for key, cap_values in (
                ('stimulus_modes', caps.get('stimulus_modes')),
                ('capture_modes', caps.get('capture_modes')),
                ('timing_points', caps.get('timing_points'))):
            values = _as_string_list(profile.get(key))
            if values is None:
                return f'measurement_profile.{key} 必须是字符串数组', None
            declared = _as_string_list(cap_values) or []
            extra = sorted(set(values) - set(declared))
            if extra:
                return (f'measurement_profile.{key} 超出 capabilities 声明：'
                        f'{"、".join(extra)}；测量方式必须与能力画像一致'), None
        captures = _as_string_list(profile.get('capture_modes')) or cap_captures
        timings = _as_string_list(profile.get('timing_points')) or cap_timings
        stimuli = _as_string_list(profile.get('stimulus_modes')) or cap_stimuli

    capture_set = set(captures)
    timing_set = set(timings)
    for goal in goals:
        accepted = GOAL_CAPTURES.get(goal, ())
        if accepted and not (capture_set & set(accepted)):
            return (f'测量路径不可测：测试目标 {goal} 需要采集方式 '
                    f'{" / ".join(accepted)} 之一，当前只有 '
                    f'{sorted(capture_set)}。{_downgrade_hint(goal)}'), None
        if goal == 'TTS' and not _has_audio_capture(capture_set, details):
            return ('测量路径不可测：测试目标 TTS 需要音频采集，当前只有录屏且'
                    '未声明音轨（capture_details.SCREEN_RECORD.audio=false）。'
                    + _downgrade_hint(goal)), None
        if goal == 'ASR' and not (capture_set & TEXT_CAPTURES):
            if not _supports_recognition(details, extra_recognition):
                return ('测量路径不可测：测试目标 ASR 只能拿到录屏 / PCM 音频，'
                        '缺少 ASR 识别步骤（extra_recognition=true 或 '
                        'capture_details.<mode>.asr=true）。' + _downgrade_hint(goal)), None
        needs_timing = GOAL_TIMINGS.get(goal)
        if needs_timing and not (timing_set & set(needs_timing)):
            return (f'测量路径不可测：测试目标 {goal} 需要时序点 '
                    f'{" / ".join(needs_timing)} 之一，当前只有 '
                    f'{sorted(timing_set)}。'), None
        metrics = GOAL_METRICS.get(goal, ())
        if cap_metrics and metrics and not (set(metrics) & set(cap_metrics)):
            return (f'测量路径不可测：测试目标 {goal} 需要指标 '
                    f'{" / ".join(metrics)} 之一，capabilities.supported_metrics='
                    f'{sorted(set(cap_metrics))} 未声明。{_downgrade_hint(goal)}'), None

    plan = {
        'test_goals': list(goals),
        'stimulus_modes': list(stimuli),
        'capture_modes': list(captures),
        'timing_points': list(timings),
        'result_fields': list(_as_string_list(caps.get('result_fields')) or []),
        'supported_metrics': list(cap_metrics),
        'computable_metrics': computable_metrics(caps),
        'completion': completion or '按 test_plan.md 的完成判定采集一轮结果',
        'assets': list(assets or []),
        'extra_recognition': extra_recognition,
        'limitations': list(_as_string_list(caps.get('limitations')) or []),
    }
    return None, plan


def _goals_from_metrics(metrics: Sequence[str]) -> List[str]:
    goals: List[str] = []
    mapping = (
        ('ASR', {'WER', 'CER', 'SENTENCE_ACC'}),
        ('TTS', {'TTS_QUALITY'}),
        ('DIALOG', {'REPLY_LATENCY'}),
        ('BARGE_IN', {'BARGE_IN'}),
    )
    for goal, wanted in mapping:
        if wanted & set(metrics):
            goals.append(goal)
    return goals


def computable_metrics(capabilities: Any) -> List[str]:
    """按采集方式 / 时序点筛出**能算**的指标（driver_tools 的同一套规则）。"""
    caps = capabilities if isinstance(capabilities, dict) else {}
    captures = set(_as_string_list(caps.get('capture_modes')) or [])
    timings = set(_as_string_list(caps.get('timing_points')) or [])
    metrics = _as_string_list(caps.get('supported_metrics')) or []
    result: List[str] = []
    for metric in metrics:
        needs = driver_tools.METRIC_CAPTURE_REQUIREMENTS.get(metric, ())
        if needs and not (captures & set(needs)):
            continue
        timing_needs = driver_tools.METRIC_TIMING_REQUIREMENTS.get(metric, ())
        if timing_needs and not (timings & set(timing_needs)):
            continue
        result.append(metric)
    return result


def metric_fields_available(capabilities: Any,
                            result_fields: Mapping[str, Any]
                            ) -> List[str]:
    """从**采集到的结果字段**反推可计算指标（冒烟至少要有 1 个）。"""
    metrics = computable_metrics(capabilities)
    available: List[str] = []
    has_text = any(result_fields.get(key) for key in ('asr', 'text', 'answer'))
    has_audio = any(result_fields.get(key)
                    for key in ('wav_path', 'ai_wav', 'user_wav',
                                'record_path'))
    has_timing = any(result_fields.get(key) for key in
                     ('start_ms', 'end_ms', 'first_frame_ms', 'latency_ms'))
    for metric in metrics:
        if metric in ('WER', 'CER', 'SENTENCE_ACC'):
            if has_text:
                available.append(metric)
        elif metric == 'TTS_QUALITY':
            if has_audio:
                available.append(metric)
        elif metric in ('FIRST_TOKEN_LATENCY', 'REPLY_LATENCY'):
            if has_text and has_timing:
                available.append(metric)
        elif metric == 'BARGE_IN':
            if has_audio and has_timing:
                available.append(metric)
    return available


# ---------------------------------------------------------------- 迭代边界

def _evidence_digest(evidence: Any) -> str:
    payload = json.dumps(evidence, ensure_ascii=False, sort_keys=True,
                         default=str, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def evaluate_iterations(rounds: Any) -> Dict[str, Any]:
    """校验迭代历史：≤3 轮、失败轮必须带新证据、不收敛交回诊断。

    返回 ``{"ok", "error", "handback_required", "rounds", "evidence_sha256"}``；
    不抛异常，调用方按 ``ok`` 决定是否继续生成。
    """
    if rounds is None:
        return {'ok': True, 'error': None, 'handback_required': False,
                'rounds': 0, 'evidence_sha256': []}
    if not isinstance(rounds, list):
        return {'ok': False, 'error': '参数 iterations 必须是数组',
                'handback_required': False, 'rounds': 0,
                'evidence_sha256': []}
    if len(rounds) > MAX_ITERATIONS:
        return {
            'ok': False,
            'error': (f'迭代已超过 {MAX_ITERATIONS} 轮：不收敛必须交回诊断，'
                      '不能继续重试生成'),
            'handback_required': True,
            'rounds': len(rounds),
            'evidence_sha256': [],
        }
    digests: List[str] = []
    previous: Optional[str] = None
    last_outcome = ''
    for index, item in enumerate(rounds):
        number = index + 1
        if not isinstance(item, dict):
            return {'ok': False, 'error': f'iterations[{index}] 必须是对象',
                    'handback_required': False, 'rounds': len(rounds),
                    'evidence_sha256': digests}
        outcome = str(item.get('outcome') or '').strip().upper()
        if outcome not in ('PASSED', 'FAILED'):
            return {'ok': False,
                    'error': f'iterations[{index}].outcome 必须是 PASSED / FAILED',
                    'handback_required': False, 'rounds': len(rounds),
                    'evidence_sha256': digests}
        evidence = item.get('evidence')
        if outcome == 'FAILED' and (evidence is None or evidence == {}):
            return {'ok': False,
                    'error': (f'第 {number} 轮失败没有带新证据：迭代必须附日志 / '
                              '截图 / 元素变化 / 报文差异'),
                    'handback_required': False, 'rounds': len(rounds),
                    'evidence_sha256': digests}
        digest = _evidence_digest(evidence)
        if previous is not None and outcome == 'FAILED' and digest == previous:
            return {'ok': False,
                    'error': (f'第 {number} 轮失败证据与上一轮相同：未带新证据，'
                              '不允许重新生成'),
                    'handback_required': False, 'rounds': len(rounds),
                    'evidence_sha256': digests}
        digests.append(digest)
        previous = digest if outcome == 'FAILED' else previous
        last_outcome = outcome
        if outcome == 'PASSED':
            return {'ok': True, 'error': None, 'handback_required': False,
                    'rounds': number, 'evidence_sha256': digests}
    handback = len(rounds) >= MAX_ITERATIONS and last_outcome == 'FAILED'
    return {
        'ok': not handback,
        'error': ('3 轮迭代仍不收敛，交回诊断（保留全部失败证据，不再生成新提案）'
                  if handback else None),
        'handback_required': handback,
        'rounds': len(rounds),
        'evidence_sha256': digests,
    }


# ---------------------------------------------------------------- 代码安全

def scan_generated_code(files: Mapping[str, str]) -> List[str]:
    """扫描生成的驱动 / 适配器代码：不得联网、不得含凭证。"""
    issues: List[str] = []
    targets = [path for path in files
               if path in ('driver.py', 'adapter.py')
               or (path.endswith('.py') and path.startswith('tests/') is False)]
    for path in targets:
        content = files[path]
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError as exc:
            issues.append(f'{path} 不是合法 Python：{exc.msg}')
            continue
        for node in ast.walk(tree):
            top = None
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            else:
                continue
            for name in names:
                top = name.split('.')[0]
                if top in FORBIDDEN_IMPORTS:
                    issues.append(f'{path} 生成代码禁止联网依赖：{name}')
        for label, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(content):
                issues.append(f'{path} 生成代码包含{label}（凭证只走 key resolver）')
    return issues


# ---------------------------------------------------------------- 交付包校验

def _parse_json(files: Mapping[str, str], path: str,
                issues: List[str]) -> Optional[Any]:
    try:
        return json.loads(files[path])
    except (KeyError, ValueError) as exc:
        issues.append(f'{path} 不是合法 JSON：{exc}')
        return None


def _has_item(files: Mapping[str, str], item: str) -> bool:
    if item.endswith('/'):
        return any(path.startswith(item) for path in files)
    return item in files


def validate_package_files(files: Mapping[str, str], target_kind: str
                           ) -> List[str]:
    """校验固定交付包（10 项 / 能力画像 / manifest / 报告 / 代码安全）。"""
    issues: List[str] = []
    if target_kind not in PACKAGE_ITEMS:
        return [f'未知 target_kind：{target_kind}']
    if not isinstance(files, Mapping) or not files:
        return ['交付包为空']
    for path in files:
        if path.startswith('/') or '..' in path.split('/') or '\\' in path:
            issues.append(f'交付包路径不合法：{path}')
    missing = [item for item in PACKAGE_ITEMS[target_kind]
               if not _has_item(files, item)]
    if missing:
        issues.append(f'交付包缺少固定项：{"、".join(missing)}')

    caps = _parse_json(files, 'capabilities.json', issues)
    if caps is not None:
        error = driver_tools.validate_capabilities(caps)
        if error:
            issues.append(f'capabilities.json 不合法：{error}')

    manifest = _parse_json(files, 'manifest.json', issues)
    if manifest is not None:
        if manifest.get('target_kind') != target_kind:
            issues.append('manifest.target_kind 与提案不一致')
        artifacts = manifest.get('artifacts')
        if not isinstance(artifacts, list) or not artifacts:
            issues.append('manifest.artifacts 必须是非空数组')
        else:
            kinds = {item.get('artifact_kind') for item in artifacts
                     if isinstance(item, dict)}
            expected = {
                driver_tools.TARGET_DEVICE_DRIVER: {
                    driver_tools.TARGET_DEVICE_DRIVER},
                driver_tools.TARGET_API_ADAPTER: {
                    driver_tools.TARGET_API_ADAPTER},
                driver_tools.TARGET_PAIR: {
                    driver_tools.TARGET_DEVICE_DRIVER,
                    driver_tools.TARGET_API_ADAPTER},
            }[target_kind]
            if kinds != expected:
                issues.append(
                    f'manifest.artifacts 类型不齐：期望 {sorted(expected)}，'
                    f'实际 {sorted(k for k in kinds if k)}')
            if target_kind == driver_tools.TARGET_PAIR:
                for item in artifacts:
                    if not item.get('pair_with'):
                        issues.append('PAIR 的 manifest.artifacts 必须互相引用 '
                                      'pair_with')
                        break

    if 'ui_trace.json' in files:
        trace = _parse_json(files, 'ui_trace.json', issues)
        if trace is not None:
            error = driver_tools.validate_ui_trace(trace, required=True)
            if error:
                issues.append(f'ui_trace.json 不合法：{error}')

    smoke = _parse_json(files, 'smoke_case.json', issues)
    if smoke is not None:
        issues.extend(_validate_smoke_case(smoke, caps))

    for item in ('config.yaml', 'test_plan.md', 'onboarding_report.md'):
        if item in files:
            if not str(files[item]).strip():
                issues.append(f'{item} 不能为空')
    if 'config.yaml' in files:
        config = files['config.yaml']
        if 'target_kind:' not in config or 'capabilities.json' not in config:
            issues.append('config.yaml 必须声明 target_kind 与 capabilities 引用')
        if target_kind != driver_tools.TARGET_API_ADAPTER and 'driver:' not in config:
            issues.append('config.yaml 缺少 driver 段')
        if target_kind != driver_tools.TARGET_DEVICE_DRIVER and \
                'vendor_adapter:' not in config:
            issues.append('config.yaml 缺少 vendor_adapter 段')
    if 'onboarding_report.md' in files:
        report = files['onboarding_report.md']
        for section in REPORT_SECTIONS:
            if section not in report:
                issues.append(f'onboarding_report.md 缺少「{section}」一节')

    issues.extend(scan_generated_code(files))
    return issues


def _validate_smoke_case(smoke: Any, caps: Any) -> List[str]:
    issues: List[str] = []
    if not isinstance(smoke, dict):
        return ['smoke_case.json 必须是对象']
    case_ref = str(smoke.get('case_ref') or '').strip()
    if not case_ref:
        issues.append('smoke_case.json 缺少 case_ref')
    fields = _as_string_list(smoke.get('expected_fields'))
    if fields is None or not fields:
        issues.append('smoke_case.json.expected_fields 必须是非空字符串数组')
    else:
        unknown = _unknown(fields, driver_tools.RESULT_FIELDS)
        if unknown:
            issues.append(f'smoke_case.json.expected_fields 含未知结果字段：'
                          f'{"、".join(unknown)}')
        if 'success' not in fields:
            issues.append('smoke_case.json.expected_fields 必须包含 success')
    metrics = _as_string_list(smoke.get('metrics'))
    if not metrics:
        issues.append('smoke_case.json.metrics 不能为空：冒烟至少验证一个可计算指标')
    else:
        unknown_metrics = _unknown(metrics, driver_tools.SUPPORTED_METRICS)
        if unknown_metrics:
            issues.append(f'smoke_case.json.metrics 含未知指标：'
                          f'{"、".join(unknown_metrics)}')
        if caps is not None:
            declared = set(_as_string_list(caps.get('supported_metrics')) or [])
            if not set(metrics) & declared:
                issues.append('smoke_case.json.metrics 与 capabilities 无交集')
    if not isinstance(smoke.get('mock_results'), dict):
        issues.append('smoke_case.json.mock_results 必须是对象（staging mock 证据）')
    return issues


__all__ = [
    'CREDENTIAL_PATTERNS', 'ENTRY_APP', 'ENTRY_API', 'ENTRY_KINDS',
    'ENTRY_PAIR', 'FORBIDDEN_IMPORTS', 'GOAL_CAPTURES', 'GOAL_METRICS',
    'GOAL_TIMINGS', 'MAX_ITERATIONS', 'MEASUREMENT_PROFILE_KEYS',
    'NEEDS_RECOGNITION', 'PACKAGE_ITEMS', 'PACKAGE_ROOT', 'REPORT_SECTIONS',
    'STAGING_UNCOVERED', 'TARGET_KIND_BY_ENTRY', 'TEST_GOALS', 'TEXT_CAPTURES',
    'computable_metrics', 'evaluate_iterations', 'metric_fields_available',
    'package_ref', 'package_sha256', 'package_slug', 'resolve_measurement_plan',
    'scan_generated_code', 'validate_package_files',
]
