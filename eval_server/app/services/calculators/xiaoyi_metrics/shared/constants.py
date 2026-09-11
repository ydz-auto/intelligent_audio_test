# -*- coding: utf-8 -*-
"""xiaoyi_metrics 共享常量

所有子包共用的魔法数字/魔法字符串集中于此，
各子包可自行覆盖默认值。
"""
import os

# ─────────── LLM 配置 ───────────
LLM_DEFAULT_TIMEOUT = 300
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2  # 秒
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_DEFAULT_MAX_TOKENS = 4096
LLM_DEFAULT_MODEL = 'gpt-4o'          # 未配置 default_model 时的兜底模型名
LLM_JUDGE_MAX_TOKENS = 1024           # llm_judge 评分输出较小，用更小的 max_tokens
LLM_HTTP_CONNECT_TIMEOUT = 10.0       # httpx 连接超时（秒），读/写/池用 LLM_DEFAULT_TIMEOUT

# ─────────── ASR 配置 ───────────
ASR_USER_SEG_MERGE_GAP_S = 1.5
ASR_MODEL_SEG_MERGE_GAP_S = 0.7
ASR_HIGH_FREQ_SEG_MERGE_GAP_S = 0.7
ASR_NON_INTERACTIVE_SEG_MERGE_GAP_S = 0.7

# ─────────── 时序阈值 ───────────
TURN_DURATION_THRESHOLD = 1.0  # tor 命中词时长阈值(秒)
TURN_NUM_WORDS_THRESHOLD = 3   # tor 命中词去标点总字符数阈值

PAUSE_MIN_GAP = 0.2  # pause 区间最小间隙(秒)
PAUSE_MAX_GAP = 3.0  # pause 区间最大间隙(秒)

YIELD_GRACE_S = 0.5  # 让出宽限(秒)
EPS_S = 1e-6          # 浮点容差(秒)

MS_PER_S = 1000.0    # 秒→毫秒转换因子
ROUND_DIGITS = 3      # 数值聚合保留小数位

# ─────────── 接管时延（legacy 链路）───────────
TAKEOVER_OFFSET_MS = 40              # legacy 录屏 ASR 首词时延补偿（毫秒）
TAKEOVER_FIRST_FRAME_OFFSET_MS = 100  # legacy 首帧时间戳固定偏移（毫秒）

# ─────────── LLM 时间线展示截断 ───────────
TIMELINE_MAX_ITEMS_CHUNKS = 30  # LLM prompt 中 chunks 时间线最大展示条数
TIMELINE_MAX_ITEMS_PAUSES = 20  # LLM prompt 中 pause 时间线最大展示条数

# ─────────── 相似度阈值 ───────────
INPUT_ASR_SIMILARITY_THRESHOLD = 0.8  # 输入识别准确率匹配阈值

# ─────────── 文件扩展名 ───────────
AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.opus', '.m4a'}
VIDEO_EXTS = {
    '.mp4', '.avi', '.mkv', '.webm', '.mov', '.flv',
    '.wmv', '.m4v', '.ts', '.3gp',
}

# ─────────── 行为分类标签 ───────────
BEHAVIOR_LABELS = ['回应', '恢复', '不确定询问', '未知']
BEHAVIOR_FIELD_MAP = {
    '回应': 'behavior_respond',
    '恢复': 'behavior_recover',
    '不确定询问': 'behavior_uncertain',
    '未知': 'behavior_unknown',
}
