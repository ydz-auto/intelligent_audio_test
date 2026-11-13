# -*- coding: utf-8 -*-
"""Report Studio 导出渲染（INT-2471，设计文档 §15.6）。

同一份受控 Markdown（Studio 文档版本快照）渲染为四种产物：

- ``md``：原样字节（内容源即版本快照，不二次加工）；
- ``html``：受控 Markdown 子集 → HTML（模型输出按不可信内容处理，全部转义，
  不执行任何脚本）；
- ``pdf``：reportlab 排版（A4、中文字体走 reportlab 内置 CID 字体 STSong-Light，
  无需外部字体文件）；
- ``pptx``：python-pptx 生成幻灯片（标题页 + 按 H1/H2 分节的内容页 + 表格）。

渲染是**确定性**的：只做 Markdown 结构到格式的转换，不重新计算任何指标、
不执行模型给出的 JS/SQL/URL，也不回源报告数据（数值以文档正文为准，文档正文
由 ``report_query`` 取数后写入并由用户审批）。

依赖：reportlab 已在 requirements（平台既有 PDF 导出）；python-pptx 是本卡
新增（requirements.txt「Report Generation」段）。缺依赖时抛
:class:`ExportRenderError`，由导出作业落 ``failed`` + 可读原因，不静默成功。
"""
from __future__ import annotations

import html
import io
from typing import Dict, List, Tuple

from shared.models.common_enums import DEFAULT_EXPORT_THEME, StudioExportFormat

