"""
报告 HTML 导出渲染器
将报告详情数据渲染为自包含的 HTML 文件（内联 CSS，无外部依赖）
所见即所得：报告详情页上展示什么，导出的 HTML 就长什么样
"""
import json
import html
from datetime import datetime


class HtmlReportRenderer:
    """将报告数据渲染为自包含 HTML 文件"""

    @staticmethod
    def render(report_data: dict) -> str:
        """
        渲染报告数据为完整 HTML 字符串

        Args:
            report_data: 报告详情 dict（与 get_one API 返回的 data 字段结构一致）
                         包含 id/name/type/task_id/task_name/summary/description/status/analysis/created_at 等

        Returns:
            完整的 HTML 字符串
        """
        summary = report_data.get('summary') or {}

        # ---------- 数据提取 ----------
        report_name = report_data.get('name', '未命名报告')
        report_type = report_data.get('type', '')
        report_desc = report_data.get('description') or ''
        report_analysis = report_data.get('analysis') or ''
        created_at = report_data.get('created_at', '')
        status = report_data.get('status', 'draft')
        task_name = report_data.get('task_name', '')

        total_cases = summary.get('total_cases', 0) or 0
        completed_cases = summary.get('completed_cases', 0) or 0
        failed_cases = summary.get('failed_cases', 0) or 0

        all_metrics = summary.get('all_metrics') or []
        device_stats = summary.get('device_stats') or []
        api_stats = summary.get('api_stats') or []
        devices = summary.get('devices') or []
        apis = summary.get('apis') or []
        resource_headers = summary.get('resource_headers') or []
        case_categories = summary.get('case_categories') or []
        all_case_tags = summary.get('all_case_tags') or []
        metric_data = summary.get('metric_data') or {}
        tag_metric_data = summary.get('tag_metric_data') or {}

        # 资源表头映射 key → label
        rh_map = {}
        for rh in resource_headers:
            if isinstance(rh, dict):
                rh_map[rh.get('key', '')] = rh.get('label', rh.get('key', ''))

        # 维度信息映射 name → {unit, decimal_places}
        metric_info = {}
        for m in all_metrics:
            if isinstance(m, dict) and m.get('name'):
                metric_info[m['name']] = {
                    'unit': m.get('unit', ''),
                    'decimal_places': m.get('decimal_places', 2)
                }

        # ---------- 构建各区块 ----------
        sections = []

        # 1. Hero 标题区
        sections.append(HtmlReportRenderer._render_hero(
            report_name, report_desc, created_at, status, report_type, task_name
        ))

        # 2. 总览统计卡片
        sections.append(HtmlReportRenderer._render_overview_stats(
            total_cases, completed_cases, failed_cases, len(all_metrics), len(devices), len(apis)
        ))

        # 3. 概览维度表（资源 × 维度 全局平均值）
        if metric_data and all_metrics:
            sections.append(HtmlReportRenderer._render_overview_table(
                metric_data, all_metrics, resource_headers, rh_map, metric_info
            ))

        # 4. 设备统计
        if device_stats:
            sections.append(HtmlReportRenderer._render_device_stats(device_stats, metric_info))

        # 5. API 统计
        if api_stats:
            sections.append(HtmlReportRenderer._render_api_stats(api_stats, metric_info))

        # 6. 按用例分组维度对比
        if case_categories and metric_data:
            sections.append(HtmlReportRenderer._render_category_comparison(
                metric_data, case_categories, all_metrics, resource_headers, rh_map, metric_info
            ))

        # 7. 按用例标签维度对比
        if all_case_tags and tag_metric_data:
            sections.append(HtmlReportRenderer._render_tag_comparison(
                tag_metric_data, all_case_tags, all_metrics, resource_headers, rh_map, metric_info
            ))

        # 8. 分析结论
        if report_analysis:
            sections.append(HtmlReportRenderer._render_analysis(report_analysis))

        # ---------- 组装完整 HTML ----------
        type_label = {'task': '任务报告', 'comparison': '对比报告', 'secondary_comparison': '二次对比报告'}.get(report_type, report_type)
        status_label = '已发布' if status == 'published' else '草稿'

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(report_name)} - {type_label}</title>
<style>
{HtmlReportRenderer._get_styles()}
</style>
</head>
<body>
<div class="report-container">
{''.join(sections)}
<div class="report-footer">
  <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 状态: {status_label} | 导出自智能音频测试系统</p>
