from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

def set_font(run, size, color='334155', bold=False):
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.bold = bold
    run.font.name = 'Microsoft YaHei'
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', '微软雅黑')

def add_text_box(slide, x, y, w, h, lines, size=10, color='475569', bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Pt(2); tf.margin_right = Pt(2)
    tf.margin_top = Pt(1); tf.margin_bottom = Pt(1)
    if isinstance(lines, str):
        lines = [lines]
    for i, text in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(0); p.space_before = Pt(0)
        if line_spacing != 1.0: p.line_spacing = line_spacing
        r = p.add_run(); r.text = text
        set_font(r, size, color, bold)
    return tb

def add_rect(slide, x, y, w, h, fill='ffffff', line=None, line_w=1.0, shape=MSO_SHAPE.RECTANGLE, radius=None):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.shadow.inherit = False
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = RGBColor.from_string(line)
        sp.line.width = Pt(line_w)
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        try: sp.adjustments[0] = radius
        except: pass
    return sp

def add_rounded_rect(slide, x, y, w, h, fill='ffffff', line=None, line_w=1.0, radius=0.1):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.shadow.inherit = False
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = RGBColor.from_string(line)
        sp.line.width = Pt(line_w)
    try: sp.adjustments[0] = radius
    except: pass
    return sp

def add_circle(slide, x, y, r, fill='6366f1', text='', tsize=10, tcolor='ffffff'):
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(r*2), Inches(r*2))
    sp.shadow.inherit = False
    sp.fill.solid()
    sp.fill.fore_color.rgb = RGBColor.from_string(fill)
    sp.line.fill.background()
    tf = sp.text_frame
    tf.word_wrap = False
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = 0; tf.margin_right = 0
    tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    set_font(r, tsize, tcolor, True)
    return sp

def add_connector(slide, x1, y1, x2, y2, color='94a3b8', width=1.5, arrow=True):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.shadow.inherit = False
    conn.line.color.rgb = RGBColor.from_string(color)
    conn.line.width = Pt(width)
    if arrow:
        ln = conn.line._get_or_add_ln()
        tail = ln.makeelement(qn('a:tailEnd'), {'type': 'triangle', 'w': 'med', 'len': 'med'})
        ln.append(tail)
    return conn

def set_line_dash(shape, val='dash'):
    ln = shape.line._get_or_add_ln()
    d = ln.makeelement(qn('a:prstDash'), {'val': val})
    for child in list(ln):
        if child.tag in (qn('a:round'), qn('a:bevel'), qn('a:miter'), qn('a:headEnd'), qn('a:tailEnd')):
            child.addprevious(d)
            return
    ln.append(d)

def add_step_box(slide, x, y, w, h, num, title, desc1='', desc2='', fill='fef3c7', stroke='f59e0b', num_color='f59e0b'):
    add_rounded_rect(slide, x, y, w, h, fill, stroke, 1.2, 0.08)
    add_circle(slide, x+0.08, y+0.10, 0.12, num_color, str(num), 9, 'ffffff')
    add_text_box(slide, x+0.32, y+0.08, w-0.38, 0.24, [title], 10.5, '1e293b', True, PP_ALIGN.LEFT)
    if desc1:
        add_text_box(slide, x+0.32, y+0.38, w-0.38, 0.24, [desc1], 8.5, '64748b', False, PP_ALIGN.LEFT)
    if desc2:
        add_text_box(slide, x+0.32, y+0.66, w-0.38, 0.24, [desc2], 8.5, '64748b', False, PP_ALIGN.LEFT)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank_layout = prs.slide_layouts[6]  # blank

# ============== SLIDE 1 ==============
slide1 = prs.slides.add_slide(blank_layout)
add_rect(slide1, 0, 0, 13.333, 7.5, 'f1f5f9', line=None)

