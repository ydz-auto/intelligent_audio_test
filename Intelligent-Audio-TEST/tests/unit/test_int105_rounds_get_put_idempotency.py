# -*- coding: utf-8 -*-
"""INT-105 专项：用例 GET→PUT 回写幂等（rounds 注入完整性）。

原缺陷：GET 详情响应把全部轮次音频拍平（附合成 id）、全部轮次维度去重后
放在顶层 audios/dimensions 供展示；客户端原样回传详情时，update() 把这两份
聚合数据无条件注入 round1 —— round1.audios 逐次累积膨胀（每次 PUT 净增
N-1 条），round1 单轮维度被过期合并数据覆盖永远落不上，进而导致执行侧
单轮排入多个音频、play_round gRPC 超时。

修复语义：客户端携带 rounds 结构的 config 时 rounds 为唯一权威，顶层
audios/dimensions 仅在旧平面格式请求（未携带 rounds 结构）下注入 round1。
"""
import copy
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.testcase_helpers import collect_audios
from task_service.application.testcase.testcase_crud_service import TestCaseCrudService


class FakeTC:
    """最小用例替身：update() 触及的字段。"""

    def __init__(self, tc_id, config):
        self.id = tc_id
        self.name = '用例'
        self.description = None
        self.group_id = 'g1'
        self.config = config
        self.algorithm_params = None
        self.reference_params = None
        self.algorithm_type = None
        self.tags = []
        self.updated_at = None


class FakeRepo:
    def __init__(self, tc):
        self.tc = tc
        self.committed = False

    def get_testcase(self, tc_id):
        return self.tc if tc_id == self.tc.id else None

    def get_group_by_name(self, name):
        return None

    def create_group(self, *a, **k):
        return None

    def set_testcase_tags(self, tc, tags):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def make_service(tc):
    svc = TestCaseCrudService()
    svc.repo = FakeRepo(tc)
    return svc


def three_round_config():
    return {
        'rounds': [
            {'roundNumber': 1,
             'audios': [{'audio_id': 2219, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 11, 'name': '准确率', 'weight': 1.0}]}},
            {'roundNumber': 2,
             'audios': [{'audio_id': 2218, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 11, 'name': '准确率', 'weight': 1.0}]}},
            {'roundNumber': 3,
             'audios': [{'audio_id': 2217, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 12, 'name': '唤醒率', 'weight': 1.0}]}},
        ],
    }


def detail_echo_body(config):
    """模拟 GET 详情响应原样回传：config + 拍平 audios（合成 id）+ 去重 dimensions。"""
    audios = [
        {'id': i, 'audio_id': a.get('audio_id'), 'spl': a.get('spl'),
         'playback_device_id': None, 'play_order': a.get('play_order')}
        for i, a in enumerate(collect_audios(config))
    ]
    return {
        'name': '用例',
        'config': copy.deepcopy(config),
        'audios': audios,
        'dimensions': [{'id': 11, 'name': '准确率', 'type': 'accuracy'},
                       {'id': 12, 'name': '唤醒率', 'type': 'wake'}],
    }


def test_roundtrip_echo_keeps_rounds_audios_unchanged():
    config = three_round_config()
    tc = FakeTC('c1', copy.deepcopy(config))
    svc = make_service(tc)

    body = detail_echo_body(config)
    assert svc.update('c1', body)['success']
    rounds = tc.config['rounds']
    # round1 不吸收顶层拍平 audios（原缺陷两次 PUT 后 round1 变 5 条）
    assert [a['audio_id'] for a in rounds[0]['audios']] == [2219]
    assert [a['audio_id'] for a in collect_audios(tc.config)] == [2219, 2218, 2217]

    # 连续回写仍幂等
    assert svc.update('c1', detail_echo_body(config))['success']
    assert [a['audio_id'] for a in rounds[0]['audios']] == [2219]
    assert [a['audio_id'] for a in collect_audios(tc.config)] == [2219, 2218, 2217]


def test_round1_dimensions_update_lands_via_config_echo():
    config = three_round_config()
    tc = FakeTC('c1', copy.deepcopy(config))
    svc = make_service(tc)

    body = detail_echo_body(config)
    body['config']['rounds'][0]['evaluation']['dimensions'] = [
        {'id': 13, 'name': '响应时延', 'weight': 0.5}
    ]
    assert svc.update('c1', body)['success']

    rounds = tc.config['rounds']
    # round1 单轮维度以 config 为准落库（原缺陷被顶层过期合并数据覆盖）
    assert [d['id'] for d in rounds[0]['evaluation']['dimensions']] == [13]
    # round2/3 不受影响
    assert [d['id'] for d in rounds[1]['evaluation']['dimensions']] == [11]
    assert [d['id'] for d in rounds[2]['evaluation']['dimensions']] == [12]


def test_legacy_flat_body_without_config_still_targets_round1():
    # 单轮用例 + 旧平面部分更新（不带 config）：顶层字段仍是 round1 输入
    config = three_round_config()
    config['rounds'] = config['rounds'][:1]
    tc = FakeTC('c1', copy.deepcopy(config))
    svc = make_service(tc)

    assert svc.update('c1', {'audios': [
        {'audio_id': 33, 'spl': 70, 'play_order': 0, 'playback_device_id': None},
    ]})['success']
    assert [a['audio_id'] for a in tc.config['rounds'][0]['audios']] == [33]

    assert svc.update('c1', {'dimensions': [{'id': 9, 'name': '误唤醒'}]})['success']
    assert [d['id'] for d in tc.config['rounds'][0]['evaluation']['dimensions']] == [9]


def test_flat_config_with_top_level_fields_targets_round1():
    # 旧平面 config + 顶层 audios/dimensions（创建口径的更新路径）保持原语义
    tc = FakeTC('c1', {'audios': [{'audio_id': 1, 'spl': 65, 'play_order': 0}],
                       'dimensions': [{'id': 11, 'name': '准确率'}]})
    svc = make_service(tc)

    body = {
        'config': {'audios': [{'audio_id': 2, 'spl': 66, 'play_order': 0}]},
        'audios': [{'audio_id': 2, 'spl': 66, 'play_order': 0, 'playback_device_id': None}],
        'dimensions': [{'id': 14, 'name': '时延'}],
    }
    assert svc.update('c1', body)['success']
    assert [a['audio_id'] for a in tc.config['rounds'][0]['audios']] == [2]
    assert [d['id'] for d in tc.config['rounds'][0]['evaluation']['dimensions']] == [14]
