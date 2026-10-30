# -*- coding: utf-8 -*-
"""播放设备按实验室换绑（用例内播放设备只属于一个实验室）。

被测设备与播放设备必须同实验室。用例里配置的 playback_device_id 是
「编写用例时那个实验室」的播放设备，跨实验室执行时必须换成执行实验室
自己的播放设备，否则会驱动别处的音箱（不同实验室并行时互相串音）。

换绑口径（执行前、音频预下载之前完成，保证按新设备采样率重采样）：
- 用例直接关联逻辑音箱（playback_speaker_group_id / playback_speaker_group_ids）→
  取组内该实验室对应设备，解析不到即失败；
- 用例的播放设备已属于执行实验室 → 保持不变；
- 有逻辑音箱组（源音箱所属组在目标实验室有对应设备）→ 用组内对应设备；
- 无对应组 → 该实验室设备中按 name 精确匹配（同名位置对应）；
- 无同名 → 该实验室第一台在线设备；
- 再无 → 该实验室任一设备；
- 该实验室没有任何播放设备 → 抛 LabPlaybackBindingError（用例直接失败）。
"""
from shared.infrastructure.config import BaseConfig
from shared.models.common_enums import PlaybackDeviceStatus

PLAYBACK_DEVICE_ID_KEY = 'playback_device_id'
PLAYBACK_DEVICE_NAME_KEY = 'playback_device_name'
PLAYBACK_DEVICE_IDS_KEY = 'device_ids'
PLAYBACK_SPEAKER_GROUP_ID_KEY = 'playback_speaker_group_id'
PLAYBACK_SPEAKER_GROUP_IDS_KEY = 'playback_speaker_group_ids'


class LabPlaybackBindingError(RuntimeError):
    """实验室播放设备换绑失败（用例直接失败，不静默用错音箱）"""