# Title
add_text_box(slide1, 0.5, 0.22, 12.33, 0.48, ['跨区网络传输方案 · A/B/C 三区链路设计'], 26, '0f172a', True, PP_ALIGN.LEFT)
add_text_box(slide1, 0.5, 0.68, 12.33, 0.30, ['DDD + CQRS + 微服务 + 多站点隔离 · 三区链路设计 · V9.7.31 v1.0'], 11, '64748b', False, PP_ALIGN.LEFT)
add_rect(slide1, 0.5, 1.08, 12.33, 0.015, 'cbd5e1', line=None)

# --- Card 1: 背景与约束 (indigo) ---
C1Y = 1.22
add_rounded_rect(slide1, 0.5, C1Y, 12.33, 1.32, 'eef2ff', '6366f1', 1.4, 0.08)
add_rounded_rect(slide1, 0.5, C1Y, 12.33, 0.32, 'e0e7ff', None)
add_circle(slide1, 0.66, C1Y+0.08, 0.14, '6366f1', '1', 9, 'ffffff')
add_text_box(slide1, 0.90, C1Y+0.06, 11.0, 0.28, ['背景与约束 — 三区网络隔离环境下的跨区协同设计'], 12.5, '3730a3', True, PP_ALIGN.LEFT)

C1IY = C1Y + 0.44  # first card row y
constraints = [
    ('三区网络隔离', 'A↔B 双向过 GW-1 · B→C 单向过 GW-2 · A↔C 经 B 中继过双 GW'),
    ('用例跨区执行', 'A/B/C 均具备执行能力 · 能力有差异 · 用例在其可执行区域执行'),
    ('执行能力分布', 'A/B：完整微服务栈 + 本地评估 · C：仅 THIRD_PARTY_C 评估'),
    ('数据隔离', 'A/B 数据不持久化到 C · C 不反向回连'),
    ('百 MB 级传输', '音频素材 + 采集结果，需分片+校验'),
    ('报告共享', 'C 评估结果需在 A/B 可见，API 响应带回'),
]
cols = [0.70, 4.72, 8.74]
cw = 3.9
for i, (c, d) in enumerate(constraints):
    cx = cols[i % 3]
    cy = C1IY + (i // 3) * 0.46
    add_rounded_rect(slide1, cx, cy, cw, 0.42, 'ffffff', 'c7d2fe', 0.8, 0.06)
    add_text_box(slide1, cx+0.08, cy+0.02, cw-0.16, 0.20, [c], 9.5, '334155', True, PP_ALIGN.LEFT)
    add_text_box(slide1, cx+0.08, cy+0.22, cw-0.16, 0.18, [d], 8.5, '64748b', False, PP_ALIGN.LEFT)

# --- Card 2: 三区拓扑 (amber) ---
C2Y = 2.68
add_rounded_rect(slide1, 0.5, C2Y, 12.33, 2.40, 'fffbeb', 'f59e0b', 1.4, 0.08)
add_rounded_rect(slide1, 0.5, C2Y, 12.33, 0.32, 'fef3c7', None)
add_circle(slide1, 0.66, C2Y+0.08, 0.14, 'f59e0b', '2', 9, 'ffffff')
add_text_box(slide1, 0.90, C2Y+0.06, 11.0, 0.28, ['三区拓扑 — A（主站点）· B（评估中枢）· C（第三方 LLM API）· 两两链路均过软件网关（A↔C 经 B 中继）'], 12.5, '92400e', True, PP_ALIGN.LEFT)

C2BY = C2Y + 0.56
zone_w = 3.30
zone_h = 1.32

# Zone A (yellow)
add_rounded_rect(slide1, 0.70, C2BY, zone_w, zone_h, 'fef3c7', 'f59e0b', 1.4, 0.06)
add_rounded_rect(slide1, 0.70, C2BY, zone_w, 0.28, 'fbbf24', None)
add_text_box(slide1, 0.70, C2BY+0.02, zone_w, 0.26, ['A 区（主站点）'], 11, '78350f', True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
add_text_box(slide1, 0.84, C2BY+0.34, zone_w-0.14, 0.17, ['11 个微服务（完整栈）'], 9, '1e293b')
add_text_box(slide1, 0.84, C2BY+0.52, zone_w-0.14, 0.17, ['PostgreSQL + Redis'], 9, '1e293b')
add_text_box(slide1, 0.84, C2BY+0.70, zone_w-0.14, 0.17, ['MinIO（本地存储）'], 9, '1e293b')
add_text_box(slide1, 0.84, C2BY+0.88, zone_w-0.14, 0.17, ['transfer_agent (T-A)'], 9, '1e293b', True)
add_rounded_rect(slide1, 0.84, C2BY+1.10, zone_w-0.14, 0.18, 'fde68a', 'd97706', 0.6, 0.04)
add_text_box(slide1, 0.84, C2BY+1.10, zone_w-0.14, 0.18, ['gw 白名单: 5000→B'], 8, '92400e', False, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)

# Zone B (green)
add_rounded_rect(slide1, 4.70, C2BY, zone_w, zone_h, 'f0fdf4', '16a34a', 1.4, 0.06)
add_rounded_rect(slide1, 4.70, C2BY, zone_w, 0.28, '4ade80', None)
add_text_box(slide1, 4.70, C2BY+0.02, zone_w, 0.26, ['B 区（评估中枢）'], 11, '14532d', True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
add_text_box(slide1, 4.84, C2BY+0.34, zone_w-0.14, 0.17, ['11 个微服务（完整栈）'], 9, '1e293b')
add_text_box(slide1, 4.84, C2BY+0.52, zone_w-0.14, 0.17, ['PostgreSQL + Redis'], 9, '1e293b')
add_text_box(slide1, 4.84, C2BY+0.70, zone_w-0.14, 0.17, ['MinIO（本地存储+中转缓存）'], 9, '1e293b')
add_text_box(slide1, 4.84, C2BY+0.88, zone_w-0.14, 0.17, ['transfer_agent (T-B)'], 9, '1e293b', True)
add_rounded_rect(slide1, 4.84, C2BY+1.10, zone_w-0.14, 0.18, 'bbf7d0', '16a34a', 0.6, 0.04)
add_text_box(slide1, 4.84, C2BY+1.10, zone_w-0.14, 0.18, ['中继枢纽 · 校验 + 转发'], 8, '166534', False, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)

# Zone C (blue)
add_rounded_rect(slide1, 8.70, C2BY, zone_w, zone_h, 'eff6ff', '3b82f6', 1.4, 0.06)
add_rounded_rect(slide1, 8.70, C2BY, zone_w, 0.28, '60a5fa', None)
add_text_box(slide1, 8.70, C2BY+0.02, zone_w, 0.26, ['C 区（第三方 LLM API）'], 11, '1e3a5f', True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
add_text_box(slide1, 8.84, C2BY+0.34, zone_w-0.14, 0.17, ['作为被测对象 / 评估 LLM'], 9, '1e293b')
add_text_box(slide1, 8.84, C2BY+0.52, zone_w-0.14, 0.17, ['无持久化存储'], 9, '1e293b')
add_text_box(slide1, 8.84, C2BY+0.70, zone_w-0.14, 0.17, ['不反向回连 A/B'], 9, '1e293b')
add_text_box(slide1, 8.84, C2BY+0.88, zone_w-0.14, 0.17, ['第三方 LLM 评估 API'], 9, '1e293b', True)
add_rounded_rect(slide1, 8.84, C2BY+1.10, zone_w-0.14, 0.18, 'e0e7ff', '6366f1', 0.6, 0.04)
add_text_box(slide1, 8.84, C2BY+1.10, zone_w-0.14, 0.18, ['仅执行 THIRD_PARTY_C 评估用例'], 8, '3730a3', False, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)

# Gateways (drawn after arrows so boxes overlay the lines)
gw_w = 0.26
gw_h = 0.36
gw_y = C2BY + 0.54
for gx, gname in [(4.22, 'GW-1'), (8.22, 'GW-2')]:
    add_rounded_rect(slide1, gx, gw_y, gw_w, gw_h, 'e2e8f0', '94a3b8', 1.0, 0.05)
    add_text_box(slide1, gx, gw_y+0.02, gw_w, gw_h-0.04, [gname], 7, '475569', True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)

# Arrows: every link passes through a GW box (explicit GW⇄zone edges)
ay_top = C2BY + 0.62
ay_bot = C2BY + 0.78
gw1_l, gw1_r = 4.22, 4.48
gw2_l, gw2_r = 8.22, 8.48
# A↔B 双向 over GW-1: A→GW-1→B 与 B→GW-1→A（四段显式箭头）
add_connector(slide1, 4.00, ay_top, gw1_l-0.02, ay_top, '94a3b8', 1.5, True)
add_connector(slide1, gw1_r+0.02, ay_top, 4.70, ay_top, '94a3b8', 1.5, True)
add_connector(slide1, 4.70, ay_bot, gw1_r+0.02, ay_bot, '94a3b8', 1.5, True)
add_connector(slide1, gw1_l-0.02, ay_bot, 4.00, ay_bot, '94a3b8', 1.5, True)
# B→C 单向 over GW-2: B→GW-2→C（两段显式箭头）
add_connector(slide1, 8.00, ay_top, gw2_l-0.02, ay_top, '16a34a', 1.5, True)
add_connector(slide1, gw2_r+0.02, ay_top, 8.70, ay_top, '16a34a', 1.5, True)
add_text_box(slide1, 4.02, C2BY+0.36, 0.60, 0.14, ['A↔B 双向'], 7, '92400e', True, PP_ALIGN.CENTER)
add_text_box(slide1, 8.02, C2BY+0.36, 0.60, 0.14, ['B→C 单向'], 7, '166534', True, PP_ALIGN.CENTER)

# A↔C 经 B 中继: purple dashed logical path under zones (no physical direct link)
ac_purple = '7c3aed'
ac_down = add_connector(slide1, 3.80, C2BY+1.10, 3.80, C2BY+1.52, ac_purple, 1.2, False)
set_line_dash(ac_down)
ac_across = add_connector(slide1, 3.80, C2BY+1.52, 8.90, C2BY+1.52, ac_purple, 1.2, False)
set_line_dash(ac_across)
ac_up = add_connector(slide1, 8.90, C2BY+1.52, 8.90, C2BY+1.10, ac_purple, 1.2, True)
set_line_dash(ac_up)
add_text_box(slide1, 4.15, C2BY+1.55, 4.40, 0.16, ['A↔C 经 B 中继过双 GW（逻辑链路·不直连）'], 8, '7c3aed', True, PP_ALIGN.CENTER)

# --- Card 3: 连通性矩阵 (blue) ---
C3Y = 5.14
add_rounded_rect(slide1, 0.5, C3Y, 12.33, 1.62, 'eff6ff', '3b82f6', 1.4, 0.08)
add_rounded_rect(slide1, 0.5, C3Y, 12.33, 0.32, 'dbeafe', None)
add_circle(slide1, 0.66, C3Y+0.08, 0.14, '3b82f6', '3', 9, 'ffffff')
add_text_box(slide1, 0.90, C3Y+0.06, 11.0, 0.28, ['连通性矩阵 — 三区网络段方向与协议约束'], 12.5, '1e40af', True, PP_ALIGN.LEFT)

C3TY = C3Y + 0.46  # table y
# header
add_rounded_rect(slide1, 0.68, C3TY, 11.93, 0.20, 'bfdbfe', None)
col_pos = [0.85, 2.20, 3.80, 5.20]
for ci, hd in enumerate(['段', '方向', '协议', '说明']):
    add_text_box(slide1, col_pos[ci], C3TY, 1.2, 0.20, [hd], 9, '1e40af', True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

rows_data = [
    ('A ↔ B', '双向', 'HTTPS', 'transfer_agent 端口需网关白名单；A/B 同安全域，数据/报告自由同步', 'f59e0b'),
    ('B → C', '单向请求', 'HTTPS', 'B 的评估服务经 transfer_agent 调 C 第三方 LLM API；请求仅输出，不依赖 C 回调', '16a34a'),
    ('C → A/B', '不通', '—', 'C 不做任何主动推送或回调，所有结果仅随 API 同步响应返回 B', 'dc2626'),
    ('A → C', '经 B 中继', 'HTTPS ×2', '逻辑链路 A→GW-1→B→GW-2→C，物理不直连；B 校验 + 转发', '7c3aed'),
]
for ri, (seg, d, proto, desc, dot) in enumerate(rows_data):
    ry = C3TY + 0.20 + ri * 0.24
    bg = 'ffffff' if ri % 2 == 0 else 'f8fafc'
    add_rect(slide1, 0.68, ry, 11.93, 0.24, bg, 'e2e8f0', 0.5)
    add_circle(slide1, col_pos[0]-0.12, ry+0.04, 0.09, dot, '', 7, 'ffffff')
    add_text_box(slide1, col_pos[0], ry+0.02, 1.2, 0.20, [seg], 9, '1e293b', True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    add_text_box(slide1, col_pos[1], ry+0.02, 1.5, 0.20, [d], 9, '1e293b', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    add_text_box(slide1, col_pos[2], ry+0.02, 1.2, 0.20, [proto], 9, '475569', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    add_text_box(slide1, col_pos[3], ry+0.02, 6.8, 0.20, [desc], 8.5, '64748b', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

# Footer bar
add_rounded_rect(slide1, 0.5, 6.96, 12.33, 0.32, '0f172a', None, 0, 0.06)
add_text_box(slide1, 0.5, 6.96, 12.33, 0.32, ['A/B 完整微服务栈可执行全部用例；C 仅执行 THIRD_PARTY_C 评估用例 · 所有跨区链路均过软件网关（A↔B 过 GW-1 · B→C 过 GW-2 · A↔C 经 B 中继过双 GW）'], 9.5, 'ffffff', False, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)

# ============== SLIDE 2 ==============
slide2 = prs.slides.add_slide(blank_layout)
add_rect(slide2, 0, 0, 13.333, 7.5, 'f1f5f9', line=None)

add_text_box(slide2, 0.5, 0.22, 12.33, 0.48, ['主线方案 · 评估中枢与跨区传输流程'], 26, '0f172a', True, PP_ALIGN.LEFT)
add_text_box(slide2, 0.5, 0.68, 12.33, 0.30, ['评估中枢 · 配置化维度路由 · transfer_agent 传输代理 · EVAL_REQUEST 完整流程 ①→⑧'], 11, '64748b', False, PP_ALIGN.LEFT)
add_rect(slide2, 0.5, 1.08, 12.33, 0.015, 'cbd5e1', line=None)

# --- Card 4: 评估中枢模型 (green) ---
C4Y = 1.22
add_rounded_rect(slide2, 0.5, C4Y, 12.33, 1.63, 'f0fdf4', '16a34a', 1.4, 0.08)
add_rounded_rect(slide2, 0.5, C4Y, 12.33, 0.32, 'dcfce7', None)
add_circle(slide2, 0.66, C4Y+0.08, 0.14, '16a34a', '4', 9, 'ffffff')
add_text_box(slide2, 0.90, C4Y+0.06, 11.0, 0.28, ['评估中枢模型 — 配置化维度路由 + transfer_agent 传输代理（DDD 四层）'], 12.5, '166534', True, PP_ALIGN.LEFT)

C4CY = C4Y + 0.46  # content start
# Registry table
add_text_box(slide2, 0.70, C4CY, 5.2, 0.16, ['评估能力注册表（配置化维度路由）'], 9.5, '14532d', True)

reg_x = 0.70
reg_w = 5.2
reg_header_y = C4CY + 0.18
reg_data = [
    ('wer', 'LOCAL', 'evaluation_service gRPC'),
    ('der', 'LOCAL', 'evaluation_service gRPC'),
    ('llm_judge', 'THIRD_PARTY_C', 'transfer_agent → C LLM API'),
    ('mos', 'THIRD_PARTY_C', 'transfer_agent → C LLM API'),
]
add_rounded_rect(slide2, reg_x, reg_header_y, reg_w, 0.14, 'bbf7d0', None)
for ci, hd in enumerate(['维度', 'target', '路由目标']):
    rx = [0.80, 1.60, 2.85][ci]
    add_text_box(slide2, rx, reg_header_y, 0.8, 0.14, [hd], 8, '166534', True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

for ri, (dim, tgt, route) in enumerate(reg_data):
    ry = reg_header_y + 0.14 + ri * 0.16
    bg = 'ffffff' if ri % 2 == 0 else 'f8fafc'
    add_rect(slide2, reg_x, ry, reg_w, 0.15, bg, 'e2e8f0', 0.3)
    add_text_box(slide2, 0.80, ry, 0.72, 0.15, [dim], 8, '1e293b', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    tcol = '16a34a' if tgt == 'LOCAL' else 'f59e0b'
    add_text_box(slide2, 1.60, ry, 1.20, 0.15, [tgt], 8, tcol, True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    add_text_box(slide2, 2.85, ry, 2.35, 0.15, [route], 8, '475569', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

# transfer_agent DDD structure (right side)
tax = 6.50
add_text_box(slide2, tax, C4CY, 6.0, 0.16, ['transfer_agent（传输代理 · DDD 四层）'], 9.5, '14532d', True)
tay = C4CY + 0.18
layers = [
    ('interfaces/api/', 'receive 收包 · 验签', 'dcfce7', '166534'),
    ('application/services/', '打包 · 分片 · 重试 · 幂等', 'fef3c7', '92400e'),
    ('domain/models/', 'TransferPackage · Status · 签名', 'e0e7ff', '3730a3'),
    ('infrastructure/', 'acl 出站 · storage · 持久化流水', 'fce7f3', '9d174d'),
]
for li, (name, desc, lfill, lcol) in enumerate(layers):
    ly = tay + li * 0.16
    add_rounded_rect(slide2, tax, ly, 5.60, 0.15, lfill, None, 0, 0.04)
    add_text_box(slide2, tax+0.04, ly, 5.52, 0.15, [name + desc], 8, lcol, False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

add_rounded_rect(slide2, 0.70, tay + 0.79, 11.40, 0.16, 'f0fdf4', '86efac', 0.6, 0.04)
add_text_box(slide2, 0.74, tay + 0.79, 11.32, 0.16, ['新增微服务 · 端口注册 shared/config/service_ports.py · proto: shared/proto/transfer_agent.proto · transfer_id 幂等唯一 · HMAC-SHA256 签名 · TTL 3600s'], 8, '166534', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

# --- Card 5: EVAL_REQUEST 流程 (amber) ---
C5Y = 3.18
add_rounded_rect(slide2, 0.5, C5Y, 12.33, 3.57, 'fffbeb', 'f59e0b', 1.4, 0.08)
add_rounded_rect(slide2, 0.5, C5Y, 12.33, 0.32, 'fef3c7', None)
add_circle(slide2, 0.66, C5Y+0.08, 0.14, 'f59e0b', '5', 9, 'ffffff')
add_text_box(slide2, 0.90, C5Y+0.06, 11.0, 0.28, ['EVAL_REQUEST 完整流程 — A 区命中第三方 LLM 评估 → B 中继 → C 第三方 LLM API（被测对象 / 评估 LLM）→ 结果返回 A'], 12.5, '92400e', True, PP_ALIGN.LEFT)

C5CY = C5Y + 0.46

# Step box definitions
bw = 2.70
bgap = (11.93 - 4*bw) / 3
col_x = [0.70, 0.70 + bw + bgap, 0.70 + 2*(bw+bgap), 0.70 + 3*(bw+bgap)]

row1_steps = [
    (1, 'A 区用例执行完成', '评估维度命中', 'THIRD_PARTY_C', 'fef3c7', 'f59e0b', 'f59e0b'),
    (2, '打包 EVAL_REQUEST', 'algorithm_result JSON', '+ 引用音频/结果文件', 'fef3c7', 'f59e0b', 'f59e0b'),
    (3, 'T-A → T-B', '分片并发上传 4MB/片', '签名+token→网关鉴权', 'fef3c7', 'f59e0b', 'f59e0b'),
    (4, 'B 中转·校验', '校验签名+幂等去重', '暂存 transit 桶(TTL)', 'fef3c7', 'f59e0b', 'f59e0b'),
]
row2_steps = [
    (5, 'T-B → C 第三方 LLM API', 'multipart / chunked', '/ presigned PUT', 'f0fdf4', '16a34a', '16a34a'),
    (6, 'C LLM API 处理', '被测对象 / 评估 LLM', '一次性请求-响应·不落 A/B', 'eff6ff', '3b82f6', '3b82f6'),
    (7, 'EVAL_RESULT 返回 B', 'B 评估服务解析', '落 B 区 DB/MinIO', 'f0fdf4', '16a34a', '16a34a'),
    (8, 'EVAL_RESULT 回同步 A', 'T-B→GW-1→T-A', '落 A 区 DB/MinIO', 'fef3c7', 'f59e0b', 'f59e0b'),
]

r1y = C5CY + 0.06
bheight = 1.05
for i, (num, title, d1, d2, fill, stroke, nc) in enumerate(row1_steps):
    add_step_box(slide2, col_x[i], r1y, bw, bheight, num, title, d1, d2, fill, stroke, nc)
    if i < 3:
        add_connector(slide2, col_x[i]+bw, r1y+bheight/2, col_x[i+1], r1y+bheight/2, 'f59e0b', 1.5, True)

d4x = col_x[3] + bw/2
r2y = C5CY + 1.68
add_connector(slide2, d4x, r1y+bheight, d4x, r2y-0.02, 'f59e0b', 1.5, True)

for i, (num, title, d1, d2, fill, stroke, nc) in enumerate(row2_steps):
    ci = 3 - i
    add_step_box(slide2, col_x[ci], r2y, bw, bheight, num, title, d1, d2, fill, stroke, nc)
    if ci > 0 and i < 3:
        add_connector(slide2, col_x[ci], r2y+bheight/2, col_x[ci-1]+bw, r2y+bheight/2, stroke, 1.5, True)

# Note line at bottom
note_y = C5Y + 3.57 - 0.30
add_text_box(slide2, 0.70, note_y, 11.93, 0.20, [
    '包类型：EVAL_REQUEST（评估输入）· EVAL_RESULT（同步响应）· REPORT_SYNC（报告同步）· DATA_SYNC（数据同步）· transfer_id 幂等唯一 · HMAC-SHA256 签名 · TTL 3600s · ephemeral true'
], 8, '64748b', False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)

# Footer
add_text_box(slide2, 0.5, 7.30, 12.33, 0.18, ['V9.7.31 · 跨区网络传输方案 · A/B/C 三区链路（A/B 完整微服务栈 · C 仅执行 THIRD_PARTY_C 评估）· 所有跨区链路均过软件网关'], 9, '94a3b8', False, PP_ALIGN.CENTER)

# Save
import os
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Intelligent-Audio-TEST', 'doc', '功能设计文档')
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, '09_跨区网络传输方案.pptx')
prs.save(out_path)
print(f'PPT saved to: {out_path}')