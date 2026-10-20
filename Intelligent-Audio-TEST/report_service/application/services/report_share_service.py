# -*- coding: utf-8 -*-
"""报告分享应用服务（INT-971）

职责：
- create_share：参数校验（access/expiry/expires_at/password/recipients）→
  报告存在性校验 → 生成 token / 换算过期 / 哈希密码 → 落库。
- list_shares / revoke_share：分享管理与撤销（软撤销，幂等）。
- get_shared_report：公开读取自校验（token 有效/未撤销/报告未删/未过期/
  密码/访问口径），**200 放行时原子递增 visits**（访问统计唯一入口；
  403/404/410 不计次）。

recipients 已由网关经 AuthService.ListUsers(keyword) 解析为
[{user_id, label}] 列表后透传，本服务只做存储与读取比对（不感知用户名/邮箱）。
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from shared.infrastructure.user_context import get_current_user_id
from shared.models.database import utc8now
from report_service.infrastructure.persistence.report_share_repository import (
    report_share_repository,
)

logger = logging.getLogger(__name__)

# 访问口径 / 有效期取值（对齐前端 mock：use-report-share.ts）
ACCESS_VALUES = ('login', 'specific', 'public')
EXPIRY_VALUES = ('none', '7d', '30d', 'custom')


def _hash_password(password: str) -> str:
    """明文密码 → bcrypt 哈希（落 password_hash，响应只回 password_set）。"""
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _verify_password(password: str, password_hash: str) -> bool:
    """bcrypt 校验；哈希格式非法时返回 False（不抛）。"""
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode('utf-8'),
                              password_hash.encode('utf-8'))
    except ValueError:
        return False


def _now_naive():
    """东八区当前时间（naive）。

    expires_at 存储/比较统一用 naive UTC+8：SQLite 读回 DateTime 无时区，
    与 utc8now()（aware +08:00）混比会抛 TypeError；创建与列表序列化口径
    也由此保持一致（isoformat 不带偏移）。
    """
    return utc8now().replace(tzinfo=None)


def _parse_datetime(value):
    """ISO 8601 → 东八区 naive datetime。

    带 Z/时区（如 '2026-10-30T00:00:00Z'）转东八区后去时区；
    无时区字符串视为东八区；解析失败返回 None。
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    try:
        s = str(value).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _share_to_dict(share) -> dict:
    """分享记录 → 对外契约 dict（列表/创建响应共用字段）。"""
    return {
        'token': share.token,
        'access': share.access,
        'expires_at': share.expires_at.isoformat() if share.expires_at else None,
        'password_set': bool(share.password_hash),
        'recipients': share.recipients or [],
        'visits': share.visits or 0,
        'last_visited_at': share.last_visited_at.isoformat() if share.last_visited_at else None,
        'revoked': bool(share.revoked),
        'created_at': share.created_at.isoformat() if share.created_at else None,
    }


