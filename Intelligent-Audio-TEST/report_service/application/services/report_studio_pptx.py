# -*- coding: utf-8 -*-
"""Report Studio PPTX 渲染（汇报版式）。

视觉规范来自内置技能 ``skills/work-report-ppt``（红白灰、16:9、大标题、少装饰）。
输入是 ``parse_markdown`` 的受控块列表：``##`` 标题切页，正文只放段落 / 列表 /
表格 / 代码块；不嵌入图片、图表与脚本。

版式要点：
- 封面：kicker + 大标题 + 主题 / 日期；
- 内容页：26–30pt 结论式标题 + 15pt 正文，按版面容量自动续页；
- 表格：独立成页，表头浅灰底、无花哨表格样式，超过单页容量自动续页；
- 页脚：品牌 + 页码；全部可编辑（原生文本框 / 表格）。
"""
from __future__ import annotations

import io
from datetime import date
from typing import Dict, List, Tuple

from shared.models.common_enums import DEFAULT_EXPORT_THEME

# 设计 token：红白灰，禁止阴影 / 渐变 / 装饰图标
ACCENT_HEX = 'C00203'
INK_HEX = '333333'
MUTED_HEX = '999999'
SURFACE_HEX = 'F2F2F2'
FONT_NAME = 'Microsoft YaHei'
CODE_FONT_NAME = 'Consolas'

SLIDE_WIDTH_EMU = 12192000   # 13.333 in
SLIDE_HEIGHT_EMU = 6858000   # 7.5 in
MARGIN_IN = 0.6
CONTENT_WIDTH_IN = 12.133
TITLE_PT = 28
SECTION_TITLE_PT = 26
MODULE_TITLE_PT = 18
BODY_PT = 15
SMALL_PT = 12
FOOTER_PT = 10
MAX_TEXT_UNITS = 12
MAX_TABLE_ROWS = 12
TABLE_STYLE_NONE = '{2D5ABB26-0587-4C30-8999-92F81FD0307C}'


def _plain(text: str) -> str:
    """去 Markdown 强调符（PPTX 里由字体样式表达，不保留 ** / __ 原文）。"""
    return (text or '').replace('**', '').replace('__', '')


def _sections(blocks: List[dict]) -> List[Tuple[str, List[dict]]]:
    """按 H1 / H2 切分页面；没有标题时整篇一页。"""
    sections: List[Tuple[str, List[dict]]] = []
    title = ''
    current: List[dict] = []
    for block in blocks:
        if block['kind'] == 'heading' and int(block['level']) <= 2:
            if title or current:
                sections.append((title, current))
            title = block['text']
            current = []
            continue
        current.append(block)
    if title or current:
        sections.append((title, current))
    return sections


def _text_units(block: dict) -> float:
    """粗略版面容量单位：12 单位约等于一页正文区。"""
    kind = block['kind']
    text = str(block.get('text') or '')
    if kind == 'heading':
        return 1.8
    if kind == 'paragraph':
        return 1.2 + len(text) // 70
    if kind == 'bullet':
        return 1.0 + len(text) // 70
    if kind == 'code':
        return max(1.0, 0.62 * (text.count('\n') + 1))
    return 1.0


def _paginate(blocks: List[dict]) -> List[List[dict]]:
    pages: List[List[dict]] = []
    current: List[dict] = []
    units = 0.0
    for block in blocks:
        if block['kind'] in ('rule', 'table'):
            continue
        size = _text_units(block)
        if current and units + size > MAX_TEXT_UNITS:
            pages.append(current)
            current = []
            units = 0.0
        current.append(block)
        units += size
    if current:
        pages.append(current)
    return pages


