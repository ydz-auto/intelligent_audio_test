# -*- coding: utf-8 -*-
"""报告聚合统计 — 导出 Mixin（P4-5 大文件拆分）。

职责：构建导出数据及 Excel/PDF/CSV 文件载荷（供 handle_export_reports 调用）。
"""
from __future__ import annotations


class _AggregationExportMixin:
    """导出 Mixin：报告导出数据构建与多格式文件载荷生成。"""

    # ==================================================================
    # 导出数据处理（供 handle_export_reports 调用）
    # ==================================================================

    @staticmethod
    def build_export_data(report_ids: list, repository) -> list:
        """查询指定报告及其摘要信息，构建导出数据列表。"""
        export_data = []
        for rid in report_ids:
            try:
                aggregate = repository.get_by_id(int(rid))
                if aggregate is None:
                    continue
                summaries = repository.load_summaries(int(rid))
            except Exception:
                continue

            summary_info = summaries[0].metadata if summaries else {}
            if summary_info:
                total_cases = summary_info.get('total_cases') or 0
                pass_rate = summary_info.get('pass_rate') or 0
            else:
                total_cases = 0
                pass_rate = 0

            gen_time = _AggregationExportMixin._format_generation_time(aggregate.created_at)

            export_data.append({
                "报告ID": str(aggregate.id),
                "报告名称": aggregate.config.get('name') if aggregate.config else None,
                "报告类型": aggregate.report_type,
                "生成时间": gen_time,
                "总用例数": str(total_cases),
                "成功率": f"{pass_rate}%",
                "分析结论": (aggregate.config.get('analysis') if aggregate.config else None) or "无"
            })
        return export_data if export_data else None

    @staticmethod
    def _format_generation_time(created_at) -> str:
        """格式化报告生成时间。"""
        if not created_at:
            return "N/A"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return "N/A"

    @staticmethod
    def build_export_payload(export_data: list, format_type: str) -> dict:
        """根据格式类型构建导出响应，返回包含 base64 编码文件内容的字典。"""
        import base64
        import io as _io
        from shared.utils.query_utils import now_cst

        if format_type == 'excel':
            return _AggregationExportMixin._build_excel_payload(export_data, _io, base64, now_cst)
        elif format_type == 'pdf':
            return _AggregationExportMixin._build_pdf_payload(export_data, _io, base64, now_cst)
        else:
            return _AggregationExportMixin._build_csv_payload(export_data, _io, base64, now_cst)

    @staticmethod
    def _build_excel_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 Excel 导出响应。"""
        import pandas as pd
        df = pd.DataFrame(export_data)
        output = _io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='报告')
        output.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.xlsx"
        mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return {
            'filename': filename,
            'format': 'excel',
            'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
        }

    @staticmethod
    def _build_pdf_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 PDF 导出响应。"""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        output = _io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(A4))
        elements = []

        data = [list(export_data[0].keys())]
        for item in export_data:
            data.append(list(item.values()))

        table = Table(data)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        output.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.pdf"
        mime_type = 'application/pdf'
        return {
            'filename': filename,
            'format': 'pdf',
            'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
        }

    @staticmethod
    def _build_csv_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 CSV 导出响应。"""
        buf = _io.BytesIO()
        buf.write('\ufeff'.encode('utf-8-sig'))
        headers = list(export_data[0].keys())
        buf.write((",".join(headers) + "\n").encode('utf-8-sig'))
        for row in export_data:
            csv_row = [row[h] for h in headers]
            csv_row = [f'"{r}"' if ',' in str(r) else str(r) for r in csv_row]
            buf.write((",".join(csv_row) + "\n").encode('utf-8-sig'))
        buf.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.csv"
        mime_type = 'text/csv'
        return {
            'filename': filename,
            'format': 'csv',
            'content_base64': base64.b64encode(buf.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
        }
