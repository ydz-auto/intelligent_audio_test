# -*- coding: utf-8 -*-
"""MCP 长尾工具 → 意图工具归属矩阵（INT-2465，方案 §6.1 / §6.2）。

单一事实源：本模块把 ``mcp_registry.TOOLS`` 的 207 个外部 MCP 工具逐项归到
31 个意图工具之一，或明确标为「仅外部 MCP（不内部暴露）」。``COVERAGE.md``
由本模块渲染，测试比对文件与代码是否一致，避免表格与注册表漂移。

口径说明：

- 依据 ``doc/agent化/07_单Agent_Skills落地方案.md`` §6.1 的 31 个意图工具
  （含 ``tool_search``；业务意图工具 25 个）。
- 外部 MCP 计数 = INT-2453 迁移谱 205 个 + INT-2461 首页只读 2 个 = 207 个。
  ``tool_search`` 索引视图是 205 个 MCP 条目：``audio_get_by_ids`` 属宿主
  语境不可暴露（INT-2530），``report_compare`` 由同名的只读意图工具顶替。
- 归属只回答「该 MCP 能力由哪个意图工具负责」。M1 阶段写 / 破坏性 MCP 工具
  即使可被 ``tool_search`` 检索，执行时仍被网关只读门禁拒绝（APPROVAL_REQUIRED）；
  M2 写工具启用时按本矩阵扩到对应意图工具的动作里。
- 「仅外部 MCP」= §6.1 没有对应意图工具、内部 Agent 不以意图动作暴露，只作为
  原始 MCP 工具存在（Agent 仍可用 ``tool_search`` 检索到，但 M1 执行受只读门禁
  约束）。新增归属必须改本模块并重新生成 ``COVERAGE.md``，不允许表格手写。
"""
from __future__ import annotations

import argparse
import io
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shared.agent_tools import intent_tools, mcp_registry

# 结论枚举（COVERAGE.md 与测试共用，禁止散落字面量）
OWNED = '内部归属'
EXTERNAL = '仅外部 MCP'

# 意图工具负责的 MCP 能力（名称 → 归属与理由）。只登记「按前缀 / HTTP 方法
# 推不出来」的工具；其余走下面的确定性规则。
OVERRIDES: Dict[str, Tuple[str, str]] = {
    # 报告：POST 但语义只读（权限码只有 :read）→ 归只读取数工具
    'report_statistics_report': ('report_query', 'POST 但只聚合返回统计、权限仅 report:read'),
    'report_case_averages': ('report_query', 'POST 但按过滤条件取用例平均值、权限仅 report:read'),
    'report_cases_search': ('report_query', 'POST 但只搜索报告内用例、权限仅 report:read'),
    'report_studio_get_document': ('report_query', '读取 Studio 文档，只读'),
    # 报告：对比 / 导出 / 写
    'report_compare': ('report_compare', '报告对比（意图工具本地组合，不落库）'),
    'report_secondary_compare': ('report_compare', '二次对比只读取数'),
    'report_export': ('report_export', '导出 PDF / PPTX / HTML / MD'),
    'report_export_get': ('report_export', '导出（GET 形态）'),
    'report_studio_export_document': ('report_export', 'Studio 导出作业'),
    'report_generate_task': ('report_generate', '按任务生成报告'),
    'report_regenerate': ('report_generate', '重新生成报告'),
    'report_studio_create_document': ('report_generate', '创建 Studio 文档草稿'),
    'report_studio_update_document': ('report_generate', '编辑 Studio 文档（M2）'),
    # 收藏是写动作（POST），按写域归属，不按权限码里的 :read
    'task_favorite': ('task_run', '收藏是写动作（M1 只读门禁拦截）'),
    'testcase_favorite': ('testcase_write', '收藏是写动作（M1 只读门禁拦截）'),
    'report_favorite': ('report_generate', '收藏是写动作（M1 只读门禁拦截）'),
    # 用例导入导出：导出作业属只读子集，导入是写
    'testcase_export': ('testcase_query', '导出作业状态在用例只读子集内（M1 拦截 POST）'),
    'testcase_import': ('testcase_write', '导入用例数据（M2）'),
    # 音频：转码 / 删除归音频写工具
    'audio_convert': ('audio_annotate', '音频转码属音频处理写动作'),
    'audio_delete': ('audio_annotate', '删除音频属音频记录写动作'),
}

