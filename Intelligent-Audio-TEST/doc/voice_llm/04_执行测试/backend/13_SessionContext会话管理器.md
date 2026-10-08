# 13_SessionContext 会话管理器

> 新增类：`backend/utils/session_context.py`

## 功能说明

SessionContext 管理 API 多轮会话的生命周期：创建会话、维护对话上下文、收集轮次结果、销毁会话。

## 类设计

```python
class SessionContext:
    """API 多轮会话上下文管理器"""
    
    def __init__(self, session_id: str, config: dict):
        """初始化会话
        
        Args:
            session_id: 会话唯一标识（UUID）
            config: 会话配置
                - session_timeout: int — 单轮超时时间（秒），默认 60
                - context_mode: str — 上下文模式：'full' | 'sliding_window'
                - max_history_rounds: int — 滑动窗口模式下保留的历史轮次数
        """
        self.session_id = session_id
        self.session_timeout = config.get('session_timeout', 60)
        self.context_mode = config.get('context_mode', 'full')
        self.max_history_rounds = config.get('max_history_rounds', 5)
        
        # 内部状态
        self._history: list[dict] = []  # 对话历史
        self._round_results: list[dict] = []      # 轮次结果
        self._created_at = time.time()
        self._is_active = True

    @property
    def is_active(self) -> bool:
        return self._is_active

    def add_history(self, round_number: int, input_text: str, output_text: str):
        """添加一轮对话历史"""
        self._history.append({
            'round': round_number,
            'input': input_text,
            'output': output_text,
            'timestamp': time.time()
        })

    def get_context(self) -> list[dict]:
        """获取当前上下文历史
        
        根据 context_mode 返回全量或滑动窗口的历史
        """
        if self.context_mode == 'sliding_window':
            return self._history[-self.max_history_rounds:]
        return self._history  # 'full' 模式返回全部

    def add_round_result(self, round_result: dict):
        """记录本轮结果"""
        self._round_results.append(round_result)

    def get_round_results(self) -> list[dict]:
        """获取所有轮次结果"""
        return self._round_results

    def get_summary(self) -> dict:
        """获取会话摘要"""
        total_latency = sum(r.get('latency', 0) for r in self._round_results)
        return {
            'session_id': self.session_id,
            'round_count': len(self._round_results),
            'total_latency': total_latency,
            'context_mode': self.context_mode,
            'history_count': len(self._history),
            'error': None,
            'rounds': self._round_results,
            'duration': time.time() - self._created_at
        }

    def destroy(self):
        """销毁会话"""
        self._is_active = False
        self._history.clear()
```

## 生命周期管理

```python
# 在 api_executor.py 中使用
from .session_context import SessionContext
import uuid

def _execute_voice_llm_session(self, api, test_case, ...):
    # 创建会话
    session_id = str(uuid.uuid4())
    session = SessionContext(session_id, {
        'session_timeout': algorithm_params.get('session_timeout', 60),
        'context_mode': algorithm_params.get('context_mode', 'full'),
        'max_history_rounds': algorithm_params.get('max_history_rounds', 5)
    })
    
    try:
        rounds = test_case.config.get('rounds', [])
        for i, round_config in enumerate(rounds):
            round_number = i + 1
            
            # 构建并发送请求
            round_result = self._send_round_request(
                api, session, round_number, round_config
            )
            
            # 更新上下文
            session.add_history(
                round_number,
                round_result['input'],
                round_result['output']
            )
            session.add_round_result(round_result)
            
            # 可选：单轮评估
            # ...
        
        # 汇总结果
        return {
            'rounds': session.get_round_results(),
            **session.get_summary()
        }
    finally:
        session.destroy()
```

## 上下文模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `full` | 每轮请求携带全部历史对话 | 需要完整上下文的对话 |
| `sliding_window` | 仅保留最近 N 轮对话 | 长对话，避免上下文过长 |

## 引用关系

- ← `04_执行测试/backend/12_api_executor多轮会话主循环` — 主循环创建和使用 SessionContext
- → `04_执行测试/backend/14_轮次请求构建` — 轮次请求使用 get_context()
- → `04_执行测试/api_adapter/02_会话状态管理` — api_adapter 端的会话管理
