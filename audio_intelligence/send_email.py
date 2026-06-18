# -*- coding: utf-8 -*-
"""
音频消费电子每日情报 - 邮件发送脚本
使用 Outlook SMTP (smtp-mail.outlook.com:587 + STARTTLS)
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, format_datetime
from pathlib import Path
from datetime import datetime


# ============== 邮件配置 ==============
SMTP_CONFIG = {
    "host": "smtp-mail.outlook.com",
    "port": 587,
    "user": "audio.weihua@outlook.com",
    "password": "Weihuaoutlook-233",   # 应用密码
}

SENDER = {
    "name": "音频情报扫描",
    "addr": "audio.weihua@outlook.com",
}

RECIPIENTS = [
    "2662062828@qq.com",
    # 可继续追加多个收件人
]

# ============== 邮件内容模板 ==============
def build_email(html_path: str, scan_date: str = None) -> MIMEMultipart:
    if scan_date is None:
        scan_date = datetime.now().strftime("%Y-%m-%d")

    html_content = Path(html_path).read_text(encoding="utf-8")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【音频消费电子每日情报】{scan_date}"
    msg["From"] = formataddr((SENDER["name"], SENDER["addr"]))
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Date"] = format_datetime(datetime.now())

    # 纯文本回退（部分客户端不支持 HTML 时显示）
    text_fallback = f"""
音频消费电子每日情报
扫描日期：{scan_date}

本期共扫描 {len(RECIPIENTS)} 个收件人关注的音频消费电子动态，
涵盖无线耳机、手机、平板、笔记本四大品类。

请使用支持 HTML 的邮件客户端（如 Outlook、Gmail、QQ 邮箱）查看完整报告。
"""
    part_text = MIMEText(text_fallback, "plain", "utf-8")
    part_html = MIMEText(html_content, "html", "utf-8")

    msg.attach(part_text)
    msg.attach(part_html)
    return msg


def send_email(html_path: str, scan_date: str = None) -> bool:
    """发送邮件，返回是否成功"""
    if scan_date is None:
        scan_date = datetime.now().strftime("%Y-%m-%d")

    msg = build_email(html_path, scan_date)

    print(f"[*] 正在连接 SMTP {SMTP_CONFIG['host']}:{SMTP_CONFIG['port']} ...")
    try:
        # STARTTLS 方式（Outlook 587 端口推荐）
        server = smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=30)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()

        print(f"[*] 正在登录 {SMTP_CONFIG['user']} ...")
        server.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])

        print(f"[*] 正在发送邮件至 {RECIPIENTS} ...")
        server.sendmail(SENDER["addr"], RECIPIENTS, msg.as_string())
        server.quit()

        print(f"[✓] 邮件发送成功！扫描日期：{scan_date}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[✗] SMTP 认证失败：{e}")
        print("    提示：如果开了两步验证，请使用「应用密码」而非登录密码")
        return False
    except smtplib.SMTPException as e:
        print(f"[✗] SMTP 错误：{e}")
        return False
    except Exception as e:
        print(f"[✗] 发送失败：{e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法：python send_email.py <html_report_path>")
        print("示例：python send_email.py audio_intelligence_2026-06-09.html")
        sys.exit(1)

    html_path = sys.argv[1]
    if not Path(html_path).exists():
        print(f"[✗] 文件不存在：{html_path}")
        sys.exit(1)

    success = send_email(html_path)
    sys.exit(0 if success else 1)
