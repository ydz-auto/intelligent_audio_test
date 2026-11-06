# -*- coding: utf-8 -*-
"""音频域异常。

INT-1533：标签名 → task_service 标签 ID 的跨域解析失败时抛出
TagResolutionError。调用方不得把它降级成「tag_id=None 照常落库」——
那会写出 audio_tags.tag_id 为 NULL 的脏关联行，同时接口还回成功。

INT-1668：task_service 拒绝建用例（CreateTestCaseConfig 返回 success=false
或 gRPC 异常）时抛出 TestCaseCreationError。调用方不得吞掉它——吞掉会让
合并/秒传接口回 success=true 而 test_case_id=null，上游误判为「列表缓存延迟」。
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


class InvalidAudioContentError(RuntimeError):
    """上传内容不是可解析的音频：空文件、纯文本改名、时长 ≤ 0 或参数无效。

    INT-2202：上传/合并链路必须在入库前探测真实音频参数，探测失败或时长为 0
    时抛本异常。调用方不得用默认值兜底（旧行为会把 0 字节/非音频 .wav 落库成
    duration=0），而应把该文件判失败、返回原因并清理临时分片。
    """

    def __init__(self, detail: str = ''):
        self.detail = detail
        message = '音频内容无效'
        if detail:
            message = f'{message}：{detail}'
        super().__init__(message)


class TestCaseCreationError(RuntimeError):
    """测试用例创建失败：task_service 拒绝，或 gRPC 调用不可用。

    Attributes:
        detail: 后端原文（task_service 返回的 message 或 gRPC 异常文本）。
    """

    # 类名以 Test 开头，避免 pytest 在导入本模块的测试里把它当测试类收集
    __test__ = False

    def __init__(self, detail: str = ''):
        self.detail = detail
        message = '创建测试用例失败'
        if detail:
            message = f'{message}：{detail}'
        super().__init__(message)
