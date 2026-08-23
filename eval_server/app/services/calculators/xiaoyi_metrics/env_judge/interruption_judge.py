# -*- coding: utf-8 -*-
"""interruption_judge.py
打断场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，评估模型在打断场景下的行为

场景:
    1. 插话打断与重新响应 — 用户插话后模型应停止并重新响应
    2. 停止指令响应 — 收到停止指令后立即停止
    3. 多轮对话打断后恢复原话题 — 打断后能恢复到原始话题

行为类别（五选一）:
    回应 / 恢复 / 询问 / 无关回复 / 沉默

输出: 严格 JSON，每场景一个 {scene, behavior, reason}
"""
import json
import os
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.xiaoyi_metrics.env_judge._common import (
    call_llm_api,
    env_events_from_ms,
    build_timeline_text,
    extract_video_paths,
    parse_json,
    parse_evaluations,
    get_asr_chunks,
)

logger = logging.getLogger(__name__)


# ─────────── 场景定义 ───────────
INTERRUPTION_SCENES = {
    '插话打断': {
        'name': '场景-插话打断与重新响应',
        'definition': '模型正在输出回复时，用户插话打断了模型（用户发起新的提问或请求）。模型应在感知到用户插话后立即停止当前输出，并根据用户插话内容重新响应。',
        'expect': '模型停止当前输出，并针对用户插话内容给出回应（回应）',
    },
    '停止指令': {
        'name': '场景-停止指令响应',
        'definition': '用户对模型发出明确的停止指令，如"停""闭嘴""不用了""停下来""好了好了"等。模型应在收到停止指令后立即停止当前输出，不应继续说完剩余内容或产生无关回复。',
        'expect': '模型立即停止输出（沉默），或简短确认后停止（回应）',
    },
    '恢复原话题': {
        'name': '场景-多轮对话打断后恢复原话题',
        'definition': '在多轮对话中，用户打断并切换了话题（如询问天气、时间等），模型完成打断话题的回复后，用户要求回到原始话题（如"我们继续聊刚才说的""回到之前的话题"）。模型应能识别用户意图，自然地恢复到打断前的原始话题并继续相关内容。',
        'expect': '模型成功恢复到原始话题并给出相关内容（恢复），或直接回应了回到原话题的请求（回应）',
    },
}

# 行为类别定义
INTERRUPTION_BEHAVIORS = """- 回应：模型针对用户的插话内容、停止指令或回到原话题的请求给出了直接、相关的回复。包括停止后简短确认（"好的"）、针对插话内容作答、直接回应回到原话题的请求。
- 恢复：模型未明确回应当前输入，但其回复内容已自然回到打断前的话题或交互主线，体现出对话恢复能力。典型用于用户要求回到原话题后，模型直接续上了原话题内容。
- 询问：模型对用户的意图进行追问、澄清或确认（如"您是想继续之前的话题吗？"），而非直接给出答案或执行指令。
- 无关回复：模型产生了回复，但内容与当前用户意图、对话上下文或场景要求无关。包括：插话后未停止而继续原输出、收到停止指令后仍继续输出、打断后话题恢复失败且回复内容与原话题无关。
- 沉默：模型未产生任何有效回复（无声、空回复、兜底拒答等）。"""


# ─────────── prompt 构建 ───────────
def build_interruption_prompt(scene: str = '',
                              timeline_text: str = '') -> str:
    """构建打断场景评估 prompt

    Args:
        scene: 指定具体场景名（如 '插话打断'），为空则输出全部场景
        timeline_text: 用户侧 ASR 转写 + 环境声事件时间线
    """
    timeline_block = ''
    if timeline_text:
        timeline_block = (
            '═══════════════════════════════════════\n'
            '【对话/事件时间线】（用户侧已转写为文本，环境声为时间窗；'
            '模型回复以随附音频为准）\n'
            '═══════════════════════════════════════\n\n'
            f'{timeline_text}\n\n'
        )

    if scene and scene in INTERRUPTION_SCENES:
        # ── 单场景 prompt ──
        sc = INTERRUPTION_SCENES[scene]
        return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】以及下方【对话/事件时间线】（用户侧已转写为文本、环境声为时间窗，环境声不可ASR）。本次测试场景为【{scene}】，请仅针对该场景评判模型的行为。

{timeline_block}═══════════════════════════════════════
【场景定义】
═══════════════════════════════════════