class LabPlaybackBindingMixin:
    """执行前把用例播放设备换绑到被测设备所属实验室"""

    def _bind_lab_playback_devices(self, task_id, test_case_id, case_config,
                                   device_info_list):
        """按执行实验室换绑 case_config 内全部播放设备（就地修改）

        Raises:
            LabPlaybackBindingError: 被测设备无实验室归属 / 组内跨实验室 /
                实验室没有任何播放设备 / 逻辑音箱在实验室无对应设备
        """
        if not getattr(BaseConfig, 'PLAYBACK_LAB_BINDING_ENABLED', True):
            return
        if not isinstance(case_config, dict):
            return

        refs = []
        self._collect_playback_refs(case_config, refs)
        if not refs:
            # 未配置播放设备的用例（如纯录音用例）无需换绑
            return

        lab_id = self._resolve_execution_lab_id(device_info_list)
        lab_devices = self._playback_repo.list_playback_devices(lab_id)
        if not lab_devices:
            raise LabPlaybackBindingError(
                f"实验室 {lab_id} 未配置可用播放设备，无法执行（播放设备须与被测设备同实验室）")

        normalized = self._normalize_lab_devices(lab_devices)
        group_list_refs = [ref for ref in refs if self._group_ids_of(ref)]
        group_refs = [
            ref for ref in refs
            if not self._group_ids_of(ref) and self._group_id_of(ref) is not None
        ]
        device_refs = [
            ref for ref in refs
            if not self._group_ids_of(ref) and self._group_id_of(ref) is None
        ]
        changes = self._bind_speaker_group_ids_refs(group_list_refs, normalized, lab_id)
        changes += self._bind_speaker_group_refs(group_refs, normalized, lab_id)
        changes += self._bind_legacy_device_refs(device_refs, normalized, lab_id)

        if changes:
            self._log(
                level='INFO',
                content=f"播放设备按实验室换绑: lab_id={lab_id}, {', '.join(changes)}",
                task_id=task_id, test_case_id=test_case_id)

    @staticmethod
    def _group_id_of(ref):
        """节点上的逻辑音箱组 ID（无则 None）"""
        return LabPlaybackBindingMixin._normalize_device_id(
            ref['node'].get(PLAYBACK_SPEAKER_GROUP_ID_KEY))

    @staticmethod
    def _group_ids_of(ref):
        """节点上的逻辑音箱组 ID 列表（背景噪声可多选；无/非法则空列表）"""
        raw = ref['node'].get(PLAYBACK_SPEAKER_GROUP_IDS_KEY)
        if not isinstance(raw, (list, tuple)):
            return []
        group_ids = []
        for value in raw:
            group_id = LabPlaybackBindingMixin._normalize_device_id(value)
            if group_id is not None:
                group_ids.append(group_id)
        return group_ids

    def _bind_speaker_group_ids_refs(self, refs, lab_devices, lab_id):
        """多选逻辑音箱（背景噪声 device_ids）→ 该实验室实体设备 ID 列表"""
        resolved = {}
        changes = []
        for ref in refs:
            device_ids = []
            for group_id in self._group_ids_of(ref):
                if group_id not in resolved:
                    resolved[group_id] = self._resolve_group_device(group_id, lab_id, lab_devices)
                    changes.append(
                        f"group:{group_id}->{resolved[group_id]['id']}"
                        f"({resolved[group_id].get('name')})")
                device_ids.append(resolved[group_id]['id'])
            ref['node'][PLAYBACK_DEVICE_IDS_KEY] = device_ids
        return changes

    def _bind_speaker_group_refs(self, refs, lab_devices, lab_id):
        """用例直接关联逻辑音箱：组 + 执行实验室 → 该实验室对应设备（解析不到即失败）"""
        resolved = {}
        changes = []
        for ref in refs:
            group_id = self._group_id_of(ref)
            if group_id not in resolved:
                resolved[group_id] = self._resolve_group_device(group_id, lab_id, lab_devices)
            target = resolved[group_id]
            ref['node'][PLAYBACK_DEVICE_ID_KEY] = target['id']
            # 用例关联的只是「位置」，设备名随实际设备回填（报表/日志需要）
            ref['node'][PLAYBACK_DEVICE_NAME_KEY] = target.get('name')
            changes.append(f"group:{group_id}->{target['id']}({target.get('name')})")
        return changes

    def _resolve_group_device(self, group_id, lab_id, lab_devices):
        """逻辑音箱组在该实验室的播放设备；未配置/设备不在该实验室 → 抛错"""
        mapped_id = self._playback_repo.resolve_speaker_group_device(group_id, lab_id)
        if mapped_id is None:
            raise LabPlaybackBindingError(
                f"逻辑音箱 {group_id} 未配置实验室 {lab_id} 的播放设备，无法执行")
        for device in lab_devices:
            if device['id'] == mapped_id:
                return device
        raise LabPlaybackBindingError(
            f"逻辑音箱 {group_id} 在实验室 {lab_id} 对应的播放设备 {mapped_id} "
            f"不存在或不属于该实验室，无法执行")

    def _bind_legacy_device_refs(self, refs, lab_devices, lab_id):
        """老用例（只配置 playback_device_id）：按实验室换绑"""
        resolved = {}
        changes = []
        for ref in refs:
            old_id = self._normalize_device_id(ref['node'].get(PLAYBACK_DEVICE_ID_KEY))
            if old_id is None:
                continue
            if old_id not in resolved:
                resolved[old_id] = self._select_lab_playback_device(
                    old_id, ref['node'].get(PLAYBACK_DEVICE_NAME_KEY), lab_devices, lab_id)
            target = resolved[old_id]
            if target is None:
                # 已属于执行实验室，保持原配置
                continue
            ref['node'][PLAYBACK_DEVICE_ID_KEY] = target['id']
            if PLAYBACK_DEVICE_NAME_KEY in ref['node']:
                ref['node'][PLAYBACK_DEVICE_NAME_KEY] = target.get('name')
            changes.append(f"{old_id}->{target['id']}({target.get('name')})")
        return changes

    @staticmethod
    def _collect_playback_refs(node, refs):
        """递归收集所有带播放设备/逻辑音箱组键的字典节点（保持原对象引用）"""
        if isinstance(node, dict):
            if (PLAYBACK_DEVICE_ID_KEY in node
                    or PLAYBACK_SPEAKER_GROUP_ID_KEY in node
                    or PLAYBACK_SPEAKER_GROUP_IDS_KEY in node):
                refs.append({'node': node})
            for value in node.values():
                LabPlaybackBindingMixin._collect_playback_refs(value, refs)
        elif isinstance(node, list):
            for item in node:
                LabPlaybackBindingMixin._collect_playback_refs(item, refs)

    @staticmethod
    def _normalize_lab_devices(lab_devices):
        """统一设备 ID 为 int"""
        normalized = []
        for device in lab_devices:
            device_id = LabPlaybackBindingMixin._normalize_device_id(device.get('id'))
            if device_id is None:
                continue
            normalized.append({**device, 'id': device_id})
        return normalized

    @staticmethod
    def _normalize_device_id(raw):
        if raw in (None, ''):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_execution_lab_id(device_info_list):
        """执行设备的实验室归属（组内必须同实验室）"""
        lab_ids = {
            info.get('lab_id') for info in (device_info_list or [])
            if info.get('lab_id') not in (None, '')
        }
        if not lab_ids:
            raise LabPlaybackBindingError(
                "被测设备未绑定实验室，无法确定播放设备（播放设备须与被测设备同实验室）")
        if len(lab_ids) > 1:
            raise LabPlaybackBindingError(
                f"同一执行组内被测设备跨实验室（lab_ids={sorted(lab_ids)}），无法确定播放设备")
        return int(next(iter(lab_ids)))

    def _select_lab_playback_device(self, old_id, old_name, lab_devices, lab_id):
        """选择执行实验室的播放设备；已属于该实验室返回 None（保持原配置）

        顺序：逻辑音箱组（源音箱所属组在目标实验室的设备）→ 同名 → 在线 → 任一。
        组内对应设备若不在该实验室设备列表中（数据过期）按无对应处理。
        """
        if any(device['id'] == old_id for device in lab_devices):
            return None

        mapped_id = self._playback_repo.resolve_speaker_device(old_id, lab_id)
        if mapped_id is not None:
            for device in lab_devices:
                if device['id'] == mapped_id:
                    return device
            self._log(level='WARNING',
                      content=(f"逻辑音箱组对应设备失效：源音箱 {old_id} 在实验室 {lab_id} "
                               f"对应到 {mapped_id}，但该设备不属于此实验室，回退名称匹配"),
                      task_id=None)

        name = (old_name or '').strip()
        if name:
            for device in lab_devices:
                if (device.get('name') or '').strip() == name:
                    return device

        for device in lab_devices:
            if device.get('status') == PlaybackDeviceStatus.ONLINE.value:
                return device
        return lab_devices[0] if lab_devices else None
