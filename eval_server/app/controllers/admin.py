# -*- coding: utf-8 -*-
"""管理端点：运行时更新 API Key（VEGA-77）。

安全红线（P0）：
- 鉴权 fail-closed：EVAL_ADMIN_TOKEN 未设置 / 空串 / 纯空白一律视为未配置，
  端点整体 403 禁用（禁止 is None 判定，防 compare_digest('','') fail-open）；
- 本端点不走 responses.py 的 success_response/error_response（其会完整记录
  请求体与响应 data，且不掩码 X-Admin-Token），一律裸 jsonify；
- 不回显：无读端点，响应 data 只有 key_name/updated_at，错误消息固定文案；
- 日志仅一行结果记录，永不含 key 值与 token 值。
"""
import hmac
import logging
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..services.admin_config_service import AdminConfigError, update_env_key

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


def _log(result, key_name='-'):
    """本端点唯一日志出口：只有 key 名（非 key 值）、结果、来源地址。"""
    logger.info('admin api_key update: key_name=%s result=%s remote_addr=%s',
                key_name, result, request.remote_addr or '-')


def _error(status_code, code, msg):
    """错误响应：裸 jsonify + 固定文案（不区分缺失/错误，不泄露原因）。"""
    return jsonify({'code': code, 'msg': msg, 'data': {}}), status_code


@admin_bp.route('/admin/config/api_key', methods=['PUT'])
def update_api_key():
    # token 判定必须 falsy 判空：请求期实时取值，未设置/空串/纯空白同判为未配置
    expected = (os.environ.get('EVAL_ADMIN_TOKEN') or '').strip()
    provided = request.headers.get('X-Admin-Token', '')
    if not expected:
        _log('disabled')
        return _error(403, 4002, '管理端点未启用')
    # encode 后比较：compare_digest 对非 ASCII str 会抛 TypeError，字节比较无此坑
    if not hmac.compare_digest(provided.encode('utf-8'), expected.encode('utf-8')):
        _log('unauthorized')
        return _error(401, 4001, '未授权')

    body = request.get_json(silent=True) or {}
    key_name = body.get('key_name')
    log_key = key_name if isinstance(key_name, str) else '-'
    try:
        update_env_key(key_name, body.get('api_key'))
    except AdminConfigError:
        _log('bad_request', log_key)
        return _error(400, 4000, '参数不合法')
    except OSError:
        # .env 写失败：固定文案，不含任何配置内容；此时文件与内存均保持原状
        _log('write_failed', log_key)
        return _error(500, 5000, '配置写入失败')

    _log('ok', log_key)
    return jsonify({
        'code': 0,
        'msg': 'success',
        'data': {
            'key_name': key_name,
            # 本地时间 ISO（部署机时区为 UTC+8）
            'updated_at': datetime.now().isoformat(timespec='seconds'),
        },
    }), 200
