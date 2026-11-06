# -*- coding: utf-8 -*-
"""SMTP 邮件发送工具（INT-80 设备告警通知渠道）。

配置化：读取 BaseConfig SMTP_* 环境变量，SMTP_HOST 未配置时视为禁用，
send_email 直接返回 False（降级不阻塞业务），与 EventBus/幂等存储降级口径一致。

测试可注入 fake transport：email_sender.send_email(..., transport=...)，
或 monkeypatch smtplib.SMTP / SMTP_SSL。
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)


class EmailSendResult:
    """邮件发送结果（供调用方落库/审计）"""

    def __init__(self, success: bool, message: str = '', recipients: Sequence[str] = ()):
        self.success = success
        self.message = message
        self.recipients = list(recipients)

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'message': self.message,
            'recipients': self.recipients,
        }


def is_email_configured() -> bool:
    """SMTP 是否已配置（未配置时告警通知渠道降级为仅落库）"""
    from shared.infrastructure.config import BaseConfig
    return bool(BaseConfig.SMTP_HOST)


def _parse_recipients(recipients: Optional[Sequence[str]]) -> List[str]:
    """合并显式收件人与配置收件人（逗号分隔），去重保序"""
    from shared.infrastructure.config import BaseConfig
    merged: List[str] = []
    for item in list(recipients or []):
        addr = str(item).strip()
        if addr and addr not in merged:
            merged.append(addr)
    for addr in (BaseConfig.ALERT_EMAIL_RECIPIENTS or '').split(','):
        addr = addr.strip()
        if addr and addr not in merged:
            merged.append(addr)
    return merged


def send_email(
    subject: str,
    body: str,
    recipients: Optional[Sequence[str]] = None,
    html: bool = False,
    transport=None,
) -> EmailSendResult:
    """发送文本/HTML 邮件。

    Args:
        subject: 邮件主题
        body: 正文（纯文本或 HTML，由 html 参数决定）
        recipients: 显式收件人列表；缺省时使用配置 ALERT_EMAIL_RECIPIENTS
        html: 正文是否为 HTML
        transport: 测试注入的 SMTP 连接工厂（返回 context manager）；
            None 时按配置使用 smtplib.SMTP / SMTP_SSL

    Returns:
        EmailSendResult（未配置 SMTP 时 success=False, message='SMTP 未配置'）
    """
    from shared.infrastructure.config import BaseConfig

    addrs = _parse_recipients(recipients)
    if not addrs:
        return EmailSendResult(False, '未配置告警收件人（ALERT_EMAIL_RECIPIENTS）', [])
    if not BaseConfig.SMTP_HOST:
        return EmailSendResult(False, 'SMTP 未配置（SMTP_HOST 为空，通知渠道禁用）', addrs)

    sender = BaseConfig.SMTP_FROM or BaseConfig.SMTP_USER
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = ', '.join(addrs)
    msg['Subject'] = subject
    content = MIMEText(body, 'html' if html else 'plain', 'utf-8')
    msg.attach(content)

    try:
        if transport is not None:
            with transport() as smtp:
                smtp.sendmail(sender, addrs, msg.as_string())
        elif BaseConfig.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(BaseConfig.SMTP_HOST, BaseConfig.SMTP_PORT, timeout=10) as smtp:
                if BaseConfig.SMTP_USER:
                    smtp.login(BaseConfig.SMTP_USER, BaseConfig.SMTP_PASSWORD)
                smtp.sendmail(sender, addrs, msg.as_string())
        else:
            with smtplib.SMTP(BaseConfig.SMTP_HOST, BaseConfig.SMTP_PORT, timeout=10) as smtp:
                # 校验服务器证书：STARTTLS 明文升级不验证书时 SMTP 凭据可被中间人截获
                smtp.starttls(context=ssl.create_default_context())
                if BaseConfig.SMTP_USER:
                    smtp.login(BaseConfig.SMTP_USER, BaseConfig.SMTP_PASSWORD)
                smtp.sendmail(sender, addrs, msg.as_string())
        return EmailSendResult(True, '邮件发送成功', addrs)
    except Exception as e:
        logger.warning("邮件发送失败: %s", e, exc_info=True)
        return EmailSendResult(False, f'邮件发送失败: {e}', addrs)