</div>
</div>
</body>
</html>"""
        return html_content

    # ==================== 区块渲染方法 ====================

    @staticmethod
    def _render_hero(name, desc, created_at, status, report_type, task_name):
        type_label = {'task': '任务报告', 'comparison': '对比报告', 'secondary_comparison': '二次对比报告'}.get(report_type, report_type)
        status_label = '已发布' if status == 'published' else '草稿'
        status_class = 'published' if status == 'published' else 'draft'

        desc_html = f'<p class="hero-desc">{html.escape(desc)}</p>' if desc else ''
        task_html = f'<span class="hero-meta-item">任务: {html.escape(task_name)}</span>' if task_name else ''

        return f"""
<section class="report-hero">
  <h1 class="hero-title">{html.escape(name)}</h1>
  {desc_html}
  <div class="hero-meta">
    {task_html}
    <span class="hero-meta-item">类型: {type_label}</span>
    <span class="hero-meta-item">创建时间: {html.escape(str(created_at)[:19] if created_at else 'N/A')}</span>
    <span class="status-badge {status_class}">{status_label}</span>
  </div>
</section>"""

    @staticmethod
    def _render_overview_stats(total_cases, completed, failed, metric_count, device_count, api_count):
        success_rate = round(completed / total_cases * 100, 1) if total_cases > 0 else 0
        return f"""
<section class="section">
  <h2 class="section-title">总览</h2>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">{total_cases}</div>
      <div class="stat-label">用例总数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value stat-green">{completed}</div>
      <div class="stat-label">已完成</div>
    </div>
    <div class="stat-card">
      <div class="stat-value stat-red">{failed}</div>
      <div class="stat-label">失败</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{success_rate}%</div>
      <div class="stat-label">成功率</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{metric_count}</div>
      <div class="stat-label">评估维度</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{device_count + api_count}</div>
      <div class="stat-label">资源数</div>
    </div>
  </div>
</section>"""

    @staticmethod
    def _render_overview_table(metric_data, all_metrics, resource_headers, rh_map, metric_info):
        """
        概览表：行=维度，列=资源，值=全局平均
        metric_data 可能是 dict 或 list（已 flatten）
        """
        # 提取 resource → metric → value 映射
        resource_metric_map = HtmlReportRenderer._extract_resource_metric_map(metric_data)
        if not resource_metric_map:
            return ''

        # 资源列
        resources = list(resource_metric_map.keys())
        resource_labels = [rh_map.get(r, r) for r in resources]

        rows_html = ''
        for m in all_metrics:
            if not isinstance(m, dict) or not m.get('name'):
                continue
            metric_name = m['name']
            unit = m.get('unit', '')
            decimal_places = m.get('decimal_places', 2)
            cells = ''
            for res in resources:
                val = resource_metric_map.get(res, {}).get(metric_name)
                if val is not None:
                    formatted = HtmlReportRenderer._format_value(val, decimal_places, unit)
                    cells += f'<td class="num-cell">{formatted}</td>'
                else:
                    cells += '<td class="num-cell">-</td>'
            metric_display = html.escape(metric_name)
            if unit:
                metric_display += f' <span class="unit">({html.escape(unit)})</span>'
            rows_html += f'<tr><td class="label-cell">{metric_display}</td>{cells}</tr>\n'

        if not rows_html:
            return ''

        header_cells = ''.join(f'<th>{html.escape(lbl)}</th>' for lbl in resource_labels)

        return f"""
