# -*- coding: utf-8 -*-
"""流式道「按事件切轮」切分器（A2 / INT-1790）。

被测 API 的流式事件与「轮次」不是一一对应（A0 / INT-1788 §3.2）：SSE / gRPC
server-stream 是「一问多回」，轮次边界由**句子结束标记**决定，零句子声明时退化
为「一条 message = 一轮」。

本模块只做纯切分，不碰网络、不碰落库，便于单测：
- 输入：`NormalizedEvent.payload`（wire payload，已归一为 dict）+ 事件时间戳；
- 输出：已闭合的轮次草稿（`StreamRoundDraft`），由执行器补齐编号 / 评估字段。

映射键沿用 `api_driver_adapter.py` 存量的五个 meta 键（A0 §3.2「不新造键名」）：
`asr_mapping` / `trans_mapping` / `sentence_end_mapping` / `session_end_mapping` /
`append_mode`。业务码取 `error_code_mapping`（缺省 `code`）/ `error_msg_mapping`
（缺省 `msg`）。

`append_mode` 语义（与存量 WS 解析一致）：
- `True`  → 轮内所有非空文本按出现顺序拼接；
- `False` → 取轮内最后一条非空文本。
"""
from shared.utils.path_extractor import extract_by_path

# 五个通用映射键（A0 §3.2 / api_driver_adapter.py:523-528），不新增键名
MAPPING_KEYS = (
    'asr_mapping',
    'trans_mapping',
    'sentence_end_mapping',
    'session_end_mapping',
    'append_mode',
)

DEFAULT_ASR_MAPPING = 'asr_result'
DEFAULT_TRANS_MAPPING = 'translation_result'
DEFAULT_SESSION_END_MAPPING = 'session_finished'
DEFAULT_ERROR_CODE_MAPPING = 'code'
DEFAULT_ERROR_MSG_MAPPING = 'msg'


class StreamRoundDraft:
    """已闭合的轮次草稿（执行器据此生成 ``rounds[i]``）"""

    __slots__ = (
        'payloads', 'asr_parts', 'trans_parts', 'asr', 'trans',
        'event_count', 'first_ts', 'last_ts', 'sentence_end', 'session_end',
        'biz_code', 'biz_msg',
    )

    def __init__(self):
        self.payloads = []
        self.asr_parts = []
        self.trans_parts = []
        self.asr = ''
        self.trans = ''
        self.event_count = 0
        self.first_ts = None
        self.last_ts = None
        self.sentence_end = False
        self.session_end = False
        self.biz_code = None
        self.biz_msg = None

    @property
    def text(self) -> str:
        """轮次文本：优先 ASR，其次翻译（与存量流式聚合口径一致）"""
        return self.asr or self.trans

    def to_dict(self) -> dict:
        return {
            'asr': self.asr,
            'trans': self.trans,
            'text': self.text,
            'event_count': self.event_count,
            'sentence_end': self.sentence_end,
            'session_end': self.session_end,
            'biz_code': self.biz_code,
            'biz_msg': self.biz_msg,
        }


class StreamRoundSplitter:
    """按事件切轮：句子边界优先，零句子声明退化为一条 message 一轮。"""

    def __init__(self, meta=None):
        meta = meta if isinstance(meta, dict) else {}
        self._meta = meta
        sentence_path = meta.get('sentence_end_mapping')
        # 零声明（缺键 / 空串）→ 「一条 message = 一轮」
        self._sentence_path = str(sentence_path).strip() if sentence_path else ''
        self._asr_path = meta.get('asr_mapping') or DEFAULT_ASR_MAPPING
        self._trans_path = meta.get('trans_mapping') or DEFAULT_TRANS_MAPPING
        self._session_path = (
            meta.get('session_end_mapping') or DEFAULT_SESSION_END_MAPPING)
        self._error_code_path = (
            meta.get('error_code_mapping') or DEFAULT_ERROR_CODE_MAPPING)
        self._error_msg_path = (
            meta.get('error_msg_mapping') or DEFAULT_ERROR_MSG_MAPPING)
        self._append_mode = bool(meta.get('append_mode'))
        self._draft = None

    # ── 只读属性（诊断 / 日志用）──
    @property
    def sentence_boundary_declared(self) -> bool:
        """是否声明了句子结束路径（零声明时按「一条 message = 一轮」切）"""
        return bool(self._sentence_path)

    @property
    def append_mode(self) -> bool:
        return self._append_mode

    # ── 切分主流程 ──
    def feed(self, payload, ts=None):
        """喂入一条 message 事件的 wire payload，返回本次闭合的轮次草稿列表。

        - 声明了 `sentence_end_mapping`：该字段为真的那条事件结束一轮；
        - 零声明：本条 message 立即结束一轮。
        """
        data = self._data_root(payload)
        draft = self._draft or StreamRoundDraft()
        self._draft = draft

        draft.payloads.append(payload)
        draft.event_count += 1
        if ts is not None:
            if draft.first_ts is None:
                draft.first_ts = ts
            draft.last_ts = ts

        asr_val = extract_by_path(data, self._asr_path)
        trans_val = extract_by_path(data, self._trans_path)
        if isinstance(asr_val, str) and asr_val:
            draft.asr_parts.append(asr_val)
        if isinstance(trans_val, str) and trans_val:
            draft.trans_parts.append(trans_val)
        draft.asr = self._join(draft.asr_parts)
        draft.trans = self._join(draft.trans_parts)

        biz_code = extract_by_path(payload, self._error_code_path)
        if biz_code is not None and str(biz_code) != '0':
            draft.biz_code = biz_code
            draft.biz_msg = extract_by_path(payload, self._error_msg_path)

        if extract_by_path(data, self._session_path) is True:
            draft.session_end = True

        closed = []
        if not self._sentence_path:
            draft.sentence_end = True
            closed.append(self._close())
        else:
            marker = extract_by_path(data, self._sentence_path)
            if marker is True:
                draft.sentence_end = True
                closed.append(self._close())
        if draft.session_end and self._draft is draft:
            # 会话结束但句子标记未到：会话收尾仍要把这一段作为一轮交出
            closed.append(self._close())
        return [item for item in closed if item is not None]

    def flush(self):
        """流结束（end_stream / 会话结束）时交出未闭合的残轮"""
        if self._draft is None:
            return []
        draft = self._close()
        return [draft] if draft is not None else []

    # ── 内部 ──
    @staticmethod
    def _data_root(payload):
        """wire payload 取值根：标准格式 ``{"code":0,"data":{...}}`` 取 data，
        否则取 payload 顶层（与 api_driver_adapter 单条响应解析同口径）。"""
        if isinstance(payload, dict):
            inner = payload.get('data')
            if isinstance(inner, dict):
                return inner
        return payload

    def _join(self, parts):
        if not parts:
            return ''
        return ''.join(parts) if self._append_mode else parts[-1]

    def _close(self):
        draft = self._draft
        self._draft = None
        if draft is None:
            return None
        if draft.event_count == 0:
            return None
        return draft
