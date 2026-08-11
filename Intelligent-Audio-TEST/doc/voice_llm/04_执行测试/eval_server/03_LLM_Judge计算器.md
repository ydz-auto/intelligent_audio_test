# 03 — LLM Judge 计算器

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：新增  
> **涉及文件**：`eval_server/app/services/llm_judge_calculator.py`（新建）

---

## 背景

LLM Judge 使用大语言模型（如 GPT-4）对对话输出进行语义级评分，适用于 voice_llm 场景中的对话质量评估。相比 WER 等自动化指标，LLM Judge 能评估语义准确性、流畅度、相关性等维度。

---

## 改造内容

### 1. 新文件 `llm_judge_calculator.py`

```python
"""LLM Judge calculator for voice_llm evaluation."""

import json
import time
import requests
from typing import Optional
from app.utils.logger import logger


# LLM API 配置（从环境变量或 config 读取）
LLM_API_BASE_URL = None  # 运行时从 config 获取
LLM_API_KEY = None
LLM_DEFAULT_TIMEOUT = 120


def evaluate_with_llm(
    hypothesis: str,
    reference: str,
    model: str = 'gpt-4',
    prompt_template: str = '',
    max_tokens: int = 1024,
    temperature: float = 0.1,
    scoring_criteria: Optional[list] = None,
    source_lang: str = 'zh',
    target_lang: str = 'en',
    **kwargs
) -> dict:
    """
    使用 LLM 对 hypothesis 进行评分。

    Args:
        hypothesis: 被测系统输出文本
        reference: 参考文本（标准答案）
        model: LLM 模型名称
        prompt_template: 评分 prompt 模板
        max_tokens: 最大输出 token 数
        temperature: 温度参数
        scoring_criteria: 评分维度列表

    Returns:
        {
            "llm_judge_score": 4.2,
            "criteria_scores": {
                "accuracy": 4.5,
                "fluency": 4.0,
                "relevance": 4.0
            },
            "reasoning": "...",
            "model": "gpt-4",
            "tokens_used": 256
        }
    """
    # 构建评分 prompt
    prompt = _build_evaluation_prompt(
        hypothesis=hypothesis,
        reference=reference,
        prompt_template=prompt_template,
        scoring_criteria=scoring_criteria,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    # 调用 LLM API
    response = _call_llm_api(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # 解析评分结果
    result = _parse_llm_response(response)

    result['model'] = model
    result['source_lang'] = source_lang
    result['target_lang'] = target_lang

    return result
```

### 2. 评分 Prompt 构建

```python
def _build_evaluation_prompt(hypothesis, reference, prompt_template,
                              scoring_criteria, source_lang, target_lang):
    """构建 LLM 评分 prompt"""
    if prompt_template:
        # 使用自定义模板
        return prompt_template.format(
            hypothesis=hypothesis,
            reference=reference,
        )

    # 默认模板
    criteria_text = ''
    if scoring_criteria:
        for idx, criterion in enumerate(scoring_criteria, 1):
            criteria_text += f'{idx}. {criterion}\n'
    else:
        criteria_text = (
            '1. Accuracy: How accurately does the hypothesis match the reference?\n'
            '2. Fluency: How fluent and natural is the hypothesis?\n'
            '3. Relevance: How relevant is the hypothesis to the context?\n'
        )

    return f"""You are a professional translation/ASR quality evaluator.

Reference (ground truth):
{reference}

Hypothesis (system output):
{hypothesis}

Please evaluate the hypothesis on a scale of 1-5 for each criterion:
{criteria_text}

Respond in the following JSON format:
{{
    "scores": {{
        "criterion_name": score
    }},
    "overall_score": average_score,
    "reasoning": "brief explanation"
}}

Only respond with the JSON, no additional text."""
```

### 3. LLM API 调用

```python
def _call_llm_api(model, prompt, max_tokens, temperature):
    """调用 LLM API（兼容 OpenAI API 格式）"""
    from app.config import config

    api_base = config.get('llm_judge', {}).get('api_base_url', '')
    api_key = config.get('llm_judge', {}).get('api_key', '')

    if not api_base or not api_key:
        raise ValueError('LLM Judge API not configured')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are a precise evaluator.'},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'response_format': {'type': 'json_object'},
    }

    response = requests.post(
        f'{api_base}/chat/completions',
        headers=headers,
        json=payload,
        timeout=LLM_DEFAULT_TIMEOUT,
    )

    response.raise_for_status()
    data = response.json()

    return {
        'content': data['choices'][0]['message']['content'],
        'tokens_used': data.get('usage', {}).get('total_tokens', 0),
    }
```

### 4. 响应解析

```python
def _parse_llm_response(response):
    """解析 LLM 返回的评分结果"""
    content = response['content']

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # 尝试从文本中提取 JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            return {
                'llm_judge_score': 0,
                'criteria_scores': {},
                'reasoning': f'Failed to parse LLM response: {content[:200]}',
                'tokens_used': response.get('tokens_used', 0),
            }

    scores = result.get('scores', {})
    overall = result.get('overall_score')

    if overall is None and scores:
        overall = sum(scores.values()) / len(scores)

    return {
        'llm_judge_score': round(overall or 0, 2),
        'criteria_scores': {k: round(v, 2) for k, v in scores.items()},
        'reasoning': result.get('reasoning', ''),
        'tokens_used': response.get('tokens_used', 0),
    }
```

### 5. 注册到 TaskService

```python
# task_service.py
from app.services.llm_judge_calculator import evaluate_with_llm

class TaskService:
    @classmethod
    def calculate(cls, task_type, task_params):
        # ...
        elif task_type == 'llm_judge':
            return evaluate_with_llm(
                hypothesis=task_params['hypothesis'],
                reference=task_params['reference'],
                model=task_params.get('model', 'gpt-4'),
                prompt_template=task_params.get('prompt_template', ''),
                max_tokens=task_params.get('max_tokens', 1024),
                temperature=task_params.get('temperature', 0.1),
                scoring_criteria=task_params.get('scoring_criteria'),
                source_lang=task_params.get('source_lang', 'zh'),
                target_lang=task_params.get('target_lang', 'en'),
            )
```

### 6. 配置项

在 `eval_server/app/config.py` 中新增：

```python
class Config:
    # ... 现有配置 ...

    # LLM Judge 配置
    LLM_JUDGE = {
        'api_base_url': os.environ.get('LLM_JUDGE_API_BASE', ''),
        'api_key': os.environ.get('LLM_JUDGE_API_KEY', ''),
        'default_model': 'gpt-4',
        'timeout': 120,
    }
```

---

## 不变部分

- 现有计算器不变
- TaskService 调度框架不变
- 任务存储不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` | 任务入口 |
| `24_evaluation_service_llm_judge分发` (主后端) | 请求发送方 |
| `25_Evaluation页面_llm_judge维度` (frontend) | 维度配置 |
