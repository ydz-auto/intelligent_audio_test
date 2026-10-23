# -*- coding: utf-8 -*-
"""音频域异常。

INT-1533：标签名 → task_service 标签 ID 的跨域解析失败时抛出
TagResolutionError。调用方不得把它降级成「tag_id=None 照常落库」——
那会写出 audio_tags.tag_id 为 NULL 的脏关联行，同时接口还回成功。
"""
from __future__ import annotations


class TagResolutionError(RuntimeError):
    """标签解析失败：task_service 不可达，或标签创建被拒。

    Attributes:
        tag_name: 解析失败的标签名。
    """

    def __init__(self, tag_name: str, detail: str = ''):
        self.tag_name = tag_name
        self.detail = detail
        message = f'标签「{tag_name}」解析失败'
        if detail:
            message = f'{message}：{detail}'
        super().__init__(message)