<section class="section">
  <h2 class="section-title">维度概览</h2>
  <div class="table-wrapper">
    <table class="data-table">
      <thead><tr><th>评估维度</th>{header_cells}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</section>"""

    @staticmethod
    def _render_device_stats(device_stats, metric_info):
        cards = ''
        for d in device_stats:
            if not isinstance(d, dict):
                continue
            name = d.get('name', 'N/A')
            model = d.get('model', '')
            status = d.get('status', '')
            total = d.get('total_cases', 0) or 0
            completed = d.get('completed_cases', 0) or 0
            failed = d.get('failed_cases', 0) or 0
            sr = d.get('success_rate', 0) or 0
            sr_class = 'sr-green' if sr >= 80 else ('sr-yellow' if sr >= 50 else 'sr-red')

            metrics_html = ''
            extra_metrics = d.get('metrics')
            if isinstance(extra_metrics, dict):
                for mk, mv in extra_metrics.items():
                    mi = metric_info.get(mk, {})
                    unit = mi.get('unit', '')
                    dp = mi.get('decimal_places', 2)
                    formatted = HtmlReportRenderer._format_value(mv, dp, unit)
                    metrics_html += f'<span class="mini-metric"><span class="mini-metric-name">{html.escape(str(mk))}</span><span class="mini-metric-value">{formatted}</span></span>'

            model_html = f'<span class="dev-model">{html.escape(str(model))}</span>' if model else ''
            metrics_section = f'<div class="dev-metrics">{metrics_html}</div>' if metrics_html else ''

            cards += f"""
<div class="device-card">
  <div class="dev-header">
    <span class="dev-name">{html.escape(str(name))}</span>
    {model_html}
    <span class="dev-status {'online' if status == 'online' else 'offline'}">{html.escape(str(status or 'N/A'))}</span>
  </div>
  <div class="dev-stats-row">
    <span>总数: {total}</span>
    <span>完成: {completed}</span>
    <span>失败: {failed}</span>
    <span class="{sr_class}">成功率: {sr}%</span>
  </div>
  {metrics_section}
</div>"""
        return f"""
<section class="section">
  <h2 class="section-title">设备统计</h2>
  <div class="device-grid">{cards}</div>
</section>"""

    @staticmethod
    def _render_api_stats(api_stats, metric_info):
        cards = ''
        for a in api_stats:
            if not isinstance(a, dict):
                continue
            name = a.get('name', 'N/A')
            status = a.get('status', '')
            total = a.get('total_cases', 0) or 0
            completed = a.get('completed_cases', 0) or 0
            failed = a.get('failed_cases', 0) or 0
            sr = a.get('success_rate', 0) or 0
            sr_class = 'sr-green' if sr >= 80 else ('sr-yellow' if sr >= 50 else 'sr-red')
            avg_rt = a.get('avg_response_time')
            stability = a.get('stability')

            metrics_html = ''
            extra_metrics = a.get('metrics')
            if isinstance(extra_metrics, dict):
                for mk, mv in extra_metrics.items():
                    mi = metric_info.get(mk, {})
                    unit = mi.get('unit', '')
                    dp = mi.get('decimal_places', 2)
                    formatted = HtmlReportRenderer._format_value(mv, dp, unit)
                    metrics_html += f'<span class="mini-metric"><span class="mini-metric-name">{html.escape(str(mk))}</span><span class="mini-metric-value">{formatted}</span></span>'

            rt_html = f'<span>平均响应: {avg_rt:.0f}ms</span>' if avg_rt is not None else ''
            stab_html = f'<span>稳定性: {stability:.1f}%</span>' if stability is not None else ''
            metrics_section = f'<div class="dev-metrics">{metrics_html}</div>' if metrics_html else ''

            cards += f"""
<div class="device-card">
  <div class="dev-header">
    <span class="dev-name">{html.escape(str(name))}</span>
    <span class="dev-status {'online' if status == 'active' or status == 'online' else 'offline'}">{html.escape(str(status or 'N/A'))}</span>
  </div>
  <div class="dev-stats-row">
    <span>总数: {total}</span>
    <span>完成: {completed}</span>
    <span>失败: {failed}</span>
    <span class="{sr_class}">成功率: {sr}%</span>
    {rt_html}
    {stab_html}
  </div>
  {metrics_section}
