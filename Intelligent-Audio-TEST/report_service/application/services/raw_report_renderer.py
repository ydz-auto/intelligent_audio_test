# -*- coding: utf-8 -*-
"""平台原始报告导出渲染器（与 Studio 文档渲染器分离）。

Studio 渲染器（``report_studio_renderer``）只处理 AI 起草的 Markdown 子集，
导不出用例明细；本模块直接吃「报告详情 + 全量用例」两份接口数据，产出与
平台报告页同构的静态产物：

- HTML：内联 CSS + 内联 JS（``file://`` 直接可用），每条用例可展开，展开后
  按「轮次 × 资源 × 维度」列出原值；主 / 子维度按 ``parent_dimension_name``
  归组；顶部带关键词过滤；
- MD：汇总表 + 按用例分节的维度表（无交互，信息完整）。

渲染是**确定性**的：不回源、不重算、不填补缺失值；数值一律引用接口原值。
不引用任何外部资源，不含音频（音频数据量大，按产品口径不打包）。
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RAW_EXPORT_FORMATS: Tuple[str, ...] = ('html', 'md')
RAW_EXPORT_MEDIA_TYPES: Dict[str, Tuple[str, str]] = {
    'html': ('.html', 'text/html; charset=utf-8'),
    'md': ('.md', 'text/markdown; charset=utf-8'),
}


def _num(value: Any) -> str:
    """数值原样输出：不四舍五入、不换算；None / 空显示为 —。"""
    if value is None:
        return '—'
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    text = str(value).strip()
    return text if text else '—'


def _split_metric(metric: str) -> Tuple[str, Optional[str]]:
    """``拒识成功数量@round:2`` → ``('拒识成功数量', 'round:2')``。"""
    name = metric or ''
    if '@' not in name:
        return name, None
    base, _, scope = name.partition('@')
    return base, scope or None


def _case_metric_groups(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把用例 ``metrics`` 归一成 ``[{resource, rounds: [{round, rows}]}]``。

    接口形态：``metrics: [{resource, metrics: [{metric, value, dimension_type,
    parent_dimension_name, ...}]}]``，其中 ``metric`` 带 ``@round:N`` / ``@overall``
    后缀。按资源 → 轮次 → 维度三级归组，子维度挂在父维度之后。
    """
    groups: List[Dict[str, Any]] = []
    for block in case.get('metrics') or []:
        if not isinstance(block, dict):
            continue
        resource = str(block.get('resource') or '默认资源')
        by_round: Dict[str, List[Dict[str, Any]]] = {}
        for item in block.get('metrics') or []:
            if not isinstance(item, dict):
                continue
            metric_name, scope = _split_metric(str(item.get('metric') or ''))
            if not metric_name:
                continue
            round_key = scope or 'overall'
            by_round.setdefault(round_key, []).append({
                'name': metric_name,
                'value': item.get('value'),
                'dimension_type': item.get('dimension_type') or 'main',
                'parent': item.get('parent_dimension_name'),
            })
        if not by_round:
            continue
        rounds = []
        for round_key in sorted(by_round.keys()):
            rows = by_round[round_key]
            mains = [r for r in rows if r['dimension_type'] != 'sub']
            subs = [r for r in rows if r['dimension_type'] == 'sub']
            ordered: List[Dict[str, Any]] = []
            for main in mains:
                ordered.append(main)
                ordered.extend(s for s in subs if s['parent'] == main['name'])
            ordered.extend(s for s in subs if s['parent'] not in
                           {m['name'] for m in mains})
            rounds.append({'round': round_key, 'rows': ordered})
        groups.append({'resource': resource, 'rounds': rounds})
    return groups


