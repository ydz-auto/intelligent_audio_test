# -*- coding: utf-8 -*-
"""xiaoyi_metrics 共享枚举

所有子包共用的枚举类型集中于此，
消除散落各文件的魔法字符串。
"""
from enum import Enum


class SceneType(str, Enum):
    """场景类型（由 task_params.scene / env_type 指定）"""
    ENV_SOUND = 'env_sound'
    INTERRUPTION = 'interruption'
    HIGH_FREQ = 'high_freq'


class EventType(str, Enum):
    """打断事件类型"""
    INTERRUPTION = 'interruption'
    RECOVERY_ONLY = 'recovery_only'
    NO_MODEL_SPEECH = 'no_model_speech'


class BehaviorLabel(str, Enum):
    """行为分类标签（四选一）"""
    RESPOND = '回应'
    RECOVER = '恢复'
    UNCERTAIN = '不确定询问'
    UNKNOWN = '未知'

    @property
    def field_name(self) -> str:
        """对应输出字段名"""
        return {
            BehaviorLabel.RESPOND: 'behavior_respond',
            BehaviorLabel.RECOVER: 'behavior_recover',
            BehaviorLabel.UNCERTAIN: 'behavior_uncertain',
            BehaviorLabel.UNKNOWN: 'behavior_unknown',
        }[self]


class SceneLabel(str, Enum):
    """拒识/打断场景标签（用于场景定义 dict 的 key）"""
    BYSTANDER_TALK = '旁人交谈'
    ENV_NOISE = '环境噪声'
    FEEDBACK_WORD = '反馈词'
    PHYSIO_SOUND = '生理声'
    ENV_RECALL = '环境回溯'

    INTERRUPTION_INTERJECT = '插话打断'
    STOP_COMMAND = '停止指令'
    RESUME_TOPIC = '恢复原话题'
