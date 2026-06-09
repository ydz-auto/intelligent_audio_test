# 16_API 测试结果存储结构

> 文件：`backend/utils/api_executor.py`、`backend/models/models.py`

## 功能说明

多轮 API 测试（用例配置了 `rounds`）的 `TestResult.algorithm_result` JSON 结构，包含多轮对话的完整结果。配置驱动，不绑定算法类型。

## 存储结构

```json
{
    "session_id": "uuid-xxx-xxx",
    "round_count": 3,
    "total_latency": 4.52,
    "context_mode": "full",
    "history_count": 3,
    "error": null,
    "rounds": [
        {
            "roundNumber": 1,
            "inputType": "text",
            "input": "你好",
            "output": "你好！有什么可以帮你的？",
            "latency": 1.23,
            "response_metrics": {
                "first_token_latency": 0.3,
                "tokens_per_second": 25
            },
            "round_evaluation": {
                "wer": 0.02,
                "bleu": 0.95,
                "llm_judge": 4.9
            }
        },
        {
            "roundNumber": 2,
            "inputType": "text",
            "input": "今天天气怎么样",
            "output": "今天北京天气晴朗，温度 25°C。",
            "latency": 1.87,
            "response_metrics": {},
            "round_evaluation": {
                "wer": 0.03,
                "bleu": 0.93,
                "llm_judge": 4.7
            }
        },
        {
            "roundNumber": 3,
            "inputType": "audio",
            "input": "audio_id_xxx",
            "output": "我听到了你的问题...",
            "output_audio_path": "/results/audio_round3.wav",
            "latency": 1.42,
            "response_metrics": {},
            "round_evaluation": {
                "wer": 0.04,
                "bleu": 0.90,
                "llm_judge": 4.5
            }
        }
    ]
}
```

## 与现有单结果结构的兼容

| 字段 | 现有结构（单轮） | 多轮会话结构（rounds 非空） |
|------|---------|---------------|
| `algorithm_result` | 单层 dict | 含 `rounds` 数组的 dict |
| `recognized_text` | 顶层字段 | 取最后一轮的 `output` |
| `reference_text` | 顶层字段 | 顶层保留（来自用例配置） |
| `audio_duration` | 顶层字段 | 替换为 `total_latency` |

### 兼容字段提取

```python
# algorithm_result_field_mapper.py
def extract_compatible_fields(self, algorithm_type, algorithm_result):
    if algorithm_type == 'voice_llm':
        rounds = algorithm_result.get('rounds', [])
        last_round = rounds[-1] if rounds else {}
        return {
            'recognized_text': last_round.get('output', ''),
            'audio_duration': algorithm_result.get('total_latency', 0),
            'process_time': algorithm_result.get('total_latency', 0)
        }
    return algorithm_result  # 现有算法不变
```

## TestResultDimension 存储

多轮评估的维度评分存储在 `TestResultDimension` 中：

```python
# 整体评估维度
TestResultDimension(
    test_result_id=result_id,
    dimension_name='WER',
    score=92.5,
    weight=50,
    round_number=None  # None 表示整体评估
)

# 单轮评估维度（如果启用）
TestResultDimension(
    test_result_id=result_id,
    dimension_name='WER',
    score=95.0,
    weight=50,
    round_number=1  # 标记为第1轮评估
)
```

## 引用关系

- ← `04_执行测试/backend/12_api_executor多轮会话主循环` — 主循环生成此结构
- → `05_查看结果/backend/11_algorithm_result_field_mapper适配` — 结果字段映射
- → `05_查看结果/frontend/20_TestCaseReportDetail多轮结果` — 前端展示
