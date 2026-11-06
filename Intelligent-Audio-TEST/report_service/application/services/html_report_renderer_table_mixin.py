# -*- coding: utf-8 -*-
"""HTML 报告渲染器 —— 表格渲染 Mixin。

从 html_report_renderer.py 拆分而来，承载：
- _render_overview_table: 概览维度表（行=维度，列=资源）
- _render_category_comparison: 按用例分组的维度对比表
- _render_tag_comparison: 按用例标签的维度对比表
"""
import html

from report_service.application.services.html_report_renderer_data_mixin import HtmlReportDataMixin
from report_service.application.services.html_report_renderer_style_mixin import HtmlReportStyleMixin


class HtmlReportTableMixin:
    """HTML 表格类区块（概览表 / 分组对比 / 标签对比）渲染方法。"""

    @staticmethod
    def _render_overview_table(metric_data, all_metrics, resource_headers, rh_map, metric_info):
        """
        概览表：行=维度，列=资源，值=全局平均
        metric_data 可能是 dict 或 list（已 flatten）
        """
        # 提取 resource → metric → value 映射
        resource_metric_map = HtmlReportDataMixin._extract_resource_metric_map(metric_data)
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
                    formatted = HtmlReportStyleMixin._format_value(val, decimal_places, unit)
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
    def _render_category_comparison(metric_data, case_categories, all_metrics, resource_headers, rh_map, metric_info):
        """
        按用例分组的维度对比表
        行=分组，列=资源，每个维度一个表格
        """
        # 提取 resource → category → metric → value
        resource_cat_metric_map = HtmlReportDataMixin._extract_resource_category_metric_map(metric_data)
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
                        formatted = HtmlReportStyleMixin._format_value(val, decimal_places, unit)
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
        resource_tag_metric_map = HtmlReportDataMixin._extract_resource_tag_metric_map(tag_metric_data)
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
                        formatted = HtmlReportStyleMixin._format_value(val, decimal_places, unit)
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
