# -*- coding: utf-8 -*-
"""音频命令处理器（CQRS 写侧）。

接收 Command 对象，编排领域服务/仓储/跨域 ACL 完成写操作。
依赖 domain/repositories ABC 接口，不直接 import ORM。
复杂子服务（annotation/testcase_creation）通过 application/services 委托。
"""
from __future__ import annotations

import logging
import os
import threading
import traceback
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from shared.utils.log_handler import log_and_emit
from shared.infrastructure.storage import storage
from shared.infrastructure.user_context import capture_identity

from audio_service.domain.repositories import AudioRepositoryInterface
from audio_service.domain.exceptions import TagResolutionError
from audio_service.application.commands.audio_commands import (
    UpdateAudioMetadataCommand,
    UpdateAudioVisibilityCommand,
    BatchUpdateAnnotationsCommand,
    BatchActionAudiosCommand,
    DeleteAudioCommand,
    UpdateAudioAlgorithmsCommand,
    BatchUpdateAudioAlgorithmsCommand,
    ConvertAudioCommand,
    PreviewAudioCommand,
    StopPreviewAudioCommand,
    PersistAnnotationsCommand,
    CreateTestCaseFromAudioCommand,
    ProcessAudioCommand,
)

logger = logging.getLogger(__name__)


def _ok(data: Any = None, message: str = 'Success', code: int = 200) -> Dict[str, Any]:
    return {'success': True, 'message': message, 'data': data, 'code': code}


def _fail(message: str, code: int = 400, data: Any = None) -> Dict[str, Any]:
    return {'success': False, 'message': message, 'data': data, 'code': code}


# ========== 批量操作（move/copy/rename/modify-properties）工具函数 ==========

_ALLOWED_AUDIO_TYPES = {'dry', 'noise', 'prompt', 'mixed'}
# modify-properties 元数据白名单列（file_path 归 move/copy 管理；
# audios 无 per-audio SPL 列，SPL 为设备/API 级映射）
_METADATA_PROPERTY_FIELDS = ('name', 'audio_type', 'asr_text', 'description', 'source_language')


def _batch_field(data: Dict[str, Any], *names: str) -> Any:
    """按 snake_case/camelCase 顺序取扩展字段（与既有 audioIds 双口径读取一致）。"""
    for name in names:
        if name in data and data.get(name) is not None:
            return data.get(name)
    return None


def _normalize_target_folder(target_folder: Any) -> str:
    """规范化批量 move/copy 目标文件夹。

    统一反斜杠、去首尾斜杠；拒绝空目录、. / .. 穿越、绝对路径；
    兼容 folder-tree 展示口径：开头的 direct/ 前缀可带可不带。
    """
    folder = (target_folder or '').replace('\\', '/').strip('/').strip()
    parts = [p for p in folder.split('/') if p and p.strip()]
    if not parts:
        raise ValueError('目标文件夹不能为空')
    if any(p in ('.', '..') for p in parts):
        raise ValueError('目标文件夹包含非法路径段（. / ..）')
    if parts[0] == 'direct':
        parts = parts[1:]
    if not parts:
        raise ValueError('目标文件夹不能为空')
    return '/'.join(parts)


def _storage_key_of(file_path: str) -> str:
    """取存储 key（去 scheme 前缀；裸 key 原样返回）。"""
    if file_path.startswith('oss://'):
        return file_path[len('oss://'):]
    if file_path.startswith('local://'):
        return file_path[len('local://'):]
    return file_path


def _same_storage_location(old_path: str, target_key: str) -> bool:
    """判断目标 key 与源存储位置是否相同（scheme 路径的 key 含 audios/ 分类前缀）。"""
    old_key = _storage_key_of(old_path)
    if old_key == target_key:
        return True
    if old_key.startswith('audios/') and old_key[len('audios/'):] == target_key:
        return True
    return False


def _extract_basename(file_path: str) -> str:
    """取 file_path 最后一段文件名（storage key 或本地路径通用）。"""
    normalized = (file_path or '').replace('\\', '/').rstrip('/')
    return normalized.rsplit('/', 1)[-1]


