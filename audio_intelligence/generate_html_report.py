# -*- coding: utf-8 -*-
"""
音频消费电子每日情报扫描 - HTML 报告生成器
"""
from datetime import datetime
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>音频消费电子每日情报 - {scan_date}</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                     "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        padding: 20px;
        color: #2c3e50;
        line-height: 1.6;
    }}
    .container {{
        max-width: 1200px;
        margin: 0 auto;
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        overflow: hidden;
    }}
    .header {{
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white;
        padding: 40px 50px;
        position: relative;
        overflow: hidden;
    }}
    .header::before {{
        content: "";
        position: absolute;
        top: -50%;
        right: -10%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        border-radius: 50%;
    }}
    .header h1 {{
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 10px;
        position: relative;
        z-index: 1;
    }}
    .header .subtitle {{
        font-size: 16px;
        opacity: 0.85;
        position: relative;
        z-index: 1;
    }}
    .header .meta {{
        display: flex;
        gap: 30px;
        margin-top: 20px;
        font-size: 14px;
        opacity: 0.8;
        position: relative;
        z-index: 1;
    }}
    .header .meta span {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }}
    .summary-section {{
        padding: 40px 50px;
        background: #f8f9fc;
        border-bottom: 1px solid #e8ecf4;
    }}
    .summary-section h2 {{
        font-size: 22px;
        color: #1a1a2e;
        margin-bottom: 25px;
        padding-bottom: 12px;
        border-bottom: 3px solid #667eea;
        display: inline-block;
    }}
    .summary-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 20px;
        margin-top: 20px;
    }}
    .summary-card {{
        background: white;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        border-left: 4px solid;
        transition: transform 0.2s;
    }}
    .summary-card:hover {{ transform: translateY(-3px); }}
    .summary-card.tech {{ border-left-color: #667eea; }}
    .summary-card.business {{ border-left-color: #f093fb; }}
    .summary-card.watch {{ border-left-color: #4facfe; }}
    .summary-card h3 {{
        font-size: 14px;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 12px;
    }}
    .summary-card ul {{
        list-style: none;
        padding: 0;
    }}
    .summary-card li {{
        padding: 8px 0;
        font-size: 14px;
        color: #374151;
        border-bottom: 1px dashed #e5e7eb;
    }}
    .summary-card li:last-child {{ border-bottom: none; }}
    .summary-card li strong {{
        color: #1a1a2e;
    }}
    .competitors-section {{
        padding: 40px 50px;
    }}
    .competitors-section h2 {{
        font-size: 22px;
        color: #1a1a2e;
        margin-bottom: 30px;
        padding-bottom: 12px;
        border-bottom: 3px solid #f093fb;
        display: inline-block;
    }}
    .competitor-card {{
        background: white;
        border: 1px solid #e8ecf4;
        border-radius: 12px;
        margin-bottom: 24px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .competitor-header {{
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        color: white;
        padding: 20px 30px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .competitor-header h3 {{
        font-size: 20px;
        font-weight: 600;
    }}
    .competitor-header .brand-tag {{
        background: rgba(255,255,255,0.2);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
    }}
    .competitor-meta {{
        background: #f8f9fc;
        padding: 12px 30px;
        font-size: 13px;
        color: #6b7280;
        border-bottom: 1px solid #e8ecf4;
    }}
    .competitor-meta strong {{
        color: #1a1a2e;
    }}
    .competitor-body {{
        padding: 24px 30px;
    }}
    .dimension-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0;
    }}
    .dimension-table th {{
        background: #f1f5f9;
        color: #475569;
        padding: 12px 16px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
        border-bottom: 2px solid #e2e8f0;
        width: 120px;
    }}
    .dimension-table td {{
        padding: 12px 16px;
        font-size: 14px;
        color: #334155;
        border-bottom: 1px solid #f1f5f9;
    }}
    .dimension-table tr:nth-child(even) {{ background: #fafbfc; }}
    .dimension-table tr:hover {{ background: #f0f4ff; }}
    .no-change {{
        color: #9ca3af;
        font-style: italic;
    }}
    .feedback-section {{
        background: #fafbfc;
        padding: 16px 20px;
        border-radius: 8px;
        margin: 16px 0;
        border-left: 3px solid #667eea;
    }}
    .feedback-section h4 {{
        font-size: 13px;
        color: #6b7280;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .feedback-item {{
        padding: 6px 0;
        font-size: 14px;
    }}
    .feedback-item.positive::before {{
        content: "✅ ";
    }}
    .feedback-item.neutral::before {{
        content: "⚠️ ";
    }}
    .feedback-item.negative::before {{
        content: "❌ ";
    }}
    .sources {{
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px dashed #e5e7eb;
    }}
    .sources h4 {{
        font-size: 12px;
        color: #6b7280;
        margin-bottom: 8px;
        text-transform: uppercase;
    }}
    .sources a {{
        display: inline-block;
        color: #667eea;
        text-decoration: none;
        font-size: 12px;
        margin: 2px 8px 2px 0;
        padding: 3px 8px;
        background: #f0f4ff;
        border-radius: 4px;
    }}
    .sources a:hover {{
        background: #667eea;
        color: white;
    }}
    .footer {{
        background: #1a1a2e;
        color: #94a3b8;
        padding: 30px 50px;
        text-align: center;
        font-size: 13px;
    }}
    .footer .brand {{
        color: #667eea;
        font-weight: 600;
        margin-bottom: 8px;
    }}
    @media (max-width: 768px) {{
        .summary-grid {{ grid-template-columns: 1fr; }}
        .header, .summary-section, .competitors-section, .footer {{
            padding: 20px;
        }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🎧 音频消费电子每日情报</h1>
        <div class="subtitle">Audio Consumer Electronics Daily Intelligence Report</div>
        <div class="meta">
            <span>📅 扫描日期：{scan_date}</span>
            <span>📡 覆盖来源：{source_count} 个</span>
            <span>🏷️ 覆盖品牌：{brand_count} 个</span>
            <span>📦 产品动态：{product_count} 条</span>
        </div>
    </div>

    <div class="summary-section">
        <h2>📊 每日竞争格局速览</h2>
        <div class="summary-grid">
            <div class="summary-card tech">
                <h3>技术趋势</h3>
                <ul>
                    {tech_trends}
                </ul>
            </div>
            <div class="summary-card business">
                <h3>商业信号</h3>
                <ul>
                    {business_signals}
                </ul>
            </div>
            <div class="summary-card watch">
                <h3>值得关注</h3>
                <ul>
                    {watch_items}
                </ul>
            </div>
        </div>
    </div>

    <div class="competitors-section">
        <h2>🏢 竞品分段呈现</h2>
        {competitors_html}
    </div>

    <div class="footer">
        <div class="brand">Audio Intelligence Scanner</div>
        <div>本报告由自动化扫描系统生成 · 扫描日期 {scan_date} · 仅供内部研究参考</div>
    </div>
</div>
</body>
</html>
"""


def render_competitor(c):
    """渲染单个竞品卡片"""
    dimensions_html = ""
    for dim_key, dim_label in [
        ("call", "通话"),
        ("audio", "音效"),
        ("spatial", "空间音频"),
        ("anc", "降噪"),
        ("pickup", "拾音增强"),
    ]:
        val = c["dimensions"].get(dim_key, "本期无动态")
        if val == "本期无动态":
            val_html = '<span class="no-change">本期无动态</span>'
        else:
            val_html = val.replace("**", "<strong>").replace("**", "</strong>")
        dimensions_html += f"""
        <tr>
            <th>{dim_label}</th>
            <td>{val_html}</td>
        </tr>
        """

    feedback_html = ""
    if c.get("feedback"):
        items = ""
        for fb in c["feedback"]:
            items += f'<div class="feedback-item {fb["type"]}">{fb["text"]}</div>'
        feedback_html = f"""
        <div class="feedback-section">
            <h4>社区反馈</h4>
            {items}
        </div>
        """

    sources_html = ""
    if c.get("sources"):
        links = "".join(
            f'<a href="{s["url"]}" target="_blank">{s["name"]}</a>'
            for s in c["sources"]
        )
        sources_html = f"""
        <div class="sources">
            <h4>信息来源</h4>
            {links}
        </div>
        """

    return f"""
    <div class="competitor-card">
        <div class="competitor-header">
            <h3>{c['name']}</h3>
            <span class="brand-tag">{c.get('category', '音频产品')}</span>
        </div>
        <div class="competitor-meta">
            <strong>发布日期：</strong>{c['date']} &nbsp;|&nbsp;
            <strong>产品：</strong>{c.get('product', '')}
        </div>
        <div class="competitor-body">
            <table class="dimension-table">
                {dimensions_html}
            </table>
            {feedback_html}
            {sources_html}
        </div>
    </div>
    """


def generate_html_report(competitors, summary, output_dir="."):
    """
    生成 HTML 报告
    :param competitors: 竞品列表，每个元素包含 name, date, product, category, dimensions, feedback, sources
    :param summary: 字典，包含 tech_trends, business_signals, watch_items
    :param output_dir: 输出目录
    :return: 生成的 HTML 文件路径
    """
    scan_date = datetime.now().strftime("%Y-%m-%d")
    competitors_html = "\n".join(render_competitor(c) for c in competitors)

    tech_trends = "\n".join(
        f"<li><strong>{t['title']}</strong>：{t['desc']}</li>"
        for t in summary.get("tech_trends", [])
    )
    business_signals = "\n".join(
        f"<li><strong>{t['title']}</strong>：{t['desc']}</li>"
        for t in summary.get("business_signals", [])
    )
    watch_items = "\n".join(
        f"<li><strong>{t['title']}</strong>：{t['desc']}</li>"
        for t in summary.get("watch_items", [])
    )

    html = HTML_TEMPLATE.format(
        scan_date=scan_date,
        source_count=sum(len(c.get("sources", [])) for c in competitors),
        brand_count=len(competitors),
        product_count=len(competitors),
        tech_trends=tech_trends or "<li>暂无</li>",
        business_signals=business_signals or "<li>暂无</li>",
        watch_items=watch_items or "<li>暂无</li>",
        competitors_html=competitors_html,
    )

    out_path = Path(output_dir) / f"audio_intelligence_{scan_date}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


# 示例数据
SAMPLE_COMPETITORS = [
    {
        "name": "当贝",
        "category": "耳夹式 AI 耳机",
        "date": "2026-06-08",
        "product": "新一代 AI 耳机 / Air1",
        "dimensions": {
            "call": "Air1 配备 4 麦克风 + 波束成形 + DNN 降噪，嘈杂环境通话清晰",
            "audio": "12mm 巨能动圈 + Hi-Res 金标 + LHDC 5.0 (1000Kbps) + BoomBass 动态低频增强",
            "spatial": "支持空间音频，乐器与人声分离度提升",
            "anc": "ANC 主动降噪 + 通透模式；新一代降噪功能升级（参数待公布）",
            "pickup": "AI 会议纪要自动区分发言人；36 种语言 + 27 种方言 AI 实时翻译；2.04 英寸 AMOLED 触屏充电仓",
        },
        "feedback": [
            {"type": "positive", "text": "AI 翻译实用性超预期，日文转中文基本无延迟"},
            {"type": "positive", "text": "TÜV 舒适度认证（行业首款耳夹耳机获此认证）"},
            {"type": "neutral", "text": "开放式物理特性决定无法达到入耳式完全封闭沉浸感"},
        ],
        "sources": [
            {"name": "快科技", "url": "https://news.qq.com/rain/a/20260608A0478O00"},
            {"name": "财法观天下", "url": "https://m.sohu.com/a/1033702102_122066678/"},
        ],
    },
    {
        "name": "Sennheiser",
        "category": "头戴式降噪耳机",
        "date": "2026-06-04",
        "product": "MOMENTUM 5 Wireless",
        "dimensions": {
            "call": "每侧 4 麦克风（翻倍），抗风噪升级，通话人声更自然",
            "audio": "42mm 动圈（HD600 调校）+ Hi-Res + aptX Lossless + 骁龙畅听 + 8 段 EQ",
            "spatial": "杜比全景声 + 头部追踪（首日固件更新解锁）",
            "anc": "中频段人声降噪提升 3 倍；每侧 4 麦克风专用于 ANC+通透",
            "pickup": "本期无动态",
        },
        "feedback": [
            {"type": "positive", "text": "可换电池设计获广泛好评，'用好几年没问题'"},
            {"type": "positive", "text": "中国售价 3299 元被认为合理"},
            {"type": "neutral", "text": "杜比全景声需固件更新 + Atmos 音源设备"},
            {"type": "neutral", "text": "续航 57h 略低于上代 60h（功耗增加所致）"},
        ],
        "sources": [
            {"name": "Sennheiser 官方", "url": "https://newsroom.sennheiser.com/introducing-momentum-5-wireless-your-sound-revelation-starts-here"},
            {"name": "IT 之家", "url": "http://news.qq.com/rain/a/20260526A02T6P00"},
        ],
    },
    {
        "name": "vivo",
        "category": "首款头戴降噪耳机",
        "date": "2026-05-29",
        "product": "vivo 头戴降噪耳机（6月10日开售）",
        "dimensions": {
            "call": "AI 管家支持 32 种语言实时翻译；AI 智能播报",
            "audio": "40mm 生物振膜动圈 + Hi-Res 有线/无线双金标 + 5Hz-40kHz + 10 段 EQ",
            "spatial": "金耳朵声学实验室 '专业空间声场音频引擎' + 头部追踪，杜比声场误差 <3°",
            "anc": "最高 58dB 降噪 + 双核降噪芯片 + 6 麦阵列 + 场景化降噪（飞机/地铁/公交）",
            "pickup": "本期无动态",
        },
        "feedback": [
            {"type": "positive", "text": "499 元定价极具竞争力（58dB + 75h + Hi-Res 双金标）"},
            {"type": "positive", "text": "238g 超轻设计，长时间佩戴无压迫感"},
            {"type": "neutral", "text": "vivo 首款头戴产品，声学调校成熟度待市场验证"},
        ],
        "sources": [
            {"name": "太平洋科技", "url": "https://g.pconline.com.cn/x/2162/21621031.html"},
            {"name": "IT Bear", "url": "http://m.itbear.com.cn/html/2026-05/1368127.html"},
        ],
    },
    {
        "name": "IK Multimedia",
        "category": "专业音频校准系统",
        "date": "2026-06-04",
        "product": "ARC ON·EAR 1.5 固件更新",
        "dimensions": {
            "call": "本期无动态",
            "audio": "新增 50 款 IEM 校准；32 位 ESS SABRE® 转换器 + 超低失真功放",
            "spatial": "先进空间处理 + 物理建模（非脉冲响应）",
            "anc": "本期无动态",
            "pickup": "本期无动态",
        },
        "feedback": [
            {"type": "positive", "text": "IEM 首次可作为专业混音参考标准，密封设计降低声学变异性"},
            {"type": "positive", "text": "5 个配置文件可存储不同校准 + 自定义 EQ 曲线；免费更新"},
            {"type": "neutral", "text": "仅支持 50 款 IEM，覆盖面有限；硬件售价 $249.99"},
        ],
        "sources": [
            {"name": "audioXpress", "url": "https://audioxpress.com/type/news"},
            {"name": "音频应用", "url": "https://m.sohu.com/a/1032472049_455142/"},
        ],
    },
    {
        "name": "Shokz",
        "category": "开放式耳夹耳机",
        "date": "2026-06-04",
        "product": "OpenDots 2 / OpenDots Air",
        "dimensions": {
            "call": "OpenDots 2：骨传导麦克风 + 双空气传导麦克风 + AI 降噪",
            "audio": "OpenDots 2：Bassphere™ 2.0 + 双 11.8mm 单元 + MirrorPitch™ + Dolby Audio",
            "spatial": "OpenDots 2：Dolby Audio 升级带来更宽声场",
            "anc": "本期无动态",
            "pickup": "OpenDots 2：骨传导麦克风拾音",
        },
        "feedback": [
            {"type": "positive", "text": "Shokz 从骨传导运动品牌向生活方式品牌转型信号明确"},
            {"type": "positive", "text": "OpenDots 2 旗舰配置（骨传导麦克风 + Dolby Audio）在耳夹品类中领先"},
            {"type": "neutral", "text": "$199.95 定价在耳夹品类中偏高"},
        ],
        "sources": [
            {"name": "PRNewswire", "url": "https://www.prnewswire.com/news-releases/shokz-introduces-opendots-2-and-opendots-air-expanding-open-ear-clip-on-earbuds-for-everyday-listening-302791659.html"},
            {"name": "audioXpress", "url": "https://audioxpress.com/type/news"},
        ],
    },
    {
        "name": "Audioscenic × Lenovo",
        "category": "笔记本空间音频",
        "date": "2026-06-02",
        "product": "Legion 7a 16 (Audioscenic 空间音频)",
        "dimensions": {
            "call": "本期无动态",
            "audio": "四颗 2W 扬声器 + 杜比全景声",
            "spatial": "Audioscenic 'Powered by Audioscenic' 自适应沉浸式音频；Windows APO 框架首次落地",
            "anc": "本期无动态",
            "pickup": "本期无动态",
        },
        "feedback": [
            {"type": "positive", "text": "首次在 Windows APO 框架下实现笔记本无耳机空间音频"},
            {"type": "positive", "text": "为'内置扬声器空间音频'开辟新路径，可能引发其他厂商跟进"},
            {"type": "neutral", "text": "实际体验是否达标需用户验证"},
        ],
        "sources": [
            {"name": "audioXpress", "url": "https://audioxpress.com/type/news"},
            {"name": "Notebookcheck", "url": "https://www.notebookcheck.net/Lenovo-Legion-7a-16-G11-Review-Lightweight-OLED-gaming-laptop-with-AMD-Ryzen-400.1261922.0.html"},
        ],
    },
]

SAMPLE_SUMMARY = {
    "tech_trends": [
        {"title": "AI 交互深度嵌入耳机", "desc": "AI 翻译、会议纪要、语音助手成为差异化核心"},
        {"title": "开放式耳夹形态爆发", "desc": "从运动专用向日常通勤/办公场景渗透"},
        {"title": "笔记本空间音频突破", "desc": "Audioscenic 通过 Windows APO 框架实现无耳机沉浸式音频"},
        {"title": "专业监听 IEM 校准平民化", "desc": "IK Multimedia 让 IEM 首次可替代录音室头戴作为混音参考"},
    ],
    "business_signals": [
        {"title": "vivo 杀入头戴降噪", "desc": "499 元 / 58dB / 75h 续航 / Hi-Res 双金标，定价极具侵略性"},
        {"title": "Sennheiser 旗舰中国开售", "desc": "MOMENTUM 5 售价 3299 元，可换电池 + aptX Lossless + 杜比全景声"},
        {"title": "耳夹式价格带下探", "desc": "从 169 元（虹觅）到 899 元（当贝）全价位覆盖"},
    ],
    "watch_items": [
        {"title": "vivo 头戴 6/10 开售", "desc": "首款产品市场反馈将决定 vivo 在音频品类后续投入"},
        {"title": "Sennheiser MOMENTUM 5 美国 6/16 上市", "desc": "可换电池设计是否引发行业跟风"},
        {"title": "当贝新一代 AI 耳机完整参数", "desc": "AI 交互 + 耳夹形态的融合程度将影响品类方向"},
        {"title": "联想 Legion 7a 空间音频体验", "desc": "笔记本无耳机空间音频是否真正可用"},
    ],
}


if __name__ == "__main__":
    out = generate_html_report(SAMPLE_COMPETITORS, SAMPLE_SUMMARY)
    print(f"HTML 报告已生成：{out}")
