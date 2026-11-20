# -*- coding: utf-8 -*-
"""LLM 端口（OpenAI 兼容适配器的抽象）。

application/run_orchestrator.py 只依赖本端口；具体 HTTP / 流式解析在
infrastructure/llm/openai_compatible.py。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from agent_service.domain.model.entities import LlmMessage, ToolCallRequest


@dataclass(frozen=True)
class LlmInstruction:
    """system + 激活 Skill 正文等常驻指令。"""

    system_prompt: str


@dataclass(frozen=True)
class LlmRequest:
    """一次模型调用的输入。"""

    messages: Tuple[LlmMessage, ...]
    tools: Tuple[Dict[str, Any], ...] = ()
    model: str = ''
    temperature: float = 0.2
    max_output_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmTextDelta:
    """流式文本增量。"""

    text: str


@dataclass(frozen=True)
class LlmToolCalls:
    """一轮中模型给出的工具调用批次（并行执行）。"""

    calls: Tuple[ToolCallRequest, ...]


@dataclass(frozen=True)
class LlmUsage:
    """token 用量（用于 run 预算）。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class LlmFinished:
    """模型本轮结束（finish_reason 仅用于诊断）。"""

    finish_reason: str = 'stop'


LlmChunk = Any  # LlmTextDelta | LlmToolCalls | LlmUsage | LlmFinished
CancelCheck = Callable[[], bool]


class LlmClient(ABC):
    """模型客户端：同步流式（线程内消费），便于与现有线程池架构一致。"""

    @abstractmethod
    def stream(self, request: LlmRequest,
               cancel_check: Optional[CancelCheck] = None) -> Iterator[LlmChunk]:
        """按到达顺序产出 LlmTextDelta / LlmToolCalls / LlmUsage / LlmFinished。

        cancel_check 返回 True 时应尽快结束迭代（抛 RunCancelled 或直接 return）。
        """

    model: str = ''
