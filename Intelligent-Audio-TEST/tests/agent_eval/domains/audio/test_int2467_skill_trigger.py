# -*- coding: utf-8 -*-
"""INT-2467 `audio-import` Skill 写章节的触发抽样（确定性词面代理）。

与 ``tests/agent_eval/domains/device/skill_support.py`` 同一口径：用 Skill L1
description 的触发词做词面命中，验证「导入 / 上传 / 批量标注 / 改元数据」
这类写意图会稳定命中 `audio-import`，域外问题不误命中。模型级触发评测归统一
评测器，这里只保证 L1 描述可用（卡面可测标准 4：≥ 90% 抽样）。
"""
from tests.agent_eval.domains.device.skill_support import route

SKILL = 'audio-import'

POSITIVES = (
    '怎么导入音频？',
    '帮我上传音频到平台',
    '这个音频有没有导入过',
    '按 MD5 查重看看重复音频',
    '帮我批量标注这些音频',
    '查一下音频质量',
    '改一下音频元数据',
    '给音频配算法',
    'URL 导入一个文件',
    '看音频标签',
)

NEGATIVES = (
    '设备重启一下',
    '生成驱动提案',
    'SPL 校准历史',
    '报告导出 PDF',
    '创建测试任务',
    '查一下评估维度',
    '任务失败诊断',
    '查看日志错误',
    '用例详情',
    '算法参数映射',
)


def test_audio_import_trigger_accuracy_at_least_90_percent():
    hits = [query for query in POSITIVES if route(query)[0] == SKILL]
    false_positives = [query for query in NEGATIVES if route(query)[0] == SKILL]
    total = len(POSITIVES) + len(NEGATIVES)
    correct = len(hits) + (len(NEGATIVES) - len(false_positives))
    accuracy = correct / total
    assert accuracy >= 0.9, (
        f'audio-import 触发准确率 {accuracy:.0%} < 90%；'
        f'未命中：{[q for q in POSITIVES if q not in hits]}；'
        f'误命中：{false_positives}')
