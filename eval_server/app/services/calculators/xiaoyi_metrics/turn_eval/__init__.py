# -*- coding: utf-8 -*-
"""turn_eval 包：逐轮三分类评估（误解管 / 接管 / 未接管）

独立主维度，从 turn_taking 拆出，专注逐轮三分类 + 接管时延 + 回复质量。

ASR 词级时间戳获取复用 turn_taking 包的 _get_asr_chunks。
"""
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase

logger = __import__('logging').getLogger(__name__)
