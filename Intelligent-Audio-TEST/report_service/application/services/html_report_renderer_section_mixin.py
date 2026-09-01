# -*- coding: utf-8 -*-
"""HTML 报告渲染器 —— 区块渲染 Mixin。

从 html_report_renderer.py 拆分而来，承载：
- _render_hero / _render_overview_stats: 标题区与总览统计卡片
- _render_device_stats / _render_api_stats: 设备与 API 统计卡片
- _render_analysis: 分析结论区块
"""
import html
import re

from report_service.application.services.html_report_renderer_style_mixin import HtmlReportStyleMixin


class HtmlReportSectionMixin:
    """HTML 区块（Hero / 总览 / 资源卡片 / 分析结论）渲染方法。"""

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
                    formatted = HtmlReportStyleMixin._format_value(mv, dp, unit)
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
                    formatted = HtmlReportStyleMixin._format_value(mv, dp, unit)
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
    def _render_analysis(analysis):
        # analysis 可能是 HTML 或纯文本
        # 简单做一下安全处理：去掉 script 标签
        safe = re.sub(r'<script[^>]*>.*?</script>', '', analysis, flags=re.IGNORECASE | re.DOTALL)
        return f"""
<section class="section">
  <h2 class="section-title">分析结论</h2>
  <div class="analysis-content">{safe}</div>
</section>"""