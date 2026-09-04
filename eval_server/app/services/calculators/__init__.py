"""calculators 包：策略模式实现，各任务类型的 Calculator 集中注册。

import 本包即自动完成所有内置 calculator 的注册。

策略类按域分子包，策略类和实现函数放一起：
  - wer/            wer / ser / cpwer / tcpwer / stm_wer
  - der/            der
  - xiaoyi_metrics/
      __init__.py   XiaoyiMetricsCalculator（全域编排：统一共享 ASR + 跨域子维度聚合）
      turn_taking/  TurnTakingCalculator（域内编排：tor / false_takeover /
                    takeover_latency / high_freq_turn_taking / high_freq_llm_judge）
      interruptibility/  interruption_metrics
      rejection_scene_awareness/  non_interactive_latency / noise_latency
      env_judge/     rejection_judge / interruption_judge
      llm_judge/     llm_judge
"""
from app.services.calculators.base import BaseCalculator
from app.services.calculators.wer.strategies import (
    WerCalculator, SerCalculator, CpwerCalculator, TcpwerCalculator, StmWerCalculator,
)
from app.services.calculators.der.strategy import DerCalculator
from app.services.calculators.xiaoyi_metrics import XiaoyiMetricsCalculator
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import (
    TurnTakingCalculator, TorCalculator, FalseTakeoverCalculator,
    TakeoverLatencyCalculator, HighFreqTurnTakingCalculator,
    HighFreqLlmJudgeCalculator,
)
from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.strategy import (
    NonInteractiveLatencyCalculator, NoiseLatencyCalculator,
)
from app.services.calculators.xiaoyi_metrics.env_judge.strategy import (
    RejectionJudgeCalculator, InterruptionJudgeCalculator,
)
from app.services.calculators.xiaoyi_metrics.llm_judge.strategy import LlmJudgeCalculator
from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
    InterruptionMetricsCalculator,
)

# ── 自动注册 ──
from app.services.task_service import TaskService

TaskService.register_calculator('wer', WerCalculator())
TaskService.register_calculator('ser', SerCalculator())
TaskService.register_calculator('cpwer', CpwerCalculator())
TaskService.register_calculator('tcpwer', TcpwerCalculator())
TaskService.register_calculator('stm_wer', StmWerCalculator())
TaskService.register_calculator('der', DerCalculator())
# xiaoyi_metrics 全域编排：统一共享 ASR + 跨域子维度聚合
TaskService.register_calculator('xiaoyi_metrics', XiaoyiMetricsCalculator())
# turn_taking 域：域内编排 + 子维度
TaskService.register_calculator('turn_taking', TurnTakingCalculator())
TaskService.register_calculator('tor', TorCalculator())
TaskService.register_calculator('false_takeover', FalseTakeoverCalculator())
TaskService.register_calculator('takeover_latency', TakeoverLatencyCalculator())
TaskService.register_calculator('high_freq_turn_taking', HighFreqTurnTakingCalculator())
TaskService.register_calculator('high_freq_llm_judge', HighFreqLlmJudgeCalculator())
# interruptibility 域
TaskService.register_calculator('interruption_metrics', InterruptionMetricsCalculator())
# rejection_scene_awareness 域
TaskService.register_calculator('non_interactive_latency', NonInteractiveLatencyCalculator())
TaskService.register_calculator('noise_latency', NoiseLatencyCalculator())
# env_judge 域 → 拆分为两个独立子维度
TaskService.register_calculator('rejection_judge', RejectionJudgeCalculator())
TaskService.register_calculator('interruption_judge', InterruptionJudgeCalculator())
# llm_judge 域
TaskService.register_calculator('llm_judge', LlmJudgeCalculator())
