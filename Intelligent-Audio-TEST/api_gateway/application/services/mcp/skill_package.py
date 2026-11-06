# -*- coding: utf-8 -*-
"""skill 包下载生成（INT-1150 / INT-1140 分道 A）。

GET /api/v1/agent/skill 动态拼装 zip：SKILL.md（curl 使用说明）+
mcp.json（MCP 配置模板，URL 指向网关 MCP 端点）。``?base_url=`` 注入
模板；无 base_url 时后端从 Origin / Host 头兜底。下载需登录。
"""
from __future__ import annotations

import io
import logging
import os
import zipfile

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', '..', '..', 'skill_templates')
# 兼容模板目录不存在时回退包内常量（单测/无模板文件环境）
_SKILL_TEMPLATE_FALLBACK = None
_MCP_TEMPLATE_FALLBACK = None

ZIP_FILENAME = 'intelligent_audio_test_skill.zip'


def _load_template(filename: str, fallback: str | None) -> str:
    """读模板文件；文件缺失回退 fallback（不阻断下载）。"""
    path = os.path.normpath(os.path.join(_TEMPLATES_DIR, filename))
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        if fallback is not None:
            logger.warning('skill 模板缺失，回退内置模板: %s', path)
            return fallback
        raise


def _inject_base_url(template: str, base_url: str) -> str:
    """模板 {{BASE_URL}} 占位符注入。"""
    return template.replace('{{BASE_URL}}', base_url.rstrip('/'))


def resolve_base_url(request) -> str:
    """base_url 解析：?base_url= → Origin 头 → Host 头（X-Forwarded-Proto 兜底协议）。"""
    query = getattr(request, 'query_params', None)
    base_url = ''
    if query is not None:
        base_url = (query.get('base_url') or '').strip()
    if not base_url:
        origin = request.headers.get('Origin', '') if hasattr(request, 'headers') else ''
        if origin:
            base_url = origin.strip()
    if not base_url:
        host = request.headers.get('Host', '') if hasattr(request, 'headers') else ''
        if host:
            scheme = ('https' if request.headers.get('X-Forwarded-Proto', 'http')
                      == 'https' else 'http') if hasattr(request, 'headers') else 'http'
            base_url = f'{scheme}://{host.strip()}'
    return base_url.rstrip('/') if base_url else ''


def build_skill_zip(base_url: str) -> bytes:
    """拼装 skill zip（SKILL.md + mcp.json，base_url 注入），返回 bytes。"""
    skill_md = _load_template('SKILL.md', _SKILL_TEMPLATE_FALLBACK)
    mcp_json = _load_template('mcp.json.tpl', _MCP_TEMPLATE_FALLBACK)
    if base_url:
        skill_md = _inject_base_url(skill_md, base_url)
        mcp_json = _inject_base_url(mcp_json, base_url)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('SKILL.md', skill_md)
        zf.writestr('mcp.json', mcp_json)
    return buf.getvalue()
