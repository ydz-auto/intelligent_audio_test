# -*- coding: utf-8 -*-
"""音频引擎 - 设备通信 Mixin

从 audio_engine.py 拆分出的职责：
- init_driver / _get_driver：PyAudio 驱动初始化（主线程预初始化）
- _get_cached_devices：带缓存的设备列表扫描
- _normalize_name / _find_device_matches / _select_by_api_priority：多策略设备匹配与 API 优先级选择
- get_device_index / get_device_sample_rate：设备索引与采样率查询
"""
from shared.utils.log_handler import log_and_emit


class EngineDeviceCommMixin:
    """PyAudio 驱动通信与物理设备匹配/选择职责"""

    def init_driver(self):
        """在主线程中预初始化 PyAudio 驱动（Pa_Initialize 非线程安全）"""
        if self.driver is None:
            with self._lock:
                if self.driver is None:
                    from audio_service.infrastructure.audio.audio_driver import PyAudioDriver
                    self.driver = PyAudioDriver()
                    log_and_emit('INFO', 'audio_engine', "PyAudio 驱动已在主线程预初始化", category='audio')
        return self.driver

    def _get_driver(self):
        """获取 PyAudio 驱动实例（应在主线程预初始化后调用）"""
        if self.driver is None:
            self.init_driver()
        return self.driver

    def _get_cached_devices(self):
        """获取带缓存的设备列表，避免频繁扫描导致驱动崩溃"""
        import time
        with self._lock:
            current_time = time.time()
            if self._device_cache is None or (current_time - self._cache_time) > self._cache_duration:
                log_and_emit('DEBUG', 'audio_engine', "Cache expired or empty, scanning devices...", category='audio')
                self._device_cache = self._get_driver().get_devices()
                self._cache_time = current_time
            else:
                log_and_emit('DEBUG', 'audio_engine', f"Using cached device list (age: {round(current_time - self._cache_time, 2)}s)", category='audio')
            return self._device_cache

    @staticmethod
    def _normalize_name(name):
        """归一化设备名：去除引号、特殊字符、多余空格，统一为小写"""
        return name.replace("'", "").replace('"', '').strip().lower()

    def _find_device_matches(self, clean_unique_id, normalized_unique_id, devices):
        """多策略设备匹配：精确 → 基础名 → 扬声器前缀 → 模糊 → 括号内容。

        Returns:
            list: 匹配的设备列表（可能为空）
        """
        normalize = self._normalize_name

        # 1. 精确匹配
        exact_matches = [
            dev for dev in devices
            if (clean_unique_id == dev['name']
                or clean_unique_id == str(dev['index'])
                or normalize(dev['name']) == normalized_unique_id)
        ]
        log_and_emit('DEBUG', 'audio_engine', f"Exact matches: {len(exact_matches)}", category='audio')
        if exact_matches:
            return exact_matches

        # 2. 基础名匹配（去掉 [Ch X] 后缀）
        base_unique_id = clean_unique_id.split(' [Ch')[0] if ' [Ch' in clean_unique_id else clean_unique_id
        normalized_base = normalize(base_unique_id)
        log_and_emit('DEBUG', 'audio_engine', f"Trying base unique_id: '{base_unique_id}' (normalized: '{normalized_base}')", category='audio')

        base_matches = [dev for dev in devices if normalize(dev['name']) == normalized_base]
        if base_matches:
            log_and_emit('DEBUG', 'audio_engine', f"Base name matches: {len(base_matches)}", category='audio')
            return base_matches

        # 3. 扬声器前缀匹配
        if "扬声器" not in clean_unique_id:
            log_and_emit('DEBUG', 'audio_engine', "Trying to match with '扬声器' prefix...", category='audio')
            normalized_speaker = normalize(f"扬声器 {clean_unique_id}")
            speaker_matches = [
                dev for dev in devices
                if normalize(dev['name']) == normalized_speaker
                or normalized_speaker in normalize(dev['name'])
            ]
            if speaker_matches:
                log_and_emit('DEBUG', 'audio_engine', f"Speaker prefix matches: {len(speaker_matches)}", category='audio')
                return speaker_matches

        # 4. 模糊匹配（包含关系）
        log_and_emit('DEBUG', 'audio_engine', "Trying flexible fuzzy matching...", category='audio')
        fuzzy_matches = [
            dev for dev in devices
            if normalized_unique_id in normalize(dev['name'])
            or normalize(dev['name']) in normalized_unique_id
        ]
        if fuzzy_matches:
            log_and_emit('DEBUG', 'audio_engine', f"Fuzzy matches: {len(fuzzy_matches)}", category='audio')
            return fuzzy_matches

        # 5. 括号内容匹配 + 主体名联合过滤
        log_and_emit('DEBUG', 'audio_engine', "Trying to match content in parentheses...", category='audio')
        import re
        bracket_content = re.findall(r'\(([^)]+)\)', clean_unique_id)
        if bracket_content:
            # 提取输入的主体名（括号外的部分），如 "扬声器 (RME Fireface UCX II)" → "扬声器"
            # 同时去掉 [Ch X] 后缀
            input_main = re.sub(r'\([^)]*\)', '', clean_unique_id)
            input_main = re.sub(r'\s*\[Ch\s*\d+\]', '', input_main).strip()
            normalized_input_main = normalize(input_main)
            bracket_matches = []
            for content in bracket_content:
                normalized_bracket = normalize(content)
                bracket_matches.extend(
                    dev for dev in devices
                    if normalized_bracket in normalize(dev['name'])
                )
            if bracket_matches:
                # 用主体名过滤：只保留设备名主体与输入主体一致的
                if normalized_input_main:
                    filtered = []
                    for dev in bracket_matches:
                        dev_main = re.sub(r'\([^)]*\)', '', dev['name']).strip()
                        normalized_dev_main = normalize(dev_main)
                        if normalized_input_main == normalized_dev_main:
                            filtered.append(dev)
                    if filtered:
                        bracket_matches = filtered
                log_and_emit('DEBUG', 'audio_engine', f"Bracket content matches: {len(bracket_matches)}", category='audio')
                return bracket_matches

        return []

    @classmethod
    def _select_by_api_priority(cls, matches):
        """按全局统一 API 从匹配列表中选择最佳设备。

        保证所有设备选择都走同一个 API，避免同一物理设备
        被不同 API 索引同时占用导致打开失败。

        Returns:
            dict: 选中的设备 dict，或 None
        """
        # 如果已确定可用品 API，优先使用
        apis_to_try = [cls._resolved_api] if cls._resolved_api else cls._api_fallback_chain

        for api in apis_to_try:
            api_matches = [dev for dev in matches if dev['host_api'] == api]
            if api_matches:
                log_and_emit('DEBUG', 'audio_engine', f"API matches for {api}: {len(api_matches)}", category='audio')

                # 优先选择不带"扬声器"字样的设备
                pure_devices = [
                    dev for dev in api_matches
                    if "扬声器" not in dev['name'] and "Speaker" not in dev['name']
                ]
                selected = pure_devices[0] if pure_devices else api_matches[0]
                tag = "" if pure_devices else " (fallback)"
                log_and_emit('INFO', 'audio_engine', f"Selected device{tag}: {selected['name']} (API: {selected['host_api']}, Index: {selected['index']})", category='audio')
                # 固定此 API，后续所有设备选择都走同一 API
                cls._resolved_api = api
                return selected

        # 所有优先级都没有，返回第一个匹配
        selected = matches[0]
        log_and_emit('INFO', 'audio_engine', f"Selected device (final fallback): {selected['name']} (API: {selected['host_api']}, Index: {selected['index']})", category='audio')
        return selected

    def get_device_index(self, unique_id):
        """根据唯一标识获取物理设备索引 - 增强版"""
        if not unique_id:
            log_and_emit('ERROR', 'audio_engine', "get_device_index called with empty unique_id", category='audio')
            return None

        devices = self._get_cached_devices()
        log_and_emit('DEBUG', 'audio_engine', f"get_device_index: unique_id={unique_id}, available_devices={len(devices)}", category='audio')

        clean_unique_id = unique_id.strip()
        normalized_unique_id = self._normalize_name(clean_unique_id)
        log_and_emit('DEBUG', 'audio_engine', f"Clean unique_id: '{clean_unique_id}', Normalized: '{normalized_unique_id}'", category='audio')

        # 多策略匹配
        matches = self._find_device_matches(clean_unique_id, normalized_unique_id, devices)

        if not matches:
            # 兜底：返回第一个可用设备
            if devices:
                selected = devices[0]
                log_and_emit('WARNING', 'audio_engine', f"No matches found for '{unique_id}', returning first available device: '{selected['name']}' (Index: {selected['index']})", category='audio')
                return selected['index']
            else:
                log_and_emit('ERROR', 'audio_engine', f"No device matches found for unique_id='{unique_id}' and no devices available", category='audio')
                return None

        # 按 API 优先级选择
        selected = self._select_by_api_priority(matches)
        return selected['index']

    def get_device_sample_rate(self, unique_id):
        """根据设备唯一标识获取设备的默认采样率（defaultSampleRate）。

        与 get_device_index 使用同一套设备匹配逻辑，命中后通过
        PyAudio.get_device_info_by_index 读取 defaultSampleRate。
        未命中时返回 None。
        """
        if not unique_id:
            return None
        device_index = self.get_device_index(unique_id)
        if device_index is None:
            return None
        try:
            dev_info = self._get_driver().pa.get_device_info_by_index(device_index)
            return int(dev_info.get('defaultSampleRate', 44100))
        except Exception as e:
            log_and_emit('WARNING', 'audio_engine',
                         f"get_device_sample_rate: unique_id={unique_id}, index={device_index}, error={e}",
                         category='audio')
            return None
