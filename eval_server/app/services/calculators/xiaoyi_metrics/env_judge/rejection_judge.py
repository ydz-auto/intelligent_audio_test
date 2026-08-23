# -*- coding: utf-8 -*-
"""rejection_judge.py
拒识场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，评估模型在拒识场景下的行为

用户输入音频包含两部分内容：
    第一段为用户交互内容，第二段为拒识干扰内容

行为类别（五选一）:
    回应 / 恢复 / 询问 / 无关回复 / 沉默

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
REJECTION_SCENES = {
    '旁人交谈': '目标用户正在与旁边的人交谈，非与模型对话。',
    '环境噪声': '录屏中出现环境噪声，如关门声、交通噪声、音乐声等非语音噪声。',
    '反馈词': '用户在交互过程中发出"嗯""啊""好的""对"等短反馈词，不具备发起新请求的意图。',
    '生理声': '用户出现咳嗽、喷嚏、笑声等非语言意图的生理性声音。',
    '环境回溯': '在交互过程中，背景出现可识别的环境事件（如地铁广播、公交报站、闹钟等）。',
}

# 行为类别定义
REJECTION_BEHAVIORS = """- 回应：模型针对用户的真实意图或主动询问给出了直接、相关的回复。包括场景5中用户询问环境事件后模型正确识别并作答的情况。
- 恢复：模型未直接回应当前输入，但其回复内容已自然回到此前的话题或交互主线，体现出对话恢复能力。
- 询问：模型对用户的意图进行追问、澄清或确认（如"您是想了解……吗？"），而非直接给出答案。
- 无关回复：模型产生了回复，但内容与当前用户意图、对话上下文或场景要求无关。包括本应沉默却给出了回复。
- 沉默：模型未产生任何有效回复（无声、空回复、兜底拒答等）。"""


# ─────────── prompt 构建 ───────────
def build_rejection_prompt(timeline_text: str = '') -> str:
    """构建拒识场景评估 prompt

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
    for i, (key, definition) in enumerate(REJECTION_SCENES.items(), 1):
        scene_blocks.append(
            f"场景{i} — {key}\n"
            f"  {definition}"
        )
    scenes_text = '\n\n'.join(scene_blocks)

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】以及下方【用户侧 ASR 时间线】。

用户输入音频包含两部分内容：第一段为用户交互内容，第二段为拒识干扰内容（非交互意图语音）。上述场景定义涵盖了拒识干扰内容的类型。

请结合回复音频、时间线和场景定义，判断在接收到非交互意图语音后，模型表现出的行为类别，并给出理由。

{timeline_block}═══════════════════════════════════════
【场景定义】（拒识干扰内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{REJECTION_BEHAVIORS}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【询问】【无关回复】【沉默】五个类别之一
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为"""


# ─────────── 主入口 ───────────
def evaluate_rejection_judge(
    ai_wav: str = '',
    user_wav: str = '',
) -> Dict[str, Any]:
    """拒识场景 LLM 裁判主入口

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
    prompt = build_rejection_prompt(timeline_text)

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
        logger.error(f'[rejection_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[rejection_judge] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    evaluations = parse_evaluations(parsed)
    result['evaluations'] = evaluations
    result['message'] = 'OK'

    logger.info(
        f'[rejection_judge] '
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
        description='拒识场景 LLM 裁判：评估模型在拒识场景下的行为'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    args = parser.parse_args()

    r = evaluate_rejection_judge(
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