# 仅外部 MCP：§6.1 没有对应意图工具，或按安全裁定不内部暴露。
EXTERNAL_ONLY: Dict[str, str] = {
    'audio_get_by_ids': '宿主语境批量读通道（不做归属校验），Agent 侧不暴露（INT-2530）',
    'favorites_list': '跨域个人收藏 ID 列表，§6.1 无对应意图工具',
    'benchmark_ranking': 'Benchmark 域不在 §6.1 工具表内',
    'benchmark_ranking_compute': 'Benchmark 域不在 §6.1 工具表内',
    'benchmark_baselines': 'Benchmark 域不在 §6.1 工具表内',
    'benchmark_reports': 'Benchmark 域不在 §6.1 工具表内',
    'data_transfer_export': '任务数据 ZIP 离线搬运，§6.1 无对应意图工具',
    'data_transfer_import_preview': '任务数据 ZIP 离线搬运，§6.1 无对应意图工具',
    'data_transfer_import': '任务数据 ZIP 离线搬运，§6.1 无对应意图工具',
}

# 前缀 → (只读归属, 方法非 GET 时的写归属)；None 表示该方向没有意图工具。
_PREFIX_OWNERS: List[Tuple[str, Optional[str], Optional[str]]] = [
    ('published_task', 'task_query', 'task_run'),
    ('task', 'task_query', 'task_run'),
    ('testcase', 'testcase_query', 'testcase_write'),
    ('audio', 'audio_query', 'audio_annotate'),
    ('device', 'device_query', 'device_control'),
    ('evaluation', 'evaluation_query', 'evaluation_manage'),
    ('algorithm', 'algorithm_query', 'algorithm_manage'),
    ('report', 'report_query', 'report_generate'),
    ('tag', 'tag_group_manage', 'tag_group_manage'),
    ('group', 'tag_group_manage', 'tag_group_manage'),
    ('log', 'log_diagnose', 'log_diagnose'),
    ('home', 'dashboard_query', 'dashboard_query'),
]

# 音频写动作细分：上传 / 导入链路归 audio_import，其它写动作归 audio_annotate。
_AUDIO_IMPORT_PREFIXES = (
    'audio_url_import', 'audio_upload_', 'audio_import',
)
# 非 GET 且权限只有读码时按只读归属处理（POST 取数型接口）。
_READ_PERMISSION_SUFFIXES = (':read', ':compare', ':ranking:read',
                             ':baseline:read', ':report:read')


@dataclass(frozen=True)
class CoverageRow:
    name: str
    method: str
    permissions: Tuple[str, ...]
    risk: str
    intent: Optional[str]
    category: str
    reason: str
    indexed: str  # 'mcp' / 'intent' / 'excluded'

    def to_dict(self) -> dict:
        return {
            'name': self.name, 'method': self.method,
            'permissions': list(self.permissions), 'risk': self.risk,
            'intent': self.intent, 'category': self.category,
            'reason': self.reason, 'indexed': self.indexed,
        }