</div>"""
        return f"""
<section class="section">
  <h2 class="section-title">API 统计</h2>
  <div class="device-grid">{cards}</div>
</section>"""

    @staticmethod
    def _render_category_comparison(metric_data, case_categories, all_metrics, resource_headers, rh_map, metric_info):
        """
        按用例分组的维度对比表
        行=分组，列=资源，每个维度一个表格
        """
        # 提取 resource → category → metric → value
        resource_cat_metric_map = HtmlReportRenderer._extract_resource_category_metric_map(metric_data)
        if not resource_cat_metric_map:
            return ''

        resources = list(resource_cat_metric_map.keys())
        resource_labels = [rh_map.get(r, r) for r in resources]

        # 获取所有分组名
        category_names = []
        for cat in case_categories:
            if isinstance(cat, dict):
                name = cat.get('name', cat.get('category_name', cat.get('categoryName', '')))
                if name:
                    category_names.append(str(name))
        # 也从 metric_data 中提取分组名
        for res in resources:
            for cat_name in resource_cat_metric_map[res].keys():
                if cat_name not in category_names:
                    category_names.append(cat_name)

        # 每个维度生成一个表格
        tables_html = ''
        for m in all_metrics:
            if not isinstance(m, dict) or not m.get('name'):
                continue
            metric_name = m['name']
            unit = m.get('unit', '')
            decimal_places = m.get('decimal_places', 2)

            rows = ''
            has_data = False
            for cat_name in category_names:
                cells = ''
                for res in resources:
                    val = resource_cat_metric_map.get(res, {}).get(cat_name, {}).get(metric_name)
                    if val is not None:
                        formatted = HtmlReportRenderer._format_value(val, decimal_places, unit)
                        cells += f'<td class="num-cell">{formatted}</td>'
                        has_data = True
                    else:
                        cells += '<td class="num-cell">-</td>'
                rows += f'<tr><td class="label-cell">{html.escape(cat_name)}</td>{cells}</tr>\n'

            if not has_data:
                continue

            header_cells = ''.join(f'<th>{html.escape(lbl)}</th>' for lbl in resource_labels)
            metric_display = html.escape(metric_name)
            if unit:
                metric_display += f' <span class="unit">({html.escape(unit)})</span>'

            tables_html += f"""
<div class="metric-sub-table">
  <h3 class="sub-table-title">{metric_display}</h3>
  <div class="table-wrapper">
    <table class="data-table">
      <thead><tr><th>用例分组</th>{header_cells}</tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""

        if not tables_html:
            return ''

        return f"""
<section class="section">
  <h2 class="section-title">按用例分组对比</h2>
  {tables_html}
</section>"""

    @staticmethod
    def _render_tag_comparison(tag_metric_data, all_case_tags, all_metrics, resource_headers, rh_map, metric_info):
        """
        按用例标签的维度对比表
        行=标签，列=资源，每个维度一个表格
        """
        # 提取 resource → tag → metric → value
        resource_tag_metric_map = HtmlReportRenderer._extract_resource_tag_metric_map(tag_metric_data)
        if not resource_tag_metric_map:
            return ''

        resources = list(resource_tag_metric_map.keys())
        resource_labels = [rh_map.get(r, r) for r in resources]

        # 获取所有标签名
        tag_names = []
        for tag in all_case_tags:
            if isinstance(tag, dict):
                name = tag.get('name', tag.get('tag_name', tag.get('tagName', '')))
                if name:
                    tag_names.append(str(name))
        # 也从 metric_data 中提取标签名
        for res in resources:
            for tn in resource_tag_metric_map[res].keys():
                if tn not in tag_names:
                    tag_names.append(tn)

        # 每个维度生成一个表格
        tables_html = ''
        for m in all_metrics:
            if not isinstance(m, dict) or not m.get('name'):
                continue
            metric_name = m['name']
            unit = m.get('unit', '')
            decimal_places = m.get('decimal_places', 2)

            rows = ''
            has_data = False
            for tag_name in tag_names:
                cells = ''
                for res in resources:
                    val = resource_tag_metric_map.get(res, {}).get(tag_name, {}).get(metric_name)
                    if val is not None:
                        formatted = HtmlReportRenderer._format_value(val, decimal_places, unit)
                        cells += f'<td class="num-cell">{formatted}</td>'
                        has_data = True
                    else:
                        cells += '<td class="num-cell">-</td>'
                rows += f'<tr><td class="label-cell">{html.escape(tag_name)}</td>{cells}</tr>\n'

            if not has_data:
                continue

            header_cells = ''.join(f'<th>{html.escape(lbl)}</th>' for lbl in resource_labels)
            metric_display = html.escape(metric_name)
            if unit:
                metric_display += f' <span class="unit">({html.escape(unit)})</span>'

            tables_html += f"""
<div class="metric-sub-table">
  <h3 class="sub-table-title">{metric_display}</h3>
  <div class="table-wrapper">
    <table class="data-table">
      <thead><tr><th>用例标签</th>{header_cells}</tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""

        if not tables_html:
            return ''

        return f"""