{sc['name']}
  {sc['definition']}
  期望行为：{sc['expect']}。

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{INTERRUPTION_BEHAVIORS}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "scene": "{sc['name']}",
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【询问】【无关回复】【沉默】五个类别之一
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为
- 若该场景在音频/时间线中未出现或无法判断，behavior 填"无法判断"并在 reason 中说明原因"""

    else:
        # ── 全场景 prompt ──
        scene_blocks = []
        for i, (key, sc) in enumerate(INTERRUPTION_SCENES.items(), 1):
            scene_blocks.append(
                f"场景{i} — {sc['name'].replace('场景-', '')}\n"
                f"  {sc['definition']}\n"
                f"  期望行为：{sc['expect']}。"
            )
        scenes_text = '\n\n'.join(scene_blocks)

        eval_items = []
        for i, (key, sc) in enumerate(INTERRUPTION_SCENES.items(), 1):
            eval_items.append(
                f'    {{\n'
                f'      "scene": "场景{i}-{sc["name"].replace("场景-", "")}",\n'
                f'      "behavior": "",\n'
                f'      "reason": ""\n'
                f'    }}'
            )
        eval_text = ',\n'.join(eval_items)

        return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】以及下方【对话/事件时间线】（用户侧已转写为文本、环境声为时间窗，环境声不可ASR）。该文件记录了用户与语音大模型的完整交互过程，其中包含多个预设场景，用于考察模型在不同情境下的行为能力。

请结合回复音频与时间线，按照以下【场景定义】判断模型在每个场景中的行为，并给出唯一的【行为类别】和判定依据。

{timeline_block}═══════════════════════════════════════
【场景定义】
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{INTERRUPTION_BEHAVIORS}

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

请对时间线/音频中识别到的每个场景分别评判，输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "evaluations": [
{eval_text}
  ]
}}

其中：
- behavior 必须是【回应】【恢复】【询问】【无关回复】【沉默】五个类别之一
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为
- 若音频/时间线中某个场景未出现或无法判断，behavior 填"无法判断"并在 reason 中说明原因"""


# ─────────── 主入口 ───────────
def evaluate_interruption_judge(
    scene: str = '',
    model: str = '',
    max_tokens: int = 4096,
    temperature: float = 0.1,
    ai_wav: str = '',
    user_wav: str = '',
    env_events: Optional[List[Dict[str, Any]]] = None,
    start_ms=None,
    end_ms=None,
    pcm_first_ms=None,
    rounds: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """打断场景 LLM 裁判主入口

    以【模型回复音频 ai_wav】为主输入（裁判模型直接听回复，不过小 ASR），
    用户侧 ASR 转写 + 环境声事件作为文本时间线上下文。

    Args:
        scene: 指定具体场景名（如 '插话打断'/'停止指令'等），为空则评估全部打断场景
        model: LLM 模型名，缺省读 config.LLM_JUDGE.default_model
        max_tokens: 最大输出 token 数
        temperature: 采样温度，评判场景建议低温 0.1
        ai_wav: 模型回复音频路径（主输入，被判定对象）
        user_wav: 用户通道音频路径（用于生成用户侧 ASR 时间线上下文）
        env_events: 环境声事件列表 [{start_s, end_s, label}]
        start_ms / end_ms / pcm_first_ms: 环境声播放的绝对毫秒 + 模型音频起点毫秒
        rounds: 多轮文本数据（可作额外上下文）

    Returns:
        dict: {
            'enabled': True,
            'model': str,
            'scene': str,
            'ai_wav': str,
            'evaluations': [{scene, behavior, reason}, ...],
            'tokens_used': int,
            'input_token': int,
            'output_token': int,
            'message': str,
        }
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    if not model:
        model = llm_config.get('default_model', 'gpt-4o')

    # 主音频：ai_wav（模型回复，被判定对象）
    if not ai_wav or not os.path.isfile(ai_wav):
        raise FileNotFoundError(
            f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        )

    file_paths: List[str] = [ai_wav]

    # legacy：额外录屏/音频文件
    file_paths.extend(extract_video_paths(kwargs))

    # ── 构建文本时间线（用户侧 ASR + 环境声事件） ──
    user_chunks: Optional[List[Dict[str, Any]]] = None
    if user_wav and os.path.isfile(user_wav):
        user_chunks = get_asr_chunks(user_wav)

    events = env_events
    if not events:
        events = env_events_from_ms(start_ms, end_ms, pcm_first_ms)

    timeline_text = build_timeline_text(user_chunks, events)
    prompt = build_interruption_prompt(scene, timeline_text)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'scene': scene,
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
        f'[interruption_judge] scene={scene or "ALL"} '
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
    parser.add_argument('--scene', default='',
                        help='指定具体场景名（如 插话打断/停止指令/恢复原话题），为空则评估全部')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    parser.add_argument('--model', default='', help='LLM 模型名')
    parser.add_argument('--max_tokens', type=int, default=4096)
    parser.add_argument('--temperature', type=float, default=0.1)
    args = parser.parse_args()

    r = evaluate_interruption_judge(
        ai_wav=args.ai_wav,
        user_wav=args.user_wav,
        scene=args.scene,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'场景: {r.get("scene", "") or "ALL"}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for ev in r.get('evaluations', []):
        print(f'\n  场景: {ev.get("scene", "")}')
        print(f'  行为: {ev.get("behavior", "")}')
        print(f'  理由: {ev.get("reason", "")}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