# 导出格式 → (扩展名, MIME)。单一事实源，download 侧与作业落盘共用。
EXPORT_MEDIA_TYPES: Dict[str, Tuple[str, str]] = {
    StudioExportFormat.MD.value: ('.md', 'text/markdown'),
    StudioExportFormat.HTML.value: ('.html', 'text/html'),
    StudioExportFormat.PDF.value: ('.pdf', 'application/pdf'),
    StudioExportFormat.PPTX.value: (
        '.pptx',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
}

# PDF 中文字体：reportlab 内置 CID 字体（不需要安装字体文件，主流阅读器可显示）
PDF_CJK_FONT = 'STSong-Light'
PDF_FALLBACK_FONT = 'Helvetica'
PDF_PAGE_MARGIN_MM = 18
PDF_TABLE_MAX_ROWS = 400

# PPTX 版式口径（16:9）
PPTX_SLIDE_WIDTH_EMU = 12192000   # 13.333 in
PPTX_SLIDE_HEIGHT_EMU = 6858000   # 7.5 in
PPTX_FONT_NAME = 'Microsoft YaHei'
PPTX_MAX_TABLE_ROWS = 12
PPTX_BODY_TOP_EMU = 1500000
PPTX_BODY_LEFT_EMU = 600000
PPTX_BODY_WIDTH_EMU = 10992000
PPTX_BODY_HEIGHT_EMU = 4600000


class ExportRenderError(ValueError):
    """导出渲染失败（格式不支持 / 依赖缺失 / 排版异常），消息可直接给用户看。"""


# ---------------------------------------------------------------- Markdown 解析


def _is_table_separator(line: str) -> bool:
    """表格分隔行（``| --- | :---: |``）判定。"""
    stripped = line.strip()
    if not stripped.startswith('|'):
        return False
    cells = (stripped.replace('|', '').replace(':', '')
             .replace('-', '').replace(' ', ''))
    return cells == ''


def _split_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def parse_markdown(markdown: str) -> List[dict]:
    """把 Markdown 子集解析成块列表（HTML / PDF / PPTX 三种渲染器共用）。

    块形状（稳定契约）：
    - ``{'kind': 'heading', 'level': 1..4, 'text': str}``
    - ``{'kind': 'paragraph', 'text': str}``
    - ``{'kind': 'bullet', 'text': str}``
    - ``{'kind': 'code', 'text': str}``
    - ``{'kind': 'table', 'headers': [...], 'rows': [[...]]}``
    - ``{'kind': 'rule'}``
    """
    lines = (markdown or '').splitlines()
    blocks: List[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('```'):
            i += 1
            code_lines: List[str] = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏（缺失时按文件末尾处理）
            blocks.append({'kind': 'code', 'text': '\n'.join(code_lines)})
            continue
        if not stripped:
            i += 1
            continue
        if stripped == '---':
            blocks.append({'kind': 'rule'})
            i += 1
            continue
        if stripped.startswith('#### '):
            blocks.append({'kind': 'heading', 'level': 4,
                           'text': stripped[5:].strip()})
            i += 1
            continue
        if stripped.startswith('### '):
            blocks.append({'kind': 'heading', 'level': 3,
                           'text': stripped[4:].strip()})
            i += 1
            continue
        if stripped.startswith('## '):
            blocks.append({'kind': 'heading', 'level': 2,
                           'text': stripped[3:].strip()})
            i += 1
            continue
        if stripped.startswith('# '):
            blocks.append({'kind': 'heading', 'level': 1,
                           'text': stripped[2:].strip()})
            i += 1
            continue
        if stripped.startswith('|') and i + 1 < len(lines) \
                and _is_table_separator(lines[i + 1]):
            headers = _split_row(stripped)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append({'kind': 'table', 'headers': headers, 'rows': rows})
            continue
        if stripped.startswith('- ') or stripped.startswith('* '):
            blocks.append({'kind': 'bullet', 'text': stripped[2:].strip()})
            i += 1
            continue
        blocks.append({'kind': 'paragraph', 'text': stripped})
        i += 1
    return blocks


def _plain(text: str) -> str:
    """去掉行内强调标记（PPTX / 纯文本口径）。"""
    return (text or '').replace('**', '').replace('__', '')


def _inline_html(text: str) -> str:
    """转义后加行内粗体 / 斜体（先转义，标签只由渲染器产生）。"""
    escaped = html.escape(text or '')
    escaped = escaped.replace('**', '<strong>', 1).replace('**', '</strong>', 1)
    escaped = escaped.replace('__', '<em>', 1).replace('__', '</em>', 1)
    return escaped


# ---------------------------------------------------------------- HTML


_HTML_CSS = (
    '.report-studio-export{font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
    'max-width:860px;margin:0 auto;padding:24px;line-height:1.6;}'
    'table{border-collapse:collapse;width:100%;margin:8px 0;}'
    'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}'
    'pre{background:#f5f5f5;padding:10px;border-radius:4px;overflow-x:auto;}'
    'code{background:#f5f5f5;padding:1px 4px;border-radius:3px;}')


def render_html(markdown: str, theme: str, title: str) -> bytes:
    """受控 Markdown → HTML（全部文本转义；无脚本、无外链资源）。"""
    out: List[str] = []
    in_list = False
    for block in parse_markdown(markdown):
        kind = block['kind']
        if kind != 'bullet' and in_list:
            out.append('</ul>')
            in_list = False
        if kind == 'heading':
            level = int(block['level'])
            out.append(f'<h{level}>{_inline_html(block["text"])}</h{level}>')
        elif kind == 'paragraph':
            out.append(f'<p>{_inline_html(block["text"])}</p>')
        elif kind == 'bullet':
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{_inline_html(block["text"])}</li>')
        elif kind == 'code':
            out.append('<pre><code>' + html.escape(block['text']) + '</code></pre>')
        elif kind == 'rule':
            out.append('<hr/>')
        elif kind == 'table':
            head = ''.join(f'<th>{_inline_html(cell)}</th>'
                           for cell in block['headers'])
            rows = ''.join(
                '<tr>' + ''.join(f'<td>{_inline_html(cell)}</td>' for cell in row)
                + '</tr>'
                for row in block['rows'])
            out.append(f'<table><thead><tr>{head}</tr></thead>'
                       f'<tbody>{rows}</tbody></table>')
    if in_list:
        out.append('</ul>')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        f'<title>{html.escape(title or "")}</title><style>{_HTML_CSS}</style>'
        '</head><body class="report-studio-export">'
        f'<h1>{html.escape(title or "")}</h1>'
        f'<p class="export-theme">主题：{html.escape(theme or DEFAULT_EXPORT_THEME)}</p>'
        + ''.join(out) + '</body></html>'
    ).encode('utf-8')


# ---------------------------------------------------------------- PDF


_PDF_FONT_CACHE: Dict[str, str] = {}


def _pdf_font() -> str:
    """注册并返回 PDF 正文字体（CID 中文字体优先，失败回退 Helvetica）。"""
    if PDF_CJK_FONT in _PDF_FONT_CACHE:
        return _PDF_FONT_CACHE[PDF_CJK_FONT]
    font = PDF_FALLBACK_FONT
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_CJK_FONT))
        font = PDF_CJK_FONT
    except Exception:  # pragma: no cover - 依赖缺失时回退拉丁字体
        font = PDF_FALLBACK_FONT
    _PDF_FONT_CACHE[PDF_CJK_FONT] = font
    return font


