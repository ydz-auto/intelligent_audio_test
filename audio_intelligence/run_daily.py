# -*- coding: utf-8 -*-
"""
一键执行：生成 HTML 报告 + 发送邮件
"""
from pathlib import Path
from datetime import datetime
from generate_html_report import (
    generate_html_report,
    SAMPLE_COMPETITORS,
    SAMPLE_SUMMARY,
)
from send_email import send_email


def main():
    output_dir = Path(__file__).parent
    scan_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  音频消费电子每日情报扫描")
    print(f"  扫描日期：{scan_date}")
    print(f"{'='*60}\n")

    # Step 1: 生成 HTML 报告
    print("[Step 1/2] 正在生成 HTML 报告 ...")
    html_path = generate_html_report(SAMPLE_COMPETITORS, SAMPLE_SUMMARY, output_dir)
    print(f"[✓] HTML 报告已生成：{html_path}\n")

    # Step 2: 发送邮件
    print("[Step 2/2] 正在发送邮件 ...")
    success = send_email(html_path, scan_date)
    print()

    if success:
        print(f"{'='*60}")
        print(f"  ✓ 全部完成！")
        print(f"  HTML 报告：{html_path}")
        print(f"  邮件已发送至：2662062828@qq.com")
        print(f"{'='*60}\n")
    else:
        print(f"{'='*60}")
        print(f"  ✗ 邮件发送失败，HTML 报告已保存：{html_path}")
        print(f"  请检查 SMTP 配置后重试")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
