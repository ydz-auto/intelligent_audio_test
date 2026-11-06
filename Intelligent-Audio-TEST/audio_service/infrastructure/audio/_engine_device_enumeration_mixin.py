# -*- coding: utf-8 -*-
"""音频引擎 - 物理设备枚举 Mixin

从 audio_engine.py 拆分出的职责：
- _extract_card_key_and_stable_name：从设备名提取声卡分组 key 和稳定设备名
- _classify_and_add_device：设备分类并添加到去重字典
- _dedup_sort_key：子设备排序 key
- get_all_physical_devices：按声卡聚合去重，生成候选播放设备列表
"""


class EngineDeviceEnumerationMixin:
    """物理输出设备扫描/按声卡聚合去重职责"""

    @staticmethod
    def _extract_card_key_and_stable_name(dev_name):
        """从设备名提取声卡分组 key 和稳定设备名。

        Returns:
            (card_key, stable_dev_name)
        """
        import re
        bracket_match = re.search(r'\(([^)]+)\)', dev_name)
        if bracket_match:
            bracket_content = bracket_match.group(1)
            if re.match(r'^\d+-\s*', bracket_content):
                stable_card_name = re.sub(r'^\d+-\s*', '', bracket_content)
            else:
                stable_card_name = bracket_content
        else:
            stable_card_name = None

        if 'RME' in dev_name or 'Fireface' in dev_name:
            if '802' in dev_name:
                card_key = 'RME Fireface 802'
            elif 'UCX' in dev_name:
                card_key = 'RME Fireface UCX II'
            elif 'Fireface' in dev_name:
                card_key = 'RME Fireface'
            else:
                card_key = 'Unknown RME'
        else:
            try:
                if ' (' in dev_name:
                    card_key = dev_name.split(' (')[0].strip()
                else:
                    card_key = dev_name[:20].strip() if len(dev_name) > 20 else dev_name.strip()
            except:
                card_key = dev_name.strip()

        if stable_card_name and bracket_match:
            stable_dev_name = dev_name.replace(bracket_match.group(0), f"({stable_card_name})")
        else:
            stable_dev_name = dev_name

        return card_key, stable_dev_name

    @staticmethod
    def _classify_and_add_device(all_devices, card_key, dev, dev_name):
        """将设备分类（Analog子设备 / 主设备 / 其他）并添加到去重字典。"""
        max_output = dev['channels']
        sample_rate = dev['sample_rate']
        host_api = dev['host_api']

        if card_key not in all_devices:
            all_devices[card_key] = {
                'sub_devices_dedup': {},
                'all_sub_devices': []
            }

        # 确定声道范围
        if 'Analog (' in dev_name:
            try:
                channel_range = dev_name.split('(')[1].split(')')[0].strip()
            except:
                channel_range = dev_name
        elif '扬声器' in dev_name or 'Speaker' in dev_name:
            channel_range = 'Main'
        else:
            channel_range = 'Main'

        # 存储原始设备
        all_devices[card_key]['all_sub_devices'].append({
            'index': dev['index'],
            'name': dev_name,
            'channels': max_output,
            'channel_range': channel_range
        })

        # 去重：仅保留首个
        if channel_range not in all_devices[card_key]['sub_devices_dedup']:
            all_devices[card_key]['sub_devices_dedup'][channel_range] = {
                'index': dev['index'],
                'name': dev_name,
                'channels': max_output,
                'channel_range': channel_range,
                'sample_rate': sample_rate,
                'host_api': host_api
            }

    @staticmethod
    def _dedup_sort_key(sub_dev):
        """子设备排序 key：Main 最前，Analog 按通道号。"""
        channel_range = sub_dev['channel_range']
        if channel_range == 'Main':
            return 0
        try:
            return int(channel_range.split('+')[0])
        except:
            return 999

    def get_all_physical_devices(self):
        """扫描所有可用的物理输出设备及通道 - 按声卡聚合并去重"""
        devices = self._get_cached_devices()
        all_devices = {}

        # 第一步：枚举所有 WASAPI 设备，按声卡分组并去重
        for dev in devices:
            if dev['host_api'] != 'Windows WASAPI':
                continue

            dev_name = dev['name']
            card_key, stable_dev_name = self._extract_card_key_and_stable_name(dev_name)
            self._classify_and_add_device(all_devices, card_key, dev, stable_dev_name)

        # 第二步：处理去重结果，生成候选设备列表
        candidates = []
        for info in all_devices.values():
            dedup_subs = sorted(
                info['sub_devices_dedup'].values(),
                key=self._dedup_sort_key
            )
            info['dedup_sub_list'] = dedup_subs
            info['total_channels_dedup'] = sum(sub['channels'] for sub in dedup_subs)
            del info['sub_devices_dedup']

            for sub_dev in dedup_subs:
                for ch in range(sub_dev['channels']):
                    unique_id = f"{sub_dev['name']} [Ch {ch+1}]"
                    candidates.append({
                        "name": unique_id,
                        "unique_id": unique_id,
                        "device_index": sub_dev['index'],
                        "channel_index": ch,
                        "sample_rate": sub_dev['sample_rate'],
                        "host_api": sub_dev['host_api']
                    })

        return candidates