def render_pptx(blocks: List[dict], theme: str, title: str) -> bytes:
    """受控 Markdown 块 → 汇报版 PPTX（16:9，可编辑原生元素）。"""
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.enum.text import MSO_ANCHOR
        from pptx.oxml.ns import qn
        from pptx.util import Emu, Inches, Pt
    except ImportError as exc:  # pragma: no cover - 容器缺依赖
        raise ImportError(
            'PPTX 渲染依赖缺失（python-pptx 未安装）；'
            f'请确认 requirements.txt 已安装后重试：{exc}') from exc

    def rgb(value: str):
        return RGBColor.from_string(value)

    def style(paragraph, text: str, *, size: float, color: str = INK_HEX,
              bold: bool = False, font: str = FONT_NAME,
              before: int = 0, after: int = 6, line: float = 1.2) -> None:
        paragraph.text = text
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.name = font
        paragraph.font.color.rgb = rgb(color)
        paragraph.space_before = Pt(before)
        paragraph.space_after = Pt(after)
        paragraph.line_spacing = line

    def box(slide, left: float, top: float, width: float, height: float):
        shape = slide.shapes.add_textbox(
            Inches(left), Inches(top), Inches(width), Inches(height))
        frame = shape.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        return frame

    def footer(slide, page: int) -> None:
        frame = box(slide, MARGIN_IN, 7.02, 6.0, 0.3)
        style(frame.paragraphs[0], 'Report Studio · 数据来自平台报告',
              size=FOOTER_PT, color=MUTED_HEX)
        frame = box(slide, 11.55, 7.02, 1.18, 0.3)
        paragraph = frame.paragraphs[0]
        style(paragraph, str(page), size=FOOTER_PT, color=MUTED_HEX,
              after=0)
        paragraph.alignment = 2  # 右对齐

    def header(slide, section_title: str) -> None:
        rule = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(MARGIN_IN), Inches(1.42),
            Inches(CONTENT_WIDTH_IN), Inches(0.018))
        rule.fill.solid()
        rule.fill.fore_color.rgb = rgb(SURFACE_HEX)
        rule.line.fill.background()
        frame = box(slide, MARGIN_IN, 0.58, CONTENT_WIDTH_IN, 0.75)
        style(frame.paragraphs[0], section_title, size=SECTION_TITLE_PT,
              color=INK_HEX, bold=True, after=0, line=1.05)

    def body(slide, page_blocks: List[dict]) -> None:
        frame = box(slide, MARGIN_IN, 1.82, CONTENT_WIDTH_IN, 4.9)
        first = True
        for block in page_blocks:
            kind = block['kind']
            if kind == 'code':
                for line in (str(block.get('text') or '').splitlines() or ['']):
                    paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
                    first = False
                    style(paragraph, line, size=11, color=MUTED_HEX,
                          font=CODE_FONT_NAME, after=0, line=1.15)
                continue
            if kind not in ('heading', 'paragraph', 'bullet'):
                continue
            paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
            first = False
            text = _plain(block['text'])
            if kind == 'heading':
                style(paragraph, text, size=MODULE_TITLE_PT, bold=True,
                      before=6, after=6)
            elif kind == 'bullet':
                style(paragraph, f'•  {text}', size=BODY_PT, after=8, line=1.25)
            else:
                style(paragraph, text, size=BODY_PT, after=8, line=1.3)

    def strip_table_style(table_shape) -> None:
        """去掉 Office 默认蓝色表格样式：只保留我们自己设的浅灰表头。"""
        tbl = table_shape._element.graphic.graphicData.tbl
        tbl_pr = tbl.tblPr
        for element in tbl_pr.findall(qn('a:tableStyleId')):
            tbl_pr.remove(element)
        element = tbl_pr.makeelement(qn('a:tableStyleId'), {})
        element.text = TABLE_STYLE_NONE
        tbl_pr.append(element)

    def table_slide(prs, section_title: str, block: dict, index: int,
                    total: int, page: int):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        suffix = f'（{index}/{total}）' if total > 1 else ''
        header(slide, f'{section_title}{suffix}')
        rows = [block['headers']] + block['rows']
        col_count = max(len(rows[0]), 1)
        shape = slide.shapes.add_table(
            len(rows), col_count, Inches(MARGIN_IN), Inches(1.82),
            Inches(CONTENT_WIDTH_IN), Inches(0.4 * len(rows)))
        strip_table_style(shape)
        table = shape.table
        weights: List[int] = []
        for column in range(col_count):
            width = max(len(str(row[column])) for row in rows
                        if column < len(row)) or 6
            weights.append(max(6, min(width, 42)))
        total_weight = sum(weights)
        for column, weight in enumerate(weights):
            table.columns[column].width = Emu(
                int(Inches(CONTENT_WIDTH_IN) * weight / total_weight))
        for row_index, row in enumerate(rows):
            table.rows[row_index].height = Inches(0.38 if row_index == 0 else 0.32)
            for column in range(col_count):
                value = str(row[column]) if column < len(row) else ''
                cell = table.cell(row_index, column)
                cell.text = _plain(value)
                cell.margin_left = cell.margin_right = Inches(0.08)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(
                    SURFACE_HEX if row_index == 0 else 'FFFFFF')
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.font.size = Pt(11 if row_index == 0 else 10.5)
                    paragraph.font.bold = row_index == 0
                    paragraph.font.name = FONT_NAME
                    paragraph.font.color.rgb = rgb(INK_HEX)
        footer(slide, page)

    presentation = Presentation()
    presentation.slide_width = Emu(SLIDE_WIDTH_EMU)
    presentation.slide_height = Emu(SLIDE_HEIGHT_EMU)
    blank = presentation.slide_layouts[6]

    # 封面：kicker + 大标题 + 红色短线 + 主题 / 日期
    cover = presentation.slides.add_slide(blank)
    frame = box(cover, MARGIN_IN, 0.78, 8.0, 0.4)
    style(frame.paragraphs[0], 'REPORT STUDIO · 测试报告',
          size=SMALL_PT, color=ACCENT_HEX, bold=True, after=0)
    frame = box(cover, MARGIN_IN, 2.15, CONTENT_WIDTH_IN, 1.9)
    style(frame.paragraphs[0], _plain(title) or '报告',
          size=TITLE_PT, bold=True, after=0, line=1.05)
    rule = cover.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(MARGIN_IN), Inches(4.22),
        Inches(1.15), Inches(0.055))
    rule.fill.solid()
    rule.fill.fore_color.rgb = rgb(ACCENT_HEX)
    rule.line.fill.background()
    frame = box(cover, MARGIN_IN, 4.45, 8.0, 0.4)
    style(frame.paragraphs[0],
          f'主题：{theme or DEFAULT_EXPORT_THEME}    ·    {date.today().isoformat()}',
          size=SMALL_PT, color=MUTED_HEX, after=0)
    footer(cover, 1)

    page_number = 2
    sections = _sections(blocks)
    for section_title, section_blocks in sections:
        text_pages = _paginate(section_blocks)
        for index, page_blocks in enumerate(text_pages, start=1):
            slide = presentation.slides.add_slide(blank)
            title_text = section_title or (_plain(title) or '报告')
            if len(text_pages) > 1:
                title_text = f'{title_text}（{index}/{len(text_pages)}）'
            header(slide, title_text)
            body(slide, page_blocks)
            footer(slide, page_number)
            page_number += 1
        for block in section_blocks:
            if block['kind'] != 'table':
                continue
            rows = block['rows']
            chunks = [rows[i:i + MAX_TABLE_ROWS]
                      for i in range(0, max(len(rows), 1), MAX_TABLE_ROWS)]
            for index, chunk in enumerate(chunks, start=1):
                table_slide(presentation, section_title or (_plain(title) or '报告'),
                            {'headers': block['headers'], 'rows': chunk},
                            index, len(chunks), page_number)
                page_number += 1

    output = io.BytesIO()
    try:
        presentation.save(output)
    except Exception as exc:  # pragma: no cover - 保存异常按作业失败
        raise RuntimeError(f'PPTX 生成失败：{exc}') from exc
    return output.getvalue()


__all__ = ['render_pptx']