class ReportShareService:
    """报告分享应用服务（INT-971）。"""

    def __init__(self, repository=report_share_repository):
        self.repository = repository

    # ------------------------------------------------------------------
    # 创建分享
    # ------------------------------------------------------------------

    def create_share(self, params: dict) -> dict:
        """创建分享链接。

        Args:
            params: {report_id, access, expiry, expires_at?, password?, recipients}
                recipients 为网关已解析的 [{user_id, label}] 列表。

        Returns:
            dict: {success, message, data?, code?}
        """
        try:
            report_id = int(params.get('report_id') or 0)
            access = (params.get('access') or 'login').strip()
            expiry = (params.get('expiry') or 'none').strip()
            expires_at_raw = params.get('expires_at') or None
            password = params.get('password') or ''
            recipients = params.get('recipients') or []

            if report_id <= 0:
                return {'success': False, 'message': '缺少 report_id',
                        'data': {'code': 400}, 'code': 400}
            if access not in ACCESS_VALUES:
                return {'success': False,
                        'message': f'access 仅支持 {" / ".join(ACCESS_VALUES)}',
                        'data': {'code': 400}, 'code': 400}
            if expiry not in EXPIRY_VALUES:
                return {'success': False,
                        'message': f'expiry 仅支持 {" / ".join(EXPIRY_VALUES)}',
                        'data': {'code': 400}, 'code': 400}
            if access == 'specific' and not recipients:
                return {'success': False, 'message': 'access=specific 时 recipients 必填',
                        'data': {'code': 400}, 'code': 400}
            if not self.repository.report_exists(report_id):
                return {'success': False, 'message': '报告不存在或已删除',
                        'data': {'code': 404}, 'code': 404}

            # expires_at 换算：none→NULL、7d/30d→now+7/30天、custom→body.expires_at
            # （统一 naive UTC+8，见 _now_naive 注记）
            expires_at = None
            if expiry == '7d':
                expires_at = _now_naive() + timedelta(days=7)
            elif expiry == '30d':
                expires_at = _now_naive() + timedelta(days=30)
            elif expiry == 'custom':
                if not expires_at_raw:
                    return {'success': False, 'message': 'expiry=custom 时 expires_at 必填',
                            'data': {'code': 400}, 'code': 400}
                expires_at = _parse_datetime(expires_at_raw)
                if expires_at is None:
                    return {'success': False,
                            'message': 'expires_at 格式非法（应为 ISO 8601）',
                            'data': {'code': 400}, 'code': 400}

            password_hash = None
            password_set = False
            if password:
                password_hash = _hash_password(password)
                password_set = True

            token = secrets.token_urlsafe(24)
            self.repository.create(
                report_id, token, access, expires_at, password_hash,
                recipients if access == 'specific' else None,
                get_current_user_id(),
            )
            return {
                'success': True,
                'message': 'ok',
                'data': {
                    'token': token,
                    'access': access,
                    'expires_at': expires_at.isoformat() if expires_at else None,
                    'password_set': password_set,
                    'recipients': recipients if access == 'specific' else [],
                    'visits': 0,
                    'last_visited_at': None,
                },
            }
        except Exception as e:
            logger.error("创建分享失败: %s", e, exc_info=True)
            return {'success': False, 'message': str(e),
                    'data': {'code': 500}, 'code': 500}

    # ------------------------------------------------------------------
    # 列表 / 撤销
    # ------------------------------------------------------------------

    def list_shares(self, report_id: int) -> dict:
        """分享管理与统计列表（按 created_at 倒序，含已撤销）。"""
        try:
            if not report_id:
                return {'success': False, 'message': '缺少 report_id',
                        'data': {'code': 400}, 'code': 400}
            if not self.repository.report_exists(report_id):
                return {'success': False, 'message': '报告不存在或已删除',
                        'data': {'code': 404}, 'code': 404}
            shares = self.repository.list_by_report(report_id)
            return {'success': True, 'message': 'ok',
                    'data': {'shares': [_share_to_dict(s) for s in shares]}}
        except Exception as e:
            logger.error("查询分享列表失败: %s", e, exc_info=True)
            return {'success': False, 'message': str(e),
                    'data': {'code': 500}, 'code': 500}

    def revoke_share(self, report_id: int, token: str) -> dict:
        """软撤销分享（幂等：已撤销再次撤销仍 200；token 不存在/不属于该报告 → 404）。"""
        try:
            if not report_id or not token:
                return {'success': False, 'message': '缺少 report_id 或 token',
                        'data': {'code': 400}, 'code': 400}
            ok = self.repository.revoke(report_id, token)
            if not ok:
                return {'success': False, 'message': '分享不存在或不属于该报告',
                        'data': {'code': 404}, 'code': 404}
            return {'success': True, 'message': 'ok', 'data': {'revoked': True}}
        except Exception as e:
            logger.error("撤销分享失败: %s", e, exc_info=True)
            return {'success': False, 'message': str(e),
                    'data': {'code': 500}, 'code': 500}

    # ------------------------------------------------------------------
    # 公开读取（自校验 + 计数）
    # ------------------------------------------------------------------

    def get_shared_report(self, token: str, password: str = None,
                          user_id: int = None) -> dict:
        """公开读取分享：校验 + 200 放行时递增 visits（唯一计数入口）。

        Returns:
            success: False 时 data={code: 404/410/401/403}，message 为错误语义；
            success: True 时 data={report_id}。
        """
        try:
            if not token:
                return {'success': False, 'message': '缺少分享 token',
                        'data': {'code': 404}, 'code': 404}
            share = self.repository.get_by_token(token)
            if share is None:
                return {'success': False, 'message': '分享不存在',
                        'data': {'code': 404}, 'code': 404}
            if share.revoked:
                return {'success': False, 'message': '分享已撤销',
                        'data': {'code': 404}, 'code': 404}
            if not self.repository.report_exists(share.report_id):
                return {'success': False, 'message': '报告已删除',
                        'data': {'code': 404}, 'code': 404}
            if share.expires_at is not None and share.expires_at < _now_naive():
                return {'success': False, 'message': '分享已过期',
                        'data': {'code': 410}, 'code': 410}

            # 密码校验（缺 → share_password_required；错 → share_password_invalid）
            if share.password_hash:
                if not password:
                    return {'success': False, 'message': 'share_password_required',
                            'data': {'code': 403, 'share_requires_password': True},
                            'code': 403}
                if not _verify_password(password, share.password_hash):
                    return {'success': False, 'message': 'share_password_invalid',
                            'data': {'code': 403}, 'code': 403}

            # 访问口径（鉴权口径汇总表见卡面）
            if share.access == 'login' and not user_id:
                return {'success': False, 'message': '登录后可访问分享',
                        'data': {'code': 401}, 'code': 401}
            if share.access == 'specific':
                if not user_id:
                    return {'success': False, 'message': '登录后可访问分享',
                            'data': {'code': 401}, 'code': 401}
                recipient_ids = {
                    str(r.get('user_id'))
                    for r in (share.recipients or []) if r.get('user_id')
                }
                if str(user_id) not in recipient_ids:
                    return {'success': False, 'message': '无权访问该分享',
                            'data': {'code': 403}, 'code': 403}

            # 200 放行：原子递增 visits + 更新最近访问时间
            self.repository.increment_visits(share.id)
            return {'success': True, 'message': 'ok',
                    'data': {'report_id': share.report_id}}
        except Exception as e:
            logger.error("读取分享失败: %s", e, exc_info=True)
            return {'success': False, 'message': str(e),
                    'data': {'code': 500}, 'code': 500}


# 模块级单例
report_share_service = ReportShareService()
