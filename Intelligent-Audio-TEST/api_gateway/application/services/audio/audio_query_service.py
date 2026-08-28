import logging
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
)
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()


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
            return success_response(AudioTagListData(items=items, total=len(items)))
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
