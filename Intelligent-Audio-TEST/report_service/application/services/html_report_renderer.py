# -*- coding: utf-8 -*-
"""报告 HTML 导出渲染器。

将报告详情数据渲染为自包含的 HTML 文件（内联 CSS，无外部依赖）。
所见即所得：报告详情页上展示什么，导出的 HTML 就长什么样。

实现采用 Mixin 组合模式（同 report_utils / report_aggregation 拆分先例）：
- HtmlReportSectionMixin: Hero / 总览 / 设备与 API 卡片 / 分析结论区块渲染
- HtmlReportTableMixin: 概览表 / 分组对比 / 标签对比表格渲染
- HtmlReportDataMixin: metric_data / tag_metric_data 格式兼容解析
- HtmlReportStyleMixin: 内联 CSS 与数值格式化
"""
import html
from datetime import datetime

from report_service.application.services.html_report_renderer_section_mixin import HtmlReportSectionMixin
from report_service.application.services.html_report_renderer_table_mixin import HtmlReportTableMixin
from report_service.application.services.html_report_renderer_data_mixin import HtmlReportDataMixin
from report_service.application.services.html_report_renderer_style_mixin import HtmlReportStyleMixin


class HtmlReportRenderer(
    HtmlReportSectionMixin,
    HtmlReportTableMixin,
    HtmlReportDataMixin,
    HtmlReportStyleMixin,
):
    """将报告数据渲染为自包含 HTML 文件"""

    @staticmethod
    def render(report_data: dict) -> str:
        """
        渲染报告数据为完整 HTML 字符串。

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