def _tag_names(case: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for tag in case.get('tags') or []:
        name = tag.get('name') if isinstance(tag, dict) else tag
        if name:
            names.append(str(name))
    return names


# 与前端 case-report-detail/execution-results.tsx 的 META_CODES 同源：
# 这些 param_code 是元信息（设备类型 / 算法类型 / 轮次数等），不是「执行结果」。
_RESULT_META_CODES = frozenset({
    'device_type', 'deviceType', 'algorithm_type', 'algorithmType',
    'total_rounds', 'totalRounds', 'aggregated', 'multi_round',
    'multiRound', 'multi_round_result', 'session_id', 'sessionId',
    'context_mode', 'contextMode', 'error',
})
_RESULT_DISPLAY_TYPES = frozenset(
    {'text', 'timestamp', 'number', 'boolean', 'json', 'audio_file'})


def _format_timestamp(value: Any) -> str:
    """秒 / 毫秒时间戳或 ISO 字符串 → ``YYYY-MM-DD HH:mm:ss``（对齐前端）。"""
    from datetime import datetime, timezone

    text = str(value).strip()
    if not text:
        return '—'
    if text.isdigit() and 10 <= len(text) <= 13:
        milliseconds = int(text) * (1000 if len(text) == 10 else 1)
        try:
            moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
            return moment.strftime('%Y-%m-%d %H:%M:%S')
        except (OverflowError, OSError, ValueError):
            return text
    try:
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return moment.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return text


def _format_result_value(value: Any, param_type: Optional[str]) -> str:
    """执行结果值 → 展示文本（对齐前端 ``formatResultValue``）。"""
    if value is None:
        return '无数据'
    param_type = param_type or 'text'
    if param_type == 'timestamp':
        return _format_timestamp(value)
    if param_type == 'number':
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float)):
            number = float(value)
            return str(int(number)) if number.is_integer() else f'{number:.2f}'
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return str(int(number)) if number.is_integer() else f'{number:.2f}'
    if param_type == 'boolean':
        if isinstance(value, bool):
            return '是' if value else '否'
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(('{', '[')):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return value
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        return value
    if isinstance(value, dict):
        if value.get('text') is not None:
            return str(value['text'])
        if value.get('value') is not None:
            return str(value['value'])
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _case_result_groups(case: Dict[str, Any],
                        all_metrics: Sequence[Dict[str, Any]]
                        ) -> List[Dict[str, Any]]:
    """把用例 ``algorithmResults`` 归一成 ``[{label, fields}]``。

    对齐前端 ``ExecutionResults``：按 ``dimension_name`` 分组（子维度归父维度），
    无维度归属的归「设备/API 执行结果」；``param_code`` 以 ``rounds`` 开头或命中
    元信息码的跳过（多轮结果由 ``rounds`` 单独承载，不在此铺平）。
    """
    parent_of: Dict[str, str] = {}
    for meta in all_metrics or []:
        if not isinstance(meta, dict):
            continue
        name = str(meta.get('name') or '')
        if meta.get('dimension_type') == 'sub' and meta.get('parent_dimension_name'):
            parent_of[name] = str(meta['parent_dimension_name'])

    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    seen: set = set()
    for item in case.get('algorithmResults') or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get('param_code') or item.get('paramCode') or '')
        if not code or code in _RESULT_META_CODES or code.startswith('rounds'):
            continue
        param_type = str(item.get('param_type') or item.get('paramType') or 'text')
        if param_type not in _RESULT_DISPLAY_TYPES:
            continue
        if code in seen:
            continue
        seen.add(code)
        dimension = item.get('dimension_name') or item.get('dimensionName')
        dim_key = str(dimension) if dimension else ''
        dim_key = parent_of.get(dim_key, dim_key)
        round_number = item.get('round_number', item.get('roundNumber'))
        round_tag = ''
        if code.lower().endswith('@overall'):
            round_tag = 'overall'
        elif '@round:' in code.lower():
            round_tag = 'round:' + code.lower().rsplit('@round:', 1)[1]
        elif round_number is not None:
            round_tag = f'round:{round_number}'
        label = str(item.get('label') or code)
        value = _format_result_value(item.get('value'), param_type)
        field = {
            'code': code,
            'label': label,
            'value': value,
            'round': round_tag,
            'device': str(item.get('device') or ''),
            'param_type': param_type,
        }
        group_key = dim_key or '_general'
        if group_key not in groups:
            groups[group_key] = {
                'label': dim_key or '设备/API 执行结果', 'fields': []}
            order.append(group_key)
        groups[group_key]['fields'].append(field)

    for group in groups.values():
        group['fields'].sort(key=lambda f: (f['round'], f['code']))
    ordered = [groups[key] for key in order if key != '_general']
    if '_general' in groups:
        ordered.append(groups['_general'])
    return ordered