def _prefix_of(name: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """最长前缀匹配，避免 ``task_`` 抢走 ``published_task_*``。"""
    matched: Optional[Tuple[str, Optional[str], Optional[str]]] = None
    for rule in _PREFIX_OWNERS:
        prefix = rule[0]
        if name == prefix or name.startswith(prefix + '_'):
            if matched is None or len(prefix) > len(matched[0]):
                matched = rule
    return matched


def _is_read_permission(permissions) -> bool:
    return bool(permissions) and all(
        str(p).endswith(_READ_PERMISSION_SUFFIXES) for p in permissions)


def is_read_only(tool: dict) -> bool:
    """工具是否只读：仅 ``GET``（与 ``mcp_registry.risk_of`` 同一口径）。

    刻意**不**按权限码推断：``task_favorite`` / ``report_favorite`` 等写动作
    声明的是 ``:read`` 权限（收藏列表需要读权限），按权限码判会把它们误标为
    只读。能力清单的「只读」只认 HTTP 方法，宁可保守。
    """
    return tool.get('method') == 'GET'


def domain_of(name: str) -> str:
    """工具名 → 域前缀（能力清单按域分组；与 ``_PREFIX_OWNERS`` 同源）。"""
    rule = _prefix_of(name)
    if rule is not None:
        return rule[0]
    return str(name).split('_')[0] or 'other'


def _read_owner(name: str, prefix_rule) -> Optional[str]:
    if name.startswith('audio_'):
        return 'audio_query'
    if prefix_rule is None:
        return None
    return prefix_rule[1]


def _write_owner(name: str, prefix_rule) -> Optional[str]:
    if name.startswith('audio_'):
        if name.startswith(_AUDIO_IMPORT_PREFIXES):
            return 'audio_import'
        return 'audio_annotate'
    if prefix_rule is None:
        return None
    return prefix_rule[2]


def _indexed(name: str) -> str:
    entry = intent_tools.TOOL_INDEX_BY_NAME.get(name)
    if entry is None:
        return 'excluded'
    return 'mcp' if entry.get('kind') == 'mcp' else 'intent'


def attribute(tool: dict) -> Tuple[Optional[str], str, str]:
    """返回 (意图工具名或 None, 结论, 理由)。"""
    name = tool['name']
    if name in EXTERNAL_ONLY:
        return None, EXTERNAL, EXTERNAL_ONLY[name]
    if name in OVERRIDES:
        intent, reason = OVERRIDES[name]
        return intent, OWNED, reason
    rule = _prefix_of(name)
    is_read = tool['method'] == 'GET' or _is_read_permission(tool['permissions'])
    intent = _read_owner(name, rule) if is_read else _write_owner(name, rule)
    if intent:
        via = 'GET' if tool['method'] == 'GET' else (
            '只读权限码' if is_read else '写动作')
        reason = f'{name.split("_")[0]} 域{via}，归 {intent}'
        return intent, OWNED, reason
    return None, EXTERNAL, '§6.1 无对应意图工具'


def coverage_rows() -> List[CoverageRow]:
    rows: List[CoverageRow] = []
    for tool in mcp_registry.TOOLS:
        intent, category, reason = attribute(tool)
        if category == OWNED and intent not in intent_tools.INTENT_TOOL_BY_NAME:
            raise ValueError(
                f'{tool["name"]} 归属到未注册的意图工具 {intent}')
        rows.append(CoverageRow(
            name=tool['name'], method=tool['method'],
            permissions=tuple(tool['permissions']),
            risk='READ' if tool['method'] == 'GET' else 'WRITE',
            intent=intent, category=category, reason=reason,
            indexed=_indexed(tool['name'])))
    names = [row.name for row in rows]
    if len(names) != len(set(names)):
        raise ValueError('MCP 注册表存在重复工具名')
    return rows


def summary() -> dict:
    rows = coverage_rows()
    owned = [r for r in rows if r.category == OWNED]
    external = [r for r in rows if r.category == EXTERNAL]
    by_intent: Dict[str, int] = {}
    for row in owned:
        by_intent[row.intent] = by_intent.get(row.intent, 0) + 1
    return {
        'mcp_total': len(rows),
        'owned': len(owned),
        'external': len(external),
        'by_intent': dict(sorted(by_intent.items())),
        'external_names': [r.name for r in external],
        'intent_total': len(intent_tools.INTENT_TOOLS),
        'intent_none': sorted(
            t.name for t in intent_tools.INTENT_TOOLS
            if t.name not in by_intent),
    }


def _cell(text) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def render_markdown() -> str:
    rows = coverage_rows()
    stats = summary()
    lines = [
        '# MCP 工具 → 意图工具归属矩阵（INT-2465）',
        '',
        f'> 本文件由 `shared/agent_tools/coverage.py` 生成，禁止手改。'
        f'重新生成：`python -m shared.agent_tools.coverage --write`。',
        '',
        '## 口径',
        '',
        f'- 外部 MCP 工具 **{stats["mcp_total"]}** 个'
        f'（INT-2453 迁移谱 205 + INT-2461 首页只读 2）。',
        f'- 意图工具 **{stats["intent_total"]}** 个'
        '（方案 §6.1；含 `tool_search`，业务意图工具 25 个）。',
        f'- 内部归属 **{stats["owned"]}** 个，仅外部 MCP **{stats["external"]}** 个。',
        '- 结论枚举：`内部归属（<意图工具>）` / `仅外部 MCP（不内部暴露）`。',
        '- M1 阶段写 / 破坏性 MCP 工具即使可检索，执行仍被只读门禁拒绝'
        '（`APPROVAL_REQUIRED`）；M2 按本矩阵落到意图工具动作。',
        '',
        '## 汇总',
        '',
        '| 指标 | 数值 |',
        '|---|---|',
        f'| MCP 工具总数 | {stats["mcp_total"]} |',
        f'| 内部归属 | {stats["owned"]} |',
        f'| 仅外部 MCP | {stats["external"]} |',
        f'| 归属到意图工具 | {len(stats["by_intent"])} 个 |',
        '',
        '### 无 MCP 归属的意图工具',
        '',
        '以下意图工具是本地能力（平台口径 / 检索 / 本地聚合 / 预留 Schema），'
        '不直接绑定 MCP 工具：',
        '',
        ', '.join(f'`{name}`' for name in stats['intent_none']) or '（无）',
        '',
        '## 仅外部 MCP（不内部暴露）',
        '',
        '| MCP 工具 | 理由 |',
        '|---|---|',
    ]
    for row in rows:
        if row.category == EXTERNAL:
            lines.append(f'| `{_cell(row.name)}` | {_cell(row.reason)} |')
    lines += [
        '',
        '## 逐项归属',
        '',
        '`索引` 列：`mcp` = 以 MCP 条目进入 `tool_search` 索引；'
        '`intent` = 同名意图工具顶替；`excluded` = 不进入索引。',
        '',
        '| MCP 工具 | 方法 | 权限 | 风险 | 归属结论 | 索引 | 理由 |',
        '|---|---|---|---|---|---|---|',
    ]
    for row in rows:
        conclusion = (f'内部归属（`{row.intent}`）'
                      if row.category == OWNED else '仅外部 MCP（不内部暴露）')
        lines.append(
            f'| `{_cell(row.name)}` | {row.method} | '
            f'{_cell(",".join(row.permissions) or "-")} | {row.risk} | '
            f'{conclusion} | {row.indexed} | {_cell(row.reason)} |')
    lines.append('')
    return '\n'.join(lines)


def intent_of(name: str) -> Tuple[Optional[str], str]:
    """单个工具名的归属：意图工具自身 → 自身；MCP 工具 → 矩阵结论。"""
    if name in intent_tools.INTENT_TOOL_BY_NAME:
        return name, OWNED
    tool = mcp_registry.get_tool(name)
    if tool is None:
        return None, '未注册'
    return attribute(tool)[:2]


def coverage_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'COVERAGE.md')


def write_markdown(path: Optional[str] = None) -> str:
    target = path or coverage_path()
    with io.open(target, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(render_markdown())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description='生成 MCP → 意图工具归属矩阵')
    parser.add_argument('--write', action='store_true',
                        help='写入 shared/agent_tools/COVERAGE.md')
    parser.add_argument('--check', action='store_true',
                        help='只校验文件与代码一致')
    args = parser.parse_args()
    rendered = render_markdown()
    if args.write:
        print(write_markdown())
        return 0
    if args.check:
        with io.open(coverage_path(), encoding='utf-8') as handle:
            current = handle.read()
        if current != rendered:
            print('COVERAGE.md 与 coverage.py 不一致，请重新生成')
            return 1
        print('COVERAGE.md 与 coverage.py 一致')
        return 0
    print(rendered)
    return 0


if __name__ == '__main__':  # pragma: no cover - 生成入口
    raise SystemExit(main())


__all__ = [
    'EXTERNAL', 'EXTERNAL_ONLY', 'OVERRIDES', 'OWNED', 'CoverageRow',
    'attribute', 'coverage_path', 'coverage_rows', 'domain_of', 'intent_of',
    'is_read_only', 'render_markdown', 'summary', 'write_markdown',
]
