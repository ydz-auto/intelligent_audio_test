# -*- coding: utf-8 -*-
"""测试用例创建 - ID 解析 Mixin

从 audio_testcase_creation_service.py 拆分出的职责：
- _build_name_to_id_maps：预查音频文件名→ID、设备名→ID 映射
- _resolve_audio_field / _resolve_device_fields：payload 内字段 ID 解析
- _resolve_bg_noise_and_interferers_ids：segment 级背景噪声和干扰人 ID 解析
"""


class CreationIdResolutionMixin:
    """文件名/设备名 → audio_id/device_ids 的 ID 解析职责"""

    def _build_name_to_id_maps(self):
        """预查音频文件名→ID、设备名→ID 映射（用于 interferers/background_noise 的 ID 解析）。

        通过 ACL 仓储获取设备列表，避免直接 import PO。
        音频列表通过仓储分页获取前 1000 条构建映射，超出部分逐个查库兜底。
        """
        # 设备名→ID 映射
        dev_name_to_id = {}
        devices = self._playback_acl.list_playback_devices()
        for dev in devices:
            if not dev.get('is_deleted'):
                dev_name_to_id.setdefault(dev.get('name'), dev.get('id'))
        # 音频文件名→ID 映射（通过仓储批量查库，取前 1000 条）
        audio_name_to_id_map = {}
        try:
            pagination = self.repo.list_audios({'page': 1, 'per_page': 1000})
            items = getattr(pagination, 'items', []) or []
            for _a in items:
                _name = getattr(_a, 'name', None)
                if _name:
                    audio_name_to_id_map.setdefault(_name, getattr(_a, 'id', None))
                _orig = getattr(_a, 'original_filename', None)
                if _orig:
                    audio_name_to_id_map.setdefault(_orig, getattr(_a, 'id', None))
        except Exception:
            pass
        return audio_name_to_id_map, dev_name_to_id

    def _resolve_audio_field(self, payload, audio_name_to_id_map=None):
        """把 payload 里的 audio(文件名)/audio_name 转成 audio_id。"""
        if not isinstance(payload, dict):
            return
        if not payload.get('audio_id'):
            _fn = payload.get('audio') or payload.get('audio_name')
            if _fn:
                # 优先用预查映射
                if audio_name_to_id_map and _fn in audio_name_to_id_map:
                    payload['audio_id'] = audio_name_to_id_map[_fn]
                else:
                    # 逐个查库兜底
                    try:
                        found = self.repo.find_audio_by_name(_fn)
                        if found:
                            payload['audio_id'] = getattr(found, 'id', None)
                    except Exception:
                        pass

    def _resolve_device_fields(self, payload, dev_name_to_id=None):
        """把 payload 里的 playback_device_name(s)/device_names 转成 device_ids。"""
        if not isinstance(payload, dict):
            return
        if not payload.get('device_ids'):
            names = (
                payload.get('playback_device_names')
                or payload.get('device_names')
            )
            if names and isinstance(names, list):
                ids = []
                for n in names:
                    if not n:
                        continue
                    # 优先用预查映射
                    if dev_name_to_id and n in dev_name_to_id:
                        ids.append(dev_name_to_id[n])
                    else:
                        # 逐个查库兜底
                        try:
                            dev = self._playback_acl.find_playback_device_by_name(n)
                            if dev:
                                ids.append(dev.get('id'))
                        except Exception:
                            pass
                if ids:
                    payload['device_ids'] = ids
            else:
                single = payload.get('playback_device_name')
                if single:
                    if dev_name_to_id and single in dev_name_to_id:
                        payload['device_ids'] = [dev_name_to_id[single]]
                    else:
                        try:
                            dev = self._playback_acl.find_playback_device_by_name(single)
                            if dev:
                                payload['device_ids'] = [dev.get('id')]
                        except Exception:
                            pass

    def _resolve_bg_noise_and_interferers_ids(self, rounds_resolved):
        """解析 segment 级背景噪声和干扰人：文件名→audio_id，设备名→device_ids/playback_device_id。

        无论 raw_annotations 是否存在都执行（前端可能已直接在 rounds_config 中传入）。
        """
        audio_name_to_id_map, dev_name_to_id = self._build_name_to_id_maps()

        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            # 轮次级背景噪声（round 级）
            _r_bg = round_item.get('background_noise')
            if isinstance(_r_bg, dict):
                self._resolve_audio_field(_r_bg, audio_name_to_id_map)
                self._resolve_device_fields(_r_bg, dev_name_to_id)
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                # segment 级背景噪声
                _seg_bg = audio_item.get('background_noise')
                if isinstance(_seg_bg, dict):
                    self._resolve_audio_field(_seg_bg, audio_name_to_id_map)
                    self._resolve_device_fields(_seg_bg, dev_name_to_id)
                # segment 级干扰人：audio→audio_id，playback_device_name→playback_device_id
                _interferers = audio_item.get('interferers')
                if isinstance(_interferers, list):
                    self._resolve_interferer_payload_ids(_interferers, audio_name_to_id_map, dev_name_to_id)

    def _resolve_interferer_payload_ids(self, interferers, audio_name_to_id_map, dev_name_to_id):
        """对干扰人列表逐个做 ID 解析（含逐个查库兜底）。"""
        for _itf in interferers:
            if not isinstance(_itf, dict):
                continue
            # audio 文件名 → audio_id
            if not _itf.get('audio_id'):
                _fn = _itf.get('audio') or _itf.get('audio_name')
                if _fn:
                    if _fn in audio_name_to_id_map:
                        _itf['audio_id'] = audio_name_to_id_map[_fn]
                    else:
                        try:
                            found = self.repo.find_audio_by_name(_fn)
                            if found:
                                _itf['audio_id'] = getattr(found, 'id', None)
                        except Exception:
                            pass
            # playback_device_name → playback_device_id
            if not _itf.get('playback_device_id'):
                _dn = _itf.get('playback_device_name')
                if _dn:
                    if _dn in dev_name_to_id:
                        _itf['playback_device_id'] = dev_name_to_id[_dn]
                    else:
                        try:
                            dev = self._playback_acl.find_playback_device_by_name(_dn)
                            if dev:
                                _itf['playback_device_id'] = dev.get('id')
                        except Exception:
                            pass
