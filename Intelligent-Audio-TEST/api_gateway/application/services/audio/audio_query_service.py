import logging
import os
from fastapi.responses import Response

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.schemas.audio import (
    AudioIdsData,
    AudioItem,
    AudioListData,
    AudioListStats,
    TagListData as AudioTagListData,
    AudioListQuery,
    AudioIdQuery,
    AudioStreamQuery,
    AudioStreamByPathQuery,
    AudioDownloadQuery,
    PlaybackHistoryItem,
    PlaybackHistoryListData,
    PlaybackHistoryQuery,
)
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()

# 音频扩展名 → Content-Type（下载/回退字节流共用白名单，与 audio_service
# stream-by-path 校验口径一致，拒绝魔法字符串）
_AUDIO_EXT_CONTENT_TYPES = {
    'wav': 'audio/wav',
    'mp3': 'audio/mpeg',
    'flac': 'audio/flac',
    'aac': 'audio/aac',
    'ogg': 'audio/ogg',
    'm4a': 'audio/mp4',
    'wma': 'audio/x-ms-wma',
    'opus': 'audio/opus',
}


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class AudioQueryService:
    # 获取所有可用的音频标签
    @staticmethod
    def get_all_tags():

        result = _audio_acl.get_all_tags()
        if result.get('success'):
            data = result.get('data') or {}
            items = data.get('items', [])
            # INT-297：列表信封统一（无分页语义：单页全量）
            return success_response(AudioTagListData(
                items=items,
                total=len(items),
                page=1,
                per_page=len(items) or 1,
                pages=1,
            ))
        return wrap_grpc_response(result, default_error_msg='获取标签失败')

    # 获取所有音频文件列表
    @staticmethod
    def _parse_list_query_params():
        # 支持分页和过滤
        # 优先从 body 获取参数（POST），其次从 query 获取（GET）
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            query = AudioListQuery.model_validate(data)
        else:
            query = _parse_query_params(AudioListQuery)

        # tags 特殊处理：POST 时是 list of dict，GET 时是 list of str
        tags_data = []
        if query.tags:
            if request.method == 'POST' and request.is_json:
                data = request.get_json() or {}
                tags_data = data.get('tags', [])
            else:
                tags_data = [{'name': t, 'mode': 'and'} for t in query.tags]

        return {
            'page': query.page,
            'per_page': query.per_page,
            'keyword': query.keyword,
            'format_': query.format,
            'audio_type': query.audio_type,
            'folder': query.folder,
            'sample_rate': query.sample_rate,
            'duration': query.duration,
            'tags_data': tags_data,
            'direction': query.direction,
            'algorithm_type': query.algorithm_type,
        }

    @staticmethod
    def get_all():
        
        params = AudioQueryService._parse_list_query_params()
        result = _audio_acl.get_all(params)
        if result.get('success'):
            data = result.get('data') or {}
            items = data.get('items', [])
            # 将 dict 列表转换为 AudioItem schema
            audio_items = [AudioItem(**item) if isinstance(item, dict) else item for item in items]
            stats = data.get('stats') or {}
            return success_response(
                AudioListData(
                    items=audio_items,
                    total=data.get('total', 0),
                    page=data.get('page', params['page']),
                    per_page=data.get('per_page', params['per_page']),
                    pages=data.get('pages', 0),
                    stats=AudioListStats(
                        total_files=stats.get('total_files', 0),
                        total_size=stats.get('total_size', '0 B'),
                        total_duration=stats.get('total_duration', '0:00'),
                        today_uploads=stats.get('today_uploads', 0),
                    ),
                )
            )
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # 获取单个音频文件详情
    @staticmethod
    def get_one(audio_id):
        result = _audio_acl.get_one(audio_id)
        if result.get('success'):
            data = result.get('data')
            if data:
                # INT-466：admin 访问私有音频详情落 PRIVATE_RESOURCE_ACCESS 审计（旁路）
                from api_gateway.application.services.visibility.visibility_audit import (
                    maybe_audit_private_detail,
                )
                maybe_audit_private_detail('audio', audio_id, data if isinstance(data, dict) else {})
                return success_response(AudioItem(**data) if isinstance(data, dict) else data)
            return success_response(None)
        return wrap_grpc_response(
            result,
            default_error_msg='音频文件不存在',
            error_code_mapping={404: ('音频文件不存在', 404)},
        )

    @staticmethod
    def get_by_ids():
        
        if not request.is_json:
            return error_response("请求必须是 JSON 格式")

        data = request.get_json() or {}
        audio_ids = data.get('ids', [])

        if not audio_ids:
            return success_response([])

        if not isinstance(audio_ids, list):
            return error_response("ids 必须是数组")

        result = _audio_acl.get_by_ids({'ids': audio_ids})
        if result.get('success'):
            data = result.get('data') or []
            audio_items = [AudioItem(**item) if isinstance(item, dict) else item for item in data]
            return success_response(audio_items)
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # 按 MD5 批量查询音频（用于批量更新标注时匹配）
    @staticmethod
    def get_by_md5():
        
        if not request.is_json:
            return error_response("请求必须是 JSON 格式")

        data = request.get_json() or {}
        md5_list = data.get('md5_list', [])

        if not md5_list:
            return success_response({})

        if not isinstance(md5_list, list):
            return error_response("md5_list 必须是数组")

        result = _audio_acl.get_by_md5({'md5_list': md5_list})
        if result.get('success'):
            return success_response(result.get('data') or {})
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # 获取所有音频ID列表（用于全选功能）
    @staticmethod
    def _parse_id_query_params():
        # 优先从 body 获取参数（POST），其次从 query 获取（GET）
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            query = AudioIdQuery.model_validate(data)
        else:
            query = _parse_query_params(AudioIdQuery)

        # tags 特殊处理
        tags_data = []
        if query.tags:
            if request.method == 'POST' and request.is_json:
                data = request.get_json() or {}
                tags_data = data.get('tags', [])
            else:
                tags_data = [{'name': t, 'mode': 'and'} for t in query.tags]

        return {
            'keyword': query.keyword,
            'format_': query.format,
            'audio_type': query.audio_type,
            'sample_rate': query.sample_rate,
            'duration': query.duration,
            'tags_data': tags_data,
            'direction': query.direction,
            'algorithm_type': query.algorithm_type,
        }

    @staticmethod
    def get_all_ids():
        
        params = AudioQueryService._parse_id_query_params()
        result = _audio_acl.get_all_ids(params)
        if result.get('success'):
            data = result.get('data') or {}
            ids = data.get('ids', [])
            return success_response(AudioIdsData(ids=ids, total=len(ids)))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # 音频流式播放 (支持 Range 请求)
    @staticmethod
    def stream(audio_id):
        
        query = _parse_query_params(AudioStreamQuery)
        result = _audio_acl.stream_audio(audio_id, {'task_type': query.task_type})
        if result.get('success'):
            data = result.get('data') or {}
            url = data.get('url')
            if url:
                return {"url": url}
        return wrap_grpc_response(
            result,
            default_error_msg='音频不存在',
            error_code_mapping={404: ('音频不存在', 404)},
        )

    @staticmethod
    def stream_by_path():
        """通过 OSS key 获取预签名 URL 播放音频"""

        query = _parse_query_params(AudioStreamByPathQuery)
        if not query.path:
            return error_response("未提供路径", 400)

        result = _audio_acl.stream_audio_by_path({'path': query.path})
        if result.get('success'):
            data = result.get('data') or {}
            url = data.get('url')
            if url:
                return {"url": url}
        return wrap_grpc_response(
            result,
            default_error_msg='获取音频失败',
            error_code_mapping={404: ('获取音频失败', 404)},
        )

    # 本地存储降级模式的音频字节流下载（stream 预签名 URL 的回退地址，
    # INT-146 缺陷4：本地模式 get_url 返回 None，网关须补此路由承载回退）
    @staticmethod
    def download():
        query = _parse_query_params(AudioDownloadQuery)
        if not query.path:
            return error_response("未提供路径", 400)

        from shared.infrastructure.config import BaseConfig
        from api_gateway.config.config import Config

        oss_key = query.path
        # 扩展名白名单校验（与 stream-by-path 口径一致）
        ext = os.path.splitext(oss_key)[1].lower().lstrip('.')
        if ext not in _AUDIO_EXT_CONTENT_TYPES:
            return error_response("不支持的文件类型", code=403, http_code=403)

        # 路径安全：拒绝目录穿越段
        if '..' in oss_key.replace(chr(92), '/').split('/'):
            return error_response("路径不合法", code=403, http_code=403)

        if os.path.isabs(oss_key):
            # 绝对路径仅允许音频存储目录（上传合并输出）与本地降级存储根目录
            allowed_bases = []
            for base in (
                getattr(Config, 'AUDIO_STORAGE_PATH', ''),
                BaseConfig.STORAGE_LOCAL_ROOT,
            ):
                if base:
                    allowed_bases.append(os.path.realpath(base))
            normalized_path = os.path.realpath(oss_key)
            if not any(
                normalized_path == base or normalized_path.startswith(base + os.sep)
                for base in allowed_bases
            ):
                return error_response("路径不在允许的目录范围内", code=403, http_code=403)
            if not os.path.isfile(normalized_path):
                return error_response("音频文件不存在", code=404, http_code=404)
            with open(normalized_path, 'rb') as f:
                content = f.read()
        else:
            # 逻辑 key（local:// 或 oss:// 或裸 key）：走统一存储抽象，
            # OSS 失败自动回退本地降级副本
            from shared.infrastructure.storage import storage
            try:
                content = storage.load_bytes(
                    oss_key if oss_key.startswith(('oss://', 'local://'))
                    else storage.build_path('audios', oss_key))
            except FileNotFoundError:
                return error_response("音频文件不存在", code=404, http_code=404)
            except Exception as e:
                logger.error("audio download 读取存储失败: %s, key=%s", e, oss_key)
                return error_response("读取音频失败", code=500, http_code=500)

        return Response(content=content, media_type=_AUDIO_EXT_CONTENT_TYPES[ext])

    # 获取音频关联的算法
    @staticmethod
    def get_audio_algorithms(audio_id):
        
        result = _audio_acl.get_audio_algorithms(audio_id)
        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(
            result,
            default_error_msg='查询失败',
            error_code_mapping={404: ('查询失败', 404)},
        )

    @staticmethod
    def get_folder_tree():
        """获取音频文件夹树结构（支持筛选、懒加载）"""
        
        data = request.get_json() or {}

        keyword = data.get('keyword')
        audio_type = data.get('audio_type')
        format_ = data.get('format')
        sample_rate = data.get('sample_rate')
        duration = data.get('duration')
        tags_data = data.get('tags', [])
        direction = data.get('direction')
        algorithm_type = data.get('algorithm_type')
        parent_path = data.get('parent_path', '')
        depth = data.get('depth', 1)

        params = {
            'keyword': keyword,
            'audio_type': audio_type,
            'format_': format_,
            'sample_rate': sample_rate,
            'duration': duration,
            'tags_data': tags_data,
            'direction': direction,
            'algorithm_type': algorithm_type,
            'parent_path': parent_path,
            'depth': depth,
        }

        result = _audio_acl.get_folder_tree(params)
        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # 分页查询音频播放历史（INT-782#2）
    @staticmethod
    def get_playback_history(audio_id):
        """获取指定音频的播放历史（分页，播放时间倒序）。"""
        try:
            query = _parse_query_params(PlaybackHistoryQuery)
            params = query.model_dump(exclude_none=True)
        except Exception:
            params = {'page': 1, 'per_page': 10}

        result = _audio_acl.get_playback_history(audio_id, params)
        if result.get('success'):
            data = result.get('data') or {}
            items = data.get('items', [])
            history_items = [
                PlaybackHistoryItem(**item) if isinstance(item, dict) else item
                for item in items
            ]
            return success_response(
                PlaybackHistoryListData(
                    items=history_items,
                    total=data.get('total', 0),
                    page=data.get('page', params.get('page', 1)),
                    per_page=data.get('per_page', params.get('per_page', 10)),
                    pages=data.get('pages', 0),
                )
            )
        return wrap_grpc_response(
            result,
            default_error_msg='查询播放历史失败',
            error_code_mapping={404: ('音频不存在', 404)},
        )
