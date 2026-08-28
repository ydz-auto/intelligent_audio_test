"""测试用例查询读侧 Service（CQRS Query Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from shared.utils.status_constants import TaskStatus
from api_gateway.infrastructure.acl import (
    AudioAclRepositoryImpl,
    PlaybackAclRepositoryImpl,
    TaskConfigAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
)
from api_gateway.schemas.testcase import (
    TagListData,
    TestCaseAudioConfigItem,
    TestCaseDetailData,
    TestCaseDimensionBrief,
    TestCaseListItem,
    TestCaseListData,
    TestCaseListQuery,
    TestCasePreviewData,
    TestCaseStatsData,
)
from shared.utils import testcase_helpers as common

logger = logging.getLogger(__name__)

_testcase_acl = TestCaseConfigAclRepositoryImpl()
_audio_acl = AudioAclRepositoryImpl()
_task_acl = TaskConfigAclRepositoryImpl()
_playback_acl = PlaybackAclRepositoryImpl()


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class TestCaseQueryService:
    """测试用例查询读侧 Service（CQRS Query Side）。

    网关侧只做参数提取 + gRPC 调用 + Pydantic 包装，不直接操作 DB。
    """

    @staticmethod
    def get_all():
        query = _parse_query_params(TestCaseListQuery)
        page = query.page
        per_page = query.per_page
        keyword = query.keyword
        tag_name = query.tag
        group_id = query.group_id
        test_type = query.test_type
        algorithm_type = query.algorithm_type
        view = query.view
        include_deleted = query.include_deleted

        result = _testcase_acl.list_testcases(
            page=page,
            per_page=per_page,
            keyword=keyword,
            tag=tag_name,
            group_id=group_id,
            test_type=test_type,
            algorithm_type=algorithm_type,
            view=view,
            include_deleted=include_deleted,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}

        # 标签视图：按标签聚合返回
        if view == 'tag':
            # raw 结构: {items: [{tag, testCases: [...]}], total, page, per_page, pages}
            return success_response(raw)

        # 普通列表视图
        items = []
        for item in raw.get('items', []):
            items.append(
                TestCaseListItem(
                    id=item.get('id'),
                    name=item.get('name'),
                    description=item.get('description'),
                    group_id=item.get('group_id'),
                    group_name=item.get('group_name'),
                    type=item.get('type'),
                    tags=item.get('tags', []),
                    config=item.get('config') or {},
                    algorithm_params=item.get('algorithm_params'),
                    reference_params=item.get('reference_params'),
                    algorithm_type=item.get('algorithm_type'),
                    created_at=item.get('created_at'),
                    updated_at=item.get('updated_at'),
                    total_duration=item.get('total_duration'),
                )
            )

        return success_response(
            TestCaseListData(
                items=items,
                total=raw.get('total', 0),
                page=raw.get('page', page),
                per_page=raw.get('per_page', per_page),
                pages=raw.get('pages', 0),
            )
        )

    @staticmethod
    def get_one(tc_id):
        result = _testcase_acl.get_testcase_detail(tc_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到测试用例", 404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}

        # 构建 Pydantic 模型返回
        audios = [
            TestCaseAudioConfigItem(
                id=a.get('id'),
                audio_id=a.get('audio_id'),
                audio_name=a.get('audio_name'),
                test_type=a.get('test_type'),
                spl=a.get('spl'),
                playback_device_id=common.normalize_optional_int(a.get('playback_device_id')),
                play_order=a.get('play_order'),
            )
            for a in item.get('audios', [])
        ]

        dimensions = [
            TestCaseDimensionBrief(
                id=d.get('id'),
                name=d.get('name'),
                type=d.get('type'),
            )
            for d in item.get('dimensions', [])
        ]

        return success_response(
            TestCaseDetailData(
                id=item.get('id'),
                name=item.get('name'),
                description=item.get('description'),
                group_id=item.get('group_id'),
                group_name=item.get('group_name'),
                group=item.get('group'),
                type=item.get('type'),
                config=item.get('config') or {},
                algorithm_params=item.get('algorithm_params'),
                reference_params=item.get('reference_params'),
                algorithm_type=item.get('algorithm_type'),
                tags=item.get('tags', []),
                audios=audios,
                dimensions=dimensions,
                created_at=item.get('created_at'),
                updated_at=item.get('updated_at'),
                total_duration=item.get('total_duration'),
            )
        )

    @staticmethod
    def preview(tc_id):
        """预览测试用例：支持前端播放和后端播放两种模式

        - frontend: 返回音频流URL，由前端浏览器播放
        - backend: 通过后端扬声器播放

        保留在网关侧：涉及跨服务编排（audio_service, playback_orchestrator），非纯 DB 操作。
        """
        # 通过 ACL 获取测试用例数据
        from api_gateway.schemas.testcase import TestCasePreviewRequest

        result = _testcase_acl.get_testcase_detail(tc_id)
        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到测试用例", 404)
            return error_response(result.get('message', '查询失败'))

        tc = result.get('data') or {}
        if not tc:
            return error_response("未找到测试用例", 404)

        req_data = TestCasePreviewRequest.model_validate(request.get_json() or {})

        offset = req_data.offset
        preview_type = req_data.preview_type
        playback_mode = req_data.playback_mode or 'backend'

        config = tc.get('config') or {}

        # 注入 algorithm_params 到 config
        # 优先从独立列读，兼容旧数据从 config 读
        algorithm_params = tc.get('algorithm_params')
        algorithm_params_dict = common.get_algorithm_params_dict_for_columns(algorithm_params, 1) if algorithm_params else None
        if not algorithm_params_dict:
            algorithm_params_dict = common.get_algorithm_params_dict_for_executor(config)
        if algorithm_params_dict:
            config = config.copy() if config else {}
            config['algorithm_params'] = algorithm_params_dict

        # 从 rounds 获取音频
        audios_config = common.collect_audios(config)

        # 1. 检查音频配置
        if not audios_config:
            return error_response("用例未配置任何音频资源，无法预览")

        # 新双记录架构：记录已是单类型，直接使用所有音频
        # preview_type 保留用于向后兼容，但优先使用记录的 test_type
        preview_audios = audios_config

        if not preview_audios:
            return error_response("用例未配置有效的音频资源")

        # 获取所有有效音频的ID（多轮可能有多个音频）
        audio_ids = []
        seen_ids = set()
        for audio_config in preview_audios:
            audio_id = audio_config.get('audio_id') or audio_config.get('audioId')
            if audio_id and audio_id not in seen_ids:
                audio_ids.append(audio_id)
                seen_ids.add(audio_id)

        if not audio_ids:
            return error_response("用例未配置有效的音频ID")

        first_audio_id = audio_ids[0]

        # 计算总时长（所有音频时长之和）
        from api_gateway.infrastructure.grpc_proxies import algorithm_query_service as _algo_svc
        _overlap_params = _algo_svc.normalize_algorithm_params(config.get('algorithm_params', {})) if config else {}
        try:
            overlap_time = max(0.0, float(_overlap_params.get('overlap_time', 0))) if config else 0
        except (ValueError, TypeError):
            overlap_time = 0
        try:
            overlap_rate = max(0.0, min(1.0, float(_overlap_params.get('overlap_rate', 0)))) if config else 0
        except (ValueError, TypeError):
            overlap_rate = 0

        total_duration = 0
        try:
            # 通过 ACL 获取音频信息
            for aid in audio_ids:
                res = _audio_acl.get_one(aid)
                if res.get('success'):
                    rec = res.get('data') or {}
                    if rec.get('duration'):
                        total_duration += rec.get('duration')
        except Exception:
            logger.warning("预览用例 %s 时获取音频总时长失败", tc_id, exc_info=True)

        # 前端播放模式：返回所有音频的预签名 URL，前端连续播放
        if playback_mode == 'frontend':
            from shared.infrastructure.storage import storage

            # 生成预签名 URL 的辅助函数（兼容旧数据裸 OSS key）
            def _make_presigned_url(file_path):
                path = file_path if file_path.startswith(('oss://', 'local://')) else storage.build_path('audios', file_path)
                url = storage.get_url(path, expires=3600)
                return url or f'/api/audio/download?path={file_path}'

            audio_stream_urls = []
            for aid in audio_ids:
                res = _audio_acl.get_one(aid)
                if res.get('success'):
                    rec = res.get('data') or {}
                    file_path = rec.get('file_path')
                    if file_path:
                        audio_stream_urls.append(_make_presigned_url(file_path))

            if not audio_stream_urls:
                return error_response("音频文件不存在", 404)

            # 兼容：单个音频时也填 audio_stream_url
            audio_stream_url = audio_stream_urls[0] if audio_stream_urls else None

            return success_response(
                TestCasePreviewData(
                    test_case_id=tc_id,
                    preview_task_id=None,
                    status="frontend_preview_ready",
                    message="前端播放模式，返回音频流URL",
                    duration=total_duration,
                    playback_mode='frontend',
                    audio_id=first_audio_id,
                    audio_stream_url=audio_stream_url,
                    audio_stream_urls=audio_stream_urls if len(audio_stream_urls) > 1 else None,
                )
            )

        # 后端播放模式：检查E2E任务并执行播放
        # 通过 gRPC 检查是否有运行中的 E2E 任务（替代直连 task_service PO）
        def _has_running_e2e_tasks():
            for st in (TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.RUNNING):
                try:
                    r = _task_acl.list_tasks(page=1, per_page=1, status=st, task_type='e2e')
                    if r.get('success'):
                        raw = r.get('data') or {}
                        if raw.get('total', 0) > 0:
                            return True
                except Exception:
                    continue
            return False

        if _has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", 403)

        # 通过 ACL 调用音频引擎
        preview_task_id = f"PREVIEW_{tc_id}"

        # 停止之前的预览
        _audio_acl.stop_task_audio_by_pattern("PREVIEW_")

        # 清除设备缓存，强制重新扫描
        _audio_acl.clear_device_cache()

        import time
        time.sleep(0.2)

        # 初始化预览停止标志（共享于 common 模块）
        common.preview_stop_flags[tc_id] = False

        try:
            # 通过 ACL 调用播放编排
            preview_result = _playback_acl.preview(
                audio_configs=preview_audios,
                case_config=config,
                task_id=preview_task_id,
                offset=offset,
                overlap_rate=overlap_rate,
                overlap_time=overlap_time,
            )
            if not preview_result or not preview_result.result_data:
                return error_response("用例未配置有效的干声音频")

            total_duration = preview_result.result_data.get('total_duration', 0)
            common.log(
                'info',
                f"Previewing test case {tc_id}: offset={offset}, duration={total_duration:.2f}s",
                test_case_id=tc_id,
                category='preview',
            )

            return success_response(
                TestCasePreviewData(
                    test_case_id=tc_id,
                    preview_task_id=preview_task_id,
                    status="preview_started",
                    message="已启动用例预览放音",
                    duration=total_duration,
                    playback_mode='backend',
                    audio_id=first_audio_id,
                    audio_stream_url=None,
                )
            )
        except Exception as e:
            return error_response(f"预览失败: {str(e)}")

    @staticmethod
    def get_stats():
        result = _testcase_acl.get_testcase_stats()

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        data = result.get('data') or {}
        return success_response(TestCaseStatsData(**data))

    @staticmethod
    def get_tags():
        result = _testcase_acl.get_testcase_tags()

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        data = result.get('data') or {}
        tag_names = data.get('items', [])
        return success_response(TagListData(items=tag_names))

    @staticmethod
    def get_ref_params(tc_id, round_number):
        """获取指定用例指定轮的参考参数文件内容"""
        result = _testcase_acl.get_testcase_ref_params(tc_id, round_number)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到测试用例'), 404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    @staticmethod
    def fetch_case_ids():
        """按筛选条件返回全量用例ID（不分页）"""
        data = request.get_json() or {}
        result = _testcase_acl.fetch_case_ids(data)

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))
