# -*- coding: utf-8 -*-
"""HTML 报告渲染器 —— 样式与格式化 Mixin。

从 html_report_renderer.py 拆分而来，承载：
- _get_styles: 自包含 HTML 的内联 CSS
- _format_value: 数值格式化辅助
"""
import html


class HtmlReportStyleMixin:
    """样式（CSS）与数值格式化辅助，供 HtmlReportRenderer 组合复用。"""

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
