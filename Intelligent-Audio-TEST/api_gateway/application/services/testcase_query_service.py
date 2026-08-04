"""测试用例查询读侧 Service。

从 TestCaseController 抽取的只读查询方法。
"""
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import TestCase, Tag, Audio
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
from sqlalchemy.orm import joinedload

from api_gateway.schemas.testcase import (
    TagListData,
    TestCaseAudioConfigItem,
    TestCaseDetailData,
    TestCaseDimensionBrief,
    TestCaseListItem,
    TestCaseListData,
    TestCasePreviewData,
    TestCaseStatsData,
)
from api_gateway.application.services import testcase_common as common


class TestCaseQueryService:
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        keyword = request.args.get('keyword')
        tag_name = request.args.get('tag')
        group_id = request.args.get('group_id')
        test_type = request.args.get('type')
        algorithm_type = request.args.get('algorithm_type')
        view = request.args.get('view')
        include_deleted_raw = request.args.get('include_deleted', 'false')
        include_deleted = str(include_deleted_raw).lower() in ('true', '1', 'yes')

        # ===== 标签视图：按标签聚合返回 =====
        if view == 'tag':
            return TestCaseQueryService._get_tag_view(
                page=page, per_page=per_page, keyword=keyword,
                test_type=test_type, algorithm_type=algorithm_type,
                include_deleted=include_deleted,
            )

        query = TestCase.query.options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags)
        ).order_by(TestCase.created_at.desc())
        if not include_deleted:
            query = query.filter(TestCase.deleted == False)

        if keyword:
            query = query.filter(
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        if tag_name:
            query = query.join(TestCase.tags).filter(Tag.name == tag_name)

        if group_id:
            query = query.filter(TestCase.group_id == group_id)

        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)

        # 按 test_type 列过滤（新双记录架构）
        if test_type and test_type in ['api', 'e2e']:
            query = query.filter(TestCase.test_type == test_type)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        test_cases = pagination.items

        audio_ids = set()
        for tc in test_cases:
            config = tc.config or {}
            for audio_item in common.collect_audios(config):
                aid = audio_item.get('audio_id')
                if aid is not None:
                    audio_ids.add(aid)

        audio_map = {}
        if audio_ids:
            audio_list = Audio.query.filter(Audio.id.in_(audio_ids)).all()
            audio_map = {a.id: a for a in audio_list}

        data = []
        for tc in test_cases:
            config = tc.config or {}
            # 直接使用 test_type 列，不再从音频配置推导
            tc_test_type = tc.test_type or 'api'

            # 计算时长：根据记录的 test_type 分配
            total_duration = 0.0
            for audio_item in common.collect_audios(config):
                audio_id = audio_item.get('audio_id')
                if audio_id:
                    audio = audio_map.get(audio_id)
                    if audio and audio.duration:
                        total_duration += float(audio.duration)

            data.append(
                TestCaseListItem(
                    id=tc.id,
                    name=tc.name,
                    description=tc.description,
                    group_id=tc.group_id,
                    group_name=tc.group.name if tc.group else None,
                    type=tc_test_type,
                    tags=[tag.name for tag in tc.tags],
                    config=tc.config.copy() if tc.config else {},
                    algorithm_params=tc.algorithm_params,
                    reference_params=tc.reference_params,
                    algorithm_type=tc.algorithm_type,
                    created_at=tc.created_at.isoformat() if tc.created_at else None,
                    updated_at=tc.updated_at.isoformat() if tc.updated_at else None,
                    total_duration=round(total_duration, 2) if total_duration > 0 else None,
                )
            )

        return success_response(
            TestCaseListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    @staticmethod
    def _get_tag_view(page=1, per_page=10, keyword=None, test_type=None, algorithm_type=None, include_deleted=False):
        """标签视图：按标签聚合用例，分页返回标签维度。

        返回结构：
        {
            "items": [
                { "tag": "男声", "testCases": [TestCaseListItem, ...] },
                ...
            ],
            "total": <标签总数>,
            "page": 1,
            "per_page": 20,
            "pages": <总页数>
        }
        """
        # 1. 分页查询标签（按名称排序）
        tag_query = Tag.query.order_by(Tag.name)
        tag_pagination = tag_query.paginate(page=page, per_page=per_page, error_out=False)
        page_tags = tag_pagination.items

        items = []
        if not page_tags:
            return success_response({
                "items": [],
                "total": tag_pagination.total,
                "page": tag_pagination.page,
                "per_page": tag_pagination.per_page,
                "pages": tag_pagination.pages,
            })

        # 2. 一次性查询所有分页标签关联的用例（避免 N+1）
        tag_ids = [t.id for t in page_tags]
        tc_query = TestCase.query.options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags),
        ).join(TestCase.tags).filter(Tag.id.in_(tag_ids))

        if not include_deleted:
            tc_query = tc_query.filter(TestCase.deleted == False)
        if keyword:
            tc_query = tc_query.filter(
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if test_type and test_type in ['api', 'e2e']:
            tc_query = tc_query.filter(TestCase.test_type == test_type)
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

        test_cases = tc_query.all()

        # 3. 收集音频 ID，批量查询音频时长（避免逐条查询）
        audio_ids = set()
        for tc in test_cases:
            config = tc.config or {}
            for audio_item in common.collect_audios(config):
                aid = audio_item.get('audio_id')
                if aid is not None:
                    audio_ids.add(aid)

        audio_map = {}
        if audio_ids:
            audio_list = Audio.query.filter(Audio.id.in_(audio_ids)).all()
            audio_map = {a.id: a for a in audio_list}

        # 4. 按标签分组聚合用例
        cases_by_tag = {t.id: [] for t in page_tags}
        for tc in test_cases:
            for t in tc.tags:
                if t.id in cases_by_tag:
                    cases_by_tag[t.id].append(tc)

        for tag in page_tags:
            case_list = []
            for tc in cases_by_tag.get(tag.id, []):
                config = tc.config or {}
                total_duration = 0.0
                for audio_item in common.collect_audios(config):
                    audio_id = audio_item.get('audio_id')
                    if audio_id:
                        audio = audio_map.get(audio_id)
                        if audio and audio.duration:
                            total_duration += float(audio.duration)
                case_list.append({
                    "id": tc.id,
                    "name": tc.name,
                    "description": tc.description,
                    "groupId": tc.group_id,
                    "groupName": tc.group.name if tc.group else None,
                    "type": tc.test_type or 'api',
                    "tags": [t.name for t in tc.tags],
                    "config": tc.config.copy() if tc.config else {},
                    "algorithmParams": tc.algorithm_params,
                    "referenceParams": tc.reference_params,
                    "algorithmType": tc.algorithm_type,
                    "createdAt": tc.created_at.isoformat() if tc.created_at else None,
                    "updatedAt": tc.updated_at.isoformat() if tc.updated_at else None,
                    "totalDuration": round(total_duration, 2) if total_duration > 0 else None,
                })

            items.append({
                "tag": tag.name,
                "testCases": case_list,
            })

        return success_response({
            "items": items,
            "total": tag_pagination.total,
            "page": tag_pagination.page,
            "per_page": tag_pagination.per_page,
            "pages": tag_pagination.pages,
        })

    @staticmethod
    def get_one(tc_id):
        from shared.models.models import TestCase, Audio, Dimension
        from shared.models.database import db
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        config = tc.config or {}
        tc_test_type = tc.test_type or 'api'

        # 从config中提取音频配置
        audios = []
        for i, audio_item in enumerate(common.collect_audios(config)):
            audio = db.session.get(Audio, audio_item.get('audio_id'))
            audios.append(
                TestCaseAudioConfigItem(
                    id=i,
                    audio_id=audio_item.get('audio_id'),
                    audio_name=audio.name if audio else None,
                    test_type=tc_test_type,
                    spl=audio_item.get('spl'),
                    playback_device_id=common.normalize_optional_int(audio_item.get('playback_device_id')),
                    play_order=audio_item.get('play_order'),
                )
            )

        # 从config中提取评测维度配置（兼容新旧格式）
        dimensions = []
        dim_config = common.collect_dimensions(config)
        dimension_ids = []

        for item in dim_config:
            if isinstance(item, dict):
                dim_id = item.get('id')
                if dim_id:
                    dimension_ids.append(dim_id)
            else:
                dimension_ids.append(item)

        # 去重
        unique_dimension_ids = list(set(dimension_ids))
        for dim_id in unique_dimension_ids:
            dim = db.session.get(Dimension, dim_id)
            if dim:
                dimensions.append(TestCaseDimensionBrief(id=dim.id, name=dim.name, type=dim.type))

        # 计算时长（兼容新旧格式）
        total_duration = 0.0
        for audio_item in common.collect_audios(config):
            audio_id = audio_item.get('audio_id')
            if audio_id:
                audio = db.session.get(Audio, audio_id)
                if audio and audio.duration:
                    total_duration += float(audio.duration)

        # Debug logging
        import json as json_debug
        log_not_emit('DEBUG', 'testcase_controller', f'get_one: tc.id={tc.id}, config type={type(config)}, is None={config is None}, is empty={config == {}}', category='testcase')
        if isinstance(config, dict):
            log_not_emit('DEBUG', 'testcase_controller', f'get_one: config keys={list(config.keys())}, JSON={json_debug.dumps(config, ensure_ascii=False)[:300]}', category='testcase')

        # Create TestCaseDetailData and check config
        detail_data = TestCaseDetailData(
            id=tc.id,
            name=tc.name,
            description=tc.description,
            group_id=tc.group_id,
            group_name=tc.group.name if tc.group else None,
            group={"id": tc.group.id, "name": tc.group.name} if tc.group else None,
            type=tc_test_type,
            config=config,
            algorithm_params=getattr(tc, 'algorithm_params', None),
            reference_params=getattr(tc, 'reference_params', None),
            algorithm_type=tc.algorithm_type,
            tags=[tag.name for tag in tc.tags],
            audios=audios,
            dimensions=dimensions,
            created_at=tc.created_at.isoformat() if tc.created_at else None,
            updated_at=tc.updated_at.isoformat() if tc.updated_at else None,
            total_duration=round(total_duration, 2) if total_duration > 0 else None,
        )

        dumped = detail_data.model_dump(by_alias=True)
        log_not_emit('DEBUG', 'testcase_controller', f'get_one: dumped config={json_debug.dumps(dumped.get("config"), ensure_ascii=False)[:300]}', category='testcase')

        return success_response(detail_data)

    @staticmethod
    def preview(tc_id):
        """预览测试用例：支持前端播放和后端播放两种模式

        - frontend: 返回音频流URL，由前端浏览器播放
        - backend: 通过后端扬声器播放
        """
        from shared.models.models import TestCase
        from shared.utils.task_utils import has_running_e2e_tasks
        from api_gateway.schemas.testcase import TestCasePreviewRequest
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        req_data = TestCasePreviewRequest.model_validate(request.get_json() or {})

        offset = req_data.offset
        preview_type = req_data.preview_type
        playback_mode = req_data.playback_mode or 'backend'

        config = tc.config or {}

        # 注入 algorithm_params 到 config
        # 优先从独立列读，兼容旧数据从 config 读
        algorithm_params = common.get_algorithm_params_dict_for_columns(tc.algorithm_params, 1)
        if not algorithm_params:
            algorithm_params = common.get_algorithm_params_dict_for_executor(config)
        if algorithm_params:
            config = config.copy() if config else {}
            config['algorithm_params'] = algorithm_params

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
        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_time = CaseParameterExtractor.get_overlap_time(config) if config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(config) if config else 0

        total_duration = 0
        try:
            from shared.models.models import Audio
            for aid in audio_ids:
                rec = Audio.query.filter_by(id=aid, deleted=False).first()
                if rec and rec.duration:
                    total_duration += rec.duration
        except:
            pass

        # 前端播放模式：返回所有音频的预签名 URL，前端连续播放
        if playback_mode == 'frontend':
            from shared.infrastructure.storage import storage
            from shared.models.models import Audio

            # 生成预签名 URL 的辅助函数（兼容旧数据裸 OSS key）
            def _make_presigned_url(file_path):
                path = file_path if file_path.startswith(('oss://', 'local://')) else storage.build_path('audios', file_path)
                url = storage.get_url(path, expires=3600)
                return url or f'/api/audio/download?path={file_path}'

            audio_stream_urls = []
            for aid in audio_ids:
                rec = Audio.query.filter_by(id=aid, deleted=False).first()
                if rec and rec.file_path:
                    audio_stream_urls.append(_make_presigned_url(rec.file_path))

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
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", 403)

        # 跨服务调用：通过 gRPC AudioService 调用音频引擎
        from api_gateway.infrastructure.grpc_proxies import audio_service
        # 跨服务调用：通过 gRPC AudioService 的 SPL 测量
        from api_gateway.infrastructure.grpc_proxies import spl_service
        from shared.models.models import PlaybackDevice, Audio

        preview_task_id = f"PREVIEW_{tc_id}"

        # 停止之前的预览
        audio_service.stop_task_audio_by_pattern("PREVIEW_")

        # 清除设备缓存，强制重新扫描
        audio_service._device_cache = None

        import time
        time.sleep(0.2)

        # 初始化预览停止标志（共享于 common 模块）
        common.preview_stop_flags[tc_id] = False

        try:
            # 跨服务调用：通过 gRPC PlaybackService 调用播放编排
            from api_gateway.infrastructure.grpc_proxies import playback_orchestrator

            preview_result = playback_orchestrator.preview(
                audio_configs=preview_audios,
                case_config=config,
                task_id=preview_task_id,
                offset=offset,
                overlap_rate=overlap_rate,
                overlap_time=overlap_time,
            )
            if not preview_result:
                return error_response("用例未配置有效的干声音频")

            total_duration = preview_result.get('total_duration', 0)
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
        from shared.models.models import TestCase, TestCaseGroup
        from shared.models.database import db
        from api_gateway.schemas.testcase import TestCaseStatsData
        try:
            total_count = TestCase.query.filter_by(deleted=False).count()

            # 按分组统计
            group_stats = db.session.query(
                TestCaseGroup.name, db.func.count(TestCase.id)
            ).join(TestCase, TestCase.group_id == TestCaseGroup.id)\
             .filter(TestCase.deleted == False)\
             .group_by(TestCaseGroup.name).all()

            # 最近更新 (前5条)
            recent_updates = TestCase.query.filter_by(deleted=False)\
                .order_by(TestCase.updated_at.desc())\
                .limit(5).all()

            return success_response(
                TestCaseStatsData(
                    total_count=total_count,
                    by_group={name: count for name, count in group_stats},
                    recent_updates=[
                        {"id": tc.id, "name": tc.name, "updated_at": tc.updated_at.isoformat()}
                        for tc in recent_updates
                    ],
                )
            )
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def get_tags():
        from shared.models.models import Tag
        from api_gateway.schemas.testcase import TagListData
        try:
            # 查询所有标签
            tags = Tag.query.order_by(Tag.updated_at.desc()).all()

            # 提取标签名称列表
            tag_names = [tag.name for tag in tags]

            return success_response(TagListData(items=tag_names))
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def get_ref_params(tc_id, round_number):
        """获取指定用例指定轮的参考参数文件内容"""
        from shared.models.models import TestCase
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        config = tc.config or {}
        rounds = config.get('rounds', [])

        target_round = None
        for r in rounds:
            if isinstance(r, dict) and r.get('roundNumber') == round_number:
                target_round = r
                break

        if not target_round:
            return error_response(f"未找到第 {round_number} 轮", 404)

        ref_path = target_round.get('referenceParamsPath')
        if not ref_path:
            return error_response(f"第 {round_number} 轮未配置参考参数路径", 404)

        ref_data = ReferenceParamsGenerator.load_from_file(ref_path)
        if ref_data is None:
            return error_response(f"参考参数文件不存在或读取失败: {ref_path}", 404)

        return success_response({
            'roundNumber': round_number,
            'referenceParamsPath': ref_path,
            'referenceParams': ref_data
        })
