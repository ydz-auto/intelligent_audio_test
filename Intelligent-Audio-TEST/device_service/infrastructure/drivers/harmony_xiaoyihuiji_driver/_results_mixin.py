# -*- coding: utf-8 -*-
"""小艺慧记驱动结果处理门面

原 749 行大文件拆分为职责单一的模块，本文件保留原类名与导入路径：
- _results_collect_mixin.ResultsCollectMixin: 结果采集（设备 UI 导出 + hdc 拉取 + OSS 上传）
- _results_parse_mixin.ResultsParseMixin: 存档解析（ASR 日志 -> STM/RTTM）
- _asr_parsers: ASR 日志纯函数解析器
"""
from ._results_collect_mixin import ResultsCollectMixin


class ResultsMixin(ResultsCollectMixin):
    """结果获取与存档解析方法（get_results / extract_results_from_archive）"""