def _case_reference_fields(case: Dict[str, Any]) -> List[Tuple[str, str]]:
    """参考数据（``referenceParams``）→ ``[(label, value)]``。"""
    fields: List[Tuple[str, str]] = []
    params = case.get('referenceParams')
    if not isinstance(params, dict):
        return fields
    for code, param in params.items():
        if isinstance(param, dict):
            label = str(param.get('label') or code)
            value = param.get('text', param.get('value'))
            param_type = str(param.get('type') or 'text')
        else:
            label, value = str(code), param
            param_type = 'text'
        if param_type == 'boolean' or isinstance(value, bool):
            truthy = value if isinstance(value, bool) else str(value).strip().lower() in (
                'true', '1', 'yes', '是')
            fields.append((label, '是' if truthy else '否'))
            continue
        text = _format_result_value(value, 'text') if value not in (None, '') else ''
        fields.append((label, text))
    return fields


def _summary_rows(detail: Dict[str, Any]) -> List[Tuple[str, str]]:
    summary = detail.get('summary') or {}
    return [
        ('用例总数', _num(summary.get('total_cases'))),
        ('已完成', _num(summary.get('completed_cases'))),
        ('失败', _num(summary.get('failed_cases'))),
        ('通过率 (%)', _num(summary.get('pass_rate'))),
    ]


