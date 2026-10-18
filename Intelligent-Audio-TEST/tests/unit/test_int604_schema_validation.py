# -*- coding: utf-8 -*-
"""INT-604 网关 schema 校验：TaskCreateRequest 的 execution_mode / serial_first。

验收标准 1 的补充：显式字段枚举校验（拒绝魔法字符串/非法值），缺省口径
（parallel / device）与显式合法值均通过。
"""
import pytest
from pydantic import ValidationError


def _make(**kwargs):
    from api_gateway.schemas.task import TaskCreateRequest
    base = {'name': 'INT-604 schema 校验任务'}
    base.update(kwargs)
    return TaskCreateRequest(**base)


class TestExecutionModeValidation:
    def test_default_parallel_device(self):
        req = _make()
        assert req.execution_mode == 'parallel'
        assert req.serial_first == 'device'

    def test_valid_values_accepted(self):
        for mode in ('parallel', 'serial'):
            for first in ('device', 'api'):
                req = _make(execution_mode=mode, serial_first=first)
                assert req.execution_mode == mode
                assert req.serial_first == first

    def test_invalid_execution_mode_rejected(self):
        with pytest.raises(ValidationError):
            _make(execution_mode='mixed')

    def test_invalid_serial_first_rejected(self):
        with pytest.raises(ValidationError):
            _make(serial_first='both')

    def test_none_explicitly_nullable(self):
        """显式 None（Optional 字段）允许——与 TaskCreateRequest 既有可空口径一致。"""
        req = _make(execution_mode=None, serial_first=None)
        assert req.execution_mode is None
        assert req.serial_first is None
