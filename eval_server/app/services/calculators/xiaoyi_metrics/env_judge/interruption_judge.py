# -*- coding: utf-8 -*-
"""interruption_judge.py
打断场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，评估模型在打断场景下的行为

用户输入音频包含两部分内容：
    第一段为用户交互内容，第二段为打断干扰内容

行为类别（四选一）:
    回应 / 恢复 / 不确定询问 / 未知

输出: 严格 JSON，{behavior, reason}
"""
import json
import os
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.xiaoyi_metrics.env_judge._common import (
    call_llm_api,
    build_timeline_text,
    parse_json,
    parse_evaluations,
    get_asr_chunks,
)

logger = logging.getLogger(__name__)


# ─────────── 场景定义 ───────────
INTERRUPTION_SCENES = {
    '插话打断': '模型正在输出回复时，用户插话打断了模型，用户发起新的提问或请求。',
    '停止指令': '用户对模型发出明确的停止指令，如"停""闭嘴""不用了""停下来""好了好了"等。',
    '恢复原话题': '在多轮对话中，用户打断并切换了话题（如询问天气、时间等），模型完成打断话题的回复后，用户要求回到原始话题（如"我们继续聊刚才说的""回到之前的话题"）。',
}

# 行为类别定义
INTERRUPTION_BEHAVIORS = """- 回应：模型对重叠内容进行了有意义的回应，包括回答、澄清或对重叠中提到或引入的内容做出反应。
- 恢复：模型忽略重叠，继续或完成重叠之前正在进行中的任务或回答。
- 不确定询问：模型表示不确定或难以听清、缺少信息（如"我没听清…""能重复一下吗？"），未给出明确的、针对内容的回答。所有泛化的重复或澄清行为归入此类。
- 未知：模型输出语义偏离目标或信息量低，未明确恢复、回应或表达不确定（如无关填充语、模板化噪音）。包括重叠后模型完全没有语音输出的情况。"""


# ─────────── prompt 构建 ───────────
def build_interruption_prompt(timeline_text: str = '') -> str:
    """构建打断场景评估 prompt

    Args:
        timeline_text: 用户侧 ASR 转写时间线
    """
    timeline_block = ''
    if timeline_text:
        timeline_block = (
            '═══════════════════════════════════════\n'
            '【用户侧 ASR 时间线】\n'
            '═══════════════════════════════════════\n\n'
            f'{timeline_text}\n\n'
        )

    scene_blocks = []
    for i, (key, definition) in enumerate(INTERRUPTION_SCENES.items(), 1):
        scene_blocks.append(
            f"场景{i} — {key}\n"
            f"  {definition}"
        )
    scenes_text = '\n\n'.join(scene_blocks)

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】以及下方【用户侧 ASR 时间线】。

用户输入音频包含两部分内容：第一段为用户交互内容，第二段为打断干扰内容。上述场景定义涵盖了打断干扰内容的类型。

请结合回复音频、时间线和场景定义，判断在接收到打断干扰内容后，模型表现出的行为类别，并给出理由。

{timeline_block}═══════════════════════════════════════
【场景定义】（打断干扰内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（四选一，仅可选其一）
═══════════════════════════════════════

{INTERRUPTION_BEHAVIORS}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【不确定询问】【未知】四个类别之一
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为"""


# ─────────── 主入口 ───────────
def evaluate_interruption_judge(
    ai_wav: str = '',
    user_wav: str = '',
) -> Dict[str, Any]:
    """打断场景 LLM 裁判主入口

    以【模型回复音频 ai_wav】为主输入（裁判模型直接听回复，不过小 ASR），
    用户侧 ASR 转写作为文本时间线上下文。

    model / max_tokens / temperature 均从 .env 配置读取。

    Args:
        ai_wav: 模型回复音频路径（主输入，被判定对象）
        user_wav: 用户通道音频路径（用于生成用户侧 ASR 时间线上下文）

    Returns:
        dict: {
            'enabled': True,
            'model': str,
            'ai_wav': str,
            'evaluations': [{behavior, reason}, ...],
            'tokens_used': int,
            'input_token': int,
            'output_token': int,
            'message': str,
        }
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    model = llm_config.get('default_model', 'gpt-4o')
    max_tokens = llm_config.get('max_tokens', 4096)
    temperature = llm_config.get('temperature', 0.1)

    # 主音频：ai_wav（模型回复，被判定对象）
    if not ai_wav or not os.path.isfile(ai_wav):
        raise FileNotFoundError(
            f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        )

    file_paths: List[str] = [ai_wav]

    # ── 构建文本时间线（用户侧 ASR） ──
    user_chunks: Optional[List[Dict[str, Any]]] = None
    if user_wav and os.path.isfile(user_wav):
        user_chunks = get_asr_chunks(user_wav)

    timeline_text = build_timeline_text(user_chunks)
    prompt = build_interruption_prompt(timeline_text)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'evaluations': [],
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    try:
        response = call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=file_paths,
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[interruption_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[interruption_judge] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    evaluations = parse_evaluations(parsed)
    result['evaluations'] = evaluations
    result['message'] = 'OK'

    logger.info(
        f'[interruption_judge] '
        f'model={model} ai_wav={ai_wav} '
        f'n_evaluations={len(evaluations)} '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    # 独立运行时加载 eval_server/.env
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='打断场景 LLM 裁判：评估模型在打断场景下的行为'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    args = parser.parse_args()

    r = evaluate_interruption_judge(
        ai_wav=args.ai_wav,
        user_wav=args.user_wav,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for ev in r.get('evaluations', []):
        print(f'\n  行为: {ev.get("behavior", "")}')
        print(f'  理由: {ev.get("reason", "")}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
