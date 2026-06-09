# 02 — BLEU 计算器

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：新增  
> **涉及文件**：`eval_server/app/services/bleu_calculator.py`（新建）

---

## 背景

BLEU（Bilingual Evaluation Understudy）是机器翻译质量评估的经典指标，通过比较候选翻译与参考翻译的 n-gram 重叠度来计算分数。voice_llm 测试中用于评估 LLM 输出的翻译质量。

---

## 改造内容

### 1. 新文件 `bleu_calculator.py`

```python
"""BLEU score calculator for voice_llm evaluation."""

import re
from collections import Counter
from typing import Optional


def tokenize(text: str, lang: str = 'auto') -> list[str]:
    """
    将文本分词为 token 列表。

    Args:
        text: 输入文本
        lang: 语言 ('zh'/'en'/'auto')
    """
    if lang == 'zh' or (lang == 'auto' and _is_chinese(text)):
        # 中文按字切分
        return [ch for ch in text if ch.strip()]
    else:
        # 英文按空格分词
        return text.lower().split()


def _is_chinese(text: str) -> bool:
    """判断文本是否主要为中文"""
    chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return chinese_chars > len(text) * 0.3


def compute_bleu(
    hypothesis: str,
    reference: str,
    source_lang: str = 'zh',
    target_lang: str = 'en',
    max_order: int = 4,
    smooth: bool = True,
    normalize: bool = True,
) -> dict:
    """
    计算 BLEU 分数。

    Args:
        hypothesis: 候选翻译文本
        reference: 参考翻译文本
        source_lang: 源语言
        target_lang: 目标语言
        max_order: n-gram 最大阶数（默认 4）
        smooth: 是否使用平滑（避免 0 分）
        normalize: 是否标准化文本

    Returns:
        {
            "bleu": 0.85,
            "bleu_1": 0.92,
            "bleu_2": 0.88,
            "bleu_3": 0.85,
            "bleu_4": 0.82,
            "brevity_penalty": 1.0,
            "precisions": [0.95, 0.90, 0.85, 0.80],
            "hypothesis_length": 15,
            "reference_length": 14,
            "source_lang": "zh",
            "target_lang": "en"
        }
    """
    if normalize:
        hypothesis = _normalize_text(hypothesis)
        reference = _normalize_text(reference)

    hyp_tokens = tokenize(hypothesis, target_lang)
    ref_tokens = tokenize(reference, target_lang)

    hyp_len = len(hyp_tokens)
    ref_len = len(ref_tokens)

    if hyp_len == 0:
        return _empty_result(source_lang, target_lang)

    # 计算各阶 n-gram 精确率
    precisions = []
    for order in range(1, max_order + 1):
        hyp_ngrams = _get_ngrams(hyp_tokens, order)
        ref_ngrams = _get_ngrams(ref_tokens, order)

        # 计算匹配数
        matches = 0
        for ngram, count in hyp_ngrams.items():
            matches += min(count, ref_ngrams.get(ngram, 0))

        total = sum(hyp_ngrams.values())

        if total == 0:
            precision = 0.0
        elif smooth and matches == 0:
            # 加 1 平滑
            precision = 1.0 / (total + 1)
        else:
            precision = matches / total

        precisions.append(precision)

    # 计算 brevity penalty
    if hyp_len > ref_len:
        bp = 1.0
    elif hyp_len == 0:
        bp = 0.0
    else:
        bp = math.exp(1.0 - ref_len / hyp_len)

    # 计算几何平均（对数空间）
    log_precisions = []
    for p in precisions:
        if p > 0:
            log_precisions.append(math.log(p))
        else:
            log_precisions.append(float('-inf'))

    log_avg = sum(log_precisions) / len(log_precisions)
    bleu_score = bp * math.exp(log_avg)

    # 各阶 BLEU
    bleu_n = {}
    for i in range(max_order):
        partial_log_avg = sum(log_precisions[:i+1]) / (i+1)
        bleu_n[f'bleu_{i+1}'] = round(bp * math.exp(partial_log_avg), 4)

    return {
        'bleu': round(bleu_score, 4),
        **bleu_n,
        'brevity_penalty': round(bp, 4),
        'precisions': [round(p, 4) for p in precisions],
        'hypothesis_length': hyp_len,
        'reference_length': ref_len,
        'source_lang': source_lang,
        'target_lang': target_lang,
    }


def _get_ngrams(tokens: list[str], n: int) -> Counter:
    """提取 n-gram 计数"""
    return Counter(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))


def _normalize_text(text: str) -> str:
    """标准化文本：去标点、统一空格"""
    text = re.sub(r'[。.!?！？，,、；;：:""\'\'（）()\[\]{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _empty_result(source_lang, target_lang):
    return {
        'bleu': 0.0,
        'bleu_1': 0.0, 'bleu_2': 0.0, 'bleu_3': 0.0, 'bleu_4': 0.0,
        'brevity_penalty': 0.0,
        'precisions': [0.0, 0.0, 0.0, 0.0],
        'hypothesis_length': 0,
        'reference_length': 0,
        'source_lang': source_lang,
        'target_lang': target_lang,
    }
```

### 2. 注册到 TaskService

```python
# task_service.py
from app.services.bleu_calculator import compute_bleu

class TaskService:
    CALCULATORS = {}

    @classmethod
    def register_calculator(cls, task_type, func):
        cls.CALCULATORS[task_type] = func

    @classmethod
    def calculate(cls, task_type, task_params):
        if task_type in cls.CALCULATORS:
            return cls.CALCULATORS[task_type](**task_params)

        if task_type == 'bleu':
            return compute_bleu(
                hypothesis=task_params['hypothesis'],
                reference=task_params['reference'],
                source_lang=task_params.get('source_lang', 'zh'),
                target_lang=task_params.get('target_lang', 'en'),
                normalize=task_params.get('normalize', True),
            )

        # ... 其他类型 ...
```

### 3. 与 NLTK/sacreBLEU 的对比

| 特性 | 本实现 | NLTK | sacreBLEU |
|------|--------|------|-----------|
| 外部依赖 | 无 | nltk | sacrebleu |
| 中文支持 | 按字切分 | 需额外分词 | 需 tokenizer |
| 平滑 | 加 1 平滑 | 多种策略 | 多种策略 |
| 轻量 | 是 | 否 | 否 |

---

## 不变部分

- 现有 WER/SER/DER 计算器不变
- TaskService 的调度框架不变
- 任务存储和状态管理不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` | 任务入口 |
| `26_evaluation_api_client适配` (主后端) | 请求发送方 |
