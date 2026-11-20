# -*- coding: utf-8 -*-
"""Skill zip 导入的上传体积上限（INT-2549 返工 P3）。

zip 导入是攻击面：整包在网关 / 接口层先被读进内存再判体积，恶意大包能
直接撑爆进程。本中间件在解析 multipart **之前**按 ``Content-Length`` 拒绝
超大上传（413），与网关 ``agent_skill_bp`` 同一口径（共用
``shared.skill_package.DEFAULT_MAX_UPLOAD_BYTES`` 与
``AGENT_SKILL_MAX_UPLOAD_BYTES``）。

``Content-Length`` 缺失（chunked 上传）时这里放行，由接口层的有界读取
（``UploadFile.read(max_bytes + 1)``）兜底，仍不会无界读入内存。
"""
import json
from typing import Any, Dict, Optional

from agent_service.domain.enums import SkillErrorCode, SkillIssueCode
from shared.skill_package import DEFAULT_MAX_UPLOAD_BYTES


class SkillImportUploadLimitMiddleware:
    """在 ASGI 入口按 ``Content-Length`` 拒绝超限的 Skill 导入请求。"""

    def __init__(self, app: Any, *,
                 path_suffix: str = '/skills/import',
                 max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES):
        self.app = app
        self.path_suffix = path_suffix
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: Dict[str, Any], receive: Any,
                       send: Any) -> None:
        if not self._matches(scope):
            await self.app(scope, receive, send)
            return
        declared = self._declared_length(scope)
        if declared is None or declared <= self.max_bytes:
            await self.app(scope, receive, send)
            return
        body = self._rejection(declared)
        await send({
            'type': 'http.response.start',
            'status': 413,
            'headers': [(b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode('ascii'))],
        })
        await send({'type': 'http.response.body', 'body': body})

    def _matches(self, scope: Dict[str, Any]) -> bool:
        return (scope.get('type') == 'http'
                and scope.get('method') == 'POST'
                and str(scope.get('path', '')).endswith(self.path_suffix))

    @staticmethod
    def _declared_length(scope: Dict[str, Any]) -> Optional[int]:
        for name, value in scope.get('headers', ()):
            if name.lower() == b'content-length':
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    def _rejection(self, declared: int) -> bytes:
        message = (f'上传包 {declared} 字节，超过上限 {self.max_bytes} 字节'
                   '（未读入内存）')
        payload = {
            'detail': message,
            'code': SkillErrorCode.SKILL_IMPORT_INVALID.value,
            'issues': [{
                'code': SkillIssueCode.PACKAGE_TOO_LARGE.value,
                'severity': 'ERROR',
                'skill': '',
                'field': 'package',
                'message': message,
            }],
        }
        return json.dumps(payload, ensure_ascii=False).encode('utf-8')


__all__ = ['SkillImportUploadLimitMiddleware']
