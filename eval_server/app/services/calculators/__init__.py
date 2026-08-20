"""calculators 包：策略模式实现，各任务类型的 Calculator 集中注册。

import 本包即自动完成所有内置 calculator 的注册。

策略类按域分子包，策略类和实现函数放一起：
  - wer/            wer / ser / cpwer / tcpwer / stm_wer
  - der/            der
  - xiaoyi_metrics/ turn_taking / interruption_metrics / non_interactive_latency / noise_latency / env_judge / llm_judge
"""
from app.services.calculators.base import BaseCalculator
from app.services.calculators.wer.strategies import (
    WerCalculator, SerCalculator, CpwerCalculator, TcpwerCalculator, StmWerCalculator,
)
from app.services.calculators.der.strategy import DerCalculator
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import (
    TurnTakingCalculator, InterruptionMetricsCalculator,
)
from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.strategy import (
    NonInteractiveLatencyCalculator, NoiseLatencyCalculator,
)
from app.services.calculators.xiaoyi_metrics.env_judge.strategy import EnvJudgeCalculator
from app.services.calculators.xiaoyi_metrics.llm_judge.strategy import LlmJudgeCalculator

# ── 自动注册 ──
from app.services.task_service import TaskService

TaskService.register_calculator('wer', WerCalculator())
TaskService.register_calculator('ser', SerCalculator())
TaskService.register_calculator('cpwer', CpwerCalculator())
TaskService.register_calculator('tcpwer', TcpwerCalculator())
TaskService.register_calculator('stm_wer', StmWerCalculator())
TaskService.register_calculator('der', DerCalculator())
TaskService.register_calculator('llm_judge', LlmJudgeCalculator())
TaskService.register_calculator('turn_taking', TurnTakingCalculator())
TaskService.register_calculator('interruption_metrics', InterruptionMetricsCalculator())
TaskService.register_calculator('non_interactive_latency', NonInteractiveLatencyCalculator())
TaskService.register_calculator('noise_latency', NoiseLatencyCalculator())
TaskService.register_calculator('env_judge', EnvJudgeCalculator())