def _dedupe_storage_key(key: str) -> str:
    """目标 storage key 已存在时追加 _1/_2 序号（与上传 _dedupe_oss_key 同口径）。

    带安全上限：storage.exists 持续为 True（存储状态异常）时最多递增 999 后直接返回。
    """
    if not storage.exists(storage.build_path('audios', key)):
        return key
    stem, ext = os.path.splitext(key)
    counter = 1
    while storage.exists(storage.build_path('audios', f'{stem}_{counter}{ext}')):
        counter += 1
        if counter >= 1000:
            break
    return f'{stem}_{counter}{ext}'


class _RelocationResult(NamedTuple):
    """一次文件迁移的结果（INT-1562）。

    - new_path：新的 file_path（写回 DB）
    - created_object：本次新写入的存储对象；原地不动（未写对象）时为 None，
      提交失败时据此回删，避免对象泄漏
    - stale_source：move 成功提交后待删除的源对象；copy / 原地不动为 None
    """

    new_path: str
    created_object: Optional[str]
    stale_source: Optional[str]


def _relocate_audio_file(audio, target_folder: str, copy_mode: bool) -> _RelocationResult:
    """迁移音频物理文件到目标文件夹，返回 _RelocationResult。

    - copy_mode=False（move）：目标 key 与源 key 相同视为原地不动；否则只做
      「复制到目标」——**不在这里删除源对象**，由调用方在 DB 提交成功后尽力删除
      （INT-1562：先删源后落库时服务中断会产生指向已丢失文件的悬空记录）。
    - copy_mode=True（copy）：下载→重存，保留源对象。
    """
    old_path = audio.file_path
    if not old_path:
        raise ValueError('音频文件路径缺失')
    filename = _extract_basename(old_path)
    target_key = f'direct/{target_folder}/{filename}'
    if not copy_mode and _same_storage_location(old_path, target_key):
        return _RelocationResult(old_path, None, None)
    deduped_key = _dedupe_storage_key(target_key)

    if old_path.startswith(('oss://', 'local://')):
        stale_source = None if copy_mode else old_path
        tmp = storage.load_file(old_path)
        try:
            new_path = storage.save_file(tmp, 'audios', deduped_key)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        return _RelocationResult(new_path, new_path, stale_source)

    if os.path.isabs(old_path):
        # 传统本地绝对路径：直接以本地文件为存储源
        stale_source = None if copy_mode else old_path
        new_path = storage.save_file(old_path, 'audios', deduped_key)
        return _RelocationResult(new_path, new_path, stale_source)

    # 裸逻辑 key（无 scheme）：按 audios 分类处理
    stale_source = None if copy_mode else storage.build_path('audios', old_path)
    src_path = storage.build_path('audios', old_path)
    tmp = storage.load_file(src_path)
    try:
        new_path = storage.save_file(tmp, 'audios', deduped_key)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    return _RelocationResult(new_path, new_path, stale_source)


# ========== 数据可见性（INT-564）工具函数 ==========

def _owner_check_fail(audio, denied_code: int = 403):
    """音频写路径 owner 校验（INT-564）：私有非 owner 返回 403，其余返回 None。

    与数据可见性设计文档 §三命令侧口径一致：Application 层先取资源 →
    check_visible owner 校验；私有资源非 owner 一律拒绝，共享资源回落
    require_permission 既有语义。admin 豁免（check_visible 内部短路）。
    写路径一律 owner+admin，不设宿主豁免（规划师裁定 INT-564 §4）。
    """
    from shared.infrastructure.visibility_filter import check_visible
    from shared.infrastructure.user_context import (
        get_current_user_id,
        get_current_user_is_admin,
    )
    try:
        check_visible(
            getattr(audio, 'created_by_user_id', None),
            getattr(audio, 'visibility', 'shared') or 'shared',
            get_current_user_id(),
            get_current_user_is_admin(),
        )
        return None
    except PermissionError as e:
        return _fail(str(e), denied_code)


def _filter_visible_audios(audios):
    """批量写取数后逐行可见性过滤（INT-564）：私有非 owner 行跳过，不整批放行。

    镜像 task_service 批量写（_filter_visible_testcases）逐行口径：visibility /
    created_by_user_id 缺省的对象按 shared 放行（零回归）。
    """
    from shared.infrastructure.visibility_filter import check_visible
    from shared.infrastructure.user_context import (
        get_current_user_id,
        get_current_user_is_admin,
    )
    uid = get_current_user_id()
    is_admin = get_current_user_is_admin()
    visible = []
    for audio in audios:
        vis = getattr(audio, 'visibility', 'shared') or 'shared'
        owner = getattr(audio, 'created_by_user_id', None)
        try:
            check_visible(owner, vis, uid, is_admin)
            visible.append(audio)
        except PermissionError:
            continue
    return visible