<section class="section">
  <h2 class="section-title">按用例标签对比</h2>
  {tables_html}
</section>"""

    @staticmethod
    def _render_analysis(analysis):
        # analysis 可能是 HTML 或纯文本
        # 简单做一下安全处理：去掉 script 标签
        import re
        safe = re.sub(r'<script[^>]*>.*?</script>', '', analysis, flags=re.IGNORECASE | re.DOTALL)
        return f"""
<section class="section">
  <h2 class="section-title">分析结论</h2>
  <div class="analysis-content">{safe}</div>
</section>"""

    # ==================== 数据提取辅助方法 ====================

    @staticmethod
    def _extract_resource_metric_map(metric_data):
        """
        从 metric_data 提取 {resource: {metric: value}} 映射（概览级全局平均）
        处理 dict 和 list 两种格式
        """
        result = {}
        if isinstance(metric_data, dict):
            # 新格式: {resource: {metric: value}}
            is_flat = all(
                isinstance(v, dict) and all(not isinstance(vv, dict) for vv in v.values())
                for v in metric_data.values()
            ) if metric_data else False
            if is_flat:
                for res, metrics in metric_data.items():
                    if isinstance(metrics, dict):
                        result[str(res)] = {k: v for k, v in metrics.items()}
            else:
                # 旧格式: {category: {resource: {metric: value}}} → 取所有 category 的全局
                # 这里取每个 resource 下所有 category 的平均
                temp = {}  # {resource: {metric: [values]}}
                for cat, res_map in metric_data.items():
                    if not isinstance(res_map, dict):
                        continue
                    for res, metrics in res_map.items():
                        if not isinstance(metrics, dict):
                            continue
                        if res not in temp:
                            temp[res] = {}
                        for mk, mv in metrics.items():
                            if mv is not None:
                                temp[res].setdefault(mk, []).append(mv)
                for res, metrics in temp.items():
                    result[res] = {k: sum(v) / len(v) for k, v in metrics.items() if v}

        elif isinstance(metric_data, list):
            # flatten 后的格式
            # 格式1: [{resource, metrics: [{metric, value}]}]  (全局平均)
            if any(isinstance(x, dict) and 'metrics' in x and 'categories' not in x for x in metric_data):
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    metrics = item.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res] = {m.get('metric'): m.get('value') for m in metrics if isinstance(m, dict)}

            # 格式2: [{resource, categories: [{categoryId, categoryName, metrics: [{metric, value}]}]}]
            elif any(isinstance(x, dict) and isinstance(x.get('categories'), list) for x in metric_data):
                temp = {}  # {resource: {metric: [values]}}
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    if res not in temp:
                        temp[res] = {}
                    for cat in item.get('categories', []):
                        if not isinstance(cat, dict):
                            continue
                        for m in cat.get('metrics', []):
                            if isinstance(m, dict) and m.get('metric') is not None:
                                val = m.get('value')
                                if val is not None:
                                    temp[res].setdefault(m['metric'], []).append(val)
                for res, metrics in temp.items():
                    result[res] = {k: sum(v) / len(v) for k, v in metrics.items() if v}

            # 格式3: [{category_id, category_name, resource, metric, value}] 或 [{metrics: [...]}]
            else:
                for item in metric_data:
                    if not isinstance(item, dict):
                        continue
                    res = str(item.get('resource', ''))
                    if not res:
                        continue
                    if res not in result:
                        result[res] = {}
                    if isinstance(item.get('metrics'), list):
                        for m in item.get('metrics', []):
                            if isinstance(m, dict) and m.get('metric') is not None:
                                result[res][m['metric']] = m.get('value')
                    elif item.get('metric') is not None:
                        result[res][item['metric']] = item.get('value')

        return result

    @staticmethod
    def _extract_resource_category_metric_map(metric_data):
        """
        从 metric_data 提取 {resource: {category_name: {metric: value}}} 映射
        用于按分组对比表
        """
        result = {}
        if isinstance(metric_data, dict):
            # 旧格式: {category: {resource: {metric: value}}}
            for cat, res_map in metric_data.items():
                cat_name = str(cat)
                if not isinstance(res_map, dict):
                    continue
                for res, metrics in res_map.items():
                    if not isinstance(metrics, dict):
                        continue
                    res_key = str(res)
                    if res_key not in result:
                        result[res_key] = {}
                    result[res_key][cat_name] = {k: v for k, v in metrics.items() if v is not None}

        elif isinstance(metric_data, list):
            # flatten 后的格式: [{resource, categories: [{categoryId, categoryName, metrics: [{metric, value}]}]}]
            for item in metric_data:
                if not isinstance(item, dict):
                    continue
                res = str(item.get('resource', ''))
                if not res:
                    continue
                if res not in result:
                    result[res] = {}
                for cat in item.get('categories', []):
                    if not isinstance(cat, dict):
                        continue
                    cat_name = cat.get('categoryName') or cat.get('category_name') or str(cat.get('categoryId', ''))
                    metrics = cat.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res][str(cat_name)] = {
                            m.get('metric'): m.get('value')
                            for m in metrics
                            if isinstance(m, dict) and m.get('metric') is not None
                        }

        return result

    @staticmethod
    def _extract_resource_tag_metric_map(tag_metric_data):
        """
        从 tag_metric_data 提取 {resource: {tag_name: {metric: value}}} 映射
        用于按标签对比表
        """
        result = {}
        if isinstance(tag_metric_data, dict):
            for tag, res_map in tag_metric_data.items():
                tag_name = str(tag)
                if not isinstance(res_map, dict):
                    continue
                for res, metrics in res_map.items():
                    if not isinstance(metrics, dict):
                        continue
                    res_key = str(res)
                    if res_key not in result:
                        result[res_key] = {}
                    result[res_key][tag_name] = {k: v for k, v in metrics.items() if v is not None}

        elif isinstance(tag_metric_data, list):
            for item in tag_metric_data:
                if not isinstance(item, dict):
                    continue
                res = str(item.get('resource', ''))
                if not res:
                    continue
                if res not in result:
                    result[res] = {}
                for tag in item.get('tags', []):
                    if not isinstance(tag, dict):
                        continue
                    tag_name = tag.get('tag_name') or tag.get('tagName') or str(tag.get('tag_id', ''))
                    metrics = tag.get('metrics', [])
                    if isinstance(metrics, list):
                        result[res][str(tag_name)] = {
                            m.get('metric'): m.get('value')
                            for m in metrics
                            if isinstance(m, dict) and m.get('metric') is not None
                        }

        return result

    # ==================== 格式化辅助 ====================

    @staticmethod
    def _format_value(val, decimal_places=2, unit=''):
        """格式化数值"""
        if val is None:
            return '-'
        try:
            if isinstance(val, str):
                # 尝试转 float
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    return html.escape(str(val))
            formatted = f"{val:.{decimal_places}f}"
            if unit:
                formatted += html.escape(unit)
            return formatted
        except (ValueError, TypeError):
            return html.escape(str(val))

    @staticmethod
    def _get_styles():
        """返回内联 CSS 样式"""
        return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #1e293b; line-height: 1.6; }
.report-container { max-width: 1200px; margin: 0 auto; padding: 24px; }

/* Hero */
.report-hero { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; border-radius: 16px; padding: 32px; margin-bottom: 24px; }
.hero-title { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.hero-desc { font-size: 14px; opacity: 0.9; margin-bottom: 16px; }
.hero-meta { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; font-size: 13px; opacity: 0.95; }
.hero-meta-item { display: inline-flex; align-items: center; }
.status-badge { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.status-badge.published { background: rgba(34, 197, 94, 0.2); color: #bbf7d0; }
.status-badge.draft { background: rgba(251, 191, 36, 0.2); color: #fde68a; }

/* Section */
.section { background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.section-title { font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }

/* Stats Grid */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 16px; }
.stat-card { background: #f8fafc; border-radius: 10px; padding: 20px; text-align: center; border: 1px solid #e2e8f0; }
.stat-value { font-size: 32px; font-weight: 700; color: #1e293b; }
.stat-value.stat-green { color: #16a34a; }
.stat-value.stat-red { color: #dc2626; }
.stat-label { font-size: 13px; color: #64748b; margin-top: 4px; }

/* Tables */
.table-wrapper { overflow-x: auto; margin-bottom: 16px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.data-table thead th { background: #f1f5f9; color: #475569; font-weight: 600; padding: 10px 14px; text-align: left; border-bottom: 2px solid #e2e8f0; white-space: nowrap; }
.data-table thead th:first-child { min-width: 140px; }
.data-table tbody td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9; }
.data-table tbody tr:nth-child(even) { background: #f8fafc; }
.data-table tbody tr:hover { background: #eff6ff; }
.label-cell { font-weight: 500; color: #334155; white-space: nowrap; }
.num-cell { text-align: right; font-variant-numeric: tabular-nums; color: #1e293b; }
.unit { font-size: 12px; color: #94a3b8; font-weight: 400; }

/* Sub Table (per metric) */
.metric-sub-table { margin-bottom: 24px; }
.sub-table-title { font-size: 15px; font-weight: 600; color: #475569; margin-bottom: 8px; padding: 6px 12px; background: #f1f5f9; border-radius: 6px; border-left: 4px solid #6366f1; }

/* Device/API Cards */
.device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.device-card { background: #f8fafc; border-radius: 10px; padding: 16px; border: 1px solid #e2e8f0; }
.dev-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.dev-name { font-weight: 600; font-size: 15px; color: #1e293b; }
.dev-model { font-size: 13px; color: #64748b; }
.dev-status { font-size: 12px; padding: 2px 8px; border-radius: 8px; }
.dev-status.online { background: #dcfce7; color: #16a34a; }
.dev-status.offline { background: #fee2e2; color: #dc2626; }
.dev-stats-row { display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; color: #475569; }
.sr-green { color: #16a34a; font-weight: 600; }
.sr-yellow { color: #ca8a04; font-weight: 600; }
.sr-red { color: #dc2626; font-weight: 600; }
.dev-metrics { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; }
.mini-metric { display: inline-flex; flex-direction: column; background: white; padding: 4px 10px; border-radius: 6px; border: 1px solid #e2e8f0; }
.mini-metric-name { font-size: 11px; color: #64748b; }
.mini-metric-value { font-size: 14px; font-weight: 600; color: #1e293b; }

/* Analysis */
.analysis-content { font-size: 14px; color: #334155; line-height: 1.8; }
.analysis-content p { margin-bottom: 8px; }
.analysis-content table { width: 100%; border-collapse: collapse; margin: 8px 0; }
.analysis-content table td, .analysis-content table th { border: 1px solid #e2e8f0; padding: 6px 10px; }

/* Footer */
.report-footer { text-align: center; padding: 16px; color: #94a3b8; font-size: 12px; }

@media print { .section { break-inside: avoid; } .report-hero { break-inside: avoid; } }
"""
