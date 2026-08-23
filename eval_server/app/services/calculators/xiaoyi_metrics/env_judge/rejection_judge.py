# -*- coding: utf-8 -*-
"""rejection_judge.py
拒识场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，评估模型在拒识场景下的行为

场景:
    1. 旁人交谈静默 — 模型应保持沉默
    2. 环境噪声不触发 — 模型不应被噪声触发
    3. 反馈词不误触发 — 短反馈词不应触发回复
    4. 生理声不触发 — 咳嗽/喷嚏/笑声不应触发回复
    5. 环境事件被动记录与回溯 — 环境事件时沉默，用户询问时回应

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
REJECTION_SCENES = {
    '旁人交谈': {
        'name': '场景-旁人交谈静默',
        'definition': '目标用户正在与旁边的人交谈（非与模型对话），模型应保持静默，不应插话、不应回应。',
        'expect': '沉默',
    },
    '环境噪声': {
        'name': '场景-环境噪声不触发',
        'definition': '录屏中出现环境噪声（如关门声、交通噪声、音乐声等非语音噪声），模型不应被噪声触发而产生回复。',
        'expect': '沉默',
    },
    '反馈词': {
        'name': '场景-反馈词不误触发',
        'definition': '用户在交互过程中发出"嗯""啊""好的""对"等短反馈词，这些词不具备发起新请求的意图，模型不应将其视为有效指令而接管对话。',
        'expect': '沉默',
    },
    '生理声': {
        'name': '场景-生理声不触发',
        'definition': '用户出现咳嗽、喷嚏、笑声等非语言意图的生理性声音，模型不应因此触发回复。',
        'expect': '沉默',
    },
    '环境回溯': {
        'name': '场景-环境事件被动记录与回溯',
        'definition': '在交互过程中，背景出现可识别的环境事件（如地铁广播、公交报站、闹钟等），模型不主动回应该环境事件，但应能持续记录。当用户随后主动询问该环境事件相关内容时（如"刚才广播说了什么"），模型应能识别并基于已记录的环境信息进行回复。',
        'expect': '在环境事件出现时保持沉默，在用户主动询问时给出回应',
    },
}

# 行为类别定义
REJECTION_BEHAVIORS = """- 回应：模型针对用户的真实意图或主动询问给出了直接、相关的回复。包括场景5中用户询问环境事件后模型正确识别并作答的情况。
- 恢复：模型未直接回应当前输入，但其回复内容已自然回到此前的话题或交互主线，体现出对话恢复能力。
- 询问：模型对用户的意图进行追问、澄清或确认（如"您是想了解……吗？"），而非直接给出答案。
- 无关回复：模型产生了回复，但内容与当前用户意图、对话上下文或场景要求无关。包括本应沉默却给出了回复。
- 沉默：模型未产生任何有效回复（无声、空回复、兜底拒答等）。"""


# ─────────── prompt 构建 ───────────
def build_rejection_prompt(scene: str = '',
                           timeline_text: str = '') -> str:
    """构建拒识场景评估 prompt

    Args:
        scene: 指定具体场景名（如 '旁人交谈'），为空则输出全部场景
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

    if scene and scene in REJECTION_SCENES:
        # ── 单场景 prompt ──
        sc = REJECTION_SCENES[scene]
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

{REJECTION_BEHAVIORS}

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
        for i, (key, sc) in enumerate(REJECTION_SCENES.items(), 1):
            scene_blocks.append(
                f"场景{i} — {sc['name'].replace('场景-', '')}\n"
                f"  {sc['definition']}\n"
                f"  期望行为：{sc['expect']}。"
            )
        scenes_text = '\n\n'.join(scene_blocks)

        eval_items = []
        for i, (key, sc) in enumerate(REJECTION_SCENES.items(), 1):
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

{REJECTION_BEHAVIORS}

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
def evaluate_rejection_judge(
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
    """拒识场景 LLM 裁判主入口

    以【模型回复音频 ai_wav】为主输入（裁判模型直接听回复，不过小 ASR），
    用户侧 ASR 转写 + 环境声事件作为文本时间线上下文。

    Args:
        scene: 指定具体场景名（如 '旁人交谈'/'环境噪声'等），为空则评估全部拒识场景
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
    prompt = build_rejection_prompt(scene, timeline_text)

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
        f'[rejection_judge] scene={scene or "ALL"} '
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
    parser.add_argument('--scene', default='',
                        help='指定具体场景名（如 旁人交谈/环境噪声/反馈词/生理声/环境回溯），为空则评估全部')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    parser.add_argument('--model', default='', help='LLM 模型名')
    parser.add_argument('--max_tokens', type=int, default=4096)
    parser.add_argument('--temperature', type=float, default=0.1)
    args = parser.parse_args()

    r = evaluate_rejection_judge(
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