def render_pdf(markdown: str, theme: str, title: str) -> bytes:
    """受控 Markdown → PDF（reportlab 排版，中文字体 STSong-Light）。"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate,
            Spacer, Table, TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - 容器缺依赖
        raise ExportRenderError(f'PDF 渲染依赖缺失：{exc}') from exc

    font = _pdf_font()
    base = ParagraphStyle('body', fontName=font, fontSize=10.5, leading=15,
                          spaceAfter=4)
    title_style = ParagraphStyle('title', parent=base, fontSize=20, leading=26,
                                 spaceAfter=10)
    heading_styles = {
        1: ParagraphStyle('h1', parent=base, fontSize=16, leading=21,
                          spaceBefore=10, spaceAfter=6),
        2: ParagraphStyle('h2', parent=base, fontSize=13.5, leading=18,
                          spaceBefore=8, spaceAfter=4),
        3: ParagraphStyle('h3', parent=base, fontSize=12, leading=16,
                          spaceBefore=6, spaceAfter=3),
        4: ParagraphStyle('h4', parent=base, fontSize=11, leading=15,
                          spaceBefore=4, spaceAfter=2),
    }
    code_style = ParagraphStyle('code', parent=base, fontName=font, fontSize=8.5,
                                leading=12, backColor=colors.HexColor('#f5f5f5'))

    def _para(text: str, style=None) -> Paragraph:
        escaped = html.escape(text or '')
        return Paragraph(escaped, style or base)

    story = [Paragraph(html.escape(title or ''), title_style),
             Paragraph(f'主题：{html.escape(theme or DEFAULT_EXPORT_THEME)}', base),
             Spacer(1, 4)]
    pending_bullets: List[str] = []

    def _flush_bullets() -> None:
        if not pending_bullets:
            return
        story.append(ListFlowable(
            [ListItem(_para(item), leftIndent=12) for item in pending_bullets],
            bulletType='bullet', start='•', leftIndent=14))
        pending_bullets.clear()

    for block in parse_markdown(markdown):
        kind = block['kind']
        if kind != 'bullet':
            _flush_bullets()
        if kind == 'heading':
            level = min(int(block['level']), 4)
            story.append(_para(block['text'], heading_styles[level]))
        elif kind == 'paragraph':
            story.append(_para(block['text']))
        elif kind == 'bullet':
            pending_bullets.append(block['text'])
        elif kind == 'code':
            story.append(Preformatted(block['text'], code_style))
            story.append(Spacer(1, 4))
        elif kind == 'rule':
            story.append(Spacer(1, 6))
        elif kind == 'table':
            truncated = len(block['rows']) > PDF_TABLE_MAX_ROWS
            rows = [block['headers']] + block['rows'][:PDF_TABLE_MAX_ROWS]
            data = [[_para(str(cell)) for cell in row] for row in rows]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9ecef')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#adb5bd')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            # 超长表格截断要注明（与 PPTX 口径一致），不静默丢行（复审 P3-3）
            if truncated:
                story.append(Paragraph(
                    f'（表格超过 {PDF_TABLE_MAX_ROWS} 行已截断，完整数据见 HTML/MD 产物）',
                    base))
            story.append(Spacer(1, 6))
    _flush_bullets()

    output = io.BytesIO()
    try:
        SimpleDocTemplate(
            output, pagesize=A4,
            leftMargin=PDF_PAGE_MARGIN_MM * mm,
            rightMargin=PDF_PAGE_MARGIN_MM * mm,
            topMargin=PDF_PAGE_MARGIN_MM * mm,
            bottomMargin=PDF_PAGE_MARGIN_MM * mm,
            title=title or '', author='Report Studio',
        ).build(story)
    except Exception as exc:  # pragma: no cover - 排版异常按作业失败
        raise ExportRenderError(f'PDF 排版失败：{exc}') from exc
    return output.getvalue()


# ---------------------------------------------------------------- PPTX


def _pptx_sections(blocks: List[dict]) -> List[Tuple[str, List[dict]]]:
    """按 H1 / H2 切分成幻灯片段落；没有标题时只有一节（标题=文档标题）。"""
    sections: List[Tuple[str, List[dict]]] = []
    current_title: str = ''
    current: List[dict] = []
    for block in blocks:
        if block['kind'] == 'heading' and int(block['level']) <= 2:
            if current_title or current:
                sections.append((current_title, current))
            current_title = block['text']
            current = []
            continue
        current.append(block)
    if current_title or current:
        sections.append((current_title, current))
    return sections


def render_pptx(markdown: str, theme: str, title: str) -> bytes:
    """受控 Markdown → PPTX（python-pptx；标题页 + 按 H1/H2 分节）。

    不嵌入外部图片 / 脚本；表格超过 ``PPTX_MAX_TABLE_ROWS`` 行时截断并注明。
    """
    try:
        from pptx import Presentation
        from pptx.util import Emu, Pt
    except ImportError as exc:  # pragma: no cover - 容器缺依赖
        raise ExportRenderError(
            'PPTX 渲染依赖缺失（python-pptx 未安装）；'
            f'请确认 requirements.txt 已安装后重试：{exc}') from exc

    blocks = parse_markdown(markdown)
    presentation = Presentation()
    presentation.slide_width = Emu(PPTX_SLIDE_WIDTH_EMU)
    presentation.slide_height = Emu(PPTX_SLIDE_HEIGHT_EMU)
    title_layout = presentation.slide_layouts[0]
    content_layout = presentation.slide_layouts[5]  # 仅标题

    cover = presentation.slides.add_slide(title_layout)
    cover.shapes.title.text = title or '报告'
    subtitle = cover.placeholders[1]
    subtitle.text = f'主题：{theme or DEFAULT_EXPORT_THEME}'

    def _add_text_frame(slide, blocks_for_slide: List[dict]) -> None:
        box = slide.shapes.add_textbox(
            Emu(PPTX_BODY_LEFT_EMU), Emu(PPTX_BODY_TOP_EMU),
            Emu(PPTX_BODY_WIDTH_EMU), Emu(PPTX_BODY_HEIGHT_EMU))
        frame = box.text_frame
        frame.word_wrap = True
        first = True
        for block in blocks_for_slide:
            kind = block['kind']
            if kind in ('heading', 'paragraph', 'bullet'):
                paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
                first = False
                paragraph.text = _plain(block['text'])
                paragraph.font.size = Pt(14)
                paragraph.font.name = PPTX_FONT_NAME
                if kind == 'heading':
                    paragraph.font.bold = True
                    paragraph.font.size = Pt(16)
                elif kind == 'bullet':
                    paragraph.level = 1
            elif kind == 'code':
                paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
                first = False
                paragraph.text = block['text']
                paragraph.font.size = Pt(10)
                paragraph.font.name = 'Consolas'
            elif kind == 'table':
                rows = [block['headers']] + block['rows']
                truncated = len(rows) - 1 > PPTX_MAX_TABLE_ROWS
                rows = rows[:PPTX_MAX_TABLE_ROWS + 1]
                row_count = max(len(rows), 1)
                col_count = max(len(rows[0]), 1)
                height = Emu(300000 * row_count)
                table_shape = slide.shapes.add_table(
                    row_count, col_count, Emu(PPTX_BODY_LEFT_EMU),
                    Emu(PPTX_BODY_TOP_EMU + 300000),
                    Emu(PPTX_BODY_WIDTH_EMU), height)
                table = table_shape.table
                for r, row in enumerate(rows):
                    for c in range(col_count):
                        value = row[c] if c < len(row) else ''
                        cell = table.cell(r, c)
                        cell.text = _plain(value)
                        for paragraph in cell.text_frame.paragraphs:
                            paragraph.font.size = Pt(10)
                            paragraph.font.name = PPTX_FONT_NAME
                if truncated:
                    paragraph = frame.add_paragraph()
                    paragraph.text = (
                        f'（表格超过 {PPTX_MAX_TABLE_ROWS} 行已截断，完整数据见 HTML/PDF 产物）')
                    paragraph.font.size = Pt(10)

    sections = _pptx_sections(blocks)
    if not sections:
        sections = [('', [])]
    for section_title, section_blocks in sections:
        slide = presentation.slides.add_slide(content_layout)
        if section_title:
            slide.shapes.title.text = section_title
            slide.shapes.title.text_frame.paragraphs[0].font.name = PPTX_FONT_NAME
        else:
            slide.shapes.title.text = title or '报告'
        _add_text_frame(slide, section_blocks)

    output = io.BytesIO()
    try:
        presentation.save(output)
    except Exception as exc:  # pragma: no cover - 保存异常按作业失败
        raise ExportRenderError(f'PPTX 生成失败：{exc}') from exc
    return output.getvalue()


# ---------------------------------------------------------------- 入口


def render_export(markdown: str, fmt: str, theme: str, title: str
                  ) -> Tuple[bytes, str, str]:
    """按格式渲染导出产物 → ``(内容, 扩展名, MIME)``；失败抛 ExportRenderError。"""
    try:
        fmt_value = StudioExportFormat(str(fmt or '').strip().lower()).value
    except ValueError:
        supported = ' / '.join(f.value for f in StudioExportFormat)
        raise ExportRenderError(f'不支持的导出格式：{fmt}（仅支持 {supported}）')
    ext, mime = EXPORT_MEDIA_TYPES[fmt_value]
    body = markdown or ''
    if fmt_value == StudioExportFormat.MD.value:
        return body.encode('utf-8'), ext, mime
    if fmt_value == StudioExportFormat.HTML.value:
        return render_html(body, theme, title), ext, mime
    if fmt_value == StudioExportFormat.PDF.value:
        return render_pdf(body, theme, title), ext, mime
    return render_pptx(body, theme, title), ext, mime


__all__ = [
    'EXPORT_MEDIA_TYPES', 'ExportRenderError', 'PDF_CJK_FONT',
    'parse_markdown', 'render_export', 'render_html', 'render_pdf',
    'render_pptx',
]
