# -*- coding: utf-8 -*-
"""INT-2179 补证：e2e 执行期「逻辑音箱 → 执行实验室实体播放设备」换绑实跑。

直接调用执行器的换绑实现 `LabPlaybackBindingMixin._bind_lab_playback_devices`
（真实 `PlaybackAclRepositoryImpl` → 宿主 device_service gRPC，真实实验室数据）：
- 组直连（playback_speaker_group_id）→ 该实验室成员设备，名字回填
- 背景噪声多选（playback_speaker_group_ids）→ 实体设备列表
- 空/无对应组 → LabPlaybackBindingError（可读文案）
- 成员离线（status=offline）→ 仍然换绑成功（后端无离线提示/降级）

配合 int2179_group_playback_probe.py（真实出声）即可证明「分组 → 实体设备 →
派发数据 → 播放」链路；本脚本只做换绑，不驱动被测设备。

用法：PYTHONPATH=. python tests/verify/int2179_group_binding_probe.py
"""
import json
import os
import sys

DEVICE_ENV_FILE = r'D:/00_code/V9.7.31/Intelligent-Audio-TEST/logs/host_services/device.env.json'
LAB_ID = 38
REAL_SN = '5SM0125701000448'


def _load_env():
    with open(DEVICE_ENV_FILE, encoding='utf-8') as fh:
        env = json.load(fh)
    for key, value in env.items():
        os.environ[key] = str(value)


class _Harness:
    def __init__(self):
        from e2e_test_service.application.services.e2e_executor.lab_playback_binding import (
            LabPlaybackBindingMixin,
        )
        from e2e_test_service.infrastructure.acl.playback_acl_repository_impl import (
            PlaybackAclRepositoryImpl,
        )
        self._mixin = LabPlaybackBindingMixin()
        self._mixin._playback_repo = PlaybackAclRepositoryImpl()
        self._mixin._log = lambda **kw: self.logs.append(kw)
        self.logs = []
        self.binder = self._mixin

    def bind(self, case_config):
        self.binder._bind_lab_playback_devices(
            999182, 'int2179-bind', case_config,
            [{'device_sn': REAL_SN, 'lab_id': LAB_ID}])
        return case_config


def main():
    _load_env()
    from e2e_test_service.application.services.e2e_executor.lab_playback_binding import (
        LabPlaybackBindingError,
    )
    h = _Harness()
    results = {}

    # 1) 组直连 → 成员设备
    cfg = {'rounds': [{'round_number': 1,
                       'audios': [{'audio_id': 1694, 'playback_speaker_group_id': 2,
                                   'playback_device_id': None}]}]}
    h.bind(cfg)
    node = cfg['rounds'][0]['audios'][0]
    results['group_direct'] = node
    print('[group_direct] playback_device_id=%s name=%s' %
          (node.get('playback_device_id'), node.get('playback_device_name')))
    print('[group_direct.logs]', h.logs[-1:])

    # 2) 背景噪声多选组 → 实体设备列表
    cfg2 = {'rounds': [{'round_number': 1,
                        'background_noise': {'playback_speaker_group_ids': [11],
                                             'device_ids': []}}]}
    h.bind(cfg2)
    noise = cfg2['rounds'][0]['background_noise']
    results['group_ids'] = noise
    print('[background_noise] device_ids=%s' % (noise.get('device_ids'),))

    # 3) 空/无对应组 → 可读异常
    cfg3 = {'rounds': [{'round_number': 1,
                        'audios': [{'audio_id': 1694, 'playback_speaker_group_id': 999}]}]}
    try:
        h.bind(cfg3)
        results['missing_group'] = {'raised': False}
        print('[missing_group] 未抛错（预期应失败）')
    except LabPlaybackBindingError as exc:
        results['missing_group'] = {'raised': True, 'message': str(exc)}
        print('[missing_group] LabPlaybackBindingError:', exc)

    # 4) 成员离线（group 3 → 播放设备 2 offline）仍换绑
    cfg4 = {'rounds': [{'round_number': 1,
                        'audios': [{'audio_id': 1694, 'playback_speaker_group_id': 3}]}]}
    h.bind(cfg4)
    node4 = cfg4['rounds'][0]['audios'][0]
    results['offline_member'] = node4
    print('[offline_member] playback_device_id=%s name=%s（离线成员仍被换绑）' %
          (node4.get('playback_device_id'), node4.get('playback_device_name')))

    ok = (results['group_direct'].get('playback_device_id') is not None
          and results['group_direct'].get('playback_device_name')
          and results['group_ids'].get('device_ids')
          and results['missing_group'].get('raised') is True
          and results['offline_member'].get('playback_device_id') is not None)
    print('[summary]', json.dumps(results, ensure_ascii=False))
    print('RESULT', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
