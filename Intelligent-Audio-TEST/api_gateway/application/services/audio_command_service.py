import logging
from sqlalchemy import cast, String
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from fastapi.responses import FileResponse
from shared.models.models import Audio, Tag, AudioAnnotation, AudioTag, TestCase
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from shared.infrastructure.storage import storage
from api_gateway.schemas.audio import (
    BatchActionRequest,
    BatchUpdateAnnotationsRequest,
    UpdateMetadataRequest,
)
from api_gateway.application.services.audio_convert_service import AudioConvertService

logger = logging.getLogger(__name__)


class AudioCommandService:
    # 元数据管理
    @staticmethod
    def update_metadata(audio_id):
        audio = db.session.get(Audio, audio_id)
        if not audio or audio.deleted:
            return error_response("未找到音频文件", 404)

        data = request.get_json() or {}
        try:
            validated = UpdateMetadataRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        try:
            if validated.name is not None:
                audio.name = validated.name
            if validated.audio_type is not None:
                audio.audio_type = validated.audio_type
            if validated.asr_text is not None:
                audio.asr_text = validated.asr_text
            if validated.description is not None:
                audio.description = validated.description
            if validated.source_language is not None:
                audio.source_language = validated.source_language

            if validated.tags is not None:
                AudioTag.query.filter_by(audio_id=audio_id).delete()

                if validated.tags:
                    tags = validated.tags.split(',')
                    for tag_name in tags:
                        tag_name = tag_name.strip()
                        if tag_name:
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                                db.session.flush()

                            audio_tag = AudioTag(audio_id=audio_id, tag_id=tag.id)
                            db.session.add(audio_tag)

            if validated.annotations is not None:
                AudioAnnotation.query.filter_by(audio_id=audio_id).delete()

                for ann in validated.annotations:
                    ann_format = ann.get('format', 'json')
                    ann_data = ann.get('data', {})
                    ann_code = ann.get('code', '')
                    ann_source_lang = ann.get('source_language', '')
                    ann_target_lang = ann.get('target_language', '')

                    new_annotation = AudioAnnotation(
                        audio_id=audio_id,
                        format=ann_format,
                        code=ann_code,
                        data=ann_data,
                        source_language=ann_source_lang,
                        target_language=ann_target_lang
                    )
                    db.session.add(new_annotation)

            audio.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "元数据更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量更新标注
    @staticmethod
    def batch_update_annotations():
        """批量更新音频标注，可选刷新关联测试用例的参数和参考参数。

        前端按文件名匹配已入库音频，构建 [{audio_id, annotations}] 列表提交。
        后端逐个写标注（同 code 覆盖），然后按 audio_id 反查 TestCase 刷新。
        """
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchUpdateAnnotationsRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        if not validated.items:
            return error_response("标注列表不能为空")

        algorithm_type = validated.algorithm_type
        refresh_test_cases = validated.refresh_test_cases

        updated_audio_ids = []
        updated_count = 0
        failed_count = 0
        refreshed_tc_ids = []

        try:
            for item in validated.items:
                audio_id = item.audio_id
                annotations = item.annotations
                if not annotations:
                    continue

                audio = db.session.get(Audio, audio_id)
                if not audio or audio.deleted:
                    failed_count += 1
                    continue

                # 复用已有的持久化逻辑：写标注 + 返回 raw_annotations
                AudioConvertService._persist_annotations_and_raw(
                    audio_id, annotations, algorithm_type
                )
                updated_audio_ids.append(audio_id)
                updated_count += 1

            db.session.flush()

            # 刷新关联测试用例
            if refresh_test_cases and updated_audio_ids:
                refreshed_tc_ids = AudioCommandService._refresh_test_cases_for_audios(
                    updated_audio_ids, algorithm_type
                )

            db.session.commit()

            return success_response({
                "updated_count": updated_count,
                "failed_count": failed_count,
                "refreshed_test_case_ids": refreshed_tc_ids,
            }, f"批量更新标注成功，更新 {updated_count} 个音频，刷新 {len(refreshed_tc_ids)} 个用例")
        except Exception as e:
            db.session.rollback()
            import traceback
            from shared.utils.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'批量更新标注失败: {str(e)}\n{traceback.format_exc()}',
                category='audio',
            )
            return error_response(str(e))

    @staticmethod
    def _refresh_test_cases_for_audios(audio_ids, algorithm_type=None):
        """按 audio_id 反查 config.rounds[].audios[].audio_id 关联的 TestCase，
        重新提取用例参数并刷新参考参数。

        Returns: 刷新的 TestCase id 列表
        """
        import json as _json
        from shared.models.algorithm_models import CaseAlgorithmParam

        # 查所有未删除的 TestCase，过滤出 config.rounds 中包含目标 audio_id 的
        all_tcs = TestCase.query.filter_by(deleted=False).all()
        target_ids = set(audio_ids)
        affected_tcs = []

        for tc in all_tcs:
            config = tc.config or {}
            rounds = config.get('rounds', [])
            if not isinstance(rounds, list):
                continue
            found = False
            for round_item in rounds:
                if not isinstance(round_item, dict):
                    continue
                for audio_item in round_item.get('audios', []):
                    if isinstance(audio_item, dict) and audio_item.get('audio_id') in target_ids:
                        found = True
                        break
                if found:
                    break
            if found:
                affected_tcs.append(tc)

        if not affected_tcs:
            return []

        refreshed_ids = []
        for tc in affected_tcs:
            tc_algo_type = algorithm_type or tc.algorithm_type
            # 重新提取用例参数
            if tc_algo_type:
                case_params_list = CaseAlgorithmParam.query.filter_by(
                    algorithm_type=tc_algo_type, deleted=False
                ).all()
                tc_test_type = tc.test_type or 'api'
                scoped_params = [
                    p for p in case_params_list
                    if p.scope == 'common' or p.scope == tc_test_type
                ]

                if scoped_params:
                    # 收集该用例所有轮的 audio_id → annotation 映射
                    config = tc.config or {}
                    rounds = config.get('rounds', [])
                    algo_params_col = tc.algorithm_params or []

                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        round_number = round_item.get('round_number', 1)
                        round_audios = round_item.get('audios', [])
                        if not isinstance(round_audios, list):
                            continue

                        round_audio_ids = [
                            a.get('audio_id') for a in round_audios
                            if isinstance(a, dict) and a.get('audio_id')
                        ]
                        if not round_audio_ids:
                            continue

                        # 从数据库查这些音频的最新标注
                        raw_anns = []
                        for aid in round_audio_ids:
                            anns = AudioAnnotation.query.filter_by(
                                audio_id=aid, deleted=False
                            ).all()
                            for ann in anns:
                                raw_anns.append({
                                    'code': ann.code,
                                    'data': ann.data,
                                })

                        if not raw_anns:
                            continue

                        # 提取参数（复用 _create_test_case_from_audio 中的逻辑）
                        extracted_params = []
                        for param in scoped_params:
                            param_code = param.param_code
                            field_path = param.field_path or param_code
                            ann_code = param.annotation_code or tc_algo_type
                            matched_anns = [a for a in raw_anns if a.get('code') == ann_code]
                            if not matched_anns:
                                matched_anns = raw_anns
                            value = None
                            for ann in matched_anns:
                                a_data = ann.get('data')
                                if a_data is None:
                                    continue
                                if isinstance(a_data, str):
                                    value = a_data
                                    break
                                if isinstance(a_data, dict):
                                    effective_fp = field_path
                                    if 'segments[]' not in effective_fp:
                                        effective_fp = f'segments[].{effective_fp}'
                                    if 'segments[]' in effective_fp:
                                        parts = effective_fp.split('[].')
                                        arr_key = parts[0]
                                        field_key = parts[1] if len(parts) > 1 else None
                                        def _get_seg_field(seg, key):
                                            if seg.get(key) is not None:
                                                return seg.get(key)
                                            import re
                                            snake = re.sub(r'([A-Z])', r'_\1', key).lower()
                                            return seg.get(snake)
                                        arr = a_data.get(arr_key, [])
                                        if isinstance(arr, list) and field_key:
                                            collected = [
                                                _get_seg_field(seg, field_key) for seg in arr
                                                if isinstance(seg, dict) and _get_seg_field(seg, field_key) is not None
                                            ]
                                            if collected:
                                                value = collected[0] if len(collected) == 1 else collected
                                                break
                            if value is not None:
                                extracted_params.append({
                                    'field_code': param_code,
                                    'field_value': value
                                })

                        # 合并到 algo_params_col 中对应轮（保留已有参数，补缺新提取的）
                        round_ap_entry = None
                        for entry in algo_params_col:
                            if entry.get('round_number') == round_number:
                                round_ap_entry = entry
                                break
                        if not round_ap_entry:
                            round_ap_entry = {'round_number': round_number, 'params': []}
                            algo_params_col.append(round_ap_entry)
                        existing_codes = set(
                            p.get('field_code') for p in round_ap_entry.get('params', [])
                        )
                        for p in extracted_params:
                            if p['field_code'] not in existing_codes:
                                round_ap_entry.setdefault('params', []).append(p)
                                existing_codes.add(p['field_code'])

                    tc.algorithm_params = algo_params_col

            # 刷新参考参数
            try:
                from api_gateway.application.services.testcase_command_service import TestCaseCommandService
                TestCaseCommandService.refresh_reference_texts(tc)
                refreshed_ids.append(tc.id)
            except Exception as e:
                logger.warning(f'刷新用例 {tc.id} 参考参数失败: {e}')

        return refreshed_ids

    # 批量操作
    @staticmethod
    def batch_action():
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchActionRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        audio_ids = validated.audio_ids
        action = validated.action

        try:
            if action == 'delete':
                # 批量删除音频文件
                from shared.models.models import TestCase, Device, Task, AudioAnnotation, AudioTag
                import os

                # 收集可删除的音频ID和被引用的音频ID
                deletable_audio_ids = []
                skipped_audio_ids = []

                # 检查每个音频文件是否被引用
                for audio_id in audio_ids:
                    is_referenced = False

                    # 1. 检查测试用例音频关联（在config.audios中）
                    test_case_count = TestCase.query.filter(
                        TestCase.deleted == False,
                        cast(TestCase.config, String).like(f'%"audio_id": {audio_id}%')
                    ).count()
                    if test_case_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue

                    # 2. 检查测试用例背景噪音引用（在config.background_noise中）
                    test_case_noise_count = TestCase.query.filter(
                        TestCase.deleted == False,
                        cast(TestCase.config, String).like(f'%"background_noise": {{"audio_id": {audio_id}}}%')
                    ).count()
                    if test_case_noise_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue

                    # 3. 检查设备提示词音频引用
                    device_count = Device.query.filter(
                        cast(Device.prompt_config, String).like(f'%{audio_id}%'),
                        Device.deleted == False
                    ).count()
                    if device_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue

                    # 4. 检查任务配置中的音频引用
                    task_count = Task.query.filter(
                        cast(Task.config, String).like(f'%{audio_id}%'),
                        Task.deleted == False
                    ).count()
                    if task_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue

                    # 如果没有被引用，添加到可删除列表
                    deletable_audio_ids.append(audio_id)

                # 如果没有可删除的音频，返回提示
                if not deletable_audio_ids:
                    return success_response(None, "没有可删除的音频文件，所有音频都被其他资源引用")

                # 获取所有要删除的音频文件
                audios = Audio.query.filter(Audio.id.in_(deletable_audio_ids), Audio.deleted == False).all()

                for audio in audios:
                    # 物理删除音频文件（storage.delete 会自动处理 oss:// / local:// 前缀）
                    try:
                        storage.delete(audio.file_path)
                    except Exception:
                        pass

                    # 删除关联的标注
                    AudioAnnotation.query.filter_by(audio_id=audio.id).delete()

                    # 删除关联的音频标签
                    AudioTag.query.filter_by(audio_id=audio.id).delete()

                # 软删除音频文件记录
                now = now_cst()
                Audio.query.filter(Audio.id.in_(deletable_audio_ids)).update(
                    {"deleted": True, "deleted_at": now, "updated_at": now},
                    synchronize_session=False
                )

                # 构建返回信息
                message = f"成功删除 {len(deletable_audio_ids)} 个音频文件"
                if skipped_audio_ids:
                    message += f"，跳过了 {len(skipped_audio_ids)} 个被引用的音频文件"
            elif action == 'export':
                # 批量导出为 ZIP
                import zipfile
                from io import BytesIO

                audios = Audio.query.filter(Audio.id.in_(audio_ids), Audio.deleted == False).all()
                memory_file = BytesIO()
                with zipfile.ZipFile(memory_file, 'w') as zf:
                    for audio in audios:
                        try:
                            local_path = storage.load_file(audio.file_path)
                            zf.write(local_path, audio.original_filename)
                        except Exception:
                            pass

                memory_file.seek(0)
                return FileResponse(
                    memory_file,
                    media_type='application/zip',
                    headers={"Content-Disposition": f"attachment; filename=audios_export_{now_cst().strftime('%Y%m%d%H%M%S')}.zip"}
                )
            elif action == 'tags':
                tags = validated.tags
                for audio_id in audio_ids:
                    audio = db.session.get(Audio, audio_id)
                    if audio and not audio.deleted:
                        # 清空旧标签并添加新标签 (简化处理)
                        from shared.models.models import AudioTag, Tag
                        AudioTag.query.filter_by(audio_id=audio_id).delete()
                        for tag_name in tags:
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                                db.session.flush()
                            db.session.add(AudioTag(audio_id=audio_id, tag_id=tag.id))

            db.session.commit()
            if action == 'delete':
                return success_response(None, message)
            else:
                return success_response(None, f"批量操作 {action} 执行成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除音频文件（逻辑删除）
    @staticmethod
    def delete(audio_id):
        audio = db.session.get(Audio, audio_id)
        if not audio or audio.deleted:
            return error_response("未找到音频文件", 404)

        try:
            # 检查是否有其他实体引用该音频文件
            # 1. 检查测试用例音频关联（在config.audios中）
            test_case_count = TestCase.query.filter(
                TestCase.deleted == False,
                cast(TestCase.config, String).like(f'%"audio_id": {audio_id}%')
            ).count()
            if test_case_count > 0:
                return error_response("该音频文件已被测试用例使用，禁止删除", 400)

            # 2. 检查测试用例背景噪音引用
            test_case_noise_count = TestCase.query.filter(
                TestCase.deleted == False,
                cast(TestCase.config, String).like(f'%"background_noise": {{"audio_id": {audio_id}}}%')
            ).count()
            if test_case_noise_count > 0:
                return error_response("该音频文件已被测试用例作为背景噪音使用，禁止删除", 400)

            # 3. 检查设备提示词音频引用
            from shared.models.models import Device
            device_count = Device.query.filter(
                cast(Device.prompt_config, String).like(f'%{audio_id}%'),
                Device.deleted == False
            ).count()
            if device_count > 0:
                return error_response("该音频文件已被设备作为提示词使用，禁止删除", 400)

            # 4. 检查任务配置中的音频引用
            from shared.models.models import Task
            task_count = Task.query.filter(
                cast(Task.config, String).like(f'%{audio_id}%'),
                Task.deleted == False
            ).count()
            if task_count > 0:
                return error_response("该音频文件已被任务使用，禁止删除", 400)

            # 物理删除音频文件（storage.delete 会自动处理 oss:// / local:// 前缀）
            try:
                storage.delete(audio.file_path)
            except Exception:
                pass

            # 删除关联的标注
            from shared.models.models import AudioAnnotation
            AudioAnnotation.query.filter_by(audio_id=audio_id).delete()

            # 删除关联的音频标签
            from shared.models.models import AudioTag
            AudioTag.query.filter_by(audio_id=audio_id).delete()

            # 软删除音频文件记录
            now = now_cst()
            audio.deleted = True
            audio.deleted_at = now
            audio.updated_at = now
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "音频文件已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新音频关联的算法
    @staticmethod
    def update_audio_algorithms(audio_id):
        try:
            from shared.models.models import AudioAlgorithmRelation
            from api_gateway.schemas.audio import UpdateAudioAlgorithmsRequest

            audio = db.session.get(Audio, audio_id)
            if not audio or audio.deleted:
                return error_response("音频不存在", 404)

            data = request.get_json() or {}
            try:
                validated = UpdateAudioAlgorithmsRequest.model_validate(data)
            except Exception as e:
                return error_response(f"参数验证失败: {e}")

            AudioAlgorithmRelation.query.filter_by(audio_id=audio_id).update({'deleted': True})

            for item in validated.algorithms:
                relation = AudioAlgorithmRelation(
                    audio_id=audio_id,
                    algorithm_type=item.algorithm_type,
                    is_primary=item.is_primary,
                    weight=item.weight,
                    params=item.params
                )
                db.session.add(relation)

            db.session.commit()
            return success_response(None, "算法关联更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量更新音频算法关联
    @staticmethod
    def batch_update_audio_algorithms():
        try:
            from shared.models.models import AudioAlgorithmRelation
            from api_gateway.schemas.audio import BatchUpdateAudioAlgorithmsRequest

            data = request.get_json() or {}
            try:
                validated = BatchUpdateAudioAlgorithmsRequest.model_validate(data)
            except Exception as e:
                return error_response(f"参数验证失败: {e}")

            audio_ids = validated.audio_ids
            algorithms = validated.algorithms

            updated_count = 0
            for audio_id in audio_ids:
                audio = db.session.get(Audio, audio_id)
                if not audio or audio.deleted:
                    continue

                AudioAlgorithmRelation.query.filter_by(audio_id=audio_id).update({'deleted': True})

                for item in algorithms:
                    relation = AudioAlgorithmRelation(
                        audio_id=audio_id,
                        algorithm_type=item.algorithm_type,
                        is_primary=item.is_primary,
                        weight=item.weight,
                        params=item.params
                    )
                    db.session.add(relation)
                updated_count += 1

            db.session.commit()
            return success_response({"updated_count": updated_count}, f"成功更新 {updated_count} 个音频的算法关联")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