class AudioCommandHandler:
    """音频写命令处理器。

    依赖注入 AudioRepositoryInterface（ABC），不直接 import 具体仓储类。
    """

    def __init__(self, repository: AudioRepositoryInterface = None) -> None:
        if repository is None:
            from audio_service.infrastructure.persistence.audio_repository import audio_repository
            repository = audio_repository
        self.repo = repository
        self._annotation_service = None
        self._testcase_creation_service = None
        # ACL 仓储（跨域只读查询）
        from audio_service.infrastructure.acl.task_acl_repository import (
            TaskACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.device_acl_repository import (
            DeviceACLRepositoryImpl,
        )
        self._task_acl = TaskACLRepositoryImpl()
        self._device_acl = DeviceACLRepositoryImpl()

    @property
    def annotation_service(self):
        if self._annotation_service is None:
            from audio_service.application.services.audio_annotation_service import audio_annotation_service
            self._annotation_service = audio_annotation_service
        return self._annotation_service

    @property
    def testcase_creation_service(self):
        if self._testcase_creation_service is None:
            from audio_service.application.services.audio_testcase_creation_service import audio_testcase_creation_service
            self._testcase_creation_service = audio_testcase_creation_service
        return self._testcase_creation_service

    @staticmethod
    def _delete_audio_file_best_effort(file_path: str) -> None:
        """尽力删除音频物理文件，不阻塞删除响应（INT-1306）。

        OSS 不可达时 storage.delete 可能长时间挂起（连接/读取超时叠加，
        真实环境实测 ~158s），软删落库与接口响应不应等待物理清理。改后台
        线程尽力执行，异常/超时均记录后放行；DB 软删是删除的权威状态。
        """
        if not file_path:
            return

        def _run():
            try:
                storage.delete(file_path)
            except Exception:
                logger.debug("删除音频物理文件失败: file_path=%s", file_path, exc_info=True)

        threading.Thread(
            target=_run, daemon=True, name='audio-file-cleanup'
        ).start()

    @staticmethod
    def _delete_relocated_object_best_effort(path: str) -> None:
        """尽力删除迁移产生的对象：成功后的源对象 / 失败项回删的目标对象（INT-1562）。

        DB 提交后删源失败只会留下未被引用的对象，绝不能让异常冒泡把已提交的
        批量操作变成失败响应；本地绝对路径（历史数据）走 os.remove，其余走
        storage.delete。
        """
        if not path:
            return
        try:
            if os.path.isabs(path):
                if os.path.exists(path):
                    os.remove(path)
            else:
                storage.delete(path)
        except Exception:
            logger.warning(
                "清理批量迁移文件失败（仅对象泄漏，不影响记录）: path=%s", path, exc_info=True)

    # ========== 音频元数据写操作 ==========

    def handle_update_metadata(self, cmd: UpdateAudioMetadataCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('未找到音频文件', 404)
        denied = _owner_check_fail(audio)
        if denied:
            return denied

        try:
            data = cmd.data
            name = data.get('name')
            audio_type = data.get('audio_type') or data.get('audioType')
            asr_text = data.get('asr_text') or data.get('asrText')
            description = data.get('description')
            source_language = data.get('source_language') or data.get('sourceLanguage')
            tags_str = data.get('tags')
            annotations = data.get('annotations', [])

            update_fields = {}
            if name is not None:
                update_fields['name'] = name
            if audio_type is not None:
                update_fields['audio_type'] = audio_type
            if asr_text is not None:
                update_fields['asr_text'] = asr_text
            if description is not None:
                update_fields['description'] = description
            if source_language is not None:
                update_fields['source_language'] = source_language

            if update_fields:
                self.repo.update_audio(cmd.audio_id, update_fields)

            if tags_str is not None:
                self.repo.delete_audio_tags(cmd.audio_id)
                if tags_str:
                    for tag_name in tags_str.split(','):
                        tag_name = tag_name.strip()
                        if tag_name:
                            # INT-1533：标签解析失败要整单失败并回滚，不能写 NULL 关联
                            tag = self.repo.get_or_create_tag(tag_name)
                            self.repo.add_audio_tag(cmd.audio_id, tag.id)

            if annotations is not None:
                self.repo.delete_audio_annotations(cmd.audio_id)
                for ann in annotations:
                    self.repo.create_audio_annotation(cmd.audio_id, ann)

            self.repo.commit()
            return _ok(message='元数据更新成功')
        except TagResolutionError as e:
            self.repo.rollback()
            logger.warning("更新音频元数据失败（标签解析）: audio_id=%s err=%s", cmd.audio_id, e)
            return _fail(str(e))
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_update_audio_visibility(self, cmd: UpdateAudioVisibilityCommand) -> Dict[str, Any]:
        """仅更新音频可见性（INT-464 跟随用例 gRPC 同步）。

        内部通道：task_service 用例建/改后调用，经 ACL gRPC 同步，
        不对外暴露独立可见性修改端点。visibility 取值校验对齐
        shared/models/common_enums.py 的 Visibility 二值枚举。
        """
        from shared.models.common_enums import Visibility
        try:
            vis = cmd.visibility
            if vis not in (Visibility.SHARED.value, Visibility.PRIVATE.value):
                return _fail(f'非法的可见性取值: {vis!r}（合法值: shared/private）', 400)

            audio = self.repo.get_audio(cmd.audio_id)
            if not audio:
                return _fail('未找到音频文件', 404)

            if not self.repo.update_audio_visibility(cmd.audio_id, vis):
                return _fail('未找到音频文件', 404)
            self.repo.commit()
            return _ok(data={'audio_id': cmd.audio_id, 'visibility': vis},
                       message='音频可见性更新成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_batch_update_annotations(self, cmd: BatchUpdateAnnotationsCommand) -> Dict[str, Any]:
        if not cmd.data:
            return _fail('请求体不能为空')

        items = cmd.data.get('items', [])
        algorithm_type = cmd.data.get('algorithm_type') or cmd.data.get('algorithmType')
        refresh_test_cases = cmd.data.get('refresh_test_cases', cmd.data.get('refreshTestCases', True))

        if not items:
            return _fail('标注列表不能为空')

        updated_audio_ids = []
        updated_count = 0
        failed_count = 0

        try:
            for item in items:
                audio_id = item.get('audio_id') or item.get('audioId')
                annotations = item.get('annotations', [])
                if not annotations:
                    continue

                audio = self.repo.get_audio(audio_id)
                if not audio:
                    failed_count += 1
                    continue
                # INT-564：批量写逐行可见性过滤——私有非 owner 行跳过，不整批放行
                if _owner_check_fail(audio) is not None:
                    failed_count += 1
                    continue

                self.annotation_service.persist_annotations_and_raw(audio_id, annotations, algorithm_type)
                updated_audio_ids.append(audio_id)
                updated_count += 1

            self.repo.flush()
            # INT-2042：标注先落库提交，刷新关联用例不再占住本次 RPC —— 原先
            # 刷新串在命令里，全表扫描 + 逐用例重算实测 >60s，必然撞上网关
            # gRPC 客户端 deadline，标注已写库却回 400 DEADLINE_EXCEEDED。
            self.repo.commit()
        except Exception as e:
            self.repo.rollback()
            log_and_emit(
                level='error', module='audio_controller',
                content=f'批量更新标注失败: {str(e)}\n{traceback.format_exc()}',
                category='audio',
            )
            return _fail(str(e))

        # 标注已提交；用例参数刷新改后台执行（INT-2042），不影响本次响应
        refresh_scheduled = False
        if refresh_test_cases and updated_audio_ids:
            refresh_scheduled = self._schedule_testcase_refresh(
                updated_audio_ids, algorithm_type)

        data = {
            'updated_count': updated_count,
            'failed_count': failed_count,
            # 异步刷新后不再能同步返回命中用例；保留字段避免调用方解析失败
            'refreshed_test_case_ids': [],
            'refresh_scheduled': refresh_scheduled,
        }
        if refresh_scheduled:
            message = (f'批量更新标注成功，更新 {updated_count} 个音频，'
                       f'关联用例参考参数刷新已在后台执行')
        else:
            message = f'批量更新标注成功，更新 {updated_count} 个音频'
        return _ok(data=data, message=message)

    def _schedule_testcase_refresh(self, audio_ids, algorithm_type) -> bool:
        """把关联用例参考参数刷新交给后台调度器（INT-2042）。

        刷新失败不影响标注结果（标注已是提交态），异常只记录日志并回 False。
        """
        try:
            from audio_service.application.services.testcase_refresh_scheduler import (
                get_testcase_refresh_scheduler,
            )
            return get_testcase_refresh_scheduler().enqueue(
                audio_ids, algorithm_type, capture_identity())
        except Exception as e:
            logger.warning("提交关联用例刷新任务失败: %s", e, exc_info=True)
            return False

    def handle_batch_action(self, cmd: BatchActionAudiosCommand) -> Dict[str, Any]:
        if not cmd.data:
            return _fail('请求体不能为空')

        audio_ids = cmd.data.get('audio_ids') or cmd.data.get('audioIds', [])
        action = cmd.data.get('action')
        tags = cmd.data.get('tags', [])

        try:
            if action == 'delete':
                deletable_audio_ids = []
                skipped_audio_ids = []

                # INT-1306：引用检查改 task_service 批量 gRPC（DB 侧单次扫描），
                # 替代逐页 ListTestCases/ListTasks 全量拉取（真实库 580 用例下
                # 超 gRPC 60s deadline）；引用状态未知时抛异常 fail-closed，不静默落库。
                refs = self._task_acl.check_audio_references_batch(audio_ids)
                for audio_id in audio_ids:
                    ref = refs.get(audio_id, {})
                    if (ref.get('testcase_audio', 0) > 0
                            or ref.get('testcase_noise', 0) > 0
                            or ref.get('task', 0) > 0
                            or self._device_acl.check_audio_in_devices(audio_id) > 0):
                        skipped_audio_ids.append(audio_id)
                        continue
                    deletable_audio_ids.append(audio_id)

                if not deletable_audio_ids:
                    return _ok(message='没有可删除的音频文件，所有音频都被其他资源引用')

                audios = self.repo.get_audios_by_ids(deletable_audio_ids)
                # INT-564：批量删除逐行可见性过滤——私有非 owner 行跳过（写路径
                # 一律 owner+admin，无宿主豁免），其余行正常删除
                visible_audios = _filter_visible_audios(audios)
                deletable_audio_ids = [a.id for a in visible_audios]
                if not deletable_audio_ids:
                    return _ok(message='没有可删除的音频文件，所有音频均无权访问')

                for audio in visible_audios:
                    # INT-1306：物理文件删除改后台尽力执行，OSS 不可达时不阻塞响应
                    self._delete_audio_file_best_effort(audio.file_path)
                    self.repo.delete_audio_annotations(audio.id)
                    self.repo.delete_audio_tags(audio.id)

                self.repo.batch_soft_delete_audios(deletable_audio_ids)

                message = f'成功删除 {len(deletable_audio_ids)} 个音频文件'
                if skipped_audio_ids:
                    message += f'，跳过了 {len(skipped_audio_ids)} 个被引用的音频文件'

                self.repo.commit()
                return _ok(message=message)

            elif action == 'export':
                import zipfile
                from io import BytesIO
                audios = self.repo.get_audios_by_ids(audio_ids)
                # INT-564：批量导出逐行可见性过滤——私有非 owner 行不进入导出包
                audios = _filter_visible_audios(audios)
                memory_file = BytesIO()
                with zipfile.ZipFile(memory_file, 'w') as zf:
                    for audio in audios:
                        try:
                            local_path = storage.load_file(audio.file_path)
                            zf.write(local_path, audio.original_filename)
                        except Exception:
                            logger.debug("导出音频到压缩包失败: audio_id=%s, file_path=%s", audio.id, audio.file_path, exc_info=True)
                memory_file.seek(0)
                import base64
                zip_b64 = base64.b64encode(memory_file.getvalue()).decode('ascii')
                from shared.utils.query_utils import now_cst
                return _ok(data={
                    'zip_base64': zip_b64,
                    'filename': f'audios_export_{now_cst().strftime("%Y%m%d%H%M%S")}.zip',
                }, message='批量导出成功')

            elif action == 'tags':
                for audio_id in audio_ids:
                    audio = self.repo.get_audio(audio_id)
                    if audio and _owner_check_fail(audio) is None:
                        self.repo.delete_audio_tags(audio_id)
                        for tag_name in tags:
                            tag = self.repo.get_or_create_tag(tag_name)
                            self.repo.add_audio_tag(audio_id, tag.id)

                self.repo.commit()
                return _ok(message=f'批量操作 {action} 执行成功')

            elif action == 'move':
                return self._handle_batch_move_or_copy(cmd.data, audio_ids, copy_mode=False)

            elif action == 'copy':
                return self._handle_batch_move_or_copy(cmd.data, audio_ids, copy_mode=True)

            elif action == 'rename':
                return self._handle_batch_rename(cmd.data, audio_ids)

            elif action == 'modify-properties':
                return self._handle_batch_modify_properties(cmd.data, audio_ids)

            else:
                return _fail(f'不支持的操作: {action}')

        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    # ========== 批量 move / copy（storage + file_path 更新，INT-818） ==========

    def _handle_batch_move_or_copy(self, data: Dict[str, Any], audio_ids: List[int], copy_mode: bool) -> Dict[str, Any]:
        """批量移动/复制音频到目标文件夹。

        move：物理文件迁移 + file_path 更新（目标 key 与源相同视为原地不动）。
        copy：物理文件复制 + 新建 Audio 记录（保留源记录与文件）。
        """
        action_label = '复制' if copy_mode else '移动'
        target_folder = _batch_field(data, 'target_folder', 'targetFolder')
        try:
            folder = _normalize_target_folder(target_folder)
        except ValueError as e:
            return _fail(f'批量{action_label}失败: {e}')

        if not audio_ids:
            return _fail('音频 ID 列表不能为空')

        audios = self.repo.get_audios_by_ids(audio_ids)
        if not audios:
            return _fail('未找到音频文件')

        success_count = 0
        failed_count = 0
        failed_ids = []
        pending_source_deletes: List[str] = []
        created_objects: List[str] = []
        try:
            for audio in audios:
                created_object = None
                try:
                    relocation = _relocate_audio_file(audio, folder, copy_mode=copy_mode)
                    created_object = relocation.created_object
                    if copy_mode:
                        self.repo.create_audio({
                            'name': audio.name,
                            'original_filename': audio.original_filename,
                            'file_path': relocation.new_path,
                            'size': audio.size,
                            'duration': audio.duration,
                            'sample_rate': audio.sample_rate,
                            'channels': audio.channels,
                            'bitrate': audio.bitrate,
                            'format': audio.format,
                            'audio_type': audio.audio_type,
                            'asr_text': audio.asr_text,
                            'description': audio.description,
                            'md5': audio.md5,
                            'source_language': audio.source_language,
                        })
                    else:
                        self.repo.update_audio(audio.id, {'file_path': relocation.new_path})
                        if relocation.stale_source:
                            pending_source_deletes.append(relocation.stale_source)
                    if created_object:
                        created_objects.append(created_object)
                    success_count += 1
                except Exception as e:
                    logger.debug("批量%s音频失败: audio_id=%s, err=%s", action_label, audio.id, e, exc_info=True)
                    failed_count += 1
                    failed_ids.append(audio.id)
                    if created_object:
                        # 该项未成功，新写入的目标对象没有 DB 记录引用，尽力回删
                        self._delete_relocated_object_best_effort(created_object)
            self.repo.commit()
        except Exception as e:
            self.repo.rollback()
            # 提交失败：本批新写入的目标对象均无 DB 记录引用，尽力回删；
            # 源对象尚未删除，失败后存储回到原状（INT-1562）
            for path in created_objects:
                self._delete_relocated_object_best_effort(path)
            return _fail(f'批量{action_label}失败: {e}')

        # DB 已提交：此刻起删除源对象即使失败也只是对象泄漏，
        # 不会出现记录指向已丢失文件。按建议优先提交后删源（INT-1562）。
        for path in pending_source_deletes:
            self._delete_relocated_object_best_effort(path)

        message = f'成功{action_label} {success_count} 个音频'
        if failed_count:
            message += f'，{failed_count} 个失败（audio_id: {failed_ids}）'
        return _ok(data={
            'action': 'copy' if copy_mode else 'move',
            'success_count': success_count,
            'failed_count': failed_count,
        }, message=message)

    # ========== 批量 rename（name 列更新，INT-818） ==========

    def _handle_batch_rename(self, data: Dict[str, Any], audio_ids: List[int]) -> Dict[str, Any]:
        """批量重命名：name = {rename_rule}{01..N}{原扩展名}（React 预览口径）。"""
        rename_rule = _batch_field(data, 'rename_rule', 'renameRule')
        if not rename_rule:
            return _fail('重命名规则不能为空')

        if not audio_ids:
            return _fail('音频 ID 列表不能为空')

        audios = self.repo.get_audios_by_ids(audio_ids)
        if not audios:
            return _fail('未找到音频文件')

        success_count = 0
        try:
            for index, audio in enumerate(audios, start=1):
                ext = os.path.splitext(audio.name)[1] if audio.name else ''
                new_name = f'{rename_rule}{index:02d}{ext}'
                self.repo.update_audio(audio.id, {'name': new_name})
                success_count += 1
            self.repo.commit()
            return _ok(data={
                'action': 'rename',
                'success_count': success_count,
                'failed_count': 0,
            }, message=f'成功重命名 {success_count} 个音频')
        except Exception as e:
            self.repo.rollback()
            return _fail(f'批量重命名失败: {e}')

    # ========== 批量 modify-properties（元数据/音频类型，INT-818） ==========

    def _handle_batch_modify_properties(self, data: Dict[str, Any], audio_ids: List[int]) -> Dict[str, Any]:
        """批量修改属性：metadata（字段字典白名单）/ audio-type（类型值）。

        SPL 无 per-audio 落点（spl_mappings 为设备/API 级），本期明确拒绝并说明。
        """
        property_name = _batch_field(data, 'property')
        if not property_name:
            return _fail('属性名称不能为空')

        if property_name == 'spl':
            return _fail(
                '批量修改 SPL 暂不支持：audios 表无 per-audio SPL 列（SPL 为设备/API 级映射），'
                '本期仅支持 metadata / audio-type'
            )

        if not audio_ids:
            return _fail('音频 ID 列表不能为空')

        audios = self.repo.get_audios_by_ids(audio_ids)
        if not audios:
            return _fail('未找到音频文件')

        if property_name == 'metadata':
            property_value = _batch_field(data, 'property_value', 'propertyValue')
            if not isinstance(property_value, dict) or not property_value:
                return _fail('修改元数据需要 property_value 为字段字典（如 {"description": "..."}）')
            update_fields = {k: v for k, v in property_value.items() if k in _METADATA_PROPERTY_FIELDS}
            if not update_fields:
                return _fail(f'未提供可修改的元数据字段，允许字段: {"/".join(_METADATA_PROPERTY_FIELDS)}')
            return self._apply_property_update(audios, update_fields)

        if property_name == 'audio-type':
            property_value = _batch_field(data, 'property_value', 'propertyValue', 'value')
            if property_value not in _ALLOWED_AUDIO_TYPES:
                return _fail(f'无效的音频类型: {property_value}，允许值: dry / noise / prompt / mixed')
            return self._apply_property_update(audios, {'audio_type': property_value})

        return _fail(f'不支持的属性: {property_name}，允许值: metadata / audio-type / spl')

    def _apply_property_update(self, audios: List[Any], update_fields: dict) -> Dict[str, Any]:
        success_count = 0
        try:
            for audio in audios:
                self.repo.update_audio(audio.id, update_fields)
                success_count += 1
            self.repo.commit()
            return _ok(data={
                'action': 'modify-properties',
                'success_count': success_count,
                'failed_count': 0,
            }, message=f'成功修改 {success_count} 个音频的属性')
        except Exception as e:
            self.repo.rollback()
            return _fail(f'批量修改属性失败: {e}')

    def handle_delete(self, cmd: DeleteAudioCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('未找到音频文件', 404)
        denied = _owner_check_fail(audio)
        if denied:
            return denied

        try:
            # INT-1306：引用检查改 task_service 批量 gRPC（DB 侧单次扫描），
            # 替代逐页 ListTestCases/ListTasks 全量拉取；引用状态未知时 fail-closed。
            refs = self._task_acl.check_audio_references_batch([cmd.audio_id])
            ref = refs.get(cmd.audio_id, {})
            if ref.get('testcase_audio', 0) > 0:
                return _fail('该音频文件已被测试用例使用，禁止删除')
            if ref.get('testcase_noise', 0) > 0:
                return _fail('该音频文件已被测试用例作为背景噪音使用，禁止删除')
            if self._device_acl.check_audio_in_devices(cmd.audio_id) > 0:
                return _fail('该音频文件已被设备作为提示词使用，禁止删除')
            if ref.get('task', 0) > 0:
                return _fail('该音频文件已被任务使用，禁止删除')

            # INT-1306：物理文件删除改后台尽力执行，OSS 不可达时不阻塞响应
            self._delete_audio_file_best_effort(audio.file_path)

            self.repo.delete_audio_annotations(cmd.audio_id)
            self.repo.delete_audio_tags(cmd.audio_id)
            self.repo.delete_audio(cmd.audio_id)
            self.repo.commit()

            # INT-1306：统计缓存刷新改后台尽力执行（Redis 不可达时读缓存超时
            # 会让删除响应拖到 ~9s+），缓存刷新不阻塞删除结果返回。
            def _refresh_stats():
                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    logger.debug("删除音频后刷新统计缓存失败: audio_id=%s", cmd.audio_id, exc_info=True)

            threading.Thread(
                target=_refresh_stats, daemon=True, name='audio-stats-refresh'
            ).start()

            return _ok(message='音频文件已删除')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_update_audio_algorithms(self, cmd: UpdateAudioAlgorithmsCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('音频不存在', 404)
        denied = _owner_check_fail(audio)
        if denied:
            return denied

        algorithms = cmd.data.get('algorithms', [])
        try:
            self.repo.soft_delete_audio_algorithm_relations(cmd.audio_id)
            for item in algorithms:
                self.repo.create_audio_algorithm_relation(cmd.audio_id, item)
            self.repo.commit()
            return _ok(message='算法关联更新成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_batch_update_audio_algorithms(self, cmd: BatchUpdateAudioAlgorithmsCommand) -> Dict[str, Any]:
        audio_ids = cmd.data.get('audio_ids') or cmd.data.get('audioIds', [])
        algorithms = cmd.data.get('algorithms', [])

        try:
            updated_count = 0
            for audio_id in audio_ids:
                audio = self.repo.get_audio(audio_id)
                if not audio:
                    continue
                # INT-564：批量写逐行可见性过滤——私有非 owner 行跳过，不整批放行
                if _owner_check_fail(audio) is not None:
                    continue
                self.repo.soft_delete_audio_algorithm_relations(audio_id)
                for item in algorithms:
                    self.repo.create_audio_algorithm_relation(audio_id, item)
                updated_count += 1

            self.repo.commit()
            return _ok(
                data={'updated_count': updated_count},
                message=f'成功更新 {updated_count} 个音频的算法关联',
            )
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    # ========== 转换/预览（委托子服务） ==========

    def handle_convert_audio(self, cmd: ConvertAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_convert_service import audio_convert_service
        return audio_convert_service.convert_audio(cmd.audio_id, cmd.data)

    def handle_preview_audio(self, cmd: PreviewAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_preview_service import audio_preview_service
        return audio_preview_service.preview_audio(cmd.audio_id, cmd.data)

    def handle_stop_preview_audio(self, cmd: StopPreviewAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_preview_service import audio_preview_service
        return audio_preview_service.stop_preview_audio(cmd.audio_id)

    def handle_process_audio(self, cmd: ProcessAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_analysis_service import audio_analysis_service
        return audio_analysis_service.process(cmd.audio_id, cmd.data)

    # ========== 标注/测试用例创建（委托子服务） ==========

    def handle_persist_annotations(self, cmd: PersistAnnotationsCommand) -> Dict[str, Any]:
        try:
            self.annotation_service.persist_annotations_and_raw(
                cmd.audio_id, cmd.annotations, cmd.algorithm_type
            )
            self.repo.commit()
            return _ok(message='标注持久化成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_create_test_case_from_audio(self, cmd: CreateTestCaseFromAudioCommand) -> Dict[str, Any]:
        try:
            tc_ids = self.testcase_creation_service.create_test_case_from_audio(
                cmd.audio_id,
                cmd.test_types,
                cmd.tags,
                cmd.default_playback_device_id,
                cmd.default_spl,
                cmd.noise_spl,
                cmd.noise_audio_id,
                cmd.group_name,
                cmd.dimensions_data,
                cmd.algorithm_type,
                cmd.algorithm_params_dict,
                rounds_config=cmd.rounds_config,
                inherit_tags=cmd.inherit_tags,
                raw_annotations=cmd.raw_annotations,
                noise_device_ids=cmd.noise_device_ids,
                case_background_noise=cmd.case_background_noise,
            )
            self.repo.commit()
            return _ok(data={
                'test_case_id': tc_ids[0] if isinstance(tc_ids, list) and tc_ids else tc_ids,
                'test_case_count': len(tc_ids) if isinstance(tc_ids, list) else (1 if tc_ids else 0),
            }, message='测试用例创建成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))
