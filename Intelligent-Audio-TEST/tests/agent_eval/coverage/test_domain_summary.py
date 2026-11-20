# -*- coding: utf-8 -*-
"""INT-2465 汇总跑：M1 各域各 10 条任务的数据集仍在位、可解析。

各域卡已完成自己的域评测（``tests/agent_eval/domains/*``）；本卡做汇总核对：
7 个域每个至少 10 条任务、期望工具在注册表内、任务 ID / 名称不重复。
实际执行由同一次 pytest 运行中各域测试模块完成（见交付评论命令）。
"""
import glob
import io
import json
import os

import pytest

from shared.agent_tools import device_tools, intent_tools, mcp_registry
from shared.agent_tools import testcase_tools

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DOMAINS_DIR = os.path.join(PROJECT_ROOT, 'tests', 'agent_eval', 'domains')

MIN_TASKS_PER_DOMAIN = 10


def _load_json(domain):
    path = os.path.join(DOMAINS_DIR, domain, 'golden_tasks.json')
    with io.open(path, encoding='utf-8') as handle:
        return json.load(handle)


def _all_tool_names(items):
    names = []
    for item in items:
        for key in ('expected_tool', 'tool'):
            if item.get(key):
                names.append(item[key])
        names.extend(item.get('must_not_call') or [])
    return names


def _dataset_cases():
    """返回 {domain: [case...]}，把异构数据集归一成 case 列表。"""
    cases = {}
    for domain in ('algorithm', 'audio', 'task', 'testcase'):
        doc = _load_json(domain)
        if domain == 'testcase':
            items = list(doc.get('testcase_tasks') or []) + \
                list(doc.get('tag_tasks') or [])
        else:
            items = list(doc.get('tasks') or []) + list(doc.get('cases') or [])
        cases[domain] = items
    from tests.agent_eval.domains.device import fixtures as device_fixtures
    from tests.agent_eval.domains.evaluation import fixtures as eval_fixtures
    from tests.agent_eval.domains.report import fixtures as report_fixtures
    cases['device'] = list(device_fixtures.DOMAIN_TASKS)
    cases['evaluation'] = list(eval_fixtures.DOMAIN_TASKS)
    cases['report'] = list(report_fixtures.DOMAIN_TASKS)
    return cases


def test_every_domain_has_at_least_ten_tasks():
    cases = _dataset_cases()
    assert set(cases) == {
        'algorithm', 'audio', 'device', 'evaluation', 'report', 'task',
        'testcase'}
    for domain, items in cases.items():
        assert len(items) >= MIN_TASKS_PER_DOMAIN, (
            f'{domain} 只有 {len(items)} 条任务（要求 ≥ {MIN_TASKS_PER_DOMAIN}）')


def test_domain_task_ids_are_unique():
    cases = _dataset_cases()
    for domain, items in cases.items():
        ids = [item.get('id') or item.get('name') for item in items]
        assert all(ids), f'{domain} 存在无 ID 任务'
        assert len(ids) == len(set(ids)), f'{domain} 任务 ID 重复'


def _agent_only_tool_names():
    """Agent 专用只读 REST 目标（不写进对外 MCP 清单，见 device/testcase_tools）。"""
    names = {tool['name'] for tool in testcase_tools.TESTCASE_READ_TOOLS}
    names |= {tool['name'] for tool in device_tools.DEVICE_SPL_TARGETS.values()}
    return names


def test_domain_expected_tools_are_registered():
    cases = _dataset_cases()
    agent_only = _agent_only_tool_names()
    unknown = []
    for domain, items in cases.items():
        for name in _all_tool_names(items):
            if name in intent_tools.INTENT_TOOL_BY_NAME:
                continue
            if mcp_registry.get_tool(name) is not None:
                continue
            if name in agent_only:
                continue
            unknown.append((domain, name))
    assert not unknown, f'域任务引用未注册工具：{unknown}'


def test_domain_read_tools_are_enabled():
    cases = _dataset_cases()
    for domain, items in cases.items():
        for item in items:
            name = item.get('tool') or item.get('expected_tool')
            tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
            if tool is None:
                continue
            assert tool.enabled is True, (
                f'{domain} 任务引用了未启用的意图工具 {name}')
            assert tool.risk == 'READ', f'{domain} 任务引用了非只读工具 {name}'


def test_domain_datasets_still_exist_on_disk():
    json_domains = {os.path.basename(os.path.dirname(path))
                    for path in glob.glob(os.path.join(
                        DOMAINS_DIR, '*', 'golden_tasks.json'))}
    assert {'algorithm', 'audio', 'task', 'testcase'} <= json_domains


@pytest.mark.parametrize('domain,minimum', [
    ('algorithm', 10), ('audio', 10), ('device', 10), ('evaluation', 10),
    ('report', 10), ('task', 10), ('testcase', 20),
])
def test_domain_task_counts(domain, minimum):
    assert len(_dataset_cases()[domain]) >= minimum
