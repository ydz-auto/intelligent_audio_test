# -*- coding: utf-8 -*-
"""INT-2560 注册期风险等级一致性：``IntentTool.risk`` 必填，写映射必须声明写。

INT-2559 P1-1 的 fail-open：``IntentTool.risk`` 曾默认 ``'READ'``，漏写 risk
的新写工具在注册期就被当成只读 —— ``run_orchestrator`` 不进提案、
``tool_gateway`` 按只读放行、网关按 POST 直发，整条「提案 → 审批 → 幂等执行」
被绕开且无测试拦截。本文件按四层把它钉死：

1. 构造期：``risk`` 无默认值（漏写 TypeError）、非法取值 ValueError；
2. 注册期正方向：任何映射到非 GET REST 动作的意图工具必须是 WRITE /
   DESTRUCTIVE。四个 POST 只承载查询体的只读端点
   （``READ_ONLY_NON_GET_TOOLS``）显式白名单放行，且白名单本身受紧校验；
   探针覆盖完整性另有断言，避免新 REST 工具躲开检查。探针行统一取自
   ``intent_tools.rest_action_targets()``（INT-2562：共读 ``_REST_ACTION_MAP``
   与 ``DOMAIN_ACTION_MAPS``，写域 / Agent 专用目标不再需要手改本文件）；
3. 注册期反方向：WRITE / DESTRUCTIVE 工具必须真的映射到写动作、有本地写
   实现或尚未启用（防止只读工具被误标成写，把 classification 变成噪声）；
4. 同源：``SharedToolRegistryBridge`` 的 ``ToolDescriptor.risk`` 逐项等于
   注册表声明，转换处不再有自己的默认值。

另含 INT-2559 P2-4：``AUDIT_REDACTED_ARGUMENTS`` 的工具只登记自带提案原语
的（``proposal_capable``），不得进通用审批链。

不做的事：不动 ``test_registry_consistency.py`` 的
``test_skills_allowed_tools_stay_inside_the_31_names``（该断言的口径调整归
第一张域写卡统一处理，见 INT-2560「不做」）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ToolRisk
from agent_service.infrastructure.tools.registry_bridge import (
    RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import intent_tools, mcp_registry


# ---------------------------------------------------------------- 探针

def _rest_action_targets():
    """所有映射到 REST 的意图动作：(意图工具名, 动作, REST 目标定义)。

    行集合由 ``intent_tools.rest_action_targets()`` 给出（INT-2562）：注册表
    内的 ``_REST_ACTION_MAP``（只读业务域）与 ``DOMAIN_ACTION_MAPS``（写域与
    Agent 专用目标 —— 设备 / SPL、评估写）一起枚举。探针不再手工列模块：
    漏登记一个域会被 ``test_risk_probe_covers_every_rest_mapping`` 抓到。
    """
    return intent_tools.rest_action_targets()


def _write_targets():
    """映射到「写动作」的 REST 目标：非 GET 且不在只读白名单里。"""
    rows = []
    for name, action, target in _rest_action_targets():
        method = target['method'].upper()
        if method == 'GET':
            continue
        if target['name'] in intent_tools.READ_ONLY_NON_GET_TOOLS:
            continue
        rows.append((name, action, target))
    return rows


class _NoRest:
    """本文件只做注册期检查，不回源；误发请求时立刻失败。"""

    def call(self, *args, **kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError('注册期一致性测试不发起 REST 调用')


# ---------------------------------------------------------------- 构造期

def test_intent_tool_risk_is_required():
    """漏写 risk 的构造在构造期即 TypeError（不再落成 READ）。"""
    with pytest.raises(TypeError):
        intent_tools.IntentTool(  # type: ignore[call-arg]
            name='risk_missing', description='漏写风险等级',
            parameters={'type': 'object', 'properties': {}})


@pytest.mark.parametrize('risk', ['read', 'write', '', 'ADMIN', None])
def test_intent_tool_risk_rejects_values_outside_the_enum(risk):
    """取值必须与 ToolRisk 同口径；大小写写错不能静默变成「非 READ」或 READ。"""
    with pytest.raises(ValueError):
        intent_tools.IntentTool(
            name='risk_bad', description='非法风险等级',
            parameters={'type': 'object', 'properties': {}}, risk=risk)


def test_declared_risk_levels_match_the_tool_risk_enum():
    assert set(intent_tools.RISK_LEVELS) == {level.value for level in ToolRisk}
    assert intent_tools.WRITE_RISK_LEVELS == {
        level.value for level in ToolRisk if level.requires_approval}


# ---------------------------------------------------------------- 注册期·正方向

def test_every_rest_action_resolves_to_a_registered_target():
    rows = _rest_action_targets()
    assert rows
    for name, action, target in rows:
        assert target is not None, f'{name}.{action} 的 REST 映射失效'
        assert target.get('method'), f'{name}.{action} 的目标缺少 method'


def test_risk_probe_covers_every_rest_mapping():
    """探针要覆盖所有 REST 映射与 ``kind='intent_rest'`` 工具。

    漏一个映射，就等于给新写工具留了一条躲开风险断言的旁路。
    """
    covered = {name for name, _, _ in _rest_action_targets()}
    declared = set(intent_tools._REST_ACTION_MAP) | {
        tool.name for tool in intent_tools.INTENT_TOOLS
        if tool.kind == 'intent_rest'}
    assert declared <= covered, f'探针未覆盖：{declared - covered}'


def test_read_only_non_get_allowlist_is_tight():
    """只读白名单只能放真的「非 GET」目标，且每项写明为什么只读。

    白名单本身是 fail-open 的口子：宽松登记等于把写端点标成只读。
    """
    assert intent_tools.READ_ONLY_NON_GET_TOOLS, '只读白名单不应为空'
    for name, reason in intent_tools.READ_ONLY_NON_GET_TOOLS.items():
        target = intent_tools._lookup_rest_tool(name)
        assert target is not None, f'白名单登记了不存在的 REST 目标：{name}'
        assert target['method'].upper() != 'GET', (
            f'{name} 是 GET，不需要进只读白名单')
        assert reason.strip(), f'{name} 缺少只读理由'


def _risk_violations(rows):
    """正方向断言本体：(工具名, 声明 risk, 动作, REST 目标) → 违规描述。

    写动作 = 非 GET 且不在 ``READ_ONLY_NON_GET_TOOLS``（POST 只承载查询体）。
    拆成纯函数，便于用合成行证明「写映射被标成 READ」一定会被抓到。
    """
    offenders = []
    for name, risk, action, target in rows:
        if target['method'].upper() == 'GET':
            continue
        if target['name'] in intent_tools.READ_ONLY_NON_GET_TOOLS:
            continue
        if risk not in intent_tools.WRITE_RISK_LEVELS:
            offenders.append(
                f'{name}.{action} -> {target["method"]} {target["name"]}'
                f'（risk={risk}）')
    return offenders


def _registry_risk_rows():
    return [(name, intent_tools.INTENT_TOOL_BY_NAME[name].risk, action, target)
            for name, action, target in _rest_action_targets()]


def test_rest_non_get_action_requires_write_risk():
    """正方向：映射到写动作的意图工具必须是 WRITE / DESTRUCTIVE。

    反例见 ``test_risk_guard_catches_write_mapping_declared_read``：把任一写
    映射改回 READ 即红；登记在只读白名单里的 POST 查询体端点不受影响。
    """
    offenders = _risk_violations(_registry_risk_rows())
    assert not offenders, (
        '以下意图工具映射到写动作却未声明 WRITE / DESTRUCTIVE：'
        + '；'.join(offenders))


def test_risk_guard_catches_write_mapping_declared_read():
    """护栏自证：写映射（非 GET、非只读白名单）声明成 READ 必须报违规。

    这条用例就是 INT-2560 的验收反例：没有它，正方向断言可能因为注册表里
    此刻恰好没有写映射而空转。
    """
    write_target = {'name': 'task_create', 'method': 'POST'}
    read_only_target = {'name': 'report_cases_search', 'method': 'POST'}

    offenders = _risk_violations([
        # 写映射 + READ：正是 INT-2559 P1-1 的 fail-open 形态
        ('task_query', 'READ', 'create', write_target),
        # 写映射 + WRITE：合法
        ('task_query', 'WRITE', 'create', write_target),
        # POST 只读（白名单）+ READ：合法
        ('report_query', 'READ', 'cases_search', read_only_target),
    ])
    assert len(offenders) == 1, offenders
    assert 'task_query.create' in offenders[0]
    assert 'POST task_create' in offenders[0]


def test_risk_guard_catches_every_registered_rest_writer_declared_read():
    """护栏自证（INT-2562）：每个有写动作的意图工具改成 READ 都必须被抓。

    这是上一条的实测版：行取自注册表（``rest_action_targets``），不靠人工
    构造。INT-2469 的 ``evaluation_manage`` 合入后漏进探针，就是这条在
    评估域没有落地 —— 只要域动作表登记进 ``DOMAIN_ACTION_MAPS``，它的写
    动作（POST / PUT / PATCH / DELETE）就会出现在这里；把 ``risk`` 退回
    ``READ`` 会被 ``_risk_violations`` 判红，不再有 fail-open 旁路。
    """
    write_rows = _write_targets()
    expected = {name for name, _action, _target in write_rows}
    if not expected:  # pragma: no cover - 当前树必含写域（evaluation_manage）
        pytest.skip('当前树没有任何映射到写动作的已启用意图工具')
    offenders = _risk_violations(
        [(name, 'READ', action, target) for name, action, target in write_rows])
    flagged = {line.split('.', 1)[0] for line in offenders}
    assert flagged == expected, (
        f'以下意图工具的写动作被标成 READ 却没被抓到：{expected - flagged}')


# ---------------------------------------------------------------- 注册期·反方向

def test_write_risk_tools_have_a_real_write_path():
    """反方向：声明 WRITE / DESTRUCTIVE 的工具不能只是「标着写」。

    合法情形只有三种：映射到写动作（非 GET 且不在只读白名单）、有本地写
    实现（``kind='local'``，如 ``memory_write`` 自带提案原语）、或尚未启用的
    M2 预留工具（不可执行，risk 是前瞻声明）。只读工具误标成写会在这里暴露。
    """
    rest_writers = {name for name, _action, _target in _write_targets()}

    offenders = []
    for tool in intent_tools.INTENT_TOOLS:
        if tool.risk not in intent_tools.WRITE_RISK_LEVELS:
            continue
        if tool.name in rest_writers:
            continue            # 有写 REST 动作
        if tool.kind == 'local':
            continue            # 本地写实现（不经 REST）
        if not tool.enabled:
            continue            # 预留写工具：不可执行
        offenders.append(
            f'{tool.name} 声明 {tool.risk} 且已启用，但既无写 REST 动作'
            f'也无本地写实现')
    assert not offenders, '；'.join(offenders)


# ---------------------------------------------------------------- 同源

def test_tool_descriptor_risk_mirrors_intent_declaration():
    """bridge 转换处不引入自己的默认值：描述符风险逐项等于注册表声明。"""
    bridge = SharedToolRegistryBridge()
    descriptors = {item.name: item for item in bridge.descriptors()}
    assert set(descriptors) == {tool.name for tool in intent_tools.INTENT_TOOLS}
    for tool in intent_tools.INTENT_TOOLS:
        expected = ToolRisk(tool.risk)
        assert descriptors[tool.name].risk is expected, tool.name
        described = bridge.describe(tool.name)
        assert described is not None, tool.name
        assert described.risk is expected, tool.name
        assert described.risk.requires_approval is tool.requires_approval


def test_risk_of_matches_the_declaration():
    """网关实际使用的 ``risk_of`` 与声明同源（含 MCP 工具的 GET 推导）。"""
    for tool in intent_tools.INTENT_TOOLS:
        assert intent_tools.risk_of(tool.name) == tool.risk, tool.name
    for entry in mcp_registry.TOOLS:
        name = entry['name']
        if name in intent_tools.INTENT_TOOL_BY_NAME:
            # 同名意图工具优先（report_compare / report_export）：risk_of
            # 返回意图声明，已在上面的循环里断言过。
            continue
        if name in intent_tools.AGENT_UNEXPOSED_MCP_TOOLS:
            # 宿主语境专用工具不在 Agent 通道，risk_of 返回 None（fail-closed）
            assert intent_tools.risk_of(name) is None, name
            continue
        expected = 'READ' if entry['method'] == 'GET' else 'WRITE'
        assert intent_tools.risk_of(name) == expected, name


# ---------------------------------------------------------------- P2-4

def test_audit_redacted_tools_stay_out_of_the_generic_approval_chain():
    """``AUDIT_REDACTED_ARGUMENTS`` 的工具自带提案原语，不进通用审批链。

    通用链拿 ``record.arguments``（已 ``redact_for_audit``）做审批后执行与
    崩溃重提案，登记进来的工具必须被 ``proposal_capable`` 排除；否则审批
    通过的「原文」会变成 ``{redacted, sha256, length}``。
    """
    # memory=object() 是哨兵：只让 proposal_capable 走「记忆服务已装配」分支，
    # 本用例不执行任何工具、不触碰记忆实现。
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=_NoRest(),
        credentials=RunCredentialRegistry(), memory=object())

    assert intent_tools.AUDIT_REDACTED_ARGUMENTS, '脱敏表不应为空'
    for name in intent_tools.AUDIT_REDACTED_ARGUMENTS:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
        assert tool is not None, f'脱敏表登记了未知工具：{name}'
        assert tool.risk in intent_tools.WRITE_RISK_LEVELS, (
            f'{name} 的参数被脱敏却不是写操作')
        assert gateway.proposal_capable(name), (
            f'{name} 的参数已脱敏，不能走通用审批链（执行 / 崩溃重提案会用'
            f' record.arguments 的脱敏占位值）')
