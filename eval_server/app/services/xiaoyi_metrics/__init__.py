# -*- coding: utf-8 -*-
"""xiaoyi_metrics 包

评估指标已迁移至子包 turn_taking：
    - tor (正确回复率)
    - false_takeover (误接管率)
    - takeover_latency (接管时延)
    - input_asr (输入识别准确率)
    - interruption (打断指标)
    - non_interactive_latency (非交互意图时延)
    - interruption_llm (打断 LLM 评估)
    - noise_latency (噪声打断时延)
    - env_sound_judge (环境音裁判)

统一入口见 turn_taking.calculate_xiaoyi_metrics。
"""