def _metric_matrix(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``metric_data``（资源 × 指标）+ ``all_metrics``（单位 / 聚合）合并。"""
    metric_meta: Dict[str, Dict[str, Any]] = {}
    for meta in detail.get('all_metrics') or []:
        if isinstance(meta, dict) and meta.get('name'):
            metric_meta[str(meta['name'])] = meta
    matrix: List[Dict[str, Any]] = []
    for block in detail.get('metric_data') or []:
        if not isinstance(block, dict):
            continue
        resource = str(block.get('resource') or '默认资源')
        rows = []
        for item in block.get('metrics') or []:
            if not isinstance(item, dict):
                continue
            name, _scope = _split_metric(str(item.get('metric') or ''))
            meta = metric_meta.get(name, {})
            rows.append({
                'name': name,
                'value': item.get('value'),
                'unit': meta.get('unit') or '',
                'statistic': meta.get('statistic_method') or '',
                'dimension_type': meta.get('dimension_type') or 'main',
                'parent': meta.get('parent_dimension_name'),
            })
        if rows:
            matrix.append({'resource': resource, 'rows': rows})
    return matrix


def _category_stats(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    stats: List[Dict[str, Any]] = []
    for group in detail.get('case_type_stats') or []:
        if not isinstance(group, dict):
            continue
        rows = []
        for item in group.get('metrics') or []:
            if isinstance(item, dict) and item.get('metric'):
                rows.append({'name': str(item['metric']), 'value': item.get('value')})
        stats.append({
            'name': str(group.get('group_name') or group.get('name') or '未分组'),
            'rows': rows,
        })
    return stats


# ---------------------------------------------------------------- HTML

_HTML_CSS = (
    '*,*::before,*::after{box-sizing:border-box;}'
    'html,body{margin:0;padding:0;}'
    'body{background:#f5f7fa;color:#1f2329;font-family:-apple-system,BlinkMacSystemFont,'
    '"Segoe UI","PingFang SC","Microsoft YaHei",Roboto,sans-serif;font-size:14px;'
    'line-height:1.6;}'
    '.raw-report{max-width:1100px;margin:0 auto;padding:24px 28px 64px;}'
    '.raw-report h1{font-size:22px;margin:0 0 4px;}'
    '.raw-report .meta{color:#8a8f99;font-size:12px;margin:0 0 18px;}'
    '.raw-report h2{font-size:17px;margin:26px 0 10px;padding-bottom:6px;'
    'border-bottom:1px solid #e5e7eb;}'
    '.raw-report table{width:100%;border-collapse:collapse;margin:8px 0 16px;'
    'font-size:13px;}'
    '.raw-report th,.raw-report td{border:1px solid #e5e7eb;padding:6px 10px;'
    'text-align:left;vertical-align:top;}'
    '.raw-report th{background:#f7f8fa;font-weight:600;}'
    '.raw-report .toolbar{position:sticky;top:0;z-index:5;background:#f5f7fa;'
    'padding:10px 0;border-bottom:1px solid #e5e7eb;margin-bottom:12px;}'
    '.raw-report .toolbar input{width:320px;max-width:100%;padding:6px 10px;'
    'border:1px solid #d0d3d9;border-radius:6px;font-size:13px;}'
    '.raw-report .toolbar .count{margin-left:12px;color:#8a8f99;font-size:12px;}'
    '.raw-report details.case{background:#fff;border:1px solid #e5e7eb;'
    'border-radius:8px;margin:8px 0;padding:0;}'
    '.raw-report details.case>summary{cursor:pointer;padding:10px 14px;'
    'list-style:none;display:flex;gap:10px;align-items:flex-start;}'
    '.raw-report details.case>summary::-webkit-details-marker{display:none;}'
    '.raw-report details.case>summary .name{flex:1;min-width:0;'
    'word-break:break-all;}'
    '.raw-report details.case>summary .badge{flex:none;font-size:12px;'
    'color:#57606a;background:#eef1f4;border-radius:4px;padding:1px 8px;}'
    '.raw-report details.case .body{padding:4px 14px 14px;border-top:1px solid #f0f1f3;}'
    '.raw-report .resource{font-weight:600;margin:12px 0 4px;}'
    '.raw-report .sub-title{font-weight:600;margin:14px 0 4px;padding-left:8px;'
    'border-left:3px solid #4f7cff;}'
    '.raw-report .desc{color:#57606a;font-size:12px;margin:8px 0 4px;}'
    '.raw-report .code{color:#8a8f99;font-size:11px;margin-left:6px;}'
    '.raw-report td:nth-child(2){white-space:nowrap;}'
    '.raw-report .pre{white-space:pre-wrap;word-break:break-all;'
    'font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;}'
    '.raw-report .round{color:#57606a;font-size:12px;margin:8px 0 2px;}'
    '.raw-report .sub td:first-child{padding-left:28px;color:#57606a;}'
    '.raw-report .sub td:first-child::before{content:"↳ ";}'
    '.raw-report .empty{color:#8a8f99;font-size:12px;padding:6px 0;}'
    '.raw-report .hint{color:#8a8f99;font-size:12px;margin:6px 0 0;}'
)

_HTML_SCRIPT = """(function () {
  'use strict';
  var input = document.getElementById('raw-case-filter');
  var count = document.getElementById('raw-case-count');
  var cards = Array.prototype.slice.call(
    document.querySelectorAll('details[data-raw-case]'));
  var expandAll = document.getElementById('raw-expand-all');
  var collapseAll = document.getElementById('raw-collapse-all');
  function apply() {
    var keyword = (input && input.value || '').trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var haystack = (card.getAttribute('data-raw-haystack') || '').toLowerCase();
      var visible = !keyword || haystack.indexOf(keyword) !== -1;
      card.style.display = visible ? '' : 'none';
      if (visible) shown += 1;
    });
    if (count) count.textContent = '显示 ' + shown + ' / ' + cards.length + ' 条';
  }
  if (input) input.addEventListener('input', apply);
  if (expandAll) expandAll.addEventListener('click', function () {
    cards.forEach(function (c) { c.open = true; });
  });
  if (collapseAll) collapseAll.addEventListener('click', function () {
    cards.forEach(function (c) { c.open = false; });
  });
  apply();
})();"""


def _render_metric_rows_html(rows: Iterable[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for row in rows:
        is_sub = row.get('dimension_type') == 'sub'
        cls = ' class="sub"' if is_sub else ''
        out.append(
            f'<tr{cls}><td>{html.escape(str(row["name"]))}</td>'
            f'<td>{html.escape(_num(row.get("value")))}</td></tr>')
    return out


def render_raw_report_html(detail: Dict[str, Any], cases: Sequence[Dict[str, Any]],
                           title: Optional[str] = None) -> bytes:
    """报告详情 + 全量用例 → 可交互静态 HTML（每条用例可展开看各维度值）。"""
    report_title = title or str(detail.get('name') or '平台报告')
    summary = detail.get('summary') or {}
    total_cases = summary.get('total_cases')
    pass_rate = summary.get('pass_rate')

    parts: List[str] = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f'<title>{html.escape(report_title)}</title>',
        f'<style>{_HTML_CSS}</style></head><body><div class="raw-report">',
        f'<h1>{html.escape(report_title)}</h1>',
        '<p class="meta">平台原始报告导出 ｜ '
        f'报告 ID {html.escape(_num(detail.get("id")))} ｜ '
        f'状态 {html.escape(str(detail.get("status") or ""))} ｜ '
        f'用例 {html.escape(_num(total_cases))} 条 ｜ '
        f'通过率 {html.escape(_num(pass_rate))}%</p>',
    ]

    # 总览
    parts.append('<h2>一、总览</h2><table><tbody>')
    for label, value in _summary_rows(detail):
        parts.append(f'<tr><th style="width:160px">{html.escape(label)}</th>'
                     f'<td>{html.escape(value)}</td></tr>')
    parts.append('</tbody></table>')

    # 指标矩阵
    matrix = _metric_matrix(detail)
    if matrix:
        parts.append('<h2>二、指标矩阵</h2>')
        for block in matrix:
            parts.append(f'<div class="resource">{html.escape(block["resource"])}</div>')
            parts.append('<table><thead><tr><th>指标</th><th>值</th>'
                         '<th>单位</th><th>聚合方式</th></tr></thead><tbody>')
            for row in block['rows']:
                is_sub = row.get('dimension_type') == 'sub'
                cls = ' class="sub"' if is_sub else ''
                parts.append(
                    f'<tr{cls}><td>{html.escape(str(row["name"]))}</td>'
                    f'<td>{html.escape(_num(row.get("value")))}</td>'
                    f'<td>{html.escape(str(row.get("unit") or ""))}</td>'
                    f'<td>{html.escape(str(row.get("statistic") or ""))}</td></tr>')
            parts.append('</tbody></table>')

    # 分类统计
    categories = _category_stats(detail)
    if categories:
        parts.append('<h2>三、分类统计</h2>')
        for group in categories:
            parts.append(f'<div class="resource">{html.escape(group["name"])}</div>')
            parts.append('<table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>')
            for row in group['rows']:
                parts.append(
                    f'<tr><td>{html.escape(row["name"])}</td>'
                    f'<td>{html.escape(_num(row.get("value")))}</td></tr>')
            parts.append('</tbody></table>')

    # 用例明细
    parts.append('<h2>四、用例明细</h2>')
    parts.append(
        '<div class="toolbar">'
        '<input id="raw-case-filter" type="search" placeholder="按用例名 / 分类 / 标签 / 指标过滤"/>'
        '<span class="count" id="raw-case-count"></span>'
        '<button type="button" id="raw-expand-all">全部展开</button>'
        '<button type="button" id="raw-collapse-all">全部收起</button>'
        '</div>')
    parts.append('<p class="hint">音频文件不随报告打包，请在平台内播放。</p>')

    case_count = 0
    all_metrics = detail.get('all_metrics') or []
    for index, case in enumerate(cases, 1):
        groups = _case_metric_groups(case)
        result_groups = _case_result_groups(case, all_metrics)
        reference_fields = _case_reference_fields(case)
        tags = _tag_names(case)
        name = str(case.get('name') or f'用例 {index}')
        category = str(case.get('category') or '')
        haystack = ' '.join([name, category, ' '.join(tags)] +
                            [r['name'] for g in groups for rd in g['rounds']
                             for r in rd['rows']] +
                            [f['label'] for g in result_groups
                             for f in g['fields']]).lower()
        parts.append(
            f'<details class="case" data-raw-case data-raw-haystack='
            f'"{html.escape(haystack, quote=True)}">'
            f'<summary><span class="name">{html.escape(name)}</span>'
            + (f'<span class="badge">{html.escape(category)}</span>' if category else '')
            + '</summary><div class="body">')
        if tags:
            parts.append(f'<div class="round">标签：{html.escape(" / ".join(tags))}</div>')
        if case.get('description'):
            parts.append(f'<div class="desc">{html.escape(str(case["description"]))}</div>')
        if reference_fields:
            parts.append('<div class="sub-title">参考数据</div>')
            parts.append('<table><tbody>')
            for label, value in reference_fields:
                parts.append(
                    f'<tr><th>{html.escape(label)}</th>'
                    f'<td class="pre">{html.escape(value or "—")}</td></tr>')
            parts.append('</tbody></table>')
        if result_groups:
            parts.append('<div class="sub-title">执行结果</div>')
            for group in result_groups:
                parts.append(f'<div class="resource">{html.escape(group["label"])}</div>')
                parts.append('<table><thead><tr><th>字段</th><th>轮次</th>'
                             '<th>值</th></tr></thead><tbody>')
                for field in group['fields']:
                    round_label = {'overall': '整体'}.get(
                        field['round'], field['round'].replace('round:', '第 ') + ' 轮'
                        if field['round'] else '')
                    parts.append(
                        f'<tr><td>{html.escape(field["label"])}'
                        f'<span class="code">{html.escape(field["code"])}</span></td>'
                        f'<td>{html.escape(round_label)}</td>'
                        f'<td class="pre">{html.escape(field["value"])}</td></tr>')
                parts.append('</tbody></table>')
        if groups:
            parts.append('<div class="sub-title">评分指标</div>')
        if not groups:
            if not result_groups and not reference_fields:
                parts.append('<div class="empty">该用例没有指标数据</div>')
        for group in groups:
            parts.append(f'<div class="resource">{html.escape(group["resource"])}</div>')
            for rd in group['rounds']:
                parts.append(f'<div class="round">{html.escape(rd["round"])}</div>')
                parts.append('<table><thead><tr><th>维度</th><th>值</th>'
                             '</tr></thead><tbody>')
                parts.extend(_render_metric_rows_html(rd['rows']))
                parts.append('</tbody></table>')
        parts.append('</div></details>')
        case_count += 1

    parts.append(f'<script>{_HTML_SCRIPT}</script></div></body></html>')
    parts.append(f'<!-- raw-case-count={case_count} -->')
    return ''.join(parts).encode('utf-8')


# ---------------------------------------------------------------- Markdown


def render_raw_report_markdown(detail: Dict[str, Any],
                               cases: Sequence[Dict[str, Any]],
                               title: Optional[str] = None) -> bytes:
    """报告详情 + 全量用例 → Markdown（汇总表 + 按用例分节的维度表）。"""
    report_title = title or str(detail.get('name') or '平台报告')
    lines: List[str] = [f'# {report_title}', '']
    lines.append('## 一、总览')
    lines.append('')
    lines.append('| 指标 | 值 |')
    lines.append('|---|---|')
    for label, value in _summary_rows(detail):
        lines.append(f'| {label} | {value} |')
    lines.append('')

    matrix = _metric_matrix(detail)
    if matrix:
        lines.append('## 二、指标矩阵')
        lines.append('')
        for block in matrix:
            lines.append(f'### {block["resource"]}')
            lines.append('')
            lines.append('| 指标 | 值 | 单位 | 聚合方式 |')
            lines.append('|---|---|---|---|')
            for row in block['rows']:
                lines.append(
                    f'| {row["name"]} | {_num(row.get("value"))} | '
                    f'{row.get("unit") or ""} | {row.get("statistic") or ""} |')
            lines.append('')

    categories = _category_stats(detail)
    if categories:
        lines.append('## 三、分类统计')
        lines.append('')
        for group in categories:
            lines.append(f'### {group["name"]}')
            lines.append('')
            lines.append('| 指标 | 值 |')
            lines.append('|---|---|')
            for row in group['rows']:
                lines.append(f'| {row["name"]} | {_num(row.get("value"))} |')
            lines.append('')

    lines.append('## 四、用例明细')
    lines.append('')
    lines.append('> 音频文件不随报告打包，需在平台内播放。')
    lines.append('')
    all_metrics = detail.get('all_metrics') or []
    for index, case in enumerate(cases, 1):
        name = str(case.get('name') or f'用例 {index}')
        category = str(case.get('category') or '')
        tags = _tag_names(case)
        header = f'### {index}. {name}'
        if category:
            header += f' ｜ {category}'
        lines.append(header)
        lines.append('')
        if tags:
            lines.append(f'标签：{" / ".join(tags)}')
            lines.append('')
        if case.get('description'):
            lines.append(f'用例描述：{case["description"]}')
            lines.append('')
        reference_fields = _case_reference_fields(case)
        if reference_fields:
            lines.append('**参考数据**')
            lines.append('')
            lines.append('| 字段 | 值 |')
            lines.append('|---|---|')
            for label, value in reference_fields:
                lines.append(f'| {label} | {value or "—"} |')
            lines.append('')
        result_groups = _case_result_groups(case, all_metrics)
        if result_groups:
            lines.append('**执行结果**')
            lines.append('')
            for group in result_groups:
                lines.append(f'**{group["label"]}**')
                lines.append('')
                lines.append('| 字段 | 轮次 | 值 |')
                lines.append('|---|---|---|')
                for field in group['fields']:
                    round_label = {'overall': '整体'}.get(
                        field['round'],
                        field['round'].replace('round:', '第 ') + ' 轮'
                        if field['round'] else '')
                    value = str(field['value']).replace('|', '\\|').replace('\n', ' ')
                    lines.append(
                        f'| {field["label"]} | {round_label} | {value} |')
                lines.append('')
        groups = _case_metric_groups(case)
        if not groups:
            if not result_groups and not reference_fields:
                lines.append('（该用例没有指标数据）')
            lines.append('')
            continue
        lines.append('**评分指标**')
        lines.append('')
        for group in groups:
            for rd in group['rounds']:
                lines.append(f'**{group["resource"]} / {rd["round"]}**')
                lines.append('')
                lines.append('| 维度 | 值 |')
                lines.append('|---|---|')
                for row in rd['rows']:
                    lines.append(f'| {row["name"]} | {_num(row.get("value"))} |')
                lines.append('')
    return '\n'.join(lines).encode('utf-8')


def render_raw_report(detail: Dict[str, Any], cases: Sequence[Dict[str, Any]],
                      fmt: str, title: Optional[str] = None
                      ) -> Tuple[bytes, str, str]:
    """按格式渲染原始报告 → ``(内容, 扩展名, MIME)``。"""
    fmt_value = str(fmt or '').strip().lower()
    if fmt_value not in RAW_EXPORT_FORMATS:
        supported = ' / '.join(RAW_EXPORT_FORMATS)
        raise ValueError(f'不支持的原始报告导出格式：{fmt}（仅支持 {supported}）')
    ext, mime = RAW_EXPORT_MEDIA_TYPES[fmt_value]
    if fmt_value == 'md':
        return render_raw_report_markdown(detail, cases, title), ext, mime
    return render_raw_report_html(detail, cases, title), ext, mime


__all__ = [
    'RAW_EXPORT_FORMATS', 'RAW_EXPORT_MEDIA_TYPES', 'render_raw_report',
    'render_raw_report_html', 'render_raw_report_markdown',
]
