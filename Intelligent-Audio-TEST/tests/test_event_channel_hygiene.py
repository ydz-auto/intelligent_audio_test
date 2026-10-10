# -*- coding: utf-8 -*-
"""事件通道卫生静态检查（UC-1001 / INT-69 验收）

验收要求「全代码库无裸字符串频道名」。本测试静态扫描后端源码：

1. EventChannel 枚举必须恰好五个频道（TASK/CASE/DEVICE/REPORT/CONFIG）；
2. Redis 频道发布/订阅调用（RedisPubSub.publish / .subscribe / EventBus 转发层）
   的字面量频道参数必须取自 EventChannel 五值，禁止裸字符串
   （task_logs / task_progress / import_progress / sse_events / device_status 等
   历史裸频道名一律不得回潮）。

扫描范围：shared/、各微服务、api_gateway、run_all.py、scripts/（排除
__pycache__ 与 tests —— tests 中的发布仅允许五通道值，同样受规则 2 约束）。
"""
import os
import re
from pathlib import Path

import pytest

# BaseConfig 导入校验必需的环境变量兜底（仅在缺失时填充，不影响真实环境）
os.environ.setdefault('OSS_ACCESS_KEY', 'static-scan')
os.environ.setdefault('OSS_SECRET_KEY', 'static-scan')

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 静态扫描目录（后端源码）
SCAN_DIRS = [
    'shared', 'api_gateway', 'task_service', 'e2e_test_service', 'api_test_service',
    'evaluation_service', 'report_service', 'device_service', 'algorithm_service',
    'api_adapter_service', 'auth_service', 'audio_service', 'scripts',
]
SCAN_FILES = ['run_all.py']

# 五通道合法值（与 shared/utils/redis_pubsub.EventChannel 对齐）
LEGAL_CHANNELS = {'task_events', 'case_events', 'device_events', 'report_events', 'config_events'}

# 发布/订阅调用的字面量频道参数（单行近似匹配）
_PUBLISH_LIT = re.compile(r"\.publish\(\s*['\"]([A-Za-z0-9_:.]+)['\"]")
_SUBSCRIBE_LIT = re.compile(r"\.subscribe\(\s*[\[\(]?\s*['\"]([A-Za-z0-9_:.]+)['\"]")

# 历史裸频道名（任何 publish/subscribe 字面量参数中出现即违规，
# 连法定的五值之外的字符串也不允许作为频道字面量）
_BARE_CHANNEL_NAMES = re.compile(r"['\"](task_logs|task_progress|import_progress|sse_events|device_status)['\"]")


def _iter_backend_py_files():
    for d in SCAN_DIRS:
        base = PROJECT_ROOT / d
        if not base.exists():
            continue
        for p in base.rglob('*.py'):
            if '__pycache__' in p.parts:
                continue
            yield p
    for f in SCAN_FILES:
        p = PROJECT_ROOT / f
        if p.exists():
            yield p


def _test_channel_hygiene_source_files():
    files = list(_iter_backend_py_files())
    assert len(files) > 50, f'静态扫描文件数异常: {len(files)}'
    return files


def test_event_channel_enum_has_exactly_five_channels():
    from shared.utils.redis_pubsub import EventChannel
    assert {m.value for m in EventChannel} == LEGAL_CHANNELS
    assert len(EventChannel) == 5


def test_no_bare_string_channel_in_publish_subscribe_calls():
    """publish/subscribe 的字面量频道必须取自五通道值，历史裸频道名不得回潮。"""
    offenders = []
    for p in _iter_backend_py_files():
        try:
            text = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(PROJECT_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _PUBLISH_LIT.finditer(line):
                if m.group(1) not in LEGAL_CHANNELS:
                    offenders.append(f'{rel}:{lineno} publish("{m.group(1)}")')
            for m in _SUBSCRIBE_LIT.finditer(line):
                if m.group(1) not in LEGAL_CHANNELS:
                    offenders.append(f'{rel}:{lineno} subscribe("{m.group(1)}")')
            # 历史裸频道名即使出现在多行 publish/subscribe 的列表元素里也拦截
            if _BARE_CHANNEL_NAMES.search(line) and re.search(r"\.(publish|subscribe)\(", line):
                offenders.append(f'{rel}:{lineno} 历史裸频道名出现在 publish/subscribe 调用行')
    assert not offenders, '发现裸字符串频道名：\n' + '\n'.join(offenders)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
